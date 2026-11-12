"""Narrow, offline review of the published synthetic smoke's preparation notes.

A pointer alone cannot discharge a limitation. These criteria bind the exact
synthetic inventory, objective and final evidence. Unknown messages stay pending.
"""
import json
from importlib.resources import files
from .security import object_hash, PolicyError

POLICY = 'python-smoke-v1'
NOTES = {
    'synthetic-inventory': ('Scanner de segredos/PII é heurístico: revisar inventário antes do run; omissões reduzem cobertura.',
        'procedure_note', 'Inventário integral corresponde por SHA-256 à fixture sintética publicada e revisada; nenhum arquivo foi omitido. O scanner continua heurístico.'),
    'synthetic-production': ('Nenhuma ocorrência em produção fornecida.', 'scope_note',
        'O objetivo é testar a integração nesta fixture sintética. Os casos e o julgamento não demonstram ocorrência em produção; essa ausência não impede concluir esse objetivo restrito.'),
}


def policy():
    return json.loads(files('audit3').joinpath('assets/smoke-review-policy.json').read_text())[POLICY]


def supporting_evidence(report, criterion):
    expected = policy()
    manifest = report['manifest']
    inventory = manifest.get('files', [])
    if (manifest.get('requirements') != expected['objective']
        or {f['path']: f['sha256'] for f in inventory} != expected['files']
        or len(inventory) != len(expected['files'])
        or any(f['category'] in {'excluded', 'prior_report'} for f in inventory)
        or report.get('structural_checks', {}).get('source_integrity') is not True):
        raise PolicyError('Critério sintético não corresponde ao objetivo/inventário íntegro')
    if not report.get('judgment') or not report['judgment'].get('baseline_assessment'):
        raise PolicyError('Critério requer julgamento final com avaliação do baseline')
    if any(f.get('production_observation') == 'observed_with_evidence' for f in report.get('findings', [])):
        raise PolicyError('Alegação de produção excede o critério sintético')
    receipts = report.get('receipts', [])
    if not any(r.get('owner') == 'baseline' and r.get('execution') in {'docker', 'compose'}
               and r.get('status') == 'failed' and not r.get('timeout')
               and not r.get('output_truncated') and r.get('source_id') == manifest.get('source_id')
               and r.get('run_id') == manifest.get('run_id') for r in receipts):
        raise PolicyError('Critério requer baseline factual íntegro da mesma fonte/run')
    if criterion not in NOTES:
        raise PolicyError('Critério de revisão desconhecido')
    return ['/manifest/requirements', '/manifest/files', '/structural_checks/source_integrity',
            '/judgment', '/receipts', '/findings']


def validate_annotation(report, message, annotation):
    criterion = annotation.get('criterion')
    if criterion not in NOTES or annotation.get('policy') != POLICY:
        raise PolicyError('Classificação sem critério verificável suportado')
    text, kind, _ = NOTES[criterion]
    if (message['text'] != text or annotation['kind'] != kind
        or (not any(origin.startswith('/manifest/limitations/') for origin in message['origins'])
            or any(not origin.startswith(('/manifest/limitations/', '/state/limitations/')) for origin in message['origins']))):
        raise PolicyError('Mensagem/proveniência fora do critério de preparação')
    refs = supporting_evidence(report, criterion)
    if annotation['evidence'] != refs:
        raise PolicyError('Referências não sustentam o critério de revisão')


def make_review(report):
    from .completion import VERSION, context_hash, limitation_messages
    review = {'version': VERSION, 'policy': POLICY, 'context_hash': context_hash(report),
              'objective': report['manifest']['requirements'], 'messages': {}}
    for key, message in limitation_messages(report).items():
        for criterion, (text, kind, justification) in NOTES.items():
            if message['text'] != text:
                continue
            annotation = {'kind': kind, 'justification': justification, 'policy': POLICY,
                          'criterion': criterion, 'evidence': []}
            try:
                annotation['evidence'] = supporting_evidence(report, criterion)
                validate_annotation(report, message, annotation)
            except PolicyError:
                continue  # Unknown or unsupported evidence remains unresolved.
            review['messages'][key] = annotation
    review['id'] = object_hash(review)
    return review


def review_report(report):
    """Return separate evaluation; never mutate raw state or saved responses."""
    from .completion import assess_completion
    review = make_review(report)
    return {'review': review, 'completion_assessment': assess_completion(report, review)}
