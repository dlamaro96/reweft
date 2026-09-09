from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Role(StrEnum):
    OWNER = "owner"
    ADMINISTRATOR = "administrator"
    OPERATOR = "operator"
    CONTRIBUTOR = "contributor"
    VIEWER = "viewer"


class KnowledgeState(StrEnum):
    COLLECTED = "collected"
    DETERMINISTICALLY_DERIVED = "deterministically-derived"
    AI_INFERRED = "ai-inferred"
    USER_ASSERTED = "user-asserted"
    INDEPENDENTLY_VERIFIED = "independently-verified"
    CONFLICTING = "conflicting"
    UNRESOLVED = "unresolved"


class RunState(StrEnum):
    QUEUED = "queued"
    COLLECTING = "collecting"
    ANALYZING = "analyzing"
    DESIGNING = "designing"
    VERIFYING = "verifying"
    PAUSED_BY_USER = "paused-by-user"
    PAUSED_BY_SOURCE_POLICY = "paused-by-source-policy"
    PAUSED_BY_BUDGET = "paused-by-budget"
    COMPLETED = "completed"
    COMPLETED_WITH_GAPS = "completed-with-gaps"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SourceExecutionState(StrEnum):
    QUEUED = "queued"
    RESERVED = "reserved"
    DISPATCHED = "dispatched"
    EXECUTING = "executing"
    CANCEL_REQUESTED = "cancel-requested"
    CONFIRMED_FINISHED = "confirmed-finished"
    CONFIRMED_CANCELLED = "confirmed-cancelled"
    OUTCOME_UNKNOWN = "outcome-unknown"
    REJECTED = "rejected"


class CostClass(StrEnum):
    HEALTH = "health"
    METADATA = "metadata"
    PROFILE = "profile"


class AssessmentCreate(StrictModel):
    project_id: UUID
    objective: str = Field(min_length=3, max_length=1000)
    scope: dict[str, Any] = Field(default_factory=dict)
    inference_profile_id: UUID | None = None
    deadline: datetime | None = None


class Assessment(AssessmentCreate):
    id: UUID = Field(default_factory=uuid4)
    workspace_id: UUID
    state: RunState = RunState.QUEUED
    policy_revision: int = 1
    configuration_revision: int = 1
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    version: int = 1
    gaps: list[str] = Field(default_factory=list)


class ProviderType(StrEnum):
    OPENAI = "openai"
    AZURE_OPENAI = "azure_openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    VERTEX = "vertex"
    BEDROCK = "bedrock"
    OPENAI_COMPATIBLE = "openai_compatible"


class EndpointClass(StrEnum):
    PUBLIC = "public"
    PRIVATE = "private"
    LOCAL = "local"


class InferenceCapabilities(StrictModel):
    structured_output: bool = False
    tool_calling: bool = False
    streaming: bool = False
    native_responses: bool = False
    observed_at: datetime | None = None
    test_status: str = "not-tested"


class InferenceLimits(StrictModel):
    max_concurrent_requests: int = Field(default=2, ge=1, le=100)
    max_output_tokens: int = Field(default=4096, ge=1)
    max_requests_per_run: int = Field(default=200, ge=1)
    max_tokens_per_run: int | None = Field(default=None, ge=1)
    max_wall_time_seconds: int = Field(default=120, ge=1)
    currency_budget: Decimal | None = Field(default=None, ge=0)


class InferenceProfileCreate(StrictModel):
    name: str = Field(min_length=1, max_length=80)
    provider: ProviderType
    endpoint_class: EndpointClass
    model: str = Field(min_length=1, max_length=255)
    credential_ref: str | None = Field(default=None, pattern=r"^secret://[A-Za-z0-9_./-]+$")
    base_url: HttpUrl | None = None
    region: str | None = Field(default=None, max_length=100)
    api_version: str | None = Field(default=None, max_length=100)
    tls_verify: bool = True
    custom_ca_ref: str | None = None
    proxy_ref: str | None = None
    context_limit: int | None = Field(default=None, ge=1)
    limits: InferenceLimits = Field(default_factory=InferenceLimits)
    capabilities: InferenceCapabilities = Field(default_factory=InferenceCapabilities)
    required_capabilities: set[str] = Field(default_factory=set)
    allowed_data_classes: set[str] = Field(default_factory=lambda: {"metadata"})
    fallback_profile_ids: list[UUID] = Field(default_factory=list)
    retention_notes: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def provider_fields(self) -> InferenceProfileCreate:
        if not self.tls_verify:
            raise ValueError("TLS verification cannot be disabled")
        if self.endpoint_class == EndpointClass.LOCAL and self.provider != ProviderType.OPENAI_COMPATIBLE:
            raise ValueError("local endpoints currently require openai_compatible provider")
        if self.provider == ProviderType.BEDROCK and not self.region:
            raise ValueError("Bedrock profiles require region")
        if self.provider == ProviderType.AZURE_OPENAI and not (self.base_url and self.api_version):
            raise ValueError("Azure OpenAI profiles require base_url and api_version")
        if self.endpoint_class != EndpointClass.LOCAL and not self.credential_ref and self.provider != ProviderType.BEDROCK:
            raise ValueError("non-local profiles require a credential reference")
        return self


class InferenceRouting(StrictModel):
    default_profile_id: UUID
    planning: UUID | None = None
    semantic_analysis: UUID | None = None
    code_generation: UUID | None = None
    verification: UUID | None = None
    narrative_generation: UUID | None = None


class InferenceProfile(InferenceProfileCreate):
    id: UUID = Field(default_factory=uuid4)
    workspace_id: UUID
    revision: int = 1
    last_successful_test: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)


