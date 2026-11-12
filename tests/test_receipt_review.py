"""Local receipt/review contracts. Docker and model dependencies are simulated."""
import asyncio
import copy
import json
from pathlib import Path
import pytest
from audit3.completion import limitation_messages, assess_completion
from audit3.receipt_review import (MEASUREMENT_NOTE, MEASUREMENT_CRITERION, COUNTERS,
    supporting_receipt_evidence, validate_receipt_note)
from audit3.security import PolicyError, digest
from test_assessment import completion_fixture
from test_smoke_causality import smoke_run


def note(report):
    return next(item for item in limitation_messages(report).values() if item['text'] == MEASUREMENT_NOTE)


def annotation(report):
    return {'kind': 'procedure_note', 'criterion': MEASUREMENT_CRITERION,
        'justification': 'Qualitative review of the recorded outcomes; numerical counts are not required and remain unknown.',
        'evidence': supporting_receipt_evidence(report, note(report))}


def test_measurement_note_preserves_receipt_and_unknown_counts():
    report = completion_fixture()
    original = copy.deepcopy(report)
    validate_receipt_note(report, note(report), annotation(report), {'quantitative_measurement_required': False})
    assert report == original
    assert report['receipts'][0]['limitations'] == [MEASUREMENT_NOTE]
    assert all(report['receipts'][0][key] is None for key in COUNTERS)
    assert report['usage']['tokens'] is None and report['usage']['known_cost_usd'] is None


@pytest.mark.parametrize('failure', ['timeout', 'truncated', 'not_executed', 'mock', 'other_run',
    'other_source', 'other_profile', 'stderr', 'missing_field', 'count', 'duplicate', 'exit_code', 'metadata'])
def test_measurement_note_does_not_hide_bad_receipt(failure):
    report = completion_fixture()
    receipt = report['receipts'][0]
    if failure == 'timeout': receipt['timeout'] = True
    if failure == 'truncated': receipt['output_truncated'] = True
    if failure == 'not_executed': receipt.update(execution='not_executed', status='blocked')
    if failure == 'mock': receipt['execution'] = 'mock'
    if failure == 'other_run': receipt['run_id'] = 'f' * 24
    if failure == 'other_source': receipt['source_id'] = 'other'
    if failure == 'other_profile': receipt['profile_hash'] = 'f' * 64
    if failure == 'stderr': receipt['stderr'] += ' modified'
    if failure == 'missing_field': del receipt['command']
    if failure == 'count': del receipt['cases']
    if failure == 'duplicate': report['receipts'].append(copy.deepcopy(receipt))
    if failure == 'exit_code': receipt['exit_code'] = 0
    if failure == 'metadata': receipt['image_ids'] = {}
    with pytest.raises(PolicyError):
        supporting_receipt_evidence(report, note(report))


@pytest.mark.parametrize('origin', ['opinion', 'judgment', 'manifest'])
def test_identical_model_or_manifest_text_cannot_inherit_receipt_authority(origin):
    report = completion_fixture()
    if origin == 'opinion': report['opinions']['auditor'][0]['output']['limitations'] = [MEASUREMENT_NOTE]
    if origin == 'judgment': report['judgment']['limitations'] = [MEASUREMENT_NOTE]
    if origin == 'manifest': report['manifest']['limitations'].append(MEASUREMENT_NOTE)
    with pytest.raises(PolicyError, match='proveniência exclusiva'):
        supporting_receipt_evidence(report, note(report))


def test_state_copy_requires_authentic_receipt_origin():
    report = completion_fixture()
    report['state']['limitations'] = [MEASUREMENT_NOTE]
    assert supporting_receipt_evidence(report, note(report))[-1] == '/receipts/0'
    report['receipts'][0]['limitations'] = []
    with pytest.raises(PolicyError, match='sem receipt original'):
        supporting_receipt_evidence(report, note(report))


@pytest.mark.parametrize('contract', [None, {}, {'quantitative_measurement_required': True},
                                    {'quantitative_measurement_required': 'false'}])
def test_required_or_unknown_measurements_are_not_waived(contract):
    report = completion_fixture()
    with pytest.raises(PolicyError, match='métricas exigidas'):
        validate_receipt_note(report, note(report), annotation(report), contract)


def test_unknown_receipt_limitation_still_blocks_after_measurement_review():
    from audit3.scope_review import make_review
    report = completion_fixture()
    report['receipts'][0]['limitations'].append('Isolation verification unavailable')
    assessment = assess_completion(report, make_review(report))
    assert assessment['status'] == 'partial'
    assert any(b.get('text') == 'Isolation verification unavailable' for b in assessment['blockers'])
    assert next(x for x in assessment['limitations'] if x['text'] == MEASUREMENT_NOTE)['kind'] == 'procedure_note'


