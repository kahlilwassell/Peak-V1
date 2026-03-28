"""Placeholder Strava OAuth helpers for future integration work."""

from secrets import token_urlsafe
from typing import Dict, List, Optional
from urllib.parse import urlencode
from uuid import UUID

from app.config import (
    STRAVA_CLIENT_ID_ENV_VAR,
    STRAVA_CLIENT_SECRET_ENV_VAR,
    STRAVA_REDIRECT_URI_ENV_VAR,
    get_optional_env,
)

STRAVA_AUTHORIZE_URL = "https://www.strava.com/oauth/authorize"
DEFAULT_STRAVA_SCOPES = "activity:read_all,profile:read_all"


def get_strava_oauth_config() -> Dict[str, Optional[str]]:
    return {
        "client_id": get_optional_env(STRAVA_CLIENT_ID_ENV_VAR),
        "client_secret": get_optional_env(STRAVA_CLIENT_SECRET_ENV_VAR),
        "redirect_uri": get_optional_env(STRAVA_REDIRECT_URI_ENV_VAR),
    }


def get_missing_start_config() -> List[str]:
    config = get_strava_oauth_config()
    missing: List[str] = []

    if not config["client_id"]:
        missing.append(STRAVA_CLIENT_ID_ENV_VAR)
    if not config["redirect_uri"]:
        missing.append(STRAVA_REDIRECT_URI_ENV_VAR)

    return missing


def build_connect_state(user_id: UUID) -> str:
    return f"{user_id}:{token_urlsafe(24)}"


def build_authorize_url(*, state: str, scope: str = DEFAULT_STRAVA_SCOPES) -> str:
    missing = get_missing_start_config()
    if missing:
        raise ValueError(
            f"Missing Strava OAuth configuration: {', '.join(missing)}"
        )

    config = get_strava_oauth_config()
    params = {
        "client_id": config["client_id"],
        "redirect_uri": config["redirect_uri"],
        "response_type": "code",
        "approval_prompt": "auto",
        "scope": scope,
        "state": state,
    }
    return f"{STRAVA_AUTHORIZE_URL}?{urlencode(params)}"
