from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AssessmentWorkflowInput:
    workspace_id: str
    project_id: str
    run_id: str
    source_ids: list[str]
    objective: str
    inference_profile_id: str | None = None


@dataclass
class SourceTestWorkflowInput:
    workspace_id: str
    project_id: str
    run_id: str
    source_id: str


@dataclass
class ProviderTestWorkflowInput:
    workspace_id: str
    profile_id: str | None = None


@dataclass
class CollectionActivityInput:
    workspace_id: str
    project_id: str
    run_id: str
    source_id: str
    operation: str | None = None


@dataclass
class AnalysisActivityInput:
    workspace_id: str
    project_id: str
    run_id: str
    objective: str
    evidence_ids: list[str] = field(default_factory=list)


@dataclass
class InferenceActivityInput:
    workspace_id: str
    run_id: str | None
    profile_id: str | None
    evidence_summary: dict[str, Any]
    purpose: str = "analysis"


@dataclass
class DesignActivityInput:
    workspace_id: str
    project_id: str
    run_id: str
    objective: str
    analysis: dict[str, Any]
    inference: dict[str, Any] | None = None


@dataclass
class ValidationActivityInput:
    workspace_id: str
    run_id: str
    scenario_id: str
    spec_id: str


@dataclass
class FinalizeActivityInput:
    workspace_id: str
    run_id: str
    gaps: list[str]
    output: dict[str, Any]
