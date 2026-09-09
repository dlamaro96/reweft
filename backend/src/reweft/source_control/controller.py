from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from reweft.domain.models import (
    ActualUsage,
    AdmissionDecision,
    EvidenceRequest,
    ExecutionPermit,
    OperationResult,
    ReservedLimits,
    SourceExecutionState,
    SourcePolicy,
)
from reweft.persistence import Database


ACTIVE_STATES = {
    SourceExecutionState.RESERVED.value,
    SourceExecutionState.DISPATCHED.value,
    SourceExecutionState.EXECUTING.value,
    SourceExecutionState.CANCEL_REQUESTED.value,
    SourceExecutionState.OUTCOME_UNKNOWN.value,
}
TERMINAL_STATES = {
    SourceExecutionState.CONFIRMED_FINISHED.value,
    SourceExecutionState.CONFIRMED_CANCELLED.value,
    SourceExecutionState.REJECTED.value,
}


class AdmissionError(ValueError):
    def __init__(self, code: str, detail: str, status_code: int = 422):
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status_code = status_code


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _json(value: Any) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


class WorkloadController:
    """Durable, fail-closed admission and permit service.

    All capacity checks and reservations happen in one short ``BEGIN IMMEDIATE``
    transaction. An unknown external outcome deliberately remains slot-charged.
    """

    def __init__(self, database: Database, signing_key: bytes | None = None, *, verification_key: bytes | None = None):
        if signing_key is None and verification_key is None:
            raise ValueError("a permit signing or verification key is required")
        self.database = database
        self._legacy_hmac_key: bytes | None = None
        self._private_key: Ed25519PrivateKey | None = None
        self._public_key: Ed25519PublicKey | None = None
        if signing_key and signing_key.startswith(b"-----BEGIN"):
            loaded = serialization.load_pem_private_key(signing_key, password=None)
            if not isinstance(loaded, Ed25519PrivateKey):
                raise ValueError("permit signing key must be Ed25519")
            self._private_key, self._public_key = loaded, loaded.public_key()
        elif verification_key:
            loaded = serialization.load_pem_public_key(verification_key)
            if not isinstance(loaded, Ed25519PublicKey):
                raise ValueError("permit verification key must be Ed25519")
            self._public_key = loaded
        elif signing_key:
            # Compatibility for existing SQLite tests and previously generated demo
            # configuration. Real mode requires the asymmetric key-file path.
            if len(signing_key) < 32:
                raise ValueError("permit signing key must be at least 32 bytes")
            self._legacy_hmac_key = signing_key

    def create_resource_group(
        self,
        resource_fingerprint: str,
        policy: SourcePolicy,
        *,
        parent_id: UUID | None = None,
        group_id: UUID | None = None,
    ) -> UUID:
        group_id = group_id or uuid4()
        now = _iso(_now())
        try:
            with self.database.transaction(immediate=True) as connection:
                connection.execute(
                    "INSERT INTO resource_groups(id,parent_id,resource_fingerprint,policy_json,policy_version,created_at) VALUES(?,?,?,?,1,?)",
                    (str(group_id), str(parent_id) if parent_id else None, resource_fingerprint, _json(policy), now),
                )
        except sqlite3.IntegrityError as exc:
            raise AdmissionError("RESOURCE_GROUP_CONFLICT", "resource fingerprint or group already exists", 409) from exc
        return group_id

    def register_connection_alias(
        self,
        *,
        workspace_id: UUID,
        connection_id: UUID,
        source_id: UUID,
        resource_group_ids: list[UUID],
        connector_id: str,
        allowed_operations: set[str],
        authorized_scope: list[str],
    ) -> None:
        if not resource_group_ids or not allowed_operations or not authorized_scope:
            raise AdmissionError("INVALID_ALIAS", "resource groups, operations, and scope are required")
        now = _iso(_now())
        with self.database.transaction(immediate=True) as connection:
            if not connection.execute("SELECT 1 FROM workspaces WHERE id=?", (str(workspace_id),)).fetchone():
                raise AdmissionError("WORKSPACE_NOT_FOUND", "workspace not found", 404)
            for group_id in resource_group_ids:
                if not connection.execute("SELECT 1 FROM resource_groups WHERE id=?", (str(group_id),)).fetchone():
                    raise AdmissionError("RESOURCE_GROUP_NOT_FOUND", "resource group not found", 404)
                connection.execute(
                    "INSERT INTO connection_aliases(workspace_id,connection_id,source_id,resource_group_id,connector_id,allowed_operations_json,authorized_scope_json,created_at) VALUES(?,?,?,?,?,?,?,?)",
                    (
                        str(workspace_id), str(connection_id), str(source_id), str(group_id), connector_id,
                        _json(sorted(allowed_operations)), _json(authorized_scope), now,
                    ),
                )

    def _resolve_alias(self, connection: sqlite3.Connection, request: EvidenceRequest) -> tuple[str, list[str], set[str], list[str]]:
        rows = connection.execute(
            "SELECT * FROM connection_aliases WHERE workspace_id=? AND source_id=? ORDER BY connection_id,resource_group_id",
            (str(request.workspace_id), str(request.source_id)),
        ).fetchall()
        if not rows:
            raise AdmissionError("SOURCE_NOT_AUTHORIZED", "source is not configured in this workspace", 403)
        # A source identifier resolves to one local connection. Multiple rows model its hierarchy.
        connection_ids = {row["connection_id"] for row in rows}
        if len(connection_ids) != 1:
            raise AdmissionError("AMBIGUOUS_SOURCE_ALIAS", "source identifier maps to multiple connections", 409)
        if any(row["connector_id"] != request.connector_id for row in rows):
            raise AdmissionError("CONNECTOR_MISMATCH", "connector does not match configured source", 403)
        configured_groups = sorted({row["resource_group_id"] for row in rows})
        requested_groups = sorted(str(group_id) for group_id in request.resource_group_ids)
        if configured_groups != requested_groups:
            raise AdmissionError("RESOURCE_GROUP_MISMATCH", "resource groups must be resolved from the configured source", 403)
        operations = set.intersection(*(set(json.loads(row["allowed_operations_json"])) for row in rows))
        if request.operation_id not in operations:
            raise AdmissionError("OPERATION_NOT_ALLOWED", "operation is not in the connector's semantic allowlist", 403)
        scopes = list(json.loads(rows[0]["authorized_scope_json"]))
        if not all(any(asset == root or asset.startswith(root.rstrip("/") + "/") for root in scopes) for asset in request.authorized_asset_scope):
            raise AdmissionError("SCOPE_EXPANSION_DENIED", "requested assets exceed the configured source scope", 403)
        return next(iter(connection_ids)), configured_groups, operations, scopes

    def submit(self, request: EvidenceRequest) -> AdmissionDecision:
        now = _now()
        if request.deadline.astimezone(timezone.utc) <= now:
            raise AdmissionError("REQUEST_DEADLINE_EXPIRED", "request deadline has expired")
        operation_id = uuid4()
        with self.database.transaction(immediate=True) as connection:
            self._validate_domain_links(connection, request)
            alias_id, group_ids, _, _ = self._resolve_alias(connection, request)
            existing = connection.execute(
                "SELECT * FROM source_operations WHERE workspace_id=? AND idempotency_key=?",
                (str(request.workspace_id), request.idempotency_key),
            ).fetchone()
            if existing:
                return self._decision_from_row(existing, reason="idempotency-key-reuse")
            equivalent = connection.execute(
                "SELECT * FROM source_operations WHERE workspace_id=? AND evidence_fingerprint=? ORDER BY queued_at DESC LIMIT 1",
                (str(request.workspace_id), request.evidence_fingerprint),
            ).fetchone()
            if equivalent and (equivalent["state"] in ACTIVE_STATES or equivalent["state"] == SourceExecutionState.QUEUED.value):
                return self._decision_from_row(equivalent, reason="equivalent-operation-in-flight")
            connection.execute(
                "INSERT INTO source_operations(id,workspace_id,project_id,run_id,task_id,source_id,connection_id,connector_id,connector_version,operation_id,resource_group_ids_json,request_json,evidence_fingerprint,idempotency_key,cost_class,state,queued_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    str(operation_id), str(request.workspace_id), str(request.project_id), str(request.run_id),
                    str(request.task_id), str(request.source_id), alias_id, request.connector_id,
                    request.connector_version, request.operation_id, _json(group_ids), _json(request),
                    request.evidence_fingerprint, request.idempotency_key,
                    request.estimated_operation_class.value, SourceExecutionState.QUEUED.value, _iso(now), _iso(now),
                ),
            )
            self._event(connection, str(request.workspace_id), str(operation_id), "queued", {"cost_class": request.estimated_operation_class.value})
            return self._try_admit_locked(connection, str(operation_id), now)

    def _validate_domain_links(self, connection: sqlite3.Connection, request: EvidenceRequest) -> None:
        project = connection.execute("SELECT workspace_id FROM projects WHERE id=?", (str(request.project_id),)).fetchone()
        run = connection.execute("SELECT workspace_id,project_id,state FROM assessments WHERE id=?", (str(request.run_id),)).fetchone()
        if not project or project["workspace_id"] != str(request.workspace_id):
            raise AdmissionError("PROJECT_NOT_AUTHORIZED", "project is not in the workspace", 403)
        if not run or run["workspace_id"] != str(request.workspace_id) or run["project_id"] != str(request.project_id):
            raise AdmissionError("RUN_NOT_AUTHORIZED", "assessment run is not in the project", 403)
        if run["state"] in {"paused-by-user", "paused-by-source-policy", "paused-by-budget", "cancelled", "completed", "completed-with-gaps", "failed"}:
            raise AdmissionError("RUN_NOT_ADMITTING", f"run state {run['state']} does not admit source work", 409)

    def try_admit_queued(self, operation_request_id: UUID) -> AdmissionDecision:
        with self.database.transaction(immediate=True) as connection:
            return self._try_admit_locked(connection, str(operation_request_id), _now())

    def _try_admit_locked(self, connection: sqlite3.Connection, operation_id: str, now: datetime) -> AdmissionDecision:
        row = connection.execute("SELECT * FROM source_operations WHERE id=?", (operation_id,)).fetchone()
        if not row:
            raise AdmissionError("OPERATION_NOT_FOUND", "operation not found", 404)
        if row["state"] != SourceExecutionState.QUEUED.value:
            return self._decision_from_row(row)
        request = EvidenceRequest.model_validate_json(row["request_json"])
        group_ids: list[str] = json.loads(row["resource_group_ids_json"])
        group_rows = [connection.execute("SELECT * FROM resource_groups WHERE id=?", (group_id,)).fetchone() for group_id in group_ids]
        if any(group is None for group in group_rows):
            raise AdmissionError("RESOURCE_GROUP_NOT_FOUND", "configured resource group no longer exists", 409)
        # FIFO fairness among queued work that overlaps any constrained group.
        for queued in connection.execute("SELECT id,resource_group_ids_json FROM source_operations WHERE state=? AND queued_at<?", (SourceExecutionState.QUEUED.value, row["queued_at"])).fetchall():
            if set(json.loads(queued["resource_group_ids_json"])) & set(group_ids):
                return AdmissionDecision(operation_request_id=UUID(operation_id), state=SourceExecutionState.QUEUED, reason="waiting-for-earlier-workspace-request")
        active_rows = connection.execute("SELECT resource_group_ids_json FROM source_operations WHERE slot_charged=1").fetchall()
        active_counts = {group_id: 0 for group_id in group_ids}
        for active in active_rows:
            for group_id in set(json.loads(active["resource_group_ids_json"])) & set(group_ids):
                active_counts[group_id] += 1
        policies: list[SourcePolicy] = []
        for group in group_rows:
            policy = SourcePolicy.model_validate_json(group["policy_json"])
            policies.append(policy)
            if active_counts[group["id"]] >= policy.max_active_operations:
                return AdmissionDecision(operation_request_id=UUID(operation_id), state=SourceExecutionState.QUEUED, reason="shared-resource-capacity-retained")
            if group["last_admitted_at"]:
                earliest = datetime.fromisoformat(group["last_admitted_at"]) + timedelta(milliseconds=policy.min_request_interval_ms)
                if now < earliest:
                    return AdmissionDecision(operation_request_id=UUID(operation_id), state=SourceExecutionState.QUEUED, reason="shared-resource-rate-limit")
            try:
                local_hour = now.astimezone(ZoneInfo(policy.timezone)).hour
            except ZoneInfoNotFoundError as exc:
                raise AdmissionError("INVALID_POLICY_TIMEZONE", "resource policy timezone is invalid", 409) from exc
            if not (policy.allowed_hours_start <= local_hour < policy.allowed_hours_end):
                return AdmissionDecision(operation_request_id=UUID(operation_id), state=SourceExecutionState.QUEUED, reason="outside-permitted-window")
            if request.estimated_operation_class.value == "profile" and not policy.profiling_enabled:
                raise AdmissionError("PROFILING_DISABLED", "profiling is disabled by shared resource policy", 403)
            if request.estimated_limits.response_bytes > policy.max_response_bytes or request.estimated_limits.pages > policy.max_pages_per_operation or request.estimated_limits.duration_seconds > policy.request_deadline_seconds:
                raise AdmissionError("ESTIMATE_EXCEEDS_POLICY", "estimated operation limits exceed resource policy", 422)
            usage_rows = connection.execute(
                "SELECT result_json FROM source_operations WHERE run_id=? AND cost_class=?",
                (row["run_id"], row["cost_class"]),
            ).fetchall()
            used_bytes = sum(
                int((json.loads(item["result_json"]).get("actual_usage") or {}).get("response_bytes", 0))
                for item in usage_rows
                if item["result_json"]
            )
            if len(usage_rows) >= policy.max_operations_per_run or used_bytes + request.estimated_limits.response_bytes > policy.max_collection_bytes_per_run:
                return AdmissionDecision(operation_request_id=UUID(operation_id), state=SourceExecutionState.QUEUED, reason="run-collection-budget-exhausted")
        generation = max(int(group["fencing_generation"]) for group in group_rows) + 1
        permit_id = uuid4()
        ttl = min(policy.permit_ttl_seconds for policy in policies)
        deadline_seconds = min(policy.request_deadline_seconds for policy in policies)
        expires_at = min(now + timedelta(seconds=ttl), request.deadline.astimezone(timezone.utc))
        reserved_deadline = min(now + timedelta(seconds=deadline_seconds), request.deadline.astimezone(timezone.utc))
        policy_version = max(int(group["policy_version"]) for group in group_rows)
        if request.policy_version != policy_version:
            raise AdmissionError("POLICY_REVISION_STALE", "request policy revision is not current", 409)
        payload = {
            "operation_request_id": operation_id,
            "permit_id": str(permit_id),
            "groups": group_ids,
            "generation": generation,
            "expires_at": _iso(expires_at),
            "policy_version": policy_version,
        }
        token = self._sign(payload)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        connection.execute(
            "UPDATE source_operations SET state=?,slot_charged=1,permit_id=?,permit_token_hash=?,fencing_generation=?,permit_expires_at=?,updated_at=? WHERE id=?",
            (SourceExecutionState.RESERVED.value, str(permit_id), token_hash, generation, _iso(expires_at), _iso(now), operation_id),
        )
        for group in group_rows:
            connection.execute("UPDATE resource_groups SET fencing_generation=?,last_admitted_at=? WHERE id=?", (generation, _iso(now), group["id"]))
        self._event(connection, row["workspace_id"], operation_id, "reserved", {"permit_id": str(permit_id), "generation": generation})
        permit = ExecutionPermit(
            operation_request_id=UUID(operation_id), permitted_resource_groups=[UUID(value) for value in group_ids],
            permit_id=permit_id, fencing_generation=generation, expires_at=expires_at,
            reserved_limits=ReservedLimits(
                max_response_bytes=min(policy.max_response_bytes for policy in policies),
                max_pages=min(policy.max_pages_per_operation for policy in policies), deadline=reserved_deadline,
            ),
            policy_version=policy_version, token=token,
        )
        return AdmissionDecision(operation_request_id=UUID(operation_id), state=SourceExecutionState.RESERVED, permit=permit)

    def begin_execution(self, permit: ExecutionPermit, *, lease_seconds: int = 30) -> UUID:
        now = _now()
        payload = self._verify_signature(permit.token)
        if payload.get("operation_request_id") != str(permit.operation_request_id) or payload.get("permit_id") != str(permit.permit_id):
            raise AdmissionError("PERMIT_TAMPERED", "permit claims do not match token", 403)
        with self.database.transaction(immediate=True) as connection:
            row = connection.execute("SELECT * FROM source_operations WHERE id=?", (str(permit.operation_request_id),)).fetchone()
            if not row or row["permit_id"] != str(permit.permit_id) or row["permit_token_hash"] != hashlib.sha256(permit.token.encode()).hexdigest():
                raise AdmissionError("PERMIT_INVALID", "permit is not active for this operation", 403)
            if row["state"] != SourceExecutionState.RESERVED.value:
                raise AdmissionError("PERMIT_ALREADY_USED", "permit cannot start new I/O", 409)
            if now >= datetime.fromisoformat(row["permit_expires_at"]):
                connection.execute("UPDATE source_operations SET state=?,slot_charged=0,updated_at=? WHERE id=?", (SourceExecutionState.REJECTED.value, _iso(now), row["id"]))
                self._event(connection, row["workspace_id"], row["id"], "permit-expired-before-io", {})
                raise AdmissionError("PERMIT_EXPIRED", "permit expired before source I/O", 409)
            attempt_id = uuid4()
            connection.execute(
                "UPDATE source_operations SET state=?,attempt_id=?,attempt_count=attempt_count+1,lease_expires_at=?,admitted_at=?,updated_at=? WHERE id=?",
                (SourceExecutionState.EXECUTING.value, str(attempt_id), _iso(now + timedelta(seconds=lease_seconds)), _iso(now), _iso(now), row["id"]),
            )
            self._event(connection, row["workspace_id"], row["id"], "executing", {"attempt_id": str(attempt_id)})
            return attempt_id

    def heartbeat(self, operation_request_id: UUID, attempt_id: UUID, *, lease_seconds: int = 30) -> None:
        now = _now()
        with self.database.transaction(immediate=True) as connection:
            cursor = connection.execute(
                "UPDATE source_operations SET lease_expires_at=?,updated_at=? WHERE id=? AND attempt_id=? AND state IN (?,?)",
                (_iso(now + timedelta(seconds=lease_seconds)), _iso(now), str(operation_request_id), str(attempt_id), SourceExecutionState.EXECUTING.value, SourceExecutionState.CANCEL_REQUESTED.value),
            )
            if cursor.rowcount != 1:
                raise AdmissionError("ATTEMPT_NOT_ACTIVE", "attempt is not active", 409)

    def record_result(self, result: OperationResult) -> None:
        if result.source_execution_state not in {SourceExecutionState.CONFIRMED_FINISHED, SourceExecutionState.CONFIRMED_CANCELLED, SourceExecutionState.OUTCOME_UNKNOWN}:
            raise AdmissionError("INVALID_RESULT_STATE", "result must be terminal or outcome-unknown")
        now = _now()
        with self.database.transaction(immediate=True) as connection:
            row = connection.execute("SELECT * FROM source_operations WHERE id=?", (str(result.operation_request_id),)).fetchone()
            if not row:
                raise AdmissionError("OPERATION_NOT_FOUND", "operation not found", 404)
            if row["attempt_id"] != str(result.attempt_id):
                raise AdmissionError("STALE_ATTEMPT", "stale attempt cannot commit a result", 409)
            if row["state"] in TERMINAL_STATES:
                # An activity retry may safely replay the identical committed result.
                if row["result_json"] == _json(result):
                    return
                raise AdmissionError("RESULT_ALREADY_COMMITTED", "a different result is already committed", 409)
            slot_charged = 1 if result.source_execution_state == SourceExecutionState.OUTCOME_UNKNOWN else 0
            connection.execute(
                "UPDATE source_operations SET state=?,slot_charged=?,source_native_reference=?,result_json=?,sanitized_error=?,updated_at=? WHERE id=?",
                (result.source_execution_state.value, slot_charged, result.source_native_execution_reference, _json(result), result.sanitized_error, _iso(now), row["id"]),
            )
            self._event(connection, row["workspace_id"], row["id"], result.source_execution_state.value, {"slot_charged": bool(slot_charged)})

    def request_cancellation(self, operation_request_id: UUID) -> None:
        now = _now()
        with self.database.transaction(immediate=True) as connection:
            row = connection.execute("SELECT * FROM source_operations WHERE id=?", (str(operation_request_id),)).fetchone()
            if not row:
                raise AdmissionError("OPERATION_NOT_FOUND", "operation not found", 404)
            if row["state"] not in {SourceExecutionState.EXECUTING.value, SourceExecutionState.DISPATCHED.value}:
                raise AdmissionError("OPERATION_NOT_CANCELLABLE", "operation is not in a cancellable state", 409)
            connection.execute("UPDATE source_operations SET state=?,updated_at=? WHERE id=?", (SourceExecutionState.CANCEL_REQUESTED.value, _iso(now), row["id"]))
            self._event(connection, row["workspace_id"], row["id"], "cancel-requested", {})

    def expire_leases(self) -> int:
        """Mark lost executing work unknown without releasing its capacity."""
        now = _now()
        with self.database.transaction(immediate=True) as connection:
            rows = connection.execute(
                "SELECT * FROM source_operations WHERE state IN (?,?) AND lease_expires_at IS NOT NULL AND lease_expires_at<?",
                (SourceExecutionState.EXECUTING.value, SourceExecutionState.CANCEL_REQUESTED.value, _iso(now)),
            ).fetchall()
            for row in rows:
                connection.execute("UPDATE source_operations SET state=?,slot_charged=1,updated_at=? WHERE id=?", (SourceExecutionState.OUTCOME_UNKNOWN.value, _iso(now), row["id"]))
                self._event(connection, row["workspace_id"], row["id"], "lease-expired-outcome-unknown", {"slot_charged": True})
            return len(rows)

    def reconcile(self, operation_request_id: UUID, *, confirmed_state: SourceExecutionState, confirmation: str) -> None:
        if confirmed_state not in {SourceExecutionState.CONFIRMED_FINISHED, SourceExecutionState.CONFIRMED_CANCELLED}:
            raise AdmissionError("INVALID_RECONCILIATION", "reconciliation requires a confirmed terminal state")
        now = _now()
        with self.database.transaction(immediate=True) as connection:
            row = connection.execute("SELECT * FROM source_operations WHERE id=?", (str(operation_request_id),)).fetchone()
            if not row or row["state"] not in {SourceExecutionState.OUTCOME_UNKNOWN.value, SourceExecutionState.CANCEL_REQUESTED.value}:
                raise AdmissionError("NOT_RECONCILABLE", "operation is not awaiting reconciliation", 409)
            connection.execute("UPDATE source_operations SET state=?,slot_charged=0,updated_at=? WHERE id=?", (confirmed_state.value, _iso(now), row["id"]))
            self._event(connection, row["workspace_id"], row["id"], "reconciled", {"state": confirmed_state.value, "confirmation": confirmation[:500]})

    def status(self, operation_request_id: UUID, workspace_id: UUID) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM source_operations WHERE id=? AND workspace_id=?", (str(operation_request_id), str(workspace_id))).fetchone()
            if not row:
                raise AdmissionError("OPERATION_NOT_FOUND", "operation not found", 404)
            return self._public_status(row)

    def resource_health(self, workspace_id: UUID, source_id: UUID) -> dict[str, Any]:
        with self.database.connect() as connection:
            aliases = connection.execute("SELECT resource_group_id FROM connection_aliases WHERE workspace_id=? AND source_id=?", (str(workspace_id), str(source_id))).fetchall()
            if not aliases:
                raise AdmissionError("SOURCE_NOT_FOUND", "source not found", 404)
            group_ids = {row["resource_group_id"] for row in aliases}
            operations = connection.execute("SELECT state,slot_charged,resource_group_ids_json,updated_at FROM source_operations WHERE slot_charged=1 OR state=?", (SourceExecutionState.QUEUED.value,)).fetchall()
            relevant = [row for row in operations if set(json.loads(row["resource_group_ids_json"])) & group_ids]
            unknown = sum(row["state"] == SourceExecutionState.OUTCOME_UNKNOWN.value for row in relevant)
            active = sum(bool(row["slot_charged"]) for row in relevant)
            queued = sum(row["state"] == SourceExecutionState.QUEUED.value for row in relevant)
            return {
                "health_mode": "unknown" if unknown else "conservative",
                "active_operations": active,
                "queue_depth": queued,
                "uncertain_executions": unknown,
                "pause_reasons": ["source execution outcome unknown"] if unknown else [],
                "termination_status": "unknown" if unknown else "no-unknown-execution",
            }

    def _sign(self, payload: dict[str, Any]) -> str:
        encoded = base64.urlsafe_b64encode(_json(payload).encode()).rstrip(b"=").decode()
        if self._private_key:
            signature = base64.urlsafe_b64encode(self._private_key.sign(encoded.encode())).rstrip(b"=").decode()
            return f"ed25519.{encoded}.{signature}"
        if self._legacy_hmac_key:
            signature = hmac.new(self._legacy_hmac_key, encoded.encode(), hashlib.sha256).hexdigest()
            return f"hmac-sha256.{encoded}.{signature}"
        raise AdmissionError("PERMIT_AUTHORITY_UNAVAILABLE", "this process cannot issue source permits", 503)

    def _verify_signature(self, token: str) -> dict[str, Any]:
        try:
            algorithm, encoded, supplied = token.split(".", 2)
            if algorithm == "ed25519" and self._public_key:
                signature = base64.urlsafe_b64decode(supplied + "=" * (-len(supplied) % 4))
                self._public_key.verify(signature, encoded.encode())
            elif algorithm == "hmac-sha256" and self._legacy_hmac_key:
                expected = hmac.new(self._legacy_hmac_key, encoded.encode(), hashlib.sha256).hexdigest()
                if not hmac.compare_digest(supplied, expected):
                    raise ValueError
            else:
                raise ValueError
            padded = encoded + "=" * (-len(encoded) % 4)
            payload = json.loads(base64.urlsafe_b64decode(padded))
            if _now() >= datetime.fromisoformat(payload["expires_at"]):
                raise AdmissionError("PERMIT_EXPIRED", "permit has expired", 409)
            return payload
        except AdmissionError:
            raise
        except Exception as exc:
            raise AdmissionError("PERMIT_INVALID", "permit signature is invalid", 403) from exc

    def _decision_from_row(self, row: sqlite3.Row, reason: str | None = None) -> AdmissionDecision:
        state = SourceExecutionState(row["state"])
        result = OperationResult.model_validate_json(row["result_json"]) if row["result_json"] else None
        return AdmissionDecision(operation_request_id=UUID(row["id"]), state=state, reused_result=result, reason=reason)

    @staticmethod
    def _event(connection: sqlite3.Connection, workspace_id: str, operation_id: str, event_type: str, body: dict[str, Any]) -> None:
        connection.execute(
            "INSERT INTO operation_events(workspace_id,operation_id,event_type,body_json,created_at) VALUES(?,?,?,?,?)",
            (workspace_id, operation_id, event_type, _json(body), _iso(_now())),
        )

    @staticmethod
    def _public_status(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "operation_request_id": row["id"],
            "state": row["state"],
            "slot_charged": bool(row["slot_charged"]),
            "cost_class": row["cost_class"],
            "attempt_count": row["attempt_count"],
            "source_native_execution_reference": row["source_native_reference"],
            "sanitized_error": row["sanitized_error"],
            "queued_at": row["queued_at"],
            "admitted_at": row["admitted_at"],
            "updated_at": row["updated_at"],
        }


def generate_signing_key() -> bytes:
    return secrets.token_bytes(32)


def generate_permit_keypair() -> tuple[bytes, bytes]:
    private = Ed25519PrivateKey.generate()
    private_pem = private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem
