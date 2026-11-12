"""Protocol and failure-injection MOCKS. These never perform model inference."""
import asyncio
import copy
import json
import tomllib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from pathlib import Path
import pytest
from audit3.agents import AmbiguousTurn, RuntimePaused, SDKRuntime
from audit3.codex_runtime import CodexRuntime, tool_specs, output_schema
from audit3.codex_rpc import BACKEND, StdioRPC, clean_environment
from audit3.codex_policy import (account_identity, check_effective_config, financial_check,
    financial_policy, private_config, select_effort, setup_home)
from audit3.config import Config
from audit3.schemas import Judgment, Opinion, TestRequest as Request
from audit3.security import PolicyError, now, object_hash
from audit3.tools import SourceTools, ToolContext
from audit3.workflow import Workflow
from audit3.report import build_report, export_zip

ACCOUNT = {'type': 'chatgpt', 'planType': 'pro', 'email': 'synthetic@example.invalid'}
MODEL = {'model': 'gpt-6-astra', 'supportedReasoningEfforts': [{'reasoningEffort': 'max'}, {'reasoningEffort': 'xhigh'}]}
QUOTA = {'ordinaryUsageAllowed': True, 'rateLimits': {'credits': {'hasCredits': False, 'unlimited': False, 'balance': '0'}, 'primary': {'usedPercent': 10}}}


def proof():
    return {'source': 'operator_factual_confirmation', 'checked_at': now(), 'account_fingerprint': account_identity(ACCOUNT),
        'auto_recharge': 'disabled', 'extra_credits': 'none'}


class FakeRPC:
    """Mock official wire contract, explicitly not evidence of a real backend."""
    def __init__(self, home):
        self.home, self.events = home, asyncio.Queue()
        self.calls, self.responses, self.sessions = [], [], []
        self.quota, self.account = copy.deepcopy(QUOTA), copy.deepcopy(ACCOUNT)
        self.mode, self.turn = 'complete', 0
        self.config = tomllib.loads(private_config(home).decode())
        self.config.pop('tools')
        self.config['features'].pop('apps_mcp_path_override')
        self.closed = False

    async def request(self, method, params, *, dispatch=None):
        if dispatch is not None:
            dispatch.check()
            dispatch.write_attempted = dispatch.written = True
        self.calls.append((method, params))
        if method == 'config/read': return {'config': self.config}
        if method == 'account/read': return {'account': self.account}
        if method == 'model/list': return {'data': [MODEL], 'nextCursor': None}
        if method == 'account/rateLimits/read': return self.quota
        if method in {'thread/start', 'thread/resume'}:
            ident = params.get('threadId', 'thread-' + str(len(self.sessions)))
            self.sessions.append(ident)
            return {'thread': {'id': ident}, 'model': 'gpt-6-astra', 'modelProvider': 'openai',
                'reasoningEffort': 'max', 'serviceTier': 'default', 'instructionSources': [],
                'activePermissionProfile': {'id':'audit3'}, 'approvalPolicy':'never', 'cwd':str(self.home/'empty')}
        if method == 'turn/start':
            self.turn += 1
            tid = 'turn-' + str(self.turn)
            base = {'threadId': params['threadId'], 'turnId': tid}
            if self.mode == 'transport': self.events.put_nowait({'method': 'audit3/transportLost'})
            elif self.mode == 'quota':
                self.quota['ordinaryUsageAllowed']=False
                self.events.put_nowait({'method': 'account/rateLimits/updated', 'params': {**QUOTA, 'ordinaryUsageAllowed': False}})
            elif self.mode == 'native': self.events.put_nowait({'method': 'item/started', 'params': {**base, 'item': {'type': 'commandExecution'}}})
            elif self.mode == 'approval': self.events.put_nowait({'id': 'server-approval', 'method': 'item/commandExecution/requestApproval', 'params': base})
            elif self.mode == 'wrong_thread': self.events.put_nowait({'method': 'turn/completed', 'params': {**base, 'threadId': 'other', 'turn': {'id': tid, 'status': 'completed'}}})
            elif self.mode != 'timeout':
                output = getattr(self, 'output', None) or Opinion(summary='MOCK contract result', inspections=[], findings=[], positions=[], limitations=[]).model_dump_json()
                self.events.put_nowait({'method': 'item/completed', 'params': {**base, 'item': {'type': 'agentMessage', 'phase': 'final_answer', 'text': output}}})
                self.events.put_nowait({'method': 'turn/completed', 'params': {**base, 'turn': {'id': tid, 'status': 'completed'}}})
            return {'turn': {'id': tid, 'status': 'inProgress'}}
        if method == 'turn/interrupt': return {}
        raise AssertionError(method)

    async def respond(self, ident, data): self.responses.append((ident, data))
    async def send(self, data): self.responses.append(data)
    async def close(self): self.closed = True


def rig(make_run):
    store, m = make_run()
    runtime = CodexRuntime(store, m.run_id, Config())
    rpc = FakeRPC(runtime.home)
    runtime.rpc = rpc
    store.put(m.run_id, 'financial-confirmation', proof())
    tools = SourceTools(store, m, Config(), SimpleNamespace(), ToolContext(m.run_id, 'auditor', 'initial-0000', 'a'*24))
    return store, m, runtime, rpc, tools


@pytest.mark.parametrize('account', [None, {'type':'apiKey'}, {'type':'amazonBedrock'}, {'type':'gcp'}, {**ACCOUNT, 'planType':'plus'}])
def test_auth_rejected_without_fallback(account):
    with pytest.raises(RuntimePaused): account_identity(account)
    with pytest.raises(PolicyError, match='removido'): SDKRuntime(None, None, None)


@pytest.mark.parametrize('plan', json.loads((Path(__file__).parent/'contracts/GetAccountResponse.json').read_text())['definitions']['PlanType']['enum'])
def test_only_explicit_personal_pro_tiers_pass_account_policy(plan):
    account = {**ACCOUNT, 'planType': plan}
    if plan in ('pro', 'prolite', 'promax'):
        identity = account_identity(account)
        assert identity == object_hash({k: account.get(k) for k in ('type', 'email', 'planType', 'workspaceName')})
        assert account['planType'] == plan
    else:
        with pytest.raises(RuntimePaused, match='Plano Pro não confirmado oficialmente'):
            account_identity(account)


