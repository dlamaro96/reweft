from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import inspect

from reweft.persistence import Database


RUNTIME_TABLES = {
    "users", "workspaces", "projects", "sources", "assessments", "run_tasks",
    "run_events", "model_invocations", "evidence", "source_operations",
    "scenarios", "modernization_specs", "validation_results", "exports",
    "config_versions", "outbox", "alembic_version",
}


def test_sqlite_migrations_and_raw_query_compatibility(tmp_path: Path):
    database = Database(tmp_path / "runtime.db")
    database.initialize()
    database.initialize()  # startup migrations are idempotent
    assert database.dialect_name == "sqlite"
    assert RUNTIME_TABLES <= set(inspect(database.engine).get_table_names())

    workspace_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with database.transaction(immediate=True) as connection:
        connection.execute(
            "INSERT INTO workspaces(id,name,created_at) VALUES(?,?,?)",
            (workspace_id, "SQLite fixture", now),
        )
        row = connection.execute("SELECT '?' AS literal, name FROM workspaces WHERE id=?", (workspace_id,)).fetchone()
        assert row["literal"] == "?"
        assert row[1] == "SQLite fixture"
        assert dict(row)["name"] == "SQLite fixture"

    with pytest.raises(RuntimeError):
        with database.transaction(immediate=True) as connection:
            connection.execute("UPDATE workspaces SET name=? WHERE id=?", ("must rollback", workspace_id))
            raise RuntimeError("rollback")
    with database.connect() as connection:
        assert connection.execute("SELECT name FROM workspaces WHERE id=?", (workspace_id,)).fetchone()[0] == "SQLite fixture"
    database.dispose()


def test_pre_alembic_sqlite_schema_is_upgraded_in_place(tmp_path: Path):
    path = tmp_path / "legacy.db"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE users (id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE, display_name TEXT NOT NULL, created_at TEXT NOT NULL)")
    connection.execute("INSERT INTO users VALUES ('legacy-user','legacy@example.test','Legacy','2026-09-09T00:00:00+00:00')")
    connection.commit()
    connection.close()

    database = Database(path)
    database.initialize()
    assert RUNTIME_TABLES <= set(inspect(database.engine).get_table_names())
    with database.connect() as migrated:
        assert migrated.execute("SELECT display_name FROM users WHERE id=?", ("legacy-user",)).fetchone()[0] == "Legacy"
    database.dispose()


@pytest.mark.skipif(not os.getenv("REWEFT_TEST_DATABASE_URL"), reason="REWEFT_TEST_DATABASE_URL is not configured")
def test_postgres_migrations_and_compatibility_interface():
    url = os.environ["REWEFT_TEST_DATABASE_URL"]
    if not url.startswith(("postgresql://", "postgresql+psycopg://")):
        pytest.fail("REWEFT_TEST_DATABASE_URL must identify a dedicated PostgreSQL test database")
    database = Database(url)
    database.initialize()
    database.initialize()
    assert database.dialect_name == "postgresql"
    assert RUNTIME_TABLES <= set(inspect(database.engine).get_table_names())

    user_id, workspace_id = str(uuid4()), str(uuid4())
    now = datetime.now(timezone.utc).isoformat()
    try:
        with database.transaction(immediate=True) as connection:
            connection.execute("INSERT INTO users(id,email,display_name,created_at) VALUES(?,?,?,?)", (user_id, f"{user_id}@example.test", "Postgres fixture", now))
            connection.execute("INSERT INTO workspaces(id,name,created_at) VALUES(?,?,?)", (workspace_id, "Postgres fixture", now))
            connection.execute("INSERT INTO memberships(workspace_id,user_id,role) VALUES(?,?,?)", (workspace_id, user_id, "owner"))
        with database.connect() as connection:
            row = connection.execute("SELECT id,name FROM workspaces WHERE id=?", (workspace_id,)).fetchone()
            assert row["id"] == workspace_id
            assert row[1] == "Postgres fixture"
    finally:
        with database.transaction(immediate=True) as connection:
            connection.execute("DELETE FROM memberships WHERE workspace_id=?", (workspace_id,))
            connection.execute("DELETE FROM workspaces WHERE id=?", (workspace_id,))
            connection.execute("DELETE FROM users WHERE id=?", (user_id,))
        database.dispose()
