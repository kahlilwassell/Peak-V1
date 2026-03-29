"""Placeholder Strava OAuth routes."""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from app.schemas import StravaCallbackOut, StravaConnectStartOut
from app.services.strava import (
    DEFAULT_STRAVA_SCOPES,
    build_authorize_url,
    build_connect_state,
    get_strava_oauth_config,
)

router = APIRouter(tags=["Strava"])


@router.get("/v1/strava/connect/start", response_model=StravaConnectStartOut)
def start_strava_connect(
    user_id: UUID,
    scope: str = Query(DEFAULT_STRAVA_SCOPES),
) -> StravaConnectStartOut:
    state = build_connect_state(user_id)

    try:
        authorize_url = build_authorize_url(state=state, scope=scope)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    config = get_strava_oauth_config()
    return StravaConnectStartOut(
        authorize_url=authorize_url,
        scope=scope,
        state=state,
        redirect_uri=config["redirect_uri"] or "",
    )


@router.get(
    "/v1/strava/connect/callback",
    response_model=StravaCallbackOut,
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
)
def strava_connect_callback(
    code: Optional[str] = Query(None),
    scope: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
) -> StravaCallbackOut:
    return StravaCallbackOut(
        message=(
            "Strava OAuth callback scaffolded. "
            "Token exchange and persistence are not implemented yet."
        ),
        code=code,
        scope=scope,
        state=state,
        error=error,
    )
