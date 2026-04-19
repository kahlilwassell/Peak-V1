from pathlib import Path
from types import SimpleNamespace
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from scripts import seed_smoke_data


def test_smoke_seed_script_creates_missing_entities(monkeypatch, capsys):
    base_url = "https://peak-v1-production.up.railway.app"
    state = {
        "user": None,
        "workout": None,
        "plan": None,
        "posts": [],
    }

    def fake_request_json(*, method, url, headers, expected_statuses, payload=None):
        path = url.removeprefix(base_url)

        if path == "/health" and method == "GET":
            return {"status": "healthy", "database": "ok"}
        if path == "/" and method == "GET":
            return {"message": "Peak V1 API", "docs": "/docs", "database_backend": "postgres"}

        if path == "/users" and method == "POST":
            state["posts"].append(path)
            state["user"] = {
                "id": "user-1",
                "name": payload["name"],
                "email": payload["email"].lower(),
                "created_at": "2026-03-31T12:00:00Z",
                "dob": payload["dob"],
                "height": payload["height"],
                "weight": payload["weight"],
                "is_male": payload["is_male"],
            }
            return state["user"]
        if path == "/auth/login" and method == "POST":
            assert payload == {
                "email": "smoke-test@peak.local",
                "password": seed_smoke_data.DEFAULT_PASSWORD,
            }
            return {
                **state["user"],
                "access_token": "smoke-token",
                "token_type": "bearer",
                "expires_in": 604800,
            }
        if path == "/auth/me" and method == "GET":
            assert headers["Authorization"] == "Bearer smoke-token"
            return state["user"]

        if path == "/users/user-1/workouts" and method == "GET":
            assert headers["Authorization"] == "Bearer smoke-token"
            return [state["workout"]] if state["workout"] else []
        if path == "/users/user-1/workouts" and method == "POST":
            assert headers["Authorization"] == "Bearer smoke-token"
            state["posts"].append(path)
            state["workout"] = {
                "id": "workout-1",
                "user_id": "user-1",
                "source": "strava",
                "strava_activity_id": payload["strava_activity_id"],
                "name": payload["name"],
                "sport_type": payload["sport_type"],
                "start_date": payload["start_date"],
                "distance_meters": payload["distance_meters"],
                "moving_time_seconds": payload["moving_time_seconds"],
                "calories": payload["calories"],
                "notes": payload["notes"],
                "raw_data": payload["raw_data"],
                "created_at": "2026-03-31T12:00:00Z",
            }
            return state["workout"]
        if path == "/workouts/workout-1" and method == "GET":
            assert headers["Authorization"] == "Bearer smoke-token"
            return state["workout"]

        if path == "/users/user-1/fueling-plans" and method == "GET":
            assert headers["Authorization"] == "Bearer smoke-token"
            return [state["plan"]] if state["plan"] else []
        if path == "/users/user-1/fueling-plans" and method == "POST":
            assert headers["Authorization"] == "Bearer smoke-token"
            state["posts"].append(path)
            state["plan"] = {
                "id": "plan-1",
                "user_id": "user-1",
                "workout_id": payload["workout_id"],
                "goal": payload["goal"],
                "carbs_per_hour": payload["carbs_per_hour"],
                "hydration_ml_per_hour": payload["hydration_ml_per_hour"],
                "sodium_mg_per_hour": payload["sodium_mg_per_hour"],
                "notes": payload["notes"],
                "created_at": "2026-03-31T12:00:00Z",
            }
            return state["plan"]
        if path == "/fueling-plans/plan-1" and method == "GET":
            assert headers["Authorization"] == "Bearer smoke-token"
            return state["plan"]

        raise AssertionError(f"Unexpected request: {method} {url}")

    monkeypatch.setattr(seed_smoke_data, "request_json", fake_request_json)
    monkeypatch.setattr(
        seed_smoke_data,
        "parse_args",
        lambda: SimpleNamespace(
            base_url=base_url,
            email="smoke-test@peak.local",
            name="Peak Smoke Test",
            activity_id="peak-smoke-activity",
            goal="Smoke test fueling plan",
            api_key=None,
        ),
    )

    exit_code = seed_smoke_data.main()
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Smoke test succeeded." in captured.out
    assert state["user"] == {
        "id": "user-1",
        "name": "Peak Smoke Test",
        "email": "smoke-test@peak.local",
        "created_at": "2026-03-31T12:00:00Z",
        "dob": seed_smoke_data.DEFAULT_DOB,
        "height": seed_smoke_data.DEFAULT_HEIGHT,
        "weight": seed_smoke_data.DEFAULT_WEIGHT,
        "is_male": seed_smoke_data.DEFAULT_IS_MALE,
    }
    assert state["posts"] == [
        "/users",
        "/users/user-1/workouts",
        "/users/user-1/fueling-plans",
    ]
