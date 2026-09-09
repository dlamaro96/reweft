from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE, display_name TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS bootstrap_tokens (
  token_hash TEXT PRIMARY KEY, expires_at TEXT NOT NULL, consumed_at TEXT
);
CREATE TABLE IF NOT EXISTS api_tokens (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
  token_hash TEXT NOT NULL UNIQUE, scopes_json TEXT NOT NULL,
  expires_at TEXT, revoked_at TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS workspaces (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS memberships (
  workspace_id TEXT NOT NULL REFERENCES workspaces(id),
  user_id TEXT NOT NULL REFERENCES users(id), role TEXT NOT NULL,
  PRIMARY KEY(workspace_id, user_id)
);
CREATE TABLE IF NOT EXISTS projects (
  id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id),
  name TEXT NOT NULL, created_at TEXT NOT NULL,
  UNIQUE(workspace_id, name)
);
CREATE TABLE IF NOT EXISTS inference_profiles (
  id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id),
  name TEXT NOT NULL, revision INTEGER NOT NULL, body_json TEXT NOT NULL,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(workspace_id, name)
);
CREATE TABLE IF NOT EXISTS assessments (
  id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id),
  project_id TEXT NOT NULL REFERENCES projects(id), state TEXT NOT NULL,
  version INTEGER NOT NULL, body_json TEXT NOT NULL,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_assessments_workspace ON assessments(workspace_id, created_at);
CREATE TABLE IF NOT EXISTS evidence (
  id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id),
  project_id TEXT NOT NULL REFERENCES projects(id), run_id TEXT,
  artifact_sha256 TEXT NOT NULL, body_json TEXT NOT NULL, created_at TEXT NOT NULL,
  UNIQUE(workspace_id, project_id, artifact_sha256)
);
CREATE INDEX IF NOT EXISTS ix_evidence_workspace_run ON evidence(workspace_id, run_id);
CREATE TABLE IF NOT EXISTS findings (
  id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id),
  run_id TEXT NOT NULL REFERENCES assessments(id), stable_key TEXT NOT NULL,
  body_json TEXT NOT NULL, created_at TEXT NOT NULL,
  UNIQUE(workspace_id, run_id, stable_key)
);
CREATE TABLE IF NOT EXISTS lineage_nodes (
  id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id),
  project_id TEXT NOT NULL REFERENCES projects(id), native_id TEXT NOT NULL,
  namespace TEXT NOT NULL, environment TEXT NOT NULL, body_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(workspace_id, project_id, namespace, environment, native_id)
);
CREATE TABLE IF NOT EXISTS lineage_edges (
  id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id),
  project_id TEXT NOT NULL REFERENCES projects(id), from_node_id TEXT NOT NULL,
  to_node_id TEXT NOT NULL, relationship TEXT NOT NULL, body_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY(from_node_id) REFERENCES lineage_nodes(id),
  FOREIGN KEY(to_node_id) REFERENCES lineage_nodes(id)
);
CREATE INDEX IF NOT EXISTS ix_edges_from ON lineage_edges(workspace_id, from_node_id);
CREATE INDEX IF NOT EXISTS ix_edges_to ON lineage_edges(workspace_id, to_node_id);

-- Resource groups are deployment-wide admission identities. Their labels are never
-- returned through workspace APIs; connections expose only workspace-local aliases.
CREATE TABLE IF NOT EXISTS resource_groups (
  id TEXT PRIMARY KEY, parent_id TEXT REFERENCES resource_groups(id),
  resource_fingerprint TEXT NOT NULL UNIQUE, policy_json TEXT NOT NULL,
  policy_version INTEGER NOT NULL, fencing_generation INTEGER NOT NULL DEFAULT 0,
  last_admitted_at TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS connection_aliases (
  workspace_id TEXT NOT NULL REFERENCES workspaces(id), connection_id TEXT NOT NULL,
  source_id TEXT NOT NULL, resource_group_id TEXT NOT NULL REFERENCES resource_groups(id),
  connector_id TEXT NOT NULL, allowed_operations_json TEXT NOT NULL,
  authorized_scope_json TEXT NOT NULL, created_at TEXT NOT NULL,
  PRIMARY KEY(workspace_id, connection_id, resource_group_id)
);
CREATE INDEX IF NOT EXISTS ix_alias_source ON connection_aliases(workspace_id, source_id);
CREATE TABLE IF NOT EXISTS source_operations (
  id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, project_id TEXT NOT NULL,
  run_id TEXT NOT NULL, task_id TEXT NOT NULL, source_id TEXT NOT NULL,
  connection_id TEXT NOT NULL, connector_id TEXT NOT NULL,
  connector_version TEXT NOT NULL, operation_id TEXT NOT NULL,
  resource_group_ids_json TEXT NOT NULL, request_json TEXT NOT NULL,
  evidence_fingerprint TEXT NOT NULL, idempotency_key TEXT NOT NULL,
  cost_class TEXT NOT NULL, state TEXT NOT NULL, slot_charged INTEGER NOT NULL DEFAULT 0,
  attempt_count INTEGER NOT NULL DEFAULT 0,
  permit_id TEXT, permit_token_hash TEXT, fencing_generation INTEGER,
  permit_expires_at TEXT, lease_expires_at TEXT, attempt_id TEXT,
  source_native_reference TEXT, result_json TEXT, sanitized_error TEXT,
  queued_at TEXT NOT NULL, admitted_at TEXT, updated_at TEXT NOT NULL,
  UNIQUE(workspace_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS ix_operations_group_state ON source_operations(state, slot_charged, queued_at);
CREATE INDEX IF NOT EXISTS ix_operations_fingerprint ON source_operations(workspace_id, evidence_fingerprint);
CREATE TABLE IF NOT EXISTS operation_events (
  sequence INTEGER PRIMARY KEY AUTOINCREMENT, workspace_id TEXT NOT NULL,
  operation_id TEXT NOT NULL, event_type TEXT NOT NULL, body_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
"""


class Database:
    """Small durable store for development and tests.

    Each transaction gets a fresh connection. ``BEGIN IMMEDIATE`` serializes the
    short admission decision across API/collector processes sharing the database.
    Production deployments can replace this repository with PostgreSQL while
    preserving the controller contract.
    """

    def __init__(self, path: str | Path):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 15000")
        if self.path != ":memory:":
            connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    @contextmanager
    def transaction(self, *, immediate: bool = False) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        if self.path != ":memory:":
            connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    @contextmanager
    def transaction(self, *, immediate: bool = False) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
