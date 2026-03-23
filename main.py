"""
Peak V1 - FastAPI Backend
CRUD and retrieval API for Peak application entities.
"""

import os
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlparse
from uuid import UUID

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Query, Response, Security, status
from fastapi.security import APIKeyHeader
from psycopg.errors import ForeignKeyViolation, NotNullViolation, UniqueViolation
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import AliasChoices, BaseModel, ConfigDict, Field

API_KEY_ENV_VAR = "PEAK_API_KEY"
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

USER_COLUMNS = """
    id,
    email,
    name,
    created_at,
    updated_at
"""

USER_CONNECTION_COLUMNS = """
    id,
    user_id,
    provider,
    provider_user_id,
    access_token,
    refresh_token,
    token_expires_at,
    scopes,
    created_at,
    updated_at
"""

WORKOUT_COLUMNS = """
    id,
    user_id,
    provider,
    provider_workout_id,
    name,
    sport_type,
    start_date,
    start_date_local,
    timezone,
    distance_meters,
    moving_time_seconds,
    elapsed_time_seconds,
    elevation_gain_meters,
    average_speed,
    max_speed,
    average_heartrate,
    max_heartrate,
    calories,
    device_name,
    raw,
    created_at,
    updated_at
"""

ATHLETE_PROFILE_COLUMNS = """
    id,
    user_id,
    birth_year,
    sex,
    weight_kg,
    height_cm,
    primary_sport,
    training_goal,
    dietary_preferences,
    sweat_rate_notes,
    caffeine_preference,
    created_at,
    updated_at
"""

FUELING_PROFILE_COLUMNS = """
    id,
    user_id,
    pre_workout_carb_target_g,
    during_workout_carb_target_g_per_hr,
    hydration_target_ml_per_hr,
    sodium_target_mg_per_hr,
    preferred_fuel_types,
    gi_sensitivity,
    caffeine_strategy,
    created_at,
    updated_at
"""

RECOMMENDATION_COLUMNS = """
    id,
    user_id,
    workout_id,
    recommendation_type,
    title,
    body,
    carb_grams,
    fluid_ml,
    sodium_mg,
    caffeine_mg,
    reason,
    status,
    created_at
"""


class PeakBaseModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class UserCreate(PeakBaseModel):
    email: str
    name: Optional[str] = None


class UserUpdate(PeakBaseModel):
    email: Optional[str] = None
    name: Optional[str] = None


class UserOut(PeakBaseModel):
    id: UUID
    email: str
    name: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class UserConnectionFields(PeakBaseModel):
    provider_user_id: Optional[str] = None
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    token_expires_at: Optional[datetime] = None
    scopes: Optional[str] = None


class UserConnectionCreate(UserConnectionFields):
    provider: str


class UserConnectionUpdate(UserConnectionFields):
    provider: Optional[str] = None


class UserConnectionOut(UserConnectionFields):
    id: UUID
    user_id: UUID
    provider: str
    created_at: datetime
    updated_at: datetime


class WorkoutFields(PeakBaseModel):
    name: Optional[str] = None
    sport_type: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("sport_type", "sport"),
    )
    start_date: Optional[datetime] = Field(
        default=None,
        validation_alias=AliasChoices("start_date", "started_at"),
    )
    start_date_local: Optional[datetime] = None
    timezone: Optional[str] = None
    distance_meters: Optional[float] = None
    moving_time_seconds: Optional[int] = Field(
        default=None,
        validation_alias=AliasChoices("moving_time_seconds", "duration_seconds"),
    )
    elapsed_time_seconds: Optional[int] = None
    elevation_gain_meters: Optional[float] = None
    average_speed: Optional[float] = None
    max_speed: Optional[float] = None
    average_heartrate: Optional[float] = None
    max_heartrate: Optional[float] = None
    calories: Optional[float] = None
    device_name: Optional[str] = None
    raw: Optional[Any] = None


class WorkoutCreate(WorkoutFields):
    provider: str
    provider_workout_id: str


class WorkoutUpdate(WorkoutFields):
    provider: Optional[str] = None
    provider_workout_id: Optional[str] = None


class WorkoutOut(WorkoutFields):
    id: UUID
    user_id: UUID
    provider: str
    provider_workout_id: str
    created_at: datetime
    updated_at: datetime


