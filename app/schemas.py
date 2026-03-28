"""Pydantic models shared across routers."""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class PeakBaseModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class UserCreate(PeakBaseModel):
    email: str
    name: Optional[str] = None


class UserUpdate(PeakBaseModel):
    email: Optional[str] = None
    name: Optional[str] = None


class UserOut(PeakBaseModel):
    id: UUID
    email: str
    name: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class UserConnectionFields(PeakBaseModel):
    provider_user_id: Optional[str] = None
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    token_expires_at: Optional[datetime] = None
    scopes: Optional[str] = None


class UserConnectionCreate(UserConnectionFields):
    provider: str


class UserConnectionUpdate(UserConnectionFields):
    provider: Optional[str] = None


class UserConnectionOut(UserConnectionFields):
    id: UUID
    user_id: UUID
    provider: str
    created_at: datetime
    updated_at: datetime


class WorkoutFields(PeakBaseModel):
    name: Optional[str] = None
    sport_type: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("sport_type", "sport"),
    )
    start_date: Optional[datetime] = Field(
        default=None,
        validation_alias=AliasChoices("start_date", "started_at"),
    )
    start_date_local: Optional[datetime] = None
    timezone: Optional[str] = None
    distance_meters: Optional[float] = None
    moving_time_seconds: Optional[int] = Field(
        default=None,
        validation_alias=AliasChoices("moving_time_seconds", "duration_seconds"),
    )
    elapsed_time_seconds: Optional[int] = None
    elevation_gain_meters: Optional[float] = None
    average_speed: Optional[float] = None
    max_speed: Optional[float] = None
    average_heartrate: Optional[float] = None
    max_heartrate: Optional[float] = None
    calories: Optional[float] = None
    device_name: Optional[str] = None
    raw: Optional[Any] = None


class WorkoutCreate(WorkoutFields):
    provider: str
    provider_workout_id: str


class WorkoutUpdate(WorkoutFields):
    provider: Optional[str] = None
    provider_workout_id: Optional[str] = None


class WorkoutOut(WorkoutFields):
    id: UUID
    user_id: UUID
    provider: str
    provider_workout_id: str
    created_at: datetime
    updated_at: datetime


class AthleteProfileFields(PeakBaseModel):
    birth_year: Optional[int] = None
    sex: Optional[str] = None
    weight_kg: Optional[float] = None
    height_cm: Optional[float] = None
    primary_sport: Optional[str] = None
    training_goal: Optional[str] = None
    dietary_preferences: Optional[str] = None
    sweat_rate_notes: Optional[str] = None
    caffeine_preference: Optional[str] = None


class AthleteProfileCreate(AthleteProfileFields):
    pass


class AthleteProfileUpdate(AthleteProfileFields):
    pass


class AthleteProfileOut(AthleteProfileFields):
    id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime


class FuelingProfileFields(PeakBaseModel):
    pre_workout_carb_target_g: Optional[float] = None
    during_workout_carb_target_g_per_hr: Optional[float] = None
    hydration_target_ml_per_hr: Optional[float] = None
    sodium_target_mg_per_hr: Optional[float] = None
    preferred_fuel_types: Optional[str] = None
    gi_sensitivity: Optional[str] = None
    caffeine_strategy: Optional[str] = None


class FuelingProfileCreate(FuelingProfileFields):
    pass


class FuelingProfileUpdate(FuelingProfileFields):
    pass


class FuelingProfileOut(FuelingProfileFields):
    id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime


class RecommendationFields(PeakBaseModel):
    workout_id: Optional[UUID] = None
    carb_grams: Optional[float] = None
    fluid_ml: Optional[float] = None
    sodium_mg: Optional[float] = None
    caffeine_mg: Optional[float] = None
    reason: Optional[str] = None
    status: Optional[str] = None


class RecommendationCreate(RecommendationFields):
    recommendation_type: str
    title: str
    body: str
    status: str = "active"


class RecommendationUpdate(RecommendationFields):
    recommendation_type: Optional[str] = None
    title: Optional[str] = None
    body: Optional[str] = None


class RecommendationOut(RecommendationFields):
    id: UUID
    user_id: UUID
    recommendation_type: str
    title: str
    body: str
    status: str
    created_at: datetime


class StravaConnectStartOut(PeakBaseModel):
    authorize_url: str
    scope: str
    state: str
    redirect_uri: str


class StravaCallbackOut(PeakBaseModel):
    message: str
    code: Optional[str] = None
    scope: Optional[str] = None
    state: Optional[str] = None
    error: Optional[str] = None
