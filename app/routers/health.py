"""System and health endpoints."""

from typing import Any, Dict
from urllib.parse import urlparse

import psycopg
from fastapi import APIRouter, HTTPException

from app.config import get_database_url

router = APIRouter(tags=["System"])


@router.get("/")
async def root() -> Dict[str, str]:
    return {"message": "Welcome to Peak V1 API"}


@router.get("/health")
async def health_check() -> Dict[str, str]:
    return {"status": "healthy", "service": "Peak V1 API"}


@router.get("/health/db")
@router.get("/db/health", include_in_schema=False)
def database_health_check() -> Dict[str, Any]:
    try:
        database_url = get_database_url()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    try:
        with psycopg.connect(database_url, connect_timeout=5) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                value = cur.fetchone()
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Database connection failed ({exc.__class__.__name__})",
        ) from exc

    parsed = urlparse(database_url)
    return {
        "status": "healthy",
        "service": "Peak V1 API",
        "database": "connected",
        "check": value[0] if value else None,
        "host": parsed.hostname,
        "port": parsed.port,
        "name": parsed.path.lstrip("/") or None,
    }