@pytest.mark.parametrize('plan', [None, '', 'Pro', 'pro_trial', 'prolite_future', 'future_plan', [], {}])
def test_absent_unknown_or_malformed_plan_is_never_confirmation(plan):
    with pytest.raises(RuntimePaused, match='Plano Pro não confirmado oficialmente'):
        account_identity({**ACCOUNT, 'planType': plan})


@pytest.mark.parametrize('plan', ['pro', 'prolite', 'promax'])
def test_metadata_preflight_preserves_official_plan_without_starting_turns(make_run, plan):
    store, m, runtime, rpc, tools = rig(make_run)
    rpc.account['planType'] = plan
    store.put(m.run_id, 'financial-confirmation', {**proof(), 'account_fingerprint': account_identity(rpc.account)})
    effective = asyncio.run(runtime.preflight())
    assert effective['plan'] == plan == store.get(m.run_id, 'runtime')['plan']
    events = [store.get(m.run_id, 'events/' + name) for name in store.names(m.run_id, 'events')]
    assert next(e['data']['plan'] for e in events if e['kind'] == 'codex_preflight') == plan
    assert not any(method in {'thread/start', 'turn/start'} for method, _ in rpc.calls)
    assert store.get(m.run_id, 'ledger')['calls'] == []


@pytest.mark.parametrize('plan', ['pro', 'prolite', 'promax'])
@pytest.mark.parametrize('failure', ['missing_proof', 'recharge_enabled', 'extra_credits', 'quota_unknown', 'official_credits'])
def test_pro_tiers_keep_financial_blocks_before_threads_or_turns(make_run, plan, failure):
    store, m, runtime, rpc, tools = rig(make_run)
    rpc.account['planType'] = plan
    confirmation = {**proof(), 'account_fingerprint': account_identity(rpc.account)}
    if failure == 'recharge_enabled': confirmation['auto_recharge'] = 'enabled'
    if failure == 'extra_credits': confirmation['extra_credits'] = 'present'
    store.put(m.run_id, 'financial-confirmation', confirmation)
    if failure == 'missing_proof': store.path(m.run_id, 'financial-confirmation.json').unlink()
    if failure == 'quota_unknown': rpc.quota['ordinaryUsageAllowed'] = None
    if failure == 'official_credits': rpc.quota['rateLimits']['credits']['hasCredits'] = True
    with pytest.raises(RuntimePaused): asyncio.run(runtime.preflight())
    assert not any(method in {'thread/start', 'turn/start'} for method, _ in rpc.calls)
    assert store.get(m.run_id, 'ledger')['calls'] == []


@pytest.mark.parametrize('plan', ['pro', 'prolite', 'promax'])
def test_doctor_preserves_received_plan_without_starting_turns(monkeypatch, tmp_path, plan):
    from audit3.cli import probe_codex
    instances = []
    class ProbeRPC(FakeRPC):
        def __init__(self, binary, home, cwd):
            super().__init__(home)
            self.account['planType'] = plan
            instances.append(self)
        async def start(self): return self
    monkeypatch.setattr('audit3.codex_rpc.StdioRPC', ProbeRPC)
    monkeypatch.setattr('audit3.codex_policy.executable', lambda: 'mock-codex')
    monkeypatch.setattr('audit3.codex_policy.verify_client', lambda binary, home: None)
    result = asyncio.run(probe_codex(tmp_path))
    assert result['plan'] == plan and result['generation_calls'] == 0
    assert instances[0].closed
    assert [method for method, _ in instances[0].calls] == ['config/read', 'account/read', 'model/list', 'account/rateLimits/read']


def test_environment_drops_keys_proxies_and_injection(monkeypatch, tmp_path):
    for key in ['OPENAI_API_KEY', 'CODEX_API_KEY', 'ANTHROPIC_API_KEY', 'OPENAI_BASE_URL', 'HTTPS_PROXY', 'NODE_OPTIONS', 'PYTHONPATH', 'AWS_PROFILE', 'CODEX_HOME', 'CODEX_ACCESS_TOKEN']:
        monkeypatch.setenv(key, 'SYNTHETIC-SECRET')
    env = clean_environment(tmp_path)
    assert set(env) == {'PATH','HOME','CODEX_HOME','LANG','LC_ALL'}
    assert 'SYNTHETIC-SECRET' not in str(env)


