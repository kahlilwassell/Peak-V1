"""
Peak V1 - FastAPI Backend
CRUD API for users, user connections, and workouts.
"""

import os
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
from uuid import UUID

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Query, Response, Security, status
from fastapi.security import APIKeyHeader
from psycopg.errors import ForeignKeyViolation, UniqueViolation
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel

API_KEY_ENV_VAR = "PEAK_API_KEY"
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


class UserCreate(BaseModel):
    email: Optional[str] = None
    name: Optional[str] = None


class UserUpdate(BaseModel):
    email: Optional[str] = None
    name: Optional[str] = None


class UserOut(BaseModel):
    id: UUID
    email: Optional[str] = None
    name: Optional[str] = None
    created_at: datetime


class UserConnectionCreate(BaseModel):
    provider: str
    provider_user_id: Optional[str] = None
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    token_expires_at: Optional[datetime] = None


class UserConnectionUpdate(BaseModel):
    provider: Optional[str] = None
    provider_user_id: Optional[str] = None
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    token_expires_at: Optional[datetime] = None


class UserConnectionOut(BaseModel):
    id: UUID
    user_id: UUID
    provider: str
    provider_user_id: Optional[str] = None
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    token_expires_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class WorkoutCreate(BaseModel):
    provider: Optional[str] = None
    provider_workout_id: Optional[str] = None
    started_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    distance_meters: Optional[int] = None
    sport: Optional[str] = None
    calories: Optional[int] = None
    raw: Optional[Any] = None


class WorkoutUpdate(BaseModel):
    provider: Optional[str] = None
    provider_workout_id: Optional[str] = None
    started_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    distance_meters: Optional[int] = None
    sport: Optional[str] = None
    calories: Optional[int] = None
    raw: Optional[Any] = None


class WorkoutOut(BaseModel):
    id: UUID
    user_id: UUID
    provider: Optional[str] = None
    provider_workout_id: Optional[str] = None
    started_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    distance_meters: Optional[int] = None
    sport: Optional[str] = None
    calories: Optional[int] = None
    raw: Optional[Any] = None
    created_at: datetime


def require_api_key(api_key: Optional[str] = Security(api_key_header)) -> None:
    """Require a valid API key header for all endpoints."""
    expected_api_key = os.getenv(API_KEY_ENV_VAR)
    if not expected_api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{API_KEY_ENV_VAR} is not configured",
        )

    if api_key != expected_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )


def get_database_url() -> str:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise HTTPException(status_code=500, detail="DATABASE_URL is not configured")
    return database_url


def get_connection():
    return psycopg.connect(get_database_url(), row_factory=dict_row)


def handle_db_error(exc: Exception) -> None:
    if isinstance(exc, UniqueViolation):
        raise HTTPException(
            status_code=409,
            detail="Request conflicts with an existing record.",
        ) from exc
    if isinstance(exc, ForeignKeyViolation):
        raise HTTPException(
            status_code=400,
            detail="Request references a record that does not exist.",
        ) from exc
    raise HTTPException(
        status_code=500,
        detail=f"Database error ({exc.__class__.__name__})",
    ) from exc


def ensure_update_fields(fields: Dict[str, Any]) -> None:
    if not fields:
        raise HTTPException(
            status_code=400, detail="At least one field must be provided for update."
        )


def to_jsonb_value(value: Any) -> Any:
    if value is None:
        return None
    return Jsonb(value)


app = FastAPI(
    title="Peak V1 API",
    description="Backend API for Peak application",
    version="1.0.0",
    dependencies=[Depends(require_api_key)],
)


@app.get("/")
async def root() -> Dict[str, str]:
    return {"message": "Welcome to Peak V1 API"}


@app.get("/health")
async def health_check() -> Dict[str, str]:
    return {"status": "healthy", "service": "Peak V1 API"}


@app.get("/health/db")
def database_health_check() -> Dict[str, Any]:
    database_url = get_database_url()
    try:
        with psycopg.connect(database_url, connect_timeout=5) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                value = cur.fetchone()
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Database connection failed ({exc.__class__.__name__})",
        ) from exc

    parsed = urlparse(database_url)
    return {
        "status": "healthy",
        "service": "Peak V1 API",
        "database": "connected",
        "check": value[0] if value else None,
        "host": parsed.hostname,
        "port": parsed.port,
        "name": parsed.path.lstrip("/") or None,
    }


