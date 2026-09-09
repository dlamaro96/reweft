import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from reweft.auth import AuthContext, AuthService
from reweft.auth.service import AuthenticationError, AuthorizationError, generate_bootstrap_token
from reweft.domain.models import (
    Assessment,
    AssessmentCreate,
    Evidence,
    EvidenceCreate,
    EvidenceRequest,
    FindingCreate,
    InferenceProfile,
    InferenceProfileCreate,
    LineageEdgeCreate,
    LineageNodeCreate,
    OperationResult,
    Role,
    RunState,
    SourceExecutionState,
    SourcePolicy,
)
from reweft.persistence import Database
from reweft.source_control import AdmissionError, WorkloadController
from reweft.source_control.controller import generate_signing_key


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _dump(value: Any) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


class BootstrapRequest(BaseModel):
    token: str = Field(min_length=32)
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    display_name: str = Field(min_length=1, max_length=100)
    workspace_name: str = Field(min_length=1, max_length=100)


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class ResourceGroupCreate(BaseModel):
    resource_fingerprint: str = Field(min_length=16, max_length=255)
    policy: SourcePolicy = Field(default_factory=SourcePolicy)
    parent_id: UUID | None = None


class AliasCreate(BaseModel):
    connection_id: UUID
    source_id: UUID
    resource_group_ids: list[UUID] = Field(min_length=1)
    connector_id: str
    allowed_operations: set[str] = Field(min_length=1)
    authorized_scope: list[str] = Field(min_length=1)


class PermitStart(BaseModel):
    permit: dict[str, Any]
    lease_seconds: int = Field(default=30, ge=5, le=300)


class RunTransition(BaseModel):
    action: str = Field(pattern=r"^(start|pause|resume|cancel|advance|complete|complete-with-gaps|fail)$")
    expected_version: int = Field(ge=1)
    gaps: list[str] = Field(default_factory=list)


TRANSITIONS: dict[tuple[RunState, str], RunState] = {
    (RunState.QUEUED, "start"): RunState.COLLECTING,
    (RunState.COLLECTING, "advance"): RunState.ANALYZING,
    (RunState.ANALYZING, "advance"): RunState.DESIGNING,
    (RunState.DESIGNING, "advance"): RunState.VERIFYING,
    (RunState.COLLECTING, "pause"): RunState.PAUSED_BY_USER,
    (RunState.ANALYZING, "pause"): RunState.PAUSED_BY_USER,
    (RunState.DESIGNING, "pause"): RunState.PAUSED_BY_USER,
    (RunState.VERIFYING, "pause"): RunState.PAUSED_BY_USER,
    (RunState.PAUSED_BY_USER, "resume"): RunState.COLLECTING,
    (RunState.COLLECTING, "complete-with-gaps"): RunState.COMPLETED_WITH_GAPS,
    (RunState.ANALYZING, "complete-with-gaps"): RunState.COMPLETED_WITH_GAPS,
    (RunState.DESIGNING, "complete-with-gaps"): RunState.COMPLETED_WITH_GAPS,
    (RunState.VERIFYING, "complete"): RunState.COMPLETED,
    (RunState.VERIFYING, "complete-with-gaps"): RunState.COMPLETED_WITH_GAPS,
}
for _state in (RunState.QUEUED, RunState.COLLECTING, RunState.ANALYZING, RunState.DESIGNING, RunState.VERIFYING, RunState.PAUSED_BY_USER, RunState.PAUSED_BY_SOURCE_POLICY, RunState.PAUSED_BY_BUDGET):
    TRANSITIONS[(_state, "cancel")] = RunState.CANCELLED
    TRANSITIONS[(_state, "fail")] = RunState.FAILED


