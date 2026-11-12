"""Controlled Engine inspection doubles; these do not validate a live Docker daemon."""
import copy
import asyncio
import json
from pathlib import Path
import pytest
from audit3.security import PolicyError
from audit3.wordpress import collect_startup_observations, compose_spec, safety_observation, verify_compose_container
from audit3.config import Config, Profile, load_profile
from audit3.executor import Executor, ProcessResult
from audit3.schemas import TestRequest as Request
from audit3.security import digest


def safe_inspection():
    info = {"HostConfig": {"Privileged": False, "ReadonlyRootfs": True, "CapAdd": [], "CapDrop": ["ALL"],
        "SecurityOpt": ["no-new-privileges"], "PidMode": "", "IpcMode": "private", "Devices": [],
        "PortBindings": {}, "Binds": [], "Memory": 536870912, "NanoCpus": 1000000000, "PidsLimit": 128},
        "Config": {"User": "1000:1000", "Env": ["HOME=/tmp"]},
        "Mounts": [{"Type": "bind", "Source": "/synthetic/source", "Destination": "/source", "RW": False}],
        "NetworkSettings": {"Networks": {"synthetic_isolated": {}}}}
    expected = {"user": "1000:1000", "volumes": [{"source": "/synthetic/source", "target": "/source", "read_only": True}]}
    return info, expected


def test_explicit_readonly_mount_remains_permitted():
    info, expected = safe_inspection()
    verify_compose_container(info, expected, "synthetic_isolated")


@pytest.mark.parametrize("field,value", [("PidMode", "host"), ("IpcMode", "host"),
    ("Devices", [{"PathOnHost": "/dev/synthetic"}]), ("PortBindings", {"80/tcp": [{"HostPort": "8080"}]}),
    ("Binds", ["/synthetic/source:/source:ro"])])
def test_host_access_still_rejected_with_specific_field(field, value):
    info, expected = safe_inspection()
    info["HostConfig"][field] = value
    with pytest.raises(PolicyError, match="Compose expõe host: " + field):
        verify_compose_container(info, expected, "synthetic_isolated")


@pytest.mark.parametrize("attack", ["writable", "extra_mount", "wrong_source", "other_network", "credential", "root", "privileged"])
def test_mount_and_security_guards_still_reject_violations(attack):
    info, expected = safe_inspection()
    if attack == "writable": info["Mounts"][0]["RW"] = True
    if attack == "extra_mount": info["Mounts"].append({"Type": "bind", "Source": "/var/run/docker.sock", "Destination": "/docker.sock", "RW": False})
    if attack == "wrong_source": info["Mounts"][0]["Source"] = "/unexpected"
    if attack == "other_network": info["NetworkSettings"]["Networks"]["unexpected"] = {}
    if attack == "credential": info["Config"]["Env"].append("OPENAI_API_KEY=synthetic-canary")
    if attack == "root": info["Config"]["User"] = "0:0"
    if attack == "privileged": info["HostConfig"]["Privileged"] = True
    with pytest.raises(PolicyError):
        verify_compose_container(info, expected, "synthetic_isolated")


def test_diagnostic_keeps_reason_fields_without_environment_values():
    info, _ = safe_inspection()
    info["Config"]["Env"] = ["OPENAI_API_KEY=synthetic-canary"]
    info["HostConfig"]["Binds"] = ["/synthetic/source:/source:ro"]
    before = copy.deepcopy(info)
    observation = safety_observation(info)
    assert observation["host_config"]["Binds"] == info["HostConfig"]["Binds"]
    assert observation["mounts"][0]["RW"] is False
    assert "synthetic-canary" not in json.dumps(observation)
    assert "Env" not in json.dumps(observation)
    assert info == before


@pytest.mark.parametrize("change", ["remote_driver", "unbounded_files", "different_size", "default_compression", "enabled_compression"])
def test_startup_logs_require_explicit_local_rotation(change):
    info, expected = safe_inspection()
    expected["logging"] = {"driver": "local", "options": {"max-size": "1m", "max-file": "1", "compress": "false"}}
    info["HostConfig"]["LogConfig"] = {"Type": "local", "Config": {"max-size": "1m", "max-file": "1", "compress": "false"}}
    verify_compose_container(info, expected, "synthetic_isolated")
    if change == "remote_driver": info["HostConfig"]["LogConfig"]["Type"] = "syslog"
    if change == "unbounded_files": info["HostConfig"]["LogConfig"]["Config"]["max-file"] = "0"
    if change == "different_size": info["HostConfig"]["LogConfig"]["Config"]["max-size"] = "100m"
    if change == "default_compression": info["HostConfig"]["LogConfig"]["Config"].pop("compress")
    if change == "enabled_compression": info["HostConfig"]["LogConfig"]["Config"]["compress"] = "true"
    with pytest.raises(PolicyError, match="logging"):
        verify_compose_container(info, expected, "synthetic_isolated")


