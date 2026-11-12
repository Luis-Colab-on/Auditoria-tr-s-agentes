"""Offline checks of permanent policy, actual timestamps and denied RPCs."""
import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest

from audit3.agents import RuntimePaused
from audit3.cli import main
from audit3.codex_policy import financial_policy, financial_remaining
from audit3.codex_rpc import StdioRPC
from audit3.workflow import Workflow
from helpers import MockRuntime


def test_cli_preserves_actual_operator_time_instead_of_registration_time(make_run, capsys):
    store, manifest = make_run()
    checked = (datetime.now(timezone.utc) - timedelta(minutes=7)).astimezone(timezone(timedelta(hours=-3))).isoformat()
    args = ['--store', str(store.root), 'financial-confirm', manifest.run_id,
        '--account-fingerprint', 'synthetic-identity', '--auto-recharge', 'disabled', '--extra-credits', 'none']
    with pytest.raises(SystemExit) as absent:
        main(args)
    assert absent.value.code == 2
    assert not store.exists(manifest.run_id, 'financial-confirmation')
    assert main([*args, '--checked-at', checked]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output['checked_at'] == checked and 0 < output['remaining_valid_seconds'] < 1500
    saved = store.get(manifest.run_id, 'financial-confirmation')
    assert saved['checked_at'] == checked
    assert main([*args, '--checked-at', (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()]) == 2
    assert store.get(manifest.run_id, 'financial-confirmation') == saved


@pytest.mark.parametrize('checked', [None, '[HH:MM]', '', '2026-11-11T09:00:00',
    (datetime.now(timezone.utc) + timedelta(minutes=2)).isoformat(),
    (datetime.now(timezone.utc) - timedelta(minutes=31)).isoformat()])
def test_absent_invalid_naive_future_and_expired_times_block(checked):
    with pytest.raises(RuntimePaused):
        financial_remaining(checked)


@pytest.mark.parametrize('method', ['account/login/start', 'account/logout',
    'account/rateLimitResetCredit/consume', 'account/sendAddCreditsNudgeEmail',
    'billing/credits/purchase', 'config/value/write', 'process/spawn', 'unknown/paidFallback'])
@pytest.mark.parametrize('direct', [False, True])
def test_unapproved_rpc_cannot_reach_the_subprocess(tmp_path, method, direct):
    rpc = StdioRPC('unused', tmp_path, tmp_path)
    async def attempt():
        if direct:
            await rpc.send({'id': 1, 'method': method, 'params': {}})
        else:
            await rpc.request(method, {})
    with pytest.raises(RuntimePaused, match='RPC fora do escopo'):
        asyncio.run(attempt())
    assert rpc.pending == {} and rpc.proc is None


def test_workflow_persists_permanent_rule_and_sends_it_on_every_phase(make_run, monkeypatch):
    monkeypatch.setattr('audit3.executor.shutil.which', lambda _: None)
    store, manifest = make_run()
    runtime = MockRuntime()
    asyncio.run(Workflow(store, manifest.run_id, runtime=runtime).run())
    saved = store.get(manifest.run_id, 'financial-policy')
    assert saved == {'permanent': True, 'rule': financial_policy()}
    assert all(call['payload']['financial_restriction'] == financial_policy() for call in runtime.calls)
    assert {call['role'] for call in runtime.calls} == {'auditor', 'defensor', 'juiz'}
    count = len(runtime.calls)
    asyncio.run(Workflow(store, manifest.run_id, runtime=runtime).run(resume=True))
    assert len(runtime.calls) == count and store.get(manifest.run_id, 'financial-policy') == saved
