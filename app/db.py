import json
import os
import sqlite3
from contextlib import closing
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from fastapi import HTTPException, status

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover - requirements install psycopg in CI/prod
    psycopg = None
    dict_row = None


DEFAULT_DB_PATH = "peak.db"
SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        password TEXT NOT NULL,
        created_at TEXT NOT NULL,
        dob DATE NOT NULL,
        height INTEGER NOT NULL,
        weight INTEGER NOT NULL,
        is_male BOOLEAN NOT NULL
    )
    """,
    """
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
    )
    """,
    """
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
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS strava_connections (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL UNIQUE,
        strava_athlete_id TEXT NOT NULL UNIQUE,
        strava_username TEXT,
        access_token TEXT NOT NULL,
        refresh_token TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        scope TEXT,
        last_synced_at TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_workouts_user_id
    ON workouts (user_id)
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_workouts_user_strava_activity
    ON workouts (user_id, strava_activity_id)
    WHERE strava_activity_id IS NOT NULL
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_fueling_plans_user_id
    ON fueling_plans (user_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_strava_connections_user_id
    ON strava_connections (user_id)
    """,
]
RowMapping = Mapping[str, Any]
ConnectionType = Any

if psycopg is None:
    INTEGRITY_ERRORS: Tuple[type, ...] = (sqlite3.IntegrityError,)
else:
    INTEGRITY_ERRORS = (sqlite3.IntegrityError, psycopg.IntegrityError)


def get_database_url() -> Optional[str]:
    return os.getenv("DATABASE_URL")


def get_database_backend() -> str:
    return "postgres" if get_database_url() else "sqlite"


def get_db_path() -> str:
    return os.getenv("PEAK_DB_PATH", DEFAULT_DB_PATH)


def get_connection() -> ConnectionType:
    database_url = get_database_url()
    if database_url:
        if psycopg is None:
            raise RuntimeError("psycopg is required when DATABASE_URL is set.")
        return psycopg.connect(database_url, row_factory=dict_row)

    connection = sqlite3.connect(get_db_path())
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON;")
    return connection


def execute(connection: ConnectionType, query: str, params: Sequence[Any] = ()) -> Any:
    normalized_query = query if isinstance(connection, sqlite3.Connection) else query.replace("?", "%s")
    return connection.execute(normalized_query, tuple(params))


def fetch_one(
    connection: ConnectionType, query: str, params: Sequence[Any] = ()
) -> Optional[RowMapping]:
    return execute(connection, query, params).fetchone()


def fetch_all(
    connection: ConnectionType, query: str, params: Sequence[Any] = ()
) -> List[RowMapping]:
    return execute(connection, query, params).fetchall()


_USER_MIGRATIONS = [
    "ALTER TABLE users ADD COLUMN dob DATE NOT NULL DEFAULT '1900-01-01'",
    "ALTER TABLE users ADD COLUMN height INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE users ADD COLUMN weight INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE users ADD COLUMN is_male BOOLEAN NOT NULL DEFAULT FALSE",
]


def init_db() -> None:
    with closing(get_connection()) as connection:
        for statement in SCHEMA_STATEMENTS:
            execute(connection, statement)
        for migration in _USER_MIGRATIONS:
            try:
                execute(connection, migration)
            except Exception:
                pass
        connection.commit()


def fetch_user_or_404(connection: ConnectionType, user_id: str) -> RowMapping:
    row = fetch_one(
        connection,
        "SELECT id, name, email, created_at, dob, height, weight, is_male FROM users WHERE id = ?",
        (user_id,),
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )
    return row


def fetch_workout_or_404(connection: ConnectionType, workout_id: str) -> RowMapping:
    row = fetch_one(
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
        WHERE id = ?
        """,
        (workout_id,),
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workout not found.",
        )
    return row


def fetch_fueling_plan_or_404(
    connection: ConnectionType, plan_id: str
) -> RowMapping:
    row = fetch_one(
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
        WHERE id = ?
        """,
        (plan_id,),
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fueling plan not found.",
        )
    return row


def fetch_strava_connection_by_user_id(
    connection: ConnectionType, user_id: str
) -> Optional[RowMapping]:
    return fetch_one(
        connection,
        """
        SELECT
            id,
            user_id,
            strava_athlete_id,
            strava_username,
            access_token,
            refresh_token,
            expires_at,
            scope,
            last_synced_at,
            created_at,
            updated_at
        FROM strava_connections
        WHERE user_id = ?
        """,
        (user_id,),
    )


def serialize_user(row: RowMapping) -> Dict[str, Any]:
    return dict(row)


def serialize_workout(row: RowMapping) -> Dict[str, Any]:
    item = dict(row)
    item["raw_data"] = json.loads(item["raw_data"]) if item["raw_data"] else None
    return item


def serialize_fueling_plan(row: RowMapping) -> Dict[str, Any]:
    return dict(row)


def serialize_strava_connection(row: RowMapping) -> Dict[str, Any]:
    item = dict(row)
    item.pop("access_token", None)
    item.pop("refresh_token", None)
    return item
