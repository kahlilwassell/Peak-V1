"""
Postgres integration tests.

These run against a real Postgres instance so we exercise the production code
path: psycopg3 connections, the ``?`` -> ``%s`` parameter rewrite in
``app.db.execute``, and the DDL transaction semantics in ``init_db``.

The SQLite test suite cannot catch regressions in any of the above.

Skipped automatically when ``PEAK_POSTGRES_TEST_URL`` is not set, so local
``pytest`` runs on machines without Postgres stay green. CI provides the
env var via the ``test-postgres`` job in ``.github/workflows/ci.yml``.

Run locally with:

    PEAK_POSTGRES_TEST_URL=postgresql://peak:peak@localhost:5432/peak_test \
        pytest tests/test_postgres_integration.py
"""

import importlib
import os
import sys
from contextlib import closing
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


PG_URL = os.getenv("PEAK_POSTGRES_TEST_URL")

pytestmark = pytest.mark.skipif(
    not PG_URL,
    reason="PEAK_POSTGRES_TEST_URL is not set; skipping Postgres integration tests.",
)


def _reset_schema() -> None:
    """Drop every table the app owns so each test starts from a clean slate."""
    import psycopg

    with closing(psycopg.connect(PG_URL)) as connection:
        connection.execute(
            """
            DROP TABLE IF EXISTS
                running_plans,
                fueling_plans,
                strava_connections,
                workouts,
                users
            CASCADE
            """
        )
        connection.commit()


@pytest.fixture
def pg_client(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", PG_URL)
    monkeypatch.delenv("PEAK_DB_PATH", raising=False)

    _reset_schema()

    # Reload the app modules so they pick up the new env. Without this,
    # a prior test that imported app.main with DATABASE_URL unset would
    # leave the module-level app bound to the SQLite code path.
    for module_name in ("app.main", "app.db"):
        if module_name in sys.modules:
            importlib.reload(sys.modules[module_name])

    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        yield client


def test_init_db_is_idempotent_on_postgres(pg_client):
    """``init_db`` must be safe to call repeatedly on Postgres.

    Regression guard for the bug where a failed ``ALTER TABLE ADD COLUMN``
    marked the psycopg3 transaction as aborted and every subsequent
    statement on that connection raised ``current transaction is aborted,
    commands ignored until end of transaction block``.

    The lifespan handler calls ``init_db`` on startup, so this effectively
    asserts the second boot against the same Postgres database works.
    """
    from app.db import init_db

    init_db()
    init_db()  # must not raise

    # Sanity check: the users table is usable after the double-init.
    response = pg_client.get("/health")
    assert response.status_code == 200


def test_user_create_and_read_round_trip(pg_client):
    """Proves the ?->%s rewrite and dict_row factory work end-to-end."""
    email = "pg-tester@peak.local"
    password = "super-secret"
    payload = {
        "name": "Postgres Tester",
        "email": email,
        "password": password,
        "dob": "1990-01-01",
        "height": 180,
        "weight": 75,
        "is_male": True,
    }
    create = pg_client.post("/users", json=payload)
    assert create.status_code == 201, create.text
    user_id = create.json()["id"]

    login = pg_client.post("/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    read = pg_client.get("/users/{0}".format(user_id), headers=headers)
    assert read.status_code == 200, read.text
    body = read.json()
    assert body["email"] == email
    assert body["height"] == 180
    assert body["is_male"] is True


def test_duplicate_email_maps_to_conflict_on_postgres(pg_client):
    """INTEGRITY_ERRORS must include psycopg.IntegrityError so uniqueness
    violations surface as 409 rather than 500."""
    payload = {
        "name": "Dupe",
        "email": "dupe@peak.local",
        "password": "x",
        "dob": "1990-01-01",
        "height": 180,
        "weight": 75,
        "is_male": True,
    }
    first = pg_client.post("/users", json=payload)
    assert first.status_code == 201, first.text

    second = pg_client.post("/users", json=payload)
    assert second.status_code == 409, second.text