def create_app(
    *,
    database_path: str | Path | None = None,
    bootstrap_token: str | None = None,
    permit_signing_key: bytes | None = None,
) -> FastAPI:
    path = database_path or os.getenv("REWEFT_DATABASE_PATH", ".data/reweft.db")
    database = Database(path)
    database.initialize()
    auth = AuthService(database)
    initial_token = bootstrap_token or os.getenv("REWEFT_BOOTSTRAP_TOKEN") or generate_bootstrap_token()
    auth.install_bootstrap_token(initial_token)
    configured_key = os.getenv("REWEFT_PERMIT_SIGNING_KEY") or os.getenv("REWEFT_SECRET_KEY")
    key = permit_signing_key or (configured_key.encode() if configured_key else generate_signing_key())
    controller = WorkloadController(database, key)

    app = FastAPI(title="Reweft API", version="0.1.0", openapi_url="/api/v1/openapi.json")
    app.state.database = database
    app.state.auth = auth
    app.state.controller = controller
    # Available to local launcher/test code, never returned from an HTTP route or log.
    app.state.initial_bootstrap_token = initial_token
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[origin for origin in os.getenv("REWEFT_ALLOWED_ORIGINS", "http://localhost:5173").split(",") if origin],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "If-Match"],
    )

    def context_for(
        workspace_id: UUID,
        authorization: Annotated[str | None, Header()] = None,
    ) -> AuthContext:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "bearer token required")
        try:
            return auth.authenticate(authorization.removeprefix("Bearer ").strip(), workspace_id)
        except AuthenticationError as exc:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc

    def require(permission: str):
        def dependency(context: Annotated[AuthContext, Depends(context_for)]) -> AuthContext:
            try:
                auth.require(context, permission)
                return context
            except AuthorizationError as exc:
                raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc

        return dependency

    def translate_admission(exc: AdmissionError) -> None:
        raise HTTPException(exc.status_code, {"code": exc.code, "message": exc.detail}) from exc

    @app.get("/api/v1/health")
    @app.get("/health", include_in_schema=False)
    def health() -> dict[str, Any]:
        with database.connect() as connection:
            bootstrapped = bool(connection.execute("SELECT 1 FROM users LIMIT 1").fetchone())
        return {"status": "ok", "persistence": "sqlite-development", "bootstrapped": bootstrapped}

    @app.post("/api/v1/auth/bootstrap", status_code=201)
    def bootstrap(body: BootstrapRequest) -> dict[str, Any]:
        try:
            user_id, workspace_id, token = auth.bootstrap(**body.model_dump())
        except AuthenticationError as exc:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
        return {"user_id": user_id, "workspace_id": workspace_id, "api_token": token, "token_type": "bearer"}

    @app.get("/api/v1/workspaces/{workspace_id}")
    def get_workspace(workspace_id: UUID, _: Annotated[AuthContext, Depends(context_for)]) -> dict[str, Any]:
        with database.connect() as connection:
            row = connection.execute("SELECT id,name,created_at FROM workspaces WHERE id=?", (str(workspace_id),)).fetchone()
        if not row:
            raise HTTPException(404, "workspace not found")
        return dict(row)

    @app.post("/api/v1/workspaces/{workspace_id}/projects", status_code=201)
    def create_project(workspace_id: UUID, body: ProjectCreate, _: Annotated[AuthContext, Depends(require("workspace:admin"))]) -> dict[str, Any]:
        project_id, now = uuid4(), _now().isoformat()
        with database.transaction(immediate=True) as connection:
            connection.execute("INSERT INTO projects(id,workspace_id,name,created_at) VALUES(?,?,?,?)", (str(project_id), str(workspace_id), body.name, now))
        return {"id": project_id, "workspace_id": workspace_id, "name": body.name, "created_at": now}

    @app.get("/api/v1/workspaces/{workspace_id}/projects")
    def list_projects(workspace_id: UUID, _: Annotated[AuthContext, Depends(context_for)]) -> list[dict[str, Any]]:
        with database.connect() as connection:
            return [dict(row) for row in connection.execute("SELECT id,workspace_id,name,created_at FROM projects WHERE workspace_id=? ORDER BY created_at", (str(workspace_id),))]

    @app.post("/api/v1/workspaces/{workspace_id}/inference-profiles", status_code=201)
    def create_inference_profile(workspace_id: UUID, body: InferenceProfileCreate, _: Annotated[AuthContext, Depends(require("inference:admin"))]) -> InferenceProfile:
        profile = InferenceProfile(workspace_id=workspace_id, **body.model_dump())
        with database.transaction(immediate=True) as connection:
            for fallback in profile.fallback_profile_ids:
                row = connection.execute("SELECT body_json FROM inference_profiles WHERE id=? AND workspace_id=?", (str(fallback), str(workspace_id))).fetchone()
                if not row:
                    raise HTTPException(422, f"fallback profile not found: {fallback}")
                target = InferenceProfile.model_validate_json(row["body_json"])
                if profile.endpoint_class.value == "local" and target.endpoint_class.value != "local":
                    raise HTTPException(422, "local-only profiles cannot fall back to a non-local endpoint")
                if not profile.allowed_data_classes.issubset(target.allowed_data_classes):
                    raise HTTPException(422, "fallback profile does not allow all routed data classifications")
            connection.execute(
                "INSERT INTO inference_profiles(id,workspace_id,name,revision,body_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                (str(profile.id), str(workspace_id), profile.name, profile.revision, _dump(profile), profile.created_at.isoformat(), profile.created_at.isoformat()),
            )
        return profile

    @app.get("/api/v1/workspaces/{workspace_id}/inference-profiles")
    def list_inference_profiles(workspace_id: UUID, _: Annotated[AuthContext, Depends(require("inference:admin"))]) -> list[InferenceProfile]:
        with database.connect() as connection:
            rows = connection.execute("SELECT body_json FROM inference_profiles WHERE workspace_id=? ORDER BY name", (str(workspace_id),)).fetchall()
        return [InferenceProfile.model_validate_json(row["body_json"]) for row in rows]

    @app.post("/api/v1/workspaces/{workspace_id}/assessments", status_code=201)
    def create_assessment(workspace_id: UUID, body: AssessmentCreate, _: Annotated[AuthContext, Depends(require("assessment:run"))]) -> Assessment:
        with database.transaction(immediate=True) as connection:
            project = connection.execute("SELECT workspace_id FROM projects WHERE id=?", (str(body.project_id),)).fetchone()
            if not project or project["workspace_id"] != str(workspace_id):
                raise HTTPException(404, "project not found")
            if body.inference_profile_id and not connection.execute("SELECT 1 FROM inference_profiles WHERE id=? AND workspace_id=?", (str(body.inference_profile_id), str(workspace_id))).fetchone():
                raise HTTPException(404, "inference profile not found")
            run = Assessment(workspace_id=workspace_id, **body.model_dump())
            connection.execute(
                "INSERT INTO assessments(id,workspace_id,project_id,state,version,body_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                (str(run.id), str(workspace_id), str(run.project_id), run.state.value, run.version, _dump(run), run.created_at.isoformat(), run.updated_at.isoformat()),
            )
        return run

    @app.get("/api/v1/workspaces/{workspace_id}/assessments")
    def list_assessments(workspace_id: UUID, _: Annotated[AuthContext, Depends(context_for)]) -> list[Assessment]:
        with database.connect() as connection:
            rows = connection.execute("SELECT body_json FROM assessments WHERE workspace_id=? ORDER BY created_at DESC", (str(workspace_id),)).fetchall()
        return [Assessment.model_validate_json(row["body_json"]) for row in rows]

    @app.post("/api/v1/workspaces/{workspace_id}/assessments/{run_id}/transition")
    def transition_assessment(workspace_id: UUID, run_id: UUID, body: RunTransition, _: Annotated[AuthContext, Depends(require("assessment:run"))]) -> Assessment:
        now = _now()
        with database.transaction(immediate=True) as connection:
            row = connection.execute("SELECT * FROM assessments WHERE id=? AND workspace_id=?", (str(run_id), str(workspace_id))).fetchone()
            if not row:
                raise HTTPException(404, "assessment not found")
            run = Assessment.model_validate_json(row["body_json"])
            if run.version != body.expected_version:
                raise HTTPException(409, {"code": "VERSION_CONFLICT", "current_version": run.version})
            target = TRANSITIONS.get((run.state, body.action))
            if target is None:
                raise HTTPException(409, f"cannot {body.action} from {run.state.value}")
            if target == RunState.COMPLETED_WITH_GAPS and not body.gaps:
                raise HTTPException(422, "completed-with-gaps requires at least one explicit gap")
            run.state, run.updated_at, run.version = target, now, run.version + 1
            if body.gaps:
                run.gaps = body.gaps
            connection.execute("UPDATE assessments SET state=?,version=?,body_json=?,updated_at=? WHERE id=?", (target.value, run.version, _dump(run), now.isoformat(), str(run_id)))
        return run

    @app.post("/api/v1/workspaces/{workspace_id}/evidence", status_code=201)
    def create_evidence(workspace_id: UUID, body: EvidenceCreate, _: Annotated[AuthContext, Depends(require("evidence:write"))]) -> Evidence:
        evidence = Evidence(workspace_id=workspace_id, **body.model_dump())
        with database.transaction(immediate=True) as connection:
            project = connection.execute("SELECT workspace_id FROM projects WHERE id=?", (str(body.project_id),)).fetchone()
            if not project or project["workspace_id"] != str(workspace_id):
                raise HTTPException(404, "project not found")
            if body.run_id and not connection.execute("SELECT 1 FROM assessments WHERE id=? AND workspace_id=? AND project_id=?", (str(body.run_id), str(workspace_id), str(body.project_id))).fetchone():
                raise HTTPException(404, "assessment not found")
            existing = connection.execute("SELECT body_json FROM evidence WHERE workspace_id=? AND project_id=? AND artifact_sha256=?", (str(workspace_id), str(body.project_id), body.artifact_sha256)).fetchone()
            if existing:
                return Evidence.model_validate_json(existing["body_json"])
            connection.execute(
                "INSERT INTO evidence(id,workspace_id,project_id,run_id,artifact_sha256,body_json,created_at) VALUES(?,?,?,?,?,?,?)",
                (str(evidence.id), str(workspace_id), str(body.project_id), str(body.run_id) if body.run_id else None, body.artifact_sha256, _dump(evidence), evidence.created_at.isoformat()),
            )
        return evidence

    @app.get("/api/v1/workspaces/{workspace_id}/evidence")
    def list_evidence(workspace_id: UUID, _: Annotated[AuthContext, Depends(require("evidence:read"))], run_id: UUID | None = None, limit: int = Query(100, ge=1, le=500)) -> list[Evidence]:
        query, params = "SELECT body_json FROM evidence WHERE workspace_id=?", [str(workspace_id)]
        if run_id:
            query, params = query + " AND run_id=?", params + [str(run_id)]
        with database.connect() as connection:
            rows = connection.execute(query + " ORDER BY created_at DESC LIMIT ?", (*params, limit)).fetchall()
        return [Evidence.model_validate_json(row["body_json"]) for row in rows]

    @app.post("/api/v1/workspaces/{workspace_id}/findings", status_code=201)
    def create_finding(workspace_id: UUID, body: FindingCreate, _: Annotated[AuthContext, Depends(require("evidence:write"))]) -> dict[str, Any]:
        finding_id, now = uuid4(), _now()
        with database.transaction(immediate=True) as connection:
            if not connection.execute("SELECT 1 FROM assessments WHERE id=? AND workspace_id=?", (str(body.run_id), str(workspace_id))).fetchone():
                raise HTTPException(404, "assessment not found")
            placeholders = ",".join("?" for _ in body.evidence_ids)
            count = connection.execute(f"SELECT COUNT(*) FROM evidence WHERE workspace_id=? AND id IN ({placeholders})", (str(workspace_id), *(str(value) for value in body.evidence_ids))).fetchone()[0]
            if count != len(set(body.evidence_ids)):
                raise HTTPException(422, "every evidence reference must resolve inside the workspace")
            payload = {"id": str(finding_id), "workspace_id": str(workspace_id), **body.model_dump(mode="json"), "created_at": now.isoformat()}
            existing = connection.execute("SELECT body_json FROM findings WHERE workspace_id=? AND run_id=? AND stable_key=?", (str(workspace_id), str(body.run_id), body.stable_key)).fetchone()
            if existing:
                return json.loads(existing["body_json"])
            connection.execute("INSERT INTO findings(id,workspace_id,run_id,stable_key,body_json,created_at) VALUES(?,?,?,?,?,?)", (str(finding_id), str(workspace_id), str(body.run_id), body.stable_key, _dump(payload), now.isoformat()))
        return payload

    @app.post("/api/v1/workspaces/{workspace_id}/lineage/nodes", status_code=201)
    def create_lineage_node(workspace_id: UUID, body: LineageNodeCreate, _: Annotated[AuthContext, Depends(require("lineage:write"))]) -> dict[str, Any]:
        node_id, now = uuid4(), _now().isoformat()
        payload = {"id": str(node_id), "workspace_id": str(workspace_id), **body.model_dump(mode="json"), "created_at": now}
        with database.transaction(immediate=True) as connection:
            project = connection.execute("SELECT 1 FROM projects WHERE id=? AND workspace_id=?", (str(body.project_id), str(workspace_id))).fetchone()
            if not project:
                raise HTTPException(404, "project not found")
            connection.execute("INSERT INTO lineage_nodes(id,workspace_id,project_id,native_id,namespace,environment,body_json,created_at) VALUES(?,?,?,?,?,?,?,?)", (str(node_id), str(workspace_id), str(body.project_id), body.native_id, body.namespace, body.environment, _dump(payload), now))
        return payload

    @app.post("/api/v1/workspaces/{workspace_id}/lineage/edges", status_code=201)
    def create_lineage_edge(workspace_id: UUID, body: LineageEdgeCreate, _: Annotated[AuthContext, Depends(require("lineage:write"))]) -> dict[str, Any]:
        edge_id, now = uuid4(), _now().isoformat()
        payload = {"id": str(edge_id), "workspace_id": str(workspace_id), **body.model_dump(mode="json"), "created_at": now}
        with database.transaction(immediate=True) as connection:
            endpoints = connection.execute("SELECT COUNT(*) FROM lineage_nodes WHERE workspace_id=? AND project_id=? AND id IN (?,?)", (str(workspace_id), str(body.project_id), str(body.from_node_id), str(body.to_node_id))).fetchone()[0]
            if endpoints != 2:
                raise HTTPException(422, "both lineage endpoints must resolve inside the workspace and project")
            placeholders = ",".join("?" for _ in body.evidence_ids)
            evidence_count = connection.execute(f"SELECT COUNT(*) FROM evidence WHERE workspace_id=? AND project_id=? AND id IN ({placeholders})", (str(workspace_id), str(body.project_id), *(str(value) for value in body.evidence_ids))).fetchone()[0]
            if evidence_count != len(set(body.evidence_ids)):
                raise HTTPException(422, "lineage evidence references must resolve inside the workspace and project")
            connection.execute("INSERT INTO lineage_edges(id,workspace_id,project_id,from_node_id,to_node_id,relationship,body_json,created_at) VALUES(?,?,?,?,?,?,?,?)", (str(edge_id), str(workspace_id), str(body.project_id), str(body.from_node_id), str(body.to_node_id), body.relationship, _dump(payload), now))
        return payload

    @app.get("/api/v1/workspaces/{workspace_id}/lineage/neighborhood/{node_id}")
    def lineage_neighborhood(workspace_id: UUID, node_id: UUID, _: Annotated[AuthContext, Depends(require("lineage:read"))], depth: int = Query(2, ge=0, le=5), direction: str = Query("both", pattern="^(upstream|downstream|both)$"), limit: int = Query(200, ge=1, le=500)) -> dict[str, Any]:
        with database.connect() as connection:
            root = connection.execute("SELECT * FROM lineage_nodes WHERE id=? AND workspace_id=?", (str(node_id), str(workspace_id))).fetchone()
            if not root:
                raise HTTPException(404, "lineage node not found")
            seen, frontier, edges = {str(node_id)}, {str(node_id)}, {}
            for _level in range(depth):
                if not frontier or len(seen) >= limit:
                    break
                marks = ",".join("?" for _ in frontier)
                clauses, params = [], [str(workspace_id)]
                if direction in {"downstream", "both"}:
                    clauses.append(f"from_node_id IN ({marks})")
                    params.extend(frontier)
                if direction in {"upstream", "both"}:
                    clauses.append(f"to_node_id IN ({marks})")
                    params.extend(frontier)
                rows = connection.execute(f"SELECT * FROM lineage_edges WHERE workspace_id=? AND ({' OR '.join(clauses)}) LIMIT ?", (*params, limit)).fetchall()
                next_frontier = set()
                for row in rows:
                    edges[row["id"]] = json.loads(row["body_json"])
                    next_frontier.update((row["from_node_id"], row["to_node_id"]))
                next_frontier -= seen
                seen.update(list(next_frontier)[: max(0, limit - len(seen))])
                frontier = next_frontier & seen
            marks = ",".join("?" for _ in seen)
            nodes = [json.loads(row["body_json"]) for row in connection.execute(f"SELECT body_json FROM lineage_nodes WHERE workspace_id=? AND id IN ({marks})", (str(workspace_id), *seen))]
        return {"root_id": node_id, "depth": depth, "truncated": len(seen) >= limit, "nodes": nodes, "edges": list(edges.values())}

    @app.post("/api/v1/workspaces/{workspace_id}/source-control/resource-groups", status_code=201)
    def create_resource_group(workspace_id: UUID, body: ResourceGroupCreate, _: Annotated[AuthContext, Depends(require("source:admin"))]) -> dict[str, Any]:
        try:
            group_id = controller.create_resource_group(body.resource_fingerprint, body.policy, parent_id=body.parent_id)
            return {"id": group_id, "policy_version": 1}
        except AdmissionError as exc:
            translate_admission(exc)

    @app.post("/api/v1/workspaces/{workspace_id}/source-control/aliases", status_code=201)
    def create_alias(workspace_id: UUID, body: AliasCreate, _: Annotated[AuthContext, Depends(require("source:admin"))]) -> dict[str, Any]:
        try:
            controller.register_connection_alias(workspace_id=workspace_id, **body.model_dump())
            return {"connection_id": body.connection_id, "source_id": body.source_id, "status": "configured"}
        except AdmissionError as exc:
            translate_admission(exc)

    @app.post("/api/v1/workspaces/{workspace_id}/source-control/operations", status_code=202)
    def submit_operation(workspace_id: UUID, body: EvidenceRequest, _: Annotated[AuthContext, Depends(require("assessment:run"))]):
        if body.workspace_id != workspace_id:
            raise HTTPException(403, "workspace path and request do not match")
        try:
            return controller.submit(body)
        except AdmissionError as exc:
            translate_admission(exc)

    @app.post("/api/v1/workspaces/{workspace_id}/source-control/operations/{operation_id}/start")
    def start_operation(workspace_id: UUID, operation_id: UUID, body: PermitStart, _: Annotated[AuthContext, Depends(require("source:admin"))]) -> dict[str, Any]:
        from reweft.domain.models import ExecutionPermit

        permit = ExecutionPermit.model_validate(body.permit)
        if permit.operation_request_id != operation_id:
            raise HTTPException(422, "permit operation does not match path")
        try:
            attempt_id = controller.begin_execution(permit, lease_seconds=body.lease_seconds)
            return {"operation_request_id": operation_id, "attempt_id": attempt_id, "state": "executing"}
        except AdmissionError as exc:
            translate_admission(exc)

    @app.post("/api/v1/workspaces/{workspace_id}/source-control/results", status_code=202)
    def record_operation_result(workspace_id: UUID, body: OperationResult, _: Annotated[AuthContext, Depends(require("source:admin"))]) -> dict[str, str]:
        try:
            # Workspace ownership is checked without exposing a foreign operation.
            controller.status(body.operation_request_id, workspace_id)
            controller.record_result(body)
            return {"status": "recorded"}
        except AdmissionError as exc:
            translate_admission(exc)

    @app.get("/api/v1/workspaces/{workspace_id}/source-control/operations/{operation_id}")
    def operation_status(workspace_id: UUID, operation_id: UUID, _: Annotated[AuthContext, Depends(require("assessment:run"))]) -> dict[str, Any]:
        try:
            return controller.status(operation_id, workspace_id)
        except AdmissionError as exc:
            translate_admission(exc)

    @app.get("/api/v1/workspaces/{workspace_id}/source-control/sources/{source_id}/health")
    def source_health(workspace_id: UUID, source_id: UUID, _: Annotated[AuthContext, Depends(require("assessment:run"))]) -> dict[str, Any]:
        try:
            return controller.resource_health(workspace_id, source_id)
        except AdmissionError as exc:
            translate_admission(exc)

    @app.get("/api/v1/demo/snapshot")
    def demo_snapshot() -> dict[str, Any]:
        """Deterministic, credential-free fixture. Every record is visibly synthetic."""
        return _demo_snapshot()

    return app


