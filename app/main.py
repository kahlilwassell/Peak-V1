"""
Minimal Peak V1 API.

This version keeps the backend intentionally small:
- users
- Strava workout records
- fueling plans
"""

import json
import os
from contextlib import asynccontextmanager, closing
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, Response, status
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth import (
    ACCESS_TOKEN_TTL_SECONDS,
    create_access_token,
    create_oauth_state,
    hash_password,
    verify_access_token,
    verify_oauth_state,
    verify_password,
)
from app.db import (
    INTEGRITY_ERRORS,
    execute,
    fetch_all,
    fetch_strava_connection_by_user_id,
    fetch_one,
    fetch_fueling_plan_or_404,
    fetch_running_plan_or_404,
    fetch_user_or_404,
    fetch_workout_or_404,
    get_database_backend,
    get_connection,
    init_db,
    serialize_fueling_plan,
    serialize_running_plan,
    serialize_strava_connection,
    serialize_user,
    serialize_workout,
)
from app.schemas import (
    FuelingPlanCreate,
    FuelingPlanRead,
    LoginRequest,
    LoginResponse,
    RunningPlanCreate,
    RunningPlanRead,
    StravaConnectStartOut,
    StravaConnectionRead,
    StravaSyncOut,
    UserCreate,
    UserRead,
    UserUpdate,
    WorkoutCreate,
    WorkoutRead,
)
from app.strava import (
    build_authorization_url,
    exchange_code_for_token,
    fetch_athlete_activities,
    refresh_access_token,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Peak V1 API",
    description="Minimal API for users, Strava workouts, and fueling plans.",
    version="1.0.0",
    lifespan=lifespan,
)
bearer_scheme = HTTPBearer(auto_error=False)


def utc_now_iso() -> str:
    # Strip microseconds — Swift's ISO8601DateFormatter rejects fractional seconds
    # by default, so we keep all timestamps as whole-second precision.
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_required_text(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="{0} cannot be empty.".format(field_name),
        )
    return normalized


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> Dict[str, Any]:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = verify_access_token(credentials.credentials)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    with closing(get_connection()) as connection:
        row = fetch_one(
            connection,
            """
            SELECT id, name, email, created_at, dob, height, weight, is_male
            FROM users
            WHERE id = ?
            """,
            (user_id,),
        )
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired bearer token.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return serialize_user(row)


def require_current_user_matches_path(
    user_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    if current_user["id"] != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only access your own resources.",
        )
    return current_user


def token_response_for_user(row: Dict[str, Any]) -> Dict[str, Any]:
    item = serialize_user(row)
    item.pop("password", None)
    item["access_token"] = create_access_token(item["id"])
    item["token_type"] = "bearer"
    item["expires_in"] = ACCESS_TOKEN_TTL_SECONDS
    return item


def iso_from_epoch_seconds(value: int) -> str:
    return datetime.fromtimestamp(value, timezone.utc).replace(microsecond=0).isoformat()


def maybe_redirect_after_strava_callback(
    redirect_url: Optional[str],
    payload: Dict[str, Any],
) -> Any:
    if not redirect_url:
        return payload

    separator = "&" if "?" in redirect_url else "?"
    query = "status={status}".format(status=payload["status"])
    if "user_id" in payload:
        query += "&user_id={user_id}".format(user_id=payload["user_id"])
    return RedirectResponse(f"{redirect_url}{separator}{query}")


@app.get("/")
def root() -> Dict[str, Any]:
    return {
        "message": "Peak V1 API",
        "docs": "/docs",
        "database_backend": get_database_backend(),
    }


@app.get("/health")
def health_check() -> Dict[str, str]:
    with closing(get_connection()) as connection:
        execute(connection, "SELECT 1").fetchone()
    return {"status": "healthy", "database": "ok"}


