from __future__ import annotations

import csv
import hashlib
import io
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from reweft.runtime.models import ArtifactBundleConfiguration

from .postgresql import CollectionResult, ConnectorError


class ArtifactBundleCollector:
    """Read a named, operator-mounted bundle without executing imported content."""

    EXTENSIONS = {".sql": "sql", ".json": "json", ".yaml": "yaml", ".yml": "yaml", ".csv": "csv"}

    def __init__(self, root: str | Path | None = None):
        self.root = Path(root or os.getenv("REWEFT_ARTIFACT_ROOT", "/opt/reweft/artifacts")).resolve()

    def collect(self, configuration: ArtifactBundleConfiguration) -> CollectionResult:
        bundle = (self.root / configuration.bundle_id).resolve()
        try:
            bundle.relative_to(self.root)
        except ValueError as exc:
            raise ConnectorError("BUNDLE_PATH_DENIED", "artifact bundle escaped the configured root") from exc
        if not bundle.is_dir() or bundle.is_symlink():
            raise ConnectorError("BUNDLE_NOT_FOUND", "configured artifact bundle is unavailable")
        files: list[dict[str, Any]] = []
        total_bytes = 0
        candidates = sorted(path for path in bundle.rglob("*") if path.is_file())
        if len(candidates) > configuration.max_files:
            raise ConnectorError("BUNDLE_FILE_LIMIT", "artifact bundle contains too many files")
        for path in candidates:
            if path.is_symlink():
                raise ConnectorError("BUNDLE_SYMLINK_DENIED", "artifact bundle contains a symlink")
            kind = self.EXTENSIONS.get(path.suffix.lower())
            if not kind or kind not in configuration.formats:
                raise ConnectorError("BUNDLE_TYPE_DENIED", f"unsupported artifact type: {path.suffix.lower() or '<none>'}")
            size = path.stat().st_size
            if size > configuration.max_file_bytes:
                raise ConnectorError("BUNDLE_FILE_LIMIT", "artifact file exceeds configured size limit")
            total_bytes += size
            if total_bytes > configuration.max_total_bytes:
                raise ConnectorError("BUNDLE_TOTAL_LIMIT", "artifact bundle exceeds configured total size")
            raw = path.read_bytes()
            if b"\x00" in raw:
                raise ConnectorError("BUNDLE_BINARY_DENIED", "binary artifact content is unsupported")
            text = raw.decode("utf-8")
            parsed = self._parse(kind, text)
            files.append(
                {
                    "path": str(path.relative_to(bundle)),
                    "kind": kind,
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "size": size,
                    "content": parsed,
                }
            )
        payload = {
            "bundle_id": configuration.bundle_id,
            "files": files,
            "coverage": {"file_count": len(files), "total_bytes": total_bytes, "complete": True},
            "execution": "content parsed as data; no imported code, SQL, macro, or formula was executed",
        }
        content = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        return CollectionResult(
            operation="import_bundle",
            native_execution_reference=None,
            artifact_sha256=hashlib.sha256(content).hexdigest(),
            artifact_bytes=content,
            media_type="application/vnd.reweft.artifact-bundle+json",
            object_count=len(files),
            duration_ms=0,
            completeness={"status": "complete", "files": len(files), "truncated": False, "unsupported": []},
        )

    @staticmethod
    def _parse(kind: str, text: str) -> Any:
        if kind == "json":
            return json.loads(text)
        if kind == "yaml":
            return yaml.safe_load(text)
        if kind == "csv":
            return list(csv.DictReader(io.StringIO(text)))
        # SQL is evidence text. It is intentionally never passed to a database.
        return {"text": text, "statements_not_executed": True}
