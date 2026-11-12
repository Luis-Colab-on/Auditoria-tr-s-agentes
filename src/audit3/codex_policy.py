"""Auditor-specific configuration and factual financial preconditions."""
from __future__ import annotations
import json
import shutil
import subprocess
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from importlib.resources import files
from pathlib import Path
from .agents import RuntimePaused
from .codex_rpc import CLI_VERSION, clean_environment
from .security import atomic_write, object_hash


def asset(name):
    return files('audit3').joinpath('assets', name).read_bytes()


def financial_policy():
    return asset('financial-policy.txt').decode()


def financial_remaining(checked_at):
    try:
        checked = datetime.fromisoformat(checked_at)
        if checked.utcoffset() is None:
            raise ValueError('timezone required')
        age = (datetime.now(timezone.utc) - checked).total_seconds()
    except (ValueError, TypeError):
        raise RuntimePaused('Data da verificação financeira desconhecida; informe horário real com fuso') from None
    if not 0 <= age < 1800:
        raise RuntimePaused('Verificação financeira expirada/futura: nova conferência factual necessária; nenhum gasto autorizado')
    return 1800 - age


def private_config(home):
    features = {name: False for name in json.loads(asset('codex-contract.json'))['features']}
    features['skip_host_skill_discovery'] = True
    text = '''forced_login_method = "chatgpt"
cli_auth_credentials_store = "file"
model_provider = "openai"
model = "gpt-6-astra"
model_reasoning_effort = "max"
service_tier = "default"
approval_policy = "never"
default_permissions = "audit3"
web_search = "disabled"
project_doc_max_bytes = 0
project_doc_fallback_filenames = []
allow_login_shell = false
hide_agent_reasoning = true
show_raw_agent_reasoning = false
'''
    text += 'model_catalog_json = ' + json.dumps(str(home / 'models.json')) + '\n'
    text += '[permissions.audit3.filesystem]\n":root" = "deny"\n[permissions.audit3.network]\nenabled = false\n'
    text += '[memories]\ngenerate_memories = false\nuse_memories = false\ndedicated_tools = false\n'
    text += '[skills]\ninclude_instructions = false\n[skills.bundled]\nenabled = false\n'
    text += '[plugins._default]\nenabled = false\n[tools.update_plan]\nenabled = false\n'
    text += '[features]\n' + ''.join(k + ' = ' + str(v).lower() + '\n' for k, v in features.items())
    return text.encode()


def setup_home(home):
    home = home.absolute()
    if any(p.is_symlink() for p in (home, *home.parents)):
        raise RuntimePaused('CODEX_HOME do auditor não pode ser link')
    home.mkdir(mode=0o700, parents=True, exist_ok=True)
    for name, data in [('config.toml', private_config(home)), ('models.json', asset('codex-model.json'))]:
        path = home / name
        if path.exists() and (path.is_symlink() or path.read_bytes() != data):
            raise RuntimePaused('Configuração privada divergente: ' + name + '; não será sobrescrita')
        if not path.exists():
            atomic_write(path, data)
    if (home / 'empty').is_symlink():
        raise RuntimePaused('cwd privado não pode ser link')
    (home / 'empty').mkdir(mode=0o700, exist_ok=True)
    if any((home / 'empty').iterdir()):
        raise RuntimePaused('cwd privado deve permanecer vazio')
    return home


def executable():
    binary = shutil.which('codex')
    if not binary:
        raise RuntimePaused('Codex oficial ausente; backend real bloqueado')
    path = Path(binary).resolve()
    if path.suffix == '.js':
        # Official npm distribution: run its pinned native dependency directly;
        # no Node interpreter or inherited NODE_OPTIONS enters the subprocess.
        import platform
        target = {'x86_64': ('codex-linux-x64', 'x86_64-unknown-linux-musl'),
                  'aarch64': ('codex-linux-arm64', 'aarch64-unknown-linux-musl')}.get(platform.machine())
        if not target:
            raise RuntimePaused('Use um executável Codex nativo compatível')
        package, triple = target
        path = path.parent.parent / 'node_modules' / '@openai' / package / 'vendor' / triple / 'bin' / 'codex'
        if not path.is_file():
            raise RuntimePaused('Dependência nativa oficial do Codex ausente')
    return str(path.absolute())


def verify_client(binary, home):
    def command(args):
        r = subprocess.run([binary, *args], cwd=home / 'empty', env=clean_environment(home),
            capture_output=True, timeout=20, text=True)
        if r.returncode:
            raise RuntimePaused('Cliente Codex incompatível com contrato privado (sem inferência)')
        return r.stdout
    if command(['--version']).strip() != 'codex-cli ' + CLI_VERSION:
        raise RuntimePaused('Versão Codex incompatível; requer ' + CLI_VERSION)
    # Official parser, strict configuration, no model call. Actual server config is
    # checked again through config/read before thread/start.
    command(['app-server', '--strict-config', '--print-startup-config'])
    catalog = json.loads(command(['debug', 'models']))
    catalog = catalog.get('models', []) if isinstance(catalog, dict) else catalog
    target = next((m for m in catalog if m.get('slug') == 'gpt-6-astra'), None)
    if not target:
        raise RuntimePaused('Astra ausente no catálogo do cliente')
    if target.get('shell_type') != 'disabled' or target.get('apply_patch_tool_type') is not None or target.get('experimental_supported_tools'):
        raise RuntimePaused('Catálogo efetivo permite ferramentas nativas; isolamento bloqueado')