@app.post("/users", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate) -> Dict[str, Any]:
    user_id = str(uuid4())
    created_at = utc_now_iso()
    name = normalize_required_text(payload.name, "name")
    email = normalize_required_text(payload.email, "email").lower()
    password = hash_password(normalize_required_text(payload.password, "password"))

    with closing(get_connection()) as connection:
        try:
            execute(
                connection,
                """
                INSERT INTO users (
                    id,
                    name,
                    email,
                    password,
                    created_at,
                    dob,
                    height,
                    weight,
                    is_male
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    name,
                    email,
                    password,
                    created_at,
                    payload.dob.isoformat(),
                    payload.height,
                    payload.weight,
                    payload.is_male,
                ),
            )
            connection.commit()
        except INTEGRITY_ERRORS as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A user with that email already exists.",
            ) from exc

        row = fetch_user_or_404(connection, user_id)
        return serialize_user(row)


@app.get("/users/me", response_model=UserRead)
def get_current_user_profile(
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    return current_user


@app.get("/users/{user_id}", response_model=UserRead)
def get_user(
    user_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    if current_user["id"] != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this user.",
        )
    return current_user


@app.patch("/users/{user_id}", response_model=UserRead)
def update_user(
    user_id: str,
    payload: UserUpdate,
    _: Dict[str, Any] = Depends(require_current_user_matches_path),
) -> Dict[str, Any]:
    """
    Partially update a user profile.
    Accepts any combination of: height (cm), weight (kg), password.
    Only the supplied fields are written — everything else is left unchanged.
    """
    # Build SET clause dynamically from whichever fields were provided
    updates: Dict[str, Any] = {}
    if payload.height is not None:
        updates["height"] = payload.height
    if payload.weight is not None:
        updates["weight"] = payload.weight
    if payload.password is not None:
        updates["password"] = hash_password(payload.password)

    set_clause = ", ".join(f"{col} = ?" for col in updates)
    values = list(updates.values()) + [user_id]

    with closing(get_connection()) as connection:
        fetch_user_or_404(connection, user_id)
        execute(
            connection,
            f"UPDATE users SET {set_clause} WHERE id = ?",
            values,
        )
        connection.commit()
        row = fetch_user_or_404(connection, user_id)
        return serialize_user(row)


@app.post(
    "/users/{user_id}/workouts",
    response_model=WorkoutRead,
    status_code=status.HTTP_201_CREATED,
)
def create_workout(
    user_id: str,
    payload: WorkoutCreate,
    _: Dict[str, Any] = Depends(require_current_user_matches_path),
) -> Dict[str, Any]:
    workout_id = str(uuid4())
    created_at = utc_now_iso()
    name = normalize_required_text(payload.name, "name")
    raw_data = json.dumps(payload.raw_data) if payload.raw_data is not None else None

    with closing(get_connection()) as connection:
        fetch_user_or_404(connection, user_id)

        try:
            execute(
                connection,
                """
                INSERT INTO workouts (
                    id,
                    user_id,
                    source,
                    strava_activity_id,
                    name,
                    sport_type,
                    start_date,
                    distance_meters,
                    moving_time_seconds,
                    calories,
                    notes,
                    raw_data,
                    created_at
                )
                VALUES (?, ?, 'strava', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    workout_id,
                    user_id,
                    payload.strava_activity_id,
                    name,
                    payload.sport_type,
                    payload.start_date.isoformat(),
                    payload.distance_meters,
                    payload.moving_time_seconds,
                    payload.calories,
                    payload.notes,
                    raw_data,
                    created_at,
                ),
            )
            connection.commit()
        except INTEGRITY_ERRORS as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="That Strava activity is already stored for this user.",
            ) from exc

        row = fetch_workout_or_404(connection, workout_id)
        return serialize_workout(row)


@app.get("/users/{user_id}/workouts", response_model=List[WorkoutRead])
def list_workouts(
    user_id: str,
    _: Dict[str, Any] = Depends(require_current_user_matches_path),
) -> List[Dict[str, Any]]:
    with closing(get_connection()) as connection:
        fetch_user_or_404(connection, user_id)
        rows = fetch_all(
            connection,
            """
            SELECT
                id,
                user_id,
                source,
                strava_activity_id,
                name,
                sport_type,
                start_date,
                distance_meters,
                moving_time_seconds,
                calories,
                notes,
                raw_data,
                created_at
            FROM workouts
            WHERE user_id = ?
            ORDER BY start_date DESC, created_at DESC
            """,
            (user_id,),
        )
    return [serialize_workout(row) for row in rows]


