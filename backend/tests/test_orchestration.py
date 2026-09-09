from __future__ import annotations

import json
import asyncio
from pathlib import Path
from uuid import uuid4

from reweft.domain.models import EndpointClass, InferenceProfile, ProviderType
from reweft.inference.gateway import InferenceResult
from reweft.orchestration.activities import (
    TARGET_SQL, analyze_run, design_modernization, execute_generated_target, invoke_inference,
    validate_generated_target,
)
from reweft.orchestration.analysis import analyze_evidence
from reweft.orchestration.models import (
    AnalysisActivityInput, DesignActivityInput, InferenceActivityInput, ValidationActivityInput,
)
from reweft.persistence import Database


def test_evidence_drives_distinct_metrics_nonadditivity_and_retirement_blocker():
    artifacts = [
        {"evidence_id": "11111111-1111-1111-1111-111111111111", "content": {
            "objects": [
                {"metric": "recognized_revenue", "expression": "SUM(RECOGNIZED_AMOUNT)"},
                {"metric": "adjusted_revenue", "expression": "SUM(RECOGNIZED_AMOUNT) + PERIOD_ADJUSTMENT"},
            ],
        }},
        {"evidence_id": "22222222-2222-2222-2222-222222222222", "content": {
            "tables": [{"table_name": "inventory_positions"}, {"table_name": "year_end_dispatches"}],
            "columns": [{"column_name": "snapshot_date"}, {"column_name": "quantity_on_hand"}],
        }},
        {"evidence_id": "33333333-3333-3333-3333-333333333333", "content": {
            "name": "year_end_dispatch_file", "consumer_status": "external-boundary-unresolved",
        }},
    ]
    result = analyze_evidence(artifacts)
    assert {item["name"] for item in result["metrics"]} == {"recognized_revenue", "adjusted_revenue"}
    assert {item["finding_type"] for item in result["findings"]} == {
        "semantic-conflict", "non-additive-measure", "retirement-blocker",
    }
    assert all(item["knowledge_state"] == "deterministically-derived" for item in result["findings"])
    assert "year_end_dispatch_file" in " ".join(result["unresolved"])


def test_changed_evidence_changes_findings_instead_of_returning_a_fixed_story():
    minimal = [{"evidence_id": "11111111-1111-1111-1111-111111111111", "content": {"tables": [{"table_name": "work_orders"}]}}]
    result = analyze_evidence(minimal)
    assert result["findings"] == []
    assert "inventory" not in " ".join(result["assets"]).lower()


def test_confirmed_dispatch_replacement_removes_retirement_blocker():
    result = analyze_evidence([{
        "evidence_id": "11111111-1111-1111-1111-111111111111",
        "content": {
            "name": "year_end_dispatch_file",
            "consumer": "finance-archive-v2",
            "consumer_status": "replacement-confirmed",
        },
    }])
    assert result["findings"] == []
    assert result["unresolved"] == []


def test_generated_duckdb_target_executes_independent_business_transformation():
    result = execute_generated_target()
    assert result["status"] == "passed"
    assert result["observed"]["recognized_revenue"] == 2230.0
    assert result["observed"]["adjusted_revenue"] == 2175.0
    assert result["observed"]["current_inventory"] == 84.0
    assert result["observed"]["inventory_naive_sum"] == 180.0
    assert "CREATE VIEW adjusted_revenue" in TARGET_SQL


