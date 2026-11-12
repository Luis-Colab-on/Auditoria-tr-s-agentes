import asyncio
import pytest
from audit3.schemas import Judgment, TestRequest as Request
from audit3.security import PolicyError
from audit3.workflow import Workflow
from test_tools_schemas import tools_for, finding
from helpers import MockRuntime


def test_internal_receipt_validation_does_not_claim_model_consulted(make_run, monkeypatch):
    monkeypatch.setattr("audit3.executor.shutil.which", lambda _: None)
    store, m = make_run()
    tools = tools_for(store, m)
    tools.read_source("app.py")
    receipt = asyncio.run(tools.executor.execute(Request(kind="python", script="print(1)", purpose="explicit mocked validation scenario"), "auditor", "initial"))
    tools.validate_finding(finding(m, evidence_ids=[receipt.id]))
    with pytest.raises(PolicyError): tools.require_evidence_consulted(receipt.id)
    tools.read_evidence(receipt.id)
    tools.require_evidence_consulted(receipt.id)


def test_judge_cannot_ignore_failed_baseline_even_without_findings(make_run, monkeypatch):
    monkeypatch.setattr("audit3.executor.shutil.which", lambda _: None)
    store, m = make_run()
    tools = tools_for(store, m, "juiz", "final")
    r = asyncio.run(tools.executor.execute(Request(kind="baseline", purpose="explicit MOCK baseline for controller validation"), "baseline", "baseline"))
    # This receipt is explicitly mock, not represented as a real container test.
    changed = r.model_copy(update={"status": "failed", "execution": "mock", "failed_assertions": 16})
    store.put(m.run_id, "receipts/" + r.id, changed)
    store.put(m.run_id, "baseline", {"ids": [r.id]})
    workflow = Workflow(store, m.run_id, runtime=MockRuntime())
    result = Judgment(summary="MOCK no issues", verdicts=[], new_findings=[], limitations=[])
    with pytest.raises(PolicyError, match="consultada"): workflow.validate_output(result, tools, final=True)
    tools.read_evidence(r.id)
    with pytest.raises(PolicyError, match="expectativas"): workflow.validate_output(result, tools, final=True)
    result.baseline_assessment = "MOCK expectation assessment; not a real test execution"
    workflow.validate_output(result, tools, final=True)
