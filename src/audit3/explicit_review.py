"""Explicit operator review of controller notes for a declared audit objective.

The operator interprets the objective; code checks the declared requirements,
current inventory, provenance and evidence. This is not a generic waiver API.
"""
import copy
import re
from .security import PolicyError, object_hash
from .receipt_review import MEASUREMENT_NOTE, supporting_receipt_evidence, validate_receipt_note

POLICY = 'explicit-scope-v1'
SCOPE_FLAGS = ('production_occurrence_required', 'quantitative_measurement_required',
               'secret_absence_certification_required')


def seal_review(review):
    """Identify an edited draft without refreshing any factual binding."""
    result = copy.deepcopy(review)
    result.pop('draft', None)
    result.pop('id', None)
    result['id'] = object_hash(result)
    return result


def criteria():
    from .scope_review import NOTES
    return {'inventory-reviewed': (NOTES['synthetic-inventory'][0], 'procedure_note'),
            'production-outside-objective': (NOTES['synthetic-production'][0], 'scope_note'),
            'executor-measurement': (MEASUREMENT_NOTE, 'procedure_note')}


def evidence_references(report, message, criterion):
    if criterion == 'executor-measurement':
        return supporting_receipt_evidence(report, message)
    return ['/manifest/requirements', '/manifest/files', '/coverage',
            '/structural_checks', '/judgment', '/findings']


def review_template(report):
    from .completion import VERSION, context_hash, limitation_messages
    result = {'draft': True, 'version': VERSION, 'policy': POLICY,
        'objective': report['manifest']['requirements'], 'context_hash': context_hash(report),
        'reviewer': '', 'scope': {'objective': report['manifest']['requirements'],
            'inventory_hash': object_hash(report['manifest']['files']),
            **{flag: None for flag in SCOPE_FLAGS}, 'rationale': ''}, 'messages': {}}
    for key, message in limitation_messages(report).items():
        for criterion, (text, kind) in criteria().items():
            if message['text'] != text:
                continue
            try:
                references = evidence_references(report, message, criterion)
            except PolicyError:
                continue  # Unsupported receipt stays unresolved; do not propose evidence-free approval.
            result['messages'][key] = {'policy': POLICY, 'criterion': criterion, 'kind': kind,
                'justification': '', 'evidence': references}
    return result


def validate_contract(report, review):
    scope = review.get('scope', {})
    if (review.get('policy') != POLICY or not isinstance(review.get('reviewer'), str)
        or not review['reviewer'].strip() or not isinstance(scope, dict)
        or set(scope) != {'objective', 'inventory_hash', 'rationale', *SCOPE_FLAGS}
        or scope.get('objective') != report['manifest']['requirements']
        or not scope.get('objective', '').strip()
        or scope.get('inventory_hash') != object_hash(report['manifest']['files'])
        or not isinstance(scope.get('rationale'), str) or not scope['rationale'].strip()
        or any(type(scope.get(flag)) is not bool for flag in SCOPE_FLAGS)):
        raise PolicyError('Revisão explícita exige revisor, interpretação do objetivo e inventário atual')
    return scope


def validate_annotation(report, message, annotation, review):
    scope = validate_contract(report, review)
    criterion = annotation.get('criterion')
    supported = criteria()
    if criterion not in supported or annotation.get('policy') != POLICY:
        raise PolicyError('Critério explícito não suportado')
    text, kind = supported[criterion]
    if message['text'] != text or annotation['kind'] != kind:
        raise PolicyError('Mensagem/classificação fora do critério explícito')
    if criterion == 'executor-measurement':
        validate_receipt_note(report, message, annotation, scope)
        return
    # Preparation notes may also be copied by Workflow into raw state, but a
    # model's identical prose is never authenticated as a controller note.
    origins = message['origins']
    if (not any(re.fullmatch(r'/manifest/limitations/\d+', p) for p in origins)
        or any(not re.fullmatch(r'/(manifest|state)/limitations/\d+', p) for p in origins)):
        raise PolicyError('Proveniência da nota não é a preparação do controlador')
    if annotation['evidence'] != evidence_references(report, message, criterion):
        raise PolicyError('Referências não sustentam o critério explícito')
    checks = report.get('structural_checks', {})
    if checks.get('source_integrity') is not True or checks.get('final_validation') is not True:
        raise PolicyError('Revisão explícita exige fonte íntegra e julgamento verificado')
    if criterion == 'inventory-reviewed':
        inventory = report['manifest']['files']
        if (scope['secret_absence_certification_required'] or not inventory
            or len({f.get('path') for f in inventory}) != len(inventory)
            or any(not f.get('path') or not re.fullmatch('[a-f0-9]{64}', f.get('sha256', ''))
                   or f.get('category') in {'excluded', 'prior_report'} for f in inventory)
            or report['coverage'].get('excluded')
            or not report['coverage'].get('independent_investigation', {}).get('valid')
            or report['coverage'].get('gaps')):
            raise PolicyError('Inventário/escopo não sustenta dispensa da nota heurística')
    elif (scope['production_occurrence_required'] or not report.get('judgment')
          or any(f.get('production_observation') == 'observed_with_evidence' for f in report.get('findings', []))):
        raise PolicyError('Ausência de ocorrência em produção não atende ao objetivo declarado')
