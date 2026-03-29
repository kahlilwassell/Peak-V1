from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    email: str = Field(..., min_length=3, max_length=255)


class UserRead(BaseModel):
    id: str
    name: str
    email: str
    created_at: datetime


class WorkoutCreate(BaseModel):
    strava_activity_id: Optional[str] = Field(default=None, max_length=100)
    name: str = Field(..., min_length=1, max_length=255)
    sport_type: Optional[str] = Field(default=None, max_length=100)
    start_date: datetime
    distance_meters: Optional[float] = Field(default=None, ge=0)
    moving_time_seconds: Optional[int] = Field(default=None, ge=0)
    calories: Optional[int] = Field(default=None, ge=0)
    notes: Optional[str] = Field(default=None, max_length=2000)
    raw_data: Optional[Dict[str, Any]] = None


class WorkoutRead(BaseModel):
    id: str
    user_id: str
    source: str
    strava_activity_id: Optional[str] = None
    name: str
    sport_type: Optional[str] = None
    start_date: datetime
    distance_meters: Optional[float] = None
    moving_time_seconds: Optional[int] = None
    calories: Optional[int] = None
    notes: Optional[str] = None
    raw_data: Optional[Dict[str, Any]] = None
    created_at: datetime


class FuelingPlanCreate(BaseModel):
    workout_id: Optional[str] = None
    goal: str = Field(..., min_length=1, max_length=255)
    carbs_per_hour: Optional[int] = Field(default=None, ge=0)
    hydration_ml_per_hour: Optional[int] = Field(default=None, ge=0)
    sodium_mg_per_hour: Optional[int] = Field(default=None, ge=0)
    notes: Optional[str] = Field(default=None, max_length=2000)


class FuelingPlanRead(BaseModel):
    id: str
    user_id: str
    workout_id: Optional[str] = None
    goal: str
    carbs_per_hour: Optional[int] = None
    hydration_ml_per_hour: Optional[int] = None
    sodium_mg_per_hour: Optional[int] = None
    notes: Optional[str] = None
    created_at: datetime
