from __future__ import annotations
import re
from dataclasses import dataclass
from .config import Config
from .evidence import Store
from .executor import Executor
from .schemas import EvidenceReceipt, InspectionRecord, RunManifest, SourceRef, TestRequest
from .security import PolicyError, contained, digest, object_hash, redact


@dataclass(frozen=True)
class ToolContext:
    run_id: str
    role: str
    phase: str
    invocation_id: str


class SourceTools:
    def __init__(self, store: Store, manifest: RunManifest, config: Config, executor: Executor, context: ToolContext):
        if context.run_id != manifest.run_id or context.role not in {"auditor", "defensor", "juiz"}:
            raise PolicyError("identidade inválida")
        self.store, self.manifest, self.config, self.executor, self.context = store, manifest, config, executor, context
        self.index = {f.path: f for f in manifest.files}

    def check(self):
        if self.store.exists(self.context.run_id, "cancel"):
            raise PolicyError("execução cancelada")

    def source_bytes_for_validation(self, path):
        """Controller validation only; never counts as a model source read."""
        record = self.index.get(path)
        if not record or record.category in {'excluded', 'prior_report'}:
            raise PolicyError('Fonte causal fora do snapshot atual')
        data = contained(self.store.path(self.context.run_id, 'source'), path).read_bytes()
        if digest(data) != record.sha256:
            raise PolicyError('Fonte causal adulterada')
        return data

    def published(self):
        if not self.store.exists(self.context.run_id, "barrier"):
            return False
        barrier = self.store.get(self.context.run_id, "barrier")
        for role, expected in barrier["initial_hashes"].items():
            if object_hash(self.store.get(self.context.run_id, f"roles/{role}/initial")) != expected:
                raise PolicyError("parecer inicial adulterado")
        return True

    def log(self, tool: str, data: dict):
        self.store.event(self.context.run_id, "tool", {"role": self.context.role, "phase": self.context.phase, "invocation_id": self.context.invocation_id, "tool": tool, **data})

    def list_source(self, offset: int = 0, limit: int = 100):
        self.check()
        if offset < 0 or not 1 <= limit <= 200:
            raise PolicyError("paginação inválida")
        records = [f for f in self.manifest.files if f.category != "prior_report" or self.published()]
        self.log("list_source", {"offset": offset, "count": min(limit, len(records[offset:]))})
        return {"files": [f.model_dump() for f in records[offset:offset+limit]], "next_offset": offset + limit if offset + limit < len(records) else None}

    def read_source(self, path: str, start: int = 1, end: int = 160):
        self.check()
        f = self.index.get(path)
        if not f or f.category == "excluded" or (f.category == "prior_report" and not self.published()):
            raise PolicyError("fonte não disponível nesta fase")
        if start < 1 or end < start or start > max(1, f.lines):
            raise PolicyError("intervalo inválido")
        root = self.store.path(self.context.run_id, "prior" if f.category == "prior_report" else "source")
        data = contained(root, path).read_bytes()
        if digest(data) != f.sha256:
            raise PolicyError("fonte adulterada")
        lines = data.decode("utf-8").splitlines()
        last = min(end, start + self.config.limits.read_lines - 1, len(lines))
        output, full_end, size = [], start - 1, 0
        partial_line = None
        for n in range(start, last + 1):
            line = lines[n - 1]
            if size + len(line.encode()) > 16000:
                partial_line = n
                break
            output.append({"line": n, "text": line})
            size += len(line.encode())
            full_end = n
        truncated = full_end < min(end, len(lines))
        self.log("read_source", {"path": path, "sha256": f.sha256, "start": start, "end": full_end, "truncated": truncated, "omitted_long_line": partial_line})
        return {"path": path, "sha256": f.sha256, "lines": output, "truncated": truncated, "next_line": full_end + 1 if truncated else None, "omitted_long_line": partial_line}

    def search_source(self, query: str, offset: int = 0):
        self.check()
        if not 1 <= len(query) <= 200 or offset < 0:
            raise PolicyError("busca literal limitada")
        matches = []
        skipped = 0
        for f in self.manifest.files:
            if f.category in {"excluded", "prior_report"}:
                continue
            data = contained(self.store.path(self.context.run_id, "source"), f.path).read_bytes()
            if digest(data) != f.sha256:
                raise PolicyError("fonte adulterada")
            for n, line in enumerate(data.decode().splitlines(), 1):
                if query in line:
                    if skipped < offset:
                        skipped += 1
                        continue
                    if len(matches) == 20:
                        return {"matches": matches, "next_offset": offset + 20}
                    matches.append(self.read_source(f.path, n, n))
        self.log("search_source", {"query_hash": digest(query.encode()), "matches": len(matches)})
        return {"matches": matches, "next_offset": None}

    def read_evidence(self, evidence_id: str, *, record_access: bool = True):
        self.check()
        if not re.fullmatch(r"[a-f0-9]{24}", evidence_id):
            raise PolicyError("ID de evidência inválido")
        if self.store.exists(self.context.run_id, "comparisons/" + evidence_id):
            from .comparison import read_comparison
            result = read_comparison(self.store, self.context.run_id, evidence_id)
            if record_access:
                self.log("read_comparison", {"id": evidence_id, "before_source_id": result["before_source_id"], "excerpts_hash": object_hash(result["before_source_excerpts"]), "ranges": [{k: e[k] for k in ("path", "sha256", "start", "end", "truncated")} for e in result["before_source_excerpts"]], "truncated": result["excerpt_budget_exhausted"]})
            return result
        if not self.store.exists(self.context.run_id, "receipts/" + evidence_id):
            raise PolicyError("ID de evidência não disponível")
        receipt = EvidenceReceipt.model_validate(self.store.get(self.context.run_id, "receipts/" + evidence_id))
        if receipt.owner not in {"baseline", self.context.role} and not self.published():
            raise PolicyError("evidência privada antes da barreira")
        if receipt.run_id != self.context.run_id or receipt.source_id != self.manifest.source_id:
            raise PolicyError("receipt de outra versão")
        if record_access:
            self.log("read_evidence", {"id": evidence_id})
        return {"receipt": receipt.model_dump(), "test": self.store.get(self.context.run_id, "tests/" + evidence_id)}

    def require_evidence_consulted(self, evidence_id: str):
        for name in self.store.names(self.context.run_id, "events"):
            event = self.store.get(self.context.run_id, "events/" + name)
            data = event["data"]
            if event["kind"] == "tool" and data.get("role") == self.context.role and data.get("tool") in {"read_evidence", "submit_test", "read_comparison"} and data.get("id") == evidence_id:
                return
        raise PolicyError("evidência não consultada diretamente pelo papel")

    async def submit_test(self, request: TestRequest):
        self.check()
        receipt = await self.executor.execute(request, self.context.role, self.context.phase)
        self.log("submit_test", {"id": receipt.id, "status": receipt.status})
        return receipt.model_dump()

    def validate_ref(self, ref: SourceRef, require_read=True):
        f = self.index.get(ref.path)
        if not f or f.category == "excluded" or f.sha256 != ref.sha256 or ref.end > f.lines:
            raise PolicyError("referência de código inválida")
        if require_read:
            intervals = []
            for n in self.store.names(self.context.run_id, "events"):
                event = self.store.get(self.context.run_id, "events/" + n)
                d = event["data"]
                if event["kind"] == "tool" and d.get("role") == self.context.role and d.get("tool") == "read_source" and d.get("path") == ref.path:
                    intervals.append((d["start"], d["end"]))
            cursor = ref.start
            for start, end in sorted(intervals):
                if start <= cursor:
                    cursor = max(cursor, end + 1)
            if cursor <= ref.end:
                raise PolicyError("referência não foi devolvida pelas ferramentas ao papel")

    def validate_inspection(self, inspection: InspectionRecord):
        if not inspection.refs:
            raise PolicyError("análise sem referências")
        for ref in inspection.refs:
            self.validate_ref(ref)
        if inspection.flow_verified and not inspection.flow_description.strip():
            raise PolicyError("fluxo verificado sem descrição")

    def validate_finding(self, finding):
        if finding.source_id != self.manifest.source_id:
            raise PolicyError("achado de outra versão")
        for ref in finding.refs:
            self.validate_ref(ref)
        for eid in finding.evidence_ids:
            result = self.read_evidence(eid, record_access=False)
            if "receipt" not in result:
                raise PolicyError("comparação não é execução de teste")
            receipt = result["receipt"]
            if finding.proof_method == "executed" and (receipt["execution"] not in {"docker", "compose"} or receipt["status"] not in {"passed", "failed"}):
                raise PolicyError("teste alegado não executado")
        # Version comparisons need a separate signed comparison, not a self-declared origin.
        for eid in finding.origin_evidence_ids:
            comparison = self.read_evidence(eid, record_access=False)
            if comparison.get("after_source_id") != self.manifest.source_id or not comparison.get("before_source_id"):
                raise PolicyError("origem sem comparação válida")
        if finding.production_observation == "observed_with_evidence":
            raise PolicyError("MVP não importa evidência de produção; mantenha ocorrência desconhecida")
