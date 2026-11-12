from __future__ import annotations
import asyncio
import hashlib
import json
import os
import secrets
import shutil
import signal
import tempfile
from pathlib import Path
from .config import Config, Profile
from .evidence import Store
from .schemas import EvidenceReceipt, RunManifest, TestRequest
from .security import PolicyError, atomic_write, digest, now, object_hash, redact
from .snapshot import verify_source


class ProcessResult:
    def __init__(self, code, stdout, stderr, out_hash, err_hash, truncated, timeout=False,
                 output_complete=True, execution_seconds=0.0, cleanup_seconds=0.0):
        self.code, self.stdout, self.stderr = code, stdout, stderr
        self.out_hash, self.err_hash, self.truncated, self.timeout = out_hash, err_hash, truncated, timeout
        self.output_complete = output_complete
        self.execution_seconds, self.cleanup_seconds = execution_seconds, cleanup_seconds


PROCESS_CLEANUP_SECONDS = 0.25


async def process(argv: list[str], timeout: float, limit: int = 64000) -> ProcessResult:
    """Trusted controller argv; execution + pipe drainage share the timeout.

    A separate, bounded cleanup allowance kills the dedicated POSIX process group.
    Hashes cover all bytes actually drained (including bytes beyond retention).
    If pipes cannot reach EOF during cleanup, output_complete is false and hashes
    describe only the observed prefix; output_truncated also remains true.
    """
    if os.name != "posix":
        raise PolicyError("encerramento de subprocessos requer sessão POSIX exclusiva")
    loop = asyncio.get_running_loop()
    started = loop.time()
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": "/nonexistent", "LANG": "C.UTF-8"}
    proc = await asyncio.create_subprocess_exec(*argv, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE, env=env, start_new_session=True)
    captures = [{"hash": hashlib.sha256(), "buffer": bytearray(), "size": 0, "complete": False} for _ in range(2)]

    async def drain(stream, capture):
        while data := await stream.read(8192):
            capture["hash"].update(data)
            capture["size"] += len(data)
            capture["buffer"].extend(data[:max(0, limit - len(capture["buffer"]))])
        capture["complete"] = True

    tasks = [asyncio.create_task(proc.wait()), asyncio.create_task(drain(proc.stdout, captures[0])),
             asyncio.create_task(drain(proc.stderr, captures[1]))]

    def kill_group():
        # start_new_session guarantees pgid == child pid, never controller pgid.
        # Kill even after the parent exits: descendants may still hold pipes.
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    async def cleanup():
        kill_group()
        _, pending = await asyncio.wait(tasks, timeout=PROCESS_CLEANUP_SECONDS)
        if pending:
            # asyncio.Process offers no public operation to close inherited pipes.
            # Closing its transport detaches stuck descriptors before cancellation.
            proc._transport.close()
            for task in pending:
                task.cancel()
        # Only local drain/proc.wait tasks remain; cancellation does not run any
        # user callbacks or wait for a descendant's EOF.
        await asyncio.gather(*tasks, return_exceptions=True)

    timed_out = False
    cleanup_seconds = 0.0
    try:
        _, pending = await asyncio.wait(tasks, timeout=max(0.0, started + timeout - loop.time()))
        execution_seconds = loop.time() - started
        timed_out = bool(pending)
        if not pending:
            for task in tasks:
                task.result()
    except BaseException:
        # Shield cleanup against further cancellation while preserving the
        # original cancellation/error and ensuring no background tasks survive.
        cleanup_task = asyncio.create_task(cleanup())
        while not cleanup_task.done():
            try:
                await asyncio.shield(cleanup_task)
            except asyncio.CancelledError:
                continue
        cleanup_task.result()
        raise
    if timed_out:
        cleanup_started = loop.time()
        cleanup_task = asyncio.create_task(cleanup())
        try:
            await asyncio.shield(cleanup_task)
        except asyncio.CancelledError:
            while not cleanup_task.done():
                try:
                    await asyncio.shield(cleanup_task)
                except asyncio.CancelledError:
                    continue
            cleanup_task.result()
            raise
        cleanup_seconds = loop.time() - cleanup_started
    out, err = captures
    complete = all(c["complete"] for c in captures)
    return ProcessResult(proc.returncode, redact(out["buffer"].decode(errors="replace")),
        redact(err["buffer"].decode(errors="replace")), out["hash"].hexdigest(), err["hash"].hexdigest(),
        not complete or any(c["size"] > limit for c in captures), timed_out,
        complete, execution_seconds, cleanup_seconds)