@app.get("/workouts/{workout_id}", response_model=WorkoutRead)
def get_workout(
    workout_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    with closing(get_connection()) as connection:
        row = fetch_workout_or_404(connection, workout_id)
        if row["user_id"] != current_user["id"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only access your own resources.",
            )
        return serialize_workout(row)


@app.post(
    "/users/{user_id}/fueling-plans",
    response_model=FuelingPlanRead,
    status_code=status.HTTP_201_CREATED,
)
def create_fueling_plan(
    user_id: str,
    payload: FuelingPlanCreate,
    _: Dict[str, Any] = Depends(require_current_user_matches_path),
) -> Dict[str, Any]:
    plan_id = str(uuid4())
    created_at = utc_now_iso()
    goal = normalize_required_text(payload.goal, "goal")

    with closing(get_connection()) as connection:
        fetch_user_or_404(connection, user_id)

        if payload.workout_id is not None:
            workout_row = fetch_workout_or_404(connection, payload.workout_id)
            if workout_row["user_id"] != user_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Workout does not belong to this user.",
                )

        execute(
            connection,
            """
            INSERT INTO fueling_plans (
                id,
                user_id,
                workout_id,
                goal,
                carbs_per_hour,
                hydration_ml_per_hour,
                sodium_mg_per_hour,
                notes,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                plan_id,
                user_id,
                payload.workout_id,
                goal,
                payload.carbs_per_hour,
                payload.hydration_ml_per_hour,
                payload.sodium_mg_per_hour,
                payload.notes,
                created_at,
            ),
        )
        connection.commit()

        row = fetch_fueling_plan_or_404(connection, plan_id)
        return serialize_fueling_plan(row)


@app.get("/users/{user_id}/fueling-plans", response_model=List[FuelingPlanRead])
def list_fueling_plans(
    user_id: str,
    _: Dict[str, Any] = Depends(require_current_user_matches_path),
) -> List[Dict[str, Any]]:
    with closing(get_connection()) as connection:
        fetch_user_or_404(connection, user_id)
        rows = fetch_all(
            connection,
            """
            SELECT
                id,
                user_id,
                workout_id,
                goal,
                carbs_per_hour,
                hydration_ml_per_hour,
                sodium_mg_per_hour,
                notes,
                created_at
            FROM fueling_plans
            WHERE user_id = ?
            ORDER BY created_at DESC
            """,
            (user_id,),
        )
    return [serialize_fueling_plan(row) for row in rows]


@app.get("/fueling-plans/{plan_id}", response_model=FuelingPlanRead)
def get_fueling_plan(
    plan_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    with closing(get_connection()) as connection:
        row = fetch_fueling_plan_or_404(connection, plan_id)
        if row["user_id"] != current_user["id"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only access your own resources.",
            )
        return serialize_fueling_plan(row)


@app.post(
    "/users/{user_id}/running-plans",
    response_model=RunningPlanRead,
    status_code=status.HTTP_201_CREATED,
)
def create_running_plan(
    user_id: str,
    payload: RunningPlanCreate,
    _: Dict[str, Any] = Depends(require_current_user_matches_path),
) -> Dict[str, Any]:
    """Create a scheduled running plan for a user."""
    with closing(get_connection()) as connection:
        fetch_user_or_404(connection, user_id)
        plan_id = str(uuid4())
        created_at = utc_now_iso()
        # Store planned_at as whole-second ISO string (same rule as created_at)
        planned_at = payload.planned_at.replace(microsecond=0).isoformat()
        execute(
            connection,
            """
            INSERT INTO running_plans
                (id, user_id, planned_at, distance_km, speed_kph, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                plan_id,
                user_id,
                planned_at,
                payload.distance_km,
                payload.speed_kph,
                payload.notes,
                created_at,
            ),
        )
        connection.commit()
        row = fetch_running_plan_or_404(connection, plan_id)
        return serialize_running_plan(row)


@app.get("/users/{user_id}/running-plans", response_model=List[RunningPlanRead])
def list_running_plans(
    user_id: str,
    _: Dict[str, Any] = Depends(require_current_user_matches_path),
) -> List[Dict[str, Any]]:
    """List all running plans for a user, most recent first."""
    with closing(get_connection()) as connection:
        fetch_user_or_404(connection, user_id)
        rows = fetch_all(
            connection,
            """
            SELECT id, user_id, planned_at, distance_km, speed_kph, notes, created_at
            FROM running_plans
            WHERE user_id = ?
            ORDER BY planned_at ASC
            """,
            (user_id,),
        )
    return [serialize_running_plan(row) for row in rows]


