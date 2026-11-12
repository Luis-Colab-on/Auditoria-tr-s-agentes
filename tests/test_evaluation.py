import pytest
from audit3.evaluation import evaluate
from audit3.security import PolicyError


def test_quality_counts_mechanisms_not_assertions_or_votes():
    report = {"state": {"runtime_mode": "mock"}, "validation": "implementado, integração real ainda não validada", "coverage": {"gaps": ["synthetic"]},
        "verdicts": [{"finding_id": fid, "classification": "falha comprovada"} for fid in ("a", "b", "c")],
        "metrics": {"failed_assertions": 16}}
    score = evaluate(report, ["refund-sign", "missing-defect"], {"a": "refund-sign", "b": "refund-sign", "c": None})
    assert score["true_positive_mechanisms"] == ["refund-sign"]
    assert score["known_defects_omitted"] == ["missing-defect"]
    assert score["false_positive_ids"] == ["c"]
    assert score["precision"] == .5 and score["recall"] == .5
    assert score["duplicate_candidate_count"] == 1
    assert not score["real_integration_validated"]
    with pytest.raises(PolicyError): evaluate(report, ["refund-sign"], {"a": "refund-sign"})
