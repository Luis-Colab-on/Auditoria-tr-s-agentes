"""Evidence-bound causal certificates for pure Python numeric expressions.

No audited code or reproduction script is executed. Unsupported proofs stay gaps.
Certificates are controller reviews, separate from unmodified model responses.
"""
import ast
import copy
import math
import operator
import re
from .security import object_hash, digest, PolicyError

PROOF_VERSION = 'pure-expression-intervention-1'
OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
       ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
       ast.Lt: operator.lt, ast.LtE: operator.le, ast.Gt: operator.gt,
       ast.GtE: operator.ge, ast.Eq: operator.eq, ast.NotEq: operator.ne}


def numeric(value):
    if type(value) not in (int, float) or not math.isfinite(value) or abs(value) > 10**12:
        raise PolicyError('Valor fora do verificador numérico limitado')
    return value


def evaluate(node, values):
    if isinstance(node, ast.Name):
        return numeric(values[node.id])
    if isinstance(node, ast.Constant):
        return numeric(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        value = evaluate(node.operand, values)
        return numeric(-value if isinstance(node.op, ast.USub) else value)
    if isinstance(node, ast.BinOp) and type(node.op) in OPS:
        return numeric(OPS[type(node.op)](evaluate(node.left, values), evaluate(node.right, values)))
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'abs'
        and len(node.args) == 1 and not node.keywords):
        return abs(evaluate(node.args[0], values))
    if isinstance(node, ast.Compare) and len(node.ops) == 1 and type(node.ops[0]) in OPS:
        return OPS[type(node.ops[0])](evaluate(node.left, values), evaluate(node.comparators[0], values))
    raise PolicyError('Expressão fora do subconjunto verificável; prova pendente')


def expression(text):
    node = ast.parse(text, mode='eval').body
    if sum(1 for _ in ast.walk(node)) > 128:
        raise PolicyError('Expressão de prova excede limite')
    return node


def assertions(script, module, function):
    tree = ast.parse(script)
    aliases = {a.asname or a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
               and n.module == module for a in n.names if a.name == function}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)) and node.id in aliases:
            raise PolicyError('Teste reatribui a função causal importada')
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in aliases:
            raise PolicyError('Teste redefine a função causal importada')
        if isinstance(node, ast.arg) and node.arg in aliases:
            raise PolicyError('Teste sombreia a função causal importada')
    results = {}
    for method in (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)):
        assigned = {}
        for statement in method.body:
            if isinstance(statement, ast.Assign) and len(statement.targets) == 1 and isinstance(statement.targets[0], ast.Name):
                assigned[statement.targets[0].id] = statement.value
            call = statement.value if isinstance(statement, ast.Expr) else None
            if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                    and call.func.attr == 'assertEqual' and len(call.args) == 2):
                continue
            actual = call.args[0]
            if isinstance(actual, ast.Name):
                actual = assigned.get(actual.id)
            if not (isinstance(actual, ast.Call) and isinstance(actual.func, ast.Name)
                    and actual.func.id in aliases and not actual.keywords):
                continue
            try:
                arguments = [numeric(ast.literal_eval(n)) for n in actual.args]
                expected = numeric(ast.literal_eval(call.args[1]))
            except (ValueError, TypeError, PolicyError):
                continue
            results[(method.name, statement.lineno)] = (arguments, expected)
    return results