def validate_image(image: str):
    import re
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/@:-]{1,200}", image) or (":" not in image and "@sha256:" not in image) or image.endswith(":latest"):
        raise PolicyError("imagem requer versão explícita/digest")


def test_argv(request: TestRequest, profile: Profile) -> list[str]:
    if request.kind == "baseline":
        if request.script:
            raise PolicyError("baseline não aceita script arbitrário")
        if not profile.baseline:
            raise PolicyError("perfil sem teste de base")
        argv = profile.baseline
        if argv[0] not in {"python", "python3", "php", "node", "wp", "phpunit"} or any("\x00" in a or len(a) > 4096 for a in argv):
            raise PolicyError("argv de base não permitido")
        return argv
    if request.kind not in profile.languages or not request.script.strip():
        raise PolicyError("linguagem não permitida ou reprodução vazia")
    return {"python": ["python", "-B", "/test/repro.py"], "php": ["php", "/test/repro.php"], "browser": ["node", "/test/repro.cjs"], "wp-cli": ["wp", "--path=/work/wordpress", "eval-file", "/test/repro.php"]}[request.kind]


def docker_create(name: str, image: str, source: Path, script_dir: Path, profile: Profile, argv: list[str]):
    for p in (source, script_dir):
        if any(c in str(p) for c in (",", "\n", "\x00")):
            raise PolicyError("caminho de montagem inválido")
    return ["docker", "create", "--name", name, "--pull=never", "--network=none", "--read-only", "--user=65534:65534",
        "--cap-drop=ALL", "--security-opt=no-new-privileges", "--pids-limit", str(profile.pids),
        "--memory", f"{profile.memory_mb}m", "--memory-swap", f"{profile.memory_mb}m", "--cpus", str(profile.cpus),
        "--ulimit", "nofile=256:256", "--ipc=private", "--log-driver=none", "--workdir=/work",
        "--tmpfs", "/tmp:rw,nosuid,nodev,noexec,size=64m,mode=1777", "--tmpfs", "/work:rw,nosuid,nodev,size=128m,mode=1777",
        "--mount", f"type=bind,source={source},target=/source,readonly",
        "--mount", f"type=bind,source={script_dir},target=/test,readonly",
        "--env", "HOME=/tmp", "--env", "PYTHONDONTWRITEBYTECODE=1", "--env", "PYTHONPATH=/source",
        "--entrypoint", argv[0], image, *argv[1:]]


def verify_container(info: dict, source: Path, script_dir: Path, profile: Profile):
    host = info["HostConfig"]
    if host.get("Privileged") or not host.get("ReadonlyRootfs") or host.get("NetworkMode") != "none":
        raise PolicyError("isolamento de rede/rootfs inválido")
    if info["Config"].get("User") != "65534:65534" or "ALL" not in host.get("CapDrop", []) or host.get("CapAdd"):
        raise PolicyError("privilégios excessivos")
    if not any(x.startswith("no-new-privileges") for x in host.get("SecurityOpt", [])):
        raise PolicyError("no-new-privileges ausente")
    if host.get("PidMode") == "host" or host.get("IpcMode") == "host" or host.get("Devices") or host.get("Binds") or host.get("PortBindings"):
        raise PolicyError("acesso ao host")
    if not 0 < host.get("Memory", 0) <= profile.memory_mb * 1024**2 or not 0 < host.get("PidsLimit", 0) <= profile.pids:
        raise PolicyError("limites de recursos ausentes")
    if not 0 < host.get("NanoCpus", 0) <= int(profile.cpus * 1e9):
        raise PolicyError("limite de CPU ausente")
    mounts = [m for m in info.get("Mounts", []) if m.get("Type") != "tmpfs"]
    allowed = {("/source", str(source)), ("/test", str(script_dir))}
    if len(mounts) != 2 or {(m["Destination"], m["Source"]) for m in mounts} != allowed or any(m.get("RW") for m in mounts):
        raise PolicyError("montagens inesperadas")
    for item in info["Config"].get("Env", []):
        name = item.split("=", 1)[0].upper()
        if any(x in name for x in ("TOKEN", "SECRET", "API_KEY", "SSH_AUTH", "AWS_")):
            raise PolicyError("credencial na imagem")


