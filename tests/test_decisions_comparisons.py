import asyncio
import json
import zipfile
from pathlib import Path
import pytest
from audit3.comparison import read_comparison, register_comparison
from audit3.report import build_report, export_zip
from audit3.schemas import Judgment, Opinion, Verdict
from audit3.security import PolicyError
from audit3.workflow import Workflow
from helpers import MockRuntime
from test_tools_schemas import finding, tools_for


def verdict(fid, cause="refund-sign", **kwargs):
    values = dict(finding_id=fid, classification="falha comprovada", decision="corrigir agora", rationale="static flow explicitly contradicts subtraction requirement", evidence_ids=[], proof_method="static",
        impact="balance error", reach="positive refunds", correction_cost="one operator", regression_risk="existing tests cover result", reversibility="small reversible change", test_interpretation="static proof; no executed test claim", mandatory_justification="visible addition contradicts requirement", root_cause_id=cause)
    values.update(kwargs)
    return Verdict(**values)


def test_new_judge_finding_gets_one_bounded_contestation_round(make_run, monkeypatch):
    monkeypatch.setattr("audit3.executor.shutil.which", lambda _: None)
    store, m = make_run()
    async def handler(role, phase, payload, tools, final):
        if phase == "review":
            tools.read_source("app.py")
            return Opinion(summary="MOCK new static observation", inspections=[], findings=[finding(m, id="juiz-new")], positions=[], limitations=[])
        if final:
            tools.read_source("app.py")
            return Judgment(summary="MOCK adjudication", verdicts=[verdict("juiz-new")], new_findings=[], limitations=[])
    runtime = MockRuntime(handler)
    state = asyncio.run(Workflow(store, m.run_id, runtime=runtime).run())
    assert state["phase"] == "done", state
    assert sum(c["phase"] == "extra-contest" for c in runtime.calls) == 2
    assert sum(c["phase"] == "extra-reply" for c in runtime.calls) == 2
    assert store.get(m.run_id, "material-review")["new_finding_ids"] == ["juiz-new"]


def test_new_final_finding_stays_pending_without_mandatory_fix(make_run, monkeypatch):
    monkeypatch.setattr("audit3.executor.shutil.which", lambda _: None)
    store, m = make_run()
    async def handler(role, phase, payload, tools, final):
        if final:
            tools.read_source("app.py")
            return Judgment(summary="MOCK final discovery", verdicts=[], new_findings=[finding(m, id="juiz-late")], limitations=[])
    state = asyncio.run(Workflow(store, m.run_id, runtime=MockRuntime(handler)).run())
    report = build_report(store, m.run_id)
    assert state["status"] == "partial"
    assert report["verdicts"][0]["decision"] == "investigar"


def test_defender_findings_are_included_and_duplicate_ids_keep_one_cause(make_run, monkeypatch):
    monkeypatch.setattr("audit3.executor.shutil.which", lambda _: None)
    store, m = make_run()
    async def handler(role, phase, payload, tools, final):
        if phase.startswith("initial"):
            tools.read_source("app.py")
            return Opinion(summary="MOCK independent discovery", inspections=[], findings=[finding(m, id=role+"-refund")], positions=[], limitations=[])
        if final:
            tools.read_source("app.py")
            return Judgment(summary="MOCK one mechanism", verdicts=[verdict("auditor-refund"), verdict("defensor-refund")], new_findings=[], limitations=[])
    state = asyncio.run(Workflow(store, m.run_id, runtime=MockRuntime(handler)).run())
    report = build_report(store, m.run_id)
    assert state["phase"] == "done", state
    assert len(report["verdicts"]) == 2
    assert report["metrics"]["unique_finding_ids"] == 2
    assert report["metrics"]["established_root_causes"] == 1


def test_different_mechanisms_in_same_file_cannot_merge(make_run):
    store, m = make_run()
    tools = tools_for(store, m, "juiz", "final")
    tools.read_source("app.py")
    a, b = finding(m), finding(m, id="defensor-other", mechanism="different independent defect")
    for role, f in (("auditor", a), ("defensor", b)):
        store.put(m.run_id, f"roles/{role}/phases/initial-0000", {"output": Opinion(summary="MOCK", inspections=[], findings=[f], positions=[], limitations=[]).model_dump(mode="json")})
    output = Judgment(summary="MOCK invalid merge", verdicts=[verdict(a.id), verdict(b.id)], new_findings=[], limitations=[])
    with pytest.raises(PolicyError): Workflow(store, m.run_id, runtime=MockRuntime()).validate_output(output, tools, final=True)


def test_version_comparison_preserves_preexisting_and_regression_as_evidence(make_run):
    store, before = make_run({"app.py": "def refund(b, a): return b+a\ndef fee(a): return max(0,a)*.02\n"})
    _, after = make_run({"app.py": "def refund(b, a): return b+a\ndef fee(a): return a*.02\n"})
    comp = register_comparison(store, before.run_id, after.run_id, "identify preexisting vs regression")
    evidence = read_comparison(store, after.run_id, comp["id"])
    assert "max(0,a)" in evidence["before_source_excerpts"][0]["text"]
    assert evidence["equivalent_execution_pairs"] == []
    tools = tools_for(store, after)
    tools.read_source("app.py")
    tools.validate_finding(finding(after, origin="preexisting", origin_evidence_ids=[comp["id"]]))
    tools.validate_finding(finding(after, origin="new", origin_evidence_ids=[comp["id"]]))
    # Validation checks provenance; it intentionally cannot decide which origin is true.
    changed = store.path(before.run_id, "source/app.py")
    changed.chmod(0o644)
    changed.write_text("tampered")
    with pytest.raises(PolicyError): read_comparison(store, after.run_id, comp["id"])


def test_export_does_not_leak_api_key_or_integrity_key(make_run, monkeypatch, tmp_path):
    monkeypatch.setattr("audit3.executor.shutil.which", lambda _: None)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-" + "SYNTHETIC_CANARY"*3)
    store, m = make_run()
    asyncio.run(Workflow(store, m.run_id, runtime=MockRuntime()).run())
    path = export_zip(store, m.run_id, tmp_path / "export.zip")
    with zipfile.ZipFile(path) as z:
        data = b"\n".join(z.read(n) for n in z.namelist())
        assert b"SYNTHETIC_CANARY" not in data
        assert store.key.hex().encode() not in data and store.key not in data


def test_resume_after_interrupted_phase_uses_next_attempt(make_run, monkeypatch):
    monkeypatch.setattr("audit3.executor.shutil.which", lambda _: None)
    store, m = make_run()
    store.put(m.run_id, "roles/auditor/attempts/initial-0000-0", {"invocation_id": "old-interrupted", "started_at": "fixture", "input_hash": "fixture"}, immutable=True)
    runtime = MockRuntime()
    state = asyncio.run(Workflow(store, m.run_id, runtime=runtime).run(resume=True))
    assert state["phase"] == "done", state
    assert store.exists(m.run_id, "roles/auditor/attempts/initial-0000-1")
    assert sum(c["role"] == "auditor" and c["phase"] == "initial-0000" for c in runtime.calls) == 1
