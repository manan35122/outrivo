"""Test setup.

DB tests need a throwaway Postgres database. Point TEST_DATABASE_URL at one whose
name contains "test" (the tests TRUNCATE tables). Without it, DB tests are skipped.

    TEST_DATABASE_URL=postgresql://user:pass@localhost:5432/outrivo_test python -m pytest
"""

import os
from pathlib import Path

import pytest

TEST_DB = os.environ.get("TEST_DATABASE_URL", "")
if TEST_DB:
    db_name = TEST_DB.rsplit("/", 1)[-1].split("?")[0]
    if "test" not in db_name:
        pytest.exit(f"Refusing to run: database name '{db_name}' must contain 'test'.", returncode=2)
    os.environ["DATABASE_URL"] = TEST_DB

SCHEMA = Path(__file__).resolve().parent.parent / "schema.sql"
TABLES = "leads, outreach, pending_actions, user_memories, usage_log"
CHECKPOINT_TABLES = ("checkpoints", "checkpoint_blobs", "checkpoint_writes")


@pytest.fixture(scope="session")
def db():
    if not TEST_DB:
        pytest.skip("TEST_DATABASE_URL not set")
    import psycopg
    from langgraph.checkpoint.postgres import PostgresSaver

    with psycopg.connect(TEST_DB, autocommit=True) as conn:
        conn.execute(SCHEMA.read_text(encoding="utf-8"))
    from app.db import get_pool

    PostgresSaver(get_pool()).setup()
    return TEST_DB


@pytest.fixture
def clean_db(db):
    import psycopg

    with psycopg.connect(db, autocommit=True) as conn:
        conn.execute(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE")
        for table in CHECKPOINT_TABLES:
            try:
                conn.execute(f"TRUNCATE {table}")
            except psycopg.errors.UndefinedTable:
                pass
    yield
