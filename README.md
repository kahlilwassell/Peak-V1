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

## Strava OAuth Flow

The Strava OAuth flow is split between the frontend and backend:

- The frontend starts the flow, opens Strava's authorization page, and later calls sync/status endpoints.
- The backend owns the Strava client secret, validates the callback, exchanges the one-time `code` for tokens, stores those tokens, refreshes them when needed, and imports activities.

### 1. Configure Strava

In the Strava API application settings, set the callback domain to the backend domain only:

```text
peak-v1-production.up.railway.app
```

Do not include `https://` or `/strava/oauth/callback` in Strava's callback domain field.

Use the values from Strava as backend environment variables:

```bash
STRAVA_CLIENT_ID=<Strava Client ID>
STRAVA_CLIENT_SECRET=<Strava Client Secret>
```

Do not use the access token or refresh token shown in the Strava dashboard. Those are user-specific tokens. This app creates and stores user tokens automatically after OAuth approval.

### 2. Configure The Backend

For Railway production, set these variables on the backend service:

```bash
DATABASE_URL=<Railway Postgres connection string>
PEAK_AUTH_SECRET=<long random string>
STRAVA_CLIENT_ID=<Strava Client ID>
STRAVA_CLIENT_SECRET=<Strava Client Secret>
STRAVA_REDIRECT_URI=https://peak-v1-production.up.railway.app/strava/oauth/callback
STRAVA_SCOPES=read,activity:read_all
```

Generate `PEAK_AUTH_SECRET` locally:

```bash
openssl rand -base64 32
```

For local development, use the local callback URL instead:

```bash
STRAVA_REDIRECT_URI=http://localhost:8000/strava/oauth/callback
```

Optional redirect URLs let the backend send the browser back to the frontend after Strava approves or rejects access:

```bash
PEAK_STRAVA_SUCCESS_REDIRECT_URL=http://localhost:3000/settings/integrations
PEAK_STRAVA_FAILURE_REDIRECT_URL=http://localhost:3000/settings/integrations
```

For the first manual test, leave `PEAK_STRAVA_SUCCESS_REDIRECT_URL` and `PEAK_STRAVA_FAILURE_REDIRECT_URL` unset. The callback will return JSON in the browser, which is easier to debug.

After changing Railway variables, redeploy or restart the backend service.

### 3. Manual Test

Set the API base URL:

```bash
export API_URL=https://peak-v1-production.up.railway.app
```

Check that the backend and database are healthy:

```bash
curl "$API_URL/health" | jq
```

Expected:

```json
{
  "status": "healthy",
  "database": "ok"
}
```

Create a Peak user if needed:

```bash
curl -X POST "$API_URL/users" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Kahlil",
    "email": "kahlil@example.com",
    "password": "super-secret-password",
    "dob": "1994-03-15",
    "height": 178,
    "weight": 72,
    "is_male": true
  }' | jq
```

Log in and save the returned `id` and `access_token`:

```bash
curl -X POST "$API_URL/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "kahlil@example.com",
    "password": "super-secret-password"
  }' | jq
```

Export those values:

```bash
export USER_ID=<id from login>
export PEAK_TOKEN=<access_token from login>
```

Start Strava OAuth:

```bash
curl "$API_URL/users/$USER_ID/strava/connect" \
  -H "Authorization: Bearer $PEAK_TOKEN" | jq
```

Expected:

```json
{
  "authorization_url": "https://www.strava.com/oauth/authorize?..."
}
```

Open the returned `authorization_url` in a browser and approve access in Strava.

After approval, Strava redirects to:

```text
GET /strava/oauth/callback?code=<code>&scope=<scope>&state=<state>
```

If frontend redirect URLs are unset, the browser should show JSON like:

```json
{
  "status": "connected",
  "user_id": "...",
  "connection": {
    "strava_athlete_id": "...",
    "scope": "read,activity:read_all",
    "last_synced_at": null
  }
}
```

Check the saved Strava connection:

```bash
curl "$API_URL/users/$USER_ID/strava/connection" \
  -H "Authorization: Bearer $PEAK_TOKEN" | jq
```

The response should include connection metadata but must not include Strava `access_token` or `refresh_token`.

Sync recent Strava activities:

```bash
curl -X POST "$API_URL/users/$USER_ID/strava/sync" \
  -H "Authorization: Bearer $PEAK_TOKEN" | jq
```

Expected:

```json
{
  "imported_workouts": 0,
  "last_synced_at": "..."
}
```

`imported_workouts` can be `0` if there are no new activities to import.

List imported workouts:

```bash
curl "$API_URL/users/$USER_ID/workouts" \
  -H "Authorization: Bearer $PEAK_TOKEN" | jq
```

### 4. What Happens Internally

1. `GET /users/{user_id}/strava/connect` creates a signed, short-lived OAuth `state` value and returns a Strava authorization URL.
2. The user approves access on Strava.
3. Strava calls `GET /strava/oauth/callback` with `code`, `scope`, and `state`.
4. The backend verifies `state`, exchanges `code` for Strava tokens, and stores the connection in `strava_connections`.
5. `POST /users/{user_id}/strava/sync` refreshes the Strava access token if needed, fetches activities, and inserts any new workouts.

### 5. Troubleshooting

If `/strava/connect` returns `503`, one of these variables is missing from the backend environment:

```text
STRAVA_CLIENT_ID
STRAVA_CLIENT_SECRET
STRAVA_REDIRECT_URI
```

If Strava rejects the authorization URL, check that:

- `STRAVA_REDIRECT_URI` exactly matches the backend callback URL.
- The Strava app callback domain is only the backend domain, with no protocol or path.
- The backend was redeployed after changing variables.

If `/strava/oauth/callback` returns `Invalid or expired Strava OAuth state`, rerun `/strava/connect` and use the new authorization URL. The `state` value expires after about 10 minutes.

If `/strava/sync` returns `404 Strava connection not found`, the OAuth callback did not save a connection for that Peak user. Repeat the connect flow and verify the callback JSON says `status: connected`.

If `/strava/sync` returns `imported_workouts: 0`, the sync worked but Strava returned no new activities that were not already imported.

### 6. Security Notes

- `STRAVA_CLIENT_SECRET`, Strava access tokens, and Strava refresh tokens stay on the backend and must not be committed to git.
- The frontend only receives the Strava authorization URL and redacted connection metadata.
- The signed OAuth `state` value binds the callback to the Peak user who started the flow.
- All user-scoped Strava endpoints require `Authorization: Bearer <access_token>` and reject requests where the token user does not match `{user_id}`.

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