class Executor:
    def __init__(self, store: Store, manifest: RunManifest, config: Config, profile: Profile):
        self.store, self.manifest, self.config, self.profile = store, manifest, config, profile
        self.lock = asyncio.Lock()

    async def execute(self, request: TestRequest, owner: str, phase: str) -> EvidenceReceipt:
        async with self.lock:
            return await self._execute(request, owner, phase)

    async def _execute(self, request: TestRequest, owner: str, phase: str) -> EvidenceReceipt:
        run_id = self.manifest.run_id
        verify_source(self.store, self.manifest)
        argv = test_argv(request, self.profile)
        fingerprint = object_hash({"source": self.manifest.source_id, "profile": self.manifest.profile_hash, "kind": request.kind, "script": request.script})
        # A crash after starting Docker but before a receipt is not a failed test
        # and cannot trigger a fresh reproduction automatically on resume.
        from .agents import RuntimePaused
        for name in self.store.names(run_id, "execution-attempts"):
            attempt = self.store.get(run_id, "execution-attempts/" + name)
            if attempt["fingerprint"] == fingerprint and attempt["owner"] == owner and attempt["status"] in {"running", "ambiguous"}:
                if attempt["status"] == "ambiguous" or not self.store.exists(run_id, "receipts/" + attempt["receipt_id"]):
                    raise RuntimePaused("Execução Docker ambígua sem receipt; não será repetida automaticamente")
        previous = [EvidenceReceipt.model_validate(self.store.get(run_id, "receipts/" + n)) for n in self.store.names(run_id, "receipts")]
        allowed_owners = {owner, "baseline"} if request.kind == "baseline" else {owner}
        equivalent = [r for r in previous if r.fingerprint == fingerprint and r.owner in allowed_owners and r.execution != "not_executed"]
        if equivalent and not request.repeat_reason:
            self.store.event(run_id, "receipt_reused", {"id": equivalent[-1].id, "owner": owner})
            return equivalent[-1]
        if equivalent and len(equivalent) > self.config.limits.max_repeats:
            raise PolicyError("limite de repetições")
        if request.repeat_reason == "confirm_failure" and equivalent and equivalent[-1].status != "failed":
            raise PolicyError("confirmação de falha sem falha anterior")
        if owner != "baseline" and sum(r.owner != "baseline" for r in previous) >= self.config.limits.max_reproductions:
            raise PolicyError("limite de novas reproduções")
        receipt_id = secrets.token_hex(12)
        start = now()
        result = ProcessResult(None, "", "", digest(b""), digest(b""), False)
        status, execution, images, limitations = "blocked", "not_executed", {}, []
        versions = {}
        cancelled = False
        try:
            if not shutil.which("docker"):
                raise PolicyError("Docker indisponível; nenhum teste executado no host")
            version = await process(["docker", "version", "--format", "{{.Server.Version}}"], 15)
            if version.code:
                raise PolicyError("daemon Docker indisponível")
            versions["docker"] = version.stdout.strip()
            self.store.put(run_id, "execution-attempts/" + receipt_id, {"fingerprint": fingerprint, "owner": owner,
                "phase": phase, "receipt_id": receipt_id, "status": "running", "started_at": start}, immutable=True)
            if self.profile.engine == "compose":
                from .wordpress import execute_compose
                result, images = await execute_compose(self, request, argv, receipt_id)
                execution = "compose"
            else:
                validate_image(self.profile.image)
                image_result = await process(["docker", "image", "inspect", self.profile.image, "--format", "{{.Id}}"], 15)
                if image_result.code:
                    raise PolicyError("imagem não adquirida; aquisição é etapa explícita separada")
                image_id = image_result.stdout.strip()
                if not image_id.startswith("sha256:"):
                    raise PolicyError("imagem não resolvida em ID")
                images["runner"] = image_id
                # Freeze image resolution across retries/resume to keep environments equivalent.
                self.store.put(run_id, "resolved-images", images, immutable=True)
                with tempfile.TemporaryDirectory(prefix="audit3-test-") as directory:
                    script_dir = Path(directory)
                    script_dir.chmod(0o755)
                    suffix = {"python": "py", "php": "php", "browser": "cjs", "wp-cli": "php", "baseline": "txt"}[request.kind]
                    atomic_write(script_dir / ("repro." + suffix), request.script.encode(), 0o444)
                    name = "audit3-" + receipt_id
                    try:
                        created = await process(docker_create(name, image_id, self.store.path(run_id, "source"), script_dir, self.profile, argv), 20)
                        if created.code:
                            raise PolicyError("Docker create bloqueado: " + created.stderr[:1000])
                        inspected = await process(["docker", "inspect", name], 15)
                        verify_container(json.loads(inspected.stdout)[0], self.store.path(run_id, "source"), script_dir, self.profile)
                        result = await process(["docker", "start", "--attach", name], self.config.limits.test_timeout, self.config.limits.max_output_bytes)
                        execution = "docker"
                        if not result.timeout:
                            ended = await process(["docker", "inspect", name, "--format", "{{json .State}}"], 15)
                            state = json.loads(ended.stdout)
                            result.code = state["ExitCode"]
                            if state.get("OOMKilled"):
                                limitations.append("processo morto por limite de memória")
                    finally:
                        cleanup = await asyncio.shield(process(["docker", "rm", "--force", name], 20))
                        if cleanup.code:
                            raise PolicyError("remoção do container não confirmada: " + name)
            if result.timeout:
                limitations.append(f"Timeout do subprocesso: execução observada {result.execution_seconds:.3f}s; "
                    f"encerramento {result.cleanup_seconds:.3f}s (tolerância de drenagem {PROCESS_CLEANUP_SECONDS:.2f}s).")
            if not result.output_complete:
                limitations.append("Drenagem não atingiu EOF no prazo de encerramento; hashes cobrem somente os bytes observados.")
            status = "passed" if result.code == 0 and not result.timeout else "failed"
        except asyncio.CancelledError:
            status, cancelled = "cancelled", True
            limitations.append("cancelado; resultado do processo incompleto")
        except (PolicyError, OSError, ValueError, KeyError) as e:
            limitations.append(redact(str(e))[:2000])
        receipt = EvidenceReceipt(id=receipt_id, run_id=run_id, owner=owner, phase=phase, source_id=self.manifest.source_id,
            profile_hash=self.manifest.profile_hash, fingerprint=fingerprint, command=argv, image_ids=images, versions=versions,
            started_at=start, finished_at=now(), status=status, exit_code=result.code, timeout=result.timeout,
            stdout=result.stdout, stderr=result.stderr, stdout_sha256=result.out_hash, stderr_sha256=result.err_hash,
            output_truncated=result.truncated, script_sha256=digest(request.script.encode()) if request.script else None,
            purpose=request.purpose, limitations=limitations + ["Exit code não mede cobertura; contagens não fornecidas são desconhecidas."], execution=execution,
            artifacts={"stdout_in_receipt": result.out_hash, "stderr_in_receipt": result.err_hash, **({"submitted_test": digest(request.script.encode())} if request.script else {})})
        self.store.put(run_id, "receipts/" + receipt_id, receipt, immutable=True)
        self.store.put(run_id, "execution-attempts/" + receipt_id, {"fingerprint": fingerprint, "owner": owner,
            "phase": phase, "receipt_id": receipt_id, "status": "ambiguous" if cancelled else "confirmed", "finished_at": now()})
        # Reviewable test code: not model chain-of-thought; never executed by controller.
        self.store.put(run_id, "tests/" + receipt_id, {"script": redact(request.script), "repeat_reason": request.repeat_reason}, immutable=True)
        if cancelled:
            raise asyncio.CancelledError
        return receipt
