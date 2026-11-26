from __future__ import annotations

from pathlib import Path

import pytest

from rerate import runner
from rerate.generator import generate


@pytest.fixture(scope="session")
def seed7(tmp_path_factory) -> dict:
    """Seed 7 raw data and one built database, shared by the acceptance tests."""
    base = tmp_path_factory.mktemp("seed7")
    raw = base / "raw"
    counts = generate(7, raw)
    db = base / "rerate.duckdb"
    built, failures = runner.build(raw, db)
    return {"raw": raw, "db": db, "counts": counts, "built": built, "failures": failures}


@pytest.fixture()
def sql_dir() -> Path:
    return runner.default_sql_dir()
