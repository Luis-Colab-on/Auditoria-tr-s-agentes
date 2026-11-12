from __future__ import annotations
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath


class PolicyError(ValueError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical(value) -> bytes:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def object_hash(value) -> str:
    return digest(canonical(value))


def safe_relative(value: str) -> str:
    if not value or len(value) > 512 or "\\" in value or ":" in value or "\x00" in value:
        raise PolicyError("caminho inválido")
    if any(ord(c) < 32 for c in value):
        raise PolicyError("controle em caminho")
    p = PurePosixPath(value)
    if p.is_absolute() or PureWindowsPath(value).drive or any(x in {"", ".", ".."} for x in value.split("/")):
        raise PolicyError("caminho fora do escopo")
    if any(x.lower().split(".")[0] in {"con", "nul", "aux", "prn", *(f"com{i}" for i in range(1,10)), *(f"lpt{i}" for i in range(1,10))} or x.endswith((" ", ".")) for x in p.parts):
        raise PolicyError("nome não portátil")
    return p.as_posix()


def contained(root: Path, relative: str) -> Path:
    rel = safe_relative(relative)
    root = root.absolute()
    if root.is_symlink():
        raise PolicyError("raiz symlink proibida")
    current = root
    for part in PurePosixPath(rel).parts:
        current = current / part
        if current.is_symlink():
            raise PolicyError("symlink proibido")
    if not current.resolve().is_relative_to(root.resolve()):
        raise PolicyError("escape de caminho")
    return current


PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"(?:ghp_|github_pat_)[A-Za-z0-9_]{16,}"),
    re.compile(r"AKIA[A-Z0-9]{16}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]*?-----END [^-]+-----"),
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b"),
    re.compile(r"(?im)(?:api[_-]?key|password|passwd|secret|access[_-]?token)\s*[=:]\s*[\"']?([^\s\"',;}]{8,})"),
]


def sensitive(text: str) -> bool:
    return any(p.search(text) for p in PATTERNS)


def redact(text: str) -> str:
    for pattern in PATTERNS:
        text = pattern.sub("[OMITIDO]", text)
    # No secret is printed even when a tool/SDK exception happens to echo the key.
    for name in ("OPENAI_API_KEY", "GITHUB_TOKEN", "GH_TOKEN"):
        secret = os.environ.get(name)
        if secret and len(secret) > 5:
            text = text.replace(secret, "[OMITIDO]")
    return text


def atomic_write(path: Path, data: bytes, mode: int = 0o600):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():
        raise PolicyError("destino symlink proibido")
    fd, temp = tempfile.mkstemp(prefix=".atomic-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            os.fchmod(f.fileno(), mode)
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
