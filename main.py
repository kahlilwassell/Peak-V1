"""
Peak V1 - FastAPI Backend
A simple FastAPI application with a health check endpoint.
"""

import os
from typing import Optional
from urllib.parse import urlparse

import psycopg
from fastapi import Depends
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi import Security
from fastapi import status
from fastapi.security import APIKeyHeader

API_KEY_ENV_VAR = "PEAK_API_KEY"
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(api_key: Optional[str] = Security(api_key_header)) -> None:
    """Require a valid API key header for all endpoints."""
    expected_api_key = os.getenv(API_KEY_ENV_VAR)
    if not expected_api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{API_KEY_ENV_VAR} is not configured",
        )

    if api_key != expected_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )

app = FastAPI(
    title="Peak V1 API",
    description="Backend API for Peak application",
    version="1.0.0",
    dependencies=[Depends(require_api_key)],
)


@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "Welcome to Peak V1 API"}


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "Peak V1 API"
    }


@app.get("/health/db")
def database_health_check():
    """Database health check endpoint."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise HTTPException(status_code=500, detail="DATABASE_URL is not configured")

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
