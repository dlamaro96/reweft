from __future__ import annotations

import asyncio
import io
import json
import os
import zipfile
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from temporalio.client import Client
from temporalio.exceptions import WorkflowAlreadyStartedError

from reweft.orchestration.models import AssessmentWorkflowInput, ProviderTestWorkflowInput, SourceTestWorkflowInput
from reweft.orchestration.workflows import AssessmentWorkflow, ProviderTestWorkflow, SourceTestWorkflow
from reweft.persistence import Database


def json_value(value: Any) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


class TemporalRuntime:
    """Small API-side Temporal boundary with stable workflow identifiers."""

    def __init__(self, address: str | None = None, task_queue: str = "analysis"):
        self.address = address or os.getenv("TEMPORAL_ADDRESS", "real-temporal:7233")
        self.task_queue = os.getenv("REWEFT_TEMPORAL_TASK_QUEUE", task_queue)

    async def _client(self) -> Client:
        return await Client.connect(self.address)

    async def start_assessment(self, payload: dict[str, Any]) -> None:
        client = await self._client()
        item = AssessmentWorkflowInput(**payload)
        try:
            await client.start_workflow(
                AssessmentWorkflow.run,
                item,
                id=f"reweft-assessment-{item.run_id}",
                task_queue=self.task_queue,
                execution_timeout=timedelta(hours=6),
            )
        except WorkflowAlreadyStartedError:
            return

    async def signal_assessment(self, run_id: str, action: str) -> None:
        client = await self._client()
        handle = client.get_workflow_handle(f"reweft-assessment-{run_id}")
        await handle.signal(action)

    async def execute_source_test(self, payload: dict[str, Any]) -> dict[str, Any]:
        client = await self._client()
        item = SourceTestWorkflowInput(**payload)
        return await client.execute_workflow(
            SourceTestWorkflow.run,
            item,
            id=f"reweft-source-test-{item.source_id}-{uuid4()}",
            task_queue=self.task_queue,
            execution_timeout=timedelta(minutes=3),
        )

    async def execute_profile_test(self, payload: dict[str, Any]) -> dict[str, Any]:
        client = await self._client()
        item = ProviderTestWorkflowInput(**payload)
        return await client.execute_workflow(
            ProviderTestWorkflow.run,
            item,
            id=f"reweft-provider-test-{item.profile_id}-{uuid4()}",
            task_queue=self.task_queue,
            execution_timeout=timedelta(minutes=3),
        )


def run_async(coroutine):
    """Run an async SDK boundary from FastAPI's synchronous worker thread."""
    return asyncio.run(coroutine)


def assessment_payload(database: Database, workspace_id: UUID, run_id: UUID) -> dict[str, Any]:
    with database.connect() as connection:
        row = connection.execute(
            "SELECT body_json FROM assessments WHERE id=? AND workspace_id=?",
            (str(run_id), str(workspace_id)),
        ).fetchone()
        if not row:
            raise LookupError("assessment not found")
        run = json.loads(row["body_json"])
        source_ids = run.get("scope", {}).get("source_ids", [])
        sources = []
        for source_id in source_ids:
            source = connection.execute(
                "SELECT id,name,connector_id,config_json,secret_ref,status FROM sources WHERE id=? AND workspace_id=?",
                (str(source_id), str(workspace_id)),
            ).fetchone()
            if source:
                sources.append(
                    {
                        "id": source["id"],
                        "name": source["name"],
                        "connector_id": source["connector_id"],
                        "configuration": json.loads(source["config_json"]),
                        "secret_ref": source["secret_ref"],
                        "status": source["status"],
                    }
                )
        profile = None
        if run.get("inference_profile_id"):
            profile_row = connection.execute(
                "SELECT body_json FROM inference_profiles WHERE id=? AND workspace_id=?",
                (run["inference_profile_id"], str(workspace_id)),
            ).fetchone()
            if profile_row:
                profile = json.loads(profile_row["body_json"])
    return {
        "workspace_id": str(workspace_id),
        "project_id": run["project_id"],
        "run_id": str(run_id),
        "objective": run["objective"],
        "source_ids": [source["id"] for source in sources],
        "inference_profile_id": profile["id"] if profile else None,
    }


