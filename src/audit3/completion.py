"""Versioned scoped completion. Narrative uncertainty is never silently dropped."""
from .security import object_hash, PolicyError

VERSION = 'scoped-assessment-3'


def pointer(document, path):
    value = document
    for part in path.strip('/').split('/'):
        part = part.replace('~1', '/').replace('~0', '~')
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def context_hash(report):
    # Bind every factual input, including receipts/streams, dispatch accounting,
    # final responses and operational interruptions. Derived review is excluded.
    return object_hash({k: report.get(k) for k in ('manifest', 'coverage', 'opinions',
        'judgment', 'causal_validation', 'proven_causal_groups', 'required_phases',
        'state', 'receipts', 'usage', 'runtime', 'structural_checks', 'findings', 'verdicts', 'comparisons')})


def limitation_messages(report):
    found = {}
    def visit(value, path):
        if isinstance(value, dict):
            for key, child in value.items():
                if key == 'limitations' and isinstance(child, list):
                    for index, text in enumerate(child):
                        if not isinstance(text, str):
                            raise PolicyError('Limitação fora do contrato')
                        message = found.setdefault(object_hash(text), {'text': text, 'origins': []})
                        message['origins'].append(path + '/limitations/' + str(index))
                else:
                    visit(child, path + '/' + key)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, path + '/' + str(index))
    for key in ('manifest', 'opinions', 'judgment', 'state', 'receipts'):
        visit(report.get(key, {}), '/' + key)
    return found


def required_phases(report):
    if 'required_phases' in report:
        return set(report['required_phases'])
    required = {f'{r}/{p}' for r in ('auditor', 'defensor') for p in ('contest', 'reply')}
    required |= {f'juiz/{p}' for p in ('blind', 'review', 'final')}
    for role in ('auditor', 'defensor'):
        initial = [r['phase'] for r in report['opinions'].get(role, []) if r['phase'].startswith('initial-')]
        required |= {role + '/' + p for p in initial or ['initial-0000']}
    return required


def protocol_phases(manifest, config, additional_round=False):
    from .workflow import batches
    required = {f'{role}/{phase}' for role in ('auditor', 'defensor') for phase in ('contest', 'reply')}
    required |= {f'{role}/initial-{index:04d}' for role in ('auditor', 'defensor')
                 for index, _ in enumerate(batches(manifest, config.limits.batch_lines))}
    required |= {'juiz/blind', 'juiz/review', 'juiz/final'}
    if additional_round:
        required |= {f'{role}/{phase}' for role in ('auditor', 'defensor') for phase in ('extra-contest', 'extra-reply')}
    return sorted(required)


def assess_completion(report, review=None, required=None):
    messages = limitation_messages(report)
    review = review or {}
    if review and (review.get('version') != VERSION or review.get('context_hash') != context_hash(report)
                   or review.get('objective') != report['manifest']['requirements']):
        raise PolicyError('Revisão de limitações não corresponde ao objetivo/evidências')
    if review and review.get('id') != object_hash({k: v for k, v in review.items() if k != 'id'}):
        raise PolicyError('Identificação da revisão inválida')
    annotations = review.get('messages', {})
    if set(annotations) - set(messages):
        raise PolicyError('Revisão contém mensagem inexistente')
    blockers = [{'kind': 'coverage_gap', 'text': text} for text in report['coverage']['gaps']]
    independent = report['coverage'].get('independent_investigation')
    if not independent or not independent.get('valid'):
        blockers.append({'kind': 'independent_investigation', 'text': 'Investigação cega não comprovada'})
    checks = report.get('structural_checks', {})
    for key in ('source_integrity', 'final_validation', 'limits_valid'):
        if checks.get(key) is not True:
            blockers.append({'kind': key, 'text': checks.get(key + '_error', key + ' não demonstrado')})
    if report.get('causal_validation', {}).get('valid') is not True:
        blockers.append({'kind': 'causality', 'text': 'Validação causal ausente/inválida'})
    if report['state'].get('status') in {'blocked', 'cancelled', 'failed'}:
        blockers.append({'kind': 'operational', 'text': 'Execução interrompida/bloqueada'})
    saved = {role + '/' + record['phase'] for role, records in report['opinions'].items() for record in records}
    missing = sorted(set(required or required_phases(report)) - (set(report['state']['completed']) & saved))
    blockers += [{'kind': 'pending_phase', 'text': phase} for phase in missing]
    if not report.get('judgment'):
        blockers.append({'kind': 'missing_judgment', 'text': 'Julgamento final ausente'})
    elif report['judgment'].get('new_findings'):
        blockers.append({'kind': 'uncontested_finding', 'text': 'Achado novo final sem contraditório'})
    entries = []
    for key, message in messages.items():
        annotation = annotations.get(key)
        entry = {'message_hash': key, **message, 'kind': 'unresolved',
                 'justification': 'Limitação ainda não classificada para este objetivo', 'evidence': []}
        if annotation:
            if (set(annotation) - {'kind', 'justification', 'evidence', 'policy', 'criterion'}
                or annotation.get('kind') not in {'blocking', 'scope_note', 'procedure_note', 'unresolved'}
                or not isinstance(annotation.get('justification'), str)
                or not annotation['justification'].strip()
                or not isinstance(annotation.get('evidence'), list) or not annotation['evidence']):
                raise PolicyError('Classificação de limitação sem justificativa/evidência')
            for reference in annotation['evidence']:
                try:
                    pointer(report, reference)
                except (KeyError, IndexError, TypeError, ValueError):
                    raise PolicyError('Evidência da classificação de limitação não encontrada') from None
            if annotation['kind'] in {'scope_note', 'procedure_note'}:
                from .scope_review import validate_annotation
                try:
                    validate_annotation(report, message, annotation)
                except PolicyError as exc:
                    entry['justification'] = str(exc)
                else:
                    entry.update(annotation)
            else:
                entry.update(annotation)
        entries.append(entry)
        if entry['kind'] in {'blocking', 'unresolved'}:
            blockers.append({'kind': entry['kind'], 'message_hash': key, 'text': message['text']})
    return {'version': VERSION, 'objective': report['manifest']['requirements'],
            'context_hash': context_hash(report), 'review_id': review.get('id'),
            'review_status': 'applied' if review else 'pending', 'status': 'partial' if blockers else 'completed',
            'blockers': blockers, 'limitations': entries,
            'interpretation': 'completed means scoped work concluded, not defect-free or production approval'}
