import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

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
    db_path = tmp_path / "test.db"
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("PEAK_DB_PATH", str(db_path))

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def testing_client(tmp_path, monkeypatch):
    """Client with PEAK_TESTING=true so the /test/reset endpoint is active."""
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


def login_headers(client, *, email="kahlil@example.com", password="test-password"):
    response = client.post(
        "/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def create_workout(client, user_id, *, activity_id="123456789", headers=None):
    if headers is None:
        headers = login_headers(client)
    response = client.post(
        f"/users/{user_id}/workouts",
        headers=headers,
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


# ---------------------------------------------------------------------------
# Infrastructure
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
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://peak:secret@postgres.railway.internal:5432/railway",
    )
    monkeypatch.delenv("PEAK_DB_PATH", raising=False)

    import app.db as db_module

    assert db_module.get_database_backend() == "postgres"


# ---------------------------------------------------------------------------
# Users — happy path
# ---------------------------------------------------------------------------


def test_create_get_user_and_current_user_profile(client):
    created = create_user(client)
    headers = login_headers(client)

    get_response = client.get(f"/users/{created['id']}", headers=headers)
    me_response = client.get("/users/me", headers=headers)

    assert get_response.status_code == 200
    assert get_response.json()["email"] == "kahlil@example.com"
    assert get_response.json()["dob"] == "1994-03-15"
    assert get_response.json()["height"] == 178
    assert get_response.json()["weight"] == 72
    assert get_response.json()["is_male"] is True
    assert "password" not in get_response.json()
    assert me_response.status_code == 200
    assert me_response.json()["id"] == created["id"]
    assert me_response.json()["dob"] == "1994-03-15"
    assert "password" not in me_response.json()


def test_get_users_collection_is_not_supported(client):
    create_user(client)
    headers = login_headers(client)

    response = client.get("/users", headers=headers)

    assert response.status_code == 405


def test_created_at_timestamp_has_no_fractional_seconds(client):
    """Regression: Swift's .iso8601 decoder rejects microseconds like
    '2026-04-14T01:46:52.059007+00:00'. Every created_at we return must be
    whole-second precision, e.g. '2026-04-14T01:46:52+00:00'."""
    user = create_user(client)
    headers = login_headers(client)
    workout = create_workout(client, user["id"], headers=headers)
    plan = client.post(
        f"/users/{user['id']}/fueling-plans",
        headers=headers,
        json={"goal": "Race fuel", "carbs_per_hour": 80},
    ).json()

    for field, value in [
        ("user created_at", user["created_at"]),
        ("workout created_at", workout["created_at"]),
        ("fueling plan created_at", plan["created_at"]),
    ]:
        assert "." not in value, (
            f"{field} contains fractional seconds which Swift cannot parse: {value!r}"
        )


def test_update_user_height_and_weight(client):
    user = create_user(client)
    headers = login_headers(client)

    response = client.patch(
        f"/users/{user['id']}",
        headers=headers,
        json={"height": 185, "weight": 80},
    )

    assert response.status_code == 200
    assert response.json()["height"] == 185
    assert response.json()["weight"] == 80
    # Fields we didn't touch must be unchanged
    assert response.json()["email"] == "kahlil@example.com"
    assert "password" not in response.json()


def test_update_user_password(client):
    user = create_user(client, password="old-password")
    headers = login_headers(client, password="old-password")

    response = client.patch(
        f"/users/{user['id']}",
        headers=headers,
        json={"password": "new-secure-password"},
    )

    assert response.status_code == 200
    assert "password" not in response.json()
    # Other fields intact
    assert response.json()["email"] == "kahlil@example.com"


def test_update_user_empty_body_is_rejected(client):
    user = create_user(client)
    headers = login_headers(client)

    response = client.patch(f"/users/{user['id']}", headers=headers, json={})

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Users — error cases
# ---------------------------------------------------------------------------


def test_duplicate_email_returns_conflict(client):
    create_user(client, email="dup@example.com")

    response = client.post(
        "/users",
        json={
            "name": "Duplicate",
            "email": "dup@example.com",
            "password": "pw",
            "dob": "1990-01-01",
            "height": 170,
            "weight": 65,
            "is_male": False,
        },
    )

    assert response.status_code == 409


def test_get_user_requires_authentication(client):
    response = client.get("/users/does-not-exist")

    assert response.status_code == 401


def test_update_user_requires_authentication(client):
    response = client.patch("/users/does-not-exist", json={"height": 180})

    assert response.status_code == 401


def test_user_scoped_routes_reject_other_users_path(client):
    user_a = create_user(client, email="owner@peak.com")
    user_b = create_user(client, email="other@peak.com")
    headers_a = login_headers(client, email="owner@peak.com")

    checks = [
        ("GET", f"/users/{user_b['id']}", None),
        ("PATCH", f"/users/{user_b['id']}", {"height": 181}),
        (
            "POST",
            f"/users/{user_b['id']}/workouts",
            {
                "strava_activity_id": "cross-user-workout",
                "name": "Cross-user workout",
                "start_date": "2026-03-28T06:30:00Z",
            },
        ),
        ("GET", f"/users/{user_b['id']}/workouts", None),
        (
            "POST",
            f"/users/{user_b['id']}/fueling-plans",
            {"goal": "Cross-user fueling"},
        ),
        ("GET", f"/users/{user_b['id']}/fueling-plans", None),
        (
            "POST",
            f"/users/{user_b['id']}/running-plans",
            {
                "planned_at": "2099-06-15T07:30:00+00:00",
                "distance_km": 5.0,
                "speed_kph": 10.0,
            },
        ),
        ("GET", f"/users/{user_b['id']}/running-plans", None),
    ]

    for method, path, payload in checks:
        response = client.request(method, path, headers=headers_a, json=payload)
        assert response.status_code == 403, f"{method} {path} should reject cross-user access"

    assert user_a["id"] != user_b["id"]


def test_password_change_takes_effect_for_login(client):
    """After PATCHing password, the old password must stop working and the new one must work."""
    user = create_user(client, email="pw@peak.com", password="old-password")
    headers = login_headers(client, email="pw@peak.com", password="old-password")

    client.patch(f"/users/{user['id']}", headers=headers, json={"password": "new-password"})

    old = client.post("/auth/login", json={"email": "pw@peak.com", "password": "old-password"})
    new = client.post("/auth/login", json={"email": "pw@peak.com", "password": "new-password"})

    assert old.status_code == 401
    assert new.status_code == 200


# ---------------------------------------------------------------------------
# Workouts — happy path
# ---------------------------------------------------------------------------


def test_create_get_and_list_workouts(client):
    user = create_user(client)
    headers = login_headers(client)
    workout = create_workout(client, user["id"], headers=headers)

    get_response = client.get(f"/workouts/{workout['id']}", headers=headers)
    list_response = client.get(f"/users/{user['id']}/workouts", headers=headers)

    assert get_response.status_code == 200
    assert get_response.json()["source"] == "strava"
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1
    assert list_response.json()[0]["strava_activity_id"] == "123456789"


# ---------------------------------------------------------------------------
# Workouts — error cases
# ---------------------------------------------------------------------------


def test_duplicate_strava_activity_returns_conflict(client):
    user = create_user(client)
    headers = login_headers(client)
    create_workout(client, user["id"], activity_id="dup-1", headers=headers)

    response = client.post(
        f"/users/{user['id']}/workouts",
        headers=headers,
        json={
            "strava_activity_id": "dup-1",
            "name": "Evening Run",
            "sport_type": "Run",
            "start_date": "2026-03-28T18:30:00Z",
        },
    )

    assert response.status_code == 409
    assert (
        response.json()["detail"]
        == "That Strava activity is already stored for this user."
    )


def test_get_workout_requires_authentication(client):
    response = client.get("/workouts/does-not-exist")

    assert response.status_code == 401


def test_list_workouts_requires_authentication(client):
    response = client.get("/users/does-not-exist/workouts")

    assert response.status_code == 401


def test_workout_id_route_rejects_other_users_workout(client):
    user_a = create_user(client, email="a@peak.com")
    user_b = create_user(client, email="b@peak.com")
    headers_a = login_headers(client, email="a@peak.com")
    headers_b = login_headers(client, email="b@peak.com")
    workout = create_workout(
        client,
        user_a["id"],
        activity_id="a-workout",
        headers=headers_a,
    )

    response = client.get(f"/workouts/{workout['id']}", headers=headers_b)

    assert user_b["id"] != user_a["id"]
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Fueling plans — happy path
# ---------------------------------------------------------------------------


def test_create_get_and_list_fueling_plans(client):
    user = create_user(client)
    headers = login_headers(client)
    workout = create_workout(client, user["id"], headers=headers)

    create_response = client.post(
        f"/users/{user['id']}/fueling-plans",
        headers=headers,
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
    get_response = client.get(f"/fueling-plans/{plan['id']}", headers=headers)
    list_response = client.get(f"/users/{user['id']}/fueling-plans", headers=headers)

    assert create_response.status_code == 201
    assert get_response.status_code == 200
    assert get_response.json()["goal"] == "Long run fueling"
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1
    assert list_response.json()[0]["workout_id"] == workout["id"]


def test_fueling_plan_without_workout(client):
    """Fueling plans don't require a workout_id."""
    user = create_user(client)
    headers = login_headers(client)

    response = client.post(
        f"/users/{user['id']}/fueling-plans",
        headers=headers,
        json={"goal": "General nutrition", "carbs_per_hour": 60},
    )

    assert response.status_code == 201
    assert response.json()["workout_id"] is None


# ---------------------------------------------------------------------------
# Fueling plans — error cases
# ---------------------------------------------------------------------------


def test_fueling_plan_rejects_other_users_workout(client):
    user_one = create_user(client, email="user-one@example.com")
    user_two = create_user(client, email="user-two@example.com")
    headers_one = login_headers(client, email="user-one@example.com")
    headers_two = login_headers(client, email="user-two@example.com")
    workout = create_workout(
        client,
        user_one["id"],
        activity_id="foreign-workout",
        headers=headers_one,
    )

    response = client.post(
        f"/users/{user_two['id']}/fueling-plans",
        headers=headers_two,
        json={
            "workout_id": workout["id"],
            "goal": "Invalid plan",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Workout does not belong to this user."


def test_fueling_plan_id_route_rejects_other_users_plan(client):
    user_a = create_user(client, email="fuel-owner@peak.com")
    user_b = create_user(client, email="fuel-other@peak.com")
    headers_a = login_headers(client, email="fuel-owner@peak.com")
    headers_b = login_headers(client, email="fuel-other@peak.com")

    create_response = client.post(
        f"/users/{user_a['id']}/fueling-plans",
        headers=headers_a,
        json={"goal": "Private fueling plan"},
    )
    plan = create_response.json()

    response = client.get(f"/fueling-plans/{plan['id']}", headers=headers_b)

    assert user_a["id"] != user_b["id"]
    assert create_response.status_code == 201
    assert response.status_code == 403


def test_get_fueling_plan_requires_authentication(client):
    response = client.get("/fueling-plans/does-not-exist")

    assert response.status_code == 401


def test_list_fueling_plans_requires_authentication(client):
    response = client.get("/users/does-not-exist/fueling-plans")

    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Running plans
# ---------------------------------------------------------------------------

FUTURE_DATE = "2099-06-15T07:30:00+00:00"


def create_running_plan(
    client,
    user_id,
    *,
    headers=None,
    planned_at=FUTURE_DATE,
    distance_km=10.0,
    speed_kph=12.0,
):
    if headers is None:
        headers = login_headers(client)
    response = client.post(
        f"/users/{user_id}/running-plans",
        headers=headers,
        json={
            "planned_at": planned_at,
            "distance_km": distance_km,
            "speed_kph": speed_kph,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_create_and_list_running_plans(client):
    user = create_user(client)
    headers = login_headers(client)
    plan = create_running_plan(
        client,
        user["id"],
        headers=headers,
        distance_km=21.1,
        speed_kph=11.0,
    )

    assert plan["distance_km"] == 21.1
    assert plan["speed_kph"] == 11.0
    assert plan["user_id"] == user["id"]
    assert "." not in plan["created_at"], "created_at must not have fractional seconds"
    assert "." not in plan["planned_at"], "planned_at must not have fractional seconds"

    list_resp = client.get(f"/users/{user['id']}/running-plans", headers=headers)
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1


def test_running_plans_ordered_by_planned_at_ascending(client):
    user = create_user(client)
    headers = login_headers(client)
    create_running_plan(
        client,
        user["id"],
        headers=headers,
        planned_at="2099-12-01T08:00:00+00:00",
    )
    create_running_plan(
        client,
        user["id"],
        headers=headers,
        planned_at="2099-06-01T06:00:00+00:00",
    )
    create_running_plan(
        client,
        user["id"],
        headers=headers,
        planned_at="2099-09-15T07:00:00+00:00",
    )

    plans = client.get(f"/users/{user['id']}/running-plans", headers=headers).json()
    dates = [p["planned_at"] for p in plans]
    assert dates == sorted(dates)


def test_running_plan_past_date_rejected(client):
    user = create_user(client)
    headers = login_headers(client)

    response = client.post(
        f"/users/{user['id']}/running-plans",
        headers=headers,
        json={
            "planned_at": "2000-01-01T00:00:00+00:00",
            "distance_km": 5.0,
            "speed_kph": 10.0,
        },
    )

    assert response.status_code == 422


def test_running_plan_zero_distance_rejected(client):
    user = create_user(client)
    headers = login_headers(client)

    response = client.post(
        f"/users/{user['id']}/running-plans",
        headers=headers,
        json={"planned_at": FUTURE_DATE, "distance_km": 0.0, "speed_kph": 10.0},
    )

    assert response.status_code == 422


def test_running_plan_requires_authentication(client):
    response = client.post(
        "/users/ghost/running-plans",
        json={"planned_at": FUTURE_DATE, "distance_km": 5.0, "speed_kph": 10.0},
    )

    assert response.status_code == 401


def test_running_plan_with_notes(client):
    user = create_user(client)
    headers = login_headers(client)
    plan = create_running_plan(client, user["id"], headers=headers)

    response = client.post(
        f"/users/{user['id']}/running-plans",
        headers=headers,
        json={
            "planned_at": FUTURE_DATE,
            "distance_km": 5.0,
            "speed_kph": 10.0,
            "notes": "Easy recovery run, keep HR below 140.",
        },
    )

    assert response.status_code == 201
    assert response.json()["notes"] == "Easy recovery run, keep HR below 140."


def test_list_running_plans_requires_authentication(client):
    response = client.get("/users/does-not-exist/running-plans")

    assert response.status_code == 401


def test_running_plan_zero_speed_rejected(client):
    """speed_kph must be > 0 (schema Field gt=0)."""
    user = create_user(client)
    headers = login_headers(client)

    response = client.post(
        f"/users/{user['id']}/running-plans",
        headers=headers,
        json={"planned_at": FUTURE_DATE, "distance_km": 5.0, "speed_kph": 0.0},
    )

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Authentication — login
# ---------------------------------------------------------------------------


def test_login_returns_user_on_valid_credentials(client):
    create_user(client, email="runner@peak.com", password="correct-horse")

    response = client.post(
        "/auth/login",
        json={"email": "runner@peak.com", "password": "correct-horse"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "runner@peak.com"
    assert "password" not in data
    assert "id" in data


def test_login_is_case_insensitive_for_email(client):
    create_user(client, email="runner@peak.com", password="secret")

    response = client.post(
        "/auth/login",
        json={"email": "RUNNER@PEAK.COM", "password": "secret"},
    )

    assert response.status_code == 200
    assert response.json()["email"] == "runner@peak.com"


def test_login_wrong_password_returns_401(client):
    create_user(client, email="runner@peak.com", password="correct")

    response = client.post(
        "/auth/login",
        json={"email": "runner@peak.com", "password": "wrong"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password."


def test_login_unknown_email_returns_401(client):
    response = client.post(
        "/auth/login",
        json={"email": "ghost@nowhere.com", "password": "any"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password."


def test_login_does_not_expose_password_in_response(client):
    create_user(client, email="secure@peak.com", password="topsecret")

    response = client.post(
        "/auth/login",
        json={"email": "secure@peak.com", "password": "topsecret"},
    )

    assert response.status_code == 200
    assert "password" not in response.json()


def test_login_response_created_at_has_no_fractional_seconds(client):
    """Regression: login response must not return microseconds in created_at."""
    create_user(client, email="ts@peak.com", password="pw")

    user = client.post(
        "/auth/login",
        json={"email": "ts@peak.com", "password": "pw"},
    ).json()

    assert "." not in user["created_at"], (
        f"created_at contains fractional seconds which Swift cannot parse: {user['created_at']!r}"
    )


# ---------------------------------------------------------------------------
# Authentication — bearer token
# ---------------------------------------------------------------------------


def test_login_returns_bearer_token_and_auth_me(client):
    create_user(client, email="runner@peak.com", password="secret")

    login_response = client.post(
        "/auth/login",
        json={"email": "runner@peak.com", "password": "secret"},
    )

    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    assert login_response.json()["token_type"] == "bearer"
    assert login_response.json()["expires_in"] > 0

    me_response = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert me_response.status_code == 200
    assert me_response.json()["email"] == "runner@peak.com"
    assert "password" not in me_response.json()


def test_auth_me_requires_valid_bearer_token(client):
    response = client.get("/auth/me")

    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Strava OAuth
# ---------------------------------------------------------------------------


def test_strava_connect_requires_current_user_to_match_path(client, monkeypatch):
    user_one = create_user(client, email="one@peak.com")
    user_two = create_user(client, email="two@peak.com")
    headers = login_headers(client, email="one@peak.com")
    monkeypatch.setenv("STRAVA_CLIENT_ID", "123")
    monkeypatch.setenv("STRAVA_REDIRECT_URI", "https://api.peak.test/strava/oauth/callback")

    response = client.get(
        f"/users/{user_two['id']}/strava/connect",
        headers=headers,
    )

    assert user_one["id"] != user_two["id"]
    assert response.status_code == 403


def test_strava_connect_returns_authorization_url(client, monkeypatch):
    user = create_user(client)
    headers = login_headers(client)
    monkeypatch.setenv("STRAVA_CLIENT_ID", "123")
    monkeypatch.setenv("STRAVA_REDIRECT_URI", "https://api.peak.test/strava/oauth/callback")
    monkeypatch.setenv("STRAVA_SCOPES", "read,activity:read_all")

    response = client.get(f"/users/{user['id']}/strava/connect", headers=headers)

    assert response.status_code == 200
    url = response.json()["authorization_url"]
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    assert parsed.netloc == "www.strava.com"
    assert parsed.path == "/oauth/authorize"
    assert query["client_id"] == ["123"]
    assert query["redirect_uri"] == ["https://api.peak.test/strava/oauth/callback"]
    assert query["scope"] == ["read,activity:read_all"]
    assert query["response_type"] == ["code"]
    assert "state" in query
    assert "client_secret" not in query


def test_strava_oauth_callback_stores_connection_without_exposing_tokens(
    client,
    monkeypatch,
):
    from app.auth import create_oauth_state

    user = create_user(client)
    headers = login_headers(client)
    state = create_oauth_state(user["id"])

    def fake_exchange_code_for_token(code):
        assert code == "oauth-code"
        return {
            "access_token": "strava-access",
            "refresh_token": "strava-refresh",
            "expires_at": 4102444800,
            "athlete": {"id": 987, "username": "peak-runner"},
        }

    monkeypatch.setattr(
        "app.main.exchange_code_for_token",
        fake_exchange_code_for_token,
    )

    callback_response = client.get(
        "/strava/oauth/callback",
        params={
            "code": "oauth-code",
            "scope": "read,activity:read_all",
            "state": state,
        },
    )
    connection_response = client.get(
        f"/users/{user['id']}/strava/connection",
        headers=headers,
    )

    assert callback_response.status_code == 200
    assert callback_response.json()["status"] == "connected"
    assert callback_response.json()["connection"]["strava_athlete_id"] == "987"
    assert "access_token" not in callback_response.json()["connection"]
    assert "refresh_token" not in callback_response.json()["connection"]
    assert connection_response.status_code == 200
    assert connection_response.json()["strava_username"] == "peak-runner"
    assert "access_token" not in connection_response.json()
    assert "refresh_token" not in connection_response.json()


def test_strava_sync_refreshes_token_and_imports_new_workouts(client, monkeypatch):
    from app.auth import create_oauth_state

    user = create_user(client)
    headers = login_headers(client)
    state = create_oauth_state(user["id"])
    seen = {}

    monkeypatch.setattr(
        "app.main.exchange_code_for_token",
        lambda code: {
            "access_token": "old-access",
            "refresh_token": "old-refresh",
            "expires_at": 946684800,
            "athlete": {"id": 987, "username": "peak-runner"},
        },
    )
    client.get(
        "/strava/oauth/callback",
        params={"code": "oauth-code", "scope": "read,activity:read_all", "state": state},
    )

    def fake_refresh_access_token(refresh_token):
        assert refresh_token == "old-refresh"
        return {
            "access_token": "new-access",
            "refresh_token": "new-refresh",
            "expires_at": 4102444800,
        }

    def fake_fetch_athlete_activities(access_token):
        seen["access_token"] = access_token
        return [
            {
                "id": 12345,
                "name": "Imported Run",
                "sport_type": "Run",
                "start_date": "2026-04-01T12:00:00Z",
                "distance": 5000.0,
                "moving_time": 1500,
                "calories": 350,
            }
        ]

    monkeypatch.setattr("app.main.refresh_access_token", fake_refresh_access_token)
    monkeypatch.setattr("app.main.fetch_athlete_activities", fake_fetch_athlete_activities)

    sync_response = client.post(
        f"/users/{user['id']}/strava/sync",
        headers=headers,
    )
    workouts_response = client.get(f"/users/{user['id']}/workouts", headers=headers)

    assert sync_response.status_code == 200
    assert sync_response.json()["imported_workouts"] == 1
    assert seen["access_token"] == "new-access"
    assert workouts_response.status_code == 200
    assert workouts_response.json()[0]["strava_activity_id"] == "12345"
    assert workouts_response.json()[0]["name"] == "Imported Run"


# ---------------------------------------------------------------------------
# Test-reset endpoint
# ---------------------------------------------------------------------------


def test_reset_forbidden_without_env_flag(client):
    """POST /test/reset must return 403 unless PEAK_TESTING=true."""
    response = client.post("/test/reset")

    assert response.status_code == 403


def test_reset_wipes_and_reinitialises_database(testing_client):
    """After a reset, previously created users are gone and new ones can be made."""
    create_user(testing_client, email="before-reset@example.com")
    before_headers = login_headers(testing_client, email="before-reset@example.com")
    before_response = testing_client.get("/users/me", headers=before_headers)
    assert before_response.status_code == 200

    reset_response = testing_client.post("/test/reset")
    assert reset_response.status_code == 204

    stale_response = testing_client.get("/users/me", headers=before_headers)
    assert stale_response.status_code == 401

    # Schema is intact — new registrations work immediately after reset
    create_user(testing_client, email="after-reset@example.com")
    after_headers = login_headers(testing_client, email="after-reset@example.com")
    after_response = testing_client.get("/users/me", headers=after_headers)
    assert after_response.status_code == 200
