"""Offline tests of a final-only time extension; no real model or Docker."""
import asyncio
import copy
from datetime import datetime, timedelta, timezone
import pytest
from audit3.config import Config, Limits
from audit3.completion import protocol_phases
from audit3.codex_runtime import CodexRuntime
from audit3.agents import RuntimePaused, BudgetExceeded
from audit3.operational import GLOBAL_AUTHORIZATION, total_seconds
from audit3.schemas import Opinion, Judgment
from audit3.security import now, object_hash, PolicyError
from audit3.tools import SourceTools, ToolContext
from audit3.workflow import Workflow
from test_codex_runtime import FakeRPC, proof
from test_operational import authorize as authorize_turn


def setup_extension(make_run):
    cfg = Config(limits=Limits(max_calls=16, total_seconds=900))
    store, m = make_run(content={'plugin.php': '<?php\n// MOCK synthetic PHP scope\n'}, config=cfg)
    runtime = CodexRuntime(store, m.run_id, cfg)
    rpc = FakeRPC(runtime.home); runtime.rpc = rpc
    store.put(m.run_id, 'financial-confirmation', proof())
    async def session():
        return await runtime.session('juiz', await runtime.preflight())
    thread = asyncio.run(session())
    from helpers import initial_investigation
    initial_opinions = {role: initial_investigation(store, m, role).model_dump(mode='json')
                        for role in ('auditor', 'defensor', 'juiz')}
    opinion = Opinion(summary='MOCK completed phase', inspections=[], findings=[], positions=[], limitations=[]).model_dump(mode='json')
    prior_phases = set(protocol_phases(m, cfg)) - {'juiz/final'}
    hashes = {}
    for item in prior_phases:
        role, phase = item.split('/')
        output = initial_opinions[role] if phase.startswith('initial-') or phase == 'blind' else opinion
        value = {'role': role, 'phase': phase, 'output': copy.deepcopy(output), 'published_at': now()}
        store.put(m.run_id, f'roles/{role}/phases/{phase}', value)
        hashes[item] = object_hash(value)
    initial = {}
    for role in ('auditor', 'defensor', 'juiz'):
        value = {'role': role, 'opinions': [copy.deepcopy(initial_opinions[role])]}
        store.put(m.run_id, f'roles/{role}/initial', value)
        initial[role] = object_hash(value)
    store.put(m.run_id, 'barrier', {'published_at': now(), 'initial_hashes': initial})
    store.put(m.run_id, 'baseline', {'ids': []})
    store.put(m.run_id, 'material-review', {'additional_round': False, 'new_finding_ids': [], 'new_receipt_ids': []})
    store.put(m.run_id, 'review-start', {'finding_ids': [], 'receipt_ids': []})
    state = store.get(m.run_id, 'state')
    state.update(status='partial', phase='final', completed=sorted(prior_phases), elapsed_seconds=900.04)
    store.put(m.run_id, 'state', state)
    old = 'f' * 24
    store.put(m.run_id, 'codex-turns/' + old, {'role': 'juiz', 'phase': 'final', 'status': 'ambiguous',
        'error_type': 'TimeoutError', 'thread_id': thread, 'turn_id': 'MOCK-old-final',
        'timeout': {'origin': 'global_deadline'}})
    store.put(m.run_id, 'roles/juiz/attempts/final-0', {'invocation_id': old})
    store.put(m.run_id, 'roles/juiz/attempts/final-0-interrupted', {'source': 'official_app_server_thread_read',
        'status': 'interrupted', 'invocation_id': old, 'thread_id': thread, 'turn_id': 'MOCK-old-final'})
    calls = [{'id': str(i), 'role': 'juiz', 'status': 'error', 'input_tokens': None, 'output_tokens': None} for i in range(10)]
    store.put(m.run_id, 'ledger', {'calls': calls, 'tokens': None, 'known_cost_usd': None, 'unknown_cost_calls': 10})
    snap_name = 'validation/global-extension-baseline'
    store.put(m.run_id, snap_name, {'run_id': m.run_id, 'config_hash': m.config_hash,
        'calls': calls, 'elapsed_seconds': 900.04, 'phase_hashes': hashes})
    auth = {'source': 'explicit_operator_authorization', 'run_id': m.run_id, 'config_hash': m.config_hash,
        'base_total_seconds': 900, 'total_seconds': 1500, 'allowed_phases': ['juiz/final'],
        'snapshot_record': snap_name, 'timeout_invocation_id': old}
    store.put(m.run_id, GLOBAL_AUTHORIZATION, auth)
    authorize_turn(store, m)
    tools = SourceTools(store, m, cfg, None, ToolContext(m.run_id, 'juiz', 'final', 'a' * 24))
    return store, m, runtime, rpc, tools, auth


