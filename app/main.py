"""
Minimal Peak V1 API.

This version keeps the backend intentionally small:
- users
- Strava workout records
- fueling plans
"""

import json
import os
from contextlib import asynccontextmanager, closing
from datetime import datetime, timezone
from typing import Any, Dict, List
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Response, status

from app.db import (
    INTEGRITY_ERRORS,
    execute,
    fetch_all,
    fetch_one,
    fetch_fueling_plan_or_404,
    fetch_running_plan_or_404,
    fetch_user_or_404,
    fetch_workout_or_404,
    get_database_backend,
    get_connection,
    init_db,
    serialize_fueling_plan,
    serialize_running_plan,
    serialize_user,
    serialize_workout,
)
from app.schemas import (
    FuelingPlanCreate,
    FuelingPlanRead,
    LoginRequest,
    RunningPlanCreate,
    RunningPlanRead,
    UserCreate,
    UserRead,
    UserUpdate,
    WorkoutCreate,
    WorkoutRead,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Peak V1 API",
    description="Minimal API for users, Strava workouts, and fueling plans.",
    version="1.0.0",
    lifespan=lifespan,
)


def utc_now_iso() -> str:
    # Strip microseconds — Swift's ISO8601DateFormatter rejects fractional seconds
    # by default, so we keep all timestamps as whole-second precision.
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_required_text(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="{0} cannot be empty.".format(field_name),
        )
    return normalized


@app.get("/")
def root() -> Dict[str, Any]:
    return {
        "message": "Peak V1 API",
        "docs": "/docs",
        "database_backend": get_database_backend(),
    }


@app.get("/health")
def health_check() -> Dict[str, str]:
    with closing(get_connection()) as connection:
        execute(connection, "SELECT 1").fetchone()
    return {"status": "healthy", "database": "ok"}


@app.post("/users", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate) -> Dict[str, Any]:
    user_id = str(uuid4())
    created_at = utc_now_iso()
    name = normalize_required_text(payload.name, "name")
    email = normalize_required_text(payload.email, "email").lower()
    password = normalize_required_text(payload.password, "password")

    with closing(get_connection()) as connection:
        try:
            execute(
                connection,
                """
                INSERT INTO users (
                    id,
                    name,
                    email,
                    password,
                    created_at,
                    dob,
                    height,
                    weight,
                    is_male
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    name,
                    email,
                    password,
                    created_at,
                    payload.dob.isoformat(),
                    payload.height,
                    payload.weight,
                    payload.is_male,
                ),
            )
            connection.commit()
        except INTEGRITY_ERRORS as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A user with that email already exists.",
            ) from exc

        row = fetch_user_or_404(connection, user_id)
        return serialize_user(row)


@app.get("/users", response_model=List[UserRead])
def list_users() -> List[Dict[str, Any]]:
    with closing(get_connection()) as connection:
        rows = fetch_all(
            connection,
            """
            SELECT id, name, email, created_at, dob, height, weight, is_male
            FROM users
            ORDER BY created_at DESC
            """
        )
    return [serialize_user(row) for row in rows]


@app.get("/users/{user_id}", response_model=UserRead)
def get_user(user_id: str) -> Dict[str, Any]:
    with closing(get_connection()) as connection:
        row = fetch_user_or_404(connection, user_id)
        return serialize_user(row)


@app.patch("/users/{user_id}", response_model=UserRead)
def update_user(user_id: str, payload: UserUpdate) -> Dict[str, Any]:
    """
    Partially update a user profile.
    Accepts any combination of: height (cm), weight (kg), password.
    Only the supplied fields are written — everything else is left unchanged.
    """
    # Build SET clause dynamically from whichever fields were provided
    updates: Dict[str, Any] = {}
    if payload.height is not None:
        updates["height"] = payload.height
    if payload.weight is not None:
        updates["weight"] = payload.weight
    if payload.password is not None:
        updates["password"] = payload.password

    set_clause = ", ".join(f"{col} = ?" for col in updates)
    values = list(updates.values()) + [user_id]

    with closing(get_connection()) as connection:
        fetch_user_or_404(connection, user_id)
        execute(
            connection,
            f"UPDATE users SET {set_clause} WHERE id = ?",
            values,
        )
        connection.commit()
        row = fetch_user_or_404(connection, user_id)
        return serialize_user(row)


@app.post(
    "/users/{user_id}/workouts",
    response_model=WorkoutRead,
    status_code=status.HTTP_201_CREATED,
)
def create_workout(user_id: str, payload: WorkoutCreate) -> Dict[str, Any]:
    workout_id = str(uuid4())
    created_at = utc_now_iso()
    name = normalize_required_text(payload.name, "name")
    raw_data = json.dumps(payload.raw_data) if payload.raw_data is not None else None

    with closing(get_connection()) as connection:
        fetch_user_or_404(connection, user_id)

        try:
            execute(
                connection,
                """
                INSERT INTO workouts (
                    id,
                    user_id,
                    source,
                    strava_activity_id,
                    name,
                    sport_type,
                    start_date,
                    distance_meters,
                    moving_time_seconds,
                    calories,
                    notes,
                    raw_data,
                    created_at
                )
                VALUES (?, ?, 'strava', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    workout_id,
                    user_id,
                    payload.strava_activity_id,
                    name,
                    payload.sport_type,
                    payload.start_date.isoformat(),
                    payload.distance_meters,
                    payload.moving_time_seconds,
                    payload.calories,
                    payload.notes,
                    raw_data,
                    created_at,
                ),
            )
            connection.commit()
        except INTEGRITY_ERRORS as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="That Strava activity is already stored for this user.",
            ) from exc

        row = fetch_workout_or_404(connection, workout_id)
        return serialize_workout(row)