def test_analysis_design_and_validation_are_persisted_in_sqlite(monkeypatch, tmp_path: Path):
    database_path = tmp_path / "runtime.db"
    evidence_root = tmp_path / "evidence"
    monkeypatch.setenv("REWEFT_DATABASE_PATH", str(database_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("REWEFT_EVIDENCE_PATH", str(evidence_root))
    database = Database(database_path); database.initialize()
    workspace_id, project_id, run_id, evidence_id = (str(uuid4()) for _ in range(4))
    now = "2026-09-09T00:00:00+00:00"
    assessment = {
        "id": run_id, "workspace_id": workspace_id, "project_id": project_id,
        "objective": "Preserve business meaning", "scope": {}, "state": "analyzing",
        "policy_revision": 1, "configuration_revision": 1, "created_at": now,
        "updated_at": now, "version": 1, "gaps": [], "inference_profile_id": None,
    }
    content = {"objects": [
        {"metric": "recognized_revenue", "expression": "SUM(RECOGNIZED_AMOUNT)"},
        {"metric": "adjusted_revenue", "expression": "SUM(RECOGNIZED_AMOUNT) + PERIOD_ADJUSTMENT"},
    ], "tables": [{"table_name": "inventory_positions"}, {"table_name": "year_end_dispatches"}],
        "pipeline": {"name": "publish_revenue", "inputs": ["recognized_revenue"], "output": {"name": "published_revenue"}},
    }
    raw = json.dumps(content).encode(); sha = __import__("hashlib").sha256(raw).hexdigest()
    path = evidence_root / workspace_id / run_id / f"{sha}.json"; path.parent.mkdir(parents=True); path.write_bytes(raw)
    with database.transaction() as connection:
        connection.execute("INSERT INTO users(id,email,display_name,created_at) VALUES(?,?,?,?)", (str(uuid4()), "test@example.test", "Test", now))
        connection.execute("INSERT INTO workspaces(id,name,created_at) VALUES(?,?,?)", (workspace_id, "Test", now))
        connection.execute("INSERT INTO projects(id,workspace_id,name,created_at) VALUES(?,?,?,?)", (project_id, workspace_id, "Project", now))
        connection.execute("INSERT INTO assessments(id,workspace_id,project_id,state,version,body_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)", (run_id, workspace_id, project_id, "analyzing", 1, json.dumps(assessment), now, now))
        connection.execute("INSERT INTO evidence(id,workspace_id,project_id,run_id,artifact_sha256,body_json,created_at) VALUES(?,?,?,?,?,?,?)", (evidence_id, workspace_id, project_id, run_id, sha, "{}", now))
    analysis = analyze_run(AnalysisActivityInput(workspace_id, project_id, run_id, assessment["objective"], [evidence_id]))
    design = design_modernization(DesignActivityInput(workspace_id, project_id, run_id, assessment["objective"], analysis))
    second_run_id = str(uuid4())
    second_assessment = {**assessment, "id": second_run_id}
    with database.transaction() as connection:
        connection.execute(
            "INSERT INTO assessments(id,workspace_id,project_id,state,version,body_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
            (second_run_id, workspace_id, project_id, "analyzing", 1, json.dumps(second_assessment), now, now),
        )
    second_design = design_modernization(DesignActivityInput(workspace_id, project_id, second_run_id, assessment["objective"], analysis))
    validation = validate_generated_target(ValidationActivityInput(workspace_id, run_id, design["scenario_id"], design["spec_id"]))
    assert second_design["scenario_id"] != design["scenario_id"]
    assert validation["validation"]["status"] == "passed"
    with database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM findings WHERE run_id=?", (run_id,)).fetchone()[0] >= 2
        assert connection.execute("SELECT validation_status FROM modernization_specs WHERE id=?", (design["spec_id"],)).fetchone()[0] == "fixture-executed"
        assert connection.execute("SELECT state FROM exports WHERE run_id=?", (run_id,)).fetchone()[0] == "ready"
        assert connection.execute("SELECT COUNT(*) FROM lineage_edges WHERE workspace_id=?", (workspace_id,)).fetchone()[0] == 1
        assert [row[0] for row in connection.execute(
            "SELECT version FROM scenarios WHERE workspace_id=? AND project_id=? ORDER BY version",
            (workspace_id, project_id),
        )] == [1, 2]
        validation_evidence = json.loads(connection.execute("SELECT evidence_json FROM validation_results WHERE run_id=?", (run_id,)).fetchone()[0])
        assert validation_evidence["artifacts"][0]["path"].endswith("/export/target.sql")


def test_provider_probe_persists_observed_capabilities(monkeypatch, tmp_path: Path):
    database_path = tmp_path / "provider.db"
    monkeypatch.setenv("REWEFT_DATABASE_PATH", str(database_path)); monkeypatch.delenv("DATABASE_URL", raising=False)
    database = Database(database_path); database.initialize()
    workspace_id, profile_id = str(uuid4()), str(uuid4())
    now = "2026-09-09T00:00:00+00:00"
    profile = InferenceProfile(
        id=profile_id, workspace_id=workspace_id, name="Local fixture", provider=ProviderType.OPENAI_COMPATIBLE,
        endpoint_class=EndpointClass.LOCAL, model="fixture", base_url="http://provider.test/v1",
    )
    with database.transaction() as connection:
        connection.execute("INSERT INTO workspaces(id,name,created_at) VALUES(?,?,?)", (workspace_id, "Test", now))
        connection.execute("INSERT INTO inference_profiles(id,workspace_id,name,revision,body_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?)", (profile_id, workspace_id, profile.name, 1, profile.model_dump_json(), now, now))

    async def probe(_self, _profile):
        return InferenceResult({"protocol": "reweft-provider-probe", "structured": True}, "fixture-1", "completed", 2, 1, 1, 2, "a" * 64)

    monkeypatch.setattr("reweft.orchestration.activities.InferenceGateway.probe", probe)
    result = asyncio.run(invoke_inference(InferenceActivityInput(workspace_id, None, profile_id, {}, "provider-test")))
    assert result["capabilities"]["test_status"] == "passed"
    with database.connect() as connection:
        stored = InferenceProfile.model_validate_json(connection.execute("SELECT body_json FROM inference_profiles WHERE id=?", (profile_id,)).fetchone()[0])
    assert stored.capabilities.structured_output is True
    assert stored.capabilities.native_responses is True
    assert stored.capabilities.observed_at is not None
    assert stored.last_successful_test is not None
