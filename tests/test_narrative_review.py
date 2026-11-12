"""Offline MOCK evidence contracts with verbatim synthetic-run narrative examples."""
import copy
from pathlib import Path
import pytest
from audit3.completion import assess_completion, context_hash, limitation_messages
from audit3.explicit_review import seal_review
from audit3.narrative_review import POLICY, REQUIRED_CHECKS, aggregate
from audit3.security import object_hash, PolicyError
from test_explicit_review import explicit_report, requested_review

REAL_NOTES = [
    'Nenhuma correção foi aplicada ou testada.',
    'As execuções são do snapshot original; não demonstram uma versão corrigida.',
    'O baseline usa rest_do_request e wp_set_current_user; não verifica autenticação HTTP ponta a ponta.',
    'A função apenas retorna um valor; não há persistência de estoque demonstrada no snapshot.',
    'Os exemplos não representam cobertura exaustiva.',
    'Parecer cego: nenhum argumento de outro papel foi consultado.',
    'Sem certificado causal PHP: os IDs permanecem separados, sem fusão ou contagem de defeitos independentes.',
]


def pieces(text, fragments):
    assert ''.join(fragments) == text
    cursor = 0
    result = []
    for fragment in fragments:
        result.append({'start': cursor, 'end': cursor+len(fragment), 'text': fragment})
        cursor += len(fragment)
    return result


def narrative_fixture(text=REAL_NOTES[0], fragments=None, kind='procedure_note'):
    report = explicit_report('php')
    report['judgment']['limitations'] = [text]
    review = requested_review(report)
    review['narrative_policy'] = POLICY
    objective = report['manifest']['requirements']
    review['narrative_requirements'] = [{**pieces(objective, [objective])[0], 'id': 'R0',
        'interpretation': 'MOCK reviewer: inspect this frozen synthetic contract; no remediation or production certification.'}]
    source = Path(__file__).parent/'fixtures/wordpress-stock'
    review['evidence_bundle'] = {'sources': {str(p.relative_to(source)): p.read_text()
        for p in source.rglob('*') if p.is_file()}, 'tests': {}}
    fact = {'domain':'source','key':'inventory.php','op':'contains','expected':'return $stock + $quantity;'}
    review['scope_boundaries'] = {'snapshot': {'requirement_ids':['R0'],
        'interpretation':'MOCK semantic scope decision: verify the original function, do not certify a repaired or persistent external system.',
        'semantic_responsibility':'reviewer','facts':[fact]}}
    key=object_hash(text);message=limitation_messages(report)[key]
    claims=[]
    for span in pieces(text, fragments or [text]):
        claims.append({**span, 'kind':kind,'requirement_ids':['R0'],
            'interpretation':'MOCK reviewer examined this assertion against the original objective and source; no required obligation is waived.',
            'semantic_responsibility':'reviewer','boundary_id':'snapshot' if kind=='scope_note' else None,
            'checks':sorted(REQUIRED_CHECKS),
            'facts':[fact, {'domain':'report','reference':'/structural_checks/source_integrity','op':'equals','expected':True}]})
    review['messages'][key]={'policy':POLICY,'criterion':'reviewed-claims','kind':aggregate(claims),
        'justification':'MOCK explicit review of the actual assertion, without interpreting example outputs as exhaustive coverage.',
        'original_text':text,'original_hash':key,'origins':message['origins'],
        'requirements_hash':object_hash(review['narrative_requirements']),'claims':claims,
        'evidence':['/structural_checks/source_integrity']}
    return report,seal_review(review),key


