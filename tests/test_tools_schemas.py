import asyncio
import pytest
from pydantic import ValidationError
from audit3.config import Config, Profile
from audit3.executor import Executor
from audit3.schemas import CandidateFinding, SourceRef, TestRequest as Request, Verdict
from audit3.security import PolicyError, object_hash
from audit3.tools import SourceTools, ToolContext


def tools_for(store, manifest, role="auditor", phase="initial"):
    config = Config.model_validate(store.get(manifest.run_id, "config"))
    executor = Executor(store, manifest, config, Profile.model_validate(store.get(manifest.run_id, "profile")))
    return SourceTools(store, manifest, config, executor, ToolContext(manifest.run_id, role, phase, "test-invocation"))


def finding(m, **overrides):
    f = next(f for f in m.files if f.path == "app.py")
    data = dict(id="auditor-refund", source_id=m.source_id, title="synthetic", mechanism="refund sign", refs=[SourceRef(path=f.path, start=1, end=1, sha256=f.sha256)],
        invariant="decrease", trigger="refund", necessary_conditions=["amount positive"], complete_flow="caller -> refund", protections_considered=["upstream validation"], expected="decrease", observed="increase",
        evidence_ids=[], proof_method="static", static_demonstration="addition used where subtraction required", limitations=[], impact="balance error", real_environment_relevance="fixture only",
        production_observation="unknown", production_evidence=None, origin="unknown", origin_evidence_ids=[])
    data.update(overrides)
    return CandidateFinding(**data)


def test_no_role_or_run_identity_in_model_arguments(make_run):
    store, m = make_run()
    tools = tools_for(store, m)
    with pytest.raises(TypeError): tools.read_source("app.py", role="juiz")
    with pytest.raises(TypeError): tools.read_evidence("a"*24, run_id="b"*24)
    with pytest.raises(ValidationError): Request(kind="python", script="print(1)", purpose="test", owner="juiz")


def test_ranges_truncation_and_inspection_requires_actual_read(make_run):
    store, m = make_run({"app.py": "".join(f"x = {i}\n" for i in range(300))})
    tools = tools_for(store, m)
    f = finding(m)
    with pytest.raises(PolicyError): tools.validate_finding(f)
    r = tools.read_source("app.py", 1, 300)
    assert r["truncated"] and r["next_line"] == 161
    tools.validate_finding(f)
    with pytest.raises(PolicyError): tools.validate_ref(SourceRef(path="app.py", start=160, end=200, sha256=m.files[0].sha256))
    tools.read_source("app.py", 161, 300)
    tools.validate_ref(SourceRef(path="app.py", start=1, end=300, sha256=m.files[0].sha256))


def test_long_line_not_counted_as_read(make_run):
    store, m = make_run({"app.py": "x"*17000 + "\ny=1\n"})
    r = tools_for(store, m).read_source("app.py", 1, 2)
    assert r["truncated"] and r["lines"] == [] and r["omitted_long_line"] == 1


def test_other_role_receipt_and_prior_report_barrier(make_run, monkeypatch):
    monkeypatch.setattr("audit3.executor.shutil.which", lambda _: None)
    store, m = make_run({"app.py": "x=1\n", "audits/old.md": "old opinion\n"})
    auditor, defender = tools_for(store, m), tools_for(store, m, "defensor")
    receipt = asyncio.run(auditor.submit_test(Request(kind="python", script="print(1)", purpose="probe isolation")))
    with pytest.raises(PolicyError): defender.read_evidence(receipt["id"])
    with pytest.raises(PolicyError): defender.read_source("audits/old.md")
    with pytest.raises(PolicyError): defender.read_source("../roles/auditor/initial.json")
    hashes = {}
    for role in ("auditor", "defensor", "juiz"):
        store.put(m.run_id, f"roles/{role}/initial", {"frozen": role}, immutable=True)
        hashes[role] = object_hash({"frozen": role})
    store.put(m.run_id, "barrier", {"initial_hashes": hashes}, immutable=True)
    assert defender.read_evidence(receipt["id"])["receipt"]["status"] == "blocked"
    assert defender.read_source("audits/old.md")["lines"]


def test_missing_wrong_version_and_unexecuted_receipt_rejected(make_run, monkeypatch):
    monkeypatch.setattr("audit3.executor.shutil.which", lambda _: None)
    store, m = make_run()
    tools = tools_for(store, m)
    tools.read_source("app.py")
    with pytest.raises(PolicyError): tools.validate_finding(finding(m, proof_method="executed", evidence_ids=["a"*24]))
    receipt = asyncio.run(tools.submit_test(Request(kind="python", script="print(1)", purpose="synthetic check")))
    with pytest.raises(PolicyError): tools.validate_finding(finding(m, proof_method="executed", evidence_ids=[receipt["id"]]))
    receipt["source_id"] = "wrong"
    store.put(m.run_id, "receipts/" + receipt["id"], receipt)
    with pytest.raises(PolicyError): tools.read_evidence(receipt["id"])


def test_schemas_do_not_equate_hypothesis_with_required_fix():
    kwargs = dict(finding_id="x", classification="hipótese não confirmada", decision="corrigir agora", rationale="consensus", evidence_ids=[], proof_method="unconfirmed", impact="unknown", reach="unknown", correction_cost="unknown", regression_risk="unknown", reversibility="unknown", test_interpretation="not executed", mandatory_justification="votes", root_cause_id=None)
    with pytest.raises(ValidationError): Verdict(**kwargs)
    kwargs.update(classification="falha comprovada", proof_method="static", mandatory_justification="static verified flow")
    assert Verdict(**kwargs).decision == "corrigir agora"


def test_origin_cannot_be_claimed_without_comparison(make_run):
    _, m = make_run()
    with pytest.raises(ValidationError): finding(m, origin="preexisting")
    with pytest.raises(ValidationError): finding(m, origin="new")
    with pytest.raises(ValidationError): finding(m, production_observation="observed_with_evidence")
