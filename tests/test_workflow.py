import asyncio
import json
import pytest
from audit3.agents import Budget, BudgetExceeded, SDKRuntime
from audit3.config import Config, Limits
from audit3.report import build_report, export_zip
from audit3.schemas import Opinion
from audit3.security import PolicyError
from audit3.workflow import Workflow, batches
from helpers import MockRuntime


def test_independent_inputs_barrier_debate_and_no_change_mock(make_run, monkeypatch, tmp_path):
    monkeypatch.setattr("audit3.executor.shutil.which", lambda _: None)
    store, m = make_run()
    runtime = MockRuntime()
    state = asyncio.run(Workflow(store, m.run_id, runtime=runtime).run())
    assert state["status"] == "partial"  # Docker unavailable must stay visible.
    assert state["technical_result"].startswith("MOCK")
    first = [c for c in runtime.calls if c["phase"].startswith("initial") or c["phase"] == "blind"]
    assert {c["role"] for c in first} == {"auditor", "defensor", "juiz"}
    assert len({c["context"].invocation_id for c in first}) == 3
    assert all("published_opinions" not in c["payload"] for c in first)
    assert all(c["payload"]["own_observations"] == [] for c in first)
    assert first[0]["payload"]["manifest"] == first[1]["payload"]["manifest"]
    assert store.exists(m.run_id, "barrier")
    assert [(c["role"], c["phase"]) for c in runtime.calls][-2:] == [("juiz", "review"), ("juiz", "final")]
    assert sum(c["phase"] == "contest" for c in runtime.calls) == 2
    assert sum(c["phase"] == "reply" for c in runtime.calls) == 2
    report = build_report(store, m.run_id)
    assert report["metrics"]["unique_finding_ids"] == 0
    assert report["validation"] == "implementado, integração real ainda não validada"
    assert report["usage"]["calls"] == []
    artifact = export_zip(store, m.run_id, tmp_path / "report.zip")
    import zipfile
    with zipfile.ZipFile(artifact) as z:
        assert {"report.md", "report.json", "manifest.json", "coverage.json", "checksums.json"} <= set(z.namelist())
        assert not any("integrity-key" in n or "history" in n for n in z.namelist())


def test_invalid_json_bounded_no_fake_success(make_run, monkeypatch):
    monkeypatch.setattr("audit3.executor.shutil.which", lambda _: None)
    store, m = make_run()
    async def invalid(*args): return "{not json"
    runtime = MockRuntime(invalid)
    state = asyncio.run(Workflow(store, m.run_id, runtime=runtime).run())
    assert state["status"] == "partial" and not store.exists(m.run_id, "barrier")
    assert len([c for c in runtime.calls if c["role"] == "auditor"]) == 2
    assert not store.exists(m.run_id, "judgment")


def test_budget_reserves_unknown_and_counts_retries(make_run):
    cfg = Config(limits=Limits(budget_usd=1, call_reserve_usd=.5, max_calls=2))
    store, m = make_run(config=cfg)
    async def exercise():
        budget = Budget(store, m.run_id, cfg)
        first = await budget.reserve("auditor", "one")
        await budget.finish(first, error="RateLimitError")
        second = await budget.reserve("auditor", "retry")
        await budget.finish(second, error="Timeout")
        with pytest.raises(BudgetExceeded): await budget.reserve("defensor", "three")
    asyncio.run(exercise())
    ledger = store.get(m.run_id, "ledger")
    assert ledger["unknown_cost_calls"] == 2 and ledger["tokens"] is None
    assert all(c["cost_usd"] is None for c in ledger["calls"])


def test_budget_observed_tokens_and_cost(make_run):
    cfg = Config(input_usd_per_million=1, output_usd_per_million=2)
    store, m = make_run(config=cfg)
    class Usage:
        input_tokens, output_tokens = 1000, 100
    async def exercise():
        b = Budget(store, m.run_id, cfg)
        cid = await b.reserve("juiz", "one")
        await b.finish(cid, Usage())
    asyncio.run(exercise())
    ledger = store.get(m.run_id, "ledger")
    assert ledger["tokens"] == 1100
    assert ledger["known_cost_usd"] is None  # Pro tokens never converted using API prices


def test_cancel_active_and_resume_prepared(make_run, monkeypatch):
    monkeypatch.setattr("audit3.executor.shutil.which", lambda _: None)
    store, m = make_run()
    store.put(m.run_id, "cancel", {"test": True})
    first = asyncio.run(Workflow(store, m.run_id, runtime=MockRuntime()).run())
    assert first["status"] == "cancelled"
    second = asyncio.run(Workflow(store, m.run_id, runtime=MockRuntime()).run(resume=True))
    assert second["phase"] == "done"


def test_active_cancel_interrupts_calls(make_run, monkeypatch):
    monkeypatch.setattr("audit3.executor.shutil.which", lambda _: None)
    store, m = make_run()
    async def slow(*args): await asyncio.sleep(20)
    async def exercise():
        task = asyncio.create_task(Workflow(store, m.run_id, runtime=MockRuntime(slow)).run())
        await asyncio.sleep(.05)
        store.put(m.run_id, "cancel", {"test": True})
        return await asyncio.wait_for(task, 2)
    state = asyncio.run(exercise())
    assert state["status"] == "cancelled"


def test_total_timeout_and_batch_coverage(make_run, monkeypatch):
    monkeypatch.setattr("audit3.executor.shutil.which", lambda _: None)
    store, m = make_run({"app.py": "x=1\n"*150}, config=Config(limits=Limits(total_seconds=1, batch_lines=50)))
    assert len(batches(m, 50)) == 3
    async def slow(*args): await asyncio.sleep(20)
    state = asyncio.run(Workflow(store, m.run_id, runtime=MockRuntime(slow)).run())
    assert state["status"] == "partial" and state["technical_result"] == "inconclusivo"
    assert build_report(store, m.run_id)["coverage"]["roles"]["auditor"]["app.py"]["consulted_lines"] == 0


def test_resume_completed_does_not_repeat_calls(make_run, monkeypatch):
    monkeypatch.setattr("audit3.executor.shutil.which", lambda _: None)
    store, m = make_run()
    runtime = MockRuntime()
    asyncio.run(Workflow(store, m.run_id, runtime=runtime).run())
    count = len(runtime.calls)
    asyncio.run(Workflow(store, m.run_id, runtime=runtime).run(resume=True))
    assert len(runtime.calls) == count


def test_missing_codex_is_honest_and_resumable(make_run, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("audit3.executor.shutil.which", lambda _: None)
    store, m = make_run()
    state = asyncio.run(Workflow(store, m.run_id).run())
    assert state["status"] == "blocked"
    assert "Codex" in state["limitations"][0]
    assert store.get(m.run_id, "ledger")["calls"] == []
    assert not store.exists(m.run_id, "barrier")
    resumed = asyncio.run(Workflow(store, m.run_id, runtime=MockRuntime()).run(resume=True))
    assert resumed["phase"] == "done"
    assert len(store.names(m.run_id, "receipts")) == 1


def test_controller_single_writer_lock(make_run):
    store, m = make_run()
    with store.lock(m.run_id):
        with pytest.raises(PolicyError):
            with store.lock(m.run_id): pass
