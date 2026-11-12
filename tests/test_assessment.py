"""Offline protocol fixtures. No model, container or audited source is executed."""
import copy
import pytest
from audit3.causality import causal_groups, PROOF_VERSION
from audit3.completion import assess_completion, context_hash, limitation_messages, VERSION
from audit3.acceptance import assert_known_cause
from audit3.security import PolicyError, digest, object_hash


class OfflineEvidence:
    def __init__(self):
        self.bundles = {}
        self.consulted = set()

    def require_evidence_consulted(self, eid):
        if eid not in self.consulted:
            raise PolicyError('Evidence not consulted')

    def read_evidence(self, eid, record_access=False):
        if eid not in self.bundles:
            raise PolicyError('Evidence missing')
        return self.bundles[eid]


def fixture_member(tools, source, fid, eid, arguments, expected, observed,
                   controls, operation_path, replacement, precondition, mechanism='wording'):
    # Explicitly synthetic copies of the recorded-receipt contract, not executions.
    source_hash = digest(source)
    script = ('from unit_module import transform\nimport unittest\nclass Checks(unittest.TestCase):\n'
              f'    def test_failure(self):\n        self.assertEqual(transform({", ".join(map(repr,arguments))}), {expected!r})\n'
              f'    def test_control(self):\n        self.assertEqual(transform({", ".join(map(repr,controls[0]))}), {controls[1]!r})\n')
    stderr = (f'test_failure (unit.Checks.test_failure) ... FAIL\ntest_control (unit.Checks.test_control) ... ok\n'
              f'FAIL: test_failure (unit.Checks.test_failure)\n  File "/test/repro.py", line 5, in test_failure\n'
              f'AssertionError: {observed} != {expected}\n')
    receipt = {'id':eid,'execution':'docker','status':'failed','timeout':False,'output_truncated':False,
        'source_id':'unit-source','script_sha256':digest(script.encode()),'stdout':'','stdout_sha256':digest(b''),
        'stderr':stderr,'stderr_sha256':digest(stderr.encode())}
    tools.bundles[eid]={'receipt':receipt,'test':{'script':script}}
    tools.consulted.add(eid)
    ref={'path':'unit_module.py','start':1,'end':2,'sha256':source_hash}
    finding={'id':fid,'source_id':'unit-source','refs':[ref],'evidence_ids':[eid],'mechanism':mechanism}
    proof={'version':PROOF_VERSION,'finding_id':fid,'finding_hash':object_hash(finding),'ref':ref,
        'function':'transform','operation_path':operation_path,'replacement':replacement,'precondition':precondition,
        'witnesses':[{'evidence_id':eid,'method':'test_failure','line':5}],
        'controls':[{'evidence_id':eid,'method':'test_control','line':7}],
        'justification':'Reviewed original operation, contract assertion, observed failure and preserved control.'}
    verdict={'finding_id':fid,'classification':'falha comprovada','decision':'corrigir agora',
        'root_cause_id':None,'evidence_ids':[eid]}
    return finding,proof,verdict


def equivalent_members():
    source=b'def transform(base, value):\n    return base - abs(value)\n'
    tools=OfflineEvidence()
    members=[fixture_member(tools,source,'left','1'*24,[100,-20],120,80,([100,20],80),['right'],'value','value < 0','first description'),
             fixture_member(tools,source,'right','2'*24,[250,-35],285,215,([250,35],215),['right'],'value','value < 0','different description')]
    return source,tools,members


@pytest.mark.parametrize('proposed',[False,True])
def test_evidence_groups_different_wording_without_changing_ids_or_verdicts(proposed):
    source,tools,members=equivalent_members()
    findings,proofs,verdicts=map(list,zip(*members))
    if proposed:
        for verdict in verdicts:verdict['root_cause_id']='shared-label'
    before=copy.deepcopy(verdicts)
    groups=causal_groups(findings,verdicts,tools,lambda path:source,proofs)
    assert len(groups)==1 and set(groups[0]['member_ids'])=={'left','right'}
    assert len(groups[0]['proofs'])==2 and verdicts==before


def test_shared_label_location_and_similar_text_do_not_merge_distinct_operations():
    source=b'def transform(x, y):\n    return abs(x) + abs(y)\n'
    tools=OfflineEvidence()
    members=[fixture_member(tools,source,'x-fault','3'*24,[-2,0],-2,2,([1,1],2),['left'],'x','x < 0','identical description'),
             fixture_member(tools,source,'y-fault','4'*24,[0,-3],-3,3,([1,1],2),['right'],'y','y < 0','identical description')]
    findings,proofs,verdicts=map(list,zip(*members))
    groups=causal_groups(findings,verdicts,tools,lambda path:source,proofs)
    assert len(groups)==2  # Same function/span and wording; distinct causal nodes.
    for verdict in verdicts:verdict['root_cause_id']='one-unsupported-label'
    with pytest.raises(PolicyError,match='sem prova equivalente'):
        causal_groups(findings,verdicts,tools,lambda path:source,proofs)


