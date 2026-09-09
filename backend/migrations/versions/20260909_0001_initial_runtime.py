"""Initial durable Reweft runtime schema.

Revision ID: 20260909_0001
Revises: None
Create Date: 2026-09-09
"""

from alembic import context, op
import sqlalchemy as sa


revision = "20260909_0001"
down_revision = None
branch_labels = None
depends_on = None

ID = sa.String(64)
TIME = sa.String(64)
JSON_TEXT = sa.Text()
SEQUENCE = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def _create_table(name: str, *elements, **kwargs) -> None:
    # The pre-Alembic development build created a subset of these tables. This
    # conditional path upgrades that data in place while fresh installs still use
    # normal versioned DDL.
    if context.is_offline_mode() or name not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table(name, *elements, **kwargs)


def _create_index(name: str, table_name: str, columns: list[str]) -> None:
    if context.is_offline_mode():
        op.create_index(name, table_name, columns)
        return
    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}
    if name not in indexes:
        op.create_index(name, table_name, columns)


def upgrade() -> None:
    _create_table(
        "users",
        sa.Column("id", ID, primary_key=True),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("created_at", TIME, nullable=False),
    )
    _create_table(
        "bootstrap_tokens",
        sa.Column("token_hash", sa.String(128), primary_key=True),
        sa.Column("expires_at", TIME, nullable=False),
        sa.Column("consumed_at", TIME),
    )
    _create_table(
        "workspaces",
        sa.Column("id", ID, primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("created_at", TIME, nullable=False),
    )
    _create_table(
        "api_tokens",
        sa.Column("id", ID, primary_key=True),
        sa.Column("user_id", ID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_hash", sa.String(128), nullable=False, unique=True),
        sa.Column("scopes_json", JSON_TEXT, nullable=False),
        sa.Column("expires_at", TIME),
        sa.Column("revoked_at", TIME),
        sa.Column("created_at", TIME, nullable=False),
    )
    _create_table(
        "memberships",
        sa.Column("workspace_id", ID, sa.ForeignKey("workspaces.id"), primary_key=True),
        sa.Column("user_id", ID, sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("role", sa.String(64), nullable=False),
    )
    _create_table(
        "projects",
        sa.Column("id", ID, primary_key=True),
        sa.Column("workspace_id", ID, sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("created_at", TIME, nullable=False),
        sa.UniqueConstraint("workspace_id", "name", name="uq_projects_workspace_name"),
    )
    _create_table(
        "config_versions",
        sa.Column("id", ID, primary_key=True),
        sa.Column("workspace_id", ID, sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("configuration_type", sa.String(80), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("body_json", JSON_TEXT, nullable=False),
        sa.Column("content_hash", sa.String(128), nullable=False),
        sa.Column("created_by", ID, sa.ForeignKey("users.id")),
        sa.Column("created_at", TIME, nullable=False),
        sa.UniqueConstraint("workspace_id", "configuration_type", "revision", name="uq_config_versions_revision"),
    )
    _create_table(
        "inference_profiles",
        sa.Column("id", ID, primary_key=True),
        sa.Column("workspace_id", ID, sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("body_json", JSON_TEXT, nullable=False),
        sa.Column("created_at", TIME, nullable=False),
        sa.Column("updated_at", TIME, nullable=False),
        sa.UniqueConstraint("workspace_id", "name", name="uq_inference_profiles_workspace_name"),
    )
    _create_table(
        "sources",
        sa.Column("id", ID, primary_key=True),
        sa.Column("workspace_id", ID, sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("connector_id", sa.String(200), nullable=False),
        sa.Column("config_json", JSON_TEXT, nullable=False),
        sa.Column("secret_ref", sa.String(500)),
        sa.Column("status", sa.String(80), nullable=False),
        sa.Column("last_tested_at", TIME),
        sa.Column("created_at", TIME, nullable=False),
        sa.Column("updated_at", TIME, nullable=False),
        sa.UniqueConstraint("workspace_id", "name", name="uq_sources_workspace_name"),
    )
    _create_table(
        "assessments",
        sa.Column("id", ID, primary_key=True),
        sa.Column("workspace_id", ID, sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("project_id", ID, sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("state", sa.String(80), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("body_json", JSON_TEXT, nullable=False),
        sa.Column("created_at", TIME, nullable=False),
        sa.Column("updated_at", TIME, nullable=False),
    )
    _create_index("ix_assessments_workspace", "assessments", ["workspace_id", "created_at"])
    _create_table(
        "run_tasks",
        sa.Column("id", ID, primary_key=True),
        sa.Column("workspace_id", ID, sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("run_id", ID, sa.ForeignKey("assessments.id"), nullable=False),
        sa.Column("task_key", sa.String(300), nullable=False),
        sa.Column("state", sa.String(80), nullable=False),
        sa.Column("owner_role", sa.String(80)),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("body_json", JSON_TEXT, nullable=False),
        sa.Column("created_at", TIME, nullable=False),
        sa.Column("updated_at", TIME, nullable=False),
        sa.UniqueConstraint("workspace_id", "run_id", "task_key", name="uq_run_tasks_key"),
    )
    _create_table(
        "run_events",
        sa.Column("sequence", SEQUENCE, primary_key=True, autoincrement=True),
        sa.Column("workspace_id", ID, sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("run_id", ID, sa.ForeignKey("assessments.id"), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("body_json", JSON_TEXT, nullable=False),
        sa.Column("created_at", TIME, nullable=False),
    )
    _create_index("ix_run_events_replay", "run_events", ["workspace_id", "run_id", "sequence"])
    _create_table(
        "model_invocations",
        sa.Column("id", ID, primary_key=True),
        sa.Column("workspace_id", ID, sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("run_id", ID, sa.ForeignKey("assessments.id"), nullable=False),
        sa.Column("task_id", ID),
        sa.Column("profile_id", ID, sa.ForeignKey("inference_profiles.id")),
        sa.Column("profile_revision", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(100), nullable=False),
        sa.Column("model", sa.String(300), nullable=False),
        sa.Column("state", sa.String(80), nullable=False),
        sa.Column("reserved_json", JSON_TEXT, nullable=False),
        sa.Column("actual_usage_json", JSON_TEXT),
        sa.Column("created_at", TIME, nullable=False),
        sa.Column("updated_at", TIME, nullable=False),
    )
    _create_table(
        "evidence",
        sa.Column("id", ID, primary_key=True),
        sa.Column("workspace_id", ID, sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("project_id", ID, sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("run_id", ID),
        sa.Column("artifact_sha256", sa.String(128), nullable=False),
        sa.Column("body_json", JSON_TEXT, nullable=False),
        sa.Column("created_at", TIME, nullable=False),
        sa.UniqueConstraint("workspace_id", "project_id", "artifact_sha256", name="uq_evidence_content"),
    )
    _create_index("ix_evidence_workspace_run", "evidence", ["workspace_id", "run_id"])
    _create_table(
        "findings",
        sa.Column("id", ID, primary_key=True),
        sa.Column("workspace_id", ID, sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("run_id", ID, sa.ForeignKey("assessments.id"), nullable=False),
        sa.Column("stable_key", sa.String(300), nullable=False),
        sa.Column("body_json", JSON_TEXT, nullable=False),
        sa.Column("created_at", TIME, nullable=False),
        sa.UniqueConstraint("workspace_id", "run_id", "stable_key", name="uq_findings_stable_key"),
    )
    _create_table(
        "lineage_nodes",
        sa.Column("id", ID, primary_key=True),
        sa.Column("workspace_id", ID, sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("project_id", ID, sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("native_id", sa.String(1000), nullable=False),
        sa.Column("namespace", sa.String(500), nullable=False),
        sa.Column("environment", sa.String(200), nullable=False),
        sa.Column("body_json", JSON_TEXT, nullable=False),
        sa.Column("created_at", TIME, nullable=False),
        sa.UniqueConstraint("workspace_id", "project_id", "namespace", "environment", "native_id", name="uq_lineage_nodes_native"),
    )
    _create_table(
        "lineage_edges",
        sa.Column("id", ID, primary_key=True),
        sa.Column("workspace_id", ID, sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("project_id", ID, sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("from_node_id", ID, sa.ForeignKey("lineage_nodes.id"), nullable=False),
        sa.Column("to_node_id", ID, sa.ForeignKey("lineage_nodes.id"), nullable=False),
        sa.Column("relationship", sa.String(100), nullable=False),
        sa.Column("body_json", JSON_TEXT, nullable=False),
        sa.Column("created_at", TIME, nullable=False),
    )
    _create_index("ix_edges_from", "lineage_edges", ["workspace_id", "from_node_id"])
    _create_index("ix_edges_to", "lineage_edges", ["workspace_id", "to_node_id"])
    _create_table(
        "resource_groups",
        sa.Column("id", ID, primary_key=True),
        sa.Column("parent_id", ID, sa.ForeignKey("resource_groups.id")),
        sa.Column("resource_fingerprint", sa.String(500), nullable=False, unique=True),
        sa.Column("policy_json", JSON_TEXT, nullable=False),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column("fencing_generation", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("last_admitted_at", TIME),
        sa.Column("created_at", TIME, nullable=False),
    )
    _create_table(
        "connection_aliases",
        sa.Column("workspace_id", ID, sa.ForeignKey("workspaces.id"), primary_key=True),
        sa.Column("connection_id", ID, primary_key=True),
        sa.Column("source_id", ID, nullable=False),
        sa.Column("resource_group_id", ID, sa.ForeignKey("resource_groups.id"), primary_key=True),
        sa.Column("connector_id", sa.String(200), nullable=False),
        sa.Column("allowed_operations_json", JSON_TEXT, nullable=False),
        sa.Column("authorized_scope_json", JSON_TEXT, nullable=False),
        sa.Column("created_at", TIME, nullable=False),
    )
    _create_index("ix_alias_source", "connection_aliases", ["workspace_id", "source_id"])
    _create_table(
        "source_operations",
        sa.Column("id", ID, primary_key=True),
        sa.Column("workspace_id", ID, nullable=False),
        sa.Column("project_id", ID, nullable=False),
        sa.Column("run_id", ID, nullable=False),
        sa.Column("task_id", ID, nullable=False),
        sa.Column("source_id", ID, nullable=False),
        sa.Column("connection_id", ID, nullable=False),
        sa.Column("connector_id", sa.String(200), nullable=False),
        sa.Column("connector_version", sa.String(100), nullable=False),
        sa.Column("operation_id", sa.String(200), nullable=False),
        sa.Column("resource_group_ids_json", JSON_TEXT, nullable=False),
        sa.Column("request_json", JSON_TEXT, nullable=False),
        sa.Column("evidence_fingerprint", sa.String(500), nullable=False),
        sa.Column("idempotency_key", sa.String(500), nullable=False),
        sa.Column("cost_class", sa.String(80), nullable=False),
        sa.Column("state", sa.String(80), nullable=False),
        sa.Column("slot_charged", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("permit_id", ID),
        sa.Column("permit_token_hash", sa.String(128)),
        sa.Column("fencing_generation", sa.BigInteger()),
        sa.Column("permit_expires_at", TIME),
        sa.Column("lease_expires_at", TIME),
        sa.Column("attempt_id", ID),
        sa.Column("source_native_reference", sa.String(1000)),
        sa.Column("result_json", JSON_TEXT),
        sa.Column("sanitized_error", sa.Text()),
        sa.Column("queued_at", TIME, nullable=False),
        sa.Column("admitted_at", TIME),
        sa.Column("updated_at", TIME, nullable=False),
        sa.UniqueConstraint("workspace_id", "idempotency_key", name="uq_source_operations_idempotency"),
    )
    _create_index("ix_operations_group_state", "source_operations", ["state", "slot_charged", "queued_at"])
    _create_index("ix_operations_fingerprint", "source_operations", ["workspace_id", "evidence_fingerprint"])
    _create_table(
        "operation_events",
        sa.Column("sequence", SEQUENCE, primary_key=True, autoincrement=True),
        sa.Column("workspace_id", ID, nullable=False),
        sa.Column("operation_id", ID, nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("body_json", JSON_TEXT, nullable=False),
        sa.Column("created_at", TIME, nullable=False),
    )
    _create_table(
        "scenarios",
        sa.Column("id", ID, primary_key=True),
        sa.Column("workspace_id", ID, sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("project_id", ID, sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("body_json", JSON_TEXT, nullable=False),
        sa.Column("created_at", TIME, nullable=False),
        sa.Column("updated_at", TIME, nullable=False),
        sa.UniqueConstraint("workspace_id", "project_id", "name", "version", name="uq_scenarios_version"),
    )
    _create_table(
        "modernization_specs",
        sa.Column("id", ID, primary_key=True),
        sa.Column("workspace_id", ID, sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("scenario_id", ID, sa.ForeignKey("scenarios.id"), nullable=False),
        sa.Column("spec_type", sa.String(100), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("validation_status", sa.String(80), nullable=False),
        sa.Column("body_json", JSON_TEXT, nullable=False),
        sa.Column("created_at", TIME, nullable=False),
        sa.UniqueConstraint("workspace_id", "scenario_id", "spec_type", "version", name="uq_modernization_specs_version"),
    )
    _create_table(
        "validation_results",
        sa.Column("id", ID, primary_key=True),
        sa.Column("workspace_id", ID, sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("run_id", ID, sa.ForeignKey("assessments.id")),
        sa.Column("spec_id", ID, sa.ForeignKey("modernization_specs.id")),
        sa.Column("status", sa.String(80), nullable=False),
        sa.Column("evidence_json", JSON_TEXT, nullable=False),
        sa.Column("created_at", TIME, nullable=False),
    )
    _create_table(
        "exports",
        sa.Column("id", ID, primary_key=True),
        sa.Column("workspace_id", ID, sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("run_id", ID, sa.ForeignKey("assessments.id")),
        sa.Column("export_type", sa.String(100), nullable=False),
        sa.Column("state", sa.String(80), nullable=False),
        sa.Column("artifact_ref", sa.String(1000)),
        sa.Column("manifest_json", JSON_TEXT, nullable=False),
        sa.Column("created_at", TIME, nullable=False),
        sa.Column("expires_at", TIME),
    )
    _create_table(
        "outbox",
        sa.Column("id", ID, primary_key=True),
        sa.Column("workspace_id", ID, sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("aggregate_type", sa.String(100), nullable=False),
        sa.Column("aggregate_id", ID, nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("payload_json", JSON_TEXT, nullable=False),
        sa.Column("created_at", TIME, nullable=False),
        sa.Column("published_at", TIME),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
    )
    _create_index("ix_outbox_pending", "outbox", ["published_at", "created_at"])


def downgrade() -> None:
    for table in (
        "outbox", "exports", "validation_results", "modernization_specs", "scenarios",
        "operation_events", "source_operations", "connection_aliases", "resource_groups",
        "lineage_edges", "lineage_nodes", "findings", "evidence", "model_invocations",
        "run_events", "run_tasks", "assessments", "sources", "inference_profiles",
        "config_versions", "projects", "memberships", "api_tokens", "workspaces",
        "bootstrap_tokens", "users",
    ):
        op.drop_table(table)
