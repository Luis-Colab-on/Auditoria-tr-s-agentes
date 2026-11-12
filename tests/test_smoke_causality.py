"""Synthetic receipt contracts only; this module never executes audited code."""
import ast
import asyncio
import copy
import json
import zipfile
from pathlib import Path
from importlib.resources import files
import pytest
from audit3.causality import causal_groups
from audit3.config import Config, Profile
from audit3.evidence import Store
from audit3.schemas import EvidenceReceipt, SourceRef
from audit3.security import PolicyError, digest, now, object_hash
from audit3.snapshot import prepare
from audit3.receipt_review import MEASUREMENT_NOTE
from audit3.smoke_causality import (POLICY, MARKER, script, check_scope,
    prepare_smoke_evidence, certificates_for_smoke)
from test_tools_schemas import finding, tools_for


@pytest.fixture
def smoke_run(tmp_path):
    policy = json.loads(files('audit3').joinpath('assets', 'smoke-review-policy.json').read_text())[POLICY]
    source = Path(__file__).parent / 'fixtures/codex-smoke'
    archive = tmp_path / 'synthetic-smoke.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        for path in policy['files']:
            z.writestr(path, (source / path).read_bytes())
    store, config = Store(tmp_path / 'state'), Config()
    manifest = prepare(store, str(archive), None, Profile(name='synthetic'), config, policy['objective'])
    return store, manifest, config


class SyntheticExecutor:
    """Hand-authored contract observations, explicitly NOT Docker execution."""
    def __init__(self, store, manifest):
        self.store, self.manifest, self.calls = store, manifest, []
        self.execution = 'docker'  # fixture of this field; command/versions identify the mock
        self.setup_error = False

    async def execute(self, request, owner, phase):
        self.calls.append((request, owner, phase))
        eid = str(len(self.calls)) * 24
        stderr = ''
        if request.kind == 'python':
            methods = {node.name: node.body[0].lineno for node in ast.walk(ast.parse(request.script))
                       if isinstance(node, ast.FunctionDef) and node.name.startswith('test_')}
            for method in ('test_payment_twenty', 'test_payment_thirty_five'):
                stderr += f'{method} (synthetic.RefundContract.{method}) ... ok\n'
            for method, actual, expected in (('test_refund_twenty', 80, 120), ('test_refund_thirty_five', 215, 285)):
                stderr += (f'======================================================================\n'
                    f'FAIL: {method} (synthetic.RefundContract.{method})\n'
                    f'  File "/test/repro.py", line {methods[method]}, in {method}\n'
                    f'AssertionError: {actual} != {expected}\n')
            if self.setup_error:
                stderr = 'MOCK setup/import failure; no test cases executed\n'
        receipt = EvidenceReceipt(id=eid, run_id=self.manifest.run_id, owner=owner, phase=phase,
            source_id=self.manifest.source_id, profile_hash=self.manifest.profile_hash,
            fingerprint=object_hash(request), command=['MOCK', 'no-source-executed'], image_ids={'runner': 'sha256:' + 'e' * 64},
            versions={'fixture': 'synthetic-receipt-contract'}, started_at=now(), finished_at=now(),
            status='failed', exit_code=1, timeout=False, stdout='', stderr=stderr,
            stdout_sha256=digest(b''), stderr_sha256=digest(stderr.encode()), output_truncated=False,
            script_sha256=digest(request.script.encode()), purpose=request.purpose,
            limitations=[MEASUREMENT_NOTE], execution=self.execution)
        self.store.put(self.manifest.run_id, 'receipts/' + eid, receipt, immutable=True)
        self.store.put(self.manifest.run_id, 'tests/' + eid, {'script': request.script, 'repeat_reason': None}, immutable=True)
        return receipt


def prepared(smoke_run, consulted=True):
    store, manifest, config = smoke_run
    executor = SyntheticExecutor(store, manifest)
    marker = asyncio.run(prepare_smoke_evidence(store, manifest, config, executor))
    tools = tools_for(store, manifest, 'juiz', 'final')
    tools.read_source('app.py')
    if consulted:
        tools.read_evidence(marker['receipt_id'])
    source = next(f for f in manifest.files if f.path == 'app.py')
    findings = [finding(manifest, id=role + '-refund',
        refs=[SourceRef(path='app.py', start=2, end=4, sha256=source.sha256)],
        evidence_ids=[marker['receipt_id']], proof_method='executed',
        mechanism='abs removes the negative payment sign', invariant='subtract signed payment').model_dump(mode='json')
        for role in ('auditor', 'defensor')]
    return store, manifest, config, executor, marker, tools, findings


