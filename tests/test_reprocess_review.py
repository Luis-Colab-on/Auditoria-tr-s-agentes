"""Read-only derived review of explicitly MOCK historical response contracts."""
import asyncio
import json
from pathlib import Path
import pytest
from audit3.reprocess import ReadOnlyStore, response_view, reprocess_response
from audit3.report import build_report
from audit3.completion import context_hash
from audit3.scope_review import make_review
from audit3.schemas import Judgment
from audit3.smoke_causality import prepare_smoke_evidence
from audit3.workflow import Workflow
from audit3.security import PolicyError
from helpers import MockRuntime
from test_smoke_causality import smoke_run, SyntheticExecutor


def historical_mock(smoke_run):
    store, manifest, config = smoke_run
    executor = SyntheticExecutor(store, manifest)
    asyncio.run(prepare_smoke_evidence(store, manifest, config, executor))
    async def handler(role, phase, payload, tools, final):
        if final:
            for eid in payload['baseline_receipts']:
                tools.read_evidence(eid)
            return Judgment(summary='MOCK final response; no model or container execution',
                baseline_assessment='MOCK signed refunds fail; positive payments remain controls.',
                verdicts=[], new_findings=[], limitations=[])
    state = asyncio.run(Workflow(store, manifest.run_id, runtime=MockRuntime(handler), executor=executor).run())
    assert state['phase'] == 'done'
    phase = store.get(manifest.run_id, 'roles/juiz/phases/final')
    invocation = 'b' * 24
    raw = json.dumps(phase['output'], ensure_ascii=False).encode()
    store.put(manifest.run_id, 'codex-turns/' + invocation, {
        'status': 'completed', 'role': 'juiz', 'phase': 'final',
        'output': raw.decode(), 'finished_at': phase['published_at'],
        'fixture_only': 'MOCK saved checkpoint, never real inference'}, immutable=True)
    return store, manifest, invocation, raw


def bytes_by_path(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}


def test_reprocessing_uses_supplied_certificates_without_writing_smoke_contract(smoke_run):
    store, manifest, invocation, raw = historical_mock(smoke_run)
    before = bytes_by_path(store.root)
    view = response_view(ReadOnlyStore(store.root), manifest.run_id, invocation, raw, [])
    assert view.get(manifest.run_id, 'assessment/causal-certificates') == []
    assert view.get(manifest.run_id, 'judgment') == json.loads(raw)
    assert bytes_by_path(store.root) == before


def test_reprocessed_scope_preserves_raw_state_and_current_context(smoke_run):
    store, manifest, invocation, raw = historical_mock(smoke_run)
    readonly = ReadOnlyStore(store.root)
    view = response_view(readonly, manifest.run_id, invocation, raw, [])
    # A saved unrelated/stale review must not interfere with explicit reprocessing.
    store.put(manifest.run_id, 'assessment/completion-review', {'version': 'obsolete'})
    original = store.get(manifest.run_id, 'state')
    before = bytes_by_path(store.root)
    current = build_report(view, manifest.run_id, use_review=False)
    review = make_review(current)
    report, _ = reprocess_response(readonly, manifest.run_id, invocation, raw, [], review)
    assert report['state'] == original == report['derivation']['original_historical_state']
    assert report['completion_assessment']['status'] == 'completed', report['completion_assessment']['blockers']
    assert report['state']['status'] == 'partial'
    assert report['completion_assessment']['context_hash'] == context_hash(report)
    assert report['completion_review'] == review
    assert report['state']['runtime_mode'] == 'mock'
    assert 'evidências reais' not in report['validation']
    assert report['derivation']['new_real_execution'] is False
    assert bytes_by_path(store.root) == before


def test_reprocessing_rejects_changed_response_without_modifying_any_record(smoke_run):
    store, manifest, invocation, raw = historical_mock(smoke_run)
    before = bytes_by_path(store.root)
    changed = json.loads(raw)
    changed['summary'] = 'different response'
    with pytest.raises(PolicyError, match='checkpoint original'):
        response_view(ReadOnlyStore(store.root), manifest.run_id, invocation,
            json.dumps(changed).encode(), [])
    assert bytes_by_path(store.root) == before