def test_grouping_without_evidence_remains_unconfirmed():
    source,tools,members=equivalent_members();findings,proofs,verdicts=map(list,zip(*members))
    assert len(causal_groups(findings,verdicts,tools,lambda path:source))==2
    for verdict in verdicts:verdict['root_cause_id']='shared'
    with pytest.raises(PolicyError,match='sem prova equivalente'):
        causal_groups(findings,verdicts,tools,lambda path:source)


@pytest.mark.parametrize('failure',['hash','missing','unconsulted','witness','control','source','replacement'])
def test_invalid_causal_proofs_are_never_used(failure):
    source,tools,members=equivalent_members();findings,proofs,verdicts=map(list,zip(*members))
    if failure=='hash':proofs[0]['finding_hash']='wrong'
    elif failure=='missing':tools.bundles.clear()
    elif failure=='unconsulted':tools.consulted.clear()
    elif failure=='witness':proofs[0]['witnesses'][0]['line']=999
    elif failure=='control':proofs[0]['controls'][0]['line']=5
    elif failure=='source':source=b'def transform(x, y):\n    return x+y\n'
    else:proofs[0]['replacement']='0'
    with pytest.raises(PolicyError):causal_groups(findings,verdicts,tools,lambda path:source,proofs)


def completion_fixture():
    """Complete MOCK report contract for the packaged synthetic review policy.

    This fixture exercises report assessment only; flags and receipt copies are
    synthetic assertions supplied to the unit under test, never real run evidence.
    """
    from audit3.scope_review import policy, NOTES
    catalog = policy()
    phases=['auditor/initial-0000','defensor/initial-0000','juiz/blind','auditor/contest',
            'defensor/contest','auditor/reply','defensor/reply','juiz/review','juiz/final']
    manifest = {'requirements': catalog['objective'], 'run_id': 'a' * 24, 'source_id': 'MOCK-source',
        'backend': 'codex-app-server', 'limitations': [note[0] for note in NOTES.values()],
        'files': [{'path': path, 'sha256': sha, 'category': 'source'} for path, sha in catalog['files'].items()]}
    verdict = {'finding_id': 'auditor-synthetic', 'classification': 'falha comprovada',
               'decision': 'corrigir agora', 'root_cause_id': None, 'evidence_ids': ['b' * 24]}
    finding = {'id': 'auditor-synthetic', 'source_id': manifest['source_id'], 'production_observation': 'unknown',
               'refs': [{'path': 'app.py', 'start': 1, 'end': 6, 'sha256': catalog['files']['app.py']}]}
    report={'manifest': manifest, 'coverage': {'gaps': [],
            'independent_investigation': {'valid': True, 'version': 'blind-investigation-1', 'gaps': []}},
        'opinions':{role:[{'phase':phase.split('/')[1],'output':{'limitations':[]}}
                         for phase in phases if phase.startswith(role+'/')]
                    for role in ('auditor','defensor','juiz')},
        'judgment':{'new_findings':[], 'limitations': [],
            'baseline_assessment': 'MOCK: failed signed refund expectation in the synthetic fixture; no production claim.',
            'verdicts': [copy.deepcopy(verdict)]},
        'state': {'completed': phases, 'phase': 'done', 'status': 'partial', 'runtime_mode': 'codex-app-server'},
        'structural_checks': {'source_integrity': True, 'final_validation': True, 'limits_valid': True},
        'causal_validation': {'valid': True, 'gaps': [], 'version': VERSION},
        'findings': [finding], 'verdicts': [verdict], 'required_phases': phases.copy(),
        'proven_causal_groups': [{'member_ids': [finding['id']], 'proofs': []}],
        'receipts': [{'id': 'b' * 24, 'owner': 'baseline', 'execution': 'docker', 'status': 'failed',
            'timeout': False, 'output_truncated': False, 'run_id': manifest['run_id'],
            'source_id': manifest['source_id'], 'purpose': 'MOCK receipt contract; no execution',
            'stdout': '', 'stderr': 'MOCK failure transcript'}],
        'usage': {'calls': [], 'tokens': None, 'known_cost_usd': None},
        'runtime': {'backend': 'codex-app-server', 'fixture_only': True}}
    return report


def scoped_review(report):
    from audit3.scope_review import make_review
    return make_review(report)


