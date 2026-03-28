"""FastAPI application assembly."""

from fastapi import Depends, FastAPI

from app.dependencies import require_api_key
from app.routers import (
    connections,
    health,
    profiles,
    recommendations,
    strava,
    users,
    workouts,
)


def create_app() -> FastAPI:
    application = FastAPI(
        title="Peak V1 API",
        description="Backend API for Peak application",
        version="1.0.0",
        dependencies=[Depends(require_api_key)],
    )

    application.include_router(health.router)
    application.include_router(users.router)
    application.include_router(connections.router)
    application.include_router(workouts.router)
    application.include_router(profiles.router)
    application.include_router(recommendations.router)
    application.include_router(strava.router)

    return application


app = create_app()
