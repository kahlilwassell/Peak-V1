"""Database helpers and shared SQL metadata."""

from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import psycopg
from fastapi import HTTPException
from psycopg.errors import ForeignKeyViolation, NotNullViolation, UniqueViolation
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.config import get_database_url

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


def get_connection():
    try:
        return psycopg.connect(get_database_url(), row_factory=dict_row)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


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