@app.post("/users", response_model=UserOut, status_code=201)
def create_user(payload: UserCreate) -> Dict[str, Any]:
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    insert into users (email, name)
                    values (%s, %s)
                    returning id, email, name, created_at
                    """,
                    (payload.email, payload.name),
                )
                row = cur.fetchone()
        return row
    except HTTPException:
        raise
    except Exception as exc:
        handle_db_error(exc)


@app.get("/users", response_model=List[UserOut])
def list_users(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> List[Dict[str, Any]]:
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select id, email, name, created_at
                    from users
                    order by created_at desc
                    limit %s offset %s
                    """,
                    (limit, offset),
                )
                rows = cur.fetchall()
        return rows
    except HTTPException:
        raise
    except Exception as exc:
        handle_db_error(exc)


@app.get("/users/{user_id}", response_model=UserOut)
def get_user(user_id: UUID) -> Dict[str, Any]:
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select id, email, name, created_at
                    from users
                    where id = %s
                    """,
                    (user_id,),
                )
                row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="User not found.")
        return row
    except HTTPException:
        raise
    except Exception as exc:
        handle_db_error(exc)


@app.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: UUID, payload: UserUpdate) -> Dict[str, Any]:
    update_data = payload.model_dump(exclude_unset=True)
    ensure_update_fields(update_data)

    set_clauses = []
    values = []
    for column in ("email", "name"):
        if column in update_data:
            set_clauses.append(f"{column} = %s")
            values.append(update_data[column])

    values.append(user_id)
    query = f"""
        update users
        set {", ".join(set_clauses)}
        where id = %s
        returning id, email, name, created_at
    """

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, values)
                row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="User not found.")
        return row
    except HTTPException:
        raise
    except Exception as exc:
        handle_db_error(exc)


@app.delete("/users/{user_id}", status_code=204)
def delete_user(user_id: UUID) -> Response:
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("delete from users where id = %s returning id", (user_id,))
                row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="User not found.")
        return Response(status_code=204)
    except HTTPException:
        raise
    except Exception as exc:
        handle_db_error(exc)


@app.post("/users/{user_id}/connections", response_model=UserConnectionOut, status_code=201)
def create_user_connection(
    user_id: UUID, payload: UserConnectionCreate
) -> Dict[str, Any]:
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    insert into user_connections (
                        user_id,
                        provider,
                        provider_user_id,
                        access_token,
                        refresh_token,
                        token_expires_at
                    )
                    values (%s, %s, %s, %s, %s, %s)
                    returning
                        id,
                        user_id,
                        provider,
                        provider_user_id,
                        access_token,
                        refresh_token,
                        token_expires_at,
                        created_at,
                        updated_at
                    """,
                    (
                        user_id,
                        payload.provider,
                        payload.provider_user_id,
                        payload.access_token,
                        payload.refresh_token,
                        payload.token_expires_at,
                    ),
                )
                row = cur.fetchone()
        return row
    except HTTPException:
        raise
    except Exception as exc:
        handle_db_error(exc)


@app.get("/users/{user_id}/connections", response_model=List[UserConnectionOut])
def list_user_connections(
    user_id: UUID,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> List[Dict[str, Any]]:
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select
                        id,
                        user_id,
                        provider,
                        provider_user_id,
                        access_token,
                        refresh_token,
                        token_expires_at,
                        created_at,
                        updated_at
                    from user_connections
                    where user_id = %s
                    order by created_at desc
                    limit %s offset %s
                    """,
                    (user_id, limit, offset),
                )
                rows = cur.fetchall()
        return rows
    except HTTPException:
        raise
    except Exception as exc:
        handle_db_error(exc)


@app.get("/connections/{connection_id}", response_model=UserConnectionOut)
def get_user_connection(connection_id: UUID) -> Dict[str, Any]:
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select
                        id,
                        user_id,
                        provider,
                        provider_user_id,
                        access_token,
                        refresh_token,
                        token_expires_at,
                        created_at,
                        updated_at
                    from user_connections
                    where id = %s
                    """,
                    (connection_id,),
                )
                row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Connection not found.")
        return row
    except HTTPException:
        raise
    except Exception as exc:
        handle_db_error(exc)


@app.patch("/connections/{connection_id}", response_model=UserConnectionOut)
def update_user_connection(
    connection_id: UUID, payload: UserConnectionUpdate
) -> Dict[str, Any]:
    update_data = payload.model_dump(exclude_unset=True)
    ensure_update_fields(update_data)

    set_clauses = []
    values = []
    for column in (
        "provider",
        "provider_user_id",
        "access_token",
        "refresh_token",
        "token_expires_at",
    ):
        if column in update_data:
            set_clauses.append(f"{column} = %s")
            values.append(update_data[column])

    set_clauses.append("updated_at = now()")
    values.append(connection_id)
    query = f"""
        update user_connections
        set {", ".join(set_clauses)}
        where id = %s
        returning
            id,
            user_id,
            provider,
            provider_user_id,
            access_token,
            refresh_token,
            token_expires_at,
            created_at,
            updated_at
    """

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, values)
                row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Connection not found.")
        return row
    except HTTPException:
        raise
    except Exception as exc:
        handle_db_error(exc)


