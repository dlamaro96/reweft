from __future__ import annotations

import json

import pytest

from reweft.connectors.builtin import ArtifactBundleCollector, SourceEndpointPolicy, SourceSecretResolver
from reweft.connectors.builtin.postgresql import ConnectorError
from reweft.runtime.models import ArtifactBundleConfiguration, PostgresSourceConfiguration


def test_postgres_configuration_rejects_sql_expressions():
    with pytest.raises(ValueError):
        PostgresSourceConfiguration(
            host="source-postgres",
            database="estate",
            schemas=["public; DROP TABLE users"],
            sslmode="disable",
            resource_fingerprint="sha256:physical-estate",
        )


def test_source_endpoint_requires_deployment_allowlist(monkeypatch):
    monkeypatch.setattr("socket.getaddrinfo", lambda *_: [(None, None, None, None, ("10.0.0.8", 5432))])
    SourceEndpointPolicy({"source-postgres:5432"}).validate("source-postgres", 5432)
    with pytest.raises(ConnectorError) as denied:
        SourceEndpointPolicy({"source-postgres:5432"}).validate("other-postgres", 5432)
    assert denied.value.code == "SOURCE_ENDPOINT_NOT_ALLOWED"


def test_source_secret_is_namespaced_and_shape_checked(monkeypatch):
    monkeypatch.setenv("REWEFT_SECRET_SOURCE_ATLAS", json.dumps({"username": "collector", "password": "canary"}))
    assert SourceSecretResolver().resolve("secret://source/atlas")["username"] == "collector"
    with pytest.raises(ConnectorError):
        SourceSecretResolver().resolve("secret://inference/atlas")


def test_artifact_bundle_is_bounded_and_never_executes_sql(tmp_path):
    bundle = tmp_path / "atlas"
    bundle.mkdir()
    (bundle / "pipeline.sql").write_text("select 1;", encoding="utf-8")
    (bundle / "report.json").write_text('{"metric":"recognized_revenue"}', encoding="utf-8")
    result = ArtifactBundleCollector(tmp_path).collect(ArtifactBundleConfiguration(bundle_id="atlas"))
    body = json.loads(result.artifact_bytes)
    assert result.object_count == 2
    assert body["execution"].startswith("content parsed as data")
    sql = next(item for item in body["files"] if item["kind"] == "sql")
    assert sql["content"]["statements_not_executed"] is True


def test_artifact_bundle_denies_symlinks(tmp_path):
    outside = tmp_path / "outside.sql"
    outside.write_text("select 'secret';", encoding="utf-8")
    bundle = tmp_path / "atlas"
    bundle.mkdir()
    (bundle / "escape.sql").symlink_to(outside)
    with pytest.raises(ConnectorError) as denied:
        ArtifactBundleCollector(tmp_path).collect(ArtifactBundleConfiguration(bundle_id="atlas"))
    assert denied.value.code == "BUNDLE_SYMLINK_DENIED"
