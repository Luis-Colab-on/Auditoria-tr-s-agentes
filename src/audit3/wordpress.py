from __future__ import annotations
import asyncio
import json
import tempfile
from importlib.resources import files
from pathlib import Path
from .executor import process, validate_image
from .security import PolicyError, atomic_write, canonical, digest, redact


# Vendored Moby default; extensions are restricted to Chromium sandbox setup.
BROWSER_SECCOMP_BASE_SHA256 = "15434cc9c9037d85b35027a60721bf45f381782b4283b01d94663366e71569f8"


def browser_seccomp_profile():
    data = files("audit3").joinpath("assets", "browser-seccomp-base.json").read_bytes()
    if digest(data) != BROWSER_SECCOMP_BASE_SHA256:
        raise PolicyError("perfil seccomp do navegador adulterado")
    profile = json.loads(data)
    profile["syscalls"].append({
        "comment": "Allow Chromium sandbox user namespaces (Playwright Docker guidance)",
        "names": ["clone", "setns", "unshare"], "action": "SCMP_ACT_ALLOW",
        "args": [], "includes": {}, "excludes": {}})
    # The base permits chroot only when the *container* initially has
    # CAP_SYS_CHROOT. We drop all outer capabilities. Chromium acquires scoped
    # capabilities in its own user namespace and chroots to an empty fdinfo dir
    # to remove filesystem access. Allow that syscall without adding outer caps.
    profile["syscalls"].append({
        "comment": "Allow Chromium DropFileSystemAccess in its own user namespace",
        "names": ["chroot"], "action": "SCMP_ACT_ALLOW",
        "args": [], "includes": {}, "excludes": {}})
    return profile


def compose_spec(profile, source: Path, test_dir: Path, assets: Path, images: dict, argv: list[str], kind: str):
    def bind(path, target):
        # Force the Mount API; Compose otherwise may serialize these as legacy Binds.
        # All sources are prepared beforehand; never auto-create missing host paths.
        return {"type": "bind", "source": str(path), "target": target, "read_only": True,
            "bind": {"create_host_path": False}}
    common = {"read_only": True, "cap_drop": ["ALL"], "security_opt": ["no-new-privileges:true"],
        "pids_limit": profile.pids, "mem_limit": f"{profile.memory_mb}m", "memswap_limit": f"{profile.memory_mb}m", "cpus": profile.cpus,
        "networks": ["isolated"], "restart": "no", "init": True, "logging": {"driver": "none"},
        "tmpfs": ["/tmp:rw,nosuid,nodev,noexec,size=64m,mode=1777"], "user": "1000:1000"}
    db = {**common, "image": images["db"], "user": "999:999", "environment": {"MYSQL_DATABASE": "audit3", "MYSQL_USER": "audit3", "MYSQL_PASSWORD": "synthetic-local-only", "MYSQL_ROOT_PASSWORD": "synthetic-root-only"},
        "tmpfs": common["tmpfs"] + ["/var/lib/mysql:rw,nosuid,nodev,size=512m,uid=999,gid=999", "/var/run/mysqld:rw,nosuid,nodev,size=16m,uid=999,gid=999"]}
    db_limit = profile.db_memory_mb if profile.db_memory_mb is not None else profile.memory_mb
    db.update(mem_limit=f"{db_limit}m", memswap_limit=f"{db_limit}m")
    wordpress = {**common, "image": images["wordpress"], "entrypoint": ["/bin/sh", "/opt/audit3/start-wordpress.sh"],
        "environment": {"HOME": "/tmp", "AUDIT3_PLUGIN_SLUG": profile.plugin_slug},
        "volumes": [bind(source, "/source"), bind(assets, "/opt/audit3"), bind(test_dir, "/test")],
        "tmpfs": common["tmpfs"] + ["/work:rw,nosuid,nodev,size=512m,mode=1777"]}
    services = {**common, "image": images["services"], "user": "65534:65534", "entrypoint": ["python", "-B", "/opt/audit3/simulators.py"], "volumes": [bind(assets, "/opt/audit3")]}
    runner = {**common, "image": images["browser"] if kind == "browser" else images["wordpress"], "working_dir": "/work", "entrypoint": argv,
        "environment": {"HOME": "/tmp", "NODE_PATH": "/opt/browser/node_modules", "AUDIT3_BASE_URL": "http://wordpress:8080"},
        "volumes": [bind(source, "/source"), bind(test_dir, "/test")],
        "tmpfs": common["tmpfs"] + ["/work:rw,nosuid,nodev,size=256m,mode=1777"], "shm_size": "256m"}
    if kind == "browser":
        # Per-container profile; retain Chromium sandbox, caps=none and NNP.
        runner["security_opt"] = ["no-new-privileges:true", "seccomp=" + str(assets / "browser-seccomp.json")]
    # Capture bootstrap failures locally with finite rotation, never a remote log driver.
    # These containers receive only synthetic data. Their logs are collected before removal.
    for service in (db, wordpress, services):
        service["logging"] = {"driver": "local", "options": {"max-size": "1m", "max-file": "1", "compress": "false"}}
    return {"services": {"db": db, "wordpress": wordpress, "services": services, "runner": runner},
        "networks": {"isolated": {"driver": "bridge", "internal": True, "enable_ipv6": False, "driver_opts": {"com.docker.network.bridge.gateway_mode_ipv4": "isolated"}}}}


