from __future__ import annotations
import secrets
from .evidence import Store
from .schemas import RunManifest
from .security import PolicyError, contained, now, sensitive
from .snapshot import verify_source


def register_comparison(store: Store, before_id: str, after_id: str, purpose: str):
    before = RunManifest.model_validate(store.get(before_id, "manifest"))
    after = RunManifest.model_validate(store.get(after_id, "manifest"))
    if sensitive(purpose):
        raise PolicyError("propósito contém possível dado sensível")
    if before.source_id == after.source_id:
        raise PolicyError("comparação requer snapshots distintos")
    if store.exists(after_id, "barrier") or store.get(after_id, "ledger")["calls"]:
        raise PolicyError("registre comparação antes das investigações")
    for m in (before, after): verify_source(store, m)
    eid = secrets.token_hex(12)
    old = {f.path: f.sha256 for f in before.files if f.category not in {"excluded", "prior_report"}}
    new = {f.path: f.sha256 for f in after.files if f.category not in {"excluded", "prior_report"}}
    receipt_pairs = []
    for name in store.names(before_id, "receipts"):
        a = store.get(before_id, "receipts/" + name)
        for name2 in store.names(after_id, "receipts"):
            b = store.get(after_id, "receipts/" + name2)
            if a["execution"] in {"docker", "compose"} and b["execution"] == a["execution"] and a["profile_hash"] == b["profile_hash"] and a["image_ids"] == b["image_ids"] and a["command"] == b["command"] and a["script_sha256"] == b["script_sha256"]:
                receipt_pairs.append({"before": a["id"], "after": b["id"]})
    record = {"kind": "comparison", "id": eid, "created_at": now(), "purpose": purpose,
        "before_run_id": before_id, "before_source_id": before.source_id, "after_run_id": after_id, "after_source_id": after.source_id,
        "files": [{"path": path, "before_sha256": old.get(path), "after_sha256": new.get(path)} for path in sorted(set(old) | set(new))],
        "equivalent_execution_pairs": receipt_pairs, "limitations": ["Snapshots distintos; origem exige interpretação do mecanismo. Sem pares equivalentes, comparação apenas estática."]}
    store.put(after_id, "comparisons/" + eid, record, immutable=True)
    return record


def read_comparison(store: Store, run_id: str, eid: str):
    record = store.get(run_id, "comparisons/" + eid)
    if record["after_run_id"] != run_id:
        raise PolicyError("comparação de outra execução")
    before = RunManifest.model_validate(store.get(record["before_run_id"], "manifest"))
    after = RunManifest.model_validate(store.get(run_id, "manifest"))
    if record["before_source_id"] != before.source_id or record["after_source_id"] != after.source_id:
        raise PolicyError("snapshot da comparação inválido")
    verify_source(store, before)
    verify_source(store, after)
    excerpts, remaining = [], 16000
    for f in before.files:
        if f.category in {"excluded", "prior_report"} or remaining <= 0:
            continue
        data = contained(store.path(before.run_id, "source"), f.path).read_bytes()
        raw = data[:remaining]
        text = raw.decode(errors="replace")
        excerpts.append({"path": f.path, "sha256": f.sha256, "source_id": before.source_id, "text": text, "start": 1, "end": len(text.splitlines()), "truncated": len(raw) < len(data)})
        remaining -= len(raw)
    return {**record, "before_source_excerpts": excerpts, "excerpt_budget_exhausted": remaining <= 0}
