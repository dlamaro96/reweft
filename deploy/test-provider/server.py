"""Deterministic, synthetic OpenAI-compatible fixture server for CI only."""

from __future__ import annotations

import json
import os
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


MODEL = os.getenv("REWEFT_TEST_PROVIDER_MODEL", "reweft-deterministic-test-v1")
NOTICE = "SYNTHETIC TEST PROVIDER — NO MODEL INFERENCE"
CREATED_AT = 1_788_912_000


def _resolve_ref(root: dict, reference: str) -> dict:
    if not reference.startswith("#/"):
        return {}
    value: object = root
    for part in reference[2:].split("/"):
        if not isinstance(value, dict):
            return {}
        value = value.get(part.replace("~1", "/").replace("~0", "~"))
    return value if isinstance(value, dict) else {}


def _schema_value(schema: dict, root: dict, name: str = "value", depth: int = 0) -> object:
    """Create a small deterministic instance for the JSON-schema subset used in CI."""
    if depth > 12:
        return None
    if "$ref" in schema:
        return _schema_value(_resolve_ref(root, str(schema["$ref"])), root, name, depth + 1)
    if "const" in schema:
        return schema["const"]
    if schema.get("enum"):
        return schema["enum"][0]
    if "default" in schema:
        return schema["default"]
    if "examples" in schema and schema["examples"]:
        return schema["examples"][0]
    if schema.get("allOf"):
        merged: dict = {}
        for item in schema["allOf"]:
            if isinstance(item, dict):
                merged.update(item)
        return _schema_value(merged, root, name, depth + 1)
    for choice_key in ("oneOf", "anyOf"):
        if schema.get(choice_key):
            return _schema_value(schema[choice_key][0], root, name, depth + 1)

    kind = schema.get("type")
    if isinstance(kind, list):
        kind = next((item for item in kind if item != "null"), "null")
    if kind == "object" or "properties" in schema:
        properties = schema.get("properties") or {}
        required = schema.get("required") or list(properties)
        return {
            key: _schema_value(properties.get(key, {}), root, key, depth + 1)
            for key in required
        }
    if kind == "array":
        minimum = max(0, int(schema.get("minItems", 0)))
        count = min(max(minimum, 1), 3)
        return [_schema_value(schema.get("items", {}), root, name, depth + 1) for _ in range(count)]
    if kind == "boolean":
        return True
    if kind == "integer":
        return int(schema.get("minimum", 1))
    if kind == "number":
        return float(schema.get("minimum", 1))
    if kind == "null":
        return None
    values = {
        "protocol": "reweft-provider-probe",
        "decision": "finish",
        "reason": "Deterministic CI fixture response; no model was invoked.",
        "status": "synthetic",
    }
    return values.get(name, f"synthetic-{name.replace('_', '-')}")


def _structured_result(request: dict, request_hash: str) -> dict:
    text = request.get("text") if isinstance(request.get("text"), dict) else {}
    format_spec = text.get("format") if isinstance(text.get("format"), dict) else {}
    schema = format_spec.get("schema") if isinstance(format_spec.get("schema"), dict) else None
    if schema is not None:
        result = _schema_value(schema, schema)
        if isinstance(result, dict):
            return result
    return {
        "synthetic": True,
        "notice": NOTICE,
        "decision": "finish",
        "reason": "Deterministic CI fixture response; no model was invoked.",
        "request_hash": request_hash,
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "ReweftDeterministicFixture/1"

    def _send(self, status: int, body: dict) -> None:
        payload = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("X-Reweft-Synthetic-Provider", "true")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/healthz":
            self._send(200, {"status": "ok", "synthetic": True})
        elif self.path == "/v1/models":
            self._send(200, {"object": "list", "data": [{"id": MODEL, "object": "model", "owned_by": "reweft-fixture"}]})
        else:
            self._send(404, {"error": {"type": "not_found", "message": NOTICE}})

    def do_POST(self) -> None:  # noqa: N802
        if self.path not in {"/v1/responses", "/v1/chat/completions"}:
            self._send(404, {"error": {"type": "not_found", "message": NOTICE}})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size <= 0 or size > 262_144:
                raise ValueError("request size must be between 1 and 262144 bytes")
            raw = self.rfile.read(size)
            request = json.loads(raw)
        except (ValueError, json.JSONDecodeError) as exc:
            self._send(400, {"error": {"type": "invalid_request", "message": str(exc)}})
            return
        request_hash = sha256(raw).hexdigest()[:16]
        result = _structured_result(request, request_hash)
        content = json.dumps(result, sort_keys=True, separators=(",", ":"))
        created = CREATED_AT
        if self.path.endswith("/responses"):
            self._send(200, {
                "id": f"resp_fixture_{request_hash}", "object": "response", "created_at": created,
                "status": "completed", "model": MODEL,
                "output": [{"id": f"msg_fixture_{request_hash}", "type": "message", "role": "assistant", "status": "completed",
                            "content": [{"type": "output_text", "text": content, "annotations": []}]}],
                "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
                "metadata": {"reweft_fixture": "true"},
            })
        else:
            self._send(200, {
                "id": f"chatcmpl_fixture_{request_hash}", "object": "chat.completion", "created": created, "model": MODEL,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            })

    def log_message(self, format: str, *args: object) -> None:
        return


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8090), Handler).serve_forever()
