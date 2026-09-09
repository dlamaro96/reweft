from __future__ import annotations

import argparse
import asyncio
import os
from concurrent.futures import ThreadPoolExecutor

from temporalio.client import Client
from temporalio.worker import Worker

from .activities import analyze_run, design_modernization, finalize_run, set_run_state, validate_generated_target
from reweft.persistence import Database
from .workflows import AssessmentWorkflow, ProviderTestWorkflow, SourceTestWorkflow


async def run_worker() -> None:
    client = await Client.connect(os.getenv("TEMPORAL_ADDRESS", "127.0.0.1:7233"))
    with ThreadPoolExecutor(max_workers=4, thread_name_prefix="reweft-analysis") as executor:
        async with Worker(
            client, task_queue=os.getenv("REWEFT_TEMPORAL_TASK_QUEUE", "analysis"),
            workflows=[AssessmentWorkflow, SourceTestWorkflow, ProviderTestWorkflow],
            activities=[set_run_state, analyze_run, design_modernization, validate_generated_target, finalize_run],
            activity_executor=executor,
        ):
            await asyncio.Event().wait()


async def health_check() -> None:
    address = os.environ["TEMPORAL_ADDRESS"]
    await asyncio.wait_for(Client.connect(address), timeout=3)
    database = Database(os.getenv("DATABASE_URL") or os.environ["REWEFT_DATABASE_PATH"])
    with database.connect() as connection:
        assert connection.execute("SELECT 1").fetchone()[0] == 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--health-check", action="store_true")
    args = parser.parse_args()
    if args.health_check:
        if not os.getenv("TEMPORAL_ADDRESS") or not (os.getenv("DATABASE_URL") or os.getenv("REWEFT_DATABASE_PATH")):
            raise SystemExit(1)
        asyncio.run(health_check()); return
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
