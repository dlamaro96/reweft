from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError

from .models import (
    AnalysisActivityInput, AssessmentWorkflowInput, CollectionActivityInput, DesignActivityInput,
    FinalizeActivityInput, InferenceActivityInput, ProviderTestWorkflowInput, SourceTestWorkflowInput,
    ValidationActivityInput,
)


ANALYSIS_QUEUE = "analysis"
COLLECTOR_QUEUE = "collector"
INFERENCE_QUEUE = "inference"
RETRY = RetryPolicy(initial_interval=timedelta(seconds=1), maximum_interval=timedelta(seconds=10), maximum_attempts=2)
COLLECTION_RETRY = RetryPolicy(initial_interval=timedelta(seconds=1), maximum_interval=timedelta(seconds=4), maximum_attempts=4)


@workflow.defn
class AssessmentWorkflow:
    def __init__(self) -> None:
        self._paused = False
        self._cancelled = False

    @workflow.signal
    def pause(self) -> None:
        self._paused = True

    @workflow.signal
    def resume(self) -> None:
        self._paused = False

    @workflow.signal
    def cancel(self) -> None:
        self._cancelled = True
        self._paused = False

    @workflow.query
    def control_state(self) -> dict[str, bool]:
        return {"paused": self._paused, "cancelled": self._cancelled}

    async def _gate(self, item: AssessmentWorkflowInput) -> bool:
        if self._paused:
            await workflow.execute_activity(
                "set_run_state", {"workspace_id": item.workspace_id, "run_id": item.run_id, "state": "paused-by-user"},
                start_to_close_timeout=timedelta(seconds=20), retry_policy=RETRY,
            )
            await workflow.wait_condition(lambda: not self._paused or self._cancelled)
        if self._cancelled:
            await workflow.execute_activity(
                "set_run_state", {"workspace_id": item.workspace_id, "run_id": item.run_id, "state": "cancelled"},
                start_to_close_timeout=timedelta(seconds=20), retry_policy=RETRY,
            )
            return False
        return True

    @workflow.run
    async def run(self, item: AssessmentWorkflowInput) -> dict:
        try:
            return await self._run_assessment(item)
        except Exception as exc:
            # Persist a bounded failure state without serializing provider, source,
            # or SDK exception messages into durable workflow-visible records.
            try:
                await workflow.execute_activity(
                    "set_run_state",
                    {"workspace_id": item.workspace_id, "run_id": item.run_id, "state": "failed", "gaps": [f"Workflow failed in {type(exc).__name__}."]},
                    start_to_close_timeout=timedelta(seconds=20), retry_policy=RETRY,
                )
            except ActivityError:
                pass
            raise

    async def _run_assessment(self, item: AssessmentWorkflowInput) -> dict:
        gaps: list[str] = []
        await workflow.execute_activity("set_run_state", {"workspace_id": item.workspace_id, "run_id": item.run_id, "state": "collecting"}, start_to_close_timeout=timedelta(seconds=20), retry_policy=RETRY)
        evidence_ids: list[str] = []
        for source_id in item.source_ids[:32]:
            if not await self._gate(item):
                return {"state": "cancelled", "gaps": gaps}
            for operation in ("discover_assets", "get_definitions"):
                try:
                    result = await workflow.execute_activity(
                        "collect_source_operation", CollectionActivityInput(item.workspace_id, item.project_id, item.run_id, source_id, operation),
                        task_queue=COLLECTOR_QUEUE, start_to_close_timeout=timedelta(minutes=3), heartbeat_timeout=timedelta(seconds=45), retry_policy=COLLECTION_RETRY,
                    )
                    evidence_ids.extend(result["evidence_ids"])
                except ActivityError as exc:
                    if operation == "discover_assets":
                        # It may be an artifact source, whose single fixed operation is import_bundle.
                        try:
                            result = await workflow.execute_activity(
                                "collect_source_operation", CollectionActivityInput(item.workspace_id, item.project_id, item.run_id, source_id, None),
                                task_queue=COLLECTOR_QUEUE, start_to_close_timeout=timedelta(minutes=3), heartbeat_timeout=timedelta(seconds=45), retry_policy=COLLECTION_RETRY,
                            )
                            evidence_ids.extend(result["evidence_ids"]); break
                        except ActivityError:
                            pass
                    gaps.append(f"Source {source_id} operation {operation} was not collected: {type(exc).__name__}")
        if not await self._gate(item):
            return {"state": "cancelled", "gaps": gaps}
        await workflow.execute_activity("set_run_state", {"workspace_id": item.workspace_id, "run_id": item.run_id, "state": "analyzing"}, start_to_close_timeout=timedelta(seconds=20), retry_policy=RETRY)
        analysis = await workflow.execute_activity("analyze_run", AnalysisActivityInput(item.workspace_id, item.project_id, item.run_id, item.objective, evidence_ids), start_to_close_timeout=timedelta(minutes=2), retry_policy=RETRY)
        gaps.extend(analysis["unresolved"])
        inference = None
        try:
            inference = await workflow.execute_activity(
                "invoke_inference", InferenceActivityInput(item.workspace_id, item.run_id, item.inference_profile_id, {"metrics": analysis["metrics"], "findings": analysis["findings"], "unresolved": analysis["unresolved"]}),
                task_queue=INFERENCE_QUEUE, start_to_close_timeout=timedelta(minutes=3), retry_policy=RETRY,
            )
        except ActivityError as exc:
            gaps.append(f"Inference summary unavailable: {type(exc).__name__}")
        if not await self._gate(item):
            return {"state": "cancelled", "gaps": gaps}
        await workflow.execute_activity("set_run_state", {"workspace_id": item.workspace_id, "run_id": item.run_id, "state": "designing"}, start_to_close_timeout=timedelta(seconds=20), retry_policy=RETRY)
        design = await workflow.execute_activity("design_modernization", DesignActivityInput(item.workspace_id, item.project_id, item.run_id, item.objective, analysis, inference), start_to_close_timeout=timedelta(minutes=2), retry_policy=RETRY)
        await workflow.execute_activity("set_run_state", {"workspace_id": item.workspace_id, "run_id": item.run_id, "state": "verifying"}, start_to_close_timeout=timedelta(seconds=20), retry_policy=RETRY)
        validation = await workflow.execute_activity("validate_generated_target", ValidationActivityInput(item.workspace_id, item.run_id, design["scenario_id"], design["spec_id"]), start_to_close_timeout=timedelta(minutes=2), retry_policy=RETRY)
        if validation["validation"]["status"] != "passed":
            gaps.append("Generated target did not pass its independent synthetic fixture.")
        return await workflow.execute_activity(
            "finalize_run", FinalizeActivityInput(item.workspace_id, item.run_id, sorted(set(gaps)), {"evidence_ids": sorted(set(evidence_ids)), "analysis": analysis, "modernization": {"scenario_id": design["scenario_id"], "spec_id": design["spec_id"]}, "export": validation}),
            start_to_close_timeout=timedelta(seconds=30), retry_policy=RETRY,
        )


@workflow.defn
class SourceTestWorkflow:
    @workflow.run
    async def run(self, item: SourceTestWorkflowInput) -> dict:
        return await workflow.execute_activity(
            "collect_source_operation", CollectionActivityInput(item.workspace_id, item.project_id, item.run_id, item.source_id, "test_connection"),
            task_queue=COLLECTOR_QUEUE, start_to_close_timeout=timedelta(minutes=2), heartbeat_timeout=timedelta(seconds=45), retry_policy=COLLECTION_RETRY,
        )


@workflow.defn
class ProviderTestWorkflow:
    @workflow.run
    async def run(self, item: ProviderTestWorkflowInput) -> dict:
        return await workflow.execute_activity(
            "invoke_inference", InferenceActivityInput(item.workspace_id, None, item.profile_id, {"classification": "synthetic-probe", "contains_customer_data": False}, "provider-test"),
            task_queue=INFERENCE_QUEUE, start_to_close_timeout=timedelta(minutes=2), retry_policy=RETRY,
        )