class AthleteProfileFields(PeakBaseModel):
    birth_year: Optional[int] = None
    sex: Optional[str] = None
    weight_kg: Optional[float] = None
    height_cm: Optional[float] = None
    primary_sport: Optional[str] = None
    training_goal: Optional[str] = None
    dietary_preferences: Optional[str] = None
    sweat_rate_notes: Optional[str] = None
    caffeine_preference: Optional[str] = None


class AthleteProfileCreate(AthleteProfileFields):
    pass


class AthleteProfileUpdate(AthleteProfileFields):
    pass


class AthleteProfileOut(AthleteProfileFields):
    id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime


class FuelingProfileFields(PeakBaseModel):
    pre_workout_carb_target_g: Optional[float] = None
    during_workout_carb_target_g_per_hr: Optional[float] = None
    hydration_target_ml_per_hr: Optional[float] = None
    sodium_target_mg_per_hr: Optional[float] = None
    preferred_fuel_types: Optional[str] = None
    gi_sensitivity: Optional[str] = None
    caffeine_strategy: Optional[str] = None


class FuelingProfileCreate(FuelingProfileFields):
    pass


class FuelingProfileUpdate(FuelingProfileFields):
    pass


class FuelingProfileOut(FuelingProfileFields):
    id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime


class RecommendationFields(PeakBaseModel):
    workout_id: Optional[UUID] = None
    carb_grams: Optional[float] = None
    fluid_ml: Optional[float] = None
    sodium_mg: Optional[float] = None
    caffeine_mg: Optional[float] = None
    reason: Optional[str] = None
    status: Optional[str] = None


class RecommendationCreate(RecommendationFields):
    recommendation_type: str
    title: str
    body: str
    status: str = "active"


class RecommendationUpdate(RecommendationFields):
    recommendation_type: Optional[str] = None
    title: Optional[str] = None
    body: Optional[str] = None


class RecommendationOut(RecommendationFields):
    id: UUID
    user_id: UUID
    recommendation_type: str
    title: str
    body: str
    status: str
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
    if isinstance(exc, NotNullViolation):
        raise HTTPException(
            status_code=400,
            detail="Request is missing one or more required fields.",
        ) from exc
    raise HTTPException(
        status_code=500,
        detail=f"Database error ({exc.__class__.__name__})",
    ) from exc


def require_record(row: Optional[Dict[str, Any]], detail: str) -> Dict[str, Any]:
    if not row:
        raise HTTPException(status_code=404, detail=detail)
    return row


def build_update_parts(
    update_data: Dict[str, Any],
    allowed_columns: Sequence[str],
    transforms: Optional[Dict[str, Callable[[Any], Any]]] = None,
    *,
    touch_updated_at: bool = True,
) -> Tuple[List[str], List[Any]]:
    if not update_data:
        raise HTTPException(
            status_code=400,
            detail="At least one field must be provided for update.",
        )

    set_clauses: List[str] = []
    values: List[Any] = []
    transforms = transforms or {}

    for column in allowed_columns:
        if column in update_data:
            set_clauses.append(f"{column} = %s")
            value = update_data[column]
            transform = transforms.get(column)
            values.append(transform(value) if transform else value)

    if not set_clauses:
        raise HTTPException(
            status_code=400,
            detail="At least one updatable field must be provided.",
        )

    if touch_updated_at:
        set_clauses.append("updated_at = now()")

    return set_clauses, values


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
@app.get("/db/health", include_in_schema=False)
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
@app.post("/v1/users", response_model=UserOut, status_code=201, include_in_schema=False)
def create_user(payload: UserCreate) -> Dict[str, Any]:
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    insert into users (email, name)
                    values (%s, %s)
                    returning {USER_COLUMNS}
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
                    f"""
                    select {USER_COLUMNS}
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
@app.get("/v1/users/{user_id}", response_model=UserOut, include_in_schema=False)
def get_user(user_id: UUID) -> Dict[str, Any]:
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    select {USER_COLUMNS}
                    from users
                    where id = %s
                    """,
                    (user_id,),
                )
                row = cur.fetchone()
        return require_record(row, "User not found.")
    except HTTPException:
        raise
    except Exception as exc:
        handle_db_error(exc)