def test_preparation_preserves_original_baseline_and_reuses_exact_contract(smoke_run):
    store, manifest, config = smoke_run
    executor = SyntheticExecutor(store, manifest)
    source_bytes = store.path(manifest.run_id, 'source/app.py').read_bytes()
    marker = asyncio.run(prepare_smoke_evidence(store, manifest, config, executor))
    assert len(executor.calls) == 2
    assert [request.kind for request, _, _ in executor.calls] == ['baseline', 'python']
    assert executor.calls[0][0].script == ''
    baseline = store.get(manifest.run_id, 'baseline')
    assert baseline['ids'] == ['1' * 24, marker['receipt_id']]
    before = {name: store.path(manifest.run_id, name + '.json').read_bytes()
              for name in ('baseline', 'receipts/' + '1' * 24, 'tests/' + '1' * 24)}
    assert asyncio.run(prepare_smoke_evidence(store, manifest, config, executor)) == marker
    assert len(executor.calls) == 2
    assert all(store.path(manifest.run_id, name + '.json').read_bytes() == data for name, data in before.items())
    assert store.path(manifest.run_id, 'source/app.py').read_bytes() == source_bytes


def test_certificates_prove_two_distinct_witnesses_and_keep_ids(smoke_run):
    store, manifest, _, _, marker, tools, findings = prepared(smoke_run)
    before = copy.deepcopy(findings)
    certificates = certificates_for_smoke(store, manifest, findings, tools)
    verdicts = [{'finding_id': f['id'], 'classification': 'falha comprovada',
                 'root_cause_id': 'a-proposal-only', 'evidence_ids': [marker['receipt_id']]} for f in findings]
    groups = causal_groups(findings, verdicts, tools, tools.source_bytes_for_validation, certificates)
    assert len(groups) == 1 and len(certificates) == 2
    assert groups[0]['member_ids'] == ['auditor-refund', 'defensor-refund']
    assert {tuple(obs['arguments']) for proof in groups[0]['proofs'] for obs in proof['observations']
            if obs['kind'] == 'witnesses'} == {(100, -20), (250, -35)}
    assert all(len(c['controls']) == 2 for c in certificates)
    assert findings == before


@pytest.mark.parametrize('failure', ['narrow_ref', 'uncited', 'unconsulted', 'changed_receipt',
                                     'changed_source', 'wrong_role', 'wrong_marker', 'mock'])
def test_invalid_smoke_proof_is_never_generated(smoke_run, failure):
    store, manifest, _, _, marker, tools, findings = prepared(smoke_run, consulted=failure != 'unconsulted')
    if failure == 'narrow_ref': findings[0]['refs'][0]['start'] = 4
    elif failure == 'uncited': findings[0]['evidence_ids'] = []
    elif failure == 'unconsulted':
        tools_for(store, manifest, 'auditor', 'initial-0000').read_evidence(marker['receipt_id'])
    elif failure in ('changed_receipt', 'mock'):
        receipt = store.get(manifest.run_id, 'receipts/' + marker['receipt_id'])
        receipt['stderr' if failure == 'changed_receipt' else 'execution'] = 'divergent' if failure == 'changed_receipt' else 'mock'
        store.put(manifest.run_id, 'receipts/' + marker['receipt_id'], receipt)
    elif failure == 'changed_source':
        path = store.path(manifest.run_id, 'source/app.py')
        path.chmod(0o600)
        path.write_text('# deliberately divergent test copy\n')
    elif failure == 'wrong_role': tools = tools_for(store, manifest, 'auditor', 'initial-0000')
    else:
        store.put(manifest.run_id, MARKER, {**marker, 'source_id': 'wrong'})
    with pytest.raises(PolicyError):
        certificates_for_smoke(store, manifest, findings, tools)


def test_shared_label_alone_still_does_not_merge_smoke_findings(smoke_run):
    _, _, _, _, marker, tools, findings = prepared(smoke_run)
    verdicts = [{'finding_id': f['id'], 'classification': 'falha comprovada',
                 'root_cause_id': 'same-label', 'evidence_ids': [marker['receipt_id']]} for f in findings]
    with pytest.raises(PolicyError, match='sem prova equivalente'):
        causal_groups(findings, verdicts, tools, tools.source_bytes_for_validation)


