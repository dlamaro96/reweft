from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from reweft.connectors import ConnectorOutcome, ControlledConnectorRuntime
from reweft.domain.models import ActualUsage, CostClass, EvidenceRequest, SourceExecutionState

from test_source_controller import setup_controller


class Resolver:
    called = False

    def resolve_for_source(self, source_id):
        self.called = True
        return {"credential": "never-returned"}


def test_runtime_resolves_secret_only_after_consuming_permit(tmp_path):
    _, controller, workspace_id, project_id, run_id, group_id = setup_controller(tmp_path)
    source_id = uuid4()
    controller.register_connection_alias(
        workspace_id=workspace_id, connection_id=uuid4(), source_id=source_id,
        resource_group_ids=[group_id], connector_id="postgresql",
        allowed_operations={"discover_assets"}, authorized_scope=["public"],
    )
    request = EvidenceRequest(
        workspace_id=workspace_id, project_id=project_id, run_id=run_id, task_id=uuid4(),
        source_id=source_id, resource_group_ids=[group_id], connector_id="postgresql",
        connector_version="1", operation_id="discover_assets", authorized_asset_scope=["public"],
        evidence_fingerprint="runtime-evidence-fingerprint", idempotency_key="runtime-idempotency-key",
        policy_version=1, deadline=datetime.now(timezone.utc) + timedelta(minutes=1),
        estimated_operation_class=CostClass.METADATA,
    )
    decision = controller.submit(request)
    resolver = Resolver()
    runtime = ControlledConnectorRuntime(
        controller,
        resolver,
        {"discover_assets": lambda params, credentials: ConnectorOutcome(actual_usage=ActualUsage(response_bytes=10, pages=1))},
    )
    result = runtime.run(permit=decision.permit, source_id=source_id, operation_id="discover_assets", validated_parameters={})
    assert resolver.called
    assert result.source_execution_state == SourceExecutionState.CONFIRMED_FINISHED
    assert "credential" not in result.model_dump_json()


def test_runtime_error_retains_unknown_capacity(tmp_path):
    _, controller, workspace_id, project_id, run_id, group_id = setup_controller(tmp_path)
    source_id = uuid4()
    controller.register_connection_alias(
        workspace_id=workspace_id, connection_id=uuid4(), source_id=source_id,
        resource_group_ids=[group_id], connector_id="postgresql",
        allowed_operations={"discover_assets"}, authorized_scope=["public"],
    )
    request = EvidenceRequest(
        workspace_id=workspace_id, project_id=project_id, run_id=run_id, task_id=uuid4(),
        source_id=source_id, resource_group_ids=[group_id], connector_id="postgresql",
        connector_version="1", operation_id="discover_assets", authorized_asset_scope=["public"],
        evidence_fingerprint="runtime-failure-fingerprint", idempotency_key="runtime-failure-idempotency",
        policy_version=1, deadline=datetime.now(timezone.utc) + timedelta(minutes=1),
        estimated_operation_class=CostClass.METADATA,
    )
    decision = controller.submit(request)

    def timeout(_params, _credentials):
        raise TimeoutError("sensitive driver detail")

    result = ControlledConnectorRuntime(controller, Resolver(), {"discover_assets": timeout}).run(
        permit=decision.permit, source_id=source_id, operation_id="discover_assets", validated_parameters={}
    )
    assert result.source_execution_state == SourceExecutionState.OUTCOME_UNKNOWN
    status = controller.status(decision.operation_request_id, workspace_id)
    assert status["slot_charged"] is True
    assert "sensitive driver detail" not in result.sanitized_error