def verify_compose_container(info, expected, network_name):
    h = info["HostConfig"]
    if h.get("Privileged") or not h.get("ReadonlyRootfs") or h.get("CapAdd") or "ALL" not in h.get("CapDrop", []):
        raise PolicyError("Compose sem isolamento de privilégios")
    if info["Config"].get("User") != expected["user"]:
        raise PolicyError("Compose usuário/security-opt inesperado")
    security = h.get("SecurityOpt", [])
    nnp = {"no-new-privileges", "no-new-privileges:true", "no-new-privileges=true"}
    want_seccomp = [opt for opt in expected.get("security_opt", []) if opt.startswith("seccomp=")]
    actual_seccomp = [opt for opt in security if opt.startswith("seccomp=")]
    if len([opt for opt in security if opt in nnp]) != 1 or any(opt not in nnp and not opt.startswith("seccomp=") for opt in security):
        raise PolicyError("Compose security-opt inesperado")
    if len(actual_seccomp) != len(want_seccomp) or len(want_seccomp) > 1:
        raise PolicyError("Compose perfil seccomp ausente/inesperado")
    if want_seccomp:
        if Path(want_seccomp[0].partition("=")[2]).name != "browser-seccomp.json":
            raise PolicyError("Compose perfil seccomp não autorizado")
        try:
            # Compose embeds the JSON file in Engine SecurityOpt. A path or
            # 'unconfined' is not proof of the profile actually installed.
            observed_profile = json.loads(actual_seccomp[0].partition("=")[2])
        except (ValueError, TypeError):
            raise PolicyError("Compose perfil seccomp não verificável") from None
        if observed_profile != browser_seccomp_profile():
            raise PolicyError("Compose perfil seccomp divergente")
    host_access = [name for name in ("PidMode", "IpcMode") if h.get(name) == "host"]
    host_access += [name for name in ("Devices", "PortBindings", "Binds") if h.get(name)]
    if host_access:
        raise PolicyError("Compose expõe host: " + ", ".join(host_access))
    if not h.get("Memory") or not h.get("NanoCpus") or not h.get("PidsLimit"):
        raise PolicyError("Compose sem limites")
    for expected_key, observed_key in (("mem_limit", "Memory"), ("memswap_limit", "MemorySwap")):
        if expected_key in expected and h.get(observed_key) != int(expected[expected_key][:-1]) * 1024**2:
            raise PolicyError("Compose limite de memória/swap divergente")
    if "logging" in expected:
        logging = h.get("LogConfig", {})
        if logging.get("Type") != expected["logging"]["driver"] or any(
                logging.get("Config", {}).get(key) != value for key, value in expected["logging"].get("options", {}).items()):
            raise PolicyError("Compose logging local/limites divergentes")
    if set(info["NetworkSettings"]["Networks"]) != {network_name}:
        raise PolicyError("Compose conectado a rede não permitida")
    mounts = [m for m in info.get("Mounts", []) if m.get("Type") != "tmpfs"]
    allowed = {(v["source"], v["target"]) for v in expected.get("volumes", [])}
    if {(m["Source"], m["Destination"]) for m in mounts} != allowed or len(mounts) != len(allowed) or any(m["RW"] for m in mounts):
        raise PolicyError("Compose montagens inesperadas, incluindo volumes de imagem")
    allowed_env = expected.get("environment", {})
    for item in info["Config"].get("Env", []):
        name, _, value = item.partition("=")
        if any(x in name.upper() for x in ("TOKEN", "SECRET", "PASSWORD", "API_KEY", "SSH_AUTH", "AWS_")) and allowed_env.get(name) != value:
            raise PolicyError("credencial não sintética no container")