@app.get("/users/{user_id}/workouts", response_model=List[WorkoutRead])
def list_workouts(user_id: str) -> List[Dict[str, Any]]:
    with closing(get_connection()) as connection:
        fetch_user_or_404(connection, user_id)
        rows = fetch_all(
            connection,
            """
            SELECT
                id,
                user_id,
                source,
                strava_activity_id,
                name,
                sport_type,
                start_date,
                distance_meters,
                moving_time_seconds,
                calories,
                notes,
                raw_data,
                created_at
            FROM workouts
            WHERE user_id = ?
            ORDER BY start_date DESC, created_at DESC
            """,
            (user_id,),
        )
    return [serialize_workout(row) for row in rows]


@app.get("/workouts/{workout_id}", response_model=WorkoutRead)
def get_workout(workout_id: str) -> Dict[str, Any]:
    with closing(get_connection()) as connection:
        row = fetch_workout_or_404(connection, workout_id)
        return serialize_workout(row)


@app.post(
    "/users/{user_id}/fueling-plans",
    response_model=FuelingPlanRead,
    status_code=status.HTTP_201_CREATED,
)
def create_fueling_plan(user_id: str, payload: FuelingPlanCreate) -> Dict[str, Any]:
    plan_id = str(uuid4())
    created_at = utc_now_iso()
    goal = normalize_required_text(payload.goal, "goal")

    with closing(get_connection()) as connection:
        fetch_user_or_404(connection, user_id)

        if payload.workout_id is not None:
            workout_row = fetch_workout_or_404(connection, payload.workout_id)
            if workout_row["user_id"] != user_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Workout does not belong to this user.",
                )

        execute(
            connection,
            """
            INSERT INTO fueling_plans (
                id,
                user_id,
                workout_id,
                goal,
                carbs_per_hour,
                hydration_ml_per_hour,
                sodium_mg_per_hour,
                notes,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                plan_id,
                user_id,
                payload.workout_id,
                goal,
                payload.carbs_per_hour,
                payload.hydration_ml_per_hour,
                payload.sodium_mg_per_hour,
                payload.notes,
                created_at,
            ),
        )
        connection.commit()

        row = fetch_fueling_plan_or_404(connection, plan_id)
        return serialize_fueling_plan(row)


@app.get("/users/{user_id}/fueling-plans", response_model=List[FuelingPlanRead])
def list_fueling_plans(user_id: str) -> List[Dict[str, Any]]:
    with closing(get_connection()) as connection:
        fetch_user_or_404(connection, user_id)
        rows = fetch_all(
            connection,
            """
            SELECT
                id,
                user_id,
                workout_id,
                goal,
                carbs_per_hour,
                hydration_ml_per_hour,
                sodium_mg_per_hour,
                notes,
                created_at
            FROM fueling_plans
            WHERE user_id = ?
            ORDER BY created_at DESC
            """,
            (user_id,),
        )
    return [serialize_fueling_plan(row) for row in rows]


@app.get("/fueling-plans/{plan_id}", response_model=FuelingPlanRead)
def get_fueling_plan(plan_id: str) -> Dict[str, Any]:
    with closing(get_connection()) as connection:
        row = fetch_fueling_plan_or_404(connection, plan_id)
        return serialize_fueling_plan(row)


@app.post(
    "/users/{user_id}/running-plans",
    response_model=RunningPlanRead,
    status_code=status.HTTP_201_CREATED,
)
def create_running_plan(user_id: str, payload: RunningPlanCreate) -> Dict[str, Any]:
    """Create a scheduled running plan for a user."""
    with closing(get_connection()) as connection:
        fetch_user_or_404(connection, user_id)
        plan_id = str(uuid4())
        created_at = utc_now_iso()
        # Store planned_at as whole-second ISO string (same rule as created_at)
        planned_at = payload.planned_at.replace(microsecond=0).isoformat()
        execute(
            connection,
            """
            INSERT INTO running_plans
                (id, user_id, planned_at, distance_km, speed_kph, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                plan_id,
                user_id,
                planned_at,
                payload.distance_km,
                payload.speed_kph,
                payload.notes,
                created_at,
            ),
        )
        connection.commit()
        row = fetch_running_plan_or_404(connection, plan_id)
        return serialize_running_plan(row)


