"""Codex is the sole generation backend; historical API helpers cannot generate."""
from __future__ import annotations
import asyncio
import secrets
from .security import PolicyError, now


class BudgetExceeded(RuntimeError):
    pass


class RuntimePaused(PolicyError):
    """Precondition failed; never treat as invalid model output or retry it."""


class AmbiguousTurn(RuntimePaused):
    pass


def retryable_api_error(error):
    """Historical offline compatibility only. There is no API retry path."""
    body = getattr(error, "body", None)
    details = body.get("error", body) if isinstance(body, dict) else {}
    details = details if isinstance(details, dict) else {}
    codes = {str(getattr(error, "code", "")), str(details.get("code", "")), str(details.get("type", ""))}
    return not any(any(word in code.lower() for word in ("quota", "billing", "credit", "spend", "budget", "usage_limit")) for code in codes)


class Budget:
    """Finite operational limits, NOT an atomic financial guard."""
    def __init__(self, store, run_id, config):
        self.store, self.run_id, self.config = store, run_id, config
        self.lock = asyncio.Lock()

    async def reserve(self, role, invocation_id):
        async with self.lock:
            ledger = self.store.get(self.run_id, "ledger")
            if len(ledger["calls"]) >= self.config.limits.max_calls:
                raise BudgetExceeded("limite operacional de turnos atingido")
            if self.store.exists(self.run_id, "cancel"):
                raise asyncio.CancelledError
            cid = secrets.token_hex(12)
            ledger["calls"].append({"id": cid, "role": role, "invocation_id": invocation_id,
                "started_at": now(), "status": "in_flight", "cost_usd": None,
                "input_tokens": None, "output_tokens": None})
            self.store.put(self.run_id, "ledger", ledger)
            return cid

    async def finish(self, cid, usage=None, error=None):
        async with self.lock:
            ledger = self.store.get(self.run_id, "ledger")
            entry = next(c for c in ledger["calls"] if c["id"] == cid)
            entry.update(finished_at=now(), status="error" if error else "completed", error=error)
            if usage is not None:
                entry["input_tokens"] = getattr(usage, "input_tokens", None)
                entry["output_tokens"] = getattr(usage, "output_tokens", None)
                if getattr(usage, "official_sample", None):
                    entry["official_token_sample"] = usage.official_sample
            ledger["known_cost_usd"] = None
            ledger["unknown_cost_calls"] = len(ledger["calls"])
            ledger["tokens"] = None if any(c["input_tokens"] is None or c["output_tokens"] is None for c in ledger["calls"]) else sum(c["input_tokens"] + c["output_tokens"] for c in ledger["calls"])
            self.store.put(self.run_id, "ledger", ledger)


class SDKRuntime:
    """Tombstone: older callers fail before importing any paid SDK."""
    def __init__(self, *args, **kwargs):
        raise PolicyError("Backend Agents SDK/API removido. Prepare nova execução Codex/ChatGPT; sem fallback pago.")
