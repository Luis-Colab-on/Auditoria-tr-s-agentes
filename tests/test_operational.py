"""Offline controller regressions; no Docker, service or real generation."""
import asyncio
from types import SimpleNamespace
import pytest
from audit3.agents import BudgetExceeded, RuntimePaused
from audit3.operational import TIMEOUT_AUTHORIZATION, turn_timeout
from audit3.report import receipt_observation, build_report
from audit3.security import PolicyError, now
from audit3.tools import SourceTools, ToolContext
from audit3.workflow import Workflow
from test_codex_runtime import rig


def authorize(store, manifest):
    inv = 'd' * 24
    store.put(manifest.run_id, 'codex-turns/' + inv, {
        'status': 'ambiguous', 'error_type': 'TimeoutError', 'role': 'auditor', 'phase': 'initial-0000',
        'thread_id': 'MOCK-old-thread', 'turn_id': 'MOCK-old-turn',
        'timeout': {'origin': 'turn_deadline', 'turn_limit_seconds': 120}})
    diagnosis = 'validation/timeout-diagnosis'
    store.put(manifest.run_id, diagnosis, {'run_id': manifest.run_id, 'timeout_invocation_id': inv,
        'normal_activity_until_deadline': True})
    authorization = {'source': 'explicit_operator_authorization', 'run_id': manifest.run_id,
        'config_hash': manifest.config_hash, 'base_call_timeout': 120, 'call_timeout': 300,
        'timeout_invocation_id': inv, 'diagnosis_record': diagnosis}
    store.put(manifest.run_id, TIMEOUT_AUTHORIZATION, authorization)
    return authorization, inv


def test_timeout_amendment_leaves_config_and_history_frozen(make_run):
    store, m, runtime, rpc, tools = rig(make_run)
    config_bytes = store.path(m.run_id, 'config.json').read_bytes()
    authorization, inv = authorize(store, m)
    old_bytes = store.path(m.run_id, 'codex-turns/' + inv + '.json').read_bytes()
    result = asyncio.run(runtime.invoke('auditor', 'initial-0000', {}, tools))
    saved = store.get(m.run_id, 'codex-turns/' + tools.context.invocation_id)
    assert saved['operational_limits']['turn_limit_seconds'] == 300
    assert 299 < saved['operational_limits']['effective_turn_seconds'] <= 300
    assert runtime.config.limits.call_timeout == 120
    assert store.path(m.run_id, 'config.json').read_bytes() == config_bytes
    assert store.path(m.run_id, 'codex-turns/' + inv + '.json').read_bytes() == old_bytes


@pytest.mark.parametrize('patch', [
    {'call_timeout': 301}, {'call_timeout': True}, {'call_timeout': 120},
    {'config_hash': 'wrong'}, {'run_id': 'b' * 24}, {'source': 'model_output'},
    {'base_call_timeout': 60}, {'diagnosis_record': 'roles/auditor/guess'},
    {'timeout_invocation_id': 'e' * 24}])
def test_invalid_amendments_never_start_inference(make_run, patch):
    store, m, runtime, rpc, tools = rig(make_run)
    authorization, _ = authorize(store, m)
    store.put(m.run_id, TIMEOUT_AUTHORIZATION, {**authorization, **patch})
    with pytest.raises(PolicyError):
        asyncio.run(runtime.invoke('auditor', 'initial-0000', {}, tools))
    assert rpc.calls == [] and store.get(m.run_id, 'ledger')['calls'] == []


def test_non_deadline_failure_does_not_justify_longer_turn(make_run):
    store, m, runtime, rpc, tools = rig(make_run)
    _, inv = authorize(store, m)
    prior = store.get(m.run_id, 'codex-turns/' + inv)
    prior['timeout']['origin'] = 'rpc_timeout'
    store.put(m.run_id, 'codex-turns/' + inv, prior)
    with pytest.raises(PolicyError, match='execução normal'):
        turn_timeout(store, m.run_id, runtime.config)


def test_amended_timeout_still_expires_at_global_deadline(make_run, monkeypatch):
    store, m, runtime, rpc, tools = rig(make_run)
    authorize(store, m)
    rpc.mode = 'timeout'
    async def exercise():
        loop = asyncio.get_running_loop()
        clock = [loop.time()]
        monkeypatch.setattr(loop, 'time', lambda: clock[0])
        original_get = rpc.events.get
        async def expire_after_dispatch():
            clock[0] += .1
            return await original_get()
        monkeypatch.setattr(rpc.events, 'get', expire_after_dispatch)
        runtime.global_deadline = loop.time() + 0.05
        with pytest.raises(RuntimePaused, match='global_deadline'):
            await runtime.invoke('auditor', 'initial-0000', {}, tools)
    asyncio.run(exercise())
    saved = store.get(m.run_id, 'codex-turns/' + tools.context.invocation_id)
    assert saved['timeout']['origin'] == 'global_deadline'
    assert saved['timeout']['turn_limit_seconds'] == 300
    assert rpc.closed and any(method == 'turn/interrupt' for method, _ in rpc.calls)


