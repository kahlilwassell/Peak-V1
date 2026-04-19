from datetime import date, datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, model_validator


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=1, max_length=100)


class UserUpdate(BaseModel):
    """All fields are optional — only supplied fields are updated."""
    height: Optional[int] = Field(default=None, ge=0)
    weight: Optional[int] = Field(default=None, ge=0)
    password: Optional[str] = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode="after")
    def at_least_one_field(self) -> "UserUpdate":
        if self.height is None and self.weight is None and self.password is None:
            raise ValueError("At least one field must be provided for an update.")
        return self


class UserCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=1, max_length=100)
    dob: date
    height: int = Field(..., ge=0)
    weight: int = Field(..., ge=0)
    is_male: bool


class UserRead(BaseModel):
    id: str
    name: str
    email: str
    created_at: datetime
    dob: date
    height: int
    weight: int
    is_male: bool


class LoginResponse(UserRead):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


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


class RunningPlanCreate(BaseModel):
    planned_at: datetime = Field(..., description="Scheduled run date/time (must be in the future)")
    distance_km: float = Field(..., gt=0, description="Planned distance in kilometres")
    speed_kph: float = Field(..., gt=0, description="Intended speed in km/h")
    notes: Optional[str] = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def planned_at_must_be_future(self) -> "RunningPlanCreate":
        from datetime import timezone
        now = datetime.now(timezone.utc)
        planned = self.planned_at
        if planned.tzinfo is None:
            planned = planned.replace(tzinfo=timezone.utc)
        if planned <= now:
            raise ValueError("planned_at must be a future date and time.")
        return self


class RunningPlanRead(BaseModel):
    id: str
    user_id: str
    planned_at: datetime
    distance_km: float
    speed_kph: float
    notes: Optional[str] = None
    created_at: datetime


class StravaConnectStartOut(BaseModel):
    authorization_url: str


class StravaConnectionRead(BaseModel):
    id: str
    user_id: str
    strava_athlete_id: str
    strava_username: Optional[str] = None
    scope: Optional[str] = None
    expires_at: datetime
    last_synced_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class StravaSyncOut(BaseModel):
    imported_workouts: int
    last_synced_at: datetime