@app.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: UUID, payload: UserUpdate) -> Dict[str, Any]:
    update_data = payload.model_dump(exclude_unset=True)
    set_clauses, values = build_update_parts(update_data, ("email", "name"))
    values.append(user_id)
    query = f"""
        update users
        set {", ".join(set_clauses)}
        where id = %s
        returning {USER_COLUMNS}
    """

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, tuple(values))
                row = cur.fetchone()
        return require_record(row, "User not found.")
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
        require_record(row, "User not found.")
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
                    f"""
                    insert into user_connections (
                        user_id,
                        provider,
                        provider_user_id,
                        access_token,
                        refresh_token,
                        token_expires_at,
                        scopes
                    )
                    values (%s, %s, %s, %s, %s, %s, %s)
                    returning {USER_CONNECTION_COLUMNS}
                    """,
                    (
                        user_id,
                        payload.provider,
                        payload.provider_user_id,
                        payload.access_token,
                        payload.refresh_token,
                        payload.token_expires_at,
                        payload.scopes,
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
    provider: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> List[Dict[str, Any]]:
    query = f"""
        select {USER_CONNECTION_COLUMNS}
        from user_connections
        where user_id = %s
    """
    values: List[Any] = [user_id]

    if provider:
        query += " and provider = %s"
        values.append(provider)

    query += """
        order by created_at desc
        limit %s offset %s
    """
    values.extend([limit, offset])

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, tuple(values))
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
                    f"""
                    select {USER_CONNECTION_COLUMNS}
                    from user_connections
                    where id = %s
                    """,
                    (connection_id,),
                )
                row = cur.fetchone()
        return require_record(row, "Connection not found.")
    except HTTPException:
        raise
    except Exception as exc:
        handle_db_error(exc)


