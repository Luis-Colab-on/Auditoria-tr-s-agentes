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