def test_extension_continues_only_final_and_preserves_all_old_calls_and_phases(make_run):
    store, m, runtime, rpc, tools, _ = setup_extension(make_run)
    before = store.get(m.run_id, 'ledger')['calls']
    frozen = {n: store.path(m.run_id, n + '.json').read_bytes() for n in (
        'config', 'manifest', 'roles/auditor/phases/initial-0000', 'roles/defensor/phases/initial-0000',
        'roles/juiz/phases/blind', 'roles/juiz/phases/review', 'roles/juiz/attempts/final-0', 'codex-turns/' + 'f' * 24)}
    original = rpc.request
    async def request(method, params, **kwargs):
        result = await original(method, params, **kwargs)
        if method == 'turn/start':
            assert params['threadId'] == store.get(m.run_id, 'roles/juiz/codex-session')['thread_id']
            assert params['outputSchema']['title'] == 'Judgment'
            # Replace the MOCK default Opinion with the final contract.
            while not rpc.events.empty(): rpc.events.get_nowait()
            turn = result['turn']['id']; base = {'threadId': params['threadId'], 'turnId': turn}
            output = Judgment(summary='MOCK final', baseline_assessment='MOCK', verdicts=[], new_findings=[], limitations=[]).model_dump_json()
            rpc.events.put_nowait({'method': 'item/completed', 'params': {**base, 'item': {'type': 'agentMessage', 'phase': 'final_answer', 'text': output}}})
            rpc.events.put_nowait({'method': 'turn/completed', 'params': {**base, 'turn': {'id': turn, 'status': 'completed'}}})
        return result
    rpc.request = request
    result = asyncio.run(Workflow(store, m.run_id, runtime=runtime).run(resume=True))
    assert result['phase'] == 'done' and 900.04 <= result['elapsed_seconds'] < 1500
    ledger = store.get(m.run_id, 'ledger')
    assert ledger['calls'][:10] == before and len(ledger['calls']) == 11
    assert sum(method == 'turn/start' for method, _ in rpc.calls) == 1
    for n, data in frozen.items(): assert store.path(m.run_id, n + '.json').read_bytes() == data
    assert store.exists(m.run_id, 'roles/juiz/attempts/final-1')
    assert not store.exists(m.run_id, 'roles/juiz/attempts/final-2')
    assert runtime.config.limits.total_seconds == 900 and runtime.config.limits.max_calls == 16
    attempt = store.get(m.run_id, 'roles/juiz/attempts/final-1')
    limits = store.get(m.run_id, 'codex-turns/' + attempt['invocation_id'])['operational_limits']
    assert limits['total_limit_seconds'] == 1500 and limits['turn_limit_seconds'] == 300
    assert limits['base_total_seconds'] == 900 and 0 < limits['global_remaining_seconds'] < 600


@pytest.mark.parametrize('patch', [
    {'source': 'model_output'}, {'run_id': 'b' * 24}, {'config_hash': 'wrong'},
    {'base_total_seconds': 800}, {'total_seconds': 1501}, {'total_seconds': True},
    {'allowed_phases': ['auditor/contest']}, {'snapshot_record': 'validation/missing'}])
