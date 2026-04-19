import json
import os
from typing import Any, Dict, List
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from fastapi import HTTPException, status


STRAVA_AUTHORIZATION_URL = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL = "https://www.strava.com/api/v3/oauth/token"
STRAVA_ACTIVITIES_URL = "https://www.strava.com/api/v3/athlete/activities"
DEFAULT_STRAVA_SCOPES = "read,activity:read_all"
REQUEST_TIMEOUT_SECONDS = 10


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"{name} is required before Strava OAuth can be used.",
        )
    return value


def get_strava_client_id() -> str:
    return _required_env("STRAVA_CLIENT_ID")


def get_strava_client_secret() -> str:
    return _required_env("STRAVA_CLIENT_SECRET")


def get_strava_redirect_uri() -> str:
    return _required_env("STRAVA_REDIRECT_URI")


def get_strava_scopes() -> str:
    return os.getenv("STRAVA_SCOPES", DEFAULT_STRAVA_SCOPES).strip()


def build_authorization_url(state: str) -> str:
    query = urlencode(
        {
            "approval_prompt": "auto",
            "client_id": get_strava_client_id(),
            "redirect_uri": get_strava_redirect_uri(),
            "response_type": "code",
            "scope": get_strava_scopes(),
            "state": state,
        }
    )
    return f"{STRAVA_AUTHORIZATION_URL}?{query}"


def _post_form_json(url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    request = Request(
        url,
        data=urlencode(payload).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Strava token request failed: {detail}",
        ) from exc
    except (URLError, TimeoutError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Strava token request failed.",
        ) from exc


def exchange_code_for_token(code: str) -> Dict[str, Any]:
    return _post_form_json(
        STRAVA_TOKEN_URL,
        {
            "client_id": get_strava_client_id(),
            "client_secret": get_strava_client_secret(),
            "code": code,
            "grant_type": "authorization_code",
        },
    )


def refresh_access_token(refresh_token: str) -> Dict[str, Any]:
    return _post_form_json(
        STRAVA_TOKEN_URL,
        {
            "client_id": get_strava_client_id(),
            "client_secret": get_strava_client_secret(),
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
    )


def fetch_athlete_activities(access_token: str, *, per_page: int = 30) -> List[Dict[str, Any]]:
    query = urlencode({"per_page": per_page})
    request = Request(
        f"{STRAVA_ACTIVITIES_URL}?{query}",
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {access_token}",
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            data = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Strava activities request failed: {detail}",
        ) from exc
    except (URLError, TimeoutError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Strava activities request failed.",
        ) from exc

    if not isinstance(data, list):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Strava activities response was not a list.",
        )
    return data
