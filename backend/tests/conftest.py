from __future__ import annotations

from pathlib import Path

import pytest

from reweft.api.app import create_app


@pytest.fixture()
def app(tmp_path: Path):
    return create_app(
        database_path=tmp_path / "test.db",
        bootstrap_token="bootstrap-token-that-is-long-enough-for-tests",
        permit_signing_key=b"test-permit-signing-key-32-bytes!!",
    )

