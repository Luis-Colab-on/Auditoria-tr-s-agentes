"""Integration preconditions and evidence capture, never a simulated executor."""
import asyncio
import importlib.util
import os
import shutil
from pathlib import Path
import pytest
from audit3.config import Config, load_config
from audit3.diagnostics import network_permission
from audit3.executor import process
from audit3.report import export_zip, write_report
from audit3.security import object_hash
from audit3.validation import write_json


def require_docker(profile):
    if not shutil.which("docker"):
        pytest.skip("Docker CLI não disponível neste ambiente; nenhum teste da fixture executado no host")
    async def inspect():
        result = await process(["docker", "version", "--format", "{{.Server.Version}}"], 15)
        if result.code:
            return "Daemon Docker local indisponível ou sem permissão"
        if profile.engine == "compose":
            if int(result.stdout.strip().split(".")[0]) < 28:
                return "Perfil WordPress requer Docker 28+ para rede internal+isolated"
            compose = await process(["docker", "compose", "version", "--short"], 15)
            if compose.code:
                return "Docker Compose indisponível"
        images = [profile.image] if profile.engine == "docker" else [profile.wp_image, profile.db_image, profile.browser_image, profile.service_image]
        for image in images:
            result = await process(["docker", "image", "inspect", image, "--format", "{{.Id}}"], 15)
            if result.code:
                return "Imagem não adquirida previamente: " + image
        return None
    reason = asyncio.run(inspect())
    if reason:
        pytest.skip(reason)


def live_config():
    if os.environ.get("AUDIT3_LIVE_TEST") != "1":
        pytest.skip("Smoke Codex não solicitado; verificação financeira obrigatória antes de inferência")
    path = os.environ.get("AUDIT3_VALIDATION_CONFIG")
    if not path or not os.environ.get("AUDIT3_FINANCIAL_CONFIRMATION"):
        pytest.skip("Faltam configuração Codex e comprovação financeira explícitas")
    return load_config(Path(path))


def artifacts_path(name):
    root = os.environ.get("AUDIT3_VALIDATION_ARTIFACTS")
    return Path(root) / name if root else None


def save_receipt(label, store, manifest, receipt):
    path = artifacts_path(label + "-receipt.json")
    if path:
        write_json(path, {"manifest": manifest.model_dump(mode="json"), "receipt": receipt.model_dump(mode="json"),
            "test": store.get(manifest.run_id, "tests/" + receipt.id)})
        diagnostic = "setup-diagnostics/" + receipt.id
        if store.exists(manifest.run_id, diagnostic):
            write_json(path.with_name(label + "-setup.json"), store.get(manifest.run_id, diagnostic))


def save_live_artifacts(store, manifest):
    run_id = manifest.run_id
    report = write_report(store, run_id)
    path = artifacts_path("three-agents-report.json")
    events = sorted([store.get(run_id, "events/" + name) for name in store.names(run_id, "events")], key=lambda item: item["at"])
    if path:
        write_json(path, report)
        write_json(path.with_name("three-agents-usage.json"), store.get(run_id, "ledger"))
        write_json(path.with_name("three-agents-events.json"), events)
        write_json(path.with_name("three-agents-location.json"), {"run_id": run_id, "store": str(store.root)})
        export_zip(store, run_id, path.with_name("three-agents.zip"))
    return report, events


def assert_real_process(store, manifest, report, events):
    """Acceptance requires observed SDK calls/tools and a completed factual baseline."""
    run_id = manifest.run_id
    assert report["state"]["phase"] == "done", report["state"]
    assert report["state"]["status"] == "completed", report["state"]
    assert report['completion_assessment']['status'] == 'completed'
    assert not report['completion_assessment']['blockers']
    assert report['causal_validation']['valid'], report['causal_validation']['gaps']
    assert report["state"]["runtime_mode"] == "codex-app-server"
    assert not report["coverage"]["gaps"], report["coverage"]["gaps"]
    baseline = [r for r in report["receipts"] if r["owner"] == "baseline"]
    assert baseline and all(r["execution"] == "docker" and r["status"] == "failed" for r in baseline)
    calls = report["usage"]["calls"]
    assert {c["role"] for c in calls if c["status"] == "completed"} == {"auditor", "defensor", "juiz"}
    barrier = store.get(run_id, "barrier")
    for role in ("auditor", "defensor", "juiz"):
        assert barrier["initial_hashes"][role] == object_hash(store.get(run_id, f"roles/{role}/initial"))
    starts = [e for e in events if e["kind"] == "runner_started"]
    assert len({e["data"]["invocation_id"] for e in starts}) == len(starts)
    assert len({e["data"]["session"] for e in starts}) == 3
    owners = {}
    for event in starts:
        data = event["data"]
        assert data["session"]
        assert data["session"] == store.get(run_id, f"roles/{data['role']}/codex-session")["thread_id"]
        assert data["mode"] == "codex-app-server" and data["input_hash"]
        owners[data["invocation_id"]] = data["role"]
        if data["phase"].startswith("initial-") or data["phase"] == "blind":
            assert event["at"] < barrier["published_at"]
        else:
            assert event["at"] > barrier["published_at"]
    for call in calls:
        assert owners[call["invocation_id"]] == call["role"]
    completed = {(e["data"]["role"], e["data"]["phase"]) for e in events if e["kind"] == "runner_completed"}
    for role in ("auditor", "defensor"):
        for phase in ("initial-0000", "contest", "reply"):
            assert (role, phase) in completed
    assert {("juiz", p) for p in ("blind", "review", "final")} <= completed
    tools = [e["data"] for e in events if e["kind"] == "tool"]
    assert {e["role"] for e in tools if e["tool"] == "read_source"} == {"auditor", "defensor", "juiz"}
    assert any(e["role"] == "juiz" and e["tool"] == "read_evidence" for e in tools)
    assert any(e["tool"] == "submit_test" for e in tools), "smoke requires a model-submitted reproduction"
    assert any(r["owner"] in {"auditor", "defensor", "juiz"} and r["execution"] == "docker" and r["status"] in {"passed", "failed"} for r in report["receipts"])
