"""Metadata-only doubles: no inference, network or financial confirmation."""
import asyncio
import importlib.util
import json
from pathlib import Path

import pytest

from audit3.agents import RuntimePaused
from audit3.codex_policy import account_identity

spec = importlib.util.spec_from_file_location('account_diagnostic', Path(__file__).parents[1] / 'scripts/diagnose_codex_account.py')
diagnostic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostic)


@pytest.mark.parametrize('plan', ['pro', 'prolite', 'promax', 'plus', 'unknown', 'future_plan', None])
def test_reports_received_plan_without_accepting_or_normalizing_it(plan):
    account = {'type': 'chatgpt', 'email': 'PRIVATE-EMAIL@example.invalid', 'access_token': 'PRIVATE-TOKEN'}
    if plan is not None:
        account['planType'] = plan
    result = diagnostic.account_fields({'account': account, 'workspaceRouting': {'chatgptAccountId': 'PRIVATE-ID'}})
    assert result == {'authentication': 'chatgpt', 'planType': plan, 'query_error': None}
    assert 'PRIVATE' not in json.dumps(result)
    if plan not in ('pro', 'prolite', 'promax'):
        with pytest.raises(RuntimePaused, match='^Plano Pro não confirmado oficialmente$'):
            account_identity(account)


@pytest.mark.parametrize('response', [{'account': None}, {'requiresOpenaiAuth': True}])
def test_absent_account_is_not_reported_as_query_failure(response):
    assert diagnostic.account_fields(response) == {'authentication': None, 'planType': None, 'query_error': None}


@pytest.mark.parametrize('response', [None, [], {'account': 'PRIVATE'}, {'account': {}},
    {'account': {'type': 'chatgpt', 'planType': {'token': 'PRIVATE'}}},
    {'account': {'type': 'chatgpt', 'planType': 'PRIVATE@example.invalid'}}])
def test_malformed_response_is_an_interpretation_error(response):
    with pytest.raises(ValueError, match='^invalid_account_response$'):
        diagnostic.account_fields(response)


@pytest.mark.parametrize('reply,check_policy,expected_error', [
    ({'account': {'type': 'chatgpt', 'planType': 'promax'}}, False, None),
    ({'account': None}, False, None),
    ({'account': []}, False, {'stage': 'interpretation', 'type': 'ValueError'}),
    (RuntimePaused('App Server recusou RPC; código -32603'), False, {'stage': 'account/read', 'type': 'RuntimePaused', 'code': -32603}),
    (OSError('PRIVATE-SECRET PRIVATE@example.invalid'), False, {'stage': 'account/read', 'type': 'OSError'}),
    ({'account': {'type': 'chatgpt', 'planType': 'prolite', 'email': 'PRIVATE@example.invalid'}}, True, None),
    ({'account': {'type': 'chatgpt', 'planType': 'unknown', 'email': 'PRIVATE@example.invalid'}}, True, {'stage': 'account_policy', 'type': 'RuntimePaused'}),
    ({'account': {'type': 'chatgpt', 'planType': 'prolite'}}, True, {'stage': 'account_policy', 'type': 'RuntimePaused'}),
])
def test_queries_only_metadata_and_closes_without_exposing_exceptions(monkeypatch, tmp_path, reply, check_policy, expected_error):
    calls = []

    class FakeRPC:
        def __init__(self, binary, home, cwd):
            assert home == tmp_path / 'codex-home' and cwd == home / 'empty'
        async def start(self):
            calls.append('initialize')
        async def request(self, method, params):
            calls.append(method)
            if method == 'config/read':
                return {'config': {}}
            assert method == 'account/read' and params == {'refreshToken': False}
            if isinstance(reply, Exception):
                raise reply
            return reply
        async def close(self):
            calls.append('close')

    monkeypatch.setattr(diagnostic, 'executable', lambda: 'mock-codex')
    monkeypatch.setattr(diagnostic, 'verify_client', lambda binary, home: calls.append('verify_client'))
    monkeypatch.setattr(diagnostic, 'check_effective_config', lambda config, home: calls.append('check_effective_config'))
    monkeypatch.setattr(diagnostic, 'AccountRPC', FakeRPC)
    result = asyncio.run(diagnostic.diagnose_account(tmp_path, check_policy))
    assert result['query_error'] == expected_error
    assert set(result) == {'authentication', 'planType', 'query_error'}
    assert 'PRIVATE' not in json.dumps(result)
    assert calls == ['verify_client', 'initialize', 'config/read', 'check_effective_config', 'account/read', 'close']


@pytest.mark.parametrize('method', ['thread/start', 'turn/start', 'account/login/start', 'account/rateLimitResetCredit/consume'])
def test_live_diagnostic_transport_refuses_generation_and_account_mutations(tmp_path, method):
    rpc = diagnostic.AccountRPC('unused', tmp_path, tmp_path)
    with pytest.raises(RuntimePaused, match='Diagnóstico restrito'):
        asyncio.run(rpc.request(method, {}))
