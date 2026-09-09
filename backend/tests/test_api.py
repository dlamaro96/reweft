from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient


def bootstrap(client: TestClient):
    response = client.post(
        "/api/v1/auth/bootstrap",
        json={
            "token": "bootstrap-token-that-is-long-enough-for-tests",
            "email": "owner@example.test",
            "display_name": "Test Owner",
            "workspace_name": "Test Workspace",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_demo_snapshot_is_explicit_and_matches_frontend_contract(app):
    client = TestClient(app)
    response = client.get("/api/v1/demo/snapshot")
    assert response.status_code == 200
    body = response.json()
    assert {"overview", "connections", "runs", "findings", "lineage", "modernization"} <= body.keys()
    assert body["mode"] == "synthetic-demo"
    assert body["workspace"]["name"] == "Synthetic Manufacturing"
    assert isinstance(body["inventory"], list)
    assert body["overview"]["label"].startswith("Synthetic demo")
    assert all(item["synthetic"] for item in body["connections"] + body["findings"])
    assert client.get("/health").json()["persistence"] == "sqlite-development"


def test_bootstrap_is_single_use_and_workspace_scoped(app):
    client = TestClient(app)
    identity = bootstrap(client)
    second = client.post(
        "/api/v1/auth/bootstrap",
        json={
            "token": "bootstrap-token-that-is-long-enough-for-tests",
            "email": "other@example.test",
            "display_name": "Other",
            "workspace_name": "Other",
        },
    )
    assert second.status_code == 401
    headers = {"Authorization": f"Bearer {identity['api_token']}"}
    project = client.post(
        f"/api/v1/workspaces/{identity['workspace_id']}/projects",
        headers=headers,
        json={"name": "Estate"},
    )
    assert project.status_code == 201

    foreign_workspace = uuid4()
    with app.state.database.transaction(immediate=True) as connection:
        connection.execute(
            "INSERT INTO workspaces(id,name,created_at) VALUES(?,?,?)",
            (str(foreign_workspace), "Foreign", datetime.now(timezone.utc).isoformat()),
        )
    # Existence is not disclosed to a token lacking membership.
    denied = client.get(f"/api/v1/workspaces/{foreign_workspace}/projects", headers=headers)
    assert denied.status_code == 401


def test_evidence_and_lineage_references_cannot_cross_workspace(app):
    client = TestClient(app)
    identity = bootstrap(client)
    workspace_id = identity["workspace_id"]
    headers = {"Authorization": f"Bearer {identity['api_token']}"}
    project = client.post(f"/api/v1/workspaces/{workspace_id}/projects", headers=headers, json={"name": "Estate"}).json()
    run = client.post(
        f"/api/v1/workspaces/{workspace_id}/assessments",
        headers=headers,
        json={"project_id": project["id"], "objective": "Map the estate"},
    ).json()
    now = datetime.now(timezone.utc).isoformat()
    evidence = client.post(
        f"/api/v1/workspaces/{workspace_id}/evidence",
        headers=headers,
        json={
            "project_id": project["id"], "run_id": run["id"], "platform": "postgresql",
            "environment": "test", "native_object_id": "public.orders",
            "artifact_sha256": "a" * 64, "artifact_size": 10, "media_type": "application/sql",
            "original_location": "fixture/orders.sql", "parser_version": "1", "collector_version": "1",
            "collection_status": "complete", "collected_from": now, "collected_to": now,
            "locator": {"kind": "line-range", "value": "1-2", "external_label": "orders.sql lines 1-2"},
        },
    )
    assert evidence.status_code == 201, evidence.text
    finding = client.post(
        f"/api/v1/workspaces/{workspace_id}/findings",
        headers=headers,
        json={
            "run_id": run["id"], "stable_key": "orders-key", "finding_type": "lineage-gap",
            "title": "Missing downstream", "interpretation": "A consumer is unresolved", "impact": "Retirement risk",
            "recommendation": "Collect consumer metadata", "severity_basis": "External boundary",
            "knowledge_state": "unresolved", "evidence_ids": [evidence.json()["id"]],
        },
    )
    assert finding.status_code == 201, finding.text
    assert len(client.get(f"/api/v1/workspaces/{workspace_id}/evidence", headers=headers).json()) == 1


def test_assessment_lifecycle_uses_optimistic_concurrency(app):
    client = TestClient(app)
    identity = bootstrap(client)
    workspace_id = identity["workspace_id"]
    headers = {"Authorization": f"Bearer {identity['api_token']}"}
    project = client.post(f"/api/v1/workspaces/{workspace_id}/projects", headers=headers, json={"name": "Estate"}).json()
    run = client.post(f"/api/v1/workspaces/{workspace_id}/assessments", headers=headers, json={"project_id": project["id"], "objective": "Assess retirement"}).json()
    started = client.post(f"/api/v1/workspaces/{workspace_id}/assessments/{run['id']}/transition", headers=headers, json={"action": "start", "expected_version": 1})
    assert started.status_code == 200
    assert started.json()["state"] == "collecting"
    conflict = client.post(f"/api/v1/workspaces/{workspace_id}/assessments/{run['id']}/transition", headers=headers, json={"action": "pause", "expected_version": 1})
    assert conflict.status_code == 409


def test_live_contract_persists_sources_and_plural_transition(app):
    client = TestClient(app)
    identity = bootstrap(client)
    workspace_id = identity["workspace_id"]
    headers = {"Authorization": f"Bearer {identity['api_token']}"}
    runtime = client.get("/api/v1/runtime").json()
    assert runtime["bootstrapped"] is True
    assert runtime["persistence"] == "sqlite-development"

    source = client.post(
        f"/api/v1/workspaces/{workspace_id}/sources/postgresql",
        headers=headers,
        json={
            "name": "Non-default source",
            "host": "source.internal",
            "port": 5437,
            "database": "atlas_source",
            "username": "readonly",
            "credential_ref": "secret://source/atlas",
            "sslmode": "verify-full",
            "scope": {"schemas": ["ops_atlas"]},
        },
    )
    assert source.status_code == 201, source.text
    listed = client.get(f"/api/v1/workspaces/{workspace_id}/sources", headers=headers)
    assert [item["name"] for item in listed.json()] == ["Non-default source"]
    assert listed.json()[0]["test_status"] == "not-tested"

    project = client.post(f"/api/v1/workspaces/{workspace_id}/projects", headers=headers, json={"name": "Estate"}).json()
    run = client.post(
        f"/api/v1/workspaces/{workspace_id}/assessments",
        headers=headers,
        json={"project_id": project["id"], "objective": "Assess Atlas", "scope": {"source_ids": [source.json()["id"]]}},
    ).json()
    started = client.post(
        f"/api/v1/workspaces/{workspace_id}/assessments/{run['id']}/transitions",
        headers=headers,
        json={"action": "start", "expected_version": 1},
    )
    assert started.status_code == 200
    now = datetime.now(timezone.utc).isoformat()
    with app.state.database.transaction(immediate=True) as connection:
        connection.execute(
            "INSERT INTO run_tasks(id,workspace_id,run_id,task_key,state,owner_role,attempt,body_json,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (str(uuid4()), workspace_id, run["id"], "collect:fixture", "completed", "system", 1, json.dumps({"message": "Collected"}), now, now),
        )
    state = client.get(f"/api/v1/workspaces/{workspace_id}/runs/{run['id']}/state", headers=headers)
    assert state.status_code == 200
    assert state.json()["run"]["state"] == "collecting"
    assert state.json()["tasks"][0]["task_key"] == "collect:fixture"
    assert state.json()["tasks"][0]["state"] == "completed"
    assert state.json()["progress"] == 100


def test_run_state_and_export_do_not_cross_workspace(app):
    client = TestClient(app)
    identity = bootstrap(client)
    headers = {"Authorization": f"Bearer {identity['api_token']}"}
    foreign = uuid4()
    assert client.get(f"/api/v1/workspaces/{foreign}/runs/{uuid4()}/state", headers=headers).status_code == 401
    assert client.get(f"/api/v1/workspaces/{foreign}/runs/{uuid4()}/export", headers=headers).status_code == 401
