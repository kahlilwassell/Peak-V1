#!/usr/bin/env python3
"""Seed and verify a reusable smoke-test user through the API."""

import argparse
import json
import os
import sys
from typing import Any, Dict, Iterable, Optional, Tuple
from urllib import error, request


DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_EMAIL = "smoke-test@peak.local"
DEFAULT_NAME = "Peak Smoke Test"
DEFAULT_PASSWORD = "peak-smoke-password"
DEFAULT_DOB = "1990-01-01"
DEFAULT_HEIGHT = 178
DEFAULT_WEIGHT = 72
DEFAULT_IS_MALE = True
DEFAULT_ACTIVITY_ID = "peak-smoke-activity"
DEFAULT_GOAL = "Smoke test fueling plan"


def build_headers(api_key: Optional[str]) -> Dict[str, str]:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if api_key:
        headers["X-API-Key"] = api_key
    return headers


def request_json(
    *,
    method: str,
    url: str,
    headers: Dict[str, str],
    expected_statuses: Iterable[int],
    payload: Optional[Dict[str, Any]] = None,
) -> Any:
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")

    req = request.Request(url, data=body, method=method, headers=headers)
    try:
        with request.urlopen(req) as response:
            raw = response.read().decode("utf-8")
            if response.status not in expected_statuses:
                raise RuntimeError(
                    f"{method} {url} returned {response.status}, expected {sorted(expected_statuses)}."
                )
            return json.loads(raw) if raw else None
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        if exc.code in expected_statuses:
            return json.loads(detail) if detail else None
        raise RuntimeError(f"{method} {url} failed with {exc.code}: {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"{method} {url} failed: {exc.reason}") from exc


def normalize_base_url(raw_base_url: str) -> str:
    return raw_base_url.rstrip("/")


def find_by(items: Iterable[Dict[str, Any]], key: str, value: Any) -> Optional[Dict[str, Any]]:
    for item in items:
        if item.get(key) == value:
            return item
    return None


def headers_with_bearer_token(headers: Dict[str, str], access_token: str) -> Dict[str, str]:
    authenticated_headers = dict(headers)
    authenticated_headers["Authorization"] = f"Bearer {access_token}"
    return authenticated_headers


def ensure_user(
    base_url: str,
    headers: Dict[str, str],
    name: str,
    email: str,
) -> Tuple[Dict[str, Any], Dict[str, str]]:
    request_json(
        method="POST",
        url=f"{base_url}/users",
        headers=headers,
        expected_statuses={201, 409},
        payload={
            "name": name,
            "email": email,
            "password": DEFAULT_PASSWORD,
            "dob": DEFAULT_DOB,
            "height": DEFAULT_HEIGHT,
            "weight": DEFAULT_WEIGHT,
            "is_male": DEFAULT_IS_MALE,
        },
    )
    login = request_json(
        method="POST",
        url=f"{base_url}/auth/login",
        headers=headers,
        expected_statuses={200},
        payload={"email": email, "password": DEFAULT_PASSWORD},
    )
    authenticated_headers = headers_with_bearer_token(headers, login["access_token"])
    user = request_json(
        method="GET",
        url=f"{base_url}/auth/me",
        headers=authenticated_headers,
        expected_statuses={200},
    )
    return user, authenticated_headers


def ensure_workout(
    base_url: str,
    headers: Dict[str, str],
    user_id: str,
    activity_id: str,
) -> Dict[str, Any]:
    workouts = request_json(
        method="GET",
        url=f"{base_url}/users/{user_id}/workouts",
        headers=headers,
        expected_statuses={200},
    )
    existing = find_by(workouts, "strava_activity_id", activity_id)
    if existing:
        return request_json(
            method="GET",
            url=f"{base_url}/workouts/{existing['id']}",
            headers=headers,
            expected_statuses={200},
        )

    created = request_json(
        method="POST",
        url=f"{base_url}/users/{user_id}/workouts",
        headers=headers,
        expected_statuses={201},
        payload={
            "strava_activity_id": activity_id,
            "name": "Smoke Test Run",
            "sport_type": "Run",
            "start_date": "2026-03-31T12:00:00Z",
            "distance_meters": 5000,
            "moving_time_seconds": 1500,
            "calories": 350,
            "notes": "Created by the smoke test seed script.",
            "raw_data": {"source": "smoke-test-script"},
        },
    )
    return request_json(
        method="GET",
        url=f"{base_url}/workouts/{created['id']}",
        headers=headers,
        expected_statuses={200},
    )


def ensure_fueling_plan(
    base_url: str,
    headers: Dict[str, str],
    user_id: str,
    workout_id: str,
    goal: str,
) -> Dict[str, Any]:
    plans = request_json(
        method="GET",
        url=f"{base_url}/users/{user_id}/fueling-plans",
        headers=headers,
        expected_statuses={200},
    )
    for plan in plans:
        if plan.get("goal") == goal and plan.get("workout_id") == workout_id:
            return request_json(
                method="GET",
                url=f"{base_url}/fueling-plans/{plan['id']}",
                headers=headers,
                expected_statuses={200},
            )

    created = request_json(
        method="POST",
        url=f"{base_url}/users/{user_id}/fueling-plans",
        headers=headers,
        expected_statuses={201},
        payload={
            "workout_id": workout_id,
            "goal": goal,
            "carbs_per_hour": 60,
            "hydration_ml_per_hour": 500,
            "sodium_mg_per_hour": 500,
            "notes": "Created by the smoke test seed script.",
        },
    )
    return request_json(
        method="GET",
        url=f"{base_url}/fueling-plans/{created['id']}",
        headers=headers,
        expected_statuses={200},
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed and verify reusable smoke-test data against the Peak API."
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("PEAK_BASE_URL", DEFAULT_BASE_URL),
        help="API base URL. Defaults to PEAK_BASE_URL or http://127.0.0.1:8000.",
    )
    parser.add_argument(
        "--email",
        default=os.getenv("PEAK_SMOKE_EMAIL", DEFAULT_EMAIL),
        help="Reusable smoke-test user email address.",
    )
    parser.add_argument(
        "--name",
        default=os.getenv("PEAK_SMOKE_NAME", DEFAULT_NAME),
        help="Reusable smoke-test user display name.",
    )
    parser.add_argument(
        "--activity-id",
        default=os.getenv("PEAK_SMOKE_ACTIVITY_ID", DEFAULT_ACTIVITY_ID),
        help="Stable Strava activity id used for the smoke-test workout.",
    )
    parser.add_argument(
        "--goal",
        default=os.getenv("PEAK_SMOKE_GOAL", DEFAULT_GOAL),
        help="Stable goal string used for the smoke-test fueling plan.",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("PEAK_API_KEY"),
        help="Optional X-API-Key header value for deployments that require it.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    base_url = normalize_base_url(args.base_url)
    headers = build_headers(args.api_key)

    try:
        health = request_json(
            method="GET",
            url=f"{base_url}/health",
            headers=headers,
            expected_statuses={200},
        )
        root = request_json(
            method="GET",
            url=f"{base_url}/",
            headers=headers,
            expected_statuses={200},
        )
        user, authenticated_headers = ensure_user(base_url, headers, args.name, args.email)
        workout = ensure_workout(
            base_url,
            authenticated_headers,
            user["id"],
            args.activity_id,
        )
        plan = ensure_fueling_plan(
            base_url,
            authenticated_headers,
            user["id"],
            workout["id"],
            args.goal,
        )
    except RuntimeError as exc:
        print(f"Smoke test failed: {exc}", file=sys.stderr)
        return 1

    print("Smoke test succeeded.")
    print(f"Base URL: {base_url}")
    print(f"Health: {json.dumps(health, sort_keys=True)}")
    print(f"Root: {json.dumps(root, sort_keys=True)}")
    print(f"User ID: {user['id']} ({user['email']})")
    print(f"Workout ID: {workout['id']} ({workout['strava_activity_id']})")
    print(f"Fueling Plan ID: {plan['id']} ({plan['goal']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
