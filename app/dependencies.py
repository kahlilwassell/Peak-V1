"""FastAPI dependencies shared across routers."""

from typing import Optional

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from app.config import PEAK_API_KEY_ENV_VAR, get_optional_env

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(api_key: Optional[str] = Security(api_key_header)) -> None:
    """Require a valid API key header for all endpoints."""
    expected_api_key = get_optional_env(PEAK_API_KEY_ENV_VAR)
    if not expected_api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{PEAK_API_KEY_ENV_VAR} is not configured",
        )

    if api_key != expected_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
