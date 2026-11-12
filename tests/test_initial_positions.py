"""Offline regressions using an unedited real Defender response.

Receipts are fixture copies in a temporary Store; these tests execute no model,
Docker test or real run. SourceTools still checks references and receipt access.
"""
import hashlib
import json
from pathlib import Path

import pytest

from audit3.schemas import Opinion
from audit3.security import PolicyError
from audit3.workflow import Workflow
from test_tools_schemas import tools_for


FIXTURES = Path(__file__).parent / 'fixtures'
RESPONSE = FIXTURES / 'defender-initial-position-response.json'
ORIGINAL_SHA256 = 'db43fd5c4b99e2986657d86d03a2c0973b22a5657f0d972f9c55a14ae6d01e6f'


@pytest.fixture
def saved_response_context(make_run):
    content = {name: (FIXTURES / 'codex-smoke' / name).read_text()
        for name in ('README.md', 'app.py', 'tests/test_app.py')}
    store, manifest = make_run(content)
    raw = RESPONSE.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == ORIGINAL_SHA256
    output = Opinion.model_validate_json(raw)
    assert manifest.source_id == output.findings[0].source_id
    context = json.loads((FIXTURES / 'defender-initial-position-context.json').read_text())
    for eid, receipt in context['receipts'].items():
        # Only adapt the fixture's namespace; never modify the model response.
        store.put(manifest.run_id, 'receipts/' + eid, {
            **receipt, 'run_id': manifest.run_id, 'profile_hash': manifest.profile_hash})
        store.put(manifest.run_id, 'tests/' + eid, context['tests'][eid])
    store.put(manifest.run_id, 'roles/auditor/phases/initial-0000', context['auditor_initial'])
    tools = tools_for(store, manifest, 'defensor', 'initial-0000')
    for name in content:
        tools.read_source(name)
    return store, manifest, tools, output


def test_unedited_real_initial_response_can_position_its_validated_finding(saved_response_context):
    store, manifest, tools, output = saved_response_context
    before = output.model_dump(mode='json')
    workflow = Workflow(store, manifest.run_id)
    assert set(workflow.findings()) == {'auditor-sinal-reembolso'}
    workflow.validate_output(output, tools, final=False)
    assert output.model_dump(mode='json') == before
    assert hashlib.sha256(RESPONSE.read_bytes()).hexdigest() == ORIGINAL_SHA256
    assert store.get(manifest.run_id, 'ledger')['calls'] == []
    assert not store.exists(manifest.run_id, 'roles/defensor/phases/initial-0000')


@pytest.mark.parametrize('finding_id', ['defensor-inexistente', 'auditor-sinal-reembolso'])
def test_blind_position_cannot_reference_arbitrary_or_other_role_finding(saved_response_context, finding_id):
    store, manifest, tools, output = saved_response_context
    output.positions[0].finding_id = finding_id
    with pytest.raises(PolicyError, match='posição sobre achado inexistente'):
        Workflow(store, manifest.run_id).validate_output(output, tools, final=False)


@pytest.mark.parametrize('failure', ['namespace', 'source_id', 'source_hash', 'private_receipt'])
def test_current_response_finding_must_pass_all_existing_checks(saved_response_context, failure):
    store, manifest, tools, output = saved_response_context
    if failure == 'namespace':
        output.findings[0].id = output.positions[0].finding_id = 'auditor-outro'
        expected = 'ID deve pertencer'
    elif failure == 'source_id':
        output.findings[0].source_id = 'wrong-version'
        expected = 'achado de outra versão'
    elif failure == 'source_hash':
        output.findings[0].refs[0].sha256 = '0' * 64
        expected = 'referência de código inválida'
    else:
        eid = '296af7a367d6b911a7e33b85'
        receipt = store.get(manifest.run_id, 'receipts/' + eid)
        store.put(manifest.run_id, 'receipts/' + eid, {**receipt, 'owner': 'auditor'})
        expected = 'evidência privada'
    with pytest.raises(PolicyError, match=expected):
        Workflow(store, manifest.run_id).validate_output(output, tools, final=False)


def test_own_previous_initial_finding_remains_available(saved_response_context):
    store, manifest, tools, output = saved_response_context
    store.put(manifest.run_id, 'roles/defensor/phases/initial-0000', {
        'output': output.model_dump(mode='json')})
    output.findings = []
    tools = tools_for(store, manifest, 'defensor', 'initial-0001')
    Workflow(store, manifest.run_id).validate_output(output, tools, final=False)


def test_debate_position_can_reference_published_other_role_finding(saved_response_context):
    store, manifest, tools, output = saved_response_context
    output.findings = []
    output.positions[0].finding_id = 'auditor-sinal-reembolso'
    tools = tools_for(store, manifest, 'defensor', 'contest')
    Workflow(store, manifest.run_id).validate_output(output, tools, final=False)


def test_new_late_finding_stays_rejected(saved_response_context):
    store, manifest, tools, output = saved_response_context
    tools = tools_for(store, manifest, 'defensor', 'contest')
    with pytest.raises(PolicyError, match='novo achado tardio'):
        Workflow(store, manifest.run_id).validate_output(output, tools, final=False)


@pytest.mark.parametrize('phase', ['blind', 'review'])
def test_judge_can_position_validated_current_finding(saved_response_context, phase):
    store, manifest, tools, output = saved_response_context
    output.findings[0].id = output.positions[0].finding_id = 'juiz-reembolso-sinal'
    output.findings[0].proof_method = 'static'
    output.findings[0].evidence_ids = output.positions[0].evidence_ids = []
    tools = tools_for(store, manifest, 'juiz', phase)
    for name in ('README.md', 'app.py', 'tests/test_app.py'):
        tools.read_source(name)
    Workflow(store, manifest.run_id).validate_output(output, tools, final=False)
