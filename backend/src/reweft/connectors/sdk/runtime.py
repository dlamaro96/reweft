from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import UUID

from reweft.domain.models import ActualUsage, ExecutionPermit, OperationResult, SourceExecutionState
from reweft.source_control import WorkloadController


class SecretResolver(Protocol):
    def resolve_for_source(self, source_id: UUID) -> Mapping[str, str]: ...


@dataclass(frozen=True)
class ConnectorOutcome:
    evidence_refs: tuple[UUID, ...] = ()
    source_native_execution_reference: str | None = None
    actual_usage: ActualUsage = field(default_factory=ActualUsage)
    next_cursor: str | None = None


OperationHandler = Callable[[Mapping[str, Any], Mapping[str, str]], ConnectorOutcome]


class ControlledConnectorRuntime:
    """Only named, registered operations can cross the source boundary.

    The permit is consumed immediately before secret resolution and handler I/O.
    There is deliberately no generic ``execute(sql)`` or arbitrary function API.
    """

    def __init__(
        self,
        controller: WorkloadController,
        secret_resolver: SecretResolver,
        operations: Mapping[str, OperationHandler],
    ):
        self.controller = controller
        self.secret_resolver = secret_resolver
        self.operations = dict(operations)

    def run(
        self,
        *,
        permit: ExecutionPermit,
        source_id: UUID,
        operation_id: str,
        validated_parameters: Mapping[str, Any],
    ) -> OperationResult:
        handler = self.operations.get(operation_id)
        if handler is None:
            raise ValueError("connector operation is not registered")
        attempt_id = self.controller.begin_execution(permit)
        try:
            # Credentials become available only after the authoritative permit is
            # validated and consumed. They are never included in OperationResult.
            credentials = self.secret_resolver.resolve_for_source(source_id)
            outcome = handler(validated_parameters, credentials)
            result = OperationResult(
                operation_request_id=permit.operation_request_id,
                attempt_id=attempt_id,
                source_execution_state=SourceExecutionState.CONFIRMED_FINISHED,
                source_native_execution_reference=outcome.source_native_execution_reference,
                evidence_refs=list(outcome.evidence_refs),
                actual_usage=outcome.actual_usage,
                next_cursor=outcome.next_cursor,
            )
        except Exception as exc:
            # An exception after admission cannot prove that source-side work ended.
            # Preserve capacity for bounded connector-specific reconciliation.
            result = OperationResult(
                operation_request_id=permit.operation_request_id,
                attempt_id=attempt_id,
                source_execution_state=SourceExecutionState.OUTCOME_UNKNOWN,
                sanitized_error=f"connector operation did not return a confirmed terminal outcome ({type(exc).__name__})",
            )
        self.controller.record_result(result)
        return result
