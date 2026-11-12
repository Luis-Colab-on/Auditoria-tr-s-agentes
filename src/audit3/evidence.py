from __future__ import annotations
import fcntl
import hmac
import json
import secrets
from contextlib import contextmanager
from pathlib import Path
from .security import PolicyError, atomic_write, canonical, contained, now, object_hash


class Store:
    """Controller-only authenticated records. The local owner is in the trust boundary."""
    def __init__(self, root: Path):
        self.root = root.absolute()
        if self.root.is_symlink():
            raise PolicyError("store symlink")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        key_path = contained(self.root, ".integrity-key")
        if not key_path.exists():
            try:
                with key_path.open("xb") as f:
                    key_path.chmod(0o600)
                    f.write(secrets.token_bytes(32))
            except FileExistsError:
                pass
        self.key = key_path.read_bytes()

    def path(self, run_id: str, name: str = "") -> Path:
        import re
        if not re.fullmatch(r"[a-f0-9]{24}", run_id):
            raise PolicyError("run_id inválido")
        base = contained(self.root, run_id)
        return contained(base, name) if name else base

    def put(self, run_id: str, name: str, value, *, immutable=False):
        path = self.path(run_id, name + ".json")
        if hasattr(value, "model_dump"):
            value = value.model_dump(mode="json")
        message = {"run_id": run_id, "name": name, "payload": value}
        record = {**message, "sha256": object_hash(message), "mac": hmac.digest(self.key, canonical(message), "sha256").hex()}
        if immutable and path.exists():
            if self.get(run_id, name) != value:
                raise PolicyError("registro congelado")
            return
        atomic_write(path, canonical(record))

    def get(self, run_id: str, name: str):
        record = json.loads(self.path(run_id, name + ".json").read_bytes())
        message = {k: record[k] for k in ("run_id", "name", "payload")}
        if record["run_id"] != run_id or record["name"] != name:
            raise PolicyError("registro de outra execução/namespace")
        if not hmac.compare_digest(record["mac"], hmac.digest(self.key, canonical(message), "sha256").hex()) or record["sha256"] != object_hash(message):
            raise PolicyError("registro adulterado")
        return record["payload"]

    def exists(self, run_id: str, name: str):
        return self.path(run_id, name + ".json").exists()

    def names(self, run_id: str, namespace: str):
        folder = self.path(run_id, namespace)
        return sorted(p.stem for p in folder.glob("*.json")) if folder.exists() else []

    def event(self, run_id: str, kind: str, data: dict):
        event_id = secrets.token_hex(12)
        self.put(run_id, "events/" + event_id, {"at": now(), "kind": kind, "data": data}, immutable=True)

    @contextmanager
    def lock(self, run_id: str):
        path = self.path(run_id, "controller.lock")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as f:
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as e:
                raise PolicyError("execução já está ativa") from e
            try:
                yield
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
