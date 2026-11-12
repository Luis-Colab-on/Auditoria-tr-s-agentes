"""Explicit-review contracts using synthetic reports; no audited code executes.

The fields labelled execution/coverage are hand-authored MOCK inputs to the
assessment unit, not evidence that a model or container actually ran.
"""
import copy
from pathlib import Path
import pytest
from audit3.completion import VERSION, assess_completion, context_hash, limitation_messages
from audit3.scope_review import make_review, NOTES
from audit3.security import PolicyError, object_hash, digest
from test_assessment import completion_fixture, identify_review


def explicit_report(kind='php', *, findings=True):
    report = completion_fixture()
    if kind == 'php':
        folder = Path(__file__).parent / 'fixtures/wordpress-stock'
        source = {str(p.relative_to(folder)): p.read_bytes() for p in sorted(folder.rglob('*')) if p.is_file()}
        objective = 'Revisar somente o contrato de estoque deste snapshot sintético WordPress; sem certificação de produção ou exigência de cobertura quantitativa.'
    else:
        source = {'calculate.py': b'def increment(value):\n    return value + 1\n',
                  'README.md': b'Synthetic numeric contract: increment adds one.\n'}
        objective = 'Inspecionar o contrato numérico deste snapshot sintético; não exige ocorrência em produção nem medição quantitativa de cobertura.'
    inventory = [{'path': path, 'sha256': digest(data), 'size':len(data), 'lines':len(data.splitlines()),
                  'category': 'test' if path.startswith('tests/') else ('spec' if path.endswith('.md') else 'source'), 'reason':None}
                 for path,data in source.items()]
    manifest = report['manifest']
    manifest.update(requirements=objective, source_id=object_hash(inventory), files=inventory,
                    profile_hash='e'*64)
    report['state']['runtime_mode'] = 'mock'
    report['runtime'] = {'backend':'mock','fixture_only':True}
    report['coverage']['roles'] = {role:{f['path']:{'inventoried':True,'total_lines':f['lines'],
        'consulted_lines':f['lines'],'analysis_recorded_lines':f['lines'],
        'missing_consulted':[],'missing_analysis_recorded':[]} for f in inventory} for role in ('auditor','defensor','juiz')}
    report['coverage']['excluded'] = []
    report['judgment']['baseline_assessment'] = 'MOCK contrato: baseline aprovado; não prova ausência universal de defeitos nem ocorrência em produção.'
    baseline=report['receipts'][0]
    baseline.update(source_id=manifest['source_id'],profile_hash=manifest['profile_hash'],phase='baseline',
        execution='compose' if kind=='php' else 'docker',status='passed',exit_code=0,
        stdout='MOCK baseline passed',stdout_sha256=digest(b'MOCK baseline passed'),stderr='',stderr_sha256=digest(b''),
        limitations=['Exit code não mede cobertura; contagens não fornecidas são desconhecidas.'],
        suites=None,cases=None,assertions=None,failed_assertions=None,
        fingerprint='f'*64,command=['MOCK','no-source-executed'],image_ids={'runner':'sha256:'+'1'*64},
        versions={'fixture':'synthetic-report-only'},started_at='2026-11-12T10:00:00+00:00',
        finished_at='2026-11-12T10:00:01+00:00',script_sha256=None,artifacts={})
    if findings:
        path=next(f['path'] for f in inventory if f['category']=='source')
        record=next(f for f in inventory if f['path']==path)
        report['findings']=[{'id':role+'-synthetic','source_id':manifest['source_id'],
            'production_observation':'unknown','refs':[{'path':path,'start':1,'end':record['lines'],'sha256':record['sha256']}],
            'evidence_ids':[],'proof_method':'static','mechanism':'MOCK individual finding'} for role in ('auditor','defensor')]
        report['verdicts']=[{'finding_id':f['id'],'classification':'falha comprovada','decision':'corrigir agora',
            'root_cause_id':None,'evidence_ids':[],'proof_method':'static'} for f in report['findings']]
        report['proven_causal_groups']=[{'member_ids':[f['id']],'proofs':[]} for f in report['findings']]
    else:
        report['findings']=[];report['verdicts']=[];report['proven_causal_groups']=[]
    report['judgment']['verdicts']=copy.deepcopy(report['verdicts'])
    return report