@pytest.mark.parametrize('text', REAL_NOTES)
def test_actual_narrative_wordings_can_be_reviewed_without_phrase_allowlist(text):
    report,review,key=narrative_fixture(text)
    # These are case-specific reviewer decisions, not phrases recognized by the
    # implementation. Each example uses evidence pertinent to its own claim.
    def source(path, snippet):
        return {'domain':'source','key':path,'op':'contains','expected':snippet}
    def fact(reference, expected):
        return {'domain':'report','reference':reference,'op':'equals','expected':expected}
    cases = {
        REAL_NOTES[0]: ([source('inventory.php','return $stock + $quantity;')], [],
            'The preserved function still adds; this audit objective does not ask to implement or certify a repair.'),
        REAL_NOTES[1]: ([source('inventory.php','return $stock + $quantity;')], [],
            'The original addition remains in the hashed source; no repaired version is asserted by this review.'),
        REAL_NOTES[2]: ([source('tests/run.php','rest_do_request'),source('tests/run.php','wp_set_current_user')], [],
            'The internal REST dispatch verifies plugin capabilities; it does not certify core HTTP login, which is outside this snapshot objective.'),
        REAL_NOTES[3]: ([source('inventory.php','return $stock + $quantity;'),
                        source('synthetic-plugin.php',"return ['synthetic' => true, 'stock' => 10]")], [],
            'Both complete hashed functions return values without persistence; this objective examines that return contract, not an absent consumer.'),
        REAL_NOTES[4]: ([fact('/receipts/0/cases',None)], [],
            'The valid receipt does not supply a quantitative case count. This objective does not require exhaustive or quantitative coverage.'),
        REAL_NOTES[5]: ([fact('/coverage/independent_investigation/valid',True)], ['initial_investigation'],
            'The authenticated blind investigation assessment, not the model statement, supports independence before the barrier.'),
        REAL_NOTES[6]: ([fact('/judgment/verdicts',report['judgment']['verdicts'])], ['causal_separation'],
            'Each verdict retains its own ID and null root; the preserved judgments make no certified PHP merge.'),
    }
    facts,checks,meaning=cases[text]
    claim=review['messages'][key]['claims'][0]
    claim.update(facts=facts,checks=sorted(REQUIRED_CHECKS|set(checks)),interpretation=meaning)
    review['messages'][key]['evidence']=sorted({f['reference'] for f in facts if f['domain']=='report'}
        | {'/structural_checks/source_integrity'})
    claim['facts'].append(fact('/structural_checks/source_integrity',True))
    review=seal_review(review)
    before=copy.deepcopy(report)
    result=assess_completion(report,review)
    assert result['status']=='completed',result['blockers']
    assert next(e for e in result['limitations'] if e['message_hash']==key)['text']==text
    assert report==before


def test_outside_scope_decision_needs_current_scope_boundary_and_evidence():
    report,review,key=narrative_fixture(REAL_NOTES[3],kind='scope_note')
    assert assess_completion(report,review)['status']=='completed'
    review['scope_boundaries'].clear()
    result=assess_completion(report,seal_review(review))
    assert result['status']=='partial' and any(b.get('message_hash')==key for b in result['blockers'])


@pytest.mark.parametrize('failure',['blind','phase','consultation','judgment','source','limits','isolation','uncontested'])
def test_similar_read_completion_phrase_cannot_hide_real_obligation(failure):
    report,review,key=narrative_fixture('Nenhum intervalo ficou sem leitura; uma fase obrigatória está pendente.')
    if failure=='blind':report['coverage']['independent_investigation']['valid']=False
    if failure=='phase':report['state']['completed'].remove('juiz/review')
    if failure=='consultation':report['structural_checks']['final_validation']=False
    if failure=='judgment':
        text=report['judgment']['limitations'][0]
        report['judgment']=None
        report['opinions']['juiz'][0]['output']['limitations']=[text]
        review['messages'][key]['origins']=limitation_messages(report)[key]['origins']
    if failure=='source':report['structural_checks']['source_integrity']=False
    if failure=='limits':report['structural_checks']['limits_valid']=False
    if failure=='isolation':report['structural_checks']['isolation_valid']=False
    if failure=='uncontested':report['judgment']['new_findings']=[{'id':'late'}]
    review['context_hash']=context_hash(report)
    result=assess_completion(report,seal_review(review))
    assert result['status']=='partial' and result['blockers']


