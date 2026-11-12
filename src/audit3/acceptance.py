"""Acceptance counts demonstrated causes while preserving one verdict per ID."""
from .completion import VERSION


def assert_known_cause(report, expected_ref, decision='corrigir agora'):
    assert report['causal_validation']['version'] == VERSION
    assert report['causal_validation']['valid'], report['causal_validation']['gaps']
    findings = {f['id']: f for f in report['findings']}
    verdicts = report['verdicts']
    assert len(verdicts) == len(findings)
    assert {v['finding_id'] for v in verdicts} == set(findings)
    proven = {v['finding_id']: v for v in verdicts if v['classification'] == 'falha comprovada'}
    groups = report['proven_causal_groups']
    assert len(groups) == 1, 'O cenário exige uma causa comprovada, preservando os IDs.'
    members = groups[0]['member_ids']
    assert len(set(members)) == len(members) and set(members) == set(proven)
    assert len(members) == 1 or len(groups[0]['proofs']) == len(members), 'Equivalência causal sem prova para cada ID'
    for fid in members:
        assert proven[fid]['decision'] == decision
        assert any(ref['path'] == expected_ref['path'] and ref['start'] <= expected_ref['start']
                   and ref['end'] >= expected_ref['end'] for ref in findings[fid]['refs'])
    assert not any(v['classification'] in {'falha comprovada', 'risco fundamentado'}
                   for v in verdicts if v['finding_id'] not in members), 'Caso de controle elevado a falha/risco'
    return {'cause_count': 1, 'preserved_finding_ids': members}


def assert_scoped_completion(report):
    """Partial is acceptable only through a current, verified scope review."""
    from .completion import assess_completion
    from .security import PolicyError
    try:
        state = report['state']
        assert state['phase'] == 'done', 'Protocolo interrompido'
        assert state['status'] in {'completed', 'partial'}, 'Estado operacional bloqueante'
        if state['status'] == 'partial':
            assert report.get('completion_review'), 'Revisão de conclusão pendente'
        assessment = assess_completion(report, report.get('completion_review'))
        assert assessment == report['completion_assessment'], 'Conclusão divergente do contexto atual'
        assert assessment['status'] == 'completed', assessment['blockers']
        assert not assessment['blockers'], assessment['blockers']
        assert report['coverage']['independent_investigation']['valid'], 'Investigação cega incompleta'
        assert report['causal_validation']['valid'], report['causal_validation']['gaps']
        assert state['runtime_mode'] == 'codex-app-server', 'Backend mock/antigo não aceito'
        assert report['manifest']['backend'] == 'codex-app-server', 'Backend incompatível'
        baseline = [r for r in report['receipts'] if r['owner'] == 'baseline']
        assert baseline and all(r['execution'] == 'docker' and r['status'] == 'failed'
            and not r.get('timeout') and not r.get('output_truncated') for r in baseline), 'Baseline não executado/válido'
    except (KeyError, TypeError) as exc:
        raise AssertionError('Relatório malformado para aceitação: ' + str(exc)) from exc
    except PolicyError as exc:
        raise AssertionError('Revisão inválida: ' + str(exc)) from exc
    return {'status': 'passed', 'raw_status': state['status'], 'review_id': assessment['review_id']}
