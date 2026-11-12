"""Read-only, credential-free environment diagnostics; also works without the SDK."""
from __future__ import annotations
import errno
import json
import os
import platform
import shutil
import socket
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def network_permission():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM):
            pass
        return {"status": "available"}
    except OSError as exc:
        return {"status": "denied" if exc.errno in {errno.EPERM, errno.EACCES} else "error", "errno": exc.errno, "error_type": type(exc).__name__}


def local_command(argv):
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": "/nonexistent", "LANG": "C.UTF-8"}
    try:
        result = subprocess.run(argv, env=env, capture_output=True, timeout=15, text=True)
        # Return only exit code and version stdout; errors may contain private paths.
        return {"returncode": result.returncode, "version": result.stdout.strip()[:200] if result.returncode == 0 else None}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"returncode": None, "error_type": type(exc).__name__}


def diagnose(probe_network=False):
    result = {"schema_version": "1.0", "at": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(), "platform": platform.system(), "kernel": platform.release(),
        "api_key_present": bool(os.environ.get("OPENAI_API_KEY")), "scope": "current_process_environment_only",
        "network_changes": False, "api_generation_requests": 0, "ipv4_socket": network_permission()}
    for key, path in (("pid1_comm", "/proc/1/comm"), ("kernel_version", "/proc/version")):
        try:
            result[key] = Path(path).read_text().strip()[:300]
        except OSError:
            result[key] = None
    try:
        result["restrictions"] = dict(line.split(":", 1) for line in Path("/proc/self/status").read_text().splitlines() if line.split(":", 1)[0] in {"NoNewPrivs", "Seccomp", "Seccomp_filters", "NSpid"})
        result["restrictions"] = {k:v.strip() for k,v in result["restrictions"].items()}
        result["route_count"] = max(0, len(Path("/proc/net/route").read_text().splitlines()) - 1)
    except OSError:
        result["restrictions"], result["route_count"] = {}, None
    result["namespaces"] = {}
    for name in ("net", "pid", "mnt", "user"):
        try:
            result["namespaces"][name] = os.readlink("/proc/self/ns/" + name)
        except OSError:
            result["namespaces"][name] = None
    result["docker"] = {"cli_visible": shutil.which("docker") is not None,
        "default_socket_visible": Path("/var/run/docker.sock").exists(),
        "rootless_socket_visible": Path(f"/run/user/{os.getuid()}/docker.sock").exists() if hasattr(os, "getuid") else False}
    if result["docker"]["cli_visible"]:
        result["docker"]["client"] = local_command(["docker", "--version"])
        # Explicit local socket: never probe an inherited remote production context.
        result["docker"]["local_server"] = local_command(["docker", "--host", "unix:///var/run/docker.sock", "version", "--format", "{{.Server.Version}}"])
        result["docker"]["compose"] = local_command(["docker", "compose", "version", "--short"])
    if result["ipv4_socket"]["status"] == "denied":
        result["network_conclusion"] = "socket_policy_denial_before_dns; does_not_establish_host_wsl_dns_failure"
    else:
        result["network_conclusion"] = "needs_dns_https_observation"
    result["network_probes"] = {}
    if probe_network and result["ipv4_socket"]["status"] == "available":
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for host, url in (("api.openai.com", "https://api.openai.com/v1/models"), ("pypi.org", "https://pypi.org/simple/")):
            entry = {}
            try:
                entry["dns_resolved"] = bool(socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM))
                try:
                    with opener.open(url, timeout=8) as response:
                        entry["https_status"] = response.status
                except urllib.error.HTTPError as exc:
                    entry["https_status"] = exc.code
            except OSError as exc:
                entry["error_type"] = type(exc).__name__
                entry["errno"] = getattr(exc, "errno", None)
            result["network_probes"][host] = entry
        if all(entry.get("dns_resolved") and entry.get("https_status") for entry in result["network_probes"].values()):
            result["network_conclusion"] = "dns_and_https_observed_in_this_process; authentication_generation_not_verified"
    elif probe_network:
        result["network_probes"] = {"status": "not_executed_socket_policy_denied"}
    return result


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description="Diagnóstico somente leitura, sem revelar chave ou alterar rede")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--probe-network", action="store_true", help="DNS e HTTPS sem autenticação e sem inferência")
    args = parser.parse_args(argv)
    result = diagnose(args.probe_network)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