@app.post("/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest) -> Dict[str, Any]:
    """Authenticate a user by email and password.

    Returns the full ``UserRead`` on success.  Returns 401 if the email is not
    found or the password does not match — both cases return the same error
    message to avoid leaking which emails are registered.
    """
    email = payload.email.strip().lower()
    with closing(get_connection()) as connection:
        row = fetch_one(
            connection,
            """
            SELECT id, name, email, password, created_at, dob, height, weight, is_male
            FROM users
            WHERE LOWER(email) = ?
            """,
            (email,),
        )
        if row is None or not verify_password(row["password"], payload.password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password.",
            )

        if not row["password"].startswith("pbkdf2_sha256$"):
            execute(
                connection,
                "UPDATE users SET password = ? WHERE id = ?",
                (hash_password(payload.password), row["id"]),
            )
            connection.commit()

        return token_response_for_user(row)


@app.get("/auth/me", response_model=UserRead)
def get_me(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    return current_user


def strava_athlete_display_name(athlete: Dict[str, Any]) -> Optional[str]:
    username = athlete.get("username")
    if isinstance(username, str) and username.strip():
        return username.strip()

    names = [
        value.strip()
        for value in [athlete.get("firstname"), athlete.get("lastname")]
        if isinstance(value, str) and value.strip()
    ]
    return " ".join(names) if names else None


def store_strava_connection(
    user_id: str,
    token_payload: Dict[str, Any],
    accepted_scope: Optional[str],
) -> Dict[str, Any]:
    athlete = token_payload.get("athlete")
    if not isinstance(athlete, dict) or athlete.get("id") is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Strava token response did not include athlete information.",
        )

    expires_at = token_payload.get("expires_at")
    if not isinstance(expires_at, int):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Strava token response did not include an expiration timestamp.",
        )
    if not isinstance(token_payload.get("access_token"), str) or not isinstance(
        token_payload.get("refresh_token"), str
    ):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Strava token response did not include access and refresh tokens.",
        )

    now = utc_now_iso()
    with closing(get_connection()) as connection:
        fetch_user_or_404(connection, user_id)
        try:
            execute(
                connection,
                """
                INSERT INTO strava_connections (
                    id,
                    user_id,
                    strava_athlete_id,
                    strava_username,
                    access_token,
                    refresh_token,
                    expires_at,
                    scope,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    strava_athlete_id = excluded.strava_athlete_id,
                    strava_username = excluded.strava_username,
                    access_token = excluded.access_token,
                    refresh_token = excluded.refresh_token,
                    expires_at = excluded.expires_at,
                    scope = excluded.scope,
                    updated_at = excluded.updated_at
                """,
                (
                    str(uuid4()),
                    user_id,
                    str(athlete["id"]),
                    strava_athlete_display_name(athlete),
                    token_payload["access_token"],
                    token_payload["refresh_token"],
                    iso_from_epoch_seconds(expires_at),
                    accepted_scope,
                    now,
                    now,
                ),
            )
            connection.commit()
        except INTEGRITY_ERRORS as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="That Strava athlete is already connected to another user.",
            ) from exc

        row = fetch_strava_connection_by_user_id(connection, user_id)
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Strava connection was not saved.",
            )
        return serialize_strava_connection(row)


def ensure_fresh_strava_access_token(
    connection: Any,
    strava_connection: Dict[str, Any],
) -> str:
    expires_at = datetime.fromisoformat(strava_connection["expires_at"])
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    seconds_remaining = (expires_at - datetime.now(timezone.utc)).total_seconds()
    if seconds_remaining > 60:
        return strava_connection["access_token"]

    token_payload = refresh_access_token(strava_connection["refresh_token"])
    new_expires_at = token_payload.get("expires_at")
    if not isinstance(new_expires_at, int):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Strava refresh response did not include an expiration timestamp.",
        )
    if not isinstance(token_payload.get("access_token"), str) or not isinstance(
        token_payload.get("refresh_token"), str
    ):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Strava refresh response did not include access and refresh tokens.",
        )

    access_token = token_payload["access_token"]
    refresh_token = token_payload["refresh_token"]
    execute(
        connection,
        """
        UPDATE strava_connections
        SET access_token = ?,
            refresh_token = ?,
            expires_at = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            access_token,
            refresh_token,
            iso_from_epoch_seconds(new_expires_at),
            utc_now_iso(),
            strava_connection["id"],
        ),
    )
    return access_token


def import_strava_activity(
    connection: Any,
    user_id: str,
    activity: Dict[str, Any],
) -> bool:
    activity_id = activity.get("id")
    if activity_id is None:
        return False

    strava_activity_id = str(activity_id)
    existing = fetch_one(
        connection,
        """
        SELECT id
        FROM workouts
        WHERE user_id = ? AND strava_activity_id = ?
        """,
        (user_id, strava_activity_id),
    )
    if existing is not None:
        return False

    name = activity.get("name")
    start_date = activity.get("start_date")
    if not isinstance(name, str) or not name.strip() or not isinstance(start_date, str):
        return False

    execute(
        connection,
        """
        INSERT INTO workouts (
            id,
            user_id,
            source,
            strava_activity_id,
            name,
            sport_type,
            start_date,
            distance_meters,
            moving_time_seconds,
            calories,
            raw_data,
            created_at
        )
        VALUES (?, ?, 'strava', ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(uuid4()),
            user_id,
            strava_activity_id,
            name.strip(),
            activity.get("sport_type") or activity.get("type"),
            start_date,
            activity.get("distance"),
            activity.get("moving_time"),
            activity.get("calories"),
            json.dumps(activity),
            utc_now_iso(),
        ),
    )
    return True


