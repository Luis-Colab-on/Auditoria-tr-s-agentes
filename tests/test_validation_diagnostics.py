import errno
import json
from pathlib import Path
from types import SimpleNamespace
import xml.etree.ElementTree as ET
import pytest
from audit3 import diagnostics
from audit3.agents import retryable_api_error
from audit3.cli import doctor
from audit3.validation import CASES, summarize_junit
from audit3.config import Config, Limits


def test_socket_policy_failure_is_not_host_dns_failure(monkeypatch):
    def denied(*args, **kwargs):
        raise PermissionError(errno.EPERM, "synthetic sandbox policy")
    monkeypatch.setattr(diagnostics.socket, "socket", denied)
    monkeypatch.setattr(diagnostics.socket, "getaddrinfo", lambda *a, **kw: pytest.fail("DNS must not be blamed or called"))
    monkeypatch.setattr(diagnostics.shutil, "which", lambda _: None)
    monkeypatch.setenv("OPENAI_API_KEY", "SYNTHETIC-SECRET-NEVER-PRINT")
    result = diagnostics.diagnose(probe_network=True)
    assert result["ipv4_socket"] == {"status": "denied", "errno": errno.EPERM, "error_type": "PermissionError"}
    assert result["network_changes"] is False
    assert result["network_probes"]["status"] == "not_executed_socket_policy_denied"
    assert "does_not_establish_host_wsl_dns_failure" in result["network_conclusion"]
    assert "SYNTHETIC-SECRET-NEVER-PRINT" not in json.dumps(result)
    from audit3.security import PolicyError
    with pytest.raises(PolicyError, match="API paga proibida"):
        doctor(probe_api=True)


@pytest.mark.parametrize("code", ["insufficient_quota", "project_spend_limit_exceeded", "organization_spend_limit_exceeded", "organization_usage_limit_exceeded", "billing_hard_limit_reached", "credits_exhausted"])
def test_billing_errors_are_not_retried(code):
    assert not retryable_api_error(SimpleNamespace(code=code))
    assert not retryable_api_error(SimpleNamespace(body={"error": {"type": code}}))


def test_rate_limit_remains_retryable_with_finite_configured_retries():
    assert retryable_api_error(SimpleNamespace(code="rate_limit_exceeded"))
    assert retryable_api_error(SimpleNamespace(body=None))


def test_spend_controls_require_finite_amounts():
    for value in (float("inf"), float("nan"), -1):
        with pytest.raises(ValueError):
            Limits(budget_usd=value)
        with pytest.raises(ValueError):
            Limits(call_reserve_usd=value)
        with pytest.raises(ValueError):
            Config(input_usd_per_million=value)


@pytest.mark.parametrize('failure', ['mock', 'legacy', 'baseline'])
def test_full_live_acceptance_rejects_mock_or_unexecuted_baseline(failure):
    from integration_support import assert_real_process
    from test_assessment import completion_fixture
    from audit3.scope_review import make_review
    from audit3.completion import assess_completion
    report = completion_fixture()
    if failure == 'mock': report['state']['runtime_mode'] = 'mock'
    if failure == 'legacy': report['manifest']['backend'] = 'openai-agents'
    if failure == 'baseline':
        report['receipts'][0].update(execution='not_executed', status='blocked')
        # No scope notes: this case reaches the independent baseline guard.
        report['manifest']['limitations'] = []
        report['receipts'][0]['limitations'] = []  # Isolate the independent baseline guard.
        report['state']['status'] = 'completed'
    report['completion_review'] = make_review(report)
    report['completion_assessment'] = assess_completion(report, report['completion_review'])
    expected = {'mock': 'Backend mock', 'legacy': 'Backend incompatível', 'baseline': 'Baseline não executado'}
    with pytest.raises(AssertionError, match=expected[failure]):
        assert_real_process(None, SimpleNamespace(run_id='fixture'), report, [])


def test_malformed_acceptance_report_has_specific_diagnostic():
    from integration_support import assert_real_process
    with pytest.raises(AssertionError, match='Relatório malformado'):
        assert_real_process(None, SimpleNamespace(run_id='fixture'), {'state': {}}, [])


