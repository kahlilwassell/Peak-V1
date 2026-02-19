"""
Peak V1 - FastAPI Backend
A simple FastAPI application with a health check endpoint.
"""

from fastapi import FastAPI

app = FastAPI(
    title="Peak V1 API",
    description="Backend API for Peak application",
    version="1.0.0"
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