@app.patch("/connections/{connection_id}", response_model=UserConnectionOut)
def update_user_connection(
    connection_id: UUID, payload: UserConnectionUpdate
) -> Dict[str, Any]:
    update_data = payload.model_dump(exclude_unset=True)
    set_clauses, values = build_update_parts(
        update_data,
        (
            "provider",
            "provider_user_id",
            "access_token",
            "refresh_token",
            "token_expires_at",
            "scopes",
        ),
    )
    values.append(connection_id)
    query = f"""
        update user_connections
        set {", ".join(set_clauses)}
        where id = %s
        returning {USER_CONNECTION_COLUMNS}
    """

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, tuple(values))
                row = cur.fetchone()
        return require_record(row, "Connection not found.")
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
        require_record(row, "Connection not found.")
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
                    f"""
                    insert into workouts (
                        user_id,
                        provider,
                        provider_workout_id,
                        name,
                        sport_type,
                        start_date,
                        start_date_local,
                        timezone,
                        distance_meters,
                        moving_time_seconds,
                        elapsed_time_seconds,
                        elevation_gain_meters,
                        average_speed,
                        max_speed,
                        average_heartrate,
                        max_heartrate,
                        calories,
                        device_name,
                        raw
                    )
                    values (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    returning {WORKOUT_COLUMNS}
                    """,
                    (
                        user_id,
                        payload.provider,
                        payload.provider_workout_id,
                        payload.name,
                        payload.sport_type,
                        payload.start_date,
                        payload.start_date_local,
                        payload.timezone,
                        payload.distance_meters,
                        payload.moving_time_seconds,
                        payload.elapsed_time_seconds,
                        payload.elevation_gain_meters,
                        payload.average_speed,
                        payload.max_speed,
                        payload.average_heartrate,
                        payload.max_heartrate,
                        payload.calories,
                        payload.device_name,
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
@app.get("/v1/workouts/{user_id}", response_model=List[WorkoutOut], include_in_schema=False)
def list_workouts(
    user_id: UUID,
    provider: Optional[str] = Query(None),
    sport_type: Optional[str] = Query(None),
    start_after: Optional[datetime] = Query(None),
    start_before: Optional[datetime] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> List[Dict[str, Any]]:
    query = f"""
        select {WORKOUT_COLUMNS}
        from workouts
        where user_id = %s
    """
    values: List[Any] = [user_id]

    if provider:
        query += " and provider = %s"
        values.append(provider)
    if sport_type:
        query += " and sport_type = %s"
        values.append(sport_type)
    if start_after:
        query += " and start_date >= %s"
        values.append(start_after)
    if start_before:
        query += " and start_date <= %s"
        values.append(start_before)

    query += """
        order by start_date desc nulls last, created_at desc
        limit %s offset %s
    """
    values.extend([limit, offset])

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, tuple(values))
                rows = cur.fetchall()
        return rows
    except HTTPException:
        raise
    except Exception as exc:
        handle_db_error(exc)


@app.get("/workouts/{workout_id}", response_model=WorkoutOut)
@app.get("/v1/workout/{workout_id}", response_model=WorkoutOut, include_in_schema=False)
def get_workout(workout_id: UUID) -> Dict[str, Any]:
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    select {WORKOUT_COLUMNS}
                    from workouts
                    where id = %s
                    """,
                    (workout_id,),
                )
                row = cur.fetchone()
        return require_record(row, "Workout not found.")
    except HTTPException:
        raise
    except Exception as exc:
        handle_db_error(exc)


@app.patch("/workouts/{workout_id}", response_model=WorkoutOut)
def update_workout(workout_id: UUID, payload: WorkoutUpdate) -> Dict[str, Any]:
    update_data = payload.model_dump(exclude_unset=True)
    set_clauses, values = build_update_parts(
        update_data,
        (
            "provider",
            "provider_workout_id",
            "name",
            "sport_type",
            "start_date",
            "start_date_local",
            "timezone",
            "distance_meters",
            "moving_time_seconds",
            "elapsed_time_seconds",
            "elevation_gain_meters",
            "average_speed",
            "max_speed",
            "average_heartrate",
            "max_heartrate",
            "calories",
            "device_name",
            "raw",
        ),
        transforms={"raw": to_jsonb_value},
    )
    values.append(workout_id)
    query = f"""
        update workouts
        set {", ".join(set_clauses)}
        where id = %s
        returning {WORKOUT_COLUMNS}
    """

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, tuple(values))
                row = cur.fetchone()
        return require_record(row, "Workout not found.")
    except HTTPException:
        raise
    except Exception as exc:
        handle_db_error(exc)


@app.delete("/workouts/{workout_id}", status_code=204)
def delete_workout(workout_id: UUID) -> Response:
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "delete from workouts where id = %s returning id",
                    (workout_id,),
                )
                row = cur.fetchone()
        require_record(row, "Workout not found.")
        return Response(status_code=204)
    except HTTPException:
        raise
    except Exception as exc:
        handle_db_error(exc)


@app.post("/users/{user_id}/athlete-profile", response_model=AthleteProfileOut, status_code=201)
def create_athlete_profile(
    user_id: UUID, payload: AthleteProfileCreate
) -> Dict[str, Any]:
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    insert into athlete_profiles (
                        user_id,
                        birth_year,
                        sex,
                        weight_kg,
                        height_cm,
                        primary_sport,
                        training_goal,
                        dietary_preferences,
                        sweat_rate_notes,
                        caffeine_preference
                    )
                    values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    returning {ATHLETE_PROFILE_COLUMNS}
                    """,
                    (
                        user_id,
                        payload.birth_year,
                        payload.sex,
                        payload.weight_kg,
                        payload.height_cm,
                        payload.primary_sport,
                        payload.training_goal,
                        payload.dietary_preferences,
                        payload.sweat_rate_notes,
                        payload.caffeine_preference,
                    ),
                )
                row = cur.fetchone()
        return row
    except HTTPException:
        raise
    except Exception as exc:
        handle_db_error(exc)


@app.get("/users/{user_id}/athlete-profile", response_model=AthleteProfileOut)
def get_athlete_profile_by_user(user_id: UUID) -> Dict[str, Any]:
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    select {ATHLETE_PROFILE_COLUMNS}
                    from athlete_profiles
                    where user_id = %s
                    """,
                    (user_id,),
                )
                row = cur.fetchone()
        return require_record(row, "Athlete profile not found.")
    except HTTPException:
        raise
    except Exception as exc:
        handle_db_error(exc)


@app.get("/athlete-profiles/{profile_id}", response_model=AthleteProfileOut)
def get_athlete_profile(profile_id: UUID) -> Dict[str, Any]:
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    select {ATHLETE_PROFILE_COLUMNS}
                    from athlete_profiles
                    where id = %s
                    """,
                    (profile_id,),
                )
                row = cur.fetchone()
        return require_record(row, "Athlete profile not found.")
    except HTTPException:
        raise
    except Exception as exc:
        handle_db_error(exc)


