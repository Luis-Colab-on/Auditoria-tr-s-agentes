from __future__ import annotations
import asyncio
import json
import secrets
import time
from datetime import datetime, timezone
from importlib.resources import files
from pydantic import ValidationError
from .agents import BudgetExceeded, RuntimePaused
from .codex_runtime import CodexRuntime
from .codex_policy import financial_policy
from .config import Config, Profile
from .evidence import Store
from .executor import Executor
from .schemas import (Classification, Decision, Judgment, Opinion, Role, RunManifest, TestRequest, Verdict)
from .security import PolicyError, digest, now, object_hash, redact, sensitive
from .snapshot import verify_source
from .tools import SourceTools, ToolContext
from .causality import causal_groups
from .completion import assess_completion, VERSION as ASSESSMENT_VERSION
from .operational import total_seconds


def batches(manifest: RunManifest, line_limit: int):
    result, batch, size = [], [], 0
    for f in manifest.files:
        if f.category in {"excluded", "prior_report"}:
            continue
        for start in range(1, max(1, f.lines) + 1, line_limit):
            end = min(f.lines, start + line_limit - 1)
            if size and size + end - start + 1 > line_limit:
                result.append(batch)
                batch, size = [], 0
            batch.append({"path": f.path, "start": start, "end": end, "sha256": f.sha256})
            size += max(1, end - start + 1)
    if batch:
        result.append(batch)
    return result or [[]]


