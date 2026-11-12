#!/usr/bin/env python3
"""Official local protocol check. Creates threads, NEVER starts a model turn."""
import asyncio
import json
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from audit3.codex_rpc import CLI_VERSION, StdioRPC
from audit3.codex_policy import setup_home, executable, verify_client, check_effective_config, select_effort
from audit3.codex_runtime import tool_specs


async def check():
    with tempfile.TemporaryDirectory(prefix='audit3-contract-') as directory:
        home = setup_home(Path(directory))
        binary = executable()
        print('contract: checking CLI', file=sys.stderr, flush=True)
        verify_client(binary, home)
        print('contract: CLI confirmed', file=sys.stderr, flush=True)
        rpc = StdioRPC(binary, home, home / 'empty')
        try:
            print('contract: initializing stdio', file=sys.stderr, flush=True)
            await rpc.start()
            request = rpc.request
            async def traced(method, params):
                print('contract request: ' + method, file=sys.stderr, flush=True)
                result = await request(method, params)
                print('contract confirmed: ' + method, file=sys.stderr, flush=True)
                return result
            rpc.request = traced
            check_effective_config((await rpc.request('config/read', {'includeLayers': False}))['config'], home)
            account = (await rpc.request('account/read', {'refreshToken': False})).get('account')
            if account is not None:
                raise RuntimeError('Fresh isolated home unexpectedly authenticated')
            effort = select_effort((await rpc.request('model/list', {'limit': 100}))['data'])
            params = {'model': 'gpt-6-astra', 'modelProvider': 'openai', 'cwd': str(home / 'empty'),
                'permissions': 'audit3', 'approvalPolicy': 'never', 'serviceTier': 'default',
                'baseInstructions': 'Protocol-only synthetic check. No turns authorized.',
                'developerInstructions': 'No turns authorized.', 'config': {'model_reasoning_effort': effort},
                'runtimeWorkspaceRoots': []}
            sessions = []
            def validate(result):
                assert result['model'] == 'gpt-6-astra' and result['modelProvider'] == 'openai'
                assert result['reasoningEffort'] == effort and result['serviceTier'] in {None, 'default'}
                assert result['activePermissionProfile']['id'] == 'audit3'
                assert result['approvalPolicy'] == 'never' and result['instructionSources'] == []
                assert result['cwd'] == str(home / 'empty')
            for _ in range(3):
                response = await rpc.request('thread/start', {**params, 'dynamicTools': tool_specs(),
                    'allowProviderModelFallback': False, 'environments': [], 'experimentalRawEvents': False})
                validate(response)
                sessions.append(response['thread']['id'])
            assert len(set(sessions)) == 3
            return {'result': 'passed', 'client_version': CLI_VERSION, 'model': 'gpt-6-astra', 'effort': effort,
                'speed': 'Standard (default)', 'private_account': None, 'distinct_threads_without_turns': len(sessions),
                'explicit_thread_resume': 'not validated; previous no-turn resume attempt rejected; mock contract only', 'dynamic_tools_per_thread': 5, 'effective_permission_profile': 'audit3',
                'inherited_instruction_sources': [], 'model_turns_started': 0, 'real_agents_validated': False,
                'scope': 'official local protocol only; no financial evidence or model inference'}
        finally:
            await rpc.close()


if __name__ == '__main__':
    try:
        result = asyncio.run(asyncio.wait_for(check(), timeout=45))
    except Exception as exc:
        print(json.dumps({'result': 'blocked_or_failed', 'error_type': type(exc).__name__, 'model_turns_started': 0}))
        raise SystemExit(2)
    print(json.dumps(result, ensure_ascii=False, indent=2))