def account_identity(account):
    if not account or account.get('type') != 'chatgpt':
        raise RuntimePaused('Autenticação efetiva deve ser ChatGPT; API/provedor alternativo recusado')
    # CLI 0.167.0 exposes distinct personal Pro tiers; preserve the wire label.
    if account.get('planType') not in ('pro', 'prolite', 'promax'):
        raise RuntimePaused('Plano Pro não confirmado oficialmente')
    if not account.get('email'):
        raise RuntimePaused('Identidade da conta desconhecida')
    return object_hash({k: account.get(k) for k in ('type', 'email', 'planType', 'workspaceName')})


def select_effort(models):
    target = next((m for m in models if m.get('model') == 'gpt-6-astra'), None)
    if not target:
        raise RuntimePaused('gpt-6-astra não disponível; nenhuma substituição autorizada')
    supported = {e['reasoningEffort'] for e in target.get('supportedReasoningEfforts', [])}
    for effort in ('max', 'xhigh'):
        if effort in supported:
            return effort
    raise RuntimePaused('Astra não oferece Max nem Extra High')


def financial_check(proof, identity, quota):
    # This is an operator's factual confirmation, not a software-created claim of
    # included-only enforcement. It is rechecked against official credits/usage.
    if not proof or proof.get('source') != 'operator_factual_confirmation':
        raise RuntimePaused('Verificação financeira desconhecida: falta confirmação factual de recarga desativada e ausência de créditos extras')
    if proof.get('account_fingerprint') != identity:
        raise RuntimePaused('Confirmação financeira pertence a outra conta')
    financial_remaining(proof.get('checked_at'))
    if proof.get('auto_recharge') != 'disabled' or proof.get('extra_credits') != 'none':
        raise RuntimePaused('Verificação financeira expirada/incompatível: rever fatos no painel oficial')
    if not isinstance(quota, dict) or quota.get('ordinaryUsageAllowed') is not True:
        raise RuntimePaused('Franquia incluída indisponível/desconhecida; retomar explicitamente após renovação')
    by_limit = quota.get('rateLimitsByLimitId')
    if by_limit is not None and not isinstance(by_limit, dict):
        raise RuntimePaused('Observabilidade de quota perdida')
    buckets = list((by_limit or {}).values())
    if quota.get('rateLimits') is not None:
        buckets.append(quota['rateLimits'])  # Check every official view, including conflicts.
    if not buckets or any(not isinstance(b, dict) for b in buckets):
        raise RuntimePaused('Observabilidade de quota perdida')
    for bucket in buckets:
        credits = bucket.get('credits')
        if not isinstance(credits, dict) or credits.get('hasCredits') is not False or credits.get('unlimited') is not False:
            raise RuntimePaused('Ausência de créditos extras não confirmada oficialmente')
        try:
            if not isinstance(credits.get('balance'), str):
                raise RuntimePaused('Saldo extra desconhecido')
            if not Decimal(credits['balance']).is_zero():
                raise RuntimePaused('Saldo extra presente; geração bloqueada')
        except (InvalidOperation, KeyError, TypeError):
            raise RuntimePaused('Saldo extra desconhecido') from None
        windows = [bucket.get(w) for w in ('primary', 'secondary') if bucket.get(w) is not None]
        if not windows or any(not isinstance(w, dict) or type(w.get('usedPercent')) not in (int, float) or not 0 <= w['usedPercent'] < 100 for w in windows):
            raise RuntimePaused('Quota esgotada/desconhecida')
        if bucket.get('spendControlReached') or bucket.get('rateLimitReachedType'):
            raise RuntimePaused('Limite oficial atingido')
    return {'status': 'verified_facts', 'source': proof['source'], 'checked_at': proof['checked_at'],
        'atomic_financial_guard': False, 'ordinary_usage_allowed': True}


def check_effective_config(config, home):
    import tomllib
    expected = tomllib.loads(private_config(home).decode())
    # config/read serializes selected fields, adding null defaults and omitting
    # removed feature aliases and the update_plan stanza. The strict CLI parser
    # validates that stanza separately; the plan tool grants no I/O authority.
    def without_null(value):
        return {k: without_null(v) for k,v in value.items() if v is not None} if isinstance(value, dict) else value
    config = without_null(config)
    expected.pop('tools')
    expected['features'].pop('apps_mcp_path_override', None)
    # Higher precedence managed/system/project config must not weaken any setting.
    def subset(want, actual):
        return isinstance(actual, dict) and all(subset(v, actual.get(k)) if isinstance(v, dict) else actual.get(k) == v for k, v in want.items())
    if not subset(expected, config):
        raise RuntimePaused('Configuração efetiva herdada diverge da política privada')
    if any(config.get(k) for k in ('mcp_servers', 'model_providers', 'hooks', 'notify', 'model_instructions_file', 'sandbox_mode', 'developer_instructions', 'instructions')):
        raise RuntimePaused('Overrides/ferramentas herdados recusados')
    if config.get('permissions', {}).get('audit3') != expected['permissions']['audit3'] or config.get('plugins') != expected['plugins'] or config.get('skills') != expected['skills']:
        raise RuntimePaused('Permissões herdadas recusadas')