class Workflow:
    def __init__(self, store: Store, run_id: str, runtime=None, executor=None):
        self.store, self.run_id = store, run_id
        self.manifest = RunManifest.model_validate(store.get(run_id, "manifest"))
        if runtime is None and self.manifest.backend != "codex-app-server":
            raise PolicyError("Run histórico: somente leitura/exportação; prepare nova execução Codex, sem continuidade equivalente")
        raw_config = store.get(run_id, "config")
        self.config = Config.model_validate(raw_config)
        self.profile = Profile.model_validate(store.get(run_id, "profile"))
        if object_hash(raw_config) != self.manifest.config_hash or object_hash(self.profile) != self.manifest.profile_hash:
            raise PolicyError("configuração/perfil adulterado")
        for role, expected in self.manifest.prompt_hashes.items():
            if digest(files("audit3").joinpath("prompts", role + ".txt").read_bytes()) != expected:
                raise PolicyError("prompt mudou: nova auditoria necessária")
        self.runtime, self.executor = runtime, executor or Executor(store, self.manifest, self.config, self.profile)
        self.semaphore = asyncio.Semaphore(self.config.limits.concurrency)

    def state(self):
        return self.store.get(self.run_id, "state")

    def update(self, **kwargs):
        state = self.state()
        state.update(kwargs)
        self.store.put(self.run_id, "state", state)

    def opinions(self, role: str):
        return [self.store.get(self.run_id, f"roles/{role}/phases/{name}")["output"] for name in self.store.names(self.run_id, f"roles/{role}/phases")]

    def shared(self):
        if not self.store.exists(self.run_id, "barrier"):
            raise PolicyError("barreira não publicada")
        return {r.value: self.opinions(r.value) for r in Role}

    def findings(self):
        found = {}
        for role in Role:
            for opinion in self.opinions(role.value):
                for finding in opinion.get("findings", []):
                    if finding["id"] in found and found[finding["id"]]["mechanism"] != finding["mechanism"]:
                        raise PolicyError("ID reaproveitado para mecanismo diferente")
                    # Keep the initial allegation; revisions are preserved in positions.
                    found.setdefault(finding["id"], finding)
        return found

    def validate_output(self, output, tools: SourceTools, final: bool):
        if sensitive(json.dumps(output.model_dump(mode="json"), ensure_ascii=False)):
            raise PolicyError("saída contém possível segredo/PII")
        if not final:
            for inspection in output.inspections:
                tools.validate_inspection(inspection)
            for finding in output.findings:
                if not finding.id.startswith(tools.context.role + "-"):
                    raise PolicyError("ID deve pertencer ao papel")
                tools.validate_finding(finding)
                if not (tools.context.phase.startswith("initial") or tools.context.phase in {"blind", "review"}) and finding.id not in self.findings():
                    raise PolicyError("novo achado tardio sem contraditório: registre limitação para nova auditoria")
            # Resolve references after validating the response's own findings.
            # Blind phases can use this role's history, never another role's
            # unpublished findings merely because it happened to finish first.
            blind = tools.context.phase.startswith("initial") or tools.context.phase == "blind"
            known = ({finding["id"] for opinion in self.opinions(tools.context.role)
                for finding in opinion.get("findings", [])} if blind else set(self.findings()))
            known.update(finding.id for finding in output.findings)
            for position in output.positions:
                if position.finding_id not in known:
                    raise PolicyError("posição sobre achado inexistente")
                for eid in position.evidence_ids:
                    tools.read_evidence(eid, record_access=False)
            return
        known = self.findings()
        if self.store.exists(self.run_id, "baseline"):
            for eid in self.store.get(self.run_id, "baseline")["ids"]:
                receipt = tools.read_evidence(eid, record_access=False)["receipt"]
                if receipt["status"] in {"passed", "failed"}:
                    tools.require_evidence_consulted(eid)
                    if not output.baseline_assessment or not output.baseline_assessment.strip():
                        raise PolicyError("Juiz precisa avaliar testes de base e suas expectativas, inclusive divergências")
        if {v.finding_id for v in output.verdicts} != set(known) or len(output.verdicts) != len(known):
            raise PolicyError("cada achado exige exatamente uma decisão")
        for verdict in output.verdicts:
            finding = known[verdict.finding_id]
            # Judge has to consult source directly, including initially raised findings.
            from .schemas import SourceRef
            for ref in finding["refs"]:
                tools.validate_ref(SourceRef.model_validate(ref))
            for eid in verdict.evidence_ids:
                tools.read_evidence(eid, record_access=False)
                tools.require_evidence_consulted(eid)
            if verdict.classification == Classification.PROVEN:
                if verdict.proof_method == "executed":
                    if not verdict.evidence_ids:
                        raise PolicyError("falha executada sem receipt")
                    for eid in verdict.evidence_ids:
                        r = tools.read_evidence(eid, record_access=False)["receipt"]
                        if r["execution"] not in {"docker", "compose"} or r["status"] not in {"passed", "failed"}:
                            raise PolicyError("receipt não prova execução")
                if verdict.proof_method == "static" and not finding.get("static_demonstration"):
                    raise PolicyError("falta demonstração estática verificável")
        for finding in output.new_findings:
            tools.validate_finding(finding)
        certificate_name = 'assessment/causal-certificates'
        certificates = self.store.get(self.run_id, certificate_name) if self.store.exists(self.run_id, certificate_name) else []
        causal_groups(list(known.values()), [v.model_dump(mode='json') for v in output.verdicts],
            tools, tools.source_bytes_for_validation, certificates)

    async def invoke(self, role: str, phase: str, assignment=None, final=False):
        name = f"roles/{role}/phases/{phase}"
        if self.store.exists(self.run_id, name):
            return self.store.get(self.run_id, name)["output"]
        async with self.semaphore:
            if self.store.exists(self.run_id, "cancel"):
                raise asyncio.CancelledError
            self.update(phase=phase)
            payload = {"phase": phase, "role": role, "manifest": self.manifest.model_dump(mode="json"),
                "financial_restriction": financial_policy(),
                "assignment": assignment, "own_observations": self.opinions(role) if self.runtime.mode != "codex-app-server" else [],
                "baseline_receipts": self.store.get(self.run_id, "baseline")["ids"],
                "comparison_ids": self.store.names(self.run_id, "comparisons"),
                "instruction": "Leia os intervalos atribuídos via ferramentas. Declare lacunas. Em debate retorne posições; final exige decisão por achado."}
            if self.store.exists(self.run_id, "barrier"):
                phase_input = f"phase-inputs/{phase}"
                payload["published_opinions"] = self.store.get(self.run_id, phase_input) if self.store.exists(self.run_id, phase_input) else self.shared()
                payload["finding_ids"] = list(self.findings())
                payload["receipt_ids"] = self.store.names(self.run_id, "receipts")
            if len(json.dumps(payload, ensure_ascii=False).encode()) > self.config.limits.max_input_bytes:
                raise BudgetExceeded("entrada excede limite: cobertura parcial; reduza escopo numa nova preparação")
            attempt_count = self.config.limits.invalid_output_retries + 1
            authorization_name = name.replace('/phases/', '/attempts/') + '-extra-authorization'
            if self.store.exists(self.run_id, authorization_name):
                authorization = self.store.get(self.run_id, authorization_name)
                expected = {'source': 'explicit_operator_authorization', 'run_id': self.run_id,
                    'role': role, 'phase': phase, 'additional_attempts': 1,
                    'attempt_slot': attempt_count, 'config_hash': self.manifest.config_hash}
                previous_name = name.replace('/phases/', '/attempts/') + f'-{attempt_count - 1}'
                if (any(authorization.get(key) != value for key, value in expected.items())
                    or not all(self.store.exists(self.run_id, name.replace('/phases/', '/attempts/') + f'-{i}') for i in range(attempt_count))
                    or authorization.get('previous_invocation_id') != self.store.get(self.run_id, previous_name)['invocation_id']
                    or not self.store.exists(self.run_id, previous_name + '-interrupted')):
                    raise RuntimePaused('Exceção de tentativa adicional inválida; retomada bloqueada')
                # One immutable authorization permits one fixed slot for this
                # role/phase only. Its checkpoint prevents replay after failure.
                attempt_count += 1
            for attempt in range(attempt_count):
                attempt_name = name.replace("/phases/", "/attempts/") + f"-{attempt}"
                if self.store.exists(self.run_id, attempt_name):
                    if self.store.exists(self.run_id, attempt_name + '-interrupted'):
                        # Explicit operator recovery after an official terminal-state
                        # check. It consumes an existing slot; never creates retries.
                        recovery = self.store.get(self.run_id, attempt_name + '-interrupted')
                        previous = self.store.get(self.run_id, attempt_name)
                        turn = self.store.get(self.run_id, 'codex-turns/' + previous['invocation_id'])
                        if (recovery.get('source') != 'official_app_server_thread_read' or recovery.get('status') != 'interrupted'
                            or recovery.get('invocation_id') != previous['invocation_id'] or turn.get('status') != 'ambiguous'
                            or recovery.get('thread_id') != turn.get('thread_id') or recovery.get('turn_id') != turn.get('turn_id')
                            or turn.get('role') != role or turn.get('phase') != phase):
                            raise RuntimePaused('Reconciliação de turno interrompido inválida; retomada bloqueada')
                        continue
                    if self.store.exists(self.run_id, attempt_name + "-rejected"):
                        rejected = self.store.get(self.run_id, attempt_name + "-rejected")
                        if rejected.get("feedback"):
                            payload["validation_feedback"] = rejected["feedback"]
                        continue
                    if self.runtime.mode != "codex-app-server":
                        continue
                    invocation_id = self.store.get(self.run_id, attempt_name)["invocation_id"]
                else:
                    invocation_id = secrets.token_hex(12)
                tools = SourceTools(self.store, self.manifest, self.config, self.executor, ToolContext(self.run_id, role, phase, invocation_id))
                if not self.store.exists(self.run_id, attempt_name):
                    self.store.put(self.run_id, attempt_name, {"invocation_id": invocation_id, "started_at": now(), "input_hash": object_hash(payload)}, immutable=True)
                self.store.put(self.run_id, f"roles/{role}/state", {"phase": phase, "invocation_id": invocation_id, "status": "running"})
                try:
                    result = await self.runtime.invoke(role, phase, payload, tools, final=final)
                    cls = Judgment if final else Opinion
                    output = cls.model_validate_json(result) if isinstance(result, str) else cls.model_validate(result)
                    self.validate_output(output, tools, final)
                except RuntimePaused:
                    raise
                except (ValidationError, PolicyError, json.JSONDecodeError) as exc:
                    self.store.put(self.run_id, attempt_name + "-rejected", {"error_type": type(exc).__name__, "feedback": "Saída rejeitada: " + redact(str(exc))[:1500]}, immutable=True)
                    self.store.event(self.run_id, "invalid_output", {"role": role, "phase": phase, "error_type": type(exc).__name__, "attempt": attempt})
                    if attempt == attempt_count - 1:
                        raise PolicyError("saída inválida após limite de correções") from exc
                    payload["validation_feedback"] = "Saída rejeitada: " + redact(str(exc))[:1500]
                    continue
                record = {"role": role, "phase": phase, "invocation_id": invocation_id, "published_at": now(), "mode": self.runtime.mode, "output": output.model_dump(mode="json")}
                self.store.put(self.run_id, name, record, immutable=True)
                self.store.put(self.run_id, f"roles/{role}/state", {"phase": phase, "invocation_id": invocation_id, "status": "completed"})
                state = self.state()
                state["completed"].append(role + "/" + phase)
                self.store.put(self.run_id, "state", state)
                return record["output"]
            raise PolicyError("tentativas desta fase esgotadas; nenhuma chamada repetida automaticamente")

    async def independent(self, role: str):
        if role == "juiz":
            await self.invoke(role, "blind", {"scope": "inspeção cega de requisitos, arquitetura, entradas críticas, invariantes; escolha trechos pelo inventário"})
        else:
            for i, batch in enumerate(batches(self.manifest, self.config.limits.batch_lines)):
                await self.invoke(role, f"initial-{i:04d}", batch)
        self.store.put(self.run_id, f"roles/{role}/initial", {"role": role, "opinions": self.opinions(role)}, immutable=True)

    async def paired(self, phase: str):
        # gather waits for both; the next phase cannot start on one early result.
        self.store.put(self.run_id, f"phase-inputs/{phase}", self.store.get(self.run_id, f"phase-inputs/{phase}") if self.store.exists(self.run_id, f"phase-inputs/{phase}") else self.shared(), immutable=True)
        tasks = [asyncio.create_task(self.invoke(r, phase)) for r in ("auditor", "defensor")]
        try:
            return await asyncio.gather(*tasks)
        except BaseException:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise

    async def body(self):
        verify_source(self.store, self.manifest)
        if not self.store.exists(self.run_id, "baseline"):
            r = await self.executor.execute(TestRequest(kind="baseline", purpose="testes de base factuais do snapshot"), "baseline", "baseline")
            self.store.put(self.run_id, "baseline", {"ids": [r.id]}, immutable=True)
        if self.runtime is None:
            self.runtime = CodexRuntime(self.store, self.run_id, self.config)
        if isinstance(self.runtime, CodexRuntime):
            self.runtime.global_deadline = self._global_deadline
        if hasattr(self.runtime, "preflight"):
            await self.runtime.preflight()
        self.update(runtime_mode=self.runtime.mode)
        if not self.store.exists(self.run_id, "barrier"):
            # An explicitly authorized recovery must finish before other initial
            # roles start. Failure spends no additional role's turn.
            for role in Role:
                if self.store.exists(self.run_id, f'roles/{role.value}/attempts/initial-0000-extra-authorization'):
                    await self.independent(role.value)
            tasks = [asyncio.create_task(self.independent(r.value)) for r in Role]
            try:
                await asyncio.gather(*tasks)
            except BaseException:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                raise
            barrier = {"published_at": now(), "initial_hashes": {r.value: object_hash(self.store.get(self.run_id, f"roles/{r.value}/initial")) for r in Role}}
            self.store.put(self.run_id, "barrier", barrier, immutable=True)
            self.store.event(self.run_id, "barrier_published", barrier)
        await self.paired("contest")
        await self.paired("reply")
        if not self.store.exists(self.run_id, "review-start"):
            self.store.put(self.run_id, "review-start", {"finding_ids": list(self.findings()), "receipt_ids": self.store.names(self.run_id, "receipts")}, immutable=True)
        before_findings = set(self.store.get(self.run_id, "review-start")["finding_ids"])
        before_receipts = set(self.store.get(self.run_id, "review-start")["receipt_ids"])
        review = await self.invoke("juiz", "review")
        if not self.store.exists(self.run_id, "material-review"):
            # Persist the gate so resume makes the same decision.
            new_ids = set(self.findings()) - before_findings
            new_receipts = set(self.store.names(self.run_id, "receipts")) - before_receipts
            self.store.put(self.run_id, "material-review", {"additional_round": bool(new_ids or new_receipts), "new_finding_ids": sorted(new_ids), "new_receipt_ids": sorted(new_receipts)}, immutable=True)
        if self.store.get(self.run_id, "material-review")["additional_round"]:
            await self.paired("extra-contest")
            await self.paired("extra-reply")
        result = await self.invoke("juiz", "final", final=True)
        self.store.put(self.run_id, "judgment", result, immutable=True)
        verify_source(self.store, self.manifest)
        from .report import build_report
        report = build_report(self.store, self.run_id)
        review_name = 'assessment/completion-review'
        review = self.store.get(self.run_id, review_name) if self.store.exists(self.run_id, review_name) else None
        completion = assess_completion(report, review)
        self.store.put(self.run_id, 'assessment/completion', completion)
        technical = "decisions_recorded"
        if not result["verdicts"] or all(v["decision"] in {"manter", "descartar", "documentar/aceitar por ora"} for v in result["verdicts"]):
            technical = "Nenhuma alteração necessária no escopo verificado"
        if completion['blockers']:
            technical += "; lacunas bloqueantes/limitações não esclarecidas"
        if result["new_findings"]:
            technical = "inconclusivo: achado novo pendente de contraditório"
        if self.runtime.mode != "codex-app-server":
            technical = "MOCK: teste de infraestrutura; não é auditoria real"
        self.update(status=completion['status'], technical_result=technical, phase='done',
            limitations=[item['text'] for item in completion['limitations']],
            completion_blockers=completion['blockers'], assessment_version=ASSESSMENT_VERSION)

    async def run(self, resume=False):
        with self.store.lock(self.run_id):
            self.store.put(self.run_id, 'financial-policy', {'permanent': True, 'rule': financial_policy()}, immutable=True)
            state = self.state()
            if state["phase"] == "done":
                return state
            total_limit = total_seconds(self.store, self.run_id, self.config)
            if self.store.exists(self.run_id, "cancel"):
                if not resume:
                    self.update(status="cancelled")
                    return self.state()
                self.store.event(self.run_id, "cancel_cleared_for_resume", {})
                self.store.path(self.run_id, "cancel.json").unlink()
            if state.get("active_since"):
                state["elapsed_seconds"] += max(0, (datetime.now(timezone.utc) - datetime.fromisoformat(state["active_since"])).total_seconds())
            self.update(status="running", active_since=now())
            start = time.monotonic()
            remaining = total_limit - state.get("elapsed_seconds", 0)
            self._global_deadline = start + max(0, remaining)
            async def monitor():
                while True:
                    await asyncio.sleep(0.2)
                    if self.store.exists(self.run_id, "cancel"):
                        return
            body = asyncio.create_task(self.body())
            cancel = asyncio.create_task(monitor())
            try:
                done, _ = await asyncio.wait({body, cancel}, timeout=max(0, remaining), return_when=asyncio.FIRST_COMPLETED)
                if cancel in done or not done:
                    body.cancel()
                    await asyncio.gather(body, return_exceptions=True)
                    self.update(status="cancelled" if cancel in done else "partial", technical_result="inconclusivo", limitations=["cancelamento solicitado" if cancel in done else "limite de tempo total"])
                else:
                    await body
            except RuntimePaused as exc:
                self.update(status="blocked", technical_result="inconclusivo", limitations=[str(exc)])
            except BudgetExceeded as exc:
                self.update(status="partial", technical_result="inconclusivo", limitations=[str(exc)])
            except asyncio.CancelledError:
                body.cancel()
                await asyncio.gather(body, return_exceptions=True)
                self.update(status="cancelled", technical_result="inconclusivo", limitations=["controlador interrompido"])
            except Exception as exc:
                message = redact(str(exc))[:2000] if isinstance(exc, PolicyError) else "Falha do runtime: " + type(exc).__name__
                self.update(status="partial" if isinstance(exc, (PolicyError, TimeoutError)) else "failed", technical_result="inconclusivo", limitations=[message])
            finally:
                cancel.cancel()
                await asyncio.gather(cancel, return_exceptions=True)
                self.update(elapsed_seconds=state.get("elapsed_seconds", 0) + time.monotonic() - start, active_since=None)
                for role in Role:
                    name = f"roles/{role.value}/state"
                    if self.store.exists(self.run_id, name):
                        role_state = self.store.get(self.run_id, name)
                        if role_state["status"] == "running":
                            self.store.put(self.run_id, name, {**role_state, "status": "interrupted", "stopped_at": now()})
                if self.runtime and hasattr(self.runtime, "close"):
                    await self.runtime.close()
                from .report import write_report
                write_report(self.store, self.run_id)
            return self.state()