def safety_observation(info):
    """Minimal inspection evidence, intentionally excluding environment values."""
    keys = ("Privileged", "ReadonlyRootfs", "CapAdd", "CapDrop", "SecurityOpt", "PidMode", "IpcMode",
        "Devices", "PortBindings", "Binds", "Memory", "MemorySwap", "NanoCpus", "PidsLimit", "LogConfig")
    data = {"user": info.get("Config", {}).get("User"),
        "host_config": {key: info.get("HostConfig", {}).get(key) for key in keys},
        "mounts": [{key: mount.get(key) for key in ("Type", "Source", "Destination", "RW", "Propagation")}
            for mount in info.get("Mounts", [])],
        "networks": sorted(info.get("NetworkSettings", {}).get("Networks", {}))}
    return json.loads(redact(json.dumps(data)))


def command_observation(result):
    """Captured text is sanitized; original stream hashes may differ after redaction."""
    if isinstance(result, BaseException):
        return {"collection_error": type(result).__name__}
    return {"exit_code": result.code, "timeout": result.timeout, "stdout": redact(result.stdout),
        "stderr": redact(result.stderr), "stdout_sha256": result.out_hash, "stderr_sha256": result.err_hash,
        "output_truncated": result.truncated}


async def collect_startup_observations(container_ids, limit):
    """Read only this execution's service states/logs, with bounded output and time."""
    services = [name for name in ("db", "services", "wordpress") if name in container_ids]
    commands = []
    for name in services:
        cid = container_ids[name]
        commands.extend([
            ["docker", "inspect", cid, "--format", "{{json .State}}"],
            ["docker", "logs", "--tail", "200", "--timestamps", cid],
        ])
    results = await asyncio.gather(*(process(command, 10, min(limit, 16000)) for command in commands), return_exceptions=True)
    observations = {}
    for i, name in enumerate(services):
        state_result, logs_result = results[2*i:2*i+2]
        entry = {"state_command": command_observation(state_result), "logs": command_observation(logs_result)}
        # Never retain arbitrary inspect data/environment. Only observable process state.
        entry["state_command"].pop("stdout", None)
        if not isinstance(state_result, BaseException) and state_result.code == 0:
            try:
                state = json.loads(state_result.stdout)
                entry["state"] = {key: state.get(key) for key in (
                    "Status", "Running", "Restarting", "OOMKilled", "Dead", "ExitCode", "Error", "StartedAt", "FinishedAt")}
                entry["state"] = json.loads(redact(json.dumps(entry["state"])))
            except (ValueError, AttributeError):
                entry["state_parse_error"] = True
        observations[name] = entry
    return observations


