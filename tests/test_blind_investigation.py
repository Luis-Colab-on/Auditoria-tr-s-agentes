"""Offline protocol regressions; tool reads are real, reasoning is explicitly mock."""
import asyncio
import pytest
from audit3.config import Config, Limits
from audit3.schemas import Opinion, InspectionRecord, SourceRef
from audit3.security import PolicyError, now
from audit3.workflow import Workflow, batches
from audit3.report import build_report
from helpers import MockRuntime
from test_tools_schemas import tools_for


def empty():
    return Opinion(summary='MOCK empty opinion', inspections=[], findings=[], positions=[], limitations=[])


def inspect(tools, path='app.py', start=1, end=None):
    f = tools.index[path]
    result = tools.read_source(path, start, end or f.lines)
    return InspectionRecord(refs=[SourceRef(path=path, start=start, end=result['lines'][-1]['line'], sha256=f.sha256)],
        requirement='Synthetic input invariant', analysis='MOCK explicit examination of the input guard',
        flow_verified=False, flow_description='', limitations=[])


def test_three_empty_blind_opinions_never_publish_barrier(make_run, monkeypatch):
    monkeypatch.setattr('audit3.executor.shutil.which', lambda _: None)
    store, m = make_run()
    async def handler(role, phase, payload, tools, final):
        if phase.startswith('initial-') or phase == 'blind': return empty()
    runtime = MockRuntime(handler)
    result = asyncio.run(Workflow(store, m.run_id, runtime=runtime).run())
    assert result['status'] == 'partial'
    assert not store.exists(m.run_id, 'barrier')
    assert not any(c['phase'] in {'contest', 'review', 'final'} for c in runtime.calls)


@pytest.mark.parametrize('role,late_phase', [('auditor', 'contest'), ('defensor', 'reply'), ('juiz', 'review')])
def test_late_reads_cannot_validate_blind_inspections(make_run, role, late_phase):
    store, m = make_run({'app.py': 'x = 1\n'})
    inspection = inspect(tools_for(store, m, role, late_phase))
    phase = 'blind' if role == 'juiz' else 'initial-0000'
    opinion = empty(); opinion.inspections = [inspection]
    with pytest.raises(PolicyError):
        Workflow(store, m.run_id, runtime=MockRuntime()).validate_output(opinion, tools_for(store, m, role, phase), False)


def test_judge_baseline_only_never_satisfies_blind_source_inspection(make_run, monkeypatch):
    monkeypatch.setattr('audit3.executor.shutil.which', lambda _: None)
    store, m = make_run()
    async def handler(role, phase, payload, tools, final):
        if phase == 'blind':
            for eid in payload['baseline_receipts']: tools.read_evidence(eid)
            return empty()
    runtime = MockRuntime(handler)
    asyncio.run(Workflow(store, m.run_id, runtime=runtime).run())
    assert not store.exists(m.run_id, 'barrier')


def test_directed_judge_and_no_findings_are_valid(make_run, monkeypatch):
    monkeypatch.setattr('audit3.executor.shutil.which', lambda _: None)
    store, m = make_run({'app.py': 'x = 1\ny = 2\n', 'empty.py': ''})
    async def handler(role, phase, payload, tools, final):
        if phase == 'blind':
            opinion = empty(); opinion.inspections = [inspect(tools, end=1)]; return opinion
    runtime = MockRuntime(handler)
    asyncio.run(Workflow(store, m.run_id, runtime=runtime).run())
    assert store.exists(m.run_id, 'barrier')
    report = build_report(store, m.run_id)
    assert report['coverage']['independent_investigation']['valid']
    assert report['coverage']['independent_investigation']['empty_files'] == ['empty.py']
    assert not report['findings']


def test_persisted_empty_phase_is_rejected_without_new_call(make_run):
    store, m = make_run()
    runtime = MockRuntime()
    store.put(m.run_id, 'roles/auditor/phases/initial-0000', {
        'role': 'auditor', 'phase': 'initial-0000', 'invocation_id': 'old', 'published_at': now(),
        'output': empty().model_dump(mode='json')})
    with pytest.raises(PolicyError):
        asyncio.run(Workflow(store, m.run_id, runtime=runtime).invoke('auditor', 'initial-0000'))
    assert runtime.calls == []


def test_recovery_reuses_legitimate_initial_reads(make_run):
    store, m = make_run({'app.py': 'x = 1\n'})
    opinion = empty(); opinion.inspections = [inspect(tools_for(store, m, 'auditor', 'initial-0000'))]
    store.put(m.run_id, 'baseline', {'ids': []})
    async def handler(*args): return opinion
    runtime = MockRuntime(handler)
    workflow = Workflow(store, m.run_id, runtime=runtime)
    assert asyncio.run(workflow.invoke('auditor', 'initial-0000'))['inspections']
    assert asyncio.run(workflow.invoke('auditor', 'initial-0000'))['inspections']
    assert len(runtime.calls) == 1


@pytest.mark.parametrize('wrong', ['role', 'run', 'version', 'file_hash'])
def test_read_identity_and_version_are_checked(make_run, wrong):
    store, m = make_run({'app.py': 'x = 1\n'})
    tools = tools_for(store, m, 'auditor', 'initial-0000')
    inspection = inspect(tools)
    name = next(n for n in store.names(m.run_id, 'events') if store.get(m.run_id, 'events/' + n)['kind'] == 'tool')
    event = store.get(m.run_id, 'events/' + name)
    if wrong == 'run': event['data']['run_id'] = 'b' * 24
    elif wrong == 'version': event['data']['source_id'] = '0' * 64
    elif wrong == 'file_hash': event['data']['sha256'] = '0' * 64
    else: event['data']['role'] = 'defensor'
    store.put(m.run_id, 'events/' + name, event)
    with pytest.raises(PolicyError): tools.validate_inspection(inspection)


