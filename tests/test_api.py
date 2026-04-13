import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client(tmp_path, monkeypatch):
    """Isolated TestClient with a fresh SQLite DB per test."""
    db_path = tmp_path / "test.db"
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("PEAK_DB_PATH", str(db_path))

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def testing_client(tmp_path, monkeypatch):
    """Client with PEAK_TESTING=true so the /test/reset endpoint is enabled."""
    db_path = tmp_path / "test.db"
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("PEAK_DB_PATH", str(db_path))
    monkeypatch.setenv("PEAK_TESTING", "true")

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DEFAULT_USER_PAYLOAD = {
    "name": "Kahlil Gibran",
    "email": "kahlil@example.com",
    "password": "hunter2",
    "dob": "1990-05-15",
    "height": 178,
    "weight": 75,
    "is_male": True,
}

DEFAULT_WORKOUT_PAYLOAD = {
    "strava_activity_id": "123456789",
    "name": "Morning Run",
    "sport_type": "Run",
    "start_date": "2026-03-28T06:30:00Z",
    "distance_meters": 10000,
    "moving_time_seconds": 2820,
    "calories": 720,
    "raw_data": {"average_heartrate": 154},
}


def create_user(client, *, email="kahlil@example.com", **overrides):
    payload = {**DEFAULT_USER_PAYLOAD, "email": email, **overrides}
    response = client.post("/users", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def create_workout(client, user_id, *, activity_id="123456789", **overrides):
    payload = {**DEFAULT_WORKOUT_PAYLOAD, "strava_activity_id": activity_id, **overrides}
    response = client.post(f"/users/{user_id}/workouts", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------

def test_health_check(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "database": "ok"}


def test_root_reports_database_backend_without_exposing_path(client):
    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["database_backend"] == "sqlite"
    assert "database_path" not in response.json()


# ---------------------------------------------------------------------------
# Test reset endpoint
# ---------------------------------------------------------------------------

def test_reset_forbidden_without_testing_flag(client):
    """Ensure /test/reset returns 403 when PEAK_TESTING is not set."""
    response = client.post("/test/reset")

    assert response.status_code == 403
    assert "testing mode" in response.json()["detail"]


def test_reset_wipes_all_data(testing_client):
    """After a reset, previously created users are gone."""
    create_user(testing_client)
    assert len(testing_client.get("/users").json()) == 1

    reset = testing_client.post("/test/reset")
    assert reset.status_code == 204

    assert testing_client.get("/users").json() == []


def test_reset_allows_reuse_of_same_email(testing_client):
    """After a reset, the unique email constraint is lifted — same email can be reused."""
    create_user(testing_client, email="repeat@example.com")

    testing_client.post("/test/reset")

    # Should succeed, not conflict
    user = create_user(testing_client, email="repeat@example.com")
    assert user["email"] == "repeat@example.com"


def test_reset_reinitialises_schema(testing_client):
    """After a reset the schema is fully intact — all tables exist."""
    testing_client.post("/test/reset")

    # A fresh user create confirms the users table is healthy
    user = create_user(testing_client)
    assert user["id"]

    # A workout create confirms the workouts table + FK are healthy
    workout = create_workout(testing_client, user["id"])
    assert workout["id"]


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

def test_create_user_returns_all_fields(client):
    response = client.post("/users", json=DEFAULT_USER_PAYLOAD)

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Kahlil Gibran"
    assert body["email"] == "kahlil@example.com"
    assert body["dob"] == "1990-05-15"
    assert body["height"] == 178
    assert body["weight"] == 75
    assert body["is_male"] is True
    assert "id" in body
    assert "created_at" in body
    # Password must not be returned
    assert "password" not in body


def test_create_user_normalises_email_to_lowercase(client):
    response = client.post(
        "/users",
        json={**DEFAULT_USER_PAYLOAD, "email": "UPPER@EXAMPLE.COM"},
    )

    assert response.status_code == 201
    assert response.json()["email"] == "upper@example.com"


def test_duplicate_email_returns_conflict(client):
    create_user(client)

    response = client.post("/users", json=DEFAULT_USER_PAYLOAD)

    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


def test_create_user_rejects_missing_required_fields(client):
    """All of name, email, password, dob, height, weight, is_male are required."""
    for missing_field in ("name", "email", "password", "dob", "height", "weight", "is_male"):
        payload = {k: v for k, v in DEFAULT_USER_PAYLOAD.items() if k != missing_field}
        response = client.post("/users", json=payload)
        assert response.status_code == 422, f"Expected 422 when '{missing_field}' is missing"


def test_create_user_rejects_empty_name(client):
    response = client.post("/users", json={**DEFAULT_USER_PAYLOAD, "name": "   "})

    assert response.status_code == 400


def test_get_user_returns_correct_profile(client):
    created = create_user(client)

    response = client.get(f"/users/{created['id']}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == created["id"]
    assert body["height"] == 178
    assert body["weight"] == 75
    assert body["is_male"] is True


def test_get_unknown_user_returns_404(client):
    response = client.get("/users/does-not-exist")

    assert response.status_code == 404


def test_list_users_includes_profile_fields(client):
    create_user(client)

    response = client.get("/users")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["height"] == 178
    assert body[0]["weight"] == 75
    assert body[0]["is_male"] is True
    assert "password" not in body[0]


def test_female_user_stores_is_male_false(client):
    response = client.post(
        "/users",
        json={**DEFAULT_USER_PAYLOAD, "is_male": False, "email": "jane@example.com"},
    )

    assert response.status_code == 201
    assert response.json()["is_male"] is False


# ---------------------------------------------------------------------------
# Workouts
# ---------------------------------------------------------------------------

def test_create_get_and_list_workouts(client):
    user = create_user(client)
    workout = create_workout(client, user["id"])

    get_response = client.get(f"/workouts/{workout['id']}")
    list_response = client.get(f"/users/{user['id']}/workouts")

    assert get_response.status_code == 200
    assert get_response.json()["source"] == "strava"
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1
    assert list_response.json()[0]["strava_activity_id"] == "123456789"


def test_duplicate_strava_activity_returns_conflict(client):
    user = create_user(client)
    create_workout(client, user["id"], activity_id="dup-1")

    response = client.post(
        f"/users/{user['id']}/workouts",
        json={
            "strava_activity_id": "dup-1",
            "name": "Evening Run",
            "sport_type": "Run",
            "start_date": "2026-03-28T18:30:00Z",
        },
    )

    assert response.status_code == 409
    assert "already stored" in response.json()["detail"]


def test_workout_on_unknown_user_returns_404(client):
    response = client.post(
        "/users/ghost/workouts",
        json={**DEFAULT_WORKOUT_PAYLOAD},
    )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Fueling plans
# ---------------------------------------------------------------------------

def test_create_get_and_list_fueling_plans(client):
    user = create_user(client)
    workout = create_workout(client, user["id"])

    create_response = client.post(
        f"/users/{user['id']}/fueling-plans",
        json={
            "workout_id": workout["id"],
            "goal": "Long run fueling",
            "carbs_per_hour": 75,
            "hydration_ml_per_hour": 600,
            "sodium_mg_per_hour": 700,
            "notes": "Start at 20 minutes, then every 30 minutes.",
        },
    )
    plan = create_response.json()
    get_response = client.get(f"/fueling-plans/{plan['id']}")
    list_response = client.get(f"/users/{user['id']}/fueling-plans")

    assert create_response.status_code == 201
    assert get_response.status_code == 200
    assert get_response.json()["goal"] == "Long run fueling"
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1
    assert list_response.json()[0]["workout_id"] == workout["id"]


def test_fueling_plan_rejects_other_users_workout(client):
    user_one = create_user(client, email="user-one@example.com")
    user_two = create_user(client, email="user-two@example.com")
    workout = create_workout(client, user_one["id"], activity_id="foreign-workout")

    response = client.post(
        f"/users/{user_two['id']}/fueling-plans",
        json={
            "workout_id": workout["id"],
            "goal": "Invalid plan",
        },
    )

    assert response.status_code == 400
    assert "does not belong" in response.json()["detail"]


def test_fueling_plan_without_workout_attachment(client):
    """A plan can be created without linking it to a specific workout."""
    user = create_user(client)

    response = client.post(
        f"/users/{user['id']}/fueling-plans",
        json={"goal": "General endurance fueling", "carbs_per_hour": 60},
    )

    assert response.status_code == 201
    assert response.json()["workout_id"] is None


# ---------------------------------------------------------------------------
# Schema / infrastructure
# ---------------------------------------------------------------------------

def test_init_db_creates_strava_connections_table(tmp_path, monkeypatch):
    db_path = tmp_path / "schema-test.db"
    monkeypatch.setenv("PEAK_DB_PATH", str(db_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)

    import app.db as db_module

    db_module.init_db()

    with db_module.get_connection() as connection:
        row = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name = 'strava_connections'
            """
        ).fetchone()

    assert row is not None
    assert row["name"] == "strava_connections"


def test_database_backend_prefers_database_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://peak:secret@postgres.railway.internal:5432/railway")
    monkeypatch.delenv("PEAK_DB_PATH", raising=False)

    import app.db as db_module

    assert db_module.get_database_backend() == "postgres"
