"""Fixture quality metrics require reviewed mappings, never heuristic bug counting."""
from .security import PolicyError


def evaluate(report: dict, known_defects: list[str], reviewed_mapping: dict[str, str | None]):
    accepted = {v["finding_id"] for v in report["verdicts"] if v["classification"] == "falha comprovada"}
    if set(reviewed_mapping) != accepted:
        raise PolicyError("mapeamento revisado deve cobrir todos e apenas os achados comprovados")
    if any(value is not None and value not in known_defects for value in reviewed_mapping.values()):
        raise PolicyError("mapeamento referencia defeito fora do oráculo")
    detected = {value for value in reviewed_mapping.values() if value is not None}
    false_positives = [fid for fid, value in reviewed_mapping.items() if value is None]
    denominator = len(detected) + len(false_positives)
    return {"runtime_mode": report["state"].get("runtime_mode"), "real_integration_validated": report["validation"] == "execução real registrada",
        "true_positive_mechanisms": sorted(detected), "false_positive_ids": false_positives,
        "known_defects_omitted": sorted(set(known_defects) - detected),
        "precision": len(detected)/denominator if denominator else None,
        "recall": len(detected)/len(known_defects) if known_defects else None,
        "duplicate_candidate_count": len(accepted) - len(detected) - len(false_positives),
        "coverage_gaps": report["coverage"]["gaps"], "mapping_basis": "human-reviewed mechanism mapping; no inference from failed assertions"}