def test_startup_collector_is_bounded_sanitized_and_preserves_missing_evidence(monkeypatch):
    """MOCK process states/logs, no Docker or host services accessed."""
    calls = []
    secret = "synthetic-startup-secret-canary"
    monkeypatch.setenv("OPENAI_API_KEY", secret)

    async def fake_process(argv, timeout, limit):
        calls.append((argv, timeout, limit))
        if argv[:2] == ["docker", "inspect"]:
            text = json.dumps({"Status": "exited", "ExitCode": 137, "OOMKilled": True,
                "Config": {"Env": ["PRIVATE=" + secret]}})
            return ProcessResult(0, text, "", digest(text.encode()), digest(b""), False)
        assert argv[:2] == ["docker", "logs"]
        if argv[-1] == "synthetic-services":
            raise OSError("MOCK read failure: " + secret)
        output = "MOCK startup error: " + secret
        return ProcessResult(0, "", output, digest(b""), digest(output.encode()), False)

    monkeypatch.setattr("audit3.wordpress.process", fake_process)
    result = asyncio.run(collect_startup_observations({name: "synthetic-" + name for name in ("db", "services", "wordpress", "runner")}, 64000))
    assert set(result) == {"db", "services", "wordpress"}
    assert len(calls) == 6
    assert all(timeout == 10 and limit == 16000 for _, timeout, limit in calls)
    assert all("--follow" not in argv and "--details" not in argv for argv, _, _ in calls)
    assert all(argv[argv.index("--tail") + 1] == "200" for argv, _, _ in calls if "--tail" in argv)
    assert result["db"]["state"]["OOMKilled"] is True and result["db"]["state"]["ExitCode"] == 137
    assert result["services"]["logs"] == {"collection_error": "OSError"}
    assert secret not in json.dumps(result) and "PRIVATE=" not in json.dumps(result)
    assert "[OMITIDO]" in result["wordpress"]["logs"]["stderr"]


def test_setup_rejection_is_saved_with_cleanup_without_starting_tests(make_run, monkeypatch):
    """MOCK Docker responses: lifecycle/diagnostics only, no container execution."""
    calls, state = [], {}
    profile = load_profile("wordpress")
    store, manifest = make_run(profile=profile)

    def response(stdout=""):
        return ProcessResult(0, stdout, "", digest(stdout.encode()), digest(b""), False)

    async def fake_process(argv, *args):
        calls.append(argv)
        if argv[:2] == ["docker", "version"]:
            return response("29.9.3")
        if argv[:3] == ["docker", "compose", "version"]:
            return response("5.7.0")
        if argv[:3] == ["docker", "image", "inspect"]:
            return response("sha256:" + "a" * 64)
        if argv[:2] == ["docker", "compose"]:
            if "create" in argv:
                state["spec"] = json.loads(Path(argv[argv.index("--file") + 1]).read_text())
                state["network"] = argv[argv.index("--project-name") + 1] + "_isolated"
                return response()
            if "ps" in argv:
                return response("mock-" + argv[-1])
            if "down" in argv:
                return response()
        if argv[:3] == ["docker", "network", "inspect"]:
            return response(json.dumps([{"Internal": True, "EnableIPv6": False,
                "Options": {"com.docker.network.bridge.gateway_mode_ipv4": "isolated"}}]))
        if argv[:2] == ["docker", "inspect"]:
            service = argv[2].removeprefix("mock-")
            expected = state["spec"]["services"][service]
            info, _ = safe_inspection()
            info["Config"]["User"] = expected["user"]
            info["HostConfig"]["Memory"] = int(expected["mem_limit"][:-1]) * 1024**2
            info["HostConfig"]["MemorySwap"] = int(expected["memswap_limit"][:-1]) * 1024**2
            info["HostConfig"]["LogConfig"] = {"Type": expected["logging"]["driver"], "Config": expected["logging"].get("options", {})}
            info["NetworkSettings"]["Networks"] = {state["network"]: {}}
            info["Mounts"] = [{"Type": "bind", "Source": v["source"], "Destination": v["target"], "RW": False}
                for v in expected.get("volumes", [])]
            if service == "wordpress":
                # Fault injection: daemon returns a forbidden legacy Bind despite explicit Mount configuration.
                info["HostConfig"]["Binds"] = [f"{v['source']}:{v['target']}:ro" for v in expected["volumes"]]
                info["Config"]["Env"] = ["OPENAI_API_KEY=synthetic-observation-canary"]
            return response(json.dumps([info]))
        raise AssertionError("unexpected mock command: " + repr(argv))

    monkeypatch.setattr("audit3.executor.shutil.which", lambda _: "/synthetic/docker")
    monkeypatch.setattr("audit3.executor.process", fake_process)
    monkeypatch.setattr("audit3.wordpress.process", fake_process)
    receipt = asyncio.run(Executor(store, manifest, Config(), profile).execute(
        Request(kind="php", script="<?php echo 'must not execute';", purpose="MOCK setup rejection lifecycle"), "auditor", "initial"))
    assert receipt.status == "blocked" and receipt.execution == "not_executed"
    assert "wordpress: Compose expõe host: Binds" in receipt.limitations
    diagnostic = store.get(manifest.run_id, "setup-diagnostics/" + receipt.id)
    assert diagnostic["phase"] == "verify_containers" and diagnostic["rejected_service"] == "wordpress"
    assert diagnostic["containers"]["wordpress"]["host_config"]["Binds"]
    assert diagnostic["cleanup"]["exit_code"] == 0
    assert "synthetic-observation-canary" not in json.dumps(diagnostic)
    assert not any("start" in command or "exec" in command for command in calls)


