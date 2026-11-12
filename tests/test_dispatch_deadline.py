"""Local failure injection only: no official client, account or inference."""
import asyncio
import pytest
from audit3.agents import RuntimePaused
from test_codex_runtime import rig


@pytest.mark.parametrize('origin', ['global_deadline', 'financial_deadline'])
def test_deadline_expiring_in_persistence_prevents_dispatch(make_run, monkeypatch, origin):
    store, manifest, runtime, rpc, tools = rig(make_run)
    original_put = store.put
    original_proof = store.get(manifest.run_id, 'financial-confirmation')
    wire, pipe = wire_transport()
    original_request = rpc.request
    async def request(method, params, **kwargs):
        if method == 'turn/start':
            return await wire.request(method, params, **kwargs)
        return await original_request(method, params, **kwargs)
    rpc.request = request
    async def exercise():
        loop = asyncio.get_running_loop()
        base_time, offset = loop.time(), [0.0]
        monkeypatch.setattr(loop, 'time', lambda: base_time + offset[0])
        if origin == 'global_deadline':
            runtime.global_deadline = loop.time() + .05
        else:
            monkeypatch.setattr('audit3.codex_runtime.financial_remaining', lambda _: .05)
        def delayed_put(run_id, name, value, **kwargs):
            result = original_put(run_id, name, value, **kwargs)
            if name.startswith('codex-turns/') and value['status'] == 'sending':
                offset[0] += .12  # controlled persistence delay, no wall-clock sleep
            return result
        monkeypatch.setattr(store, 'put', delayed_put)
        with pytest.raises(RuntimePaused, match='global_deadline' if origin == 'global_deadline' else 'financeira expirou antes do envio'):
            await runtime.invoke('auditor', 'initial-0000', {}, tools)
        assert pipe.writes == []
        checkpoint = store.get(manifest.run_id, 'codex-turns/' + tools.context.invocation_id)
        assert checkpoint['status'] == 'not_sent'
        assert checkpoint['dispatch_status'] == 'not_sent'
        ledger = store.get(manifest.run_id, 'ledger')
        assert len(ledger['calls']) == 1  # reservation is not silently released
        assert ledger['calls'][0]['dispatch_status'] == 'not_sent'
        assert ledger['tokens'] is None and ledger['known_cost_usd'] is None
        assert store.get(manifest.run_id, 'financial-confirmation') == original_proof
        with pytest.raises(RuntimePaused, match='não enviado'):
            await runtime.invoke('auditor', 'initial-0000', {}, tools)
        assert len(store.get(manifest.run_id, 'ledger')['calls']) == 1
    asyncio.run(exercise())


class FakePipe:
    """Memory-only pipe exercising the production send/request methods."""
    def __init__(self, rpc):
        self.rpc, self.writes, self.drop_response, self.fail_write = rpc, [], False, False

    def write(self, wire):
        import json
        self.writes.append(wire)
        if self.fail_write:
            raise BrokenPipeError('synthetic partial-write uncertainty')
        request = json.loads(wire)
        if not self.drop_response:
            self.rpc.pending[request['id']].set_result({'turn': {'id': 'synthetic-turn'}})

    async def drain(self):
        pass


def wire_transport():
    from types import SimpleNamespace
    from audit3.codex_rpc import StdioRPC
    rpc = StdioRPC('never-executed', None, None, timeout=.01)
    pipe = FakePipe(rpc)
    rpc.proc = SimpleNamespace(stdin=pipe, returncode=0)
    return rpc, pipe


@pytest.mark.parametrize('origin', ['global_deadline', 'turn_deadline', 'financial_deadline'])
def test_transport_deadline_is_checked_after_serialization(monkeypatch, origin):
    from audit3.codex_rpc import TurnDispatch, DispatchExpired
    import audit3.codex_rpc as module
    from types import SimpleNamespace
    async def exercise():
        rpc, pipe = wire_transport()
        loop = asyncio.get_running_loop()
        clock = [loop.time()]
        monkeypatch.setattr(loop, 'time', lambda: clock[0])
        guard = TurnDispatch(clock[0] + .05, origin, lambda: None)
        dumps = module.json.dumps
        def delayed_serialize(data, **kwargs):
            wire = dumps(data, **kwargs)
            clock[0] += .12
            return wire
        monkeypatch.setattr(module, 'json', SimpleNamespace(dumps=delayed_serialize))
        with pytest.raises(DispatchExpired, match=origin):
            await rpc.request('turn/start', {}, dispatch=guard)
        assert pipe.writes == [] and guard.status == 'not_sent'
        assert rpc.pending == {}
        # Ending an existing turn remains possible after this deadline.
        await rpc.request('turn/interrupt', {'threadId': 'existing', 'turnId': 'existing'})
        assert len(pipe.writes) == 1
    asyncio.run(exercise())


def test_already_expired_turn_deadline_sends_no_bytes():
    from audit3.codex_rpc import TurnDispatch, DispatchExpired
    async def exercise():
        rpc, pipe = wire_transport()
        guard = TurnDispatch(asyncio.get_running_loop().time() - 1, 'turn_deadline', lambda: None)
        with pytest.raises(DispatchExpired):
            await rpc.request('turn/start', {}, dispatch=guard)
        assert not pipe.writes and not guard.write_attempted
    asyncio.run(exercise())


def test_transport_requires_guard_for_new_turn():
    async def exercise():
        rpc, pipe = wire_transport()
        with pytest.raises(RuntimePaused, match='proteção explícita'):
            await rpc.request('turn/start', {})
        assert not pipe.writes
    asyncio.run(exercise())


