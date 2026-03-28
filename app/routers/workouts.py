"""Workout CRUD endpoints."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response

from app.db import (
    WORKOUT_COLUMNS,
    build_update_parts,
    get_connection,
    handle_db_error,
    require_record,
    to_jsonb_value,
)
from app.schemas import WorkoutCreate, WorkoutOut, WorkoutUpdate

router = APIRouter(tags=["Workouts"])


@router.post("/users/{user_id}/workouts", response_model=WorkoutOut, status_code=201)
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


@router.get("/users/{user_id}/workouts", response_model=List[WorkoutOut])
@router.get("/v1/workouts/{user_id}", response_model=List[WorkoutOut], include_in_schema=False)
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


@router.get("/workouts/{workout_id}", response_model=WorkoutOut)
@router.get("/v1/workout/{workout_id}", response_model=WorkoutOut, include_in_schema=False)
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


@router.patch("/workouts/{workout_id}", response_model=WorkoutOut)
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


@router.delete("/workouts/{workout_id}", status_code=204)
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