@app.delete("/connections/{connection_id}", status_code=204)
def delete_user_connection(connection_id: UUID) -> Response:
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "delete from user_connections where id = %s returning id",
                    (connection_id,),
                )
                row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Connection not found.")
        return Response(status_code=204)
    except HTTPException:
        raise
    except Exception as exc:
        handle_db_error(exc)


@app.post("/users/{user_id}/workouts", response_model=WorkoutOut, status_code=201)
def create_workout(user_id: UUID, payload: WorkoutCreate) -> Dict[str, Any]:
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    insert into workouts (
                        user_id,
                        provider,
                        provider_workout_id,
                        started_at,
                        duration_seconds,
                        distance_meters,
                        sport,
                        calories,
                        raw
                    )
                    values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    returning
                        id,
                        user_id,
                        provider,
                        provider_workout_id,
                        started_at,
                        duration_seconds,
                        distance_meters,
                        sport,
                        calories,
                        raw,
                        created_at
                    """,
                    (
                        user_id,
                        payload.provider,
                        payload.provider_workout_id,
                        payload.started_at,
                        payload.duration_seconds,
                        payload.distance_meters,
                        payload.sport,
                        payload.calories,
                        to_jsonb_value(payload.raw),
                    ),
                )
                row = cur.fetchone()
        return row
    except HTTPException:
        raise
    except Exception as exc:
        handle_db_error(exc)


@app.get("/users/{user_id}/workouts", response_model=List[WorkoutOut])
def list_workouts(
    user_id: UUID,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> List[Dict[str, Any]]:
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select
                        id,
                        user_id,
                        provider,
                        provider_workout_id,
                        started_at,
                        duration_seconds,
                        distance_meters,
                        sport,
                        calories,
                        raw,
                        created_at
                    from workouts
                    where user_id = %s
                    order by started_at desc nulls last, created_at desc
                    limit %s offset %s
                    """,
                    (user_id, limit, offset),
                )
                rows = cur.fetchall()
        return rows
    except HTTPException:
        raise
    except Exception as exc:
        handle_db_error(exc)


@app.get("/workouts/{workout_id}", response_model=WorkoutOut)
def get_workout(workout_id: UUID) -> Dict[str, Any]:
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select
                        id,
                        user_id,
                        provider,
                        provider_workout_id,
                        started_at,
                        duration_seconds,
                        distance_meters,
                        sport,
                        calories,
                        raw,
                        created_at
                    from workouts
                    where id = %s
                    """,
                    (workout_id,),
                )
                row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Workout not found.")
        return row
    except HTTPException:
        raise
    except Exception as exc:
        handle_db_error(exc)


@app.patch("/workouts/{workout_id}", response_model=WorkoutOut)
def update_workout(workout_id: UUID, payload: WorkoutUpdate) -> Dict[str, Any]:
    update_data = payload.model_dump(exclude_unset=True)
    ensure_update_fields(update_data)

    set_clauses = []
    values = []
    for column in (
        "provider",
        "provider_workout_id",
        "started_at",
        "duration_seconds",
        "distance_meters",
        "sport",
        "calories",
        "raw",
    ):
        if column in update_data:
            set_clauses.append(f"{column} = %s")
            value = update_data[column]
            if column == "raw":
                values.append(to_jsonb_value(value))
            else:
                values.append(value)

    values.append(workout_id)
    query = f"""
        update workouts
        set {", ".join(set_clauses)}
        where id = %s
        returning
            id,
            user_id,
            provider,
            provider_workout_id,
            started_at,
            duration_seconds,
            distance_meters,
            sport,
            calories,
            raw,
            created_at
    """

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, values)
                row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Workout not found.")
        return row
    except HTTPException:
        raise
    except Exception as exc:
        handle_db_error(exc)


@app.delete("/workouts/{workout_id}", status_code=204)
def delete_workout(workout_id: UUID) -> Response:
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("delete from workouts where id = %s returning id", (workout_id,))
                row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Workout not found.")
        return Response(status_code=204)
    except HTTPException:
        raise
    except Exception as exc:
        handle_db_error(exc)
