from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from reweft.domain.models import KnowledgeState, utc_now


class RuntimeModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PostgresSourceConfiguration(RuntimeModel):
    host: str = Field(min_length=1, max_length=253, pattern=r"^[A-Za-z0-9._-]+$")
    port: int = Field(default=5432, ge=1, le=65535)
    database: str = Field(min_length=1, max_length=63, pattern=r"^[A-Za-z_][A-Za-z0-9_$-]*$")
    schemas: list[str] = Field(min_length=1, max_length=32)
    sslmode: Literal["require", "verify-ca", "verify-full", "disable"] = "verify-full"
    statement_timeout_ms: int = Field(default=15_000, ge=100, le=120_000)
    max_objects: int = Field(default=2_000, ge=1, le=10_000)
    resource_fingerprint: str = Field(min_length=16, max_length=255)

    @model_validator(mode="after")
    def validate_schema_names(self) -> "PostgresSourceConfiguration":
        import re

        if any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_$-]*", value) for value in self.schemas):
            raise ValueError("schema names must be identifiers, not SQL expressions")
        if len(set(self.schemas)) != len(self.schemas):
            raise ValueError("schema names must be unique")
        return self


class ArtifactBundleConfiguration(RuntimeModel):
    bundle_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    formats: set[Literal["sql", "json", "yaml", "csv"]] = Field(
        default_factory=lambda: {"sql", "json", "yaml", "csv"}
    )
    max_files: int = Field(default=100, ge=1, le=500)
    max_file_bytes: int = Field(default=4_194_304, ge=1, le=33_554_432)
    max_total_bytes: int = Field(default=33_554_432, ge=1, le=134_217_728)


class SourceCreate(RuntimeModel):
    name: str = Field(min_length=1, max_length=100)
    connector_id: Literal["postgresql", "artifact-bundle"]
    secret_ref: str | None = Field(default=None, pattern=r"^secret://source/[A-Za-z0-9_./-]+$")
    postgres: PostgresSourceConfiguration | None = None
    artifact_bundle: ArtifactBundleConfiguration | None = None

    @model_validator(mode="after")
    def connector_fields(self) -> "SourceCreate":
        if self.connector_id == "postgresql" and (not self.postgres or not self.secret_ref):
            raise ValueError("PostgreSQL sources require postgres configuration and secret_ref")
        if self.connector_id == "artifact-bundle" and not self.artifact_bundle:
            raise ValueError("artifact-bundle sources require artifact_bundle configuration")
        if self.connector_id == "artifact-bundle" and self.secret_ref:
            raise ValueError("artifact bundles do not accept credentials")
        return self


class SourceRecord(SourceCreate):
    id: UUID = Field(default_factory=uuid4)
    workspace_id: UUID
    status: Literal["configured", "testing", "ready", "failed", "partial"] = "configured"
    test_detail: str | None = None
    last_tested_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class EvidencePointer(RuntimeModel):
    evidence_id: UUID
    locator: str
    knowledge_state: KnowledgeState


class ArchitectureComponent(RuntimeModel):
    id: str
    name: str
    responsibility: str
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)


class DomainModelSpec(RuntimeModel):
    name: str
    kind: Literal["source-preserving", "domain", "fact", "dimension"]
    grain: str
    keys: list[str]
    source_assets: list[str]
    history_strategy: str
    measures: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[EvidencePointer] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)


class PipelineSpec(RuntimeModel):
    id: str
    name: str
    inputs: list[str]
    outputs: list[str]
    transformations: list[str]
    incremental_strategy: str
    delete_behavior: str
    late_arrival_behavior: str
    replay_and_backfill: str
    schema_change_behavior: str
    quality_checks: list[str]
    operational_expectations: list[str]
    evidence: list[EvidencePointer] = Field(default_factory=list)


class MetricSpec(RuntimeModel):
    name: str
    definition: str
    grain: str
    additive_behavior: str
    source_assets: list[str]
    evidence: list[EvidencePointer]
    distinct_from: list[str] = Field(default_factory=list)


class ReplacementMapping(RuntimeModel):
    source_asset: str
    target_asset: str | None = None
    status: Literal["proposed", "generated", "fixture-executed", "unresolved"]
    rationale: str
    evidence: list[EvidencePointer] = Field(default_factory=list)


class WorkPackage(RuntimeModel):
    id: str
    name: str
    dependencies: list[str] = Field(default_factory=list)
    deliverables: list[str]
    validation: list[str]
    cutover: str
    rollback: str


class ModernizationSpecification(RuntimeModel):
    schema_version: Literal["reweft.modernization/v1"] = "reweft.modernization/v1"
    id: UUID = Field(default_factory=uuid4)
    workspace_id: UUID
    run_id: UUID
    version: int = 1
    status: Literal[
        "proposed", "generated", "schema-validated", "compiled", "fixture-executed", "environment-validated"
    ] = "generated"
    generated_at: datetime = Field(default_factory=utc_now)
    objective: str
    assumptions: list[str]
    constraints: list[str]
    architecture: list[ArchitectureComponent]
    models: list[DomainModelSpec]
    pipelines: list[PipelineSpec]
    metrics: list[MetricSpec]
    report_dispositions: list[dict[str, Any]]
    mappings: list[ReplacementMapping]
    work_packages: list[WorkPackage]
    retirement_conditions: list[dict[str, Any]]
    coverage_gaps: list[str]
    generator_version: str = "reweft/0.2"