class EvidenceLocator(StrictModel):
    kind: str = Field(pattern=r"^(line-range|json-path|xml-node|cell|api-object|document-range)$")
    value: str = Field(min_length=1, max_length=1000)
    external_label: str = Field(min_length=1, max_length=300)


class EvidenceCreate(StrictModel):
    project_id: UUID
    run_id: UUID | None = None
    source_id: UUID | None = None
    platform: str = Field(min_length=1, max_length=100)
    environment: str = Field(min_length=1, max_length=100)
    native_object_id: str = Field(min_length=1, max_length=500)
    source_version: str | None = None
    artifact_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    artifact_size: int = Field(ge=0)
    media_type: str
    original_location: str
    parser_version: str
    collector_version: str
    scope_context: dict[str, Any] = Field(default_factory=dict)
    permissions_context: dict[str, Any] = Field(default_factory=dict)
    classification: str = "metadata"
    retention_policy: str = "workspace-default"
    collection_status: str
    snapshot_id: UUID | None = None
    collected_from: datetime
    collected_to: datetime
    locator: EvidenceLocator

    @model_validator(mode="after")
    def valid_interval(self) -> EvidenceCreate:
        if self.collected_to < self.collected_from:
            raise ValueError("collected_to must not precede collected_from")
        return self


class Evidence(EvidenceCreate):
    id: UUID = Field(default_factory=uuid4)
    workspace_id: UUID
    created_at: datetime = Field(default_factory=utc_now)


class FindingCreate(StrictModel):
    run_id: UUID
    stable_key: str = Field(min_length=1, max_length=255)
    finding_type: str
    title: str
    interpretation: str
    impact: str
    recommendation: str
    severity_basis: str
    knowledge_state: KnowledgeState
    evidence_ids: list[UUID] = Field(min_length=1)
    assumptions: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)


class LineageNodeCreate(StrictModel):
    project_id: UUID
    native_id: str
    namespace: str
    environment: str
    node_type: str
    name: str


class LineageEdgeCreate(StrictModel):
    project_id: UUID
    from_node_id: UUID
    to_node_id: UUID
    relationship: str = Field(pattern=r"^(reads-from|writes-to|transforms|joins-on|filters-by|aggregates|calculates-from|executes|schedules|serves|exports-to|secures|replaces)$")
    level: str = Field(pattern=r"^(object|field)$")
    knowledge_state: KnowledgeState
    evidence_ids: list[UUID] = Field(min_length=1)


class SourcePolicy(StrictModel):
    max_active_operations: int = Field(default=1, ge=1, le=64)
    min_request_interval_ms: int = Field(default=2000, ge=0)
    request_deadline_seconds: int = Field(default=30, ge=1, le=3600)
    permit_ttl_seconds: int = Field(default=15, ge=1, le=300)
    max_response_bytes: int = Field(default=4_194_304, ge=1)
    max_pages_per_operation: int = Field(default=20, ge=1)
    max_attempts: int = Field(default=2, ge=1, le=10)
    max_collection_bytes_per_run: int = Field(default=268_435_456, ge=1)
    max_operations_per_run: int = Field(default=1000, ge=1)
    profiling_enabled: bool = False
    allowed_hours_start: int = Field(default=0, ge=0, le=23)
    allowed_hours_end: int = Field(default=24, ge=1, le=24)
    timezone: str = "UTC"


class EstimatedLimits(StrictModel):
    response_bytes: int = Field(default=1_048_576, ge=1)
    pages: int = Field(default=1, ge=1)
    duration_seconds: int = Field(default=30, ge=1)


class EvidenceRequest(StrictModel):
    workspace_id: UUID
    project_id: UUID
    run_id: UUID
    task_id: UUID
    source_id: UUID
    resource_group_ids: list[UUID] = Field(min_length=1)
    connector_id: str
    connector_version: str
    operation_id: str
    authorized_asset_scope: list[str] = Field(min_length=1)
    validated_parameters: dict[str, Any] = Field(default_factory=dict)
    evidence_fingerprint: str = Field(min_length=16, max_length=255)
    idempotency_key: str = Field(min_length=16, max_length=255)
    policy_version: int = Field(ge=1)
    deadline: datetime
    estimated_operation_class: CostClass
    estimated_limits: EstimatedLimits = Field(default_factory=EstimatedLimits)


class ReservedLimits(StrictModel):
    max_response_bytes: int
    max_pages: int
    deadline: datetime


class ExecutionPermit(StrictModel):
    operation_request_id: UUID
    permitted_resource_groups: list[UUID]
    permit_id: UUID
    fencing_generation: int
    expires_at: datetime
    reserved_limits: ReservedLimits
    policy_version: int
    token: str


class ActualUsage(StrictModel):
    response_bytes: int = Field(default=0, ge=0)
    pages: int = Field(default=0, ge=0)
    duration_ms: int = Field(default=0, ge=0)


class OperationResult(StrictModel):
    operation_request_id: UUID
    attempt_id: UUID
    source_execution_state: SourceExecutionState
    source_native_execution_reference: str | None = None
    evidence_refs: list[UUID] = Field(default_factory=list)
    completeness_manifest_ref: UUID | None = None
    actual_usage: ActualUsage = Field(default_factory=ActualUsage)
    sanitized_error: str | None = None
    cancellation_confirmation: str | None = None
    next_cursor: str | None = None


class AdmissionDecision(StrictModel):
    operation_request_id: UUID
    state: SourceExecutionState
    permit: ExecutionPermit | None = None
    reused_result: OperationResult | None = None
    reason: str | None = None