def _demo_snapshot() -> dict[str, Any]:
    return {
        "mode": "synthetic-demo",
        "generatedAt": "2026-09-09T08:30:00Z",
        "workspace": {"name": "Synthetic Manufacturing", "project": "BW retirement assessment", "objective": "Assess legacy retirement readiness"},
        "overview": {"label": "Synthetic demo — no live systems", "coverage": {"known": 148, "collected": 136, "inaccessible": 5, "unresolved": 7}},
        "inventory": [
            {"label": "Systems observed", "value": 5, "qualifier": "3 fully inventoried", "href": "/connections"},
            {"label": "Assets catalogued", "value": 148, "qualifier": "12 with incomplete scope", "href": "/estate"},
            {"label": "Reports assessed", "value": 24, "qualifier": "7 need disposition", "href": "/reports"},
            {"label": "Open findings", "value": 11, "qualifier": "3 high priority", "href": "/findings"},
        ],
        "sources": [
            {"id": "src-bw", "name": "BW/4HANA sample", "type": "SAP BW", "status": "Partial", "validation": "Synthetic fixture", "scope": "Queries, transformations, ADSOs", "resourceGroup": "erp-core", "facts": [["Network", "Fixture only"], ["Authentication", "Fixture only"], ["Metadata", "42 objects"], ["Objective coverage", "Partial"]], "synthetic": True},
            {"id": "src-pg", "name": "Operations warehouse", "type": "PostgreSQL", "status": "Ready", "validation": "Synthetic fixture", "scope": "manufacturing, distribution", "resourceGroup": "analytics-postgres", "facts": [["Network", "Fixture only"], ["Authentication", "Fixture only"], ["Metadata", "42 fixture objects"], ["Objective coverage", "Complete for fixture"]], "synthetic": True},
            {"id": "src-bi", "name": "Commercial reporting", "type": "Power BI", "status": "Partial", "validation": "Not live verified", "scope": "Sales & distribution workspace", "resourceGroup": "bi-tenant", "facts": [["Network", "Not tested"], ["Authentication", "Not configured"], ["Metadata", "Fixture: 24 reports"], ["Objective coverage", "Partial"]], "synthetic": True},
        ],
        "findings": [
            {"id": "F-014", "severity": "High", "title": "Monthly adjustment is absent from the candidate shared metric", "summary": "The similarly named net sales reports are not semantically equivalent. One applies a separate period-end adjustment after invoice aggregation.", "area": "Semantics", "state": "Fact", "evidence": "3 artifacts", "locator": "bw://TRFN/ZSD_NET_ADJ/ABAP#L18-L31", "synthetic": True},
            {"id": "F-021", "severity": "High", "title": "Legacy outbound dependency blocks retirement", "summary": "A scheduled distributor extract has no mapped replacement path in the proposed target scenario.", "area": "Retirement", "state": "Interpretation", "evidence": "2 observations", "locator": "bw://DTP/ZDIST_MONTHLY#schedule", "synthetic": True},
            {"id": "F-030", "severity": "Medium", "title": "Inventory scope excludes archived workbook delivery", "summary": "The reporting scan lacks access to one archived workspace mentioned by the distribution schedule.", "area": "Coverage", "state": "Assumption", "evidence": "1 gap", "locator": "coverage://reporting/workspaces#archived", "synthetic": True},
        ],
        "assets": [
            {"id": "A-101", "name": "ZSD_NET_SALES", "type": "BW Query", "system": "BW/4HANA sample", "domain": "Commercial", "usage": "Observed 6 days ago", "status": "Observed", "description": "Invoice net amount by customer, material and fiscal period.", "synthetic": True},
            {"id": "A-102", "name": "ZSD_NET_ADJ", "type": "Transformation", "system": "BW/4HANA sample", "domain": "Commercial", "usage": "Executed monthly", "status": "Observed", "description": "Applies period-end commercial adjustments to aggregated invoices.", "synthetic": True},
            {"id": "A-105", "name": "inventory_snapshot", "type": "PostgreSQL table", "system": "Operations warehouse", "domain": "Manufacturing", "usage": "Queried 2 days ago", "status": "Observed", "description": "Daily stock-position snapshot by plant, location and product.", "synthetic": True},
        ],
        "reports": [
            {"id": "R-12", "name": "Net sales — management", "platform": "Power BI", "disposition": "Rebuild", "metric": "Adjusted net sales", "formula": "SUM(invoice.net_amount) + SUM(monthly_adjustment.amount)", "usage": "19 synthetic viewers · 30d", "distinction": "Includes signed period-end adjustment at fiscal-month grain.", "synthetic": True},
            {"id": "R-13", "name": "Net sales — operations", "platform": "Power BI", "disposition": "Consolidate", "metric": "Invoice net amount", "formula": "SUM(invoice.net_amount)", "usage": "8 synthetic viewers · 30d", "distinction": "Invoice-only value at line grain; no adjustment.", "synthetic": True},
            {"id": "R-22", "name": "Distributor delivery", "platform": "File export", "disposition": "Review", "metric": "Delivered quantity", "formula": "SUM(delivery.qty) WHERE goods_issue = true", "usage": "Scheduled monthly", "distinction": "Remaining external boundary with no confirmed target consumer.", "synthetic": True},
        ],
        "run": {
            "id": "RUN-042", "state": "Running", "started": "Today, 08:12", "progress": 72, "current": "Tracing remaining outbound dependencies",
            "tasks": [
                {"label": "Inventory & coverage", "status": "Complete", "detail": "148 assets across 5 configured systems"},
                {"label": "Semantic reconstruction", "status": "Complete", "detail": "27 metrics; 4 require reconciliation"},
                {"label": "Lineage investigation", "status": "Active", "detail": "Resolving distribution extract path"},
                {"label": "Modernization proposal", "status": "Deferred", "detail": "Starts after dependency tracing completes"},
            ],
            "synthetic": True,
        },
        "connections": [
            {"id": "demo-conn-pg", "name": "Operations metadata replica", "connector": "postgresql", "scope": ["manufacturing", "distribution"], "readOnly": True, "synthetic": True},
            {"id": "demo-conn-bw", "name": "BW definition archive", "connector": "sap-bw-definition-import", "scope": ["distribution"], "readOnly": True, "synthetic": True},
        ],
        "runs": [{"id": "RUN-042", "objective": "Assess the synthetic manufacturing estate for BW retirement", "state": "running", "synthetic": True}],
        "lineage": {
            "nodes": [
                {"id": "demo-a-orders", "label": "sales.orders", "kind": "table"},
                {"id": "demo-a-net", "label": "Net Sales", "kind": "metric"},
                {"id": "demo-r-1", "label": "Monthly Distribution Margin", "kind": "report"},
            ],
            "edges": [
                {"from": "demo-a-net", "to": "demo-a-orders", "relationship": "calculates-from", "knowledgeState": "deterministically-derived"},
                {"from": "demo-r-1", "to": "demo-a-net", "relationship": "serves", "knowledgeState": "collected"},
            ],
            "synthetic": True,
        },
        "modernization": {
            "scenario": "Target-neutral lakehouse option A",
            "status": "proposed",
            "assumptions": ["A governed monthly adjustment remains report-specific until ownership is resolved"],
            "workPackages": ["Shared invoice model", "Distribution adjustment pipeline", "Report reconciliation"],
            "synthetic": True,
        },
    }


app = create_app()
