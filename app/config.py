"""Application configuration helpers."""

import os
from typing import Optional

DATABASE_URL_ENV_VAR = "DATABASE_URL"
PEAK_API_KEY_ENV_VAR = "PEAK_API_KEY"
STRAVA_CLIENT_ID_ENV_VAR = "STRAVA_CLIENT_ID"
STRAVA_CLIENT_SECRET_ENV_VAR = "STRAVA_CLIENT_SECRET"
STRAVA_REDIRECT_URI_ENV_VAR = "STRAVA_REDIRECT_URI"


def get_optional_env(name: str) -> Optional[str]:
    value = os.getenv(name)
    return value or None


def get_required_env(name: str) -> str:
    value = get_optional_env(name)
    if not value:
        raise RuntimeError(f"{name} is not configured")
    return value


def get_database_url() -> str:
    return get_required_env(DATABASE_URL_ENV_VAR)
