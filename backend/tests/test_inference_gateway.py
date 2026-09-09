from __future__ import annotations

import json
from uuid import uuid4

import httpx
import pytest

from reweft.domain.models import EndpointClass, InferenceProfile, ProviderType
from reweft.inference import EndpointPolicy, InferenceError, InferenceGateway


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def deterministic_provider_dns(monkeypatch):
    original = __import__("socket").getaddrinfo

    def resolve(host, port, *args, **kwargs):
        if host == "provider.test":
            return [(2, 1, 6, "", ("127.0.0.42", port))]
        return original(host, port, *args, **kwargs)

    monkeypatch.setattr("socket.getaddrinfo", resolve)


class StaticSecret:
    def resolve(self, reference: str) -> str:
        assert reference == "secret://inference/test"
        return "canary-provider-secret"


def profile(**updates):
    values = {
        "workspace_id": uuid4(),
        "name": "Deterministic contract test",
        "provider": ProviderType.OPENAI_COMPATIBLE,
        "endpoint_class": EndpointClass.LOCAL,
        "model": "reweft-deterministic-test",
        "base_url": "http://provider.test:8090/v1",
        "credential_ref": "secret://inference/test",
        "allowed_data_classes": {"metadata"},
    }
    values.update(updates)
    return InferenceProfile(**values)


@pytest.mark.anyio
async def test_responses_transport_uses_structured_output_and_redacts_secret():
    observed = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        observed["headers"] = dict(request.headers)
        observed["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "id": "resp_test",
                "status": "completed",
                "output_text": json.dumps({"protocol": "reweft-provider-probe", "structured": True}),
                "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    gateway = InferenceGateway(
        StaticSecret(),
        EndpointPolicy({"http://provider.test:8090"}),
        client,
    )
    result = await gateway.probe(profile())
    await client.aclose()
    assert result.output["structured"] is True
    assert result.total_tokens == 15
    assert observed["payload"]["store"] is False
    assert observed["payload"]["tool_choice"] == "none"
    assert observed["payload"]["text"]["format"]["type"] == "json_schema"
    assert observed["headers"]["authorization"] == "Bearer canary-provider-secret"
    assert "canary-provider-secret" not in json.dumps(result.__dict__)


@pytest.mark.anyio
async def test_malformed_and_failed_provider_outputs_are_bounded():
    async def malformed(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id": "bad", "status": "completed", "output_text": "not-json"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(malformed))
    gateway = InferenceGateway(StaticSecret(), EndpointPolicy({"http://provider.test:8090"}), client)
    with pytest.raises(InferenceError) as raised:
        await gateway.probe(profile())
    assert raised.value.code == "PROVIDER_SCHEMA_INVALID"
    await client.aclose()


def test_endpoint_policy_blocks_metadata_and_unconfigured_private_hosts(monkeypatch):
    policy = EndpointPolicy({"http://provider.test:8090"})
    with pytest.raises(InferenceError) as metadata:
        policy.validate("http://169.254.169.254/latest/meta-data", EndpointClass.LOCAL)
    assert metadata.value.code == "ENDPOINT_FORBIDDEN"
    with pytest.raises(InferenceError) as private:
        policy.validate("http://127.0.0.1:8000/v1/responses", EndpointClass.LOCAL)
    assert private.value.code == "PRIVATE_ENDPOINT_NOT_ALLOWED"
