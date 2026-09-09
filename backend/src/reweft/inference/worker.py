from __future__ import annotations

import argparse
import asyncio
import os
import socket
import ssl
from urllib.parse import urlparse

from temporalio.client import Client
from temporalio.worker import Worker

from reweft.domain.models import EndpointClass
from reweft.inference.gateway import EndpointPolicy, InferenceGateway
from reweft.orchestration.activities import _environment_profile, invoke_inference
from reweft.orchestration.models import InferenceActivityInput
from reweft.persistence import Database


async def run_worker() -> None:
    client = await Client.connect(os.getenv("TEMPORAL_ADDRESS", "127.0.0.1:7233"))
    async with Worker(client, task_queue=os.getenv("REWEFT_TEMPORAL_TASK_QUEUE", "inference"), activities=[invoke_inference]):
        await asyncio.Event().wait()


async def health_check() -> None:
    await asyncio.wait_for(Client.connect(os.environ["TEMPORAL_ADDRESS"]), timeout=3)
    database = Database(os.environ["DATABASE_URL"])
    with database.connect() as connection:
        assert connection.execute("SELECT 1").fetchone()[0] == 1
    base = os.environ["REWEFT_INFERENCE_BASE_URL"]
    profile = _environment_profile(InferenceActivityInput("00000000-0000-0000-0000-000000000000", None, None, {}))
    endpoint = InferenceGateway._responses_endpoint(profile)
    EndpointPolicy({base}).validate(endpoint, EndpointClass.PUBLIC if base.startswith("https://") else EndpointClass.LOCAL)
    parsed = urlparse(endpoint)
    with socket.create_connection((parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80)), timeout=2) as connection:
        if parsed.scheme == "https":
            context = ssl.create_default_context()
            with context.wrap_socket(connection, server_hostname=parsed.hostname):
                pass


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--health-check", action="store_true")
    args = parser.parse_args()
    if args.health_check:
        if not os.getenv("TEMPORAL_ADDRESS") or not os.getenv("DATABASE_URL") or not os.getenv("REWEFT_INFERENCE_BASE_URL"):
            raise SystemExit(1)
        asyncio.run(health_check()); return
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