def run_state(database: Database, workspace_id: UUID, run_id: UUID) -> dict[str, Any]:
    with database.connect() as connection:
        row = connection.execute(
            "SELECT body_json FROM assessments WHERE id=? AND workspace_id=?",
            (str(run_id), str(workspace_id)),
        ).fetchone()
        if not row:
            raise LookupError("assessment not found")
        run = json.loads(row["body_json"])
        tasks = []
        for item in connection.execute(
            "SELECT id,task_key,state,owner_role,attempt,body_json,created_at,updated_at "
            "FROM run_tasks WHERE workspace_id=? AND run_id=? ORDER BY created_at",
            (str(workspace_id), str(run_id)),
        ):
            task = json.loads(item["body_json"])
            task.update({key: item[key] for key in ("id", "task_key", "state", "owner_role", "attempt", "created_at", "updated_at")})
            tasks.append(task)
        operations = [dict(item) for item in connection.execute(
            "SELECT id,source_id,operation_id,state,sanitized_error,source_native_reference,updated_at "
            "FROM source_operations WHERE workspace_id=? AND run_id=? ORDER BY queued_at",
            (str(workspace_id), str(run_id)),
        )]
        source_names = {row["id"]: row["name"] for row in connection.execute(
            "SELECT id,name FROM sources WHERE workspace_id=?",
            (str(workspace_id),),
        )}
        evidence = [json.loads(item["body_json"]) for item in connection.execute(
            "SELECT body_json FROM evidence WHERE workspace_id=? AND run_id=? ORDER BY created_at",
            (str(workspace_id), str(run_id)),
        )]
        findings = [json.loads(item["body_json"]) for item in connection.execute(
            "SELECT body_json FROM findings WHERE workspace_id=? AND run_id=? ORDER BY created_at",
            (str(workspace_id), str(run_id)),
        )]
        specs = []
        for item in connection.execute(
            "SELECT scenario_id,body_json FROM modernization_specs WHERE workspace_id=? ORDER BY created_at DESC",
            (str(workspace_id),),
        ):
            parsed = json.loads(item["body_json"])
            parsed["scenario_id"] = item["scenario_id"]
            specs.append(parsed)
        modernization = next((item for item in specs if item.get("run_id") == str(run_id)), None)
        if modernization:
            scenario_row = connection.execute(
                "SELECT name FROM scenarios WHERE id=? AND workspace_id=?",
                (modernization["scenario_id"], str(workspace_id)),
            ).fetchone()
            modernization["scenario"] = scenario_row["name"] if scenario_row else "Evidence-driven target"
            modernization["target_models"] = modernization.get("models", [])
            modernization["work_packages"] = [
                {
                    **package,
                    "status": "proposed",
                    "description": ", ".join(package.get("deliverables", [])),
                }
                for package in modernization.get("work_packages", [])
            ]
        validations = [dict(item) for item in connection.execute(
            "SELECT id,status,evidence_json,created_at FROM validation_results WHERE workspace_id=? AND run_id=? ORDER BY created_at",
            (str(workspace_id), str(run_id)),
        )]
        invocation_rows = [dict(item) for item in connection.execute(
            "SELECT id,profile_id,profile_revision,provider,model,state,actual_usage_json,created_at,updated_at "
            "FROM model_invocations WHERE workspace_id=? AND run_id=? ORDER BY created_at",
            (str(workspace_id), str(run_id)),
        )]
        export_rows = [dict(item) for item in connection.execute(
            "SELECT id,export_type,state,artifact_ref,manifest_json,created_at FROM exports WHERE workspace_id=? AND run_id=? ORDER BY created_at",
            (str(workspace_id), str(run_id)),
        )]
        pending = connection.execute(
            "SELECT COUNT(*) FROM outbox WHERE workspace_id=? AND aggregate_id=? AND published_at IS NULL",
            (str(workspace_id), str(run_id)),
        ).fetchone()[0]
    for operation in operations:
        operation["source_name"] = source_names.get(operation["source_id"])
        operation["operation"] = operation.pop("operation_id")
        operation["actual_termination"] = operation.pop("source_native_reference")
    for result in validations:
        result["evidence"] = json.loads(result.pop("evidence_json"))
    for invocation in invocation_rows:
        invocation["actual_usage"] = json.loads(invocation.pop("actual_usage_json")) if invocation.get("actual_usage_json") else None
    for export in export_rows:
        export["manifest"] = json.loads(export.pop("manifest_json"))
    completed_tasks = sum(1 for task in tasks if task.get("state") in {"completed", "completed-with-gaps"})
    progress = int(completed_tasks * 100 / len(tasks)) if tasks else (100 if run["state"] in {"completed", "completed-with-gaps"} else None)
    current = next((task for task in tasks if task.get("state") in {"running", "queued", "blocked"}), None)
    gaps = list(run.get("gaps", []))
    if modernization:
        gaps.extend(gap for gap in modernization.get("coverage_gaps", []) if gap not in gaps)
    return {
        "run": run,
        "progress": progress,
        "phase": run["state"],
        "message": (current or {}).get("message") or ("Workflow dispatch is pending" if pending else None),
        "tasks": tasks,
        "source_operations": operations,
        "evidence": evidence,
        "findings": findings,
        "modernization": modernization,
        "validation": validations,
        "model_invocations": invocation_rows,
        "exports": export_rows,
        "partial": bool(gaps) or run["state"] == "completed-with-gaps",
        "gaps": gaps,
    }


def build_export(database: Database, workspace_id: UUID, run_id: UUID, artifact_root: str | Path) -> bytes:
    state = run_state(database, workspace_id, run_id)
    root = Path(artifact_root).resolve()
    output = io.BytesIO()
    manifest = {
        "schema_version": "reweft.export/v1",
        "workspace_id": str(workspace_id),
        "run_id": str(run_id),
        "mode": "live",
        "contains_secrets": False,
        "files": [],
    }
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        documents = {
            "run.json": state["run"],
            "evidence/index.json": state["evidence"],
            "findings.json": state["findings"],
            "modernization/specification.json": state["modernization"] or {},
            "validation/results.json": state["validation"],
            "model/invocations.json": state["model_invocations"],
        }
        for name, body in documents.items():
            encoded = json.dumps(body, indent=2, sort_keys=True).encode()
            archive.writestr(name, encoded)
            manifest["files"].append({"path": name, "bytes": len(encoded)})
        for export in state["exports"]:
            artifact_ref = export.get("artifact_ref")
            if not artifact_ref:
                continue
            export_manifest = Path(artifact_ref).resolve()
            try:
                export_manifest.relative_to(root)
            except ValueError:
                continue
            if not export_manifest.is_file():
                continue
            for resolved in sorted(path for path in export_manifest.parent.iterdir() if path.is_file()):
                try:
                    resolved.relative_to(root)
                except ValueError:
                    continue
                if resolved.is_file() and resolved.stat().st_size <= 8_388_608:
                    target = f"target/{export['id']}/{resolved.name}"
                    archive.write(resolved, target)
                    manifest["files"].append({"path": target, "bytes": resolved.stat().st_size})
        archive.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True))
    return output.getvalue()
