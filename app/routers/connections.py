"""User connection CRUD endpoints."""

from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response

from app.db import (
    USER_CONNECTION_COLUMNS,
    build_update_parts,
    get_connection,
    handle_db_error,
    require_record,
)
from app.schemas import UserConnectionCreate, UserConnectionOut, UserConnectionUpdate

router = APIRouter(tags=["Connections"])


@router.post("/users/{user_id}/connections", response_model=UserConnectionOut, status_code=201)
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


@router.get("/users/{user_id}/connections", response_model=List[UserConnectionOut])
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


@router.get("/connections/{connection_id}", response_model=UserConnectionOut)
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


@router.patch("/connections/{connection_id}", response_model=UserConnectionOut)
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


@router.delete("/connections/{connection_id}", status_code=204)
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