def test_financial_expiry_during_serialization_preserves_original_proof(make_run, monkeypatch):
    from datetime import datetime, timedelta
    import audit3.codex_policy as policy
    from audit3.codex_rpc import TurnDispatch
    from types import SimpleNamespace
    import audit3.codex_rpc as module
    from audit3.codex_policy import financial_remaining
    store, manifest, runtime, _, _ = rig(make_run)
    original = store.get(manifest.run_id, 'financial-confirmation')
    checked = datetime.fromisoformat(original['checked_at'])
    class ExpiredClock:
        @staticmethod
        def now(tz):
            return checked + timedelta(seconds=1800)
    async def exercise():
        rpc, pipe = wire_transport()
        guard = TurnDispatch(asyncio.get_running_loop().time() + 10, 'financial_deadline',
            lambda: financial_remaining(original['checked_at']))
        dumps = module.json.dumps
        def expire_facts(data, **kwargs):
            result = dumps(data, **kwargs)
            monkeypatch.setattr(policy, 'datetime', SimpleNamespace(now=ExpiredClock.now, fromisoformat=datetime.fromisoformat))
            return result
        monkeypatch.setattr(module, 'json', SimpleNamespace(dumps=expire_facts))
        with pytest.raises(RuntimePaused, match='expirada'):
            await rpc.request('turn/start', {}, dispatch=guard)
        assert not pipe.writes and guard.status == 'not_sent'
        assert store.get(manifest.run_id, 'financial-confirmation') == original
    asyncio.run(exercise())


@pytest.mark.parametrize('failure', [None, 'lost_response', 'partial_write'])
def test_transport_tracks_sent_and_uncertain_requests(failure):
    from audit3.codex_rpc import TurnDispatch
    async def exercise():
        rpc, pipe = wire_transport()
        pipe.drop_response = failure == 'lost_response'
        pipe.fail_write = failure == 'partial_write'
        guard = TurnDispatch(asyncio.get_running_loop().time() + 10, 'turn_deadline', lambda: None)
        if failure:
            with pytest.raises(TimeoutError if failure == 'lost_response' else BrokenPipeError):
                await rpc.request('turn/start', {}, dispatch=guard)
        else:
            assert await rpc.request('turn/start', {}, dispatch=guard) == {'turn': {'id': 'synthetic-turn'}}
        assert len(pipe.writes) == 1
        assert guard.status == ('write_uncertain' if failure == 'partial_write' else 'written')
        assert guard.write_attempted and not rpc.pending
    asyncio.run(exercise())


@pytest.mark.parametrize('stage', ['reserve', 'construct'])
def test_preparation_delay_never_prolongs_dispatch_deadline(make_run, monkeypatch, stage):
    store, manifest, runtime, rpc, tools = rig(make_run)
    async def exercise():
        loop = asyncio.get_running_loop()
        clock = [loop.time()]
        monkeypatch.setattr(loop, 'time', lambda: clock[0])
        runtime.global_deadline = clock[0] + .05
        if stage == 'reserve':
            original = runtime.budget.reserve
            async def delayed_reserve(*args):
                result = await original(*args)
                clock[0] += .12
                return result
            monkeypatch.setattr(runtime.budget, 'reserve', delayed_reserve)
        else:
            import audit3.codex_runtime as module
            original = module.output_schema
            def delayed_schema(*args):
                result = original(*args)
                clock[0] += .12
                return result
            monkeypatch.setattr(module, 'output_schema', delayed_schema)
        with pytest.raises(RuntimePaused, match='global_deadline'):
            await runtime.invoke('auditor', 'initial-0000', {}, tools)
        assert not any(method == 'turn/start' for method, _ in rpc.calls)
        checkpoint = store.get(manifest.run_id, 'codex-turns/' + tools.context.invocation_id)
        assert checkpoint['status'] == 'not_sent'
        assert len(store.get(manifest.run_id, 'ledger')['calls']) == 1
    asyncio.run(exercise())


@pytest.mark.parametrize('failure', ['lost_response', 'partial_write'])
def test_runtime_preserves_ambiguity_and_reservation_after_write(make_run, failure):
    from audit3.agents import AmbiguousTurn
    store, manifest, runtime, rpc, tools = rig(make_run)
    wire, pipe = wire_transport()
    pipe.drop_response = failure == 'lost_response'
    pipe.fail_write = failure == 'partial_write'
    original_request = rpc.request
    async def request(method, params, **kwargs):
        if method == 'turn/start':
            return await wire.request(method, params, **kwargs)
        return await original_request(method, params, **kwargs)
    rpc.request = request
    async def exercise():
        with pytest.raises(RuntimePaused if failure == 'lost_response' else BrokenPipeError):
            await runtime.invoke('auditor', 'initial-0000', {}, tools)
        record = store.get(manifest.run_id, 'codex-turns/' + tools.context.invocation_id)
        assert record['status'] == 'ambiguous'
        assert record['dispatch_status'] == ('written' if failure == 'lost_response' else 'write_uncertain')
        assert len(pipe.writes) == 1
        ledger = store.get(manifest.run_id, 'ledger')
        assert len(ledger['calls']) == 1 and ledger['tokens'] is None
        assert ledger['calls'][0]['input_tokens'] is None
        with pytest.raises(AmbiguousTurn):
            await runtime.invoke('auditor', 'initial-0000', {}, tools)
        assert len(pipe.writes) == 1 and len(store.get(manifest.run_id, 'ledger')['calls']) == 1
    asyncio.run(exercise())