def test_amended_timeout_still_expires_at_financial_deadline(make_run, monkeypatch):
    store, m, runtime, rpc, tools = rig(make_run)
    authorize(store, m)
    rpc.mode = 'timeout'
    # This mock shortens the deadline. It never refreshes or extends the proof.
    monkeypatch.setattr('audit3.codex_runtime.financial_remaining', lambda _: 0.05)
    before = store.get(m.run_id, 'financial-confirmation')
    with pytest.raises(RuntimePaused, match='financeira expirou'):
        asyncio.run(runtime.invoke('auditor', 'initial-0000', {}, tools))
    saved = store.get(m.run_id, 'codex-turns/' + tools.context.invocation_id)
    assert saved['timeout']['origin'] == 'financial_deadline'
    assert store.get(m.run_id, 'financial-confirmation') == before


def test_exhausted_cumulative_time_starts_no_thread(make_run):
    store, m, runtime, rpc, tools = rig(make_run)
    authorize(store, m)
    state = store.get(m.run_id, 'state')
    store.put(m.run_id, 'state', {**state, 'elapsed_seconds': runtime.config.limits.total_seconds})
    with pytest.raises(BudgetExceeded):
        asyncio.run(runtime.invoke('auditor', 'initial-0000', {}, tools))
    assert not rpc.calls and store.get(m.run_id, 'ledger')['calls'] == []


def test_amendment_uses_only_existing_recovery_slot(make_run):
    store, m, runtime, rpc, tools = rig(make_run)
    _, old = authorize(store, m)
    store.put(m.run_id, 'baseline', {'ids': []})
    store.put(m.run_id, 'roles/auditor/attempts/initial-0000-0', {'invocation_id': old})
    store.put(m.run_id, 'roles/auditor/attempts/initial-0000-0-interrupted', {
        'source': 'official_app_server_thread_read', 'status': 'interrupted', 'invocation_id': old,
        'thread_id': 'MOCK-old-thread', 'turn_id': 'MOCK-old-turn'})
    ledger = {'calls': [{'id': 'old', 'invocation_id': old, 'role': 'auditor', 'status': 'error',
                        'input_tokens': None, 'output_tokens': None}], 'tokens': None,
              'known_cost_usd': None, 'unknown_cost_calls': 1}
    store.put(m.run_id, 'ledger', ledger)
    from helpers import initial_investigation
    rpc.output = initial_investigation(store, m, 'auditor').model_dump_json()
    workflow = Workflow(store, m.run_id, runtime=runtime)
    asyncio.run(workflow.invoke('auditor', 'initial-0000'))
    count = len(store.get(m.run_id, 'ledger')['calls'])
    asyncio.run(workflow.invoke('auditor', 'initial-0000'))
    assert count == len(store.get(m.run_id, 'ledger')['calls']) == 2
    assert store.get(m.run_id, 'ledger')['calls'][0] == ledger['calls'][0]
    assert store.exists(m.run_id, 'roles/auditor/attempts/initial-0000-1')
    assert not store.exists(m.run_id, 'roles/auditor/attempts/initial-0000-2')
    assert workflow.config.limits.invalid_output_retries == 1


def store_receipt(store, m, **patch):
    # MOCK of the stored receipt contract, never a Docker execution.
    from audit3.schemas import EvidenceReceipt
    from audit3.security import digest
    receipt = EvidenceReceipt(id='b' * 24, run_id=m.run_id, owner='auditor', phase='initial-0000',
        source_id=m.source_id, profile_hash=m.profile_hash, fingerprint='mock', command=['php', '/test/repro.php'],
        image_ids={}, versions={}, started_at=now(), finished_at=now(), status='failed', exit_code=1,
        timeout=False, stdout='', stderr='', stdout_sha256=digest(b''), stderr_sha256=digest(b''),
        output_truncated=False, script_sha256=None, purpose='MOCK', limitations=[], execution='compose')
    data = receipt.model_dump(mode='json'); data.update(patch)
    store.put(m.run_id, 'receipts/' + receipt.id, data)
    return receipt.id


def test_intermediate_receipt_exists_without_cross_role_publication(make_run):
    store, m = make_run()
    eid = store_receipt(store, m)
    observation = receipt_observation(store, m.run_id)
    assert observation['model_reproduction_status'] == 'executed_hidden_by_barrier'
    assert observation['qualifying_model_reproduction_ids'] == [eid]
    assert build_report(store, m.run_id)['receipts'] == []
    tools = SourceTools(store, m, SimpleNamespace(), None, ToolContext(m.run_id, 'defensor', 'initial-0000', 'a' * 24))
    with pytest.raises(PolicyError, match='privada antes da barreira'):
        tools.read_evidence(eid)
    store.put(m.run_id, 'barrier', {'published_at': now()})
    assert receipt_observation(store, m.run_id)['model_reproduction_status'] == 'executed_published'


@pytest.mark.parametrize('patch', [
    {'execution': 'mock'}, {'status': 'blocked', 'execution': 'not_executed'},
    {'timeout': True}, {'output_truncated': True}, {'source_id': 'wrong'}, {'profile_hash': 'wrong'}])
def test_bad_receipts_never_meet_reproduction_criterion(make_run, patch):
    store, m = make_run()
    store_receipt(store, m, **patch)
    assert not receipt_observation(store, m.run_id)['qualifying_model_reproduction_ids']


def test_missing_receipt_with_running_attempt_is_unknown(make_run):
    store, m = make_run()
    assert receipt_observation(store, m.run_id)['model_reproduction_status'] == 'not_executed'
    store.put(m.run_id, 'execution-attempts/' + 'c' * 24, {'status': 'ambiguous'})
    assert receipt_observation(store, m.run_id)['model_reproduction_status'] == 'unknown_pending_receipt'
