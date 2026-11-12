"""Run the eight explicit integration checks, preserving honest JUnit outcomes."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from .config import Config, Limits
from .diagnostics import diagnose
from .security import atomic_write, redact


CASES = [
    ("tests/test_executor.py::test_real_docker_blocks_network_credentials_and_writes", "Docker", "Isolamento: rede, credenciais e fonte readonly"),
    *[(f"tests/test_fixtures_integration.py::test_synthetic_project_in_real_container[{name}-{expected}]", "Docker", label)
      for name, expected, label in [("bug", "failed", "Defeito conhecido: 16 asserções / 1 mecanismo"), ("clean", "passed", "Código correto"), ("layered", "passed", "Proteção em outra camada"), ("rare", "failed", "Cenário raro, ocorrência real desconhecida")]],
    ("tests/test_fixtures_integration.py::test_three_real_agents_small_fixture", "Docker + Codex/ChatGPT", "Três agentes reais: fixture codex-smoke"),
    *[(f"tests/test_fixtures_integration.py::test_wordpress_mysql_email_browser_and_raw_egress[{kind}]", "Docker/Compose", label)
      for kind, label in [("php", "WordPress, MySQL, SMTP local e rede"), ("browser", "Playwright, REST/AJAX e login sintético")]],
]


def summarize_junit(path: Path):
    """Skipped or absent cases are never passed. Collection/errors remain visible."""
    observed = {}
    if path.exists():
        for item in ET.parse(path).iter("testcase"):
            observed[(item.get("classname", ""), item.get("name", ""))] = item
    result = []
    for nodeid, dependency, label in CASES:
        file, name = nodeid.split("::")
        item = observed.get((file[:-3].replace("/", "."), name))
        status, reason = "not_executed", "Sem resultado JUnit; execução não comprovada"
        if item is not None:
            bad = item.find("failure")
            if bad is None:
                bad = item.find("error")
            skipped = item.find("skipped")
            if bad is not None:
                status, reason = "failed", bad.get("message", "Falha registrada pelo pytest")
            elif skipped is not None:
                reason = skipped.get("message", "Pré-requisito ausente")
            else:
                status, reason = "passed", "Critérios de aceitação do teste satisfeitos"
        result.append({"nodeid": nodeid, "dependency": dependency, "label": label, "status": status, "reason": redact(reason)[:2000]})
    return result


def write_json(path, value):
    atomic_write(path, (redact(json.dumps(value, ensure_ascii=False, indent=2)) + "\n").encode())


def run_pytest(project: Path, destination: Path, env: dict, nodeids: list[str], *, focused=False):
    """Keep focused and full-run receipts, JUnit and streams in separate folders."""
    artifact_dir = destination / "evidence"
    artifact_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    child_env = {**env, "AUDIT3_VALIDATION_ARTIFACTS": str(artifact_dir)}
    command = [sys.executable, "-m", "pytest", "-q", "--tb=" + ("long" if focused else "short"),
        "-o", "junit_family=xunit2", "--junitxml=" + str(destination / "pending.xml"),
        "--basetemp=" + str(destination / "pytest-work"), *nodeids]
    try:
        child = subprocess.run(command, cwd=project, env=child_env, capture_output=True, text=True)
        exit_code, output = child.returncode, child.stdout + child.stderr
    except KeyboardInterrupt:
        exit_code, output = 130, "Validação interrompida pelo operador; consulte artefatos parciais."
    atomic_write(destination / "pytest-output.txt", redact(output).encode())
    junit = destination / "pending.xml"
    if junit.exists():
        atomic_write(junit, redact(junit.read_text()).encode())
    print(redact(output))
    return exit_code, summarize_junit(junit)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Integrações sintéticas; Codex real bloqueado até verificação financeira. Sem FAEPA.")
    parser.add_argument("--api", action="store_true", help="REMOVIDO: recusa sem chamadas")
    parser.add_argument("--codex", action="store_true", help="smoke Codex; ainda exige fatos financeiros e login privado")
    parser.add_argument("--financial-confirmation", type=Path, help="JSON com fatos conferidos pelo operador, nunca credenciais")
    parser.add_argument("--browser-first", action="store_true", help="validar browser com artefatos separados; integração completa só após aprovação")
    parser.add_argument("--max-calls", type=int, default=16)
    parser.add_argument("--total-seconds", type=int, default=900)
    args = parser.parse_args(argv)
    if args.api:
        parser.error("--api removido: API paga proibida, sem fallback; use --codex após verificação factual")
    if args.codex and not args.financial_confirmation:
        parser.error("Faltam fatos financeiros: --financial-confirmation; veja docs/codex-pro.md")
    config = Config(limits=Limits(max_calls=args.max_calls, total_seconds=args.total_seconds))
    project = Path(__file__).resolve().parents[2]
    if not (project / "tests/test_fixtures_integration.py").is_file():
        parser.error("execute no checkout de desenvolvimento com as fixtures sintéticas")
    session = project / "validation" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:8])
    session.mkdir(mode=0o700, parents=True)
    artifact_dir = session / "evidence"
    artifact_dir.mkdir(mode=0o700)
    write_json(session / "environment.json", diagnose())
    write_json(session / "config.json", config.model_dump(mode="json"))
    source_hashes = {}
    for folder in ("src", "tests", "scripts"):
        for path in sorted((project / folder).rglob("*")):
            generated = any(part == "__pycache__" or part.endswith(".egg-info") for part in path.parts)
            if path.is_file() and not generated and path.suffix in {".py", ".txt", ".json", ".php", ".md", ".cjs", ".sh"}:
                source_hashes[path.relative_to(project).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    for path in [project / "pyproject.toml", *project.glob("*.lock")]:
        source_hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    write_json(session / "implementation-hashes.json", source_hashes)
    env = dict(os.environ)
    env.update(AUDIT3_LIVE_TEST="1" if args.codex else "0", AUDIT3_WORDPRESS_TEST="1",
        AUDIT3_VALIDATION_CONFIG=str(session / "config.json"), AUDIT3_VALIDATION_ARTIFACTS=str(artifact_dir),
        PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
    # Never pass credentials to the validation child. Codex authenticates officially.
    for key in list(env):
        if any(w in key.upper() for w in ("API_KEY", "ACCESS_TOKEN", "SECRET", "PASSWORD")):
            env.pop(key)
    if args.financial_confirmation:
        env["AUDIT3_FINANCIAL_CONFIRMATION"] = str(args.financial_confirmation.absolute())
    env["AUDIT3_CODEX_STORE"] = str(project / ".audit3")
    env.pop("PYTEST_ADDOPTS", None)
    env.pop("PYTEST_PLUGINS", None)
    print(f"Evidências: {session}", flush=True)
    print(f"Backend Codex/ChatGPT; franquia Pro incluída; Astra Max/Extra High, Standard; limite operacional {args.max_calls}; verificação financeira obrigatória, consumo desconhecido", flush=True)
    browser_first = None
    full_suite_started = not args.browser_first
    if args.browser_first:
        browser_id = next(c[0] for c in CASES if c[0].endswith("[browser]"))
        exit_code, cases = run_pytest(project, session / "browser-first", env, [browser_id], focused=True)
        browser = next(c for c in cases if c["nodeid"] == browser_id)
        full_suite_started = exit_code == 0 and browser["status"] == "passed"
        browser_first = {"case": browser, "pytest_exit_code": exit_code,
            "full_suite_started": full_suite_started, "artifacts": "browser-first/"}
        write_json(session / "browser-first/results.json", browser_first)
        if not full_suite_started:
            for case in cases:
                if case["nodeid"] != browser_id:
                    case["reason"] = "Integração completa não iniciada: browser-first não foi aprovado"
            print("Integração completa não iniciada: veja browser-first/evidence e pytest-output.txt", flush=True)
    if full_suite_started:
        exit_code, cases = run_pytest(project, session, env, [case[0] for case in CASES])
    usage_paths = sorted(artifact_dir.glob("*-usage.json"))
    usage = [json.loads(path.read_text()) for path in usage_paths]
    calls = [call for record in usage for call in record["calls"]]
    cost = sum(call["cost_usd"] for call in calls) if calls and all(call["cost_usd"] is not None for call in calls) else None
    counts = {status: sum(case["status"] == status for case in cases) for status in ("passed", "failed", "not_executed")}
    summary = {"schema_version": "1.0", "at": datetime.now(timezone.utc).isoformat(), "pytest_exit_code": exit_code,
        "codex_smoke_requested": args.codex, "cases": cases, "counts": counts, "codex_turns_recorded": len(calls),
        "observed_estimated_cost_usd": cost, "cost_basis": "Pro: sem conversão por tarifa API; null = desconhecido",
        "scope": "somente fixtures sintéticas; FAEPA excluído", "operational_with_three_agents": all(case["status"] == "passed" for case in cases) and exit_code == 0}
    if browser_first is not None:
        summary["browser_first"] = browser_first
    write_json(session / "results.json", summary)
    lines = ["# Validação das oito integrações", "", "Somente fixtures sintéticas; FAEPA excluído.", "",
        "| Teste | Dependência | Resultado | Motivo |", "|---|---|---|---|"]
    labels = {"passed": "aprovado", "failed": "falhou", "not_executed": "não executado"}
    for case in cases:
        lines.append(f"| {case['label']} | {case['dependency']} | {labels[case['status']]} | {case['reason'].replace('|', '/').replace(chr(10), ' ')} |")
    lines += ["", f"Turnos Codex registrados: {len(calls)}. Consumo financeiro: desconhecido/não observado.", "",
        "Os testes bug e rare aprovam quando reproduzem a falha esperada da fixture. Isso não indica 16 defeitos nem ocorrência em produção.", "",
        "Fixtures corretas não medem recall de defeitos. Resultados do pytest não comprovam compreensão integral do código."]
    if browser_first is not None:
        lines += ["", "Browser primeiro: " + browser_first["case"]["status"] +
            "; integração completa iniciada: " + str(full_suite_started) +
            ". Os receipts e streams dessa etapa estão separados em browser-first/."]
    atomic_write(session / "report.md", ("\n".join(lines) + "\n").encode())
    write_json(session / "checksums.json", {p.relative_to(session).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(session.rglob("*")) if p.is_file() and "pytest-work" not in p.parts})
    print(json.dumps(counts, ensure_ascii=False))
    print(f"Relatório: {session / 'report.md'}")
    return 1 if exit_code not in {0, 5} or counts["failed"] else (2 if counts["not_executed"] else 0)