@app.patch("/athlete-profiles/{profile_id}", response_model=AthleteProfileOut)
def update_athlete_profile(
    profile_id: UUID, payload: AthleteProfileUpdate
) -> Dict[str, Any]:
    update_data = payload.model_dump(exclude_unset=True)
    set_clauses, values = build_update_parts(
        update_data,
        (
            "birth_year",
            "sex",
            "weight_kg",
            "height_cm",
            "primary_sport",
            "training_goal",
            "dietary_preferences",
            "sweat_rate_notes",
            "caffeine_preference",
        ),
    )
    values.append(profile_id)
    query = f"""
        update athlete_profiles
        set {", ".join(set_clauses)}
        where id = %s
        returning {ATHLETE_PROFILE_COLUMNS}
    """

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, tuple(values))
                row = cur.fetchone()
        return require_record(row, "Athlete profile not found.")
    except HTTPException:
        raise
    except Exception as exc:
        handle_db_error(exc)


@app.delete("/athlete-profiles/{profile_id}", status_code=204)
def delete_athlete_profile(profile_id: UUID) -> Response:
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "delete from athlete_profiles where id = %s returning id",
                    (profile_id,),
                )
                row = cur.fetchone()
        require_record(row, "Athlete profile not found.")
        return Response(status_code=204)
    except HTTPException:
        raise
    except Exception as exc:
        handle_db_error(exc)


@app.post("/users/{user_id}/fueling-profile", response_model=FuelingProfileOut, status_code=201)
def create_fueling_profile(
    user_id: UUID, payload: FuelingProfileCreate
) -> Dict[str, Any]:
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    insert into fueling_profiles (
                        user_id,
                        pre_workout_carb_target_g,
                        during_workout_carb_target_g_per_hr,
                        hydration_target_ml_per_hr,
                        sodium_target_mg_per_hr,
                        preferred_fuel_types,
                        gi_sensitivity,
                        caffeine_strategy
                    )
                    values (%s, %s, %s, %s, %s, %s, %s, %s)
                    returning {FUELING_PROFILE_COLUMNS}
                    """,
                    (
                        user_id,
                        payload.pre_workout_carb_target_g,
                        payload.during_workout_carb_target_g_per_hr,
                        payload.hydration_target_ml_per_hr,
                        payload.sodium_target_mg_per_hr,
                        payload.preferred_fuel_types,
                        payload.gi_sensitivity,
                        payload.caffeine_strategy,
                    ),
                )
                row = cur.fetchone()
        return row
    except HTTPException:
        raise
    except Exception as exc:
        handle_db_error(exc)


@app.get("/users/{user_id}/fueling-profile", response_model=FuelingProfileOut)
@app.get("/v1/fueling-profile/{user_id}", response_model=FuelingProfileOut, include_in_schema=False)
def get_fueling_profile_by_user(user_id: UUID) -> Dict[str, Any]:
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    select {FUELING_PROFILE_COLUMNS}
                    from fueling_profiles
                    where user_id = %s
                    """,
                    (user_id,),
                )
                row = cur.fetchone()
        return require_record(row, "Fueling profile not found.")
    except HTTPException:
        raise
    except Exception as exc:
        handle_db_error(exc)