@pytest.mark.parametrize('patch', [None, {'source':'auditor_boolean'}, {'auto_recharge':'enabled'}, {'extra_credits':'present'}, {'account_fingerprint':'other'}, {'checked_at':(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat()}])
def test_missing_or_wrong_financial_facts_block(patch):
    p = None if patch is None else {**proof(), **patch}
    with pytest.raises(RuntimePaused): financial_check(p, account_identity(ACCOUNT), QUOTA)


@pytest.mark.parametrize('patch', [{'ordinaryUsageAllowed':None}, {'ordinaryUsageAllowed':False}, {'rateLimits':{}}, {'rateLimits':{'credits':{'hasCredits':True,'unlimited':False,'balance':'5'}}}, {'rateLimits':{'credits':{'hasCredits':False,'unlimited':False,'balance':None}}}, {'rateLimits':{**QUOTA['rateLimits'],'primary':{'usedPercent':100}}}])
def test_quota_unknown_or_credits_present_block(patch):
    with pytest.raises(RuntimePaused): financial_check(proof(), account_identity(ACCOUNT), {**QUOTA, **patch})


def test_facts_and_quota_do_not_claim_atomic_financial_guard():
    assert financial_check(proof(), account_identity(ACCOUNT), QUOTA)['atomic_financial_guard'] is False
    assert select_effort([MODEL]) == 'max'
    assert select_effort([{**MODEL,'supportedReasoningEfforts':[{'reasoningEffort':'xhigh'}]}]) == 'xhigh'
    for models in [[], [{**MODEL, 'supportedReasoningEfforts':[{'reasoningEffort':'ultra'}]}]]:
        with pytest.raises(RuntimePaused): select_effort(models)


def test_conflicting_credit_views_and_malformed_quota_never_authorize():
    for extra_view in ('rateLimits', 'rateLimitsByLimitId'):
        quota = copy.deepcopy(QUOTA)
        quota['rateLimitsByLimitId'] = {'codex': copy.deepcopy(QUOTA['rateLimits'])}
        bucket = quota['rateLimits'] if extra_view == 'rateLimits' else quota['rateLimitsByLimitId']['codex']
        bucket['credits'] = {'hasCredits': True, 'unlimited': False, 'balance': '5'}
        with pytest.raises(RuntimePaused): financial_check(proof(), account_identity(ACCOUNT), quota)
    for patch in ({'rateLimitsByLimitId': ['invalid']}, {'rateLimits': {'primary': False}},
                  {'rateLimits': {**QUOTA['rateLimits'], 'primary': {'usedPercent': False}}}):
        with pytest.raises(RuntimePaused): financial_check(proof(), account_identity(ACCOUNT), {**QUOTA, **patch})


def test_financial_expiry_interrupts_active_turn_without_retry(make_run, monkeypatch):
    store, m, runtime, rpc, tools = rig(make_run)
    rpc.mode = 'timeout'
    # Only the local deadline is shortened; no actual account/model is called.
    monkeypatch.setattr('audit3.codex_runtime.financial_remaining', lambda checked: .02)
    async def exercise():
        loop = asyncio.get_running_loop()
        clock = [loop.time()]
        monkeypatch.setattr(loop, 'time', lambda: clock[0])
        original_get = rpc.events.get
        async def expire_after_dispatch():
            clock[0] += .03
            return await original_get()
        monkeypatch.setattr(rpc.events, 'get', expire_after_dispatch)
        with pytest.raises(RuntimePaused, match='expirou durante o turno'):
            await runtime.invoke('auditor', 'initial-0000', {}, tools)
    asyncio.run(exercise())
    assert sum(method == 'turn/start' for method, _ in rpc.calls) == 1
    assert sum(method == 'turn/interrupt' for method, _ in rpc.calls) == 1
    assert rpc.closed
    assert store.get(m.run_id, 'codex-turns/' + tools.context.invocation_id)['status'] == 'ambiguous'
    assert store.get(m.run_id, 'ledger')['calls'][0]['status'] == 'error'
    with pytest.raises(AmbiguousTurn):
        asyncio.run(runtime.invoke('auditor', 'initial-0000', {}, tools))
    assert sum(method == 'turn/start' for method, _ in rpc.calls) == 1


def test_expiry_during_session_setup_blocks_before_any_turn(make_run, monkeypatch):
    store, m, runtime, rpc, tools = rig(make_run)
    async def expired_session(role, effective):
        effective['financial']['checked_at'] = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        return 'mock-thread'
    monkeypatch.setattr(runtime, 'session', expired_session)
    with pytest.raises(RuntimePaused, match='expirada'):
        asyncio.run(runtime.invoke('auditor', 'initial-0000', {}, tools))
    assert not any(method == 'turn/start' for method, _ in rpc.calls)
    assert store.get(m.run_id, 'ledger')['calls'] == []


def test_financial_rule_is_present_in_new_and_resumed_role_instructions(make_run):
    store, m, runtime, rpc, tools = rig(make_run)
    async def exercise():
        effective = await runtime.preflight()
        for role in ('auditor', 'defensor', 'juiz'):
            await runtime.session(role, effective)
        runtime.loaded.clear()
        for role in ('auditor', 'defensor', 'juiz'):
            await runtime.session(role, effective)
    asyncio.run(exercise())
    calls = [(method, params) for method, params in rpc.calls if method in {'thread/start', 'thread/resume'}]
    assert len(calls) == 6
    for method, params in calls:
        assert financial_policy() in params['developerInstructions']
        assert 'NENHUM GASTO ADICIONAL ESTÁ AUTORIZADO' in params['baseInstructions']
        assert 'restrição financeira permanente' in params['baseInstructions']


def test_resume_with_expired_facts_stays_blocked_and_never_refreshes_time(make_run, monkeypatch):
    store, m, runtime, rpc, tools = rig(make_run)
    monkeypatch.setattr('audit3.executor.shutil.which', lambda _: None)
    rpc.quota['ordinaryUsageAllowed'] = None
    first = asyncio.run(Workflow(store, m.run_id, runtime=runtime).run())
    assert first['status'] == 'blocked'
    stale = {**proof(), 'checked_at': (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()}
    store.put(m.run_id, 'financial-confirmation', stale)
    resumed_rpc = FakeRPC(runtime.home)
    runtime.rpc = resumed_rpc
    second = asyncio.run(Workflow(store, m.run_id, runtime=runtime).run(resume=True))
    assert second['status'] == 'blocked' and any('expirada' in text for text in second['limitations'])
    assert store.get(m.run_id, 'financial-confirmation') == stale
    assert store.get(m.run_id, 'financial-policy')['permanent'] is True
    assert store.get(m.run_id, 'ledger')['calls'] == []
    assert not any(method in {'thread/start', 'turn/start'} for method, _ in resumed_rpc.calls)


@pytest.mark.parametrize('override', ['mcp_servers','model_providers','hooks','developer_instructions','instructions','sandbox_mode'])
def test_inherited_configuration_cannot_escape(override, tmp_path):
    cfg = FakeRPC(tmp_path).config
    cfg[override] = {'escape':True}
    with pytest.raises(RuntimePaused): check_effective_config(cfg,tmp_path)


def test_permissions_plugins_skills_and_symlinks_cannot_escape(tmp_path):
    for mutate in [lambda c:c['permissions']['audit3']['filesystem'].update({'/tmp':'read'}),
        lambda c:c['plugins'].update({'evil@local':{'enabled':True}}),
        lambda c:c['skills'].update({'config':[{'path':'/etc/evil','enabled':True}]}),
        lambda c:c['features'].update({'shell_tool':True})]:
        cfg=FakeRPC(tmp_path).config;mutate(cfg)
        with pytest.raises(RuntimePaused):check_effective_config(cfg,tmp_path)
    target=tmp_path/'target';target.mkdir();link=tmp_path/'link';link.symlink_to(target)
    with pytest.raises(RuntimePaused):setup_home(link)


def test_preflight_missing_proof_never_creates_thread_or_turn(make_run):
    store,m,r,rpc,tools=rig(make_run)
    store.path(m.run_id,'financial-confirmation.json').unlink()
    with pytest.raises(RuntimePaused):asyncio.run(r.invoke('auditor','initial-0000',{},tools))
    assert not any(k in {'thread/start','turn/start'} for k,_ in rpc.calls)
    assert store.get(m.run_id,'ledger')['calls']==[]


def test_three_real_session_contracts_are_distinct_mock(make_run):
    store,m,r,rpc,tools=rig(make_run)
    async def exercise():
        e=await r.preflight()
        ids=[await r.session(role,e) for role in ['auditor','defensor','juiz']]
        assert len(set(ids))==3
        for role in ['auditor','defensor','juiz']:assert await r.session(role,e) in ids
    asyncio.run(exercise())
    starts=[p for k,p in rpc.calls if k=='thread/start']
    assert len(starts)==3 and all('history' not in p for p in starts)
    assert all(p['allowProviderModelFallback'] is False and p['environments']==[] for p in starts)
    assert all(len(p['dynamicTools'])==5 for p in starts)


@pytest.mark.parametrize('key,value',[('role','defensor'),('backend','openai-agents'),('snapshot','wrong'),('model','other')])
def test_resume_wrong_binding_rejected(make_run,key,value):
    store,m,r,rpc,tools=rig(make_run)
    async def exercise():
        e=await r.preflight();await r.session('auditor',e)
        record=store.get(m.run_id,'roles/auditor/codex-session');record[key]=value
        store.put(m.run_id,'roles/auditor/codex-session',record)
        with pytest.raises(RuntimePaused):await r.session('auditor',e)
    asyncio.run(exercise())
    assert not any(k=='turn/start' for k,_ in rpc.calls)


@pytest.mark.parametrize('mode',['quota','transport','native','approval','wrong_thread','timeout'])
def test_failed_or_ambiguous_turn_never_automatically_retried(make_run,mode):
    store,m,r,rpc,tools=rig(make_run);rpc.mode=mode;r.config.limits.call_timeout=1
    async def exercise():
        with pytest.raises((RuntimePaused,TimeoutError)):await r.invoke('auditor','initial-0000',{},tools)
        with pytest.raises(AmbiguousTurn):await r.invoke('auditor','initial-0000',{},tools)
    asyncio.run(exercise())
    assert sum(k=='turn/start' for k,_ in rpc.calls)==1
    assert store.get(m.run_id,'codex-turns/'+tools.context.invocation_id)['status']=='ambiguous'
    assert rpc.closed


def test_confirmed_turn_recovered_without_duplicate_generation(make_run):
    store,m,r,rpc,tools=rig(make_run)
    async def exercise():
        first=await r.invoke('auditor','initial-0000',{},tools)
        assert await r.invoke('auditor','initial-0000',{},tools)==first
    asyncio.run(exercise())
    assert sum(k=='turn/start' for k,_ in rpc.calls)==1
    assert store.get(m.run_id,'ledger')['known_cost_usd'] is None


def test_cancel_turn_saved_as_ambiguous_and_closed(make_run):
    store,m,r,rpc,tools=rig(make_run);rpc.mode='timeout'
    async def exercise():
        task=asyncio.create_task(r.invoke('auditor','initial-0000',{},tools))
        while not any(k=='turn/start' for k,_ in rpc.calls):await asyncio.sleep(.001)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):await task
        with pytest.raises(AmbiguousTurn):await r.invoke('auditor','initial-0000',{},tools)
    asyncio.run(exercise())
    assert rpc.closed


def test_tool_request_wrong_thread_rejected_before_access(make_run):
    store,m,r,rpc,tools=rig(make_run)
    msg={'id':1,'params':{'threadId':'defender','turnId':'turn','tool':'read_source','arguments':{'path':'app.py'}}}
    with pytest.raises(RuntimePaused):asyncio.run(r.dispatch_tool(msg,tools,'auditor','turn',1))
    assert not rpc.responses


def test_cross_role_evidence_denied_via_wire_before_barrier(make_run):
    store,m,r,rpc,tools=rig(make_run)
    msg={'id':1,'params':{'threadId':'thread','turnId':'turn','tool':'read_evidence','arguments':{'evidence_id':'b'*24}}}
    asyncio.run(r.dispatch_tool(msg,tools,'thread','turn',1))
    assert rpc.responses[-1][1]['success'] is False


def test_lost_quota_preflight_pause_then_explicit_resume(make_run,monkeypatch):
    store,m,r,rpc,tools=rig(make_run)
    rpc.quota['ordinaryUsageAllowed']=None
    monkeypatch.setattr('audit3.executor.shutil.which',lambda _:None)
    state=asyncio.run(Workflow(store,m.run_id,runtime=r).run())
    assert state['status']=='blocked' and not store.exists(m.run_id,'barrier')
    assert not any(k=='turn/start' for k,_ in rpc.calls)
    # Restore observability. Explicit resume revalidates; preflight failure did
    # not create an attempt or duplicate the baseline executor receipt.
    rpc2=FakeRPC(r.home);r.rpc=rpc2
    asyncio.run(r.preflight())
    assert len(store.names(m.run_id,'receipts'))==1


def test_export_never_includes_codex_home_or_private_frames(make_run,tmp_path):
    store,m,r,rpc,tools=rig(make_run)
    home=store.root/'codex-home';home.mkdir();(home/'auth.json').write_text('SYNTHETIC-SECRET')
    store.put(m.run_id,'roles/auditor/codex-session',{'thread_id':'private'})
    import zipfile
    with zipfile.ZipFile(export_zip(store,m.run_id,tmp_path/'report.zip')) as z:
        assert not any('session' in p or 'auth' in p or 'codex-home' in p for p in z.namelist())
        assert 'SYNTHETIC-SECRET' not in str([z.read(n) for n in z.namelist()])
        assert 'integração real ainda não validada' in z.read('report.md').decode()


def test_historical_run_is_exportable_but_cannot_resume_codex(make_run):
    store,m,*_=rig(make_run)
    raw=store.get(m.run_id,'manifest');raw.pop('backend');raw.pop('client_version');raw.pop('models')
    store.put(m.run_id,'manifest',raw)
    assert build_report(store,m.run_id)['manifest'].get('backend') is None
    with pytest.raises(PolicyError,match='histórico'):Workflow(store,m.run_id)


def test_retired_cli_api_flags_fail_without_probe(monkeypatch):
    from audit3.cli import main
    from audit3.validation import main as validate
    assert main(['doctor','--probe-api'])==2
    with pytest.raises(SystemExit) as exc:validate(['--api'])
    assert exc.value.code==2


def test_protocol_schema_tool_names_and_types_are_official():
    root=Path(__file__).parent/'contracts'
    x=json.loads((root/'ThreadStartParams.json').read_text())
    assert {'dynamicTools','permissions','allowProviderModelFallback'} <= set(x['properties'])
    d=x['definitions']['DynamicToolSpec']['oneOf'][0]
    assert set(d['required'])=={'type','name','description','inputSchema'}
    for spec in tool_specs():assert set(d['required'])<=set(spec)
    x=json.loads((root/'TurnStartParams.json').read_text())
    assert 'standard speed' in x['properties']['serviceTierForTurn']['description']


@pytest.mark.parametrize('model', [Opinion, Judgment])
def test_strict_output_schema_requires_defaulted_fields_at_every_object(model):
    original = model.model_json_schema()
    assert 'schema_version' not in original['required']  # Regression: official HTTP 400.
    strict = output_schema(model)
    def check(node):
        if isinstance(node, dict):
            if 'properties' in node:
                assert node['required'] == list(node['properties'])
                assert node['additionalProperties'] is False
            for value in node.values(): check(value)
        elif isinstance(node, list):
            for value in node: check(value)
    check(strict)
    assert model.model_json_schema() == original  # Historical/local contracts unchanged.
    # Only required lists change; keep refs, nullability, constraints and defaults.
    def without_required(node):
        if isinstance(node, dict): return {k: without_required(v) for k,v in node.items() if k != 'required'}
        if isinstance(node, list): return [without_required(v) for v in node]
        return node
    assert without_required(strict) == without_required(original)
    if model is Judgment:
        assert 'baseline_assessment' in strict['required']
        assert {'type': 'null'} in strict['properties']['baseline_assessment']['anyOf']


@pytest.mark.parametrize('final', [False, True])
def test_turn_request_sends_strict_opinion_and_judgment_schemas(make_run, final):
    store, m, runtime, rpc, tools = rig(make_run)
    asyncio.run(runtime.invoke('auditor', 'initial-0000', {}, tools, final=final))
    sent = next(params['outputSchema'] for method, params in rpc.calls if method == 'turn/start')
    assert sent == output_schema(Judgment if final else Opinion)
    assert 'schema_version' in sent['required']
    if final: assert 'baseline_assessment' in sent['required']


@pytest.mark.parametrize('role,phase', [('auditor','initial-0000'),('defensor','initial-0000'),('juiz','blind'),('juiz','final')])
def test_every_turn_receives_actual_verified_financial_facts_without_secrets(make_run, role, phase):
    store, m, runtime, rpc, tools = rig(make_run)
    rpc.account['planType'] = 'prolite'
    confirmation = {**proof(), 'account_fingerprint': account_identity(rpc.account)}
    store.put(m.run_id, 'financial-confirmation', confirmation)
    payload = {'phase': phase, 'financial_context': {'status': 'untrusted_override'}}
    asyncio.run(runtime.invoke(role, phase, payload, tools, final=phase=='final'))
    sent = next(params for method, params in rpc.calls if method=='turn/start')
    wire = json.loads(sent['input'][0]['text'])
    context = wire['financial_context']
    assert context['verification_source']=='controller_preflight' and context['source']=='operator_factual_confirmation'
    assert context['status']=='verified_facts' and context['ordinary_usage_allowed'] is True
    assert context['authentication']=='chatgpt' and context['planType']=='prolite'
    assert context['checked_at']==confirmation['checked_at']  # Never renew operator time.
    assert context['auto_recharge']=='disabled' and context['extra_credits']=='none'
    assert context['atomic_financial_guard'] is False and context['additional_spending_authorized'] is False
    assert 0<context['remaining_valid_seconds']<=1800
    assert not {'email','account_fingerprint','access_token'} & set(context)
    assert ACCOUNT['email'] not in json.dumps(context)
    assert payload['financial_context']=={'status':'untrusted_override'}
    record=store.get(m.run_id,'codex-turns/'+tools.context.invocation_id)
    assert record['wire_input_hash']==object_hash(wire) and record['financial_context']==context
    assert record['input_hash']==object_hash(payload)
    session=next(params for method,params in rpc.calls if method=='thread/start')
    assert 'financial_context' in session['developerInstructions']


def test_failed_financial_preflight_never_delivers_a_verified_context_or_starts_turn(make_run):
    store,m,runtime,rpc,tools=rig(make_run)
    rpc.quota['ordinaryUsageAllowed']=None
    with pytest.raises(RuntimePaused):asyncio.run(runtime.invoke('auditor','initial-0000',{},tools))
    assert not any(method in {'thread/start','turn/start'} for method,_ in rpc.calls)
    assert store.get(m.run_id,'ledger')['calls']==[]


def test_turn_deadline_reports_role_operation_and_preserves_limit(make_run):
    store,m,runtime,rpc,tools=rig(make_run)
    runtime.config.limits.call_timeout=1
    rpc.mode='timeout'
    with pytest.raises(RuntimePaused,match='defensor/initial-0000: turn_deadline; aguardando event_stream'):
        asyncio.run(runtime.invoke('defensor','initial-0000',{},tools))
    saved=store.get(m.run_id,'codex-turns/'+tools.context.invocation_id)
    assert saved['timeout']['origin']=='turn_deadline'
    assert saved['timeout']['operation']=='event_stream'
    assert saved['timeout']['turn_limit_seconds']==1 and runtime.config.limits.call_timeout==1
    assert saved['timeout']['elapsed_monotonic_seconds']>=1
    assert rpc.closed and sum(method=='turn/interrupt' for method,_ in rpc.calls)==1


def test_rpc_timeout_inside_turn_is_distinguished_from_turn_deadline(make_run):
    store,m,runtime,rpc,tools=rig(make_run)
    original=rpc.request
    reads=0
    async def request(method,params, **kwargs):
        nonlocal reads
        if method=='account/rateLimits/read':
            reads+=1
            if reads==2:raise TimeoutError('MOCK RPC timeout; no network')
        return await original(method,params, **kwargs)
    rpc.request=request
    rpc.events.put_nowait({'method':'account/rateLimits/updated','params':{}})
    with pytest.raises(RuntimePaused,match='rpc_timeout; aguardando rpc:account/rateLimits/read'):
        asyncio.run(runtime.invoke('defensor','initial-0000',{},tools))
    saved=store.get(m.run_id,'codex-turns/'+tools.context.invocation_id)
    assert saved['timeout']['origin']=='rpc_timeout'
    assert saved['timeout']['turn_limit_seconds']==120 and saved['timeout']['rpc_limit_seconds']==20


def test_explicit_interruption_recovery_uses_existing_slot_and_reuses_auditor(make_run):
    store,m,runtime,rpc,tools=rig(make_run)
    store.put(m.run_id,'baseline',{'ids':[]})
    runtime.config.limits.call_timeout=1
    from helpers import initial_investigation
    rpc.output = initial_investigation(store, m, 'auditor').model_dump_json()
    defender_output = initial_investigation(store, m, 'defensor').model_dump_json()
    workflow=Workflow(store,m.run_id,runtime=runtime)
    async def exercise():
        await workflow.invoke('auditor','initial-0000')
        auditor_before=store.path(m.run_id,'roles/auditor/phases/initial-0000.json').read_bytes()
        rpc.mode='timeout'
        with pytest.raises(RuntimePaused,match='turn_deadline'):
            await workflow.invoke('defensor','initial-0000')
        old=store.get(m.run_id,'roles/defensor/attempts/initial-0000-0')
        turn=store.get(m.run_id,'codex-turns/'+old['invocation_id'])
        old_bytes=store.path(m.run_id,'codex-turns/'+old['invocation_id']+'.json').read_bytes()
        store.put(m.run_id,'roles/defensor/attempts/initial-0000-0-interrupted',{
            'source':'official_app_server_thread_read','status':'interrupted',
            'invocation_id':old['invocation_id'],'thread_id':turn['thread_id'],'turn_id':turn['turn_id']},immutable=True)
        recovered=FakeRPC(runtime.home)
        recovered.output = defender_output
        runtime.rpc=recovered
        await workflow.invoke('auditor','initial-0000')
        assert recovered.calls==[]
        await workflow.invoke('defensor','initial-0000')
        assert sum(method=='turn/start' for method,_ in recovered.calls)==1
        assert store.path(m.run_id,'roles/auditor/phases/initial-0000.json').read_bytes()==auditor_before
        assert store.path(m.run_id,'codex-turns/'+old['invocation_id']+'.json').read_bytes()==old_bytes
        assert store.get(m.run_id,'roles/defensor/attempts/initial-0000-1')['invocation_id']!=old['invocation_id']
        assert len(store.get(m.run_id,'ledger')['calls'])==3
        assert workflow.config.limits.invalid_output_retries==1
    asyncio.run(exercise())


@pytest.mark.parametrize('patch',[{'status':'inProgress'},{'turn_id':'wrong'},{'source':'operator_guess'},{'invocation_id':'wrong'}])
def test_invalid_interruption_recovery_cannot_start_another_turn(make_run,patch):
    store,m,runtime,rpc,tools=rig(make_run)
    store.put(m.run_id,'baseline',{'ids':[]})
    inv='d'*24
    store.put(m.run_id,'roles/defensor/attempts/initial-0000-0',{'invocation_id':inv})
    store.put(m.run_id,'codex-turns/'+inv,{'status':'ambiguous','thread_id':'MOCK-thread','turn_id':'MOCK-turn','role':'defensor','phase':'initial-0000'})
    recovery={'source':'official_app_server_thread_read','status':'interrupted','invocation_id':inv,'thread_id':'MOCK-thread','turn_id':'MOCK-turn',**patch}
    store.put(m.run_id,'roles/defensor/attempts/initial-0000-0-interrupted',recovery)
    with pytest.raises(RuntimePaused,match='Reconciliação'):
        asyncio.run(Workflow(store,m.run_id,runtime=runtime).invoke('defensor','initial-0000'))
    assert rpc.calls==[]


def test_interruption_recovery_does_not_increase_zero_retry_limit(make_run):
    cfg=Config();cfg.limits.invalid_output_retries=0
    store,m=make_run(config=cfg)
    runtime=CodexRuntime(store,m.run_id,cfg);rpc=FakeRPC(runtime.home);runtime.rpc=rpc
    store.put(m.run_id,'baseline',{'ids':[]})
    inv='d'*24
    store.put(m.run_id,'roles/defensor/attempts/initial-0000-0',{'invocation_id':inv})
    store.put(m.run_id,'codex-turns/'+inv,{'status':'ambiguous','thread_id':'MOCK-thread','turn_id':'MOCK-turn','role':'defensor','phase':'initial-0000'})
    store.put(m.run_id,'roles/defensor/attempts/initial-0000-0-interrupted',{
        'source':'official_app_server_thread_read','status':'interrupted','invocation_id':inv,'thread_id':'MOCK-thread','turn_id':'MOCK-turn'})
    with pytest.raises(PolicyError,match='esgotadas'):
        asyncio.run(Workflow(store,m.run_id,runtime=runtime).invoke('defensor','initial-0000'))
    assert rpc.calls==[] and not store.exists(m.run_id,'roles/defensor/attempts/initial-0000-1')


def mock_single_extra_authorization(store, manifest, runtime):
    """Synthetic operator exception; no official query or inference."""
    store.put(manifest.run_id,'baseline',{'ids':[]})
    for slot in (0,1):
        inv=str(slot+1)*24
        name=f'roles/defensor/attempts/initial-0000-{slot}'
        store.put(manifest.run_id,name,{'invocation_id':inv},immutable=True)
        store.put(manifest.run_id,'codex-turns/'+inv,{'role':'defensor','phase':'initial-0000',
            'status':'ambiguous','thread_id':'old-thread','turn_id':f'old-turn-{slot}'})
        store.put(manifest.run_id,name+'-interrupted',{'source':'official_app_server_thread_read',
            'status':'interrupted','invocation_id':inv,'thread_id':'old-thread','turn_id':f'old-turn-{slot}'})
    authorization={'source':'explicit_operator_authorization','run_id':manifest.run_id,
        'role':'defensor','phase':'initial-0000','additional_attempts':1,'attempt_slot':2,
        'config_hash':manifest.config_hash,'previous_invocation_id':'2'*24}
    store.put(manifest.run_id,'roles/defensor/attempts/initial-0000-extra-authorization',authorization,immutable=True)
    return authorization


def test_one_explicit_extra_slot_preserves_history_and_reuses_auditor(make_run):
    store,m,runtime,rpc,tools=rig(make_run)
    mock_single_extra_authorization(store,m,runtime)
    from helpers import initial_investigation
    auditor_opinion = initial_investigation(store, m, 'auditor')
    rpc.output = initial_investigation(store, m, 'defensor').model_dump_json()
    cached={'role': 'auditor', 'phase': 'initial-0000', 'published_at': now(), 'output': auditor_opinion.model_dump(mode='json')}
    store.put(m.run_id,'roles/auditor/phases/initial-0000',cached,immutable=True)
    preserved={str(p):p.read_bytes() for folder in ('roles/auditor/phases','roles/defensor/attempts','codex-turns')
        for p in store.path(m.run_id,folder).glob('*.json')}
    workflow=Workflow(store,m.run_id,runtime=runtime)
    async def exercise():
        await workflow.invoke('auditor','initial-0000')
        assert rpc.calls==[]
        await workflow.invoke('defensor','initial-0000')
        await workflow.invoke('defensor','initial-0000')
    asyncio.run(exercise())
    assert sum(method=='turn/start' for method,_ in rpc.calls)==1
    assert store.exists(m.run_id,'roles/defensor/attempts/initial-0000-2')
    assert not store.exists(m.run_id,'roles/defensor/attempts/initial-0000-3')
    assert all(Path(path).read_bytes()==value for path,value in preserved.items())
    assert store.get(m.run_id,'config')['limits']['invalid_output_retries']==1


def test_failed_extra_slot_cannot_be_replayed_or_replaced(make_run):
    store,m,runtime,rpc,tools=rig(make_run)
    mock_single_extra_authorization(store,m,runtime)
    rpc.mode='transport'
    workflow=Workflow(store,m.run_id,runtime=runtime)
    with pytest.raises(RuntimePaused):asyncio.run(workflow.invoke('defensor','initial-0000'))
    with pytest.raises(AmbiguousTurn):asyncio.run(workflow.invoke('defensor','initial-0000'))
    assert sum(method=='turn/start' for method,_ in rpc.calls)==1
    assert len(store.get(m.run_id,'ledger')['calls'])==1
    assert not store.exists(m.run_id,'roles/defensor/attempts/initial-0000-3')


def test_failed_extra_recovery_stops_before_judge_and_keeps_elapsed_time(make_run):
    store,m,runtime,rpc,tools=rig(make_run)
    mock_single_extra_authorization(store,m,runtime)
    state=store.get(m.run_id,'state');state['elapsed_seconds']=291.328201995002
    store.put(m.run_id,'state',state)
    rpc.mode='transport'
    result=asyncio.run(Workflow(store,m.run_id,runtime=runtime).run(resume=True))
    assert result['status']=='blocked'
    assert result['elapsed_seconds']>=291.328201995002
    assert len(store.get(m.run_id,'ledger')['calls'])==1
    assert store.get(m.run_id,'ledger')['calls'][0]['role']=='defensor'
    assert not store.exists(m.run_id,'roles/juiz/codex-session')
    assert not store.exists(m.run_id,'roles/auditor/codex-session')


def test_invalid_extra_output_stops_without_a_correction_turn(make_run,monkeypatch):
    store,m,runtime,rpc,tools=rig(make_run)
    mock_single_extra_authorization(store,m,runtime)
    calls=[]
    async def invalid(*args,**kwargs):calls.append(1);return '{'
    monkeypatch.setattr(runtime,'invoke',invalid)
    with pytest.raises(PolicyError,match='saída inválida após limite'):
        asyncio.run(Workflow(store,m.run_id,runtime=runtime).invoke('defensor','initial-0000'))
    assert calls==[1] and store.exists(m.run_id,'roles/defensor/attempts/initial-0000-2-rejected')
    assert not store.exists(m.run_id,'roles/defensor/attempts/initial-0000-3')


@pytest.mark.parametrize('patch',[{'source':'automatic_retry'},{'run_id':'0'*24},{'role':'auditor'},
    {'phase':'contest'},{'additional_attempts':2},{'attempt_slot':3},{'config_hash':'wrong'},
    {'previous_invocation_id':'wrong'}])
def test_extra_slot_requires_exact_scoped_authorization(make_run,patch):
    store,m,runtime,rpc,tools=rig(make_run)
    authorization=mock_single_extra_authorization(store,m,runtime)
    store.put(m.run_id,'roles/defensor/attempts/initial-0000-extra-authorization',{**authorization,**patch})
    with pytest.raises(RuntimePaused,match='Exceção de tentativa adicional inválida'):
        asyncio.run(Workflow(store,m.run_id,runtime=runtime).invoke('defensor','initial-0000'))
    assert rpc.calls==[]


def test_docker_execution_without_receipt_is_not_automatically_repeated(make_run):
    from audit3.executor import Executor
    from audit3.config import Profile
    store,m=make_run();req=Request(kind='baseline',purpose='MOCK restart case')
    fingerprint=object_hash({'source':m.source_id,'profile':m.profile_hash,'kind':req.kind,'script':req.script})
    store.put(m.run_id,'execution-attempts/'+'d'*24,{'fingerprint':fingerprint,'owner':'baseline','phase':'baseline','receipt_id':'d'*24,'status':'running'})
    with pytest.raises(RuntimePaused,match='ambígua'):
        asyncio.run(Executor(store,m,Config(),Profile(name='synthetic')).execute(req,'baseline','baseline'))


def test_tool_schema_rejects_hidden_controller_keyword(make_run):
    store,m,r,rpc,tools=rig(make_run)
    msg={'id':1,'params':{'threadId':'thread','turnId':'turn','tool':'read_evidence','arguments':{'evidence_id':'d'*24,'record_access':False}}}
    with pytest.raises(RuntimePaused):asyncio.run(r.dispatch_tool(msg,tools,'thread','turn',1))


def test_completed_checkpoint_recovers_interrupted_usage_ledger(make_run):
    store,m,r,rpc,tools=rig(make_run)
    async def exercise():
        output=await r.invoke('auditor','initial-0000',{},tools)
        ledger=store.get(m.run_id,'ledger');ledger['calls'][0]['status']='in_flight';store.put(m.run_id,'ledger',ledger)
        assert await r.invoke('auditor','initial-0000',{},tools)==output
    asyncio.run(exercise())
    assert store.get(m.run_id,'ledger')['calls'][0]['status']=='completed'
    assert sum(k=='turn/start' for k,_ in rpc.calls)==1


def test_successful_source_read_and_path_escape_through_wire(make_run):
    store,m,r,rpc,tools=rig(make_run)
    async def exercise():
        for path in ['app.py','../roles/defensor/initial.json']:
            msg={'id':path,'params':{'threadId':'thread','turnId':'turn','tool':'read_source','arguments':{'path':path}}}
            await r.dispatch_tool(msg,tools,'thread','turn',1)
    asyncio.run(exercise())
    assert [result['success'] for _,result in rpc.responses]==[True,False]
    data=json.loads(rpc.responses[0][1]['contentItems'][0]['text'])
    assert data['sha256']==next(f.sha256 for f in m.files if f.path=='app.py')


def test_cross_role_receipt_existing_is_private_before_barrier(make_run,monkeypatch):
    from audit3.executor import Executor
    from audit3.config import Profile
    store,m,r,rpc,tools=rig(make_run)
    monkeypatch.setattr('audit3.executor.shutil.which',lambda _:None)
    rec=asyncio.run(Executor(store,m,Config(),Profile(name='synthetic')).execute(Request(kind='python',script='print(1)',purpose='MOCK private receipt'),'defensor','initial-0000'))
    msg={'id':1,'params':{'threadId':'thread','turnId':'turn','tool':'read_evidence','arguments':{'evidence_id':rec.id}}}
    asyncio.run(r.dispatch_tool(msg,tools,'thread','turn',1))
    assert rpc.responses[-1][1]['success'] is False
    assert not store.exists(m.run_id,'barrier')


def test_official_notification_requires_full_quota_read_not_inferred_recovery(make_run):
    store,m,r,rpc,tools=rig(make_run)
    rpc.events.put_nowait({'method':'account/rateLimits/updated','params':{'rateLimits':QUOTA['rateLimits']}})
    asyncio.run(r.invoke('auditor','initial-0000',{},tools))
    assert sum(k=='account/rateLimits/read' for k,_ in rpc.calls)==2
    assert store.get(m.run_id,'codex-turns/'+tools.context.invocation_id)['status']=='completed'


def test_official_cumulative_samples_not_misreported_as_additive_turn_usage(make_run):
    store,m,r,rpc,tools=rig(make_run)
    original=rpc.request
    async def request(method,params, **kwargs):
        result=await original(method,params, **kwargs)
        if method=='turn/start':
            rpc.events._queue.appendleft({'method':'thread/tokenUsage/updated','params':{'threadId':params['threadId'],'turnId':result['turn']['id'],
                'tokenUsage':{'last':{'inputTokens':25,'outputTokens':5},'total':{'inputTokens':100,'outputTokens':20}}}})
        return result
    rpc.request=request
    asyncio.run(r.invoke('auditor','initial-0000',{},tools))
    ledger=store.get(m.run_id,'ledger')
    assert ledger['tokens'] is None and ledger['known_cost_usd'] is None
    assert ledger['calls'][0]['official_token_sample']['counters']['total']['inputTokens']==100


@pytest.mark.parametrize('prior_status', ['completed', 'ambiguous'])
def test_resume_usage_snapshot_from_known_prior_turn_is_not_current_usage(make_run, prior_status):
    store,m,runtime,rpc,tools=rig(make_run)
    async def exercise():
        effective=await runtime.preflight()
        thread=await runtime.session('auditor',effective)
        runtime.loaded.clear()
        prior_name='codex-turns/'+'d'*24
        store.put(m.run_id,prior_name,{'role':'auditor','thread_id':thread,
            'turn_id':'prior-turn','status':prior_status})
        prior_bytes=store.path(m.run_id,prior_name+'.json').read_bytes()
        original=rpc.request
        async def request(method,params, **kwargs):
            result=await original(method,params, **kwargs)
            if method=='thread/resume':
                # CLI 0.167.0 replays the last known thread usage on resume,
                # before any new turn/start and with the previous turn's ID.
                rpc.events.put_nowait({'method':'thread/tokenUsage/updated','params':{
                    'threadId':thread,'turnId':'prior-turn','tokenUsage':{
                        'last':{'inputTokens':6194,'outputTokens':830},
                        'total':{'inputTokens':25421,'outputTokens':1034}}}})
            return result
        rpc.request=request
        await runtime.invoke('auditor','initial-0000',{},tools)
        saved=store.get(m.run_id,'codex-turns/'+tools.context.invocation_id)
        assert saved['status']=='completed' and saved['usage'] is None
        assert store.path(m.run_id,prior_name+'.json').read_bytes()==prior_bytes
        assert len(store.get(m.run_id,'ledger')['calls'])==1
        assert sum(method=='turn/start' for method,_ in rpc.calls)==1
        events=[store.get(m.run_id,'events/'+n) for n in store.names(m.run_id,'events')]
        ignored=[e for e in events if e['kind']=='historical_usage_ignored']
        assert len(ignored)==1 and ignored[0]['data']['reported_turn_id']=='prior-turn'
    asyncio.run(exercise())


@pytest.mark.parametrize('method,event_turn,event_thread,prior_role', [
    ('thread/tokenUsage/updated','unknown-turn',None,'auditor'),
    ('thread/tokenUsage/updated',None,None,'auditor'),
    ('thread/tokenUsage/updated','prior-turn','other-thread','auditor'),
    ('thread/tokenUsage/updated','prior-turn',None,'defensor'),
    ('item/completed','prior-turn',None,'auditor'),
    ('turn/completed','prior-turn',None,'auditor'),
])
def test_resume_usage_exception_does_not_accept_unknown_or_other_turn_work(
        make_run,method,event_turn,event_thread,prior_role):
    store,m,runtime,rpc,tools=rig(make_run)
    async def exercise():
        thread=await runtime.session('auditor',await runtime.preflight())
        runtime.loaded.clear()
        store.put(m.run_id,'codex-turns/'+'d'*24,{'role':prior_role,
            'thread_id':thread,'turn_id':'prior-turn','status':'completed'})
        original=rpc.request
        async def request(name,params, **kwargs):
            result=await original(name,params, **kwargs)
            if name=='thread/resume':
                rpc.events.put_nowait({'method':method,'params':{
                    'threadId':event_thread or thread,'turnId':event_turn,
                    'turn':{'id':event_turn,'status':'completed'},
                    'item':{'type':'agentMessage','phase':'final_answer','text':'{}'}}})
            return result
        rpc.request=request
        with pytest.raises(RuntimePaused,match='Evento de outr'):
            await runtime.invoke('auditor','initial-0000',{},tools)
        assert store.get(m.run_id,'codex-turns/'+tools.context.invocation_id)['status']=='ambiguous'
        assert rpc.closed and sum(name=='turn/interrupt' for name,_ in rpc.calls)==1
    asyncio.run(exercise())


def test_ambiguous_executor_result_pauses_model_instead_of_becoming_tool_feedback(make_run):
    store,m,r,rpc,tools=rig(make_run)
    async def ambiguous(*args):raise RuntimePaused('MOCK ambiguous executor checkpoint')
    tools.executor=SimpleNamespace(execute=ambiguous)
    msg={'id':1,'params':{'threadId':'thread','turnId':'turn','tool':'submit_test','arguments':{'request':{'kind':'python','script':'print(1)','purpose':'MOCK'}}}}
    with pytest.raises(RuntimePaused):asyncio.run(r.dispatch_tool(msg,tools,'thread','turn',1))
    assert not rpc.responses