@pytest.mark.parametrize('failure',['absent','contradictory','changed_source','pointer_only','model_prose','changed_script'])
def test_evidence_presence_does_not_replace_factual_support(failure):
    report,review,key=narrative_fixture()
    claim=review['messages'][key]['claims'][0]
    if failure=='absent':claim['facts'][0]['key']='not-recorded.php'
    if failure=='contradictory':claim['facts'][0]['expected']='return $stock - $quantity;'
    if failure=='changed_source':review['evidence_bundle']['sources']['inventory.php']+='// changed'
    if failure=='pointer_only':claim['facts']=[{'domain':'report','reference':'/structural_checks/source_integrity','op':'equals','expected':True}]
    if failure=='model_prose':claim['facts']=[{'domain':'report','reference':'/judgment/summary','op':'equals','expected':report['judgment'].get('summary')}]
    if failure=='changed_script':review['evidence_bundle']['tests']['not-recorded-receipt']='made up script'
    result=assess_completion(report,seal_review(review))
    assert result['status']=='partial'
    assert any(e['message_hash']==key and e['kind']=='unresolved' for e in result['limitations'])


def test_mixed_claims_are_all_covered_and_blocking_part_dominates():
    text='Leitura integral concluída; uma evidência necessária não foi consultada.'
    report,review,key=narrative_fixture(text,['Leitura integral concluída; ','uma evidência necessária não foi consultada.'])
    annotation=review['messages'][key]
    annotation['claims'][1]['kind']='unresolved'
    annotation['claims'][1]['interpretation']='MOCK: do not waive the missing evidence named in the second part.'
    annotation['kind']='unresolved'
    assert assess_completion(report,seal_review(review))['status']=='partial'
    annotation['kind']='procedure_note'
    assert assess_completion(report,seal_review(review))['status']=='partial'
    annotation['claims'].pop()
    assert assess_completion(report,seal_review(review))['status']=='partial'


@pytest.mark.parametrize('failure',['timeout','truncated','missing','stream_hash','wrong_run','wrong_source','exit_status'])
def test_review_cannot_discharge_receipt_failure_even_with_plausible_scope_text(failure):
    report,review,key=narrative_fixture(REAL_NOTES[0])
    receipt=report['receipts'][0]
    if failure=='timeout':receipt['timeout']=True
    if failure=='truncated':receipt['output_truncated']=True
    if failure=='missing':
        report['receipts']=[]
        review['messages']={k:v for k,v in review['messages'].items() if k in limitation_messages(report)}
    if failure=='stream_hash':receipt['stdout']='an observation changed'
    if failure=='wrong_run':receipt['run_id']='b'*24
    if failure=='wrong_source':receipt['source_id']='another snapshot'
    if failure=='exit_status':receipt['exit_code']=1
    # A new review of this changed evidence still must not waive its defect.
    review['context_hash']=context_hash(report)
    result=assess_completion(report,seal_review(review))
    assert result['status']=='partial'
    assert any(e['message_hash']==key and e['kind']=='unresolved' for e in result['limitations'])


@pytest.mark.parametrize('field',['original_hash','origins','requirements_hash','semantic_responsibility','objective_part','receipt_origin'])
def test_message_objective_provenance_and_semantic_responsibility_are_bound(field):
    report,review,key=narrative_fixture()
    ann=review['messages'][key]
    if field=='original_hash':ann['original_hash']='wrong'
    if field=='origins':ann['origins']=['/state/limitations/0']
    if field=='requirements_hash':ann['requirements_hash']='wrong'
    if field=='semantic_responsibility':ann['claims'][0]['semantic_responsibility']='automatic'
    if field=='objective_part':review['narrative_requirements'][0]['end']-=1
    if field=='receipt_origin':
        report['receipts'][0]['limitations'].append(ann['original_text'])
        ann['origins']=limitation_messages(report)[key]['origins']
        review['context_hash']=context_hash(report)
    assert assess_completion(report,seal_review(review))['status']=='partial'


def test_stale_review_is_rejected_even_when_its_justification_still_sounds_true():
    report,review,_=narrative_fixture()
    report['receipts'][0]['stdout']='new evidence'
    with pytest.raises(PolicyError,match='objetivo/evidências'):
        assess_completion(report,review)


def test_narrative_review_does_not_enable_automatic_classification_or_real_mock_acceptance():
    from audit3.scope_review import make_review
    from audit3.acceptance import assert_scoped_completion
    report,review,key=narrative_fixture()
    assert key not in make_review(report)['messages']
    report.update(completion_review=review,completion_assessment=assess_completion(report,review))
    with pytest.raises(AssertionError,match='Backend mock'):
        assert_scoped_completion(report)