@app.get("/users/{user_id}/running-plans", response_model=List[RunningPlanRead])
def list_running_plans(user_id: str) -> List[Dict[str, Any]]:
    """List all running plans for a user, most recent first."""
    with closing(get_connection()) as connection:
        fetch_user_or_404(connection, user_id)
        rows = fetch_all(
            connection,
            """
            SELECT id, user_id, planned_at, distance_km, speed_kph, notes, created_at
            FROM running_plans
            WHERE user_id = ?
            ORDER BY planned_at ASC
            """,
            (user_id,),
        )
    return [serialize_running_plan(row) for row in rows]


@app.post("/auth/login", response_model=UserRead)
def login(payload: LoginRequest) -> Dict[str, Any]:
    """Authenticate a user by email and password.

    Returns the full ``UserRead`` on success.  Returns 401 if the email is not
    found or the password does not match — both cases return the same error
    message to avoid leaking which emails are registered.
    """
    email = payload.email.strip().lower()
    with closing(get_connection()) as connection:
        row = fetch_one(
            connection,
            """
            SELECT id, name, email, password, created_at, dob, height, weight, is_male
            FROM users
            WHERE LOWER(email) = ?
            """,
            (email,),
        )
    if row is None or row["password"] != payload.password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )
    return serialize_user(row)


@app.post("/test/reset", status_code=status.HTTP_204_NO_CONTENT)
def reset_database() -> Response:
    """Drop all tables and re-initialise the schema.

    Only available when the ``PEAK_TESTING`` environment variable is set to
    ``"true"``.  Returns 403 in all other environments so this endpoint cannot
    be called in production by mistake.
    """
    if os.getenv("PEAK_TESTING", "").lower() != "true":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Test-only endpoint. Set PEAK_TESTING=true to enable.",
        )

    drop_statements = [
        "DROP INDEX IF EXISTS idx_strava_connections_user_id",
        "DROP INDEX IF EXISTS idx_fueling_plans_user_id",
        "DROP INDEX IF EXISTS idx_workouts_user_strava_activity",
        "DROP INDEX IF EXISTS idx_workouts_user_id",
        "DROP TABLE IF EXISTS strava_connections",
        "DROP TABLE IF EXISTS fueling_plans",
        "DROP TABLE IF EXISTS workouts",
        "DROP TABLE IF EXISTS users",
    ]
    with closing(get_connection()) as connection:
        for statement in drop_statements:
            connection.execute(statement)
        connection.commit()

    init_db()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
