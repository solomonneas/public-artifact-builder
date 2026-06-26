from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class SourceRef(BaseModel):
    path: str
    kind: str
    confidence: float = Field(ge=0, le=1)


class StackItem(BaseModel):
    name: str
    category: str
    confidence: float = Field(ge=0, le=1)
    sources: list[SourceRef] = Field(default_factory=list)


class Component(BaseModel):
    name: str
    kind: str
    description: str = ""
    sources: list[SourceRef] = Field(default_factory=list)


class Workflow(BaseModel):
    name: str
    trigger: str = ""
    steps: list[str] = Field(default_factory=list)
    sources: list[SourceRef] = Field(default_factory=list)


class EntryPoint(BaseModel):
    name: str
    path: str
    command: str = ""
    kind: str = "source"


class DeploymentClue(BaseModel):
    name: str
    kind: str
    path: str
    detail: str = ""


class Risk(BaseModel):
    name: str
    severity: Literal["low", "medium", "high"]
    detail: str
    sources: list[SourceRef] = Field(default_factory=list)


class PublicClaim(BaseModel):
    claim: str
    confidence: float = Field(ge=0, le=1)
    sources: list[SourceRef] = Field(default_factory=list)


class GitMetadata(BaseModel):
    available: bool = False
    current_branch: str | None = None
    latest_commit: str | None = None
    latest_commit_date: str | None = None
    remote_hosts: list[str] = Field(default_factory=list)


class PrivacyFinding(BaseModel):
    type: str
    severity: Literal["low", "medium", "high"]
    path: str
    line: int | None = None
    evidence: str
    remediation: str


class PrivacyReport(BaseModel):
    mode: Literal["standard", "strict"]
    status: Literal["pass", "blocked"]
    findings: list[PrivacyFinding] = Field(default_factory=list)

    @property
    def high_risk_count(self) -> int:
        return sum(1 for finding in self.findings if finding.severity == "high")


class SkippedFile(BaseModel):
    path: str
    reason: str


class ArtifactMap(BaseModel):
    schema_version: str = "1.0"
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    project_name: str
    source: str
    audience: str
    privacy: PrivacyReport
    summary: str
    detected_stack: list[StackItem] = Field(default_factory=list)
    components: list[Component] = Field(default_factory=list)
    services: list[Component] = Field(default_factory=list)
    workflows: list[Workflow] = Field(default_factory=list)
    data_stores: list[Component] = Field(default_factory=list)
    entrypoints: list[EntryPoint] = Field(default_factory=list)
    deployment_clues: list[DeploymentClue] = Field(default_factory=list)
    risks: list[Risk] = Field(default_factory=list)
    public_safe_claims: list[PublicClaim] = Field(default_factory=list)
    git: GitMetadata = Field(default_factory=GitMetadata)
    assets: list[str] = Field(default_factory=list)
    skipped_files: list[SkippedFile] = Field(default_factory=list)


class ScanResult(BaseModel):
    repo_path: Path
    project_name: str
    source: str
    files: list[Path]
    text_files: dict[str, str]
    assets: list[str]
    git: GitMetadata
    skipped_files: list[SkippedFile] = Field(default_factory=list)
