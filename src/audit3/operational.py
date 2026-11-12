"""Narrow, recorded timeout amendments; the frozen run config stays intact."""
from .security import PolicyError, object_hash

TIMEOUT_AUTHORIZATION = 'operational/turn-timeout-authorization'
GLOBAL_AUTHORIZATION = 'operational/global-time-extension-authorization'


def turn_timeout(store, run_id, config):
    base = config.limits.call_timeout
    if not store.exists(run_id, TIMEOUT_AUTHORIZATION):
        return base
    authorization = store.get(run_id, TIMEOUT_AUTHORIZATION)
    manifest = store.get(run_id, 'manifest')
    limit = authorization.get('call_timeout')
    if (authorization.get('source') != 'explicit_operator_authorization'
        or authorization.get('run_id') != run_id
        or authorization.get('config_hash') != manifest['config_hash']
        or object_hash(config) != manifest['config_hash']
        or authorization.get('base_call_timeout') != base
        or type(limit) is not int or not base < limit <= 300):
        raise PolicyError('Autorização de timeout inválida; configuração original preservada')
    invocation = authorization.get('timeout_invocation_id')
    diagnosis_name = authorization.get('diagnosis_record')
    if (not isinstance(invocation, str) or len(invocation) != 24
        or not isinstance(diagnosis_name, str) or not diagnosis_name.startswith('validation/')
        or not store.exists(run_id, 'codex-turns/' + invocation)
        or not store.exists(run_id, diagnosis_name)):
        raise PolicyError('Ajuste de timeout sem diagnóstico/checkpoint vinculado')
    prior = store.get(run_id, 'codex-turns/' + invocation)
    diagnosis = store.get(run_id, diagnosis_name)
    if (prior.get('status') != 'ambiguous' or prior.get('error_type') != 'TimeoutError'
        or prior.get('timeout', {}).get('origin') != 'turn_deadline'
        or prior.get('timeout', {}).get('turn_limit_seconds') != base
        or diagnosis.get('run_id') != run_id
        or diagnosis.get('timeout_invocation_id') != invocation
        or diagnosis.get('normal_activity_until_deadline') is not True):
        raise PolicyError('Ajuste de timeout sem evidência de execução normal interrompida pelo prazo')
    return limit


def total_seconds(store, run_id, config, role=None, phase=None):
    """A final-only extension preserves the prior ledger and accepted phases."""
    base = config.limits.total_seconds
    if not store.exists(run_id, GLOBAL_AUTHORIZATION):
        return base
    auth = store.get(run_id, GLOBAL_AUTHORIZATION)
    manifest = store.get(run_id, 'manifest')
    limit = auth.get('total_seconds')
    snapshot_name = auth.get('snapshot_record')
    if (auth.get('source') != 'explicit_operator_authorization' or auth.get('run_id') != run_id
        or auth.get('config_hash') != manifest['config_hash'] or object_hash(config) != manifest['config_hash']
        or auth.get('base_total_seconds') != base or type(limit) is not int or not base < limit <= 1500
        or auth.get('allowed_phases') != ['juiz/final']
        or not isinstance(snapshot_name, str) or not snapshot_name.startswith('validation/')
        or not store.exists(run_id, snapshot_name)):
        raise PolicyError('Extensão global inválida; limites originais preservados')
    if role is not None and f'{role}/{phase}' not in auth['allowed_phases']:
        raise PolicyError('Extensão global autoriza somente juiz/final; outras fases não podem gerar novamente')
    snapshot = store.get(run_id, snapshot_name)
    state, ledger = store.get(run_id, 'state'), store.get(run_id, 'ledger')
    old_calls = snapshot.get('calls')
    spent = snapshot.get('elapsed_seconds')
    if (snapshot.get('run_id') != run_id or not isinstance(old_calls, list)
        or ledger['calls'][:len(old_calls)] != old_calls
        or type(spent) not in {int, float} or spent < base or state['elapsed_seconds'] < spent
        or snapshot.get('config_hash') != manifest['config_hash']):
        raise PolicyError('Extensão global não preserva tempo acumulado e chamadas anteriores')
    invocation = auth.get('timeout_invocation_id')
    if not isinstance(invocation, str) or not store.exists(run_id, 'codex-turns/' + invocation):
        raise PolicyError('Extensão global sem checkpoint final vinculado')
    prior = store.get(run_id, 'codex-turns/' + invocation)
    if (prior.get('status') != 'ambiguous' or prior.get('role') != 'juiz' or prior.get('phase') != 'final'
        or prior.get('timeout', {}).get('origin') != 'global_deadline'):
        raise PolicyError('Extensão global exige interrupção do julgamento pelo prazo global')
    from .completion import protocol_phases
    from .schemas import RunManifest
    additional = store.get(run_id, 'material-review').get('additional_round', False) if store.exists(run_id, 'material-review') else False
    required = set(protocol_phases(RunManifest.model_validate(manifest), config, additional)) - {'juiz/final'}
    frozen = snapshot.get('phase_hashes', {})
    if set(frozen) != required or not required <= set(state['completed']) or not store.exists(run_id, 'barrier'):
        raise PolicyError('Extensão global exige todas as fases anteriores concluídas')
    for item, expected in frozen.items():
        owner, saved_phase = item.split('/', 1)
        name = f'roles/{owner}/phases/{saved_phase}'
        if not store.exists(run_id, name) or object_hash(store.get(run_id, name)) != expected:
            raise PolicyError('Fase concluída alterada após autorização de extensão global')
    return limit
