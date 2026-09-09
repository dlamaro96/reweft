from __future__ import annotations

import sqlite3
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any, overload

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Connection, Engine, Row
from sqlalchemy.exc import IntegrityError as SQLAlchemyIntegrityError
from sqlalchemy.pool import StaticPool


MIGRATION_ADVISORY_LOCK_ID = 7_295_874_021_269_235_081
ADMISSION_ADVISORY_LOCK_ID = 6_521_031_747_921_004_519


class RowAdapter(Mapping[str, Any]):
    """DB-API/``sqlite3.Row`` compatible view over a SQLAlchemy row."""

    def __init__(self, row: Row[Any]):
        self._row = row
        self._mapping = row._mapping

    @overload
    def __getitem__(self, key: str) -> Any: ...

    @overload
    def __getitem__(self, key: int) -> Any: ...

    def __getitem__(self, key: str | int) -> Any:
        if isinstance(key, int):
            return self._row[key]
        return self._mapping[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._mapping)

    def __len__(self) -> int:
        return len(self._mapping)

    def keys(self):
        return self._mapping.keys()


class ResultAdapter:
    def __init__(self, result: Any):
        self._result = result

    @property
    def rowcount(self) -> int:
        return self._result.rowcount

    def fetchone(self) -> RowAdapter | None:
        row = self._result.fetchone()
        return RowAdapter(row) if row is not None else None

    def fetchall(self) -> list[RowAdapter]:
        return [RowAdapter(row) for row in self._result.fetchall()]

    def __iter__(self) -> Iterator[RowAdapter]:
        for row in self._result:
            yield RowAdapter(row)


class ConnectionAdapter:
    """Compatibility surface for existing SQLite-style raw queries."""

    def __init__(self, connection: Connection, dialect_name: str):
        self._connection = connection
        self.dialect_name = dialect_name

    def execute(self, statement: str, parameters: Sequence[Any] | Mapping[str, Any] = ()) -> ResultAdapter:
        sql = self._translate_dialect_sql(statement)
        if isinstance(parameters, Mapping):
            bound = dict(parameters)
        else:
            sql, bound = _bind_qmarks(sql, tuple(parameters))
        try:
            return ResultAdapter(self._connection.execute(text(sql), bound))
        except SQLAlchemyIntegrityError as exc:
            # Preserve the error contract already consumed by auth/controller.
            raise sqlite3.IntegrityError(str(exc.orig)) from exc

    def _translate_dialect_sql(self, statement: str) -> str:
        if self.dialect_name != "postgresql":
            return statement
        sql = statement.replace("INSERT OR IGNORE INTO", "INSERT INTO")
        if "INSERT OR IGNORE INTO" in statement:
            sql = f"{sql.rstrip()} ON CONFLICT DO NOTHING"
        return sql.replace(
            "json_extract(result_json,'$.actual_usage.response_bytes')",
            "(result_json::jsonb #>> '{actual_usage,response_bytes}')",
        )

    def __enter__(self) -> ConnectionAdapter:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self._connection.close()


def _bind_qmarks(statement: str, parameters: tuple[Any, ...]) -> tuple[str, dict[str, Any]]:
    """Convert qmarks to named binds without touching quoted question marks."""

    output: list[str] = []
    index = 0
    quote: str | None = None
    position = 0
    while position < len(statement):
        character = statement[position]
        if quote:
            output.append(character)
            if character == quote:
                if position + 1 < len(statement) and statement[position + 1] == quote:
                    output.append(statement[position + 1])
                    position += 1
                else:
                    quote = None
        elif character in {"'", '"'}:
            quote = character
            output.append(character)
        elif character == "?":
            if index >= len(parameters):
                raise ValueError("not enough parameters for SQL qmarks")
            output.append(f":p{index}")
            index += 1
        else:
            output.append(character)
        position += 1
    if index != len(parameters):
        raise ValueError("too many parameters for SQL qmarks")
    return "".join(output), {f"p{number}": value for number, value in enumerate(parameters)}


class Database:
    """SQLAlchemy database retaining the current raw-query repository API.

    Paths and ``:memory:`` are explicit SQLite demo/test stores. SQLAlchemy URLs
    select their dialect; real mode supplies ``postgresql+psycopg://``.
    """

    def __init__(self, path_or_url: str | Path):
        raw = str(path_or_url)
        if raw.startswith("postgresql://"):
            self.url = raw.replace("postgresql://", "postgresql+psycopg://", 1)
        elif "://" in raw:
            self.url = raw
        elif raw == ":memory:":
            self.url = "sqlite+pysqlite:///:memory:"
        else:
            path = Path(raw)
            path.parent.mkdir(parents=True, exist_ok=True)
            self.url = f"sqlite+pysqlite:///{path.absolute()}"
        self.engine = self._build_engine(self.url)
        self.dialect_name = self.engine.dialect.name
        self.path = raw

    @staticmethod
    def _build_engine(url: str) -> Engine:
        kwargs: dict[str, Any] = {"pool_pre_ping": True}
        if url == "sqlite+pysqlite:///:memory:":
            kwargs.update(connect_args={"check_same_thread": False}, poolclass=StaticPool)
        elif url.startswith("sqlite"):
            kwargs.update(connect_args={"timeout": 15})
        engine = create_engine(url, **kwargs)
        if engine.dialect.name == "sqlite":
            @event.listens_for(engine, "connect")
            def configure_sqlite(dbapi_connection, _connection_record) -> None:
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys = ON")
                cursor.execute("PRAGMA busy_timeout = 15000")
                if url != "sqlite+pysqlite:///:memory:":
                    cursor.execute("PRAGMA journal_mode = WAL")
                cursor.close()
        return engine

    def initialize(self) -> None:
        """Upgrade to head under a cross-replica PostgreSQL advisory lock."""

        config = Config(str(Path(__file__).parents[3] / "alembic.ini"))
        config.set_main_option("script_location", str(Path(__file__).parents[3] / "migrations"))
        config.set_main_option("sqlalchemy.url", self.url.replace("%", "%%"))
        with self.engine.connect() as connection:
            if self.dialect_name == "postgresql":
                transaction = connection.begin()
                try:
                    connection.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": MIGRATION_ADVISORY_LOCK_ID})
                    config.attributes["connection"] = connection
                    command.upgrade(config, "head")
                    transaction.commit()
                except Exception:
                    transaction.rollback()
                    raise
            else:
                config.attributes["connection"] = connection
                command.upgrade(config, "head")

    def connect(self) -> ConnectionAdapter:
        return ConnectionAdapter(self.engine.connect(), self.dialect_name)

    @contextmanager
    def transaction(self, *, immediate: bool = False) -> Iterator[ConnectionAdapter]:
        connection = self.engine.connect()
        transaction = None
        try:
            if immediate and self.dialect_name == "sqlite":
                connection.exec_driver_sql("BEGIN IMMEDIATE")
            else:
                transaction = connection.begin()
                if immediate and self.dialect_name == "postgresql":
                    connection.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": ADMISSION_ADVISORY_LOCK_ID})
            yield ConnectionAdapter(connection, self.dialect_name)
            if transaction is not None:
                transaction.commit()
            else:
                connection.commit()
        except Exception:
            if transaction is not None and transaction.is_active:
                transaction.rollback()
            elif connection.in_transaction():
                connection.rollback()
            raise
        finally:
            connection.close()

    def dispose(self) -> None:
        self.engine.dispose()
