import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("PEAK_DB_PATH", str(db_path))

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


def create_user(
    client,
    *,
    name="Kahlil",
    email="kahlil@example.com",
    password="test-password",
    dob="1994-03-15",
    height=178,
    weight=72,
    is_male=True,
):
    response = client.post(
        "/users",
        json={
            "name": name,
            "email": email,
            "password": password,
            "dob": dob,
            "height": height,
            "weight": weight,
            "is_male": is_male,
        },
    )
    assert response.status_code == 201
    return response.json()


def create_workout(client, user_id, *, activity_id="123456789"):
    response = client.post(
        f"/users/{user_id}/workouts",
        json={
            "strava_activity_id": activity_id,
            "name": "Morning Run",
            "sport_type": "Run",
            "start_date": "2026-03-28T06:30:00Z",
            "distance_meters": 10000,
            "moving_time_seconds": 2820,
            "calories": 720,
            "raw_data": {"average_heartrate": 154},
        },
    )
    assert response.status_code == 201
    return response.json()


def test_health_check(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "database": "ok"}


def test_root_reports_database_backend_without_exposing_path(client):
    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["database_backend"] == "sqlite"
    assert "database_path" not in response.json()


def test_create_get_and_list_users(client):
    created = create_user(client)

    get_response = client.get(f"/users/{created['id']}")
    list_response = client.get("/users")

    assert get_response.status_code == 200
    assert get_response.json()["email"] == "kahlil@example.com"
    assert get_response.json()["dob"] == "1994-03-15"
    assert get_response.json()["height"] == 178
    assert get_response.json()["weight"] == 72
    assert get_response.json()["is_male"] is True
    assert "password" not in get_response.json()
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1
    assert list_response.json()[0]["id"] == created["id"]
    assert list_response.json()[0]["dob"] == "1994-03-15"


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
    assert response.json()["detail"] == "That Strava activity is already stored for this user."


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
    assert response.json()["detail"] == "Workout does not belong to this user."


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
