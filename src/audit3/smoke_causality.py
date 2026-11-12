"""Opt-in, evidence-bound certificates for the frozen synthetic Python smoke.

Only the disposable executor may execute the packaged script. Certificate checks
parse the source and recorded observations; they never import audited code.
"""
import ast
import json
import re
from importlib.resources import files
from .causality import PROOF_VERSION, verify_certificate
from .schemas import TestRequest
from .security import PolicyError, digest, object_hash
from .snapshot import verify_source

POLICY = 'python-smoke-v1'
MARKER = 'assessment/smoke-contract'
SCRIPT_ASSET = 'smoke-causality.py'


def script():
    return files('audit3').joinpath('assets', SCRIPT_ASSET).read_text()


def check_recorded_cases(receipt):
    """Reject setup errors before any model turn; final proofs remain mandatory."""
    if (receipt.get('execution') != 'docker' or receipt.get('status') != 'failed'
        or receipt.get('exit_code') != 1 or receipt.get('timeout') or receipt.get('output_truncated')
        or receipt.get('stdout_sha256') != digest(receipt['stdout'].encode())
        or receipt.get('stderr_sha256') != digest(receipt['stderr'].encode())):
        raise PolicyError('Receipt causal smoke sem observações íntegras de execução isolada')
    stderr = receipt['stderr']
    for name, actual, expected in (('test_refund_twenty', 80, 120), ('test_refund_thirty_five', 215, 285)):
        marker = 'FAIL: ' + name + ' '
        failure = re.split(r'\n={5,}\n|\nFAIL: ', stderr.split(marker, 1)[-1], maxsplit=1)[0]
        if marker not in stderr or f'AssertionError: {actual} != {expected}' not in failure:
            raise PolicyError('Receipt causal smoke não demonstrou os dois estornos esperados')
    for name in ('test_payment_twenty', 'test_payment_thirty_five'):
        if not re.search(r'^' + name + r' \([^\n]+\) \.\.\. ok$', stderr, re.M):
            raise PolicyError('Receipt causal smoke não demonstrou os dois controles positivos')


def check_scope(store, manifest):
    catalog = json.loads(files('audit3').joinpath('assets', 'smoke-review-policy.json').read_text())
    policy = catalog[POLICY]
    actual = {record.path: record.sha256 for record in manifest.files}
    if actual != policy['files'] or manifest.requirements != policy['objective']:
        raise PolicyError('Política causal smoke restrita à fixture e ao objetivo congelados')
    verify_source(store, manifest)


def check_marker(store, manifest):
    check_scope(store, manifest)
    marker = store.get(manifest.run_id, MARKER)
    if (set(marker) != {'policy', 'source_id', 'receipt_id'} or marker['policy'] != POLICY
        or marker['source_id'] != manifest.source_id):
        raise PolicyError('Contrato causal smoke de outra política/fonte')
    baseline = store.get(manifest.run_id, 'baseline')
    if marker['receipt_id'] not in baseline['ids']:
        raise PolicyError('Reprodução causal smoke não integra os receipts de base')
    test = store.get(manifest.run_id, 'tests/' + marker['receipt_id'])
    receipt = store.get(manifest.run_id, 'receipts/' + marker['receipt_id'])
    if (test.get('script') != script() or receipt.get('run_id') != manifest.run_id
        or receipt.get('source_id') != manifest.source_id or receipt.get('profile_hash') != manifest.profile_hash
        or receipt.get('owner') != 'baseline' or receipt.get('phase') != 'smoke-causality'
        or receipt.get('script_sha256') != digest(script().encode())):
        raise PolicyError('Receipt causal smoke divergente do contrato preparado')
    check_recorded_cases(receipt)
    return marker