def test_existing_baseline_and_different_fixture_are_never_replaced(smoke_run):
    store, manifest, config = smoke_run
    executor = SyntheticExecutor(store, manifest)
    store.put(manifest.run_id, 'baseline', {'ids': ['f' * 24]}, immutable=True)
    before = store.path(manifest.run_id, 'baseline.json').read_bytes()
    with pytest.raises(PolicyError, match='run novo'):
        asyncio.run(prepare_smoke_evidence(store, manifest, config, executor))
    assert not executor.calls and store.path(manifest.run_id, 'baseline.json').read_bytes() == before
    changed = manifest.model_copy(update={'requirements': 'a different objective'})
    with pytest.raises(PolicyError, match='fixture e ao objetivo'):
        check_scope(store, changed)


def test_mock_executor_does_not_authorize_smoke_contract(smoke_run):
    store, manifest, config = smoke_run
    executor = SyntheticExecutor(store, manifest)
    executor.execution = 'mock'
    with pytest.raises(PolicyError, match='execução isolada'):
        asyncio.run(prepare_smoke_evidence(store, manifest, config, executor))
    assert not store.exists(manifest.run_id, MARKER)


def test_failed_setup_is_rejected_before_smoke_contract_is_published(smoke_run):
    store, manifest, config = smoke_run
    executor = SyntheticExecutor(store, manifest)
    executor.setup_error = True
    with pytest.raises(PolicyError, match='dois estornos'):
        asyncio.run(prepare_smoke_evidence(store, manifest, config, executor))
    assert not store.exists(manifest.run_id, MARKER)
    assert not store.exists(manifest.run_id, 'baseline')


def test_workflow_generates_verified_certificates_but_report_validation_never_writes(smoke_run):
    from dataclasses import replace
    from audit3.workflow import Workflow
    from audit3.schemas import Judgment
    from test_decisions_comparisons import verdict
    store, manifest, _, executor, marker, tools, findings = prepared(smoke_run)
    for eid in store.get(manifest.run_id, 'baseline')['ids']:
        tools.read_evidence(eid)
    workflow = Workflow(store, manifest.run_id, runtime=object(), executor=executor)
    workflow.findings = lambda: {f['id']: f for f in findings}
    judgment = Judgment(summary='Synthetic final contract test only',
        baseline_assessment='Two refunds fail and two positive payments pass in the fixture receipt.',
        verdicts=[verdict(f['id'], cause='one-proposal', evidence_ids=f['evidence_ids'], proof_method='executed')
                  for f in findings], new_findings=[], limitations=[])
    tools.context = replace(tools.context, invocation_id='report-validation')
    with pytest.raises(PolicyError, match='sem prova equivalente'):
        workflow.validate_output(judgment, tools, final=True)
    assert not store.exists(manifest.run_id, 'assessment/causal-certificates')
    tools.context = replace(tools.context, invocation_id='synthetic-final')
    before = judgment.model_dump(mode='json')
    workflow.validate_output(judgment, tools, final=True)
    stored = store.path(manifest.run_id, 'assessment/causal-certificates.json').read_bytes()
    assert len(store.get(manifest.run_id, 'assessment/causal-certificates')) == 2
    tools.context = replace(tools.context, invocation_id='report-validation')
    workflow.validate_output(judgment, tools, final=True)
    assert store.path(manifest.run_id, 'assessment/causal-certificates.json').read_bytes() == stored
    assert judgment.model_dump(mode='json') == before


def test_opted_smoke_payload_requests_receipt_consultation_without_requiring_findings(smoke_run):
    from audit3.workflow import Workflow
    from helpers import MockRuntime
    store, manifest, config = smoke_run
    executor = SyntheticExecutor(store, manifest)
    marker = asyncio.run(prepare_smoke_evidence(store, manifest, config, executor))
    runtime = MockRuntime()
    output = asyncio.run(Workflow(store, manifest.run_id, runtime=runtime).invoke('auditor', 'initial-0000'))
    instruction = runtime.calls[0]['payload']['smoke_evidence_instruction']
    assert instruction['receipt_id'] == marker['receipt_id']
    assert marker['receipt_id'] in runtime.calls[0]['payload']['baseline_receipts']
    assert 'Consulte os receipts' in instruction['instruction']
    assert 'função examinada inteira' in instruction['instruction']
    assert 'nenhum achado é obrigatório' in instruction['instruction']
    assert output['findings'] == []
    assert len(executor.calls) == 2


def test_generic_payload_does_not_enable_smoke_contract(make_run):
    from audit3.workflow import Workflow
    from helpers import MockRuntime
    store, manifest = make_run()
    store.put(manifest.run_id, 'baseline', {'ids': []})
    runtime = MockRuntime()
    asyncio.run(Workflow(store, manifest.run_id, runtime=runtime).invoke('auditor', 'initial-0000'))
    assert 'smoke_evidence_instruction' not in runtime.calls[0]['payload']
    assert not store.exists(manifest.run_id, MARKER)
