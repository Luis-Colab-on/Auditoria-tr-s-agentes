"""Evidence-backed blind investigation; never repairs or rewrites historical records."""
from .config import Config
from .schemas import Opinion
from .security import PolicyError, object_hash
from .tools import SourceTools, ToolContext

VERSION = 'blind-investigation-1'


def is_blind(phase):
    return phase.startswith('initial-') or phase == 'blind'


def validate_initial_output(output, tools, assignment=None):
    phase, role = tools.context.phase, tools.context.role
    if not is_blind(phase):
        return
    auditables = [f for f in tools.manifest.files if f.category not in {'excluded', 'prior_report'} and f.lines]
    if not auditables:
        raise PolicyError('investigação cega impedida: inventário sem linhas auditáveis')
    if not output.inspections:
        raise PolicyError('investigação cega incompleta: leitura direta e inspeção próprias ausentes')
    covered = {}
    for inspection in output.inspections:
        tools.validate_inspection(inspection)
        for ref in inspection.refs:
            covered.setdefault(ref.path, set()).update(range(ref.start, ref.end + 1))
    if role == 'juiz':
        # Directed inspection is intentional: no arbitrary fraction or finding quota.
        return
    from .workflow import batches
    assigned = batches(tools.manifest, tools.config.limits.batch_lines)
    try:
        expected = assigned[int(phase.removeprefix('initial-'))]
    except (ValueError, IndexError):
        raise PolicyError('lote inicial inexistente') from None
    if assignment is not None and assignment != expected:
        raise PolicyError('lote inicial diverge do inventário atribuído')
    assignment = expected
    for ref in assignment:
        if not set(range(ref['start'], ref['end'] + 1)) <= covered.get(ref['path'], set()):
            raise PolicyError('investigação cega incompleta: análise não cobre o lote atribuído: ' + ref['path'])


def validate_saved_initial(store, manifest, config, role, phase, assignment=None):
    record = store.get(manifest.run_id, f'roles/{role}/phases/{phase}')
    if (record.get('role') != role or record.get('phase') != phase
        or not record.get('published_at')):
        raise PolicyError('fase cega persistida sem identificação/instante verificáveis')
    if store.exists(manifest.run_id, 'barrier'):
        barrier = store.get(manifest.run_id, 'barrier')
        frozen_name = f'roles/{role}/initial'
        if (not barrier.get('published_at') or record['published_at'] > barrier['published_at']
            or not store.exists(manifest.run_id, frozen_name)):
            raise PolicyError('fase cega não comprovada antes da barreira')
        frozen = store.get(manifest.run_id, frozen_name)
        if (barrier.get('initial_hashes', {}).get(role) != object_hash(frozen)
            or record['output'] not in frozen.get('opinions', [])):
            raise PolicyError('fase cega diverge do parecer congelado na barreira')
    tools = SourceTools(store, manifest, config, None,
        ToolContext(manifest.run_id, role, phase, record.get('invocation_id', 'historical-assessment')),
        read_before=record['published_at'])
    output = Opinion.model_validate(record['output'])
    validate_initial_output(output, tools, assignment)
    return output


def assess_independent_investigation(store, manifest):
    from .workflow import batches
    config = Config.model_validate(store.get(manifest.run_id, 'config'))
    assignments = batches(manifest, config.limits.batch_lines)
    phases = [(role, f'initial-{i:04d}', batch) for role in ('auditor', 'defensor')
              for i, batch in enumerate(assignments)] + [('juiz', 'blind', None)]
    gaps, verified = [], []
    if not any(f.lines for f in manifest.files if f.category not in {'excluded', 'prior_report'}):
        gaps.append('investigação cega impedida: inventário sem linhas auditáveis')
    for role, phase, assignment in phases:
        if not store.exists(manifest.run_id, f'roles/{role}/phases/{phase}'):
            gaps.append(f'{role}/{phase}: investigação cega não comprovada (fase ausente)')
            continue
        try:
            validate_saved_initial(store, manifest, config, role, phase, assignment)
        except (PolicyError, ValueError, KeyError, TypeError) as exc:
            gaps.append(f'{role}/{phase}: investigação cega não comprovada: {exc}')
        else:
            verified.append(role + '/' + phase)
    return {'version': VERSION, 'valid': not gaps, 'gaps': gaps, 'verified_phases': verified,
            'empty_files': [f.path for f in manifest.files if not f.lines and f.category not in {'excluded', 'prior_report'}]}