@app.get(
    "/users/{user_id}/strava/connect",
    response_model=StravaConnectStartOut,
)
def start_strava_connection(
    user_id: str,
    _: Dict[str, Any] = Depends(require_current_user_matches_path),
) -> Dict[str, str]:
    state = create_oauth_state(user_id)
    return {"authorization_url": build_authorization_url(state)}


@app.get("/strava/oauth/callback")
def complete_strava_connection(
    code: Optional[str] = Query(default=None),
    scope: Optional[str] = Query(default=None),
    state: Optional[str] = Query(default=None),
    error: Optional[str] = Query(default=None),
) -> Any:
    failure_redirect_url = os.getenv("PEAK_STRAVA_FAILURE_REDIRECT_URL")
    success_redirect_url = os.getenv("PEAK_STRAVA_SUCCESS_REDIRECT_URL")

    if error is not None:
        payload = {"status": "error", "detail": error}
        if failure_redirect_url:
            return maybe_redirect_after_strava_callback(failure_redirect_url, payload)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Strava OAuth failed: {error}",
        )

    if not code or not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Strava callback requires code and state.",
        )

    user_id = verify_oauth_state(state)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired Strava OAuth state.",
        )

    token_payload = exchange_code_for_token(code)
    connection = store_strava_connection(user_id, token_payload, scope)
    payload = {
        "status": "connected",
        "user_id": user_id,
        "connection": connection,
    }
    return maybe_redirect_after_strava_callback(success_redirect_url, payload)


@app.get(
    "/users/{user_id}/strava/connection",
    response_model=StravaConnectionRead,
)
def get_strava_connection(
    user_id: str,
    _: Dict[str, Any] = Depends(require_current_user_matches_path),
) -> Dict[str, Any]:
    with closing(get_connection()) as connection:
        row = fetch_strava_connection_by_user_id(connection, user_id)
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Strava connection not found.",
            )
        return serialize_strava_connection(row)


@app.post(
    "/users/{user_id}/strava/sync",
    response_model=StravaSyncOut,
)
def sync_strava_workouts(
    user_id: str,
    _: Dict[str, Any] = Depends(require_current_user_matches_path),
) -> Dict[str, Any]:
    with closing(get_connection()) as connection:
        strava_connection = fetch_strava_connection_by_user_id(connection, user_id)
        if strava_connection is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Strava connection not found.",
            )

        access_token = ensure_fresh_strava_access_token(
            connection,
            dict(strava_connection),
        )
        activities = fetch_athlete_activities(access_token)

        imported_workouts = 0
        for activity in activities:
            if import_strava_activity(connection, user_id, activity):
                imported_workouts += 1

        last_synced_at = utc_now_iso()
        execute(
            connection,
            """
            UPDATE strava_connections
            SET last_synced_at = ?,
                updated_at = ?
            WHERE user_id = ?
            """,
            (last_synced_at, last_synced_at, user_id),
        )
        connection.commit()

    return {
        "imported_workouts": imported_workouts,
        "last_synced_at": last_synced_at,
    }


@app.post("/test/reset", status_code=status.HTTP_204_NO_CONTENT)
def reset_database() -> Response:
    """Drop all tables and re-initialise the schema.

    Only available when the ``PEAK_TESTING`` environment variable is set to
    ``"true"``.  Returns 403 in all other environments so this endpoint cannot
    be called in production by mistake.
    """
    if os.getenv("PEAK_TESTING", "").lower() != "true":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Test-only endpoint. Set PEAK_TESTING=true to enable.",
        )

    drop_statements = [
        "DROP INDEX IF EXISTS idx_strava_connections_user_id",
        "DROP INDEX IF EXISTS idx_running_plans_user_id",
        "DROP INDEX IF EXISTS idx_fueling_plans_user_id",
        "DROP INDEX IF EXISTS idx_workouts_user_strava_activity",
        "DROP INDEX IF EXISTS idx_workouts_user_id",
        "DROP TABLE IF EXISTS strava_connections",
        "DROP TABLE IF EXISTS running_plans",
        "DROP TABLE IF EXISTS fueling_plans",
        "DROP TABLE IF EXISTS workouts",
        "DROP TABLE IF EXISTS users",
    ]
    with closing(get_connection()) as connection:
        for statement in drop_statements:
            connection.execute(statement)
        connection.commit()

    init_db()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
