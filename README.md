# Peak-V1

Minimal FastAPI backend for three core resources:

- users
- workouts imported from Strava
- fueling plans

This version intentionally avoids extra layers. The API is split into a small `app/` package and still uses SQLite for persistence.
It now also supports PostgreSQL when `DATABASE_URL` is set, which is the intended production path for Railway.

## Quick Start

### Prerequisites

- Python 3.8+
- pip

### Install

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Run

```bash
uvicorn app.main:app --reload
```

The API will start on `http://localhost:8000`.

You can also run the production-style entrypoint locally:

```bash
python main.py
```

### Run Tests

```bash
pip install -r requirements-dev.txt
pytest
```

The tests use a temporary SQLite database, so they do not touch your local `peak.db`.

For local development, the app writes to `peak.db` in the project root by default. You can override that with:

```bash
export PEAK_DB_PATH=/absolute/path/to/peak.db
```

For PostgreSQL environments such as Railway, set:

```bash
export DATABASE_URL=postgresql://postgres:password@localhost:5432/peak
```

For authenticated routes and Strava OAuth, set:

```bash
export PEAK_AUTH_SECRET=replace-with-a-long-random-string
export STRAVA_CLIENT_ID=your-strava-client-id
export STRAVA_CLIENT_SECRET=your-strava-client-secret
export STRAVA_REDIRECT_URI=http://localhost:8000/strava/oauth/callback
```

Optional Strava-related settings:

```bash
export STRAVA_SCOPES=read,activity:read_all
export PEAK_STRAVA_SUCCESS_REDIRECT_URL=http://localhost:3000/settings/integrations
export PEAK_STRAVA_FAILURE_REDIRECT_URL=http://localhost:3000/settings/integrations
```

## Project Layout

```text
.
├── app/
│   ├── __init__.py
│   ├── auth.py
│   ├── db.py
│   ├── main.py
│   ├── schemas.py
│   └── strava.py
├── main.py
├── README.md
├── requirements.txt
├── requirements-dev.txt
├── pytest.ini
└── tests/
    └── test_api.py
```

`main.py` at the repo root stays as the Uvicorn entrypoint and imports the app from `app.main`.

## Minimal Endpoints

### System

- `GET /`
- `GET /health`

### Users

- `POST /users`
- `GET /users/me`
- `GET /users/{user_id}`
- `PATCH /users/{user_id}`

### Authentication

- `POST /auth/login`
- `GET /auth/me`

### Strava Workouts

- `POST /users/{user_id}/workouts`
- `GET /users/{user_id}/workouts`
- `GET /workouts/{workout_id}`

### Strava OAuth

- `GET /users/{user_id}/strava/connect`
- `GET /strava/oauth/callback`
- `GET /users/{user_id}/strava/connection`
- `POST /users/{user_id}/strava/sync`

### Fueling Plans

- `POST /users/{user_id}/fueling-plans`
- `GET /users/{user_id}/fueling-plans`
- `GET /fueling-plans/{plan_id}`

## Example Requests

Create a user:

```bash
curl -X POST http://localhost:8000/users \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Kahlil",
    "email": "kahlil@example.com",
    "password": "super-secret-password",
    "dob": "1994-03-15",
    "height": 178,
    "weight": 72,
    "is_male": true
  }'
```

Log in and keep the bearer token:

```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "kahlil@example.com",
    "password": "super-secret-password"
  }'
```

Store a Strava workout for that user:

```bash
curl -X POST http://localhost:8000/users/<user_id>/workouts \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <access_token>" \
  -d '{
    "strava_activity_id": "123456789",
    "name": "Morning Run",
    "sport_type": "Run",
    "start_date": "2026-03-28T06:30:00Z",
    "distance_meters": 10000,
    "moving_time_seconds": 2820,
    "calories": 720,
    "raw_data": {
      "average_heartrate": 154
    }
  }'
```

Attach a fueling plan to the user or a specific workout:

```bash
curl -X POST http://localhost:8000/users/<user_id>/fueling-plans \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <access_token>" \
  -d '{
    "workout_id": "<optional_workout_id>",
    "goal": "Long run fueling",
    "carbs_per_hour": 75,
    "hydration_ml_per_hour": 600,
    "sodium_mg_per_hour": 700,
    "notes": "Start at 20 minutes, then every 30 minutes."
  }'
```

Start Strava OAuth:

```bash
curl http://localhost:8000/users/<user_id>/strava/connect \
  -H "Authorization: Bearer <access_token>"
```

The response contains an `authorization_url`. The frontend should redirect the user to that URL. After the user approves in Strava, Strava redirects to `STRAVA_REDIRECT_URI`, and the backend stores the connection.

Sync recent Strava activities into workouts:

```bash
curl -X POST http://localhost:8000/users/<user_id>/strava/sync \
  -H "Authorization: Bearer <access_token>"
```

## Notes

- Login returns a signed bearer token. Set `PEAK_AUTH_SECRET` in production; the built-in default is only for local development.
- User-owned endpoints require `Authorization: Bearer <access_token>`.
- User-owned path endpoints require the bearer token user to match the `{user_id}` path parameter.
- ID-only resource endpoints, such as `GET /workouts/{workout_id}` and `GET /fueling-plans/{plan_id}`, fetch the record and verify it belongs to the bearer token user before returning it.
- Strava access and refresh tokens are stored server-side and are never returned in API responses.
- Workouts are treated as Strava-sourced records and support storing the raw Strava payload.
- Duplicate `strava_activity_id` values are blocked per user so the same workout is not imported twice.

## Security Design

Public endpoints are limited to `GET /`, `GET /health`, `POST /users`, `POST /auth/login`, `GET /strava/oauth/callback`, and the test-only `POST /test/reset` endpoint when `PEAK_TESTING=true`.

All user-owned routes use the signed bearer token from `POST /auth/login`. Routes with `{user_id}` reject requests where the path user differs from the authenticated user. Routes that identify a resource directly verify ownership after loading the record. The API exposes `GET /users/me` for the current profile and does not expose a general user-list endpoint.

Strava OAuth uses a signed, short-lived `state` value to bind the callback to the Peak user who started the flow. The frontend receives only the Strava authorization URL and redacted connection metadata; Strava access and refresh tokens remain in the backend database.

## Railway Deployment

- The repo includes `railway.json` with the start command and `/health` healthcheck.
- Set `DATABASE_URL` on the `Peak-V1` service to the private connection string from the Railway Postgres service.
- Keep `PEAK_DB_PATH` unset in production so the app uses PostgreSQL.
- The repo includes `.github/workflows/ci.yml` so Railway's `Wait for CI` option can block deploys until tests pass.

## Smoke Test Script

Run the smoke test script after a deploy to create or reuse a stable test user, workout, and fueling plan through the API itself:

```bash
python3 scripts/seed_smoke_data.py --base-url https://peak-v1-production.up.railway.app
```

The script is idempotent. It will:

- verify `GET /health`
- verify `GET /`
- create or reuse `smoke-test@peak.local`
- log in as the smoke-test user and use the returned bearer token
- create or reuse a workout with `strava_activity_id=peak-smoke-activity`
- create or reuse a fueling plan attached to that workout

You can customize the seed values with flags or environment variables such as `PEAK_BASE_URL`, `PEAK_SMOKE_EMAIL`, and `PEAK_SMOKE_NAME`.
