from __future__ import annotations

import os
from typing import Any

from temporalio.client import Client

from .models import AssessmentWorkflowInput, ProviderTestWorkflowInput, SourceTestWorkflowInput
from .workflows import ANALYSIS_QUEUE, AssessmentWorkflow, ProviderTestWorkflow, SourceTestWorkflow


async def temporal_client(address: str | None = None) -> Client:
    return await Client.connect(address or os.getenv("TEMPORAL_ADDRESS", "127.0.0.1:7233"))


async def start_assessment_workflow(item: AssessmentWorkflowInput, *, client: Client | None = None) -> str:
    active = client or await temporal_client()
    workflow_id = f"reweft-assessment-{item.run_id}"
    await active.start_workflow(AssessmentWorkflow.run, item, id=workflow_id, task_queue=ANALYSIS_QUEUE)
    return workflow_id


async def signal_assessment_workflow(run_id: str, action: str, *, client: Client | None = None) -> None:
    if action not in {"pause", "resume", "cancel"}:
        raise ValueError("workflow signal must be pause, resume, or cancel")
    active = client or await temporal_client()
    await active.get_workflow_handle(f"reweft-assessment-{run_id}").signal(action)


async def start_source_test_workflow(item: SourceTestWorkflowInput, *, client: Client | None = None) -> str:
    active = client or await temporal_client()
    workflow_id = f"reweft-source-test-{item.run_id}-{item.source_id}"
    await active.start_workflow(SourceTestWorkflow.run, item, id=workflow_id, task_queue=ANALYSIS_QUEUE)
    return workflow_id


async def start_provider_test_workflow(item: ProviderTestWorkflowInput, *, test_id: str, client: Client | None = None) -> str:
    active = client or await temporal_client()
    workflow_id = f"reweft-provider-test-{test_id}"
    await active.start_workflow(ProviderTestWorkflow.run, item, id=workflow_id, task_queue=ANALYSIS_QUEUE)
    return workflow_id