def identify_review(review):
    """Re-sign a deliberate test edit so its substantive validation is exercised."""
    review['id'] = object_hash({key: value for key, value in review.items() if key != 'id'})
    return review


def test_completed_means_concluded_scope_even_with_a_proven_defect():
    report=completion_fixture();assessment=assess_completion(report,scoped_review(report))
    assert assessment['status']=='completed' and len(assessment['limitations'])==2
    assert report['judgment']['verdicts'][0]['classification']=='falha comprovada'


@pytest.mark.parametrize('failure',['coverage','pending','unknown','new_finding','review_context','bad_evidence'])
def test_real_gaps_and_unexplained_limits_cannot_be_waived(failure):
    report=completion_fixture()
    if failure=='coverage':report['coverage']['gaps']=['Required source was not inspected']
    if failure=='pending':report['state']['completed'].remove('juiz/review')
    if failure=='new_finding':report['judgment']['new_findings']=[{'id':'uncontested'}]
    review=scoped_review(report)
    if failure=='unknown':
        report['judgment']['limitations'].append('Required data unavailable; impact unresolved.')
        review['context_hash']=context_hash(report)
    if failure=='review_context':review['context_hash']='wrong'
    if failure=='bad_evidence':next(iter(review['messages'].values()))['evidence']=['/missing']
    identify_review(review)
    if failure in ('review_context','bad_evidence'):
        with pytest.raises(PolicyError):assess_completion(report,review)
    else:
        result=assess_completion(report,review)
        assert result['status']=='partial' and result['blockers']


def test_unreviewed_notes_block_by_default():
    assert assess_completion(completion_fixture())['status']=='partial'


def test_review_cannot_replace_original_message_or_its_provenance():
    report=completion_fixture();review=scoped_review(report)
    next(iter(review['messages'].values()))['text']='silently replaced'
    identify_review(review)
    with pytest.raises(PolicyError, match='sem justificativa/evidência'):assess_completion(report,review)


def test_completed_marker_without_saved_phase_is_not_completion():
    report=completion_fixture()
    report['opinions']['juiz']=[r for r in report['opinions']['juiz'] if r['phase']!='review']
    result=assess_completion(report,scoped_review(report))
    assert result['status']=='partial'
    assert any(b['text']=='juiz/review' for b in result['blockers'])


def test_pending_additional_batch_and_round_are_not_inferred_from_existing_outputs():
    report=completion_fixture()
    report['required_phases']=report['state']['completed']+['auditor/initial-0001','defensor/extra-reply']
    result=assess_completion(report,scoped_review(report))
    assert result['status']=='partial'
    assert {item['text'] for item in result['blockers'] if item['kind']=='pending_phase'}=={
        'auditor/initial-0001','defensor/extra-reply'}


def test_acceptance_preserves_ids_and_counts_verified_causes():
    source,tools,members=equivalent_members();findings,proofs,verdicts=map(list,zip(*members))
    report={'findings':findings,'verdicts':verdicts,'causal_validation':{'version':VERSION,'valid':True},
        'proven_causal_groups':causal_groups(findings,verdicts,tools,lambda path:source,proofs)}
    assert assert_known_cause(report,{'path':'unit_module.py','start':2,'end':2})['cause_count']==1
    report['verdicts']=verdicts[:1]
    with pytest.raises(AssertionError):assert_known_cause(report,{'path':'unit_module.py','start':2,'end':2})


def test_two_distinct_causes_fail_single_cause_acceptance():
    report={'findings':[{'id':'a'},{'id':'b'}],'verdicts':[{'finding_id':'a','classification':'falha comprovada'},
        {'finding_id':'b','classification':'falha comprovada'}], 'causal_validation':{'version':VERSION,'valid':True},
        'proven_causal_groups':[{'member_ids':['a']},{'member_ids':['b']}]}
    with pytest.raises(AssertionError,match='uma causa'):
        assert_known_cause(report,{'path':'any.py','start':1,'end':1})


def test_control_case_cannot_be_promoted_to_a_risk():
    source,tools,members=equivalent_members();findings,proofs,verdicts=map(list,zip(*members))
    groups=causal_groups(findings,verdicts,tools,lambda path:source,proofs)
    findings.append({'id':'protected-control','refs':[{'path':'other.py','start':10,'end':10}]})
    verdicts.append({'finding_id':'protected-control','classification':'risco fundamentado',
        'decision':'programar correção','root_cause_id':None,'evidence_ids':[]})
    report={'findings':findings,'verdicts':verdicts,'causal_validation':{'version':VERSION,'valid':True},
        'proven_causal_groups':groups}
    with pytest.raises(AssertionError,match='Caso de controle'):
        assert_known_cause(report,{'path':'unit_module.py','start':2,'end':2})