def test_database_override_is_bounded_and_does_not_change_other_services():
    profile = load_profile("wordpress")
    spec = compose_spec(profile, Path('/source'), Path('/test'), Path('/assets'),
        {key:'sha256:synthetic' for key in ('wordpress','db','browser','services')}, ['php','/test/repro.php'], 'php')
    assert spec['services']['db']['mem_limit'] == spec['services']['db']['memswap_limit'] == '1024m'
    for name in ('wordpress','services','runner'):
        assert spec['services'][name]['mem_limit'] == spec['services'][name]['memswap_limit'] == '512m'
    for value in (0, -1, 4097):
        with pytest.raises(ValueError):
            Profile(name='synthetic', db_memory_mb=value)


def test_old_frozen_profile_keeps_its_serialized_shape_and_memory():
    legacy = Profile(name='synthetic').model_dump(mode='json')
    assert 'db_memory_mb' not in legacy
    restored = Profile.model_validate(legacy)
    assert restored.db_memory_mb is None and restored.model_dump(mode='json') == legacy


@pytest.mark.parametrize('field,value', [('Memory', 0), ('Memory', 2147483648), ('MemorySwap', -1)])
def test_database_override_cannot_disable_or_exceed_expected_limit(field, value):
    info, expected = safe_inspection()
    expected.update(mem_limit='1024m', memswap_limit='1024m')
    info['HostConfig'].update(Memory=1073741824, MemorySwap=1073741824)
    verify_compose_container(info, expected, 'synthetic_isolated')
    info['HostConfig'][field] = value
    with pytest.raises(PolicyError):
        verify_compose_container(info, expected, 'synthetic_isolated')


def test_browser_profile_extends_only_sandbox_setup_rules_and_keeps_clone3_fallback():
    """Pinned policy comparison; does not claim a real Chromium launch."""
    from importlib.resources import files
    from audit3.wordpress import browser_seccomp_profile
    base = json.loads(files('audit3').joinpath('assets', 'browser-seccomp-base.json').read_bytes())
    profile = browser_seccomp_profile()
    chroot = profile['syscalls'].pop()
    assert chroot['names'] == ['chroot'] and chroot['action'] == 'SCMP_ACT_ALLOW'
    assert chroot['args'] == [] and chroot['includes'] == chroot['excludes'] == {}
    added = profile['syscalls'].pop()
    assert profile == base
    assert added['names'] == ['clone', 'setns', 'unshare']
    assert added['action'] == 'SCMP_ACT_ALLOW' and added['args'] == []
    assert base['defaultAction'] == 'SCMP_ACT_ERRNO'
    assert any(rule['names'] == ['clone3'] and rule.get('errnoRet') == 38 for rule in base['syscalls'])


