"""Recommendation CRUD endpoints."""

from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response

from app.db import (
    RECOMMENDATION_COLUMNS,
    build_update_parts,
    get_connection,
    handle_db_error,
    require_record,
)
from app.schemas import RecommendationCreate, RecommendationOut, RecommendationUpdate

router = APIRouter(tags=["Recommendations"])


@router.post("/users/{user_id}/recommendations", response_model=RecommendationOut, status_code=201)
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


@router.get("/users/{user_id}/recommendations", response_model=List[RecommendationOut])
@router.get("/v1/recommendations/{user_id}", response_model=List[RecommendationOut], include_in_schema=False)
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


@router.get("/recommendations/{recommendation_id}", response_model=RecommendationOut)
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


@router.patch("/recommendations/{recommendation_id}", response_model=RecommendationOut)
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


@router.delete("/recommendations/{recommendation_id}", status_code=204)
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
