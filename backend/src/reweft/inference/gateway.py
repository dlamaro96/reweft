from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import socket
from dataclasses import dataclass
from time import monotonic
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx

from reweft.domain.models import EndpointClass, InferenceProfile, ProviderType


class InferenceError(RuntimeError):
    def __init__(self, code: str, detail: str, *, retryable: bool = False):
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.retryable = retryable


class SecretResolver(Protocol):
    def resolve(self, reference: str) -> str: ...


class EnvironmentSecretResolver:
    """Resolve explicit secret references without exposing values to API responses."""

    def resolve(self, reference: str) -> str:
        prefix = "secret://inference/"
        if not reference.startswith(prefix):
            raise InferenceError("SECRET_REFERENCE_DENIED", "inference secret reference is outside its namespace")
        suffix = reference.removeprefix(prefix).replace("/", "_").replace("-", "_").upper()
        variable = f"REWEFT_SECRET_INFERENCE_{suffix}"
        value = os.getenv(variable)
        if not value:
            raise InferenceError("SECRET_UNAVAILABLE", f"configured inference secret {reference} is unavailable")
        return value


class EndpointPolicy:
    """Deployment allowlist plus explicit cloud-metadata/control-plane denial."""

    _FORBIDDEN_HOSTS = {
        "metadata.google.internal",
        "metadata.azure.internal",
        "instance-data.ec2.internal",
        "host.docker.internal",
    }
    _FORBIDDEN_IPS = {
        ipaddress.ip_address("169.254.169.254"),
        ipaddress.ip_address("100.100.100.200"),
    }

    def __init__(self, allowed_endpoints: set[str] | None = None):
        configured = os.getenv("REWEFT_PROVIDER_ALLOWED_ENDPOINTS", "")
        self.allowed_endpoints = allowed_endpoints or {value.strip().rstrip("/") for value in configured.split(",") if value.strip()}

    def validate(self, url: str, endpoint_class: EndpointClass) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise InferenceError("ENDPOINT_INVALID", "provider endpoint must be an absolute HTTP(S) URL")
        if parsed.username or parsed.password:
            raise InferenceError("ENDPOINT_CREDENTIALS_DENIED", "provider credentials must not be embedded in URLs")
        host = parsed.hostname.rstrip(".").lower()
        if host in self._FORBIDDEN_HOSTS:
            raise InferenceError("ENDPOINT_FORBIDDEN", "provider endpoint targets a forbidden control-plane host")
        try:
            direct_ip = ipaddress.ip_address(host)
        except ValueError:
            direct_ip = None
        if direct_ip in self._FORBIDDEN_IPS or (direct_ip and direct_ip.is_link_local):
            raise InferenceError("ENDPOINT_FORBIDDEN", "provider endpoint targets link-local metadata space")
        origin = f"{parsed.scheme}://{host}:{parsed.port or (443 if parsed.scheme == 'https' else 80)}"
        allow = {self._origin(value) for value in self.allowed_endpoints}
        if endpoint_class in {EndpointClass.LOCAL, EndpointClass.PRIVATE} and origin not in allow:
            raise InferenceError("PRIVATE_ENDPOINT_NOT_ALLOWED", "private/local endpoints require an explicit deployment allowlist")
        if allow and origin not in allow:
            raise InferenceError("ENDPOINT_NOT_ALLOWED", "provider endpoint is not in the deployment allowlist")
        if endpoint_class == EndpointClass.PUBLIC and parsed.scheme != "https":
            raise InferenceError("PUBLIC_TLS_REQUIRED", "public provider endpoints require HTTPS")
        # DNS is checked at dispatch as defense in depth. Private/local endpoints are
        # allowed only when the deployment explicitly listed their origin.
        try:
            resolved = {ipaddress.ip_address(item[4][0]) for item in socket.getaddrinfo(host, parsed.port or 443)}
        except socket.gaierror as exc:
            raise InferenceError("ENDPOINT_DNS_FAILED", "provider endpoint DNS resolution failed", retryable=True) from exc
        if any(address in self._FORBIDDEN_IPS or address.is_link_local for address in resolved):
            raise InferenceError("ENDPOINT_FORBIDDEN", "provider endpoint resolved to forbidden link-local space")

    @staticmethod
    def _origin(value: str) -> str:
        parsed = urlparse(value)
        if not parsed.hostname:
            return ""
        return f"{parsed.scheme}://{parsed.hostname.rstrip('.').lower()}:{parsed.port or (443 if parsed.scheme == 'https' else 80)}"


@dataclass(frozen=True)
class InferenceResult:
    output: dict[str, Any]
    provider_request_id: str | None
    status: str
    latency_ms: int
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    request_hash: str