def verify_certificate(certificate, finding, tools, read_source):
    if (certificate.get('version') != PROOF_VERSION or certificate.get('finding_hash') != object_hash(finding)
        or not certificate.get('justification', '').strip()):
        raise PolicyError('Certificado causal não vinculado ao achado/justificativa')
    ref = certificate['ref']
    if ref not in finding['refs']:
        raise PolicyError('Âncora causal fora das referências do achado')
    data = read_source(ref['path'])
    if digest(data) != ref['sha256']:
        raise PolicyError('Fonte causal divergente')
    tree = ast.parse(data)
    # Evaluating a pure expression is sound only if its allowed builtin is not
    # rebound by module initialization or parameters. Unsupported modules block.
    for statement in tree.body:
        if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant) and isinstance(statement.value.value, str):
            continue
        if not isinstance(statement, ast.FunctionDef):
            raise PolicyError('Inicialização do módulo fora do subconjunto causal puro')
        annotated = [*statement.args.args, *statement.args.posonlyargs, *statement.args.kwonlyargs]
        annotated += [arg for arg in (statement.args.vararg, statement.args.kwarg) if arg]
        if (statement.name == 'abs' or statement.decorator_list or statement.args.defaults
            or any(value is not None for value in statement.args.kw_defaults)
            or statement.returns or any(arg.annotation for arg in annotated)):
            raise PolicyError('Inicialização do módulo fora do subconjunto causal puro')
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == certificate['function']]
    if len(functions) != 1:
        raise PolicyError('Função causal ausente/ambígua')
    function = functions[0]
    body = function.body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
        body = body[1:]
    if (function.decorator_list or function.args.defaults or function.args.kwonlyargs
        or function.args.vararg or function.args.kwarg or function.args.posonlyargs
        or len(body) != 1 or not isinstance(body[0], ast.Return)
        or not (ref['start'] <= function.lineno and ref['end'] >= function.end_lineno)):
        raise PolicyError('Função não é uma expressão pura isolada coberta pela âncora')
    parameters = [a.arg for a in function.args.args]
    if 'abs' in parameters:
        raise PolicyError('Builtin causal sombreado por parâmetro')
    original = body[0].value
    repaired = copy.deepcopy(original)
    parent = repaired
    path = certificate['operation_path']
    if not path or any(part not in {'left', 'right', 'operand'} for part in path):
        raise PolicyError('Operação causal não identificada')
    for part in path[:-1]:
        parent = getattr(parent, part)
    operation = getattr(parent, path[-1])
    replacement = expression(certificate['replacement'])
    setattr(parent, path[-1], replacement)
    predicate = expression(certificate['precondition'])
    module = ref['path'].removesuffix('.py').replace('/', '.')
    observations = []
    for category in ('witnesses', 'controls'):
        if not certificate.get(category):
            raise PolicyError('Prova causal exige falha observada e controles')
        for evidence in certificate[category]:
            eid = evidence['evidence_id']
            if eid not in finding['evidence_ids']:
                raise PolicyError('Observação causal não citada pelo achado')
            tools.require_evidence_consulted(eid)
            bundle = tools.read_evidence(eid, record_access=False)
            receipt, script = bundle['receipt'], bundle['test']['script']
            if (receipt['execution'] not in {'docker', 'compose'} or receipt['status'] != 'failed'
                or receipt['timeout'] or receipt['output_truncated']
                or receipt['source_id'] != finding['source_id']
                or receipt['script_sha256'] != digest(script.encode())
                or receipt['stdout_sha256'] != digest(receipt['stdout'].encode())
                or receipt['stderr_sha256'] != digest(receipt['stderr'].encode())):
                raise PolicyError('Receipt não sustenta a observação causal íntegra')
            key = (evidence['method'], evidence['line'])
            observed_assertions = assertions(script, module, function.name)
            if key not in observed_assertions:
                raise PolicyError('Asserção causal não encontrada no script salvo')
            arguments, expected = observed_assertions[key]
            if len(arguments) != len(parameters):
                raise PolicyError('Argumentos causais incompatíveis')
            values = dict(zip(parameters, arguments))
            actual, changed = evaluate(original, values), evaluate(repaired, values)
            if category == 'witnesses':
                stderr = receipt['stderr']
                marker = 'FAIL: ' + key[0] + ' '
                failure = re.split(r'\n={5,}\n|\nFAIL: ', stderr.split(marker, 1)[-1], maxsplit=1)[0]
                pairs = re.findall(r'AssertionError: ([+-]?[\d.]+) != ([+-]?[\d.]+)', failure)
                if (evaluate(predicate, values) is not True or actual == expected or changed != expected
                    or marker not in stderr or f'line {key[1]},' not in failure
                    or not any(float(a) == actual and float(b) == expected for a, b in pairs)):
                    raise PolicyError('Intervenção não explica a falha registrada e a expectativa')
            elif (evaluate(predicate, values) is not False or actual != expected or changed != expected
                  or not re.search(r'^' + re.escape(key[0]) + r' \([^\n]+\) \.\.\. ok$', receipt['stderr'], re.M)):
                raise PolicyError('Intervenção altera controle ou controle não foi observado')
            observations.append({'kind': category, 'evidence_id': eid, 'method': key[0], 'line': key[1],
                                 'arguments': arguments, 'observed': actual, 'expected': expected})
    identity = {'source_id': finding['source_id'], 'path': ref['path'], 'sha256': ref['sha256'],
                'function': function.name, 'expression': ast.dump(original), 'operation_path': path,
                'operation': ast.dump(operation), 'replacement': ast.dump(replacement), 'precondition': ast.dump(predicate)}
    return {'key': object_hash(identity), 'identity': identity, 'observations': observations,
            'certificate_hash': object_hash(certificate), 'scope': 'verified operation/intervention and recorded cases; not exhaustive correctness'}


def causal_groups(findings, verdicts, tools, read_source, certificates=None):
    certificates = certificates or []
    by_id = {f['id']: f for f in findings}
    certified = {}
    for certificate in certificates:
        fid = certificate['finding_id']
        if fid not in by_id or fid in certified:
            raise PolicyError('Certificado causal para ID ausente/duplicado')
        try:
            certified[fid] = verify_certificate(certificate, by_id[fid], tools, read_source)
        except (KeyError, ValueError, SyntaxError, AttributeError, TypeError, ZeroDivisionError, OverflowError):
            raise PolicyError('Certificado causal incompleto ou fora do subconjunto verificável') from None
    proposed = {}
    groups = {}
    for verdict in verdicts:
        fid = verdict['finding_id']
        if verdict['root_cause_id']:
            proposed.setdefault(verdict['root_cause_id'], []).append(fid)
        if verdict['classification'] != 'falha comprovada':
            continue
        proof = certified.get(fid)
        key = 'verified:' + proof['key'] if proof else 'candidate:' + fid
        group = groups.setdefault(key, {'id': key, 'member_ids': [], 'proofs': [], 'evidence_ids': []})
        group['member_ids'].append(fid)
        if proof:
            group['proofs'].append(proof)
        group['evidence_ids'] = sorted(set(group['evidence_ids']) | set(verdict['evidence_ids']))
    for members in proposed.values():
        if len(members) > 1 and (any(fid not in certified for fid in members)
            or len({certified[fid]['key'] for fid in members}) != 1):
            raise PolicyError('Agrupamento causal sem prova equivalente verificável')
    for group in groups.values():
        if len(group['member_ids']) > 1:
            cases = {tuple(p['arguments']) for proof in group['proofs'] for p in proof['observations'] if p['kind'] == 'witnesses'}
            if len(cases) < 2:
                raise PolicyError('Agrupamento causal sem diversidade de observações verificadas')
    return list(groups.values())