def test_invalid_extension_starts_no_new_turn(make_run, patch):
    store, m, runtime, rpc, tools, auth = setup_extension(make_run)
    store.put(m.run_id, GLOBAL_AUTHORIZATION, {**auth, **patch})
    with pytest.raises(PolicyError): asyncio.run(runtime.invoke('juiz', 'final', {}, tools, final=True))
    assert not any(method == 'turn/start' for method, _ in rpc.calls)


@pytest.mark.parametrize('tamper', ['elapsed_reset', 'calls_reset', 'phase_missing', 'phase_changed'])
def test_extension_cannot_reset_history_or_ignore_pending_work(make_run, tamper):
    store, m, runtime, rpc, tools, auth = setup_extension(make_run)
    if tamper == 'elapsed_reset':
        st = store.get(m.run_id, 'state'); st['elapsed_seconds'] = 0; store.put(m.run_id, 'state', st)
    elif tamper == 'calls_reset':
        ledger = store.get(m.run_id, 'ledger'); ledger['calls'] = []; store.put(m.run_id, 'ledger', ledger)
    elif tamper == 'phase_missing': store.path(m.run_id, 'roles/juiz/phases/review.json').unlink()
    else:
        value = store.get(m.run_id, 'roles/juiz/phases/review'); value['output']['summary'] = 'changed'
        store.put(m.run_id, 'roles/juiz/phases/review', value)
    with pytest.raises(PolicyError): total_seconds(store, m.run_id, runtime.config)


def test_extension_forbids_new_inference_for_other_phases(make_run):
    store, m, runtime, rpc, tools, auth = setup_extension(make_run)
    with pytest.raises(PolicyError, match='somente juiz/final'):
        asyncio.run(runtime.invoke('auditor', 'contest', {}, tools))
    assert not any(method == 'turn/start' for method, _ in rpc.calls)


def test_extension_never_renews_expired_financial_facts(make_run):
    store, m, runtime, rpc, tools, auth = setup_extension(make_run)
    facts = proof(); facts['checked_at'] = (datetime.now(timezone.utc) - timedelta(minutes=31)).isoformat()
    store.put(m.run_id, 'financial-confirmation', facts)
    with pytest.raises(RuntimePaused, match='financeira expirada'):
        asyncio.run(runtime.invoke('juiz', 'final', {}, tools, final=True))
    assert store.get(m.run_id, 'financial-confirmation') == facts
    assert not any(method == 'turn/start' for method, _ in rpc.calls)


def test_extension_does_not_open_an_extra_output_correction_slot(make_run):
    store, m, runtime, rpc, tools, auth = setup_extension(make_run)
    store.put(m.run_id, 'roles/juiz/attempts/final-1', {'invocation_id': 'e' * 24})
    store.put(m.run_id, 'roles/juiz/attempts/final-1-rejected', {'feedback': 'MOCK rejected'})
    with pytest.raises(PolicyError, match='esgotadas'):
        asyncio.run(Workflow(store, m.run_id, runtime=runtime).invoke('juiz', 'final', final=True))
    assert not any(method == 'turn/start' for method, _ in rpc.calls)
    assert not store.exists(m.run_id, 'roles/juiz/attempts/final-2')


def test_extended_global_ceiling_and_call_ceiling_still_apply(make_run):
    for ceiling in ('time', 'calls'):
        store, m, runtime, rpc, tools, auth = setup_extension(make_run)
        if ceiling == 'time':
            state = store.get(m.run_id, 'state'); state['elapsed_seconds'] = 1500
            store.put(m.run_id, 'state', state)
        else:
            ledger = store.get(m.run_id, 'ledger')
            ledger['calls'] += [{'id': str(i), 'role': 'juiz', 'status': 'error'} for i in range(10, 16)]
            store.put(m.run_id, 'ledger', ledger)
        with pytest.raises(BudgetExceeded):
            asyncio.run(runtime.invoke('juiz', 'final', {}, tools, final=True))
        assert not any(method == 'turn/start' for method, _ in rpc.calls)