def test_namespace_profile_is_browser_only_and_keeps_other_isolation():
    def spec(kind):
        return compose_spec(load_profile('wordpress'), Path('/source'), Path('/test'), Path('/assets'),
            {key:'sha256:synthetic' for key in ('wordpress','db','browser','services')}, ['node','/test/repro.cjs'], kind)
    browser, php = spec('browser'), spec('php')
    for name in ('db','wordpress','services'):
        assert browser['services'][name] == php['services'][name]
    runner = browser['services']['runner']
    assert runner['security_opt'] == ['no-new-privileges:true','seccomp=/assets/browser-seccomp.json']
    assert php['services']['runner']['security_opt'] == ['no-new-privileges:true']
    assert runner['read_only'] and runner['cap_drop'] == ['ALL'] and runner['user'] == '1000:1000'
    assert runner['networks'] == ['isolated'] and runner['shm_size'] == '256m'
    assert 'privileged' not in runner and 'cap_add' not in runner and 'ports' not in runner


def browser_inspection():
    from audit3.wordpress import browser_seccomp_profile
    info, expected = safe_inspection()
    expected['security_opt'] = ['no-new-privileges:true','seccomp=/assets/browser-seccomp.json']
    info['HostConfig']['SecurityOpt'] = ['no-new-privileges=true', 'seccomp=' + json.dumps(browser_seccomp_profile(), indent=2)]
    return info, expected


def test_inspected_seccomp_json_must_match_pinned_profile():
    info, expected = browser_inspection()
    verify_compose_container(info, expected, 'synthetic_isolated')


@pytest.mark.parametrize('attack', ['unconfined', 'file_path_only', 'missing', 'wrong_default',
    'extra_syscall', 'missing_namespace_rule', 'missing_chroot_rule', 'duplicate', 'disable_nnp', 'apparmor_unconfined', 'unexpected_on_php'])
def test_browser_seccomp_mismatch_or_security_bypass_is_rejected(attack):
    info, expected = browser_inspection()
    opts = info['HostConfig']['SecurityOpt']
    if attack == 'unconfined': opts[1] = 'seccomp=unconfined'
    elif attack == 'file_path_only': opts[1] = 'seccomp=/assets/browser-seccomp.json'
    elif attack == 'missing': opts.pop()
    elif attack in {'wrong_default','extra_syscall','missing_namespace_rule','missing_chroot_rule'}:
        profile = json.loads(opts[1].partition('=')[2])
        if attack == 'wrong_default': profile['defaultAction'] = 'SCMP_ACT_ALLOW'
        elif attack == 'extra_syscall': profile['syscalls'].append({'names':['mount'],'action':'SCMP_ACT_ALLOW'})
        elif attack == 'missing_namespace_rule': profile['syscalls'].pop(-2)
        else: profile['syscalls'].pop()
        opts[1] = 'seccomp=' + json.dumps(profile)
    elif attack == 'duplicate': opts.append(opts[1])
    elif attack == 'disable_nnp': opts[0] = 'no-new-privileges:false'
    elif attack == 'apparmor_unconfined': opts.append('apparmor=unconfined')
    elif attack == 'unexpected_on_php': expected['security_opt'] = ['no-new-privileges:true']
    with pytest.raises(PolicyError):
        verify_compose_container(info, expected, 'synthetic_isolated')


def test_modified_vendored_seccomp_base_is_blocked(monkeypatch):
    from audit3.wordpress import browser_seccomp_profile
    monkeypatch.setattr('audit3.wordpress.BROWSER_SECCOMP_BASE_SHA256', '0'*64)
    with pytest.raises(PolicyError, match='adulterado'):
        browser_seccomp_profile()


def test_chroot_is_available_without_outer_capability_but_mount_is_still_denied():
    """Model Moby's capability-gated rule selection for the affected syscalls."""
    from importlib.resources import files
    from audit3.wordpress import browser_seccomp_profile
    base = json.loads(files('audit3').joinpath('assets', 'browser-seccomp-base.json').read_bytes())

    def allowed(profile, syscall, capabilities):
        return any(syscall in rule['names'] and rule['action'] == 'SCMP_ACT_ALLOW'
            and set(rule.get('includes', {}).get('caps', [])) <= capabilities
            and not (set(rule.get('excludes', {}).get('caps', [])) & capabilities)
            for rule in profile['syscalls'])

    assert not allowed(base, 'chroot', set())
    assert allowed(base, 'chroot', {'CAP_SYS_CHROOT'})
    assert allowed(browser_seccomp_profile(), 'chroot', set())
    assert not allowed(browser_seccomp_profile(), 'mount', set())
    assert not allowed(browser_seccomp_profile(), 'clone3', set())