async def prepare_smoke_evidence(store, manifest, config, executor):
    """Prepare once, before Workflow; never replace an existing baseline."""
    check_scope(store, manifest)
    if store.exists(manifest.run_id, MARKER):
        return check_marker(store, manifest)
    if store.exists(manifest.run_id, 'baseline') or store.get(manifest.run_id, 'state').get('completed'):
        raise PolicyError('Preparação causal exige run novo; baseline/histórico preservados')
    baseline = await executor.execute(TestRequest(kind='baseline',
        purpose='testes de base factuais do snapshot'), 'baseline', 'baseline')
    if baseline.execution != 'docker' or baseline.status != 'failed' or baseline.timeout or baseline.output_truncated:
        raise PolicyError('Baseline Python smoke não demonstrou execução isolada completa')
    receipt = await executor.execute(TestRequest(kind='python', script=script(),
        purpose='Contrato sintético: duas entradas negativas distintas e dois controles positivos; '
                'conservar referências completas da função e citar este receipt ao afirmar a causa'),
        'baseline', 'smoke-causality')
    if receipt.execution != 'docker' or receipt.status != 'failed' or receipt.timeout or receipt.output_truncated:
        raise PolicyError('Reprodução causal smoke não demonstrou execução isolada completa')
    check_recorded_cases(receipt.model_dump(mode='json'))
    marker = {'policy': POLICY, 'source_id': manifest.source_id, 'receipt_id': receipt.id}
    store.put(manifest.run_id, 'baseline', {'ids': [baseline.id, receipt.id]}, immutable=True)
    store.put(manifest.run_id, MARKER, marker, immutable=True)
    check_marker(store, manifest)
    return marker


def certificates_for_smoke(store, manifest, findings, tools):
    """Return only independently verified certificates for proven candidates.

    No text/root-cause label defines equivalence, and original findings are not
    rewritten. A narrow anchor cannot be expanded on the model's behalf.
    """
    marker = check_marker(store, manifest)
    if tools.context.run_id != manifest.run_id or tools.context.role != 'juiz':
        raise PolicyError('Certificação smoke exige consultas próprias do Juiz no mesmo run')
    eid = marker['receipt_id']
    source = tools.source_bytes_for_validation('app.py')
    function = next(node for node in ast.parse(source).body
                    if isinstance(node, ast.FunctionDef) and node.name == 'balance_after_payment')
    observed = {}
    for node in ast.walk(ast.parse(script())):
        if isinstance(node, ast.FunctionDef) and node.name.startswith('test_'):
            observed[node.name] = next(statement.lineno for statement in node.body
                if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call)
                and isinstance(statement.value.func, ast.Attribute) and statement.value.func.attr == 'assertEqual')
    certificates = []
    for finding in findings:
        refs = [ref for ref in finding['refs'] if ref['path'] == 'app.py'
                and ref['start'] <= function.end_lineno and ref['end'] >= function.lineno]
        if not refs:
            continue  # Other operations do not inherit this cause.
        ref = next((ref for ref in refs if ref['start'] <= function.lineno and ref['end'] >= function.end_lineno), None)
        if not ref or eid not in finding['evidence_ids']:
            raise PolicyError('Certificado smoke pendente: achado deve citar a função completa e o receipt causal preparado')
        certificate = {'version': PROOF_VERSION, 'finding_id': finding['id'],
            'finding_hash': object_hash(finding), 'ref': ref,
            'function': 'balance_after_payment', 'operation_path': ['right'],
            'replacement': 'payment', 'precondition': 'payment < 0',
            'witnesses': [{'evidence_id': eid, 'method': name, 'line': observed[name]}
                for name in ('test_refund_twenty', 'test_refund_thirty_five')],
            'controls': [{'evidence_id': eid, 'method': name, 'line': observed[name]}
                for name in ('test_payment_twenty', 'test_payment_thirty_five')],
            'justification': 'Política python-smoke-v1: o contrato congelado exige subtrair o pagamento com sinal. '
                'Substituir apenas abs(payment) por payment corrige os dois estornos observados e mantém '
                'os dois pagamentos positivos registrados; evidência consultada pelo Juiz, sem alterar fonte/parecer.'}
        verify_certificate(certificate, finding, tools, tools.source_bytes_for_validation)
        certificates.append(certificate)
    return certificates
