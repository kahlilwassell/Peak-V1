"""Athlete and fueling profile endpoints."""

from typing import Any, Dict
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response

from app.db import (
    ATHLETE_PROFILE_COLUMNS,
    FUELING_PROFILE_COLUMNS,
    build_update_parts,
    get_connection,
    handle_db_error,
    require_record,
)
from app.schemas import (
    AthleteProfileCreate,
    AthleteProfileOut,
    AthleteProfileUpdate,
    FuelingProfileCreate,
    FuelingProfileOut,
    FuelingProfileUpdate,
)

router = APIRouter(tags=["Profiles"])


@router.post("/users/{user_id}/athlete-profile", response_model=AthleteProfileOut, status_code=201)
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


@router.get("/users/{user_id}/athlete-profile", response_model=AthleteProfileOut)
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


@router.get("/athlete-profiles/{profile_id}", response_model=AthleteProfileOut)
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


@router.patch("/athlete-profiles/{profile_id}", response_model=AthleteProfileOut)
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


@router.delete("/athlete-profiles/{profile_id}", status_code=204)
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


@router.post("/users/{user_id}/fueling-profile", response_model=FuelingProfileOut, status_code=201)
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


@router.get("/users/{user_id}/fueling-profile", response_model=FuelingProfileOut)
@router.get("/v1/fueling-profile/{user_id}", response_model=FuelingProfileOut, include_in_schema=False)
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


@router.get("/fueling-profiles/{profile_id}", response_model=FuelingProfileOut)
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


@router.patch("/fueling-profiles/{profile_id}", response_model=FuelingProfileOut)
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


@router.delete("/fueling-profiles/{profile_id}", status_code=204)
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