def requested_review(report):
    from audit3.explicit_review import review_template, seal_review
    review=review_template(report)
    review['reviewer']='MOCK local contract reviewer; no model or container run'
    review['scope'].update(production_occurrence_required=False,
        quantitative_measurement_required=False, secret_absence_certification_required=False,
        rationale='The exact objective limits this review to the frozen synthetic inventory and contract; production occurrence, numerical coverage and certification of absence of secrets are outside this objective.')
    for annotation in review['messages'].values():
        annotation['justification']={
            'inventory-reviewed': 'All listed synthetic files and hashes are within the examined snapshot; no omissions or blind investigation gaps remain. Heuristic scanner behaviour is not a missing code investigation.',
            'production-outside-objective': 'The stated objective concerns the local synthetic contract and expressly excludes production certification; no observed production event is asserted by any finding.',
            'executor-measurement': 'The source-bound receipt completed with no timeout or truncation. This objective does not require numerical coverage; unspecified counters remain unknown.',
        }[annotation['criterion']]
    return seal_review(review)


def test_explicit_php_review_can_conclude_outside_python_fixture():
    report=explicit_report('php')
    assessment=assess_completion(report,requested_review(report))
    assert assessment['status']=='completed', assessment['blockers']


def test_other_inventory_and_passed_baseline_can_conclude_without_findings():
    report=explicit_report('numeric',findings=False)
    assessment=assess_completion(report,requested_review(report))
    assert assessment['status']=='completed', assessment['blockers']


def test_automatic_python_policy_does_not_expand_to_other_inventory():
    report=explicit_report('php')
    automatic=make_review(report)
    assert not automatic['messages']
    assert assess_completion(report,automatic)['status']=='partial'


def test_php_individual_ids_do_not_require_python_certificates():
    from audit3.causality import causal_groups
    from test_assessment import OfflineEvidence
    report=explicit_report('php')
    before=copy.deepcopy(report)
    groups=causal_groups(report['findings'],report['verdicts'],OfflineEvidence(),
        lambda path:pytest.fail('A PHP individual finding must not invoke the Python expression verifier'))
    assert len(groups)==2 and all(not group['proofs'] for group in groups)
    assert {group['member_ids'][0] for group in groups}=={f['id'] for f in report['findings']}
    assert assess_completion(report,requested_review(report))['status']=='completed'
    assert report==before


def test_absent_or_draft_review_keeps_pendencies():
    from audit3.explicit_review import review_template
    report=explicit_report()
    assert assess_completion(report)['status']=='partial'
    result=assess_completion(report,review_template(report))
    assert result['status']=='partial'
    assert any(entry['kind']=='unresolved' for entry in result['limitations'])


@pytest.mark.parametrize('change',['evidence','objective','inventory','final','version'])
def test_explicit_review_rejects_stale_or_incompatible_context(change):
    report=explicit_report()
    review=requested_review(report)
    if change=='evidence':report['receipts'][0]['stdout']='different observations'
    if change=='objective':report['manifest']['requirements']='Certify production occurrence'
    if change=='inventory':report['manifest']['files'][0]['sha256']='0'*64
    if change=='final':report['judgment']['summary']='another final decision'
    if change=='version':
        review['version']='scoped-assessment-3'
        identify_review(review)
    with pytest.raises(PolicyError,match='objetivo/evidências'):
        assess_completion(report,review)


@pytest.mark.parametrize('omission',['reviewer','scope_basis','inventory_hash','justification','evidence','unsupported_criterion'])
def test_explicit_review_needs_more_than_text_and_existing_pointer(omission):
    report=explicit_report()
    review=requested_review(report)
    entry=next(iter(review['messages'].values()))
    if omission=='reviewer':review['reviewer']=''
    if omission=='scope_basis':review['scope']['rationale']=''
    if omission=='inventory_hash':review['scope']['inventory_hash']='wrong'
    if omission=='justification':entry['justification']=''
    if omission=='evidence':entry['evidence']=['/manifest/requirements']
    if omission=='unsupported_criterion':entry['criterion']='approve-anything'
    identify_review(review)
    result=assess_completion(report,review)
    assert result['status']=='partial'
    assert any(entry['kind']=='unresolved' for entry in result['limitations'])


@pytest.mark.parametrize('requirement',['production_occurrence_required','quantitative_measurement_required','secret_absence_certification_required'])
def test_required_information_cannot_be_waived_by_scope_statement(requirement):
    report=explicit_report()
    # Add the authentic controller measurement note so a quantitative objective
    # has a concrete unknown measurement to resolve, not a manufactured count.
    report['receipts'][0]['limitations']=['Exit code não mede cobertura; contagens não fornecidas são desconhecidas.']
    review=requested_review(report)
    review['scope'][requirement]=True
    identify_review(review)
    result=assess_completion(report,review)
    assert result['status']=='partial' and result['blockers']


