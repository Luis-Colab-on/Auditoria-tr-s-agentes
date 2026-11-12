from __future__ import annotations

from enum import StrEnum
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    schema_version: Literal["1.0"] = "1.0"


class Role(StrEnum):
    AUDITOR = "auditor"
    DEFENDER = "defensor"
    JUDGE = "juiz"


class Classification(StrEnum):
    PROVEN = "falha comprovada"
    RISK = "risco fundamentado"
    HYPOTHESIS = "hipótese não confirmada"
    FALSE_POSITIVE = "falso positivo"
    OPTIONAL = "melhoria opcional"
    ADEQUATE = "implementação adequada"


class Decision(StrEnum):
    FIX = "corrigir agora"
    SCHEDULE = "programar correção"
    INVESTIGATE = "investigar"
    ACCEPT = "documentar/aceitar por ora"
    KEEP = "manter"
    DROP = "descartar"


class FileRecord(Contract):
    path: str
    sha256: str
    size: int = Field(ge=0)
    lines: int = Field(ge=0)
    category: Literal["source", "spec", "test", "config", "migration", "prior_report", "excluded"]
    reason: str | None = None


class RunManifest(Contract):
    backend: str = Field(default="openai-agents", exclude_if=lambda value: value == "openai-agents")
    client_version: str | None = Field(default=None, exclude_if=lambda value: value is None)
    models: dict[str, str] | None = Field(default=None, exclude_if=lambda value: value is None)
    run_id: str
    created_at: str
    source_kind: Literal["git", "zip", "github"]
    source_id: str
    commit: str | None
    origin: str | None
    tree_state: str
    submodules: list[str] = Field(default_factory=list)
    lfs: list[str] = Field(default_factory=list)
    files: list[FileRecord]
    config_hash: str
    profile_hash: str
    prompt_hashes: dict[str, str]
    requirements: str
    limitations: list[str] = Field(default_factory=list)
    estimated_input_tokens: int
    estimated_calls: int
    prior_report_policy: str = "quarentena até publicação dos três pareceres iniciais"


class SourceRef(Contract):
    path: str
    start: int = Field(ge=1)
    end: int = Field(ge=1)
    sha256: str

    @model_validator(mode="after")
    def ordered(self):
        if self.end < self.start:
            raise ValueError("intervalo invertido")
        return self


class InspectionRecord(Contract):
    refs: list[SourceRef]
    requirement: str = Field(min_length=1)
    analysis: str = Field(min_length=1, max_length=12000)
    flow_verified: bool
    flow_description: str
    limitations: list[str]


class CandidateFinding(Contract):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    source_id: str
    title: str
    mechanism: str = Field(min_length=1)
    refs: list[SourceRef] = Field(min_length=1)
    invariant: str
    trigger: str
    necessary_conditions: list[str]
    complete_flow: str
    protections_considered: list[str]
    expected: str
    observed: str
    evidence_ids: list[str]
    proof_method: Literal["executed", "static", "unconfirmed"]
    static_demonstration: str | None
    limitations: list[str]
    impact: str
    real_environment_relevance: str
    production_observation: Literal["unknown", "not_observed", "observed_with_evidence"]
    production_evidence: str | None
    origin: Literal["preexisting", "new", "unknown"]
    origin_evidence_ids: list[str]

    @model_validator(mode="after")
    def proof(self):
        if self.proof_method == "executed" and not self.evidence_ids:
            raise ValueError("reprodução exige receipt")
        if self.proof_method == "static" and not self.static_demonstration:
            raise ValueError("prova estática exige demonstração")
        if self.origin != "unknown" and not self.origin_evidence_ids:
            raise ValueError("origem exige evidência de comparação")
        if self.production_observation == "observed_with_evidence" and not self.production_evidence:
            raise ValueError("produção exige evidência, fixture não demonstra ocorrência")
        return self


class AgentPosition(Contract):
    finding_id: str
    classification: Classification
    decision: Decision
    argument: str
    evidence_ids: list[str]
    changed_position: bool


class Opinion(Contract):
    summary: str
    inspections: list[InspectionRecord]
    findings: list[CandidateFinding]
    positions: list[AgentPosition]
    limitations: list[str]


class Verdict(Contract):
    finding_id: str
    classification: Classification
    decision: Decision
    rationale: str = Field(min_length=1)
    evidence_ids: list[str]
    proof_method: Literal["executed", "static", "unconfirmed"]
    impact: str
    reach: str
    correction_cost: str
    regression_risk: str
    reversibility: str
    test_interpretation: str
    mandatory_justification: str | None
    root_cause_id: str | None

    @model_validator(mode="after")
    def justified(self):
        if self.classification == Classification.PROVEN and self.proof_method == "unconfirmed":
            raise ValueError("falha comprovada exige método de prova")
        if self.decision in {Decision.FIX, Decision.SCHEDULE}:
            if self.classification not in {Classification.PROVEN, Classification.RISK}:
                raise ValueError("hipótese/estilo/consenso não impõe correção")
            if not self.mandatory_justification:
                raise ValueError("correção exige justificativa concreta")
        return self


class Judgment(Contract):
    summary: str
    baseline_assessment: str | None = None
    verdicts: list[Verdict]
    new_findings: list[CandidateFinding]
    limitations: list[str]


class TestRequest(Contract):
    kind: Literal["baseline", "python", "php", "browser", "wp-cli"]
    script: str = Field(default="", max_length=40000)
    purpose: str = Field(min_length=3, max_length=2000)
    repeat_reason: Literal["independent_reproduction", "confirm_failure", "intermittency"] | None = None


class EvidenceReceipt(Contract):
    id: str
    run_id: str
    owner: str
    phase: str
    source_id: str
    profile_hash: str
    fingerprint: str
    command: list[str]
    image_ids: dict[str, str]
    versions: dict[str, str]
    started_at: str
    finished_at: str
    status: Literal["passed", "failed", "skipped", "blocked", "not_executed", "cancelled"]
    exit_code: int | None
    timeout: bool
    stdout: str
    stderr: str
    stdout_sha256: str
    stderr_sha256: str
    output_truncated: bool
    script_sha256: str | None
    purpose: str
    limitations: list[str]
    artifacts: dict[str, str] = Field(default_factory=dict)
    suites: int | None = None
    cases: int | None = None
    assertions: int | None = None
    failed_assertions: int | None = None
    execution: Literal["docker", "compose", "not_executed", "mock"]
