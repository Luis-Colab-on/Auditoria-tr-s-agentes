import asyncio
import os
import shutil
import zipfile
from pathlib import Path
import pytest
from audit3.config import Config, Limits, Profile
from audit3.evidence import Store
from audit3.executor import Executor
from audit3.schemas import TestRequest as Request
from audit3.snapshot import prepare
from audit3.workflow import Workflow
from integration_support import require_docker, live_config, save_receipt, save_live_artifacts, assert_real_process, artifacts_path
from audit3.validation import write_json


def snapshot_fixture(tmp_path, fixture, config=None):
    root = Path(__file__).parent / "fixtures" / fixture
    archive = tmp_path / "fixture.zip"
    with zipfile.ZipFile(archive, "w") as z:
        for path in sorted(root.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts: z.write(path, path.relative_to(root).as_posix())
    store = Store(tmp_path / "state")
    cfg = config or Config()
    requirements = "Smoke da integração: execute pelo menos uma reprodução pertinente via submit_test; não force achados nem altere a fonte." if fixture == "codex-smoke" else ""
    m = prepare(store, str(archive), None, Profile(name="synthetic"), cfg, requirements)
    return store, m, cfg


@pytest.mark.docker
@pytest.mark.parametrize("fixture,expected", [("bug", "failed"), ("clean", "passed"), ("layered", "passed"), ("rare", "failed")])
def test_synthetic_project_in_real_container(tmp_path, fixture, expected):
    require_docker(Profile(name="synthetic"))
    store, m, cfg = snapshot_fixture(tmp_path, fixture)
    r = asyncio.run(Executor(store, m, cfg, Profile(name="synthetic")).execute(Request(kind="baseline", purpose="fixture semantic test"), "baseline", "baseline"))
    save_receipt(fixture, store, m, r)
    assert r.status == expected and r.execution == "docker", r.model_dump()
    if fixture == "bug":
        assert "failures=16" in r.stderr
        assert "Ran 1 test" in r.stderr


@pytest.mark.live
@pytest.mark.docker
def test_three_real_agents_small_fixture(tmp_path):
    cfg = live_config()
    require_docker(Profile(name="synthetic"))
    store, m, _ = snapshot_fixture(tmp_path, "codex-smoke", cfg)
    # Reuse only the auditor-specific official-login home, never personal HOME/auth.
    import json
    from audit3.security import atomic_write
    home = Path(os.environ["AUDIT3_CODEX_STORE"]) / "codex-home"
    # Runtime chooses this dedicated home; no token extraction or copying.
    from audit3.codex_runtime import CodexRuntime
    runtime = CodexRuntime(store, m.run_id, cfg)
    runtime.home = home.absolute()
    store.put(m.run_id, "financial-confirmation", json.loads(Path(os.environ["AUDIT3_FINANCIAL_CONFIRMATION"]).read_text()))
    try:
        from audit3.smoke_causality import prepare_smoke_evidence
        asyncio.run(prepare_smoke_evidence(store, m, cfg, Executor(store, m, cfg, Profile(name="synthetic"))))
        asyncio.run(Workflow(store, m.run_id, runtime=runtime).run())
    finally:
        from audit3.report import build_report
        from audit3.scope_review import make_review
        raw_report = build_report(store, m.run_id, use_review=False)
        store.put(m.run_id, 'assessment/completion-review', make_review(raw_report), immutable=True)
        report, events = save_live_artifacts(store, m)
    from audit3.acceptance import assert_python_smoke_completion
    assert_python_smoke_completion(report)
    assert_real_process(store, m, report, events)
    # One known mechanism; a protected helper must not create a second defect.
    from audit3.acceptance import assert_known_cause
    assert_known_cause(report, {'path': 'app.py', 'start': 4, 'end': 4})
    from audit3.completion import context_hash
    acceptance = {'status': 'passed', 'raw_status': report['state']['status'], 'context_hash': context_hash(report),
        'review_id': report['completion_assessment']['review_id']}
    store.put(m.run_id, 'assessment/smoke-acceptance', acceptance, immutable=True)
    save_live_artifacts(store, m)
    path = artifacts_path('three-agents-acceptance.json')
    if path:
        write_json(path, acceptance)
    # This validates the integration only; it does not estimate general quality.



@pytest.mark.docker
@pytest.mark.parametrize("kind", ["php", "browser"])
def test_wordpress_mysql_email_browser_and_raw_egress(tmp_path, kind):
    if os.environ.get("AUDIT3_WORDPRESS_TEST") != "1":
        pytest.skip("WordPress/MySQL/Playwright reais pendentes: requer Docker, imagens e AUDIT3_WORDPRESS_TEST=1")
    root = Path(__file__).parent / "fixtures/wordpress"
    archive = tmp_path / "wordpress.zip"
    with zipfile.ZipFile(archive, "w") as z:
        for path in root.rglob("*"):
            if path.is_file(): z.write(path, path.relative_to(root))
    from audit3.config import load_profile
    profile, cfg, store = load_profile("wordpress"), Config(), Store(tmp_path / "state")
    require_docker(profile)
    m = prepare(store, str(archive), None, profile, cfg)
    php = '''<?php
require '/work/wordpress/wp-load.php';
global $wpdb;
if (!$wpdb->get_var('SELECT VERSION()')) { exit(2); }
foreach (['1.1.1.1','169.254.169.254','172.17.0.1'] as $host) {
    $socket = @fsockopen($host, 80, $errno, $error, 0.5);
    if ($socket) { fclose($socket); exit(3); }
}
if (getenv('OPENAI_API_KEY') || file_exists('/var/run/docker.sock')) { exit(4); }
add_action('wp_mail_failed', function ($error) { fwrite(STDERR, 'SYNTHETIC_MAIL_FAILURE: ' . $error->get_error_message()); });
if (!wp_mail('fixture@example.invalid', 'synthetic', 'capture test')) { exit(5); }
$capture = file_get_contents('http://services:8080/mail');
if (strpos($capture, 'capture test') === false) { exit(6); }
echo "MYSQL_MAIL_EGRESS_PROBES_PASSED";
'''
    script = php if kind == "php" else (Path(__file__).parents[1] / "examples/browser.cjs").read_text()
    receipt = asyncio.run(Executor(store, m, cfg, profile).execute(Request(kind=kind, script=script, purpose="real synthetic WordPress isolation and behavior checks"), "auditor", "initial"))
    save_receipt("wordpress-" + kind, store, m, receipt)
    assert receipt.status == "passed" and receipt.execution == "compose", receipt.model_dump()