async def execute_compose(executor, request, argv, receipt_id):
    profile, store, run_id = executor.profile, executor.store, executor.manifest.run_id
    version = await process(["docker", "version", "--format", "{{.Server.Version}}"], 15)
    if int(version.stdout.split(".")[0]) < 28:
        raise PolicyError("WordPress exige Docker Engine 28+ para gateway isolated; rede internal sozinha permite acesso ao host")
    compose_version = await process(["docker", "compose", "version", "--short"], 15)
    if compose_version.code:
        raise PolicyError("Compose V2 indisponível")
    images = {}
    for key, tag in {"wordpress": profile.wp_image, "db": profile.db_image, "browser": profile.browser_image, "services": profile.service_image}.items():
        validate_image(tag)
        result = await process(["docker", "image", "inspect", tag, "--format", "{{.Id}}"], 15)
        if result.code or not result.stdout.startswith("sha256:"):
            raise PolicyError(f"imagem {key} não adquirida; build/pull explícito necessário")
        images[key] = result.stdout.strip()
    store.put(run_id, "resolved-images", images, immutable=True)
    project = "audit3-" + receipt_id
    with tempfile.TemporaryDirectory(prefix="audit3-compose-") as directory:
        root = Path(directory)
        root.chmod(0o755)
        assets = root / "assets"
        assets.mkdir(mode=0o755)
        for name in ("start-wordpress.sh", "wp-config.php", "synthetic-mail.php", "simulators.py"):
            atomic_write(assets / name, files("audit3").joinpath("assets", name).read_bytes(), 0o444)
        if request.kind == "browser":
            atomic_write(assets / "browser-seccomp.json", canonical(browser_seccomp_profile()), 0o444)
        suffix = "cjs" if request.kind == "browser" else "php"
        atomic_write(root / ("repro." + suffix), request.script.encode(), 0o444)
        spec = compose_spec(profile, store.path(run_id, "source"), root, assets, images, argv, request.kind)
        compose_path = root / "compose.json"
        atomic_write(compose_path, canonical(spec))
        base = ["docker", "compose", "--project-name", project, "--file", str(compose_path)]
        network_name = project + "_isolated"
        diagnostic = {"schema_version": "1.0", "phase": "create", "image_ids": images,
            "compose_version": compose_version.stdout.strip(), "containers": {}}
        start_attempted = False
        container_ids = {}
        try:
            created = await process(base + ["create", "--pull", "never"], 60)
            if created.code:
                raise PolicyError("Compose create falhou: " + created.stderr[:1000])
            diagnostic["phase"] = "verify_network"
            network = await process(["docker", "network", "inspect", network_name], 15)
            net = json.loads(network.stdout)[0]
            if not net.get("Internal") or net.get("EnableIPv6") or net.get("Options", {}).get("com.docker.network.bridge.gateway_mode_ipv4") != "isolated":
                raise PolicyError("rede interna isolada não aplicada")
            diagnostic["phase"] = "verify_containers"
            for service, expected in spec["services"].items():
                result = await process(base + ["ps", "--all", "--quiet", service], 15)
                cid = result.stdout.strip()
                info = await process(["docker", "inspect", cid], 15)
                observed = json.loads(info.stdout)[0]
                diagnostic["containers"][service] = safety_observation(observed)
                try:
                    verify_compose_container(observed, expected, network_name)
                except PolicyError as exc:
                    diagnostic["rejected_service"] = service
                    diagnostic["rejection"] = redact(str(exc))
                    raise PolicyError(f"{service}: {exc}") from exc
                container_ids[service] = cid
            diagnostic["phase"] = "start_services"
            start_attempted = True
            started = await process(base + ["start", "db", "services", "wordpress"], 30)
            diagnostic["start_command"] = command_observation(started)
            if started.code:
                raise PolicyError("Compose start falhou")
            ready = False
            diagnostic["phase"] = "wait_ready"
            for _ in range(30):
                result = await process(base + ["exec", "-T", "wordpress", "php", "-r", "exit(file_exists('/work/ready') ? 0 : 1);"], 5)
                diagnostic["last_readiness_probe"] = command_observation(result)
                if result.code == 0:
                    ready = True
                    break
                await asyncio.sleep(1)
            if not ready:
                raise PolicyError("WordPress não ficou pronto; bootstrap/compatibilidade pendentes")
            required = set(profile.required_plugins) | ({"woocommerce"} if profile.woocommerce_required else set())
            diagnostic["phase"] = "check_dependencies"
            for plugin in sorted(required):
                if not __import__("re").fullmatch(r"[a-z0-9_-]+", plugin):
                    raise PolicyError("slug inválido")
                result = await process(base + ["exec", "-T", "wordpress", "wp", "--path=/work/wordpress", "plugin", "is-installed", plugin], 10)
                if result.code:
                    raise PolicyError("dependência ausente: " + plugin + "; compatibilidade não declarada")
            # PHP/WP-CLI tests run in the live synthetic WP container; browser in its own container.
            diagnostic["phase"] = "test"
            if request.kind == "browser":
                result = await process(["docker", "start", "--attach", container_ids["runner"]], executor.config.limits.test_timeout, executor.config.limits.max_output_bytes)
                if not result.timeout:
                    state = await process(["docker", "inspect", container_ids["runner"], "--format", "{{json .State}}"], 15)
                    result.code = json.loads(state.stdout)["ExitCode"]
            else:
                result = await process(base + ["exec", "-T", "--workdir", "/work/wordpress", "wordpress", *argv], executor.config.limits.test_timeout, executor.config.limits.max_output_bytes)
            store.put(run_id, "environments/" + receipt_id, {"compose_version": compose_version.stdout.strip(), "images": images, "network_mode": "internal+isolated", "synthetic": True}, immutable=True)
            diagnostic["phase"] = "test_finished"
            return result, images
        finally:
            try:
                if start_attempted:
                    diagnostic["startup_observations"] = await collect_startup_observations(container_ids, executor.config.limits.max_output_bytes)
            finally:
                cleanup = await asyncio.shield(process(base + ["down", "--volumes", "--remove-orphans", "--timeout", "3"], 30))
                diagnostic["cleanup"] = {"exit_code": cleanup.code, "timeout": cleanup.timeout}
                store.put(run_id, "setup-diagnostics/" + receipt_id, diagnostic, immutable=True)
                if cleanup.code:
                    raise PolicyError("remoção do ambiente Compose não confirmada: " + project)