class InferenceGateway:
    def __init__(
        self,
        secret_resolver: SecretResolver | None = None,
        endpoint_policy: EndpointPolicy | None = None,
        client: httpx.AsyncClient | None = None,
    ):
        self.secret_resolver = secret_resolver or EnvironmentSecretResolver()
        self.endpoint_policy = endpoint_policy or EndpointPolicy()
        self._client = client

    async def probe(self, profile: InferenceProfile) -> InferenceResult:
        schema = {
            "type": "object",
            "properties": {"protocol": {"type": "string"}, "structured": {"type": "boolean"}},
            "required": ["protocol", "structured"],
            "additionalProperties": False,
        }
        return await self.generate(
            profile,
            instructions="Return protocol='reweft-provider-probe' and structured=true. Do not call tools.",
            evidence={"classification": "synthetic-probe", "contains_customer_data": False},
            schema_name="reweft_provider_probe",
            schema=schema,
        )

    async def generate(
        self,
        profile: InferenceProfile,
        *,
        instructions: str,
        evidence: dict[str, Any],
        schema_name: str,
        schema: dict[str, Any],
    ) -> InferenceResult:
        if profile.provider not in {
            ProviderType.OPENAI,
            ProviderType.OPENAI_COMPATIBLE,
            ProviderType.AZURE_OPENAI,
        }:
            raise InferenceError(
                "PROVIDER_NOT_IMPLEMENTED",
                f"provider {profile.provider.value} is not implemented by this runtime",
            )
        endpoint = self._responses_endpoint(profile)
        self.endpoint_policy.validate(endpoint, profile.endpoint_class)
        payload = {
            "model": profile.model,
            "instructions": instructions,
            "input": [{"role": "user", "content": json.dumps(evidence, separators=(",", ":"), sort_keys=True)}],
            "max_output_tokens": profile.limits.max_output_tokens,
            "store": False,
            "text": {"format": {"type": "json_schema", "name": schema_name, "strict": True, "schema": schema}},
            "tool_choice": "none",
            "metadata": {"component": "reweft", "purpose": schema_name},
        }
        encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        request_hash = hashlib.sha256(encoded).hexdigest()
        headers = {"Content-Type": "application/json"}
        if profile.credential_ref:
            secret = self.secret_resolver.resolve(profile.credential_ref)
            if profile.provider == ProviderType.AZURE_OPENAI:
                headers["api-key"] = secret
            else:
                headers["Authorization"] = f"Bearer {secret}"
        timeout = httpx.Timeout(profile.limits.max_wall_time_seconds)
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=timeout, follow_redirects=False)
        started = monotonic()
        try:
            response = await client.post(endpoint, headers=headers, content=encoded)
        except httpx.TimeoutException as exc:
            raise InferenceError("PROVIDER_TIMEOUT", "provider request exceeded the configured deadline", retryable=True) from exc
        except httpx.HTTPError as exc:
            raise InferenceError("PROVIDER_UNAVAILABLE", "provider transport failed", retryable=True) from exc
        finally:
            if owns_client:
                await client.aclose()
        latency_ms = int((monotonic() - started) * 1000)
        if response.status_code >= 400:
            retryable = response.status_code in {408, 409, 429} or response.status_code >= 500
            raise InferenceError("PROVIDER_REJECTED", f"provider returned HTTP {response.status_code}", retryable=retryable)
        try:
            body = response.json()
        except ValueError as exc:
            raise InferenceError("PROVIDER_INVALID_JSON", "provider returned malformed JSON") from exc
        if body.get("status") not in {None, "completed"}:
            reason = (body.get("incomplete_details") or {}).get("reason") or body.get("status")
            raise InferenceError("PROVIDER_INCOMPLETE", f"provider response was not completed: {reason}")
        output_text = body.get("output_text") or self._extract_output_text(body.get("output", []))
        try:
            output = json.loads(output_text)
        except (TypeError, ValueError) as exc:
            raise InferenceError("PROVIDER_SCHEMA_INVALID", "provider output was not structured JSON") from exc
        self._validate_schema(output, schema)
        usage = body.get("usage") or {}
        return InferenceResult(
            output=output,
            provider_request_id=body.get("id"),
            status="completed",
            latency_ms=latency_ms,
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            total_tokens=usage.get("total_tokens"),
            request_hash=request_hash,
        )

    @staticmethod
    def _validate_schema(output: Any, schema: dict[str, Any]) -> None:
        """Validate the strict object subset used by Reweft response contracts.

        Provider-side structured output is a constraint, not a trust boundary. The
        gateway independently checks required fields, primitive/container types and
        additional-properties denial before persisted output reaches an agent.
        """
        expected_types = {
            "object": dict,
            "array": list,
            "string": str,
            "boolean": bool,
            "integer": int,
            "number": (int, float),
            "null": type(None),
        }

        def check(value: Any, contract: dict[str, Any], path: str) -> None:
            declared = contract.get("type")
            choices = declared if isinstance(declared, list) else [declared] if declared else []
            if choices and not any(isinstance(value, expected_types[item]) and not (item in {"integer", "number"} and isinstance(value, bool)) for item in choices if item in expected_types):
                raise InferenceError("PROVIDER_SCHEMA_INVALID", f"provider output did not match the response contract at {path}")
            if isinstance(value, dict):
                properties = contract.get("properties") or {}
                missing = [key for key in contract.get("required", []) if key not in value]
                if missing:
                    raise InferenceError("PROVIDER_SCHEMA_INVALID", f"provider output omitted required fields at {path}")
                if contract.get("additionalProperties") is False and any(key not in properties for key in value):
                    raise InferenceError("PROVIDER_SCHEMA_INVALID", f"provider output added unrecognized fields at {path}")
                for key, item in value.items():
                    if key in properties:
                        check(item, properties[key], f"{path}.{key}")
            elif isinstance(value, list) and isinstance(contract.get("items"), dict):
                for index, item in enumerate(value):
                    check(item, contract["items"], f"{path}[{index}]")

        check(output, schema, "$")

    @staticmethod
    def _extract_output_text(items: list[dict[str, Any]]) -> str | None:
        for item in items:
            if item.get("type") != "message":
                continue
            for content in item.get("content", []):
                if content.get("type") == "output_text":
                    return content.get("text")
        return None

    @staticmethod
    def _responses_endpoint(profile: InferenceProfile) -> str:
        if profile.provider == ProviderType.OPENAI and not profile.base_url:
            base = "https://api.openai.com/v1"
        elif profile.base_url:
            base = str(profile.base_url).rstrip("/")
        else:
            raise InferenceError("ENDPOINT_REQUIRED", "provider base URL is required")
        if base.endswith("/responses"):
            return base
        if base.endswith("/v1"):
            return f"{base}/responses"
        return f"{base}/v1/responses"
