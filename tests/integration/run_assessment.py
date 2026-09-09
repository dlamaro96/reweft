#!/usr/bin/env python3
"""Exercise the complete durable runtime without printing credential material."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import stat
import subprocess
import time
import urllib.error
import urllib.request
import uuid
import zipfile
from pathlib import Path
from typing import Any


TERMINAL_STATES = {"completed", "completed-with-gaps", "failed", "cancelled"}


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line and not line.lstrip().startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


class API:
    def __init__(self, base_url: str, workspace_id: str, token: str):
        self.base_url = base_url.rstrip("/") + "/api/v1"
        self.workspace_id = workspace_id
        self.headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def request(self, method: str, path: str, body: dict[str, Any] | None = None, timeout: int = 180) -> Any:
        request = urllib.request.Request(
            self.base_url + path,
            data=None if body is None else json.dumps(body).encode(),
            method=method,
            headers=self.headers,
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                data = response.read()
                return json.loads(data) if response.headers.get_content_type() == "application/json" else data
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:500]
            raise RuntimeError(f"{method} {path} returned HTTP {exc.code}: {detail}") from exc

    def post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        return self.request("POST", path, body or {})

    def workspace_path(self, suffix: str) -> str:
        return f"/workspaces/{self.workspace_id}{suffix}"


def ensure_identity(base_url: str, env: dict[str, str], identity_path: Path) -> dict[str, str]:
    if identity_path.is_file():
        identity = json.loads(identity_path.read_text(encoding="utf-8"))
        if {"workspace_id", "api_token"} <= identity.keys():
            return identity
    body = json.dumps({
        "token": env["REWEFT_BOOTSTRAP_TOKEN"],
        "email": "integration-owner@reweft.invalid",
        "display_name": "Integration Owner",
        "workspace_name": "Durable Runtime Integration",
    }).encode()
    request = urllib.request.Request(
        base_url.rstrip("/") + "/api/v1/auth/bootstrap",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        identity = json.load(response)
    identity_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(identity_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(identity, handle, indent=2)
        handle.write("\n")
    return identity


def create_run(api: API, project_id: str, source_ids: list[str], profile_id: str, objective: str) -> str:
    run = api.post(api.workspace_path("/assessments"), {
        "project_id": project_id,
        "objective": objective,
        "scope": {"source_ids": source_ids},
        "inference_profile_id": profile_id,
    })
    api.post(api.workspace_path(f"/assessments/{run['id']}/transitions"), {
        "action": "start",
        "expected_version": run["version"],
    })
    return run["id"]


def wait_for_run(api: API, run_id: str, timeout_seconds: int = 180) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            state = api.request("GET", api.workspace_path(f"/runs/{run_id}/state"))
        except (RuntimeError, urllib.error.URLError):
            time.sleep(1)
            continue
        if state["run"]["state"] in TERMINAL_STATES:
            return state
        time.sleep(1)
    raise TimeoutError(f"assessment {run_id} did not reach a terminal state")


def assert_no_duplicates(state: dict[str, Any]) -> None:
    for values in (
        [item["task_key"] for item in state["tasks"]],
        [(item["source_id"], item["operation"]) for item in state["source_operations"]],
        [item["stable_key"] for item in state["findings"]],
    ):
        assert len(values) == len(set(values)), values


def compose(env_file: Path, *arguments: str, quiet: bool = False) -> None:
    subprocess.run(
        ["docker", "compose", "--env-file", str(env_file), "--profile", "real-runtime", *arguments],
        check=True,
        stdout=subprocess.DEVNULL if quiet else None,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8180")
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--identity-file", type=Path, default=Path(".data/real-runtime-identity.json"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    env = read_env(args.env_file)
    identity = ensure_identity(args.base_url, env, args.identity_file)
    assert stat.S_IMODE(args.identity_file.stat().st_mode) == 0o600
    api = API(args.base_url, identity["workspace_id"], identity["api_token"])
    suffix = f"{int(time.time())}-{os.getpid()}"

    project = api.post(api.workspace_path("/projects"), {"name": f"Atlas integration {suffix}"})
    pg = api.post(api.workspace_path("/sources/postgresql"), {
        "name": f"Atlas source {suffix}",
        "host": "synthetic-source-postgres",
        "port": 5432,
        "database": env.get("REWEFT_SOURCE_DB_NAME", "loom_source"),
        "username": env.get("REWEFT_SOURCE_READER_USER", "reweft_reader"),
        "credential_ref": "secret://source/runtime-default",
        "sslmode": "disable",
        "scope": {"schemas": [env.get("REWEFT_SOURCE_SCHEMA", "ops_atlas")]},
    })
    unresolved = api.post(api.workspace_path("/sources/artifact-bundle"), {
        "name": f"Atlas unresolved artifacts {suffix}", "bundle_id": "estate",
    })
    resolved = api.post(api.workspace_path("/sources/artifact-bundle"), {
        "name": f"Atlas resolved artifacts {suffix}", "bundle_id": "estate-resolved",
    })
    profile = api.post(api.workspace_path("/inference-profiles"), {
        "name": f"Labeled deterministic provider {suffix}",
        "provider": "openai_compatible",
        "endpoint_class": "local",
        "model": "reweft-deterministic-test-v1",
        "base_url": "http://deterministic-test-provider:8090/v1",
        "tls_verify": True,
        "required_capabilities": ["structured_output"],
        "allowed_data_classes": ["metadata"],
    })
    profile = api.post(api.workspace_path(f"/inference-profiles/{profile['id']}/test"))
    pg = api.post(api.workspace_path(f"/sources/{pg['id']}/test"))
    assert profile["capabilities"]["test_status"] == "passed"
    assert pg["status"] == "ready"

    unresolved_run = create_run(
        api, project["id"], [pg["id"], unresolved["id"]], profile["id"],
        "Preserve Atlas revenue and inventory semantics and identify retirement blockers.",
    )
    first = wait_for_run(api, unresolved_run)
    first_types = {item["finding_type"] for item in first["findings"]}
    assert first["run"]["state"] == "completed-with-gaps"
    assert {"semantic-conflict", "non-additive-measure", "retirement-blocker"} <= first_types
    assert_no_duplicates(first)

    restart_run = create_run(
        api, project["id"], [pg["id"], unresolved["id"]], profile["id"],
        "Prove durable recovery while repeating the bounded Atlas assessment.",
    )
    compose(args.env_file, "restart", "real-analysis-worker", quiet=True)
    restarted = wait_for_run(api, restart_run)
    assert restarted["run"]["state"] == "completed-with-gaps"
    assert restarted["progress"] == 100
    assert_no_duplicates(restarted)

    resolved_run = create_run(
        api, project["id"], [pg["id"], resolved["id"]], profile["id"],
        "Reassess Atlas after settlement logic and the outbound replacement are supplied.",
    )
    changed = wait_for_run(api, resolved_run)
    changed_types = {item["finding_type"] for item in changed["findings"]}
    assert changed["run"]["state"] == "completed"
    assert changed["gaps"] == []
    assert "retirement-blocker" not in changed_types
    definition = next(item["definition"] for item in changed["modernization"]["metrics"] if item["name"] == "adjusted_revenue")
    assert "COALESCE" in definition
    assert_no_duplicates(changed)

    # A collector outage leaves the workflow queued in Temporal. Starting the
    # same worker role resumes bounded work without a new assessment or source.
    compose(args.env_file, "stop", "real-collector", quiet=True)
    collector_run = create_run(
        api, project["id"], [pg["id"], resolved["id"]], profile["id"],
        "Prove pause, resume, and collector queue recovery without widening source scope.",
    )
    time.sleep(1)
    queued = api.request("GET", api.workspace_path(f"/runs/{collector_run}/state"))
    assert queued["run"]["state"] == "collecting"
    paused = api.post(api.workspace_path(f"/assessments/{collector_run}/transitions"), {
        "action": "pause", "expected_version": queued["run"]["version"],
    })
    assert paused["state"] == "paused-by-user"
    resumed = api.post(api.workspace_path(f"/assessments/{collector_run}/transitions"), {
        "action": "resume", "expected_version": paused["version"],
    })
    assert resumed["state"] == "collecting"

    cancelled_run = create_run(
        api, project["id"], [pg["id"], resolved["id"]], profile["id"],
        "Prove cancellation while source work is unavailable.",
    )
    time.sleep(1)
    cancelling = api.request("GET", api.workspace_path(f"/runs/{cancelled_run}/state"))["run"]
    paused_for_cancel = api.post(api.workspace_path(f"/assessments/{cancelled_run}/transitions"), {
        "action": "pause", "expected_version": cancelling["version"],
    })
    cancelled = api.post(api.workspace_path(f"/assessments/{cancelled_run}/transitions"), {
        "action": "cancel", "expected_version": paused_for_cancel["version"],
    })
    assert cancelled["state"] == "cancelled"
    compose(args.env_file, "start", "real-collector", quiet=True)
    collector_recovered = wait_for_run(api, collector_run)
    assert collector_recovered["run"]["state"] == "completed"
    assert_no_duplicates(collector_recovered)
    cancellation_state = wait_for_run(api, cancelled_run)
    assert cancellation_state["run"]["state"] == "cancelled"
    assert not any(item["state"] in {"reserved", "executing", "cancel-requested", "outcome-unknown"} for item in cancellation_state["source_operations"])

    # API process loss does not own workflow execution. A stable Temporal ID and
    # persisted state allow the request plane to restart while work continues.
    api_restart_run = create_run(
        api, project["id"], [pg["id"], resolved["id"]], profile["id"],
        "Prove API restart recovery while Temporal owns execution.",
    )
    compose(args.env_file, "restart", "real-api", quiet=True)
    time.sleep(2)
    api_recovered = wait_for_run(api, api_restart_run)
    assert api_recovered["run"]["state"] == "completed"
    assert_no_duplicates(api_recovered)

    # A separate profile/model identifier is operational immediately; no image
    # rebuild or worker configuration change is involved.
    alternate = api.post(api.workspace_path("/inference-profiles"), {
        "name": f"Alternate deterministic model {suffix}",
        "provider": "openai_compatible",
        "endpoint_class": "local",
        "model": "reweft-deterministic-test-v2",
        "base_url": "http://deterministic-test-provider:8090/v1",
        "tls_verify": True,
        "required_capabilities": ["structured_output"],
        "allowed_data_classes": ["metadata"],
    })
    alternate = api.post(api.workspace_path(f"/inference-profiles/{alternate['id']}/test"))
    assert alternate["capabilities"]["test_status"] == "passed"
    alternate_run = create_run(
        api, project["id"], [pg["id"], resolved["id"]], alternate["id"],
        "Prove runtime model changes do not require rebuilding Reweft.",
    )
    alternate_state = wait_for_run(api, alternate_run)
    assert alternate_state["run"]["state"] == "completed"
    assert {item["model"] for item in alternate_state["model_invocations"]} == {"reweft-deterministic-test-v2"}

    # A deliberately instruction-shaped report remains inert imported evidence.
    adversarial = api.post(api.workspace_path("/sources/artifact-bundle"), {
        "name": f"Atlas adversarial artifacts {suffix}", "bundle_id": "estate-injection",
    })
    injection_run = create_run(
        api, project["id"], [adversarial["id"]], profile["id"],
        "Assess the adversarial artifact without changing tools, scope, or endpoint policy.",
    )
    injection_state = wait_for_run(api, injection_run)
    assert injection_state["run"]["state"] == "completed"
    assert [(item["operation"], item["state"]) for item in injection_state["source_operations"]] == [
        ("import_bundle", "confirmed-finished")
    ]
    assert all("169.254.169.254" not in json.dumps(item) for item in injection_state["model_invocations"])

    # A deliberately tiny inventory limit reports partial evidence and never
    # turns that partial scan into a deletion or unused-asset finding.
    partial_source = api.post(api.workspace_path("/sources/postgresql"), {
        "name": f"Atlas partial source {suffix}",
        "host": "synthetic-source-postgres",
        "port": 5432,
        "database": env.get("REWEFT_SOURCE_DB_NAME", "loom_source"),
        "username": env.get("REWEFT_SOURCE_READER_USER", "reweft_reader"),
        "credential_ref": "secret://source/runtime-default",
        "sslmode": "disable",
        "scope": {"schemas": [env.get("REWEFT_SOURCE_SCHEMA", "ops_atlas")]},
        "max_objects": 1,
    })
    partial_run = create_run(
        api, project["id"], [partial_source["id"]], profile["id"],
        "Prove partial metadata scope remains explicitly incomplete.",
    )
    partial_state = wait_for_run(api, partial_run)
    assert any(item["collection_status"] == "partial" for item in partial_state["evidence"])
    assert not any("delet" in json.dumps(item).lower() or "unused" in json.dumps(item).lower() for item in partial_state["findings"])

    # A random workspace ID remains opaque to the authenticated token.
    try:
        api.request("GET", f"/workspaces/{uuid.uuid4()}/projects")
    except RuntimeError as exc:
        assert "HTTP 401" in str(exc)
    else:
        raise AssertionError("cross-workspace project access unexpectedly succeeded")

    # Provider transport loss is bounded and recorded as a gap. Deterministic
    # target generation remains independently testable without fabricating AI.
    compose(args.env_file, "stop", "deterministic-test-provider", quiet=True)
    try:
        outage_run = create_run(
            api, project["id"], [pg["id"], resolved["id"]], profile["id"],
            "Prove bounded and honest behavior during provider transport loss.",
        )
        outage_state = wait_for_run(api, outage_run)
        assert outage_state["run"]["state"] == "completed-with-gaps"
        assert any("Inference summary unavailable" in gap for gap in outage_state["gaps"])
        assert 1 <= len(outage_state["model_invocations"]) <= 2
        assert all(item["state"] == "failed" for item in outage_state["model_invocations"])
        assert [item["status"] for item in outage_state["validation"]] == ["fixture-executed"]
    finally:
        compose(args.env_file, "start", "deterministic-test-provider", quiet=True)

    # If the authoritative database/controller boundary is unavailable, a
    # planned run cannot transition into source work. After recovery the draft
    # remains planned and has no source operation journal entries.
    database_loss_draft = api.post(api.workspace_path("/assessments"), {
        "project_id": project["id"],
        "objective": "Prove controller/database loss fails closed before source admission.",
        "scope": {"source_ids": [pg["id"], resolved["id"]]},
        "inference_profile_id": profile["id"],
    })
    database_failure_bounded = False
    database_failure_started = time.monotonic()
    compose(args.env_file, "stop", "real-postgres", quiet=True)
    try:
        api.request(
            "POST",
            api.workspace_path(f"/assessments/{database_loss_draft['id']}/transitions"),
            {"action": "start", "expected_version": database_loss_draft["version"]},
            timeout=15,
        )
    except (RuntimeError, urllib.error.URLError, TimeoutError):
        database_failure_bounded = True
    finally:
        compose(args.env_file, "start", "real-postgres", quiet=True)
        time.sleep(3)
        compose(
            args.env_file,
            "restart",
            "real-temporal",
            "real-api",
            "real-analysis-worker",
            "real-inference-worker",
            "real-collector",
            quiet=True,
        )
    assert database_failure_bounded
    assert time.monotonic() - database_failure_started < 30
    database_recovery_deadline = time.monotonic() + 90
    while True:
        try:
            database_loss_state = api.request(
                "GET", api.workspace_path(f"/runs/{database_loss_draft['id']}/state"), timeout=5
            )
            break
        except (RuntimeError, urllib.error.URLError):
            if time.monotonic() >= database_recovery_deadline:
                raise
            time.sleep(1)
    assert database_loss_state["run"]["state"] == database_loss_draft["state"]
    assert database_loss_state["run"]["version"] == database_loss_draft["version"]
    assert database_loss_state["source_operations"] == []

    export = api.request("GET", api.workspace_path(f"/runs/{resolved_run}/export"))
    with zipfile.ZipFile(io.BytesIO(export)) as archive:
        export_names = sorted(archive.namelist())
        exported_payload = b"\n".join(archive.read(name) for name in export_names)
        manifest = json.loads(archive.read("manifest.json"))
    secret_values = [identity["api_token"], *(value for key, value in env.items() if "PASSWORD" in key or "TOKEN" in key or "SECRET" in key)]
    assert all(value.encode() not in exported_payload for value in secret_values if len(value) >= 16)
    assert manifest["contains_secrets"] is False

    # Scan all service logs and the complete runtime evidence volume for the
    # generated credentials without ever printing credential material.
    runtime_logs = subprocess.run(
        [
            "docker", "compose", "--env-file", str(args.env_file), "--profile", "real-runtime",
            "logs", "--no-color",
        ],
        check=True,
        capture_output=True,
    )
    evidence_archive = subprocess.run(
        [
            "docker", "run", "--rm", "--volume", "reweft_real_evidence:/data:ro",
            "alpine:3.22.1", "tar", "-C", "/data", "-cf", "-", ".",
        ],
        check=True,
        capture_output=True,
    ).stdout
    runtime_material = runtime_logs.stdout + runtime_logs.stderr + evidence_archive
    assert all(value.encode() not in runtime_material for value in secret_values if len(value) >= 16)

    record = {
        "schema_version": "reweft.assessment-integration-evidence/v1",
        "executed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "checks": {
            "authenticated_workspace_and_configuration": "passed",
            "postgresql_connection_test": "passed",
            "deterministic_provider_capability_test": "passed",
            "unresolved_evidence_changes_run_to_completed_with_gaps": "passed",
            "worker_restart_recovery_without_duplicates": "passed",
            "changed_artifact_logic_changes_findings_and_spec": "passed",
            "collector_queue_outage_and_recovery": "passed",
            "pause_resume_and_cancel_controls": "passed",
            "api_restart_during_execution": "passed",
            "runtime_model_change_without_rebuild": "passed",
            "prompt_injection_remains_inert": "passed",
            "partial_scan_remains_partial": "passed",
            "cross_workspace_access_denied": "passed",
            "provider_outage_degrades_honestly": "passed",
            "controller_database_loss_fails_closed": "passed",
            "duckdb_target_fixture_execution": "passed",
            "authorized_secret_free_export": "passed",
            "runtime_logs_and_evidence_secret_scan": "passed",
        },
        "observed": {
            "unresolved": {"state": first["run"]["state"], "finding_types": sorted(first_types), "gap_count": len(first["gaps"])},
            "restart": {"state": restarted["run"]["state"], "progress": restarted["progress"]},
            "resolved": {"state": changed["run"]["state"], "finding_types": sorted(changed_types), "gap_count": len(changed["gaps"])},
            "collector_recovery": {"state": collector_recovered["run"]["state"], "progress": collector_recovered["progress"]},
            "lifecycle_controls": {"resumed_state": collector_recovered["run"]["state"], "cancelled_state": cancellation_state["run"]["state"]},
            "api_recovery": {"state": api_recovered["run"]["state"], "progress": api_recovered["progress"]},
            "alternate_model": {"state": alternate_state["run"]["state"], "model": "reweft-deterministic-test-v2"},
            "prompt_injection": {"state": injection_state["run"]["state"], "source_operations": 1},
            "partial_scan": {"state": partial_state["run"]["state"], "partial_evidence": True},
            "provider_outage": {"state": outage_state["run"]["state"], "failed_invocations": len(outage_state["model_invocations"])},
            "database_loss": {
                "state_after_recovery": database_loss_state["run"]["state"],
                "version_after_recovery": database_loss_state["run"]["version"],
                "source_operations": 0,
            },
            "export": {"sha256": hashlib.sha256(export).hexdigest(), "files": export_names},
        },
        "limitations": [
            "The source and artifact estate are synthetic local fixtures.",
            "The labeled deterministic provider verifies transport and strict structured-output handling; it is not real model inference.",
            "DuckDB validation is fixture-executed, not target-environment validation.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Durable assessment integration passed; sanitized evidence: {args.output}")


if __name__ == "__main__":
    main()
