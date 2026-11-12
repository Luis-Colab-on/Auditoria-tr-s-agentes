from __future__ import annotations
import json
from pathlib import Path
from importlib.resources import files
from typing import Literal
from pydantic import Field, model_validator
from .schemas import Contract, Role


class Limits(Contract):
    concurrency: int = Field(default=1, ge=1, le=3)
    max_turns: int = Field(default=12, ge=1, le=100)
    call_timeout: int = Field(default=120, ge=1, le=1800)
    test_timeout: int = Field(default=60, ge=1, le=1800)
    total_seconds: int = Field(default=1800, ge=1, le=86400)
    max_calls: int = Field(default=48, ge=1, le=1000)
    max_output_tokens: int = Field(default=5000, ge=256, le=32000)
    max_output_bytes: int = Field(default=64000, ge=1024, le=1000000)
    max_input_bytes: int = Field(default=250000, ge=1000, le=2000000)
    max_reproductions: int = Field(default=12, ge=0, le=100)
    max_repeats: int = Field(default=1, ge=0, le=2)
    transient_retries: int = Field(default=0, ge=0, le=2)
    invalid_output_retries: int = Field(default=1, ge=0, le=1)
    batch_lines: int = Field(default=600, ge=50, le=4000)
    read_lines: int = Field(default=160, ge=1, le=500)
    budget_usd: float = Field(default=5, gt=0, allow_inf_nan=False)
    call_reserve_usd: float = Field(default=0.10, gt=0, allow_inf_nan=False)


class Config(Contract):
    backend: Literal["codex-app-server"] = "codex-app-server"
    models: dict[Role, str] = Field(default_factory=lambda: {r: "gpt-6-astra" for r in Role})
    limits: Limits = Field(default_factory=Limits)
    # Historical fields are readable but never used for Codex/Pro accounting.
    input_usd_per_million: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    output_usd_per_million: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    exclude: list[str] = Field(default_factory=list)
    prior_reports: list[str] = Field(default_factory=lambda: ["audits/**", "audit-reports/**"])
    github_allowlist: list[str] = Field(default_factory=list)
    max_files: int = Field(default=10000, ge=1, le=100000)
    max_file_bytes: int = Field(default=2_000_000, ge=1, le=20_000_000)
    max_total_bytes: int = Field(default=100_000_000, ge=1, le=500_000_000)

    @model_validator(mode="after")
    def roles(self):
        if set(self.models) != set(Role):
            raise ValueError("configure exatamente Auditor, Defensor e Juiz")
        if any(m != "gpt-6-astra" for m in self.models.values()):
            raise ValueError("somente gpt-6-astra autorizado nos três papéis")
        return self


class Profile(Contract):
    name: str
    engine: Literal["docker", "compose"] = "docker"
    image: str = "python:3.12.8-slim-bookworm"
    baseline: list[str] = Field(default_factory=lambda: ["python", "-B", "-m", "unittest", "discover", "-s", "/source/tests", "-v"])
    languages: list[Literal["python", "php", "browser", "wp-cli"]] = Field(default_factory=lambda: ["python"])
    memory_mb: int = Field(default=512, ge=128, le=4096)
    # Omit the unset override to preserve hashes/limits of already frozen profiles.
    db_memory_mb: int | None = Field(default=None, ge=128, le=4096, exclude_if=lambda value: value is None)
    cpus: float = Field(default=1, gt=0, le=4)
    pids: int = Field(default=128, ge=16, le=512)
    wp_image: str = "audit3-wordpress:local"
    db_image: str = "mysql:8.4.3"
    browser_image: str = "audit3-browser:local"
    service_image: str = "python:3.12.8-slim-bookworm"
    plugin_slug: str = Field(default="synthetic-plugin", pattern=r"^[a-z0-9_-]+$")
    woocommerce_required: bool = False
    required_plugins: list[str] = Field(default_factory=list)


def load_config(path: Path | None) -> Config:
    return Config.model_validate_json(path.read_text()) if path else Config()


def load_profile(name: str) -> Profile:
    if name in {"generic", "wordpress", "faepa"}:
        return Profile.model_validate_json(files("audit3").joinpath("profiles", name + ".json").read_text())
    # Explicit operator path, never autodiscovered inside an audited repository.
    return Profile.model_validate_json(Path(name).read_text())
