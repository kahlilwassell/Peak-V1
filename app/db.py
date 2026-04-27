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
    """
    CREATE TABLE IF NOT EXISTS running_plans (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        planned_at TEXT NOT NULL,
        distance_km REAL NOT NULL,
        speed_kph REAL NOT NULL,
        notes TEXT,
        location TEXT,
        estimated_fluid_ml INTEGER,
        estimated_sodium_mg INTEGER,
        estimated_carbs_g INTEGER,
        weather_temp_c REAL,
        weather_humidity_pct REAL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_running_plans_user_id
    ON running_plans (user_id)
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


# Catch-up migrations for pre-existing databases that were created before
# these columns were part of the `users` schema. On a fresh deploy the
# CREATE TABLE statement above already contains every column, so these are
# no-ops and only fire against older SQLite files.
#
# Each entry is (column_name, DDL). We introspect the current columns first
# and only run the DDL for columns that are genuinely missing. This avoids
# the psycopg3 failure mode where a failed ALTER marks the transaction as
# aborted and breaks every subsequent statement on the connection with
# "current transaction is aborted, commands ignored until end of transaction block".
_USER_COLUMN_ADDITIONS: List[Tuple[str, str]] = [
    ("dob", "ALTER TABLE users ADD COLUMN dob DATE NOT NULL DEFAULT '1900-01-01'"),
    ("height", "ALTER TABLE users ADD COLUMN height INTEGER NOT NULL DEFAULT 0"),
    ("weight", "ALTER TABLE users ADD COLUMN weight INTEGER NOT NULL DEFAULT 0"),
    ("is_male", "ALTER TABLE users ADD COLUMN is_male BOOLEAN NOT NULL DEFAULT FALSE"),
    ("password", "ALTER TABLE users ADD COLUMN password TEXT NOT NULL DEFAULT ''"),
]

_RUNNING_PLAN_COLUMN_ADDITIONS: List[Tuple[str, str]] = [
    ("location",              "ALTER TABLE running_plans ADD COLUMN location TEXT"),
    ("estimated_fluid_ml",    "ALTER TABLE running_plans ADD COLUMN estimated_fluid_ml INTEGER"),
    ("estimated_sodium_mg",   "ALTER TABLE running_plans ADD COLUMN estimated_sodium_mg INTEGER"),
    ("estimated_carbs_g",     "ALTER TABLE running_plans ADD COLUMN estimated_carbs_g INTEGER"),
    ("weather_temp_c",        "ALTER TABLE running_plans ADD COLUMN weather_temp_c REAL"),
    ("weather_humidity_pct",  "ALTER TABLE running_plans ADD COLUMN weather_humidity_pct REAL"),
]


def _existing_user_columns(connection: ConnectionType) -> set:
    """Return the set of column names currently present on the `users` table.

    Uses `PRAGMA table_info` on SQLite and `information_schema.columns` on
    Postgres. Returns an empty set if the table does not exist yet — the
    caller has just created it via SCHEMA_STATEMENTS in that case.
    """
    if isinstance(connection, sqlite3.Connection):
        rows = execute(connection, "PRAGMA table_info(users)").fetchall()
        return {row["name"] for row in rows}

    # Postgres — scope to the current schema so we don't match a `users`
    # table in some other schema on the same database.
    rows = fetch_all(
        connection,
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'users'
        """,
    )
    return {row["column_name"] for row in rows}


def _existing_columns(connection: ConnectionType, table: str) -> set:
    """Return the set of column names currently present on *table*.

    Returns an empty set if the table does not yet exist.
    """
    if isinstance(connection, sqlite3.Connection):
        rows = execute(connection, f"PRAGMA table_info({table})").fetchall()
        return {row["name"] for row in rows}

    rows = fetch_all(
        connection,
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = ?
        """,
        (table,),
    )
    return {row["column_name"] for row in rows}


def init_db() -> None:
    with closing(get_connection()) as connection:
        for statement in SCHEMA_STATEMENTS:
            execute(connection, statement)

        existing_user_cols = _existing_user_columns(connection)
        for column_name, migration in _USER_COLUMN_ADDITIONS:
            if column_name in existing_user_cols:
                continue
            execute(connection, migration)

        existing_plan_cols = _existing_columns(connection, "running_plans")
        for column_name, migration in _RUNNING_PLAN_COLUMN_ADDITIONS:
            if column_name in existing_plan_cols:
                continue
            execute(connection, migration)

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


def fetch_running_plan_or_404(connection: ConnectionType, plan_id: str) -> RowMapping:
    row = fetch_one(
        connection,
        """
        SELECT
            id, user_id, planned_at, distance_km, speed_kph, notes, location,
            estimated_fluid_ml, estimated_sodium_mg, estimated_carbs_g,
            weather_temp_c, weather_humidity_pct,
            created_at
        FROM running_plans
        WHERE id = ?
        """,
        (plan_id,),
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Running plan not found.",
        )
    return row


def serialize_running_plan(row: RowMapping) -> Dict[str, Any]:
    return dict(row)


def serialize_strava_connection(row: RowMapping) -> Dict[str, Any]:
    item = dict(row)
    item.pop("access_token", None)
    item.pop("refresh_token", None)
    return item
