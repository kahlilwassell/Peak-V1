import json
import os
import sqlite3
from contextlib import closing
from typing import Any, Dict

from fastapi import HTTPException, status


DB_PATH = os.getenv("PEAK_DB_PATH", "peak.db")


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON;")
    return connection


def init_db() -> None:
    with closing(get_connection()) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS workouts (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'strava',
                strava_activity_id TEXT,
                name TEXT NOT NULL,
                sport_type TEXT,
                start_date TEXT NOT NULL,
                distance_meters REAL,
                moving_time_seconds INTEGER,
                calories INTEGER,
                notes TEXT,
                raw_data TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS fueling_plans (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                workout_id TEXT,
                goal TEXT NOT NULL,
                carbs_per_hour INTEGER,
                hydration_ml_per_hour INTEGER,
                sodium_mg_per_hour INTEGER,
                notes TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
                FOREIGN KEY (workout_id) REFERENCES workouts (id) ON DELETE SET NULL
            );

            CREATE INDEX IF NOT EXISTS idx_workouts_user_id
            ON workouts (user_id);

            CREATE UNIQUE INDEX IF NOT EXISTS idx_workouts_user_strava_activity
            ON workouts (user_id, strava_activity_id)
            WHERE strava_activity_id IS NOT NULL;

            CREATE INDEX IF NOT EXISTS idx_fueling_plans_user_id
            ON fueling_plans (user_id);
            """
        )
        connection.commit()


def fetch_user_or_404(connection: sqlite3.Connection, user_id: str) -> sqlite3.Row:
    row = connection.execute(
        "SELECT id, name, email, created_at FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )
    return row


def fetch_workout_or_404(connection: sqlite3.Connection, workout_id: str) -> sqlite3.Row:
    row = connection.execute(
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
        WHERE id = ?
        """,
        (workout_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workout not found.",
        )
    return row


def fetch_fueling_plan_or_404(
    connection: sqlite3.Connection, plan_id: str
) -> sqlite3.Row:
    row = connection.execute(
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
        WHERE id = ?
        """,
        (plan_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fueling plan not found.",
        )
    return row


def serialize_user(row: sqlite3.Row) -> Dict[str, Any]:
    return dict(row)


def serialize_workout(row: sqlite3.Row) -> Dict[str, Any]:
    item = dict(row)
    item["raw_data"] = json.loads(item["raw_data"]) if item["raw_data"] else None
    return item


def serialize_fueling_plan(row: sqlite3.Row) -> Dict[str, Any]:
    return dict(row)
