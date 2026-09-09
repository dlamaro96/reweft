from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import socket
from dataclasses import dataclass
from datetime import datetime, timezone
from time import monotonic
from typing import Any

import psycopg
from psycopg.rows import dict_row

from reweft.runtime.models import PostgresSourceConfiguration


class ConnectorError(RuntimeError):
    def __init__(self, code: str, detail: str, *, execution_unknown: bool = False):
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.execution_unknown = execution_unknown


class SourceSecretResolver:
    def resolve(self, reference: str) -> dict[str, str]:
        prefix = "secret://source/"
        if not reference.startswith(prefix):
            raise ConnectorError("SECRET_REFERENCE_DENIED", "source secret reference is outside its namespace")
        suffix = reference.removeprefix(prefix).replace("/", "_").replace("-", "_").upper()
        raw = os.getenv(f"REWEFT_SECRET_SOURCE_{suffix}")
        if not raw:
            raise ConnectorError("SECRET_UNAVAILABLE", f"configured source secret {reference} is unavailable")
        try:
            value = json.loads(raw)
        except ValueError as exc:
            raise ConnectorError("SECRET_INVALID", "source secret must be a JSON object") from exc
        if set(value) != {"username", "password"} or not all(isinstance(item, str) and item for item in value.values()):
            raise ConnectorError("SECRET_INVALID", "source secret must contain only username and password")
        return value


class SourceEndpointPolicy:
    _FORBIDDEN = {ipaddress.ip_address("169.254.169.254"), ipaddress.ip_address("100.100.100.200")}

    def __init__(self, allowed: set[str] | None = None):
        configured = os.getenv("REWEFT_SOURCE_ALLOWED_ENDPOINTS", "")
        self.allowed = allowed or {value.strip().lower() for value in configured.split(",") if value.strip()}

    def validate(self, host: str, port: int) -> None:
        endpoint = f"{host.lower()}:{port}"
        if endpoint not in self.allowed:
            raise ConnectorError("SOURCE_ENDPOINT_NOT_ALLOWED", "source endpoint is not in the deployment allowlist")
        try:
            addresses = {ipaddress.ip_address(item[4][0]) for item in socket.getaddrinfo(host, port)}
        except socket.gaierror as exc:
            raise ConnectorError("SOURCE_DNS_FAILED", "source endpoint DNS resolution failed") from exc
        if any(address in self._FORBIDDEN or address.is_link_local for address in addresses):
            raise ConnectorError("SOURCE_ENDPOINT_FORBIDDEN", "source endpoint resolved to forbidden metadata space")


@dataclass(frozen=True)
class CollectionResult:
    operation: str
    native_execution_reference: str | None
    artifact_sha256: str
    artifact_bytes: bytes
    media_type: str
    object_count: int
    duration_ms: int
    completeness: dict[str, Any]


