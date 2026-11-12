"""Explicit claim reviews: machine-checked facts, accountable semantic interpretation.

No phrase matching, NLP inference, execution of source/tests, or automatic waiver.
The authenticated report is the factual input. Bundled source and test text must
hash to that report's snapshot/receipts before it can support any claim.
"""
from .security import PolicyError, digest, object_hash
from .schemas import EvidenceReceipt

POLICY = 'explicit-narrative-v1'
KINDS = {'blocking', 'unresolved', 'scope_note', 'procedure_note'}
REQUIRED_CHECKS = {'source_integrity', 'protocol', 'final_judgment', 'receipt_integrity'}
CHECKS = REQUIRED_CHECKS | {'initial_investigation', 'causal_separation', 'limits'}


def partition(text, pieces):
    """Exact character coverage; assigning semantic clauses is the reviewer's job."""
    cursor = 0
    if not isinstance(pieces, list) or not pieces:
        raise PolicyError('Revisão sem afirmações/requisitos discriminados')
    for piece in pieces:
        if (type(piece.get('start')) is not int or type(piece.get('end')) is not int
            or piece['start'] != cursor or not cursor < piece['end'] <= len(text)
            or piece.get('text') != text[cursor:piece['end']] or not piece['text'].strip()):
            raise PolicyError('Afirmações/requisitos não cobrem integralmente o texto original')
        cursor = piece['end']
    if cursor != len(text):
        raise PolicyError('Parte da mensagem/objetivo não foi examinada')


def aggregate(claims):
    kinds = {claim['kind'] for claim in claims}
    return next((kind for kind in ('blocking', 'unresolved', 'procedure_note') if kind in kinds), 'scope_note')


def check_receipts(report):
    receipts = report.get('receipts', [])
    if not receipts:
        raise PolicyError('Revisão narrativa sem execução demonstrada')
    for raw in receipts:
        r = EvidenceReceipt.model_validate(raw)
        m = report['manifest']
        if (r.run_id != m['run_id'] or r.source_id != m['source_id'] or r.profile_hash != m['profile_hash']
            or r.execution not in {'docker', 'compose'} or r.status not in {'passed', 'failed'}
            or r.timeout or r.output_truncated or type(r.exit_code) is not int
            or (r.exit_code == 0) != (r.status == 'passed')
            or digest(r.stdout.encode()) != r.stdout_sha256 or digest(r.stderr.encode()) != r.stderr_sha256):
            raise PolicyError('Receipt ausente/incompleto/contraditório não pode ser dispensado')


def check_guard(report, name):
    from .completion import required_phases
    checks = report.get('structural_checks', {})
    if name == 'source_integrity':
        ok = checks.get('source_integrity') is True
    elif name == 'final_judgment':
        ok = checks.get('final_validation') is True and bool(report.get('judgment')) and not report['judgment'].get('new_findings')
    elif name == 'protocol':
        saved = {role + '/' + rec['phase'] for role, records in report['opinions'].items() for rec in records}
        ok = required_phases(report) <= (saved & set(report['state']['completed']))
    elif name == 'receipt_integrity':
        check_receipts(report)
        ok = checks.get('isolation_valid') is not False
    elif name == 'initial_investigation':
        blind = report['coverage'].get('independent_investigation', {})
        ok = blind.get('valid') is True and not blind.get('gaps') and not report['coverage']['gaps']
    elif name == 'limits':
        ok = checks.get('limits_valid') is True
    elif name == 'causal_separation':
        roots = [v.get('root_cause_id') for v in report['judgment']['verdicts'] if v.get('root_cause_id') is not None]
        ok = report['causal_validation']['valid'] is True and len(roots) == len(set(roots))
    else:
        raise PolicyError('Condição automática narrativa desconhecida')
    if not ok:
        raise PolicyError('Obrigação não demonstrada: ' + name)


def evidence_bundle(report, review):
    bundle = review.get('evidence_bundle', {})
    if not isinstance(bundle, dict) or set(bundle) != {'sources', 'tests'}:
        raise PolicyError('Revisão narrativa sem pacote factual verificável')
    index = {f['path']: f for f in report['manifest']['files'] if f['category'] not in {'excluded', 'prior_report'}}
    for path, text in bundle['sources'].items():
        if path not in index or not isinstance(text, str) or digest(text.encode()) != index[path]['sha256']:
            raise PolicyError('Fonte da revisão diverge do snapshot autenticado')
    receipts = {r['id']: r for r in report['receipts']}
    for eid, script in bundle['tests'].items():
        if (eid not in receipts or not isinstance(script, str)
            or digest(script.encode()) != receipts[eid]['script_sha256']):
            raise PolicyError('Script da revisão diverge do receipt autenticado')
    return bundle