def test_empty_inventory_has_explicit_impediment(make_run, monkeypatch):
    monkeypatch.setattr('audit3.executor.shutil.which', lambda _: None)
    store, m = make_run({'empty.py': ''})
    assert batches(m, 100) == [[]]
    asyncio.run(Workflow(store, m.run_id, runtime=MockRuntime()).run())
    assert not store.exists(m.run_id, 'barrier')
    assert any('inventário sem linhas auditáveis' in gap for gap in build_report(store, m.run_id)['coverage']['gaps'])


def test_post_barrier_read_labeled_blind_cannot_repair_saved_opinion(make_run):
    from audit3.investigation import validate_saved_initial
    store, m = make_run({'app.py': 'x = 1\n'})
    publication = now()
    store.put(m.run_id, 'barrier', {'published_at': publication, 'initial_hashes': {}})
    tools = tools_for(store, m, 'auditor', 'initial-0000')
    opinion = empty(); opinion.inspections = [inspect(tools)]
    store.put(m.run_id, 'roles/auditor/phases/initial-0000', {
        'role': 'auditor', 'phase': 'initial-0000', 'published_at': now(), 'output': opinion.model_dump(mode='json')})
    with pytest.raises(PolicyError):
        validate_saved_initial(store, m, Config.model_validate(store.get(m.run_id, 'config')), 'auditor', 'initial-0000')


def test_partial_analysis_cannot_release_assigned_batch(make_run):
    store, m = make_run({'app.py': 'x = 1\ny = 2\n'})
    tools = tools_for(store, m, 'auditor', 'initial-0000')
    opinion = empty(); opinion.inspections = [inspect(tools, end=1)]
    with pytest.raises(PolicyError, match='não cobre o lote'):
        Workflow(store, m.run_id, runtime=MockRuntime()).validate_output(opinion, tools, False)


def test_blank_analysis_is_not_inspection(make_run):
    store, m = make_run({'app.py': 'x = 1\n'})
    tools = tools_for(store, m, 'juiz', 'blind')
    opinion = empty(); opinion.inspections = [inspect(tools)]
    opinion.inspections[0].requirement = ' '
    with pytest.raises(PolicyError, match='requisito/invariante'):
        Workflow(store, m.run_id, runtime=MockRuntime()).validate_output(opinion, tools, False)


def test_late_coverage_and_scope_review_cannot_remove_structural_gap(make_run, monkeypatch):
    from audit3.completion import assess_completion, context_hash, limitation_messages, VERSION
    from audit3.security import object_hash
    monkeypatch.setattr('audit3.executor.shutil.which', lambda _: None)
    store, m = make_run({'app.py': 'x = 1\n'})
    asyncio.run(Workflow(store, m.run_id, runtime=MockRuntime()).run())
    # A synthetic historical record: all post-barrier evidence is retained, initial
    # analysis is absent. Assessments must not rewrite it or infer conformity.
    name = 'roles/juiz/phases/blind'
    record = store.get(m.run_id, name)
    record['output']['inspections'] = []
    store.put(m.run_id, name, record)
    before = store.path(m.run_id, name + '.json').read_bytes()
    report = build_report(store, m.run_id)
    assert not report['coverage']['independent_investigation']['valid']
    review = {'version': VERSION, 'objective': m.requirements, 'context_hash': context_hash(report),
              'messages': {key: {'kind': 'scope_note', 'justification': 'Synthetic review cannot remove missing blind source evidence',
                'evidence': ['/manifest/requirements']} for key in limitation_messages(report)}}
    review['id'] = object_hash(review)
    assessment = assess_completion(report, review)
    assert assessment['status'] == 'partial'
    assert any('juiz/blind' in b['text'] for b in assessment['blockers'])
    assert store.path(m.run_id, name + '.json').read_bytes() == before


def test_finished_cached_run_revalidates_blind_protocol_without_writes_or_calls(make_run, monkeypatch):
    monkeypatch.setattr('audit3.executor.shutil.which', lambda _: None)
    store, m = make_run({'app.py': 'x = 1\n'})
    asyncio.run(Workflow(store, m.run_id, runtime=MockRuntime()).run())
    # Explicit synthetic representation of the historical bypass: stored done
    # marker, but initial analysis never demonstrated. Never repair these records.
    name = 'roles/auditor/phases/initial-0000'
    record = store.get(m.run_id, name)
    record['output']['inspections'] = []
    store.put(m.run_id, name, record)
    state = store.get(m.run_id, 'state')
    store.put(m.run_id, 'state', {**state, 'status': 'completed'})
    before = {p.relative_to(store.path(m.run_id)): p.read_bytes()
              for p in store.path(m.run_id).rglob('*') if p.is_file()}
    runtime = MockRuntime()
    with pytest.raises(PolicyError, match='Run encerrado com impedimento estrutural'):
        asyncio.run(Workflow(store, m.run_id, runtime=runtime).run(resume=True))
    assert runtime.calls == []
    assert build_report(store, m.run_id)['completion_assessment']['status'] == 'partial'
    after = {p.relative_to(store.path(m.run_id)): p.read_bytes()
             for p in store.path(m.run_id).rglob('*') if p.is_file()}
    assert after == before
    assert store.get(m.run_id, 'state')['status'] == 'completed'