class SimulatedDocker:
    """Only the external process responses are faked; no process is spawned."""
    def __init__(self, exit_code=1, timeout=False, invalid_isolation=False):
        self.exit_code, self.timeout, self.invalid_isolation = exit_code, timeout, invalid_isolation
        self.calls, self.mounts = [], []

    async def __call__(self, argv, timeout, limit=64000):
        from audit3.executor import ProcessResult
        from test_executor import inspected
        self.calls.append(list(argv))
        stdout, stderr, code, timed = '', '', 0, False
        if argv[1] == 'version': stdout = 'MOCK Docker process response only'
        elif argv[1:3] == ['image', 'inspect']: stdout = 'sha256:' + 'e' * 64
        elif argv[1] == 'create':
            self.mounts = []
            for item in argv:
                if item.startswith('type=bind,source='):
                    parts = dict(part.split('=', 1) for part in item.split(',') if '=' in part)
                    self.mounts.append({'Type': 'bind', 'Source': parts['source'], 'Destination': parts['target'], 'RW': False})
        elif argv[1] == 'inspect' and '--format' not in argv:
            info = inspected()
            info['Mounts'] = self.mounts
            if self.invalid_isolation: info['HostConfig']['NetworkMode'] = 'host'
            stdout = json.dumps([info])
        elif argv[1] == 'inspect': stdout = json.dumps({'ExitCode': self.exit_code, 'OOMKilled': False})
        elif argv[1] == 'start':
            stdout = 'MOCK process transcript; no audited code executed'
            code, timed = self.exit_code, self.timeout
        elif argv[1] != 'rm': pytest.fail('Unexpected simulated Docker command: ' + repr(argv))
        return ProcessResult(code, stdout, stderr, digest(stdout.encode()), digest(stderr.encode()), False, timed)


def controller_run(smoke_run, monkeypatch, docker=None):
    from audit3.config import Profile
    from audit3.executor import Executor
    from audit3.report import build_report
    from audit3.schemas import Judgment
    from audit3.workflow import Workflow
    from helpers import MockRuntime
    store, manifest, config = smoke_run
    docker = docker or SimulatedDocker()
    monkeypatch.setattr('audit3.executor.process', docker)
    monkeypatch.setattr('audit3.executor.shutil.which', lambda name: '/mock/docker' if name == 'docker' else None)
    async def handler(role, phase, payload, tools, final):
        if final:
            for eid in payload['baseline_receipts']:
                tools.read_evidence(eid)
            return Judgment(summary='MOCK controller protocol', verdicts=[], new_findings=[], limitations=[],
                baseline_assessment='MOCK review of simulated external process result; no real execution claim.')
    runtime = MockRuntime(handler)
    executor = Executor(store, manifest, config, Profile(name='synthetic'))
    state = asyncio.run(Workflow(store, manifest.run_id, runtime=runtime, executor=executor).run())
    assert state['phase'] == 'done', state
    return store, manifest, build_report(store, manifest.run_id), docker


def test_actual_executor_receipt_reaches_review_without_losing_caveat(smoke_run, monkeypatch):
    from audit3.scope_review import make_review
    from audit3.acceptance import assert_scoped_completion
    store, manifest, report, docker = controller_run(smoke_run, monkeypatch)
    original = {str(p): p.read_bytes() for p in store.path(manifest.run_id).rglob('*') if p.is_file()}
    assert report['state']['status'] == 'partial' and report['state']['runtime_mode'] == 'mock'
    assert len(report['receipts']) == 1
    assert report['receipts'][0]['limitations'] == [MEASUREMENT_NOTE]
    assert all(report['receipts'][0][key] is None for key in COUNTERS)
    assert any(call[1] == 'start' for call in docker.calls)
    report['completion_review'] = make_review(report)
    report['completion_assessment'] = assess_completion(report, report['completion_review'])
    assert report['completion_assessment']['status'] == 'completed', report['completion_assessment']['blockers']
    with pytest.raises(AssertionError, match='Backend mock'):
        assert_scoped_completion(report)
    assert {str(p): p.read_bytes() for p in store.path(manifest.run_id).rglob('*') if p.is_file()} == original


@pytest.mark.parametrize('failure', ['timeout', 'isolation'])
def test_actual_executor_failure_remains_blocking(smoke_run, monkeypatch, failure):
    from audit3.scope_review import make_review
    docker = SimulatedDocker(timeout=failure == 'timeout', invalid_isolation=failure == 'isolation')
    _, _, report, _ = controller_run(smoke_run, monkeypatch, docker)
    result = assess_completion(report, make_review(report))
    assert result['status'] == 'partial' and result['blockers']
    assert any(message['text'] != MEASUREMENT_NOTE and message['kind'] == 'unresolved'
               for message in result['limitations'])