def test_unknown_limitation_never_gets_an_automatic_annotation():
    report=explicit_report()
    report['judgment']['limitations']=['External contract necessary to the objective is unavailable.']
    review=requested_review(report)
    key=object_hash(report['judgment']['limitations'][0])
    assert key not in review['messages']
    assessment=assess_completion(report,review)
    assert assessment['status']=='partial'
    assert any(blocker.get('message_hash')==key for blocker in assessment['blockers'])


@pytest.mark.parametrize('failure',['blind','phase','judgment','consultation','source','isolation','causality','limits','uncontested'])
def test_explicit_review_never_waives_structural_failures(failure):
    report=explicit_report()
    if failure=='blind':report['coverage']['independent_investigation']['valid']=False
    if failure=='phase':report['state']['completed'].remove('juiz/review')
    if failure=='judgment':report['judgment']=None
    if failure=='consultation':report['structural_checks']['final_validation']=False
    if failure=='source':report['structural_checks']['source_integrity']=False
    if failure=='isolation':report['receipts'][0]['limitations']=['Isolation invariant was violated.']
    if failure=='causality':report['causal_validation']['valid']=False
    if failure=='limits':report['structural_checks']['limits_valid']=False
    if failure=='uncontested':report['judgment']['new_findings']=[{'id':'juiz-late'}]
    assessment=assess_completion(report,requested_review(report))
    assert assessment['status']=='partial' and assessment['blockers']


def test_explicit_completed_scope_does_not_turn_mock_into_real_acceptance():
    from audit3.acceptance import assert_scoped_completion
    report=explicit_report('numeric',findings=False)
    review=requested_review(report)
    report.update(completion_review=review,completion_assessment=assess_completion(report,review))
    assert report['completion_assessment']['status']=='completed'
    with pytest.raises(AssertionError,match='Backend mock'):
        assert_scoped_completion(report)


def test_passed_compose_baseline_is_allowed_by_general_acceptance_contract():
    from audit3.acceptance import assert_scoped_completion, assert_python_smoke_completion
    report=explicit_report('php',findings=False)
    # This is only a unit fixture of the real-runtime label. No inference occurs.
    report['state']['runtime_mode']='codex-app-server'
    report['runtime']['backend']='codex-app-server'
    review=requested_review(report)
    report.update(completion_review=review,completion_assessment=assess_completion(report,review))
    assert assert_scoped_completion(report)['status']=='passed'
    with pytest.raises(AssertionError,match='smoke Python'):
        assert_python_smoke_completion(report)


def test_known_defect_python_acceptance_still_requires_failed_baseline():
    from audit3.acceptance import assert_scoped_completion, assert_python_smoke_completion
    report=completion_fixture()
    report['receipts'][0].update(status='passed',exit_code=0)
    review=requested_review(report)
    report.update(completion_review=review,completion_assessment=assess_completion(report,review))
    assert assert_scoped_completion(report)['status']=='passed'
    with pytest.raises(AssertionError,match='falha esperada no baseline'):
        assert_python_smoke_completion(report)


def disk_snapshot(folder):
    return {str(p.relative_to(folder)):p.read_bytes() for p in folder.rglob('*') if p.is_file()}


def local_controller_run(make_run,monkeypatch):
    from audit3.config import Config
    from test_receipt_review import controller_run,SimulatedDocker
    store,manifest=make_run()
    config=Config.model_validate(store.get(manifest.run_id,'config'))
    return controller_run((store,manifest,config),monkeypatch,SimulatedDocker(exit_code=0))


