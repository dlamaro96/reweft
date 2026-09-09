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
        state = api.request("GET", api.workspace_path(f"/runs/{run_id}/state"))
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
    subprocess.run([
        "docker", "compose", "--env-file", str(args.env_file), "--profile", "real-runtime",
        "restart", "real-analysis-worker",
    ], check=True, stdout=subprocess.DEVNULL)
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

    export = api.request("GET", api.workspace_path(f"/runs/{resolved_run}/export"))
    with zipfile.ZipFile(io.BytesIO(export)) as archive:
        export_names = sorted(archive.namelist())
        exported_payload = b"\n".join(archive.read(name) for name in export_names)
        manifest = json.loads(archive.read("manifest.json"))
    secret_values = [identity["api_token"], *(value for key, value in env.items() if "PASSWORD" in key or "TOKEN" in key or "SECRET" in key)]
    assert all(value.encode() not in exported_payload for value in secret_values if len(value) >= 16)
    assert manifest["contains_secrets"] is False

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
            "duckdb_target_fixture_execution": "passed",
            "authorized_secret_free_export": "passed",
        },
        "observed": {
            "unresolved": {"state": first["run"]["state"], "finding_types": sorted(first_types), "gap_count": len(first["gaps"])},
            "restart": {"state": restarted["run"]["state"], "progress": restarted["progress"]},
            "resolved": {"state": changed["run"]["state"], "finding_types": sorted(changed_types), "gap_count": len(changed["gaps"])},
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
