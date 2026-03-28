"""User CRUD endpoints."""

from typing import Any, Dict, List
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response

from app.db import USER_COLUMNS, build_update_parts, get_connection, handle_db_error, require_record
from app.schemas import UserCreate, UserOut, UserUpdate

router = APIRouter(tags=["Users"])


@router.post("/users", response_model=UserOut, status_code=201)
@router.post("/v1/users", response_model=UserOut, status_code=201, include_in_schema=False)
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


@router.get("/users", response_model=List[UserOut])
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


@router.get("/users/{user_id}", response_model=UserOut)
@router.get("/v1/users/{user_id}", response_model=UserOut, include_in_schema=False)
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


@router.patch("/users/{user_id}", response_model=UserOut)
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


@router.delete("/users/{user_id}", status_code=204)
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