def test_cli_explicit_review_and_export_leave_every_original_record_intact(make_run,monkeypatch,tmp_path,capsys):
    import json
    import zipfile
    from audit3.cli import main
    store,manifest,report,_=local_controller_run(make_run,monkeypatch)
    before=disk_snapshot(store.root)
    base=['--store',str(store.root),'review-completion',manifest.run_id]
    template=tmp_path/'review-template.json'
    assert main([*base,'--template','--output',str(template)])==0
    draft=json.loads(template.read_text())
    assert draft['draft'] is True and draft['reviewer']==''
    assert draft['scope']['objective']==manifest.requirements
    # Completing the operator draft is explicit; auto Python policy cannot do it.
    review=requested_review(report)
    template.write_text(json.dumps(review))
    result_file=tmp_path/'separate-evaluation.json'
    archive=tmp_path/'separate-evaluation.zip'
    assert main([*base,'--review',str(template),'--output',str(result_file),'--export',str(archive)])==0
    result=json.loads(result_file.read_text())
    assert result['completion_assessment']['status']=='completed'
    assert result['raw_state']['status']=='partial' and result['raw_state']['runtime_mode']=='mock'
    assert result['acceptance']['status']=='not_evaluated'
    with zipfile.ZipFile(archive) as z:
        exported=json.loads(z.read('report.json'))
        assert exported['completion_assessment']['status']=='completed'
        assert exported['state']==report['state']
        assert exported['judgment']==report['judgment'] and exported['opinions']==report['opinions']
        assert exported['receipts']==report['receipts']
        assert exported['acceptance']['status']=='not_evaluated'
        assert all(exported['metrics'][key] is None for key in ('suites','cases','assertions','failed_assertions'))
    assert disk_snapshot(store.root)==before
    # A prior evaluation envelope can be supplied, without altering the originals.
    assert main([*base,'--review',str(result_file),'--output',str(tmp_path/'second-evaluation.json')])==0
    bytes_before=result_file.read_bytes()
    assert main([*base,'--review',str(template),'--output',str(result_file)])==2
    assert result_file.read_bytes()==bytes_before and disk_snapshot(store.root)==before
    capsys.readouterr()


def test_plain_export_uses_readonly_store_and_preserves_existing_reports(make_run,monkeypatch,tmp_path,capsys):
    from audit3.cli import main
    store,manifest,_,_=local_controller_run(make_run,monkeypatch)
    # Existing generated reports are historical bytes, not targets for export.
    for name in ('report.json','report.md','coverage.json'):
        store.path(manifest.run_id,name).write_text('historical opaque content '+name)
    before=disk_snapshot(store.root)
    archive=tmp_path/'plain.zip'
    assert main(['--store',str(store.root),'export',manifest.run_id,'--output',str(archive)])==0
    assert archive.exists() and disk_snapshot(store.root)==before
    capsys.readouterr()


@pytest.mark.parametrize('invalid',['review_inside_store','export_inside_store','template_export','stale_review'])
def test_cli_rejects_unsafe_or_stale_output_without_rewriting_history(make_run,monkeypatch,tmp_path,capsys,invalid):
    import json
    from audit3.cli import main
    store,manifest,report,_=local_controller_run(make_run,monkeypatch)
    before=disk_snapshot(store.root)
    base=['--store',str(store.root),'review-completion',manifest.run_id]
    review=requested_review(report)
    path=tmp_path/'review.json'
    if invalid=='stale_review':
        review['context_hash']='wrong-context'
        identify_review(review)
    path.write_text(json.dumps(review))
    output=tmp_path/'evaluation.json'
    args=[*base,'--review',str(path),'--output',str(output)]
    if invalid=='review_inside_store':args=[*base,'--review',str(path),'--output',str(store.root/'forbidden.json')]
    if invalid=='export_inside_store':args+=['--export',str(store.root/'forbidden.zip')]
    if invalid=='template_export':args=[*base,'--template','--output',str(output),'--export',str(tmp_path/'draft.zip')]
    assert main(args)==2
    result=json.loads(capsys.readouterr().out)
    assert 'error' in result
    assert disk_snapshot(store.root)==before
    assert not (store.root/'forbidden.json').exists() and not (store.root/'forbidden.zip').exists()


def test_live_artifact_path_contract_preserves_preacceptance_archive(tmp_path,monkeypatch):
    """Only artifact naming is exercised; no live process/runtime is invoked."""
    from types import SimpleNamespace
    import integration_support
    report={'acceptance':{'status':'not_evaluated'},'fixture':'MOCK path contract'}
    store=SimpleNamespace(root=tmp_path/'unused-store',names=lambda run,namespace:[],
                          get=lambda run,name:{'calls':[]} if name=='ledger' else {})
    manifest=SimpleNamespace(run_id='a'*24)
    monkeypatch.setattr(integration_support,'write_report',lambda store,run:copy.deepcopy(report))
    monkeypatch.setattr(integration_support,'artifacts_path',lambda name:tmp_path/name)
    exported=[]
    def export(store,run,path):
        with path.open('xb') as target:
            target.write(b'MOCK archive path contract; not a real audit')
        exported.append(path.name)
    monkeypatch.setattr(integration_support,'export_zip',export)
    integration_support.save_live_artifacts(store,manifest)
    before=(tmp_path/'three-agents.zip').read_bytes()
    report['acceptance']['status']='passed'
    integration_support.save_live_artifacts(store,manifest)
    assert exported==['three-agents.zip','three-agents-accepted.zip']
    assert (tmp_path/'three-agents.zip').read_bytes()==before