class PostgreSQLCollector:
    """Bounded, metadata-only PostgreSQL operations; no caller-supplied SQL path."""

    SUPPORTED_OPERATIONS = frozenset({"test_connection", "discover_assets", "get_definitions", "execution_status"})

    def __init__(self, endpoint_policy: SourceEndpointPolicy | None = None):
        self.endpoint_policy = endpoint_policy or SourceEndpointPolicy()

    def collect(
        self,
        configuration: PostgresSourceConfiguration,
        credentials: dict[str, str],
        operation: str,
        parameters: dict[str, Any] | None = None,
    ) -> CollectionResult:
        if operation not in self.SUPPORTED_OPERATIONS:
            raise ConnectorError("OPERATION_NOT_ALLOWED", "operation is not a supported PostgreSQL metadata operation")
        self.endpoint_policy.validate(configuration.host, configuration.port)
        parameters = parameters or {}
        started = monotonic()
        connection: psycopg.Connection | None = None
        native_reference = None
        try:
            connection = psycopg.connect(
                host=configuration.host,
                port=configuration.port,
                dbname=configuration.database,
                user=credentials["username"],
                password=credentials["password"],
                sslmode=configuration.sslmode,
                connect_timeout=max(1, min(10, configuration.statement_timeout_ms // 1000)),
                options=f"-c statement_timeout={configuration.statement_timeout_ms} -c default_transaction_read_only=on",
                row_factory=dict_row,
                autocommit=False,
            )
            with connection.transaction():
                connection.execute("SET TRANSACTION READ ONLY")
                native_reference = str(connection.execute("SELECT pg_backend_pid() AS pid").fetchone()["pid"])
                if operation == "test_connection":
                    payload = self._test(connection)
                elif operation == "discover_assets":
                    payload = self._discover(connection, configuration)
                elif operation == "get_definitions":
                    payload = self._definitions(connection, configuration)
                else:
                    payload = self._execution_status(connection, parameters)
            content = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
            if len(content) > 16_777_216:
                raise ConnectorError("RESPONSE_LIMIT_EXCEEDED", "metadata response exceeded the connector hard limit")
            return CollectionResult(
                operation=operation,
                native_execution_reference=native_reference,
                artifact_sha256=hashlib.sha256(content).hexdigest(),
                artifact_bytes=content,
                media_type="application/vnd.reweft.postgresql-metadata+json",
                object_count=len(payload.get("tables", [])) + len(payload.get("views", [])),
                duration_ms=int((monotonic() - started) * 1000),
                completeness={
                    "status": "complete" if not payload.get("truncated") else "partial",
                    "schemas": configuration.schemas,
                    "object_types": payload.get("object_types", ["connection"]),
                    "truncated": bool(payload.get("truncated")),
                    "unsupported": ["dynamic SQL", "functions/procedures", "extension-defined dependencies"],
                },
            )
        except psycopg.errors.QueryCanceled as exc:
            raise ConnectorError("SOURCE_TIMEOUT_CONFIRMED", "PostgreSQL confirmed statement cancellation") from exc
        except psycopg.Error as exc:
            # A lost connection cannot establish whether the server-side operation ended.
            unknown = connection is not None and getattr(connection, "closed", False)
            raise ConnectorError("SOURCE_DATABASE_ERROR", "PostgreSQL metadata operation failed", execution_unknown=bool(unknown)) from exc
        finally:
            if connection is not None:
                connection.close()

    @staticmethod
    def _test(connection: psycopg.Connection) -> dict[str, Any]:
        row = connection.execute(
            "SELECT current_database() AS database, current_user AS user, "
            "current_setting('server_version_num') AS server_version_num, "
            "current_setting('transaction_read_only') AS transaction_read_only"
        ).fetchone()
        return {"connection": row, "object_types": ["connection"]}

    @staticmethod
    def _discover(connection: psycopg.Connection, configuration: PostgresSourceConfiguration) -> dict[str, Any]:
        tables = connection.execute(
            "SELECT table_schema,s.table_name,s.table_type,COALESCE(c.reltuples,0)::bigint AS estimated_rows "
            "FROM information_schema.tables s LEFT JOIN pg_catalog.pg_namespace n ON n.nspname=s.table_schema "
            "LEFT JOIN pg_catalog.pg_class c ON c.relnamespace=n.oid AND c.relname=s.table_name "
            "WHERE s.table_schema = ANY(%s) ORDER BY s.table_schema,s.table_name LIMIT %s",
            (configuration.schemas, configuration.max_objects + 1),
        ).fetchall()
        truncated = len(tables) > configuration.max_objects
        tables = tables[: configuration.max_objects]
        columns = connection.execute(
            "SELECT table_schema,table_name,column_name,ordinal_position,data_type,is_nullable,column_default "
            "FROM information_schema.columns WHERE table_schema = ANY(%s) "
            "ORDER BY table_schema,table_name,ordinal_position LIMIT %s",
            (configuration.schemas, configuration.max_objects * 100),
        ).fetchall()
        constraints = connection.execute(
            "SELECT tc.constraint_schema,tc.table_name,tc.constraint_name,tc.constraint_type,kcu.column_name,"
            "ccu.table_schema AS foreign_table_schema,ccu.table_name AS foreign_table_name,ccu.column_name AS foreign_column_name "
            "FROM information_schema.table_constraints tc "
            "LEFT JOIN information_schema.key_column_usage kcu ON tc.constraint_name=kcu.constraint_name AND tc.constraint_schema=kcu.constraint_schema "
            "LEFT JOIN information_schema.constraint_column_usage ccu ON tc.constraint_name=ccu.constraint_name AND tc.constraint_schema=ccu.constraint_schema "
            "WHERE tc.table_schema = ANY(%s) ORDER BY tc.table_name,tc.constraint_name,kcu.ordinal_position",
            (configuration.schemas,),
        ).fetchall()
        return {
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "schemas": configuration.schemas,
            "tables": tables,
            "columns": columns,
            "constraints": constraints,
            "views": [row for row in tables if row["table_type"] == "VIEW"],
            "object_types": ["schema", "table", "view", "column", "key", "foreign-key"],
            "truncated": truncated,
        }

    @staticmethod
    def _definitions(connection: psycopg.Connection, configuration: PostgresSourceConfiguration) -> dict[str, Any]:
        views = connection.execute(
            "SELECT schemaname AS table_schema,viewname AS view_name,definition "
            "FROM pg_catalog.pg_views WHERE schemaname = ANY(%s) ORDER BY schemaname,viewname LIMIT %s",
            (configuration.schemas, configuration.max_objects),
        ).fetchall()
        return {
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "views": views,
            "object_types": ["view-definition"],
            "truncated": len(views) >= configuration.max_objects,
        }

    @staticmethod
    def _execution_status(connection: psycopg.Connection, parameters: dict[str, Any]) -> dict[str, Any]:
        reference = parameters.get("native_execution_reference")
        if not isinstance(reference, str) or not reference.isdigit():
            raise ConnectorError("PARAMETER_INVALID", "execution_status requires a numeric native execution reference")
        row = connection.execute(
            "SELECT pid,state,wait_event_type,wait_event,query_start IS NOT NULL AS observed "
            "FROM pg_catalog.pg_stat_activity WHERE pid=%s AND datname=current_database()",
            (int(reference),),
        ).fetchone()
        return {"execution": row or {"pid": int(reference), "observed": False}, "object_types": ["execution-status"]}
