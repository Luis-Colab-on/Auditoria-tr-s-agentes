from __future__ import annotations
import argparse
import asyncio
import importlib.metadata
import importlib.util
import json
import os
import platform
import shutil
import socket
from pathlib import Path
from .config import load_config, load_profile
from .evidence import Store
from .security import PolicyError, now, redact


def emit(value):
    print(redact(json.dumps(value, ensure_ascii=False, indent=2, default=str)))


def doctor(config=None, probe_api=False):
    if probe_api:
        raise PolicyError("--probe-api removido: API paga proibida; use doctor --probe-codex")
    from .diagnostics import diagnose
    from .codex_rpc import BACKEND, CLI_VERSION
    from .codex_policy import executable
    result = {"python": platform.python_version(), "backend": BACKEND, "required_client": CLI_VERSION,
        "model": "gpt-6-astra", "effort": "Max, ou Extra High se oficialmente disponível", "speed": "Standard",
        "authentication": "unknown", "financial": "unknown; geração bloqueada até comprovação factual",
        "usage": "franquia incluída Pro; saldo/recarga desconhecidos; sem estimativa API em dólares",
        "environment": diagnose(), "api_generation": "disabled_no_fallback"}
    try:
        import subprocess
        result["client"] = subprocess.run([executable(), "--version"], capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        result["client"] = "unknown"
    return result


async def probe_codex(root):
    from .codex_policy import setup_home, executable, verify_client, account_identity, select_effort, check_effective_config
    from .codex_rpc import StdioRPC
    home = setup_home(root.absolute() / "codex-home")
    binary = executable()
    verify_client(binary, home)
    rpc = StdioRPC(binary, home, home / "empty")
    try:
        await rpc.start()
        check_effective_config((await rpc.request("config/read", {"includeLayers": False}))["config"], home)
        account = (await rpc.request("account/read", {"refreshToken": False})).get("account")
        identity = account_identity(account)
        effort = select_effort((await rpc.request("model/list", {"limit": 100}))["data"])
        quota = await rpc.request("account/rateLimits/read", {})
        return {"authentication": "chatgpt", "plan": account['planType'], "account_fingerprint": identity, "model": "gpt-6-astra",
            "effort": effort, "speed": "Standard", "ordinary_usage_allowed": quota.get("ordinaryUsageAllowed"),
            "financial": "auto-recharge not exposed by this protocol; factual confirmation still required", "generation_calls": 0}
    finally:
        await rpc.close()


def main(argv=None):
    parser = argparse.ArgumentParser(prog="audit3", description="Auditoria local com três agentes reais via Codex/ChatGPT; nenhum projeto é corrigido.")
    parser.add_argument("--store", type=Path, default=Path(".audit3"), help="diretório local privado de estado")
    sub = parser.add_subparsers(dest="command", required=True)
    d = sub.add_parser("doctor")
    d.add_argument("--probe-api", action="store_true", help="REMOVIDO: falha sem acessar API")
    d.add_argument("--config", type=Path)
    d.add_argument("--probe-codex", action="store_true", help="consultar conta/modelos/quota via App Server, sem gerar texto")
    sub.add_parser("codex-setup", help="preparar configuração privada e mostrar comando oficial de login")
    f = sub.add_parser("financial-confirm", help="registrar fatos conferidos pelo operador no painel oficial, sem mudar faturamento")
    f.add_argument("id")
    f.add_argument("--account-fingerprint", required=True)
    f.add_argument("--auto-recharge", required=True, choices=["disabled"])
    f.add_argument("--extra-credits", required=True, choices=["none"])
    f.add_argument("--checked-at", required=True, help="horário real da conferência, ISO 8601 com fuso; nunca a hora de registro presumida")
    p = sub.add_parser("prepare")
    p.add_argument("--repo", required=True, help="repositório local, ZIP ou URL GitHub permitida")
    p.add_argument("--ref")
    p.add_argument("--profile", default="generic")
    p.add_argument("--config", type=Path)
    p.add_argument("--requirements", type=Path)
    r = sub.add_parser("run")
    r.add_argument("--prepared", required=True)
    comparison = sub.add_parser("compare", help="registrar comparação factual antes/depois")
    comparison.add_argument("--before", required=True)
    comparison.add_argument("--after", required=True)
    comparison.add_argument("--purpose", required=True)
    for command in ("status", "resume", "cancel", "report", "export"):
        sp = sub.add_parser(command)
        sp.add_argument("id")
        if command == "export":
            sp.add_argument("--output", type=Path)
            sp.add_argument("--evidence", action="append")
    args = parser.parse_args(argv)
    try:
        if args.command == "doctor":
            result = doctor(load_config(args.config), args.probe_api)
            if args.probe_codex:
                result["official_metadata"] = asyncio.run(probe_codex(args.store))
            emit(result)
            return 0
        store = Store(args.store)
        if args.command == "codex-setup":
            from .codex_policy import setup_home
            import shlex
            home = setup_home(store.root / "codex-home")
            emit({"home": str(home), "login_command": "env -i PATH=/usr/bin:/bin HOME=" + shlex.quote(str(home)) + " CODEX_HOME=" + shlex.quote(str(home)) + " " + shlex.quote(__import__('audit3.codex_policy', fromlist=['executable']).executable()) + ' login --device-auth', "generation": "blocked until account/financial verification"})
            return 0
        if args.command == "financial-confirm":
            from .codex_policy import financial_remaining
            store.get(args.id, "manifest")
            remaining = financial_remaining(args.checked_at)
            store.put(args.id, "financial-confirmation", {"source": "operator_factual_confirmation", "checked_at": args.checked_at,
                "account_fingerprint": args.account_fingerprint, "auto_recharge": args.auto_recharge, "extra_credits": args.extra_credits})
            emit({"recorded": "operator facts; checked again against official account/quota before generation", "checked_at": args.checked_at, "remaining_valid_seconds": remaining})
            return 0
        if args.command == "compare":
            from .comparison import register_comparison
            emit(register_comparison(store, args.before, args.after, args.purpose))
            return 0
        if args.command == "prepare":
            from .snapshot import prepare
            m = prepare(store, args.repo, args.ref, load_profile(args.profile), load_config(args.config), args.requirements.read_text() if args.requirements else "")
            emit({"prepared": m.run_id, "source_id": m.source_id, "inventory_files": len(m.files), "estimated_input_tokens": m.estimated_input_tokens,
                "estimated_runner_calls": m.estimated_calls, "model_turns": 0, "next": "Revise inventário/omissões e execute audit3 run --prepared ID. O código consultado será processado remotamente pela OpenAI via Codex."})
            return 0
        run_id = args.prepared if args.command == "run" else args.id
        if args.command in {"run", "resume"}:
            from .workflow import Workflow
            state = asyncio.run(Workflow(store, run_id).run(resume=args.command == "resume"))
            emit(state)
            return 0 if state["status"] == "completed" else 2
        if args.command == "status":
            emit({"state": store.get(run_id, "state"), "usage": store.get(run_id, "ledger"), "cancel_requested": store.exists(run_id, "cancel")})
        elif args.command == "cancel":
            store.get(run_id, "state")
            store.put(run_id, "cancel", {"requested_at": now()})
            emit({"run_id": run_id, "cancel_requested": True})
        elif args.command == "report":
            from .report import markdown, write_report
            print(markdown(write_report(store, run_id)))
        elif args.command == "export":
            from .report import export_zip
            path = export_zip(store, run_id, args.output or Path("audit3-" + run_id + ".zip"), args.evidence)
            emit({"export": str(path)})
        return 0
    except (PolicyError, ValueError, OSError, KeyError) as exc:
        emit({"error": redact(str(exc))[:2000]})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
