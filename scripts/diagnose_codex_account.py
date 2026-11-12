#!/usr/bin/env python3
"""Read official account metadata in the auditor home; never authorize generation."""
import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from audit3.agents import RuntimePaused
from audit3.codex_policy import account_identity, check_effective_config, executable, verify_client
from audit3.codex_rpc import StdioRPC


class AccountRPC(StdioRPC):
    async def request(self, method, params):
        if method not in {'initialize', 'config/read', 'account/read'}:
            raise RuntimePaused('Diagnóstico restrito a configuração e conta')
        return await super().request(method, params)


def account_fields(response):
    if not isinstance(response, dict):
        raise ValueError('invalid_account_response')
    account = response.get('account')
    if account is None:
        return {'authentication': None, 'planType': None, 'query_error': None}
    if not isinstance(account, dict) or not isinstance(account.get('type'), str):
        raise ValueError('invalid_account_response')
    # Only protocol labels can be displayed, including unrecognized plan labels.
    # Other account fields, exception messages and raw frames never leave memory.
    for value in (account['type'], account.get('planType')):
        if value is not None and (not isinstance(value, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}', value)):
            raise ValueError('invalid_account_response')
    return {'authentication': account['type'], 'planType': account.get('planType'), 'query_error': None}


async def diagnose_account(root, check_policy=False):
    rpc = None
    stage = 'client_compatibility'
    result = {'authentication': None, 'planType': None, 'query_error': None}
    try:
        home = root.absolute() / 'codex-home'
        binary = executable()
        verify_client(binary, home)
        rpc = AccountRPC(binary, home, home / 'empty')
        stage = 'initialize'
        await rpc.start()
        stage = 'config/read'
        check_effective_config((await rpc.request(stage, {'includeLayers': False}))['config'], home)
        stage = 'account/read'
        response = await rpc.request(stage, {'refreshToken': False})
        stage = 'interpretation'
        result = account_fields(response)
        if check_policy:
            stage = 'account_policy'
            account_identity(response.get('account'))  # Discard the private identity hash.
    except Exception as exc:
        error = {'stage': stage, 'type': type(exc).__name__}
        # The existing transport exposes only the RPC code. Never echo arbitrary
        # server/OS exception messages, even when they contain credentials or PII.
        code = re.fullmatch(r'App Server recusou RPC; código (-?\d+)', str(exc))
        if code:
            error['code'] = int(code[1])
        result['query_error'] = error
    finally:
        if rpc:
            try:
                await rpc.close()
            except Exception as exc:
                result['query_error'] = {'stage': 'close', 'type': type(exc).__name__}
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--store', type=Path, default=Path('.audit3'))
    parser.add_argument('--check-policy', action='store_true', help='também verificar conta/plano; sem verificar finanças ou gerar texto')
    args = parser.parse_args(argv)
    result = asyncio.run(diagnose_account(args.store, args.check_policy))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    # Success here means metadata was read, never that a plan or finances passed.
    return 2 if result['query_error'] is not None else 0


if __name__ == '__main__':
    raise SystemExit(main())
