from __future__ import annotations

import argparse
import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import psycopg
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from temporalio.client import Client
from temporalio.worker import Worker

from reweft.orchestration.activities import collect_source_operation_activity
from reweft.persistence import Database


async def run_worker() -> None:
    client = await Client.connect(os.getenv("TEMPORAL_ADDRESS", "127.0.0.1:7233"))
    with ThreadPoolExecutor(max_workers=4, thread_name_prefix="reweft-collector") as executor:
        async with Worker(
            client, task_queue=os.getenv("REWEFT_TEMPORAL_TASK_QUEUE", "collector"),
            activities=[collect_source_operation_activity], activity_executor=executor,
        ):
            await asyncio.Event().wait()


async def health_check() -> None:
    await asyncio.wait_for(Client.connect(os.environ["TEMPORAL_ADDRESS"]), timeout=3)
    database = Database(os.environ["DATABASE_URL"])
    with database.connect() as connection:
        assert connection.execute("SELECT 1").fetchone()[0] == 1
    key = serialization.load_pem_public_key(Path(os.environ["REWEFT_PERMIT_VERIFICATION_KEY_FILE"]).read_bytes())
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError("permit verification key is not Ed25519")
    artifact_root = Path(os.environ["REWEFT_ARTIFACT_ROOT"])
    if not artifact_root.is_dir() or not os.access(artifact_root, os.R_OK | os.X_OK):
        raise ValueError("artifact root is not readable")
    with psycopg.connect(os.environ["REWEFT_SOURCE_DSN"], connect_timeout=2, autocommit=False) as source:
        with source.transaction():
            source.execute("SET TRANSACTION READ ONLY")
            schema = source.execute(
                "SELECT 1 FROM pg_catalog.pg_namespace WHERE nspname=%s",
                (os.environ["REWEFT_SOURCE_SCHEMA"],),
            ).fetchone()
            if not schema:
                raise ValueError("configured source schema is unavailable")


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--health-check", action="store_true")
    args = parser.parse_args()
    if args.health_check:
        key = Path(os.getenv("REWEFT_PERMIT_VERIFICATION_KEY_FILE", ""))
        required = ("TEMPORAL_ADDRESS", "DATABASE_URL", "REWEFT_COLLECTOR_SERVICE_TOKEN", "REWEFT_SOURCE_DSN", "REWEFT_SOURCE_SCHEMA", "REWEFT_ARTIFACT_ROOT")
        if any(not os.getenv(name) for name in required) or not key.is_file():
            raise SystemExit(1)
        asyncio.run(health_check()); return
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