def test_junit_skips_and_absent_tests_are_not_success(tmp_path):
    path = tmp_path / "results.xml"
    assert all(row["status"] == "not_executed" for row in summarize_junit(path))
    root = ET.Element("testsuites")
    suite = ET.SubElement(root, "testsuite")
    for i, (nodeid, _, _) in enumerate(CASES[:4]):
        file, name = nodeid.split("::")
        test = ET.SubElement(suite, "testcase", classname=file[:-3].replace("/", "."), name=name)
        if i == 1:
            ET.SubElement(test, "skipped", message="missing Docker")
        if i == 2:
            ET.SubElement(test, "failure", message="assertion failed")
        if i == 3:
            ET.SubElement(test, "error", message="setup error")
    ET.ElementTree(root).write(path)
    rows = summarize_junit(path)
    assert [r["status"] for r in rows] == ["passed", "not_executed", "failed", "failed", *["not_executed"] * 4]
    assert len(rows) == 8
    assert sum(row["dependency"] == "Docker + Codex/ChatGPT" for row in rows) == 1


@pytest.mark.parametrize('focused_status,focused_exit,expect_full', [
    ('passed', 0, True), ('failed', 1, False), ('not_executed', 0, False), ('passed', 2, False)])
def test_browser_first_gates_full_suite_and_keeps_separate_artifacts(tmp_path, monkeypatch,
        focused_status, focused_exit, expect_full):
    """MOCK pytest processes/JUnit; never runs Docker or any model."""
    from audit3 import validation
    project = tmp_path / 'project'
    (project / 'tests').mkdir(parents=True)
    (project / 'tests/test_fixtures_integration.py').write_text('# MOCK development checkout')
    (project / 'pyproject.toml').write_text('# MOCK project metadata')
    monkeypatch.setattr(validation, '__file__', str(project / 'src/audit3/validation.py'))
    monkeypatch.setattr(validation, 'diagnose', lambda: {'scope': 'MOCK'})
    monkeypatch.setenv('OPENAI_API_KEY', 'MOCK-SECRET')
    calls = []
    browser_id = next(c[0] for c in CASES if c[0].endswith('[browser]'))

    def fake_pytest(command, **kwargs):
        calls.append(command)
        ids = [item for item in command if item.startswith('tests/')]
        focused = ids == [browser_id]
        assert kwargs['env']['AUDIT3_LIVE_TEST'] == '0'
        assert 'OPENAI_API_KEY' not in kwargs['env']
        path = next(Path(item.partition('=')[2]) for item in command if item.startswith('--junitxml='))
        root = ET.Element('testsuites')
        suite = ET.SubElement(root, 'testsuite')
        for nodeid in ids:
            file, name = nodeid.split('::')
            case = ET.SubElement(suite, 'testcase', classname=file[:-3].replace('/', '.'), name=name)
            status = focused_status if focused else ('not_executed' if 'three_real_agents' in name else 'passed')
            if status != 'passed':
                ET.SubElement(case, 'failure' if status == 'failed' else 'skipped', message='MOCK ' + status)
        ET.ElementTree(root).write(path)
        marker = Path(kwargs['env']['AUDIT3_VALIDATION_ARTIFACTS']) / 'mock-marker.json'
        marker.write_text(json.dumps({'mock_stage': 'focused' if focused else 'full'}))
        return SimpleNamespace(returncode=focused_exit if focused else 0,
            stdout='MOCK FOCUSED' if focused else 'MOCK FULL', stderr='MOCK stderr')

    monkeypatch.setattr(validation.subprocess, 'run', fake_pytest)
    outcome = validation.main(['--browser-first'])
    session = next((project / 'validation').iterdir())
    result = json.loads((session / 'results.json').read_text())
    assert result['browser_first']['full_suite_started'] is expect_full
    assert len(calls) == (2 if expect_full else 1)
    assert json.loads((session / 'browser-first/evidence/mock-marker.json').read_text()) == {'mock_stage': 'focused'}
    assert 'MOCK FOCUSED' in (session / 'browser-first/pytest-output.txt').read_text()
    if expect_full:
        assert json.loads((session / 'evidence/mock-marker.json').read_text()) == {'mock_stage': 'full'}
        assert 'MOCK FULL' in (session / 'pytest-output.txt').read_text()
        assert result['counts'] == {'passed': 7, 'failed': 0, 'not_executed': 1}
    else:
        assert not (session / 'evidence/mock-marker.json').exists()
        assert all(c['status'] == 'not_executed' for c in result['cases'] if c['nodeid'] != browser_id)
    assert outcome == (1 if focused_status == 'failed' or focused_exit == 2 else 2)
    assert result['codex_turns_recorded'] == 0 and not result['operational_with_three_agents']
