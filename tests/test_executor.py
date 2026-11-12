import asyncio
import copy
import json
import shutil
from inspect import getsource
from pathlib import Path
import pytest
from audit3.config import Config, Profile
from audit3.executor import Executor, docker_create, process, test_argv as build_argv, verify_container
from audit3.schemas import TestRequest as Request
from audit3.security import PolicyError
from audit3.wordpress import compose_spec, verify_compose_container
from integration_support import require_docker, save_receipt
from probe_support import private_path_observation


def test_argv_is_typed_no_host_shell():
    p = Profile(name="test")
    req = Request(kind="python", script="__import__('os').system('whoami')", purpose="adversarial code only in container")
    assert build_argv(req, p) == ["python", "-B", "/test/repro.py"]
    argv = docker_create("audit3-test", "sha256:abc", Path("/safe/source"), Path("/safe/test"), p, build_argv(req, p))
    assert "--network=none" in argv and "--read-only" in argv and "--cap-drop=ALL" in argv
    assert req.script not in argv
    assert not any("docker.sock" in x or "SSH_AUTH_SOCK" in x or "OPENAI_API_KEY" in x for x in argv)
    with pytest.raises(PolicyError): build_argv(Request(kind="php", script="<?php", purpose="denied"), p)
    with pytest.raises(PolicyError): build_argv(Request(kind="baseline", purpose="denied"), Profile(name="bad", baseline=["sh", "-c", "echo hello"]))
    with pytest.raises(PolicyError): build_argv(Request(kind="baseline", script="different", purpose="fingerprint bypass"), p)


def inspected():
    return {"HostConfig": {"ReadonlyRootfs": True, "NetworkMode": "none", "CapDrop": ["ALL"], "SecurityOpt": ["no-new-privileges"], "Memory": 512*1024**2, "PidsLimit": 128, "NanoCpus": 1000000000, "IpcMode": "private"},
        "Config": {"User": "65534:65534", "Env": ["HOME=/tmp"]}, "Mounts": [{"Type": "bind", "Source": "/source-host", "Destination": "/source", "RW": False}, {"Type": "bind", "Source": "/test-host", "Destination": "/test", "RW": False}]}


@pytest.mark.parametrize("attack", ["network", "privileged", "socket", "credential", "write", "pid", "memory", "cpu", "root", "capability"])
def test_container_post_create_validation(attack):
    info = inspected()
    p = Profile(name="test")
    verify_container(info, Path("/source-host"), Path("/test-host"), p)
    if attack == "network": info["HostConfig"]["NetworkMode"] = "host"
    if attack == "privileged": info["HostConfig"]["Privileged"] = True
    if attack == "socket": info["Mounts"].append({"Type":"bind", "Source":"/var/run/docker.sock", "Destination":"/docker.sock", "RW":False})
    if attack == "credential": info["Config"]["Env"].append("OPENAI_API_KEY=synthetic-canary")
    if attack == "write": info["Mounts"][0]["RW"] = True
    if attack == "pid": info["HostConfig"]["PidMode"] = "host"
    if attack == "memory": info["HostConfig"]["Memory"] = 0
    if attack == "cpu": info["HostConfig"]["NanoCpus"] = 0
    if attack == "root": info["Config"]["User"] = "0"
    if attack == "capability": info["HostConfig"]["CapAdd"] = ["SYS_ADMIN"]
    with pytest.raises(PolicyError): verify_container(info, Path("/source-host"), Path("/test-host"), p)


def test_compose_internal_isolated_no_ports_no_host_credentials():
    spec = compose_spec(Profile(name="wp", engine="compose"), Path("/source"), Path("/tests"), Path("/assets"), {key:"sha256:fixture" for key in ("wordpress","db","services","browser")}, ["node", "/test/repro.cjs"], "browser")
    network = spec["networks"]["isolated"]
    assert network["internal"] and network["driver_opts"]["com.docker.network.bridge.gateway_mode_ipv4"] == "isolated"
    for service in spec["services"].values():
        assert service["networks"] == ["isolated"] and "ports" not in service
        assert service["read_only"] and service["cap_drop"] == ["ALL"]
        assert service["user"] != "root" and service["user"] != "0"
        assert all(v["read_only"] for v in service.get("volumes", []))
        assert all(v.get("bind", {}).get("create_host_path") is False for v in service.get("volumes", []))
    assert spec["services"]["db"]["image"] == "sha256:fixture"  # explicit MySQL, no SQLite fallback
    for name in ("db", "wordpress", "services"):
        assert spec["services"][name]["logging"] == {"driver": "local", "options": {"max-size": "1m", "max-file": "1", "compress": "false"}}
    assert spec["services"]["runner"]["logging"] == {"driver": "none"}


def test_process_limits_timeout_and_sanitizes_output():
    # Trusted controller test helper, not a submitted project test.
    import sys
    async def run():
        r = await process([sys.executable, "-c", "print('x'*20000)"], 2, 1024)
        assert r.code == 0 and r.truncated and len(r.stdout) == 1024
        timed = await process([sys.executable, "-c", "import time; time.sleep(10)"], .05, 1024)
        assert timed.timeout and timed.code != 0
    asyncio.run(run())


def test_docker_absence_returns_blocked_receipt_not_pass(make_run, monkeypatch):
    monkeypatch.setattr("audit3.executor.shutil.which", lambda _: None)
    store, m = make_run()
    executor = Executor(store, m, Config(), Profile(name="synthetic"))
    r = asyncio.run(executor.execute(Request(kind="python", script="print('not run')", purpose="test blocked state"), "auditor", "initial"))
    assert r.execution == "not_executed" and r.status == "blocked" and r.exit_code is None
    assert r.stdout == "" and r.assertions is None


@pytest.mark.docker
def test_real_docker_blocks_network_credentials_and_writes(make_run):
    require_docker(Profile(name="synthetic"))
    store, m = make_run()
    executor = Executor(store, m, Config(), Profile(name="synthetic"))
    script = getsource(private_path_observation) + "\n" + """import os, socket
from pathlib import Path
assert not any(k in os.environ for k in ('OPENAI_API_KEY','GITHUB_TOKEN','SSH_AUTH_SOCK'))
print('CREDENTIAL_ENV_ABSENT', flush=True)
assert not Path('/var/run/docker.sock').exists()
print('DOCKER_SOCKET_ABSENT', flush=True)
print('SSH_PATH_' + private_path_observation(Path('/root/.ssh')).upper(), flush=True)
try:
    Path('/source/app.py').write_text('escape')
except OSError:
    pass
else:
    raise AssertionError('source writable')
print('SOURCE_WRITE_DENIED', flush=True)
for address in ('1.1.1.1', '169.254.169.254', '172.17.0.1'):
    try:
        socket.create_connection((address, 80), timeout=.3)
    except OSError:
        pass
    else:
        raise AssertionError('network escaped')
    print('NETWORK_CONNECT_BLOCKED ' + address, flush=True)
print('ISOLATION_PROBES_PASSED')
"""
    r = asyncio.run(executor.execute(Request(kind="python", script=script, purpose="real adversarial isolation validation"), "auditor", "initial"))
    save_receipt("isolation", store, m, r)
    assert r.status == "passed", r.model_dump()
    assert r.execution == "docker" and "ISOLATION_PROBES_PASSED" in r.stdout
