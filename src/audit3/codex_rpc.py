"""Version-pinned local stdio transport. Never logs wire frames or credentials."""
from __future__ import annotations
import asyncio
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from .agents import RuntimePaused

CLI_VERSION = "0.167.0"
BACKEND = "codex-app-server"
ALLOWED_METHODS = frozenset({'initialize', 'initialized', 'config/read', 'account/read',
    'model/list', 'account/rateLimits/read', 'thread/start', 'thread/resume', 'turn/start', 'turn/interrupt'})


class DispatchExpired(TimeoutError):
    """The new request was blocked before writing any bytes."""


@dataclass
class TurnDispatch:
    deadline_at: float
    deadline_origin: str
    financial_guard: Callable[[], object]
    write_attempted: bool = False
    written: bool = False

    def check(self):
        # Recheck the factual wall-clock expiry as well as the immutable
        # monotonic deadline. No persistence or serialization follows this check.
        self.financial_guard()
        if asyncio.get_running_loop().time() >= self.deadline_at:
            raise DispatchExpired(self.deadline_origin)

    @property
    def status(self):
        return 'written' if self.written else ('write_uncertain' if self.write_attempted else 'not_sent')


def clean_environment(home: Path):
    # An allowlist also removes provider keys, proxy variables, CODEX overrides,
    # Python/Node injection, cloud credentials and inherited session identifiers.
    return {"PATH": os.defpath, "HOME": str(home), "CODEX_HOME": str(home),
            "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}


class StdioRPC:
    def __init__(self, executable, home, cwd, timeout=20):
        self.executable, self.home, self.cwd, self.timeout = executable, home, cwd, timeout
        self.pending, self.sequence = {}, 0
        self.events = asyncio.Queue(maxsize=256)
        self.proc = self.reader = None

    async def start(self):
        self.proc = await asyncio.create_subprocess_exec(self.executable, "app-server", "--stdio", "--strict-config",
            cwd=self.cwd, env=clean_environment(self.home), stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL, limit=2_000_000)
        self.reader = asyncio.create_task(self._read())
        await self.request("initialize", {"clientInfo": {"name": "audit3", "version": "0.2.0"},
            "capabilities": {"experimentalApi": True}})
        await self.send({"method": "initialized", "params": {}})
        return self

    async def _read(self):
        try:
            while raw := await self.proc.stdout.readline():
                msg = json.loads(raw)
                if "method" not in msg and "id" in msg:
                    future = self.pending.get(msg["id"])
                    if future and not future.done():
                        if "error" in msg:
                            future.set_exception(RuntimePaused("App Server recusou RPC; código " + str(msg["error"].get("code"))))
                        else:
                            future.set_result(msg.get("result", {}))
                else:
                    # Backpressure: overflow is a lost-observability failure, never dropped.
                    self.events.put_nowait(msg)
            raise RuntimePaused("App Server encerrou transporte")
        except asyncio.CancelledError:
            return
        except Exception:
            for f in self.pending.values():
                if not f.done():
                    f.set_exception(RuntimePaused("Transporte Codex indisponível/observabilidade perdida"))
            # Wake a turn listener even when the queue was full.
            if self.events.full():
                self.events.get_nowait()
            self.events.put_nowait({"method": "audit3/transportLost"})

    async def send(self, data, *, dispatch=None):
        if 'method' in data and data['method'] not in ALLOWED_METHODS:
            raise RuntimePaused('RPC fora do escopo: operações de conta/faturamento e alternativas não autorizadas são bloqueadas')
        if data.get('method') == 'turn/start' and not isinstance(dispatch, TurnDispatch):
            raise RuntimePaused('turn/start exige proteção explícita de prazo no despacho')
        wire = (json.dumps(data, ensure_ascii=False) + "\n").encode()
        if dispatch is not None:
            dispatch.check()
            # Once write is attempted, an exception may mean a partial write.
            # Only a guard/serialization failure proves that nothing was sent.
            dispatch.write_attempted = True
        self.proc.stdin.write(wire)
        if dispatch is not None:
            dispatch.written = True
        await self.proc.stdin.drain()

    async def request(self, method, params, *, dispatch=None):
        self.sequence += 1
        ident = self.sequence
        future = asyncio.get_running_loop().create_future()
        self.pending[ident] = future
        try:
            await self.send({"id": ident, "method": method, "params": params}, dispatch=dispatch)
            return await asyncio.wait_for(future, self.timeout)
        finally:
            self.pending.pop(ident, None)

    async def respond(self, ident, result):
        await self.send({"id": ident, "result": result})

    async def close(self):
        if self.reader:
            self.reader.cancel()
            await asyncio.gather(self.reader, return_exceptions=True)
        if self.proc and self.proc.returncode is None:
            self.proc.terminate()
            try:
                await asyncio.wait_for(self.proc.wait(), 3)
            except TimeoutError:
                self.proc.kill()
                try:
                    await asyncio.wait_for(self.proc.wait(), 3)
                except TimeoutError:
                    raise RuntimePaused("Encerramento do App Server não confirmado; backend bloqueado") from None