def fact_value(report, bundle, fact):
    from .completion import pointer
    domain = fact.get('domain')
    if domain == 'report':
        reference = fact.get('reference', '')
        allowed = ('/coverage/', '/structural_checks/', '/receipts/', '/manifest/files',
                   '/state/completed', '/judgment/verdicts', '/judgment/new_findings',
                   '/causal_validation/', '/comparisons', '/proven_causal_groups')
        if not reference.startswith(allowed):
            raise PolicyError('Prosa do modelo/objetivo não é fato independente de execução')
        return pointer(report, reference)
    if domain in {'source', 'test'}:
        return bundle['sources' if domain == 'source' else 'tests'][fact['key']]
    raise PolicyError('Domínio factual desconhecido')


def validate_facts(report, bundle, facts):
    if not isinstance(facts, list) or not facts:
        raise PolicyError('Afirmação sem predicados factuais verificáveis')
    primary = False
    refs = set()
    for fact in facts:
        if not isinstance(fact, dict) or set(fact) - {'domain', 'reference', 'key', 'op', 'expected'}:
            raise PolicyError('Predicado factual fora do contrato')
        try:
            value = fact_value(report, bundle, fact)
        except (KeyError, IndexError, TypeError, ValueError):
            raise PolicyError('Evidência da afirmação ausente') from None
        op, expected = fact.get('op'), fact.get('expected')
        if op == 'equals':
            ok = object_hash(value) == object_hash(expected)
        elif op == 'hash':
            ok = object_hash(value) == expected
        elif op in {'contains', 'not_contains'}:
            ok = isinstance(value, str) and isinstance(expected, str) and bool(expected)
            if ok:
                ok = (expected in value) == (op == 'contains')
        else:
            raise PolicyError('Operador factual não suportado')
        if not ok:
            raise PolicyError('Evidência contradiz o predicado da revisão')
        if fact['domain'] == 'report':
            ref = fact['reference']
            refs.add(ref)
            primary |= ref.startswith(('/coverage/', '/receipts/', '/judgment/verdicts', '/proven_causal_groups', '/comparisons'))
        else:
            primary = True
    if not primary:
        raise PolicyError('Um ponteiro/flag isolado não sustenta a interpretação')
    return refs


def validate_annotation(report, message, annotation, review):
    from .explicit_review import validate_contract
    validate_contract(report, review)
    if review.get('narrative_policy') != POLICY or annotation.get('criterion') != 'reviewed-claims':
        raise PolicyError('Versão/critério de revisão narrativa inválido')
    if (annotation.get('original_text') != message['text'] or annotation.get('original_hash') != object_hash(message['text'])
        or annotation.get('origins') != message['origins']
        or not any(p.startswith(('/opinions/', '/judgment/')) for p in message['origins'])
        or any(not p.startswith(('/opinions/', '/judgment/', '/state/limitations/')) for p in message['origins'])):
        raise PolicyError('Revisão não corresponde à mensagem e a todas as origens narrativas')
    requirements = review.get('narrative_requirements', [])
    partition(report['manifest']['requirements'], requirements)
    ids = {req.get('id') for req in requirements}
    if (None in ids or len(ids) != len(requirements)
        or any(not isinstance(req.get('interpretation'), str) or not req['interpretation'].strip() for req in requirements)):
        raise PolicyError('Interpretação dos requisitos originais não discriminada')
    if annotation.get('requirements_hash') != object_hash(requirements):
        raise PolicyError('Requisitos revisados divergentes')
    claims = annotation.get('claims', [])
    partition(message['text'], claims)
    if annotation['kind'] != aggregate(claims):
        raise PolicyError('Classificação agregada ignora parte bloqueante da mensagem')
    bundle = evidence_bundle(report, review)
    references = set()
    for claim in claims:
        if (claim.get('kind') not in KINDS or not claim.get('requirement_ids')
            or not set(claim['requirement_ids']) <= ids
            or not isinstance(claim.get('interpretation'), str) or not claim['interpretation'].strip()
            or claim.get('semantic_responsibility') != 'reviewer'):
            raise PolicyError('Afirmação sem requisito, interpretação ou responsável semântico')
        guards = set(claim.get('checks', []))
        if not REQUIRED_CHECKS <= guards or not guards <= CHECKS:
            raise PolicyError('Afirmação sem condições automáticas obrigatórias')
        for guard in guards:
            check_guard(report, guard)
        references.update(validate_facts(report, bundle, claim.get('facts')))
        if claim['kind'] == 'scope_note':
            boundary = review.get('scope_boundaries', {}).get(claim.get('boundary_id'))
            if (not boundary or not boundary.get('requirement_ids') or not set(boundary['requirement_ids']) <= ids
                or not isinstance(boundary.get('interpretation'), str) or not boundary['interpretation'].strip()
                or boundary.get('semantic_responsibility') != 'reviewer'):
                raise PolicyError('Exclusão de escopo sem interpretação dos requisitos originais')
            references.update(validate_facts(report, bundle, boundary.get('facts')))
    if set(annotation['evidence']) != references:
        raise PolicyError('Referências da anotação não correspondem aos fatos examinados')
