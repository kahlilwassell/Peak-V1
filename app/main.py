"""
Minimal Peak V1 API.

This version keeps the backend intentionally small:
- users
- Strava workout records
- fueling plans
"""

import json
import sqlite3
from contextlib import asynccontextmanager, closing
from datetime import datetime, timezone
from typing import Any, Dict, List
from uuid import uuid4

from fastapi import FastAPI, HTTPException, status

from app.db import (
    DB_PATH,
    fetch_fueling_plan_or_404,
    fetch_user_or_404,
    fetch_workout_or_404,
    get_connection,
    init_db,
    serialize_fueling_plan,
    serialize_user,
    serialize_workout,
)
from app.schemas import (
    FuelingPlanCreate,
    FuelingPlanRead,
    UserCreate,
    UserRead,
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
    return datetime.now(timezone.utc).isoformat()


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
        "database_path": DB_PATH,
    }


@app.get("/health")
def health_check() -> Dict[str, str]:
    with closing(get_connection()) as connection:
        connection.execute("SELECT 1").fetchone()
    return {"status": "healthy", "database": "ok"}


@app.post("/users", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate) -> Dict[str, Any]:
    user_id = str(uuid4())
    created_at = utc_now_iso()
    name = normalize_required_text(payload.name, "name")
    email = normalize_required_text(payload.email, "email").lower()

    with closing(get_connection()) as connection:
        try:
            connection.execute(
                """
                INSERT INTO users (id, name, email, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, name, email, created_at),
            )
            connection.commit()
        except sqlite3.IntegrityError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A user with that email already exists.",
            ) from exc

        row = fetch_user_or_404(connection, user_id)
        return serialize_user(row)


@app.get("/users", response_model=List[UserRead])
def list_users() -> List[Dict[str, Any]]:
    with closing(get_connection()) as connection:
        rows = connection.execute(
            """
            SELECT id, name, email, created_at
            FROM users
            ORDER BY created_at DESC
            """
        ).fetchall()
    return [serialize_user(row) for row in rows]


@app.get("/users/{user_id}", response_model=UserRead)
def get_user(user_id: str) -> Dict[str, Any]:
    with closing(get_connection()) as connection:
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
            connection.execute(
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
        except sqlite3.IntegrityError as exc:
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
        rows = connection.execute(
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
        ).fetchall()
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

        connection.execute(
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
        rows = connection.execute(
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
        ).fetchall()
    return [serialize_fueling_plan(row) for row in rows]


@app.get("/fueling-plans/{plan_id}", response_model=FuelingPlanRead)
def get_fueling_plan(plan_id: str) -> Dict[str, Any]:
    with closing(get_connection()) as connection:
        row = fetch_fueling_plan_or_404(connection, plan_id)
        return serialize_fueling_plan(row)
