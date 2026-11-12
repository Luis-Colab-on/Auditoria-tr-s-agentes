"""Offline acceptance contracts only: MOCK reports never prove a real audit."""
import copy
import json
import pytest
from audit3.acceptance import assert_scoped_completion
from audit3.completion import assess_completion, context_hash
from audit3.scope_review import make_review, review_report
from audit3.security import PolicyError
from test_assessment import completion_fixture, identify_review


def reviewed_report():
    report = completion_fixture()
    report['completion_review'] = make_review(report)
    report['completion_assessment'] = assess_completion(report, report['completion_review'])
    return report


def test_raw_partial_is_accepted_only_with_current_supported_scope_review():
    report = completion_fixture()
    raw = copy.deepcopy(report)
    evaluation = review_report(report)
    assert report == raw
    report.update(completion_review=evaluation['review'], completion_assessment=evaluation['completion_assessment'])
    assert assert_scoped_completion(report)['status'] == 'passed'
    assert report['state'] == raw['state'] and report['state']['status'] == 'partial'
    assert report['opinions'] == raw['opinions'] and report['judgment'] == raw['judgment']


def test_absent_review_is_an_explicit_pending_result():
    report = completion_fixture()
    report['completion_assessment'] = assess_completion(report)
    assert report['completion_assessment']['review_status'] == 'pending'
    with pytest.raises(AssertionError, match='Revisão de conclusão pendente'):
        assert_scoped_completion(report)


@pytest.mark.parametrize('change', ['receipt', 'judgment', 'state', 'event_hash', 'comparison', 'objective'])
def test_changed_factual_context_invalidates_review(change):
    report = reviewed_report()
    if change == 'receipt': report['receipts'][0]['stderr'] += ' changed'
    if change == 'judgment': report['judgment']['summary'] = 'changed final response'
    if change == 'state': report['state']['elapsed_seconds'] = 900
    if change == 'event_hash': report['structural_checks']['evidence_context_hash'] = 'changed'
    if change == 'comparison': report['comparisons'] = [{'changed_evidence': True}]
    if change == 'objective': report['manifest']['requirements'] = 'certify production'
    with pytest.raises(PolicyError, match='objetivo/evidências'):
        assess_completion(report, report['completion_review'])


def test_pointer_and_justification_alone_do_not_discharge_message():
    report = reviewed_report()
    annotation = next(iter(report['completion_review']['messages'].values()))
    annotation.pop('criterion')
    annotation['evidence'] = ['/manifest/requirements']
    identify_review(report['completion_review'])
    result = assess_completion(report, report['completion_review'])
    assert result['status'] == 'partial'
    assert any(b['kind'] == 'unresolved' for b in result['blockers'])


@pytest.mark.parametrize('failure', ['blind', 'phase', 'judgment', 'evidence', 'source', 'causality', 'limit', 'timeout', 'unknown_note', 'receipt_note'])
def test_review_cannot_waive_structural_or_operational_failures(failure):
    report = completion_fixture()
    if failure == 'blind': report['coverage']['independent_investigation']['valid'] = False
    if failure == 'phase': report['state']['completed'].remove('juiz/review')
    if failure == 'judgment': report['judgment'] = None
    if failure == 'evidence': report['structural_checks']['final_validation'] = False
    if failure == 'source': report['structural_checks']['source_integrity'] = False
    if failure == 'causality': report['causal_validation']['valid'] = False
    if failure == 'limit': report['structural_checks']['limits_valid'] = False
    if failure == 'timeout': report['state']['limitations'] = ['limite de tempo total']
    if failure == 'unknown_note': report['judgment']['limitations'] = ['Entry point unavailable']
    if failure == 'receipt_note': report['receipts'][0]['limitations'] = ['isolation violation']
    result = review_report(report)
    assert result['completion_assessment']['status'] == 'partial'
    assert result['completion_assessment']['blockers']


def test_mock_never_becomes_real_through_review():
    report = completion_fixture()
    report['state']['runtime_mode'] = 'mock'
    report.update(completion_review=make_review(report))
    report['completion_assessment'] = assess_completion(report, report['completion_review'])
    with pytest.raises(AssertionError, match='Backend mock'):
        assert_scoped_completion(report)


def test_interrupted_final_never_accepted():
    report = completion_fixture()
    report['state']['phase'] = 'final'
    report['state']['completed'].remove('juiz/final')
    report['judgment'] = None
    report.update(completion_review=make_review(report))
    report['completion_assessment'] = assess_completion(report, report['completion_review'])
    with pytest.raises(AssertionError, match='Protocolo interrompido'):
        assert_scoped_completion(report)


def test_cli_separate_evaluation_preserves_every_original_record(make_run, tmp_path):
    from audit3.cli import main
    store, manifest = make_run()
    before = {str(p): p.read_bytes() for p in store.root.rglob('*') if p.is_file()}
    output = tmp_path / 'separate-review.json'
    assert main(['--store', str(store.root), 'review-completion', manifest.run_id, '--output', str(output)]) == 2
    assert json.loads(output.read_text())['completion_assessment']['status'] == 'partial'
    assert {str(p): p.read_bytes() for p in store.root.rglob('*') if p.is_file()} == before
    assert main(['--store', str(store.root), 'review-completion', manifest.run_id, '--output', str(output)]) == 2
    assert {str(p): p.read_bytes() for p in store.root.rglob('*') if p.is_file()} == before


def test_full_offline_workflow_and_review_preserve_raw_partial_and_mock(smoke_run):
    """End-to-end controller path with explicit fake runtime/executor, no models."""
    import asyncio
    from audit3.workflow import Workflow
    from audit3.report import build_report
    from audit3.schemas import Judgment
    from audit3.smoke_causality import prepare_smoke_evidence
    from helpers import MockRuntime
    from test_smoke_causality import SyntheticExecutor
    store, manifest, config = smoke_run
    executor = SyntheticExecutor(store, manifest)
    asyncio.run(prepare_smoke_evidence(store, manifest, config, executor))
    async def handler(role, phase, payload, tools, final):
        if final:
            for eid in payload['baseline_receipts']:
                tools.read_evidence(eid)
            return Judgment(summary='MOCK no findings protocol fixture', verdicts=[], new_findings=[],
                baseline_assessment='MOCK expected refunds fail and positive controls pass.', limitations=[])
    state = asyncio.run(Workflow(store, manifest.run_id, runtime=MockRuntime(handler), executor=executor).run())
    assert state['phase'] == 'done' and state['status'] == 'partial'
    before = {str(p): p.read_bytes() for p in store.path(manifest.run_id).rglob('*') if p.is_file()}
    report = build_report(store, manifest.run_id)
    review = make_review(report)
    assessment = assess_completion(report, review)
    assert assessment['status'] == 'completed', assessment['blockers']
    report.update(completion_review=review, completion_assessment=assessment)
    with pytest.raises(AssertionError, match='Backend mock'):
        assert_scoped_completion(report)
    assert {str(p): p.read_bytes() for p in store.path(manifest.run_id).rglob('*') if p.is_file()} == before


# Importing registers a synthetic ZIP fixture, never executes its source.
from test_smoke_causality import smoke_run
