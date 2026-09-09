from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from reweft.domain.models import (
    ActualUsage,
    CostClass,
    EvidenceRequest,
    OperationResult,
    SourceExecutionState,
    SourcePolicy,
)
from reweft.persistence import Database
from reweft.source_control import AdmissionError, WorkloadController


def setup_controller(tmp_path: Path):
    database = Database(tmp_path / "controller.db")
    database.initialize()
    controller = WorkloadController(database, b"controller-test-signing-key-32byte")
    workspace_id, project_id, run_id = uuid4(), uuid4(), uuid4()
    now = datetime.now(timezone.utc).isoformat()
    with database.transaction(immediate=True) as connection:
        connection.execute("INSERT INTO workspaces(id,name,created_at) VALUES(?,?,?)", (str(workspace_id), "Workspace", now))
        connection.execute("INSERT INTO projects(id,workspace_id,name,created_at) VALUES(?,?,?,?)", (str(project_id), str(workspace_id), "Project", now))
        assessment = {
            "id": str(run_id), "workspace_id": str(workspace_id), "project_id": str(project_id),
            "objective": "Collect metadata", "scope": {}, "inference_profile_id": None,
            "deadline": None, "state": "collecting", "policy_revision": 1,
            "configuration_revision": 1, "created_at": now, "updated_at": now,
            "version": 1, "gaps": [],
        }
        connection.execute("INSERT INTO assessments(id,workspace_id,project_id,state,version,body_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)", (str(run_id), str(workspace_id), str(project_id), "collecting", 1, json.dumps(assessment), now, now))
    group_id = controller.create_resource_group(
        "sha256:physical-backend-demo-001",
        SourcePolicy(max_active_operations=1, min_request_interval_ms=0, permit_ttl_seconds=30),
    )
    return database, controller, workspace_id, project_id, run_id, group_id


def request_for(workspace_id, project_id, run_id, source_id, group_id, suffix: str):
    return EvidenceRequest(
        workspace_id=workspace_id, project_id=project_id, run_id=run_id, task_id=uuid4(), source_id=source_id,
        resource_group_ids=[group_id], connector_id="postgresql", connector_version="1.0",
        operation_id="discover_assets", authorized_asset_scope=["public"], validated_parameters={"page_size": 100},
        evidence_fingerprint=f"evidence-fingerprint-{suffix}", idempotency_key=f"idempotency-key-{suffix}",
        policy_version=1, deadline=datetime.now(timezone.utc) + timedelta(minutes=5),
        estimated_operation_class=CostClass.METADATA,
    )


def test_aliases_share_capacity_and_unknown_execution_retains_it(tmp_path):
    database, controller, workspace_id, project_id, run_id, group_id = setup_controller(tmp_path)
    first_source, second_source = uuid4(), uuid4()
    for source in (first_source, second_source):
        controller.register_connection_alias(
            workspace_id=workspace_id, connection_id=uuid4(), source_id=source,
            resource_group_ids=[group_id], connector_id="postgresql",
            allowed_operations={"discover_assets"}, authorized_scope=["public"],
        )
    first = controller.submit(request_for(workspace_id, project_id, run_id, first_source, group_id, "first-0000000000"))
    assert first.state == SourceExecutionState.RESERVED
    attempt = controller.begin_execution(first.permit, lease_seconds=-1)
    assert controller.expire_leases() == 1
    first_status = controller.status(first.operation_request_id, workspace_id)
    assert first_status["state"] == "outcome-unknown"
    assert first_status["slot_charged"] is True

    second = controller.submit(request_for(workspace_id, project_id, run_id, second_source, group_id, "second-000000000"))
    assert second.state == SourceExecutionState.QUEUED
    assert second.reason == "shared-resource-capacity-retained"
    health = controller.resource_health(workspace_id, first_source)
    assert health["health_mode"] == "unknown"
    assert health["termination_status"] == "unknown"

    with pytest.raises(AdmissionError) as stale:
        controller.begin_execution(first.permit)
    assert stale.value.code == "PERMIT_ALREADY_USED"

    controller.reconcile(first.operation_request_id, confirmed_state=SourceExecutionState.CONFIRMED_CANCELLED, confirmation="connector job API confirmed cancellation")
    admitted = controller.try_admit_queued(second.operation_request_id)
    assert admitted.state == SourceExecutionState.RESERVED


def test_idempotency_reuses_request_and_result_commit_is_transactional(tmp_path):
    _, controller, workspace_id, project_id, run_id, group_id = setup_controller(tmp_path)
    source_id = uuid4()
    controller.register_connection_alias(
        workspace_id=workspace_id, connection_id=uuid4(), source_id=source_id,
        resource_group_ids=[group_id], connector_id="postgresql",
        allowed_operations={"discover_assets"}, authorized_scope=["public"],
    )
    request = request_for(workspace_id, project_id, run_id, source_id, group_id, "same-00000000000")
    first = controller.submit(request)
    replay = controller.submit(request)
    assert replay.operation_request_id == first.operation_request_id
    assert replay.reason == "idempotency-key-reuse"
    attempt = controller.begin_execution(first.permit)
    result = OperationResult(
        operation_request_id=first.operation_request_id, attempt_id=attempt,
        source_execution_state=SourceExecutionState.CONFIRMED_FINISHED,
        evidence_refs=[], actual_usage=ActualUsage(response_bytes=100, pages=1, duration_ms=50),
    )
    controller.record_result(result)
    controller.record_result(result)  # safe activity replay
    assert controller.status(first.operation_request_id, workspace_id)["slot_charged"] is False


def test_semantic_allowlist_and_scope_are_server_enforced(tmp_path):
    _, controller, workspace_id, project_id, run_id, group_id = setup_controller(tmp_path)
    source_id = uuid4()
    controller.register_connection_alias(
        workspace_id=workspace_id, connection_id=uuid4(), source_id=source_id,
        resource_group_ids=[group_id], connector_id="postgresql",
        allowed_operations={"discover_assets"}, authorized_scope=["public/sales"],
    )
    request = request_for(workspace_id, project_id, run_id, source_id, group_id, "scope-0000000000")
    request.authorized_asset_scope = ["private/payroll"]
    with pytest.raises(AdmissionError) as denied:
        controller.submit(request)
    assert denied.value.code == "SCOPE_EXPANSION_DENIED"