@app.get("/fueling-profiles/{profile_id}", response_model=FuelingProfileOut)
def get_fueling_profile(profile_id: UUID) -> Dict[str, Any]:
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    select {FUELING_PROFILE_COLUMNS}
                    from fueling_profiles
                    where id = %s
                    """,
                    (profile_id,),
                )
                row = cur.fetchone()
        return require_record(row, "Fueling profile not found.")
    except HTTPException:
        raise
    except Exception as exc:
        handle_db_error(exc)


@app.patch("/fueling-profiles/{profile_id}", response_model=FuelingProfileOut)
def update_fueling_profile(
    profile_id: UUID, payload: FuelingProfileUpdate
) -> Dict[str, Any]:
    update_data = payload.model_dump(exclude_unset=True)
    set_clauses, values = build_update_parts(
        update_data,
        (
            "pre_workout_carb_target_g",
            "during_workout_carb_target_g_per_hr",
            "hydration_target_ml_per_hr",
            "sodium_target_mg_per_hr",
            "preferred_fuel_types",
            "gi_sensitivity",
            "caffeine_strategy",
        ),
    )
    values.append(profile_id)
    query = f"""
        update fueling_profiles
        set {", ".join(set_clauses)}
        where id = %s
        returning {FUELING_PROFILE_COLUMNS}
    """

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, tuple(values))
                row = cur.fetchone()
        return require_record(row, "Fueling profile not found.")
    except HTTPException:
        raise
    except Exception as exc:
        handle_db_error(exc)


@app.delete("/fueling-profiles/{profile_id}", status_code=204)
def delete_fueling_profile(profile_id: UUID) -> Response:
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "delete from fueling_profiles where id = %s returning id",
                    (profile_id,),
                )
                row = cur.fetchone()
        require_record(row, "Fueling profile not found.")
        return Response(status_code=204)
    except HTTPException:
        raise
    except Exception as exc:
        handle_db_error(exc)


@app.post("/users/{user_id}/recommendations", response_model=RecommendationOut, status_code=201)
def create_recommendation(
    user_id: UUID, payload: RecommendationCreate
) -> Dict[str, Any]:
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    insert into recommendations (
                        user_id,
                        workout_id,
                        recommendation_type,
                        title,
                        body,
                        carb_grams,
                        fluid_ml,
                        sodium_mg,
                        caffeine_mg,
                        reason,
                        status
                    )
                    values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    returning {RECOMMENDATION_COLUMNS}
                    """,
                    (
                        user_id,
                        payload.workout_id,
                        payload.recommendation_type,
                        payload.title,
                        payload.body,
                        payload.carb_grams,
                        payload.fluid_ml,
                        payload.sodium_mg,
                        payload.caffeine_mg,
                        payload.reason,
                        payload.status,
                    ),
                )
                row = cur.fetchone()
        return row
    except HTTPException:
        raise
    except Exception as exc:
        handle_db_error(exc)


@app.get("/users/{user_id}/recommendations", response_model=List[RecommendationOut])
@app.get("/v1/recommendations/{user_id}", response_model=List[RecommendationOut], include_in_schema=False)
def list_recommendations(
    user_id: UUID,
    workout_id: Optional[UUID] = Query(None),
    recommendation_type: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> List[Dict[str, Any]]:
    query = f"""
        select {RECOMMENDATION_COLUMNS}
        from recommendations
        where user_id = %s
    """
    values: List[Any] = [user_id]

    if workout_id:
        query += " and workout_id = %s"
        values.append(workout_id)
    if recommendation_type:
        query += " and recommendation_type = %s"
        values.append(recommendation_type)
    if status_filter:
        query += " and status = %s"
        values.append(status_filter)

    query += """
        order by created_at desc
        limit %s offset %s
    """
    values.extend([limit, offset])

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, tuple(values))
                rows = cur.fetchall()
        return rows
    except HTTPException:
        raise
    except Exception as exc:
        handle_db_error(exc)


@app.get("/recommendations/{recommendation_id}", response_model=RecommendationOut)
def get_recommendation(recommendation_id: UUID) -> Dict[str, Any]:
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    select {RECOMMENDATION_COLUMNS}
                    from recommendations
                    where id = %s
                    """,
                    (recommendation_id,),
                )
                row = cur.fetchone()
        return require_record(row, "Recommendation not found.")
    except HTTPException:
        raise
    except Exception as exc:
        handle_db_error(exc)


@app.patch("/recommendations/{recommendation_id}", response_model=RecommendationOut)
def update_recommendation(
    recommendation_id: UUID, payload: RecommendationUpdate
) -> Dict[str, Any]:
    update_data = payload.model_dump(exclude_unset=True)
    set_clauses, values = build_update_parts(
        update_data,
        (
            "workout_id",
            "recommendation_type",
            "title",
            "body",
            "carb_grams",
            "fluid_ml",
            "sodium_mg",
            "caffeine_mg",
            "reason",
            "status",
        ),
        touch_updated_at=False,
    )
    values.append(recommendation_id)
    query = f"""
        update recommendations
        set {", ".join(set_clauses)}
        where id = %s
        returning {RECOMMENDATION_COLUMNS}
    """

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, tuple(values))
                row = cur.fetchone()
        return require_record(row, "Recommendation not found.")
    except HTTPException:
        raise
    except Exception as exc:
        handle_db_error(exc)


@app.delete("/recommendations/{recommendation_id}", status_code=204)
def delete_recommendation(recommendation_id: UUID) -> Response:
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "delete from recommendations where id = %s returning id",
                    (recommendation_id,),
                )
                row = cur.fetchone()
        require_record(row, "Recommendation not found.")
        return Response(status_code=204)
    except HTTPException:
        raise
    except Exception as exc:
        handle_db_error(exc)
