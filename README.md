# Peak-V1

Peak V1 is a FastAPI backend for Peak's core data model: users, user connections,
workouts, athlete profiles, fueling profiles, and recommendations. The code is
now organized into smaller modules under `app/` instead of a single large file.

## Project Layout

```text
.
├── app/
│   ├── main.py
│   ├── config.py
│   ├── dependencies.py
│   ├── db.py
│   ├── schemas.py
│   ├── routers/
│   │   ├── health.py
│   │   ├── users.py
│   │   ├── connections.py
│   │   ├── workouts.py
│   │   ├── profiles.py
│   │   ├── recommendations.py
│   │   └── strava.py
│   └── services/
│       └── strava.py
├── main.py
├── table_creation.sql
├── requirements.txt
└── .env.example
```

`main.py` at the repo root remains the Uvicorn entrypoint and imports `app` from
`app.main`.

## Prerequisites

- Python 3.8 or higher
- pip
- PostgreSQL

## Installation

1. Clone the repository and enter it:

```bash
git clone https://github.com/kahlilwassell/Peak-V1.git
cd Peak-V1
```

2. Create and activate a virtual environment:

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Export the environment variables shown in `.env.example`:

```bash
export DATABASE_URL="postgresql://<user>:<password>@<host>:<port>/<db>"
export PEAK_API_KEY="your-long-random-secret"
export STRAVA_CLIENT_ID="your-strava-client-id"
export STRAVA_CLIENT_SECRET="your-strava-client-secret"
export STRAVA_REDIRECT_URI="http://localhost:8000/v1/strava/connect/callback"
```

5. Create or update the database tables:

```bash
psql "$DATABASE_URL" -f table_creation.sql
```

## Running the Application

Start the FastAPI server:

```bash
uvicorn main:app --reload
```

The API will be available at `http://localhost:8000`.

Call endpoints with your API key:

```bash
curl -H "X-API-Key: $PEAK_API_KEY" http://localhost:8000/health
```

Interactive docs are available at:

- `GET /docs`
- `GET /redoc`

## Current API Endpoints

### System

- `GET /`
- `GET /health`
- `GET /health/db`
- `GET /db/health`

### Users

- `POST /users`
- `GET /users`
- `GET /users/{user_id}`
- `PATCH /users/{user_id}`
- `DELETE /users/{user_id}`
- `POST /v1/users`
- `GET /v1/users/{user_id}`

### User Connections

- `POST /users/{user_id}/connections`
- `GET /users/{user_id}/connections`
- `GET /connections/{connection_id}`
- `PATCH /connections/{connection_id}`
- `DELETE /connections/{connection_id}`

### Workouts

- `POST /users/{user_id}/workouts`
- `GET /users/{user_id}/workouts`
- `GET /workouts/{workout_id}`
- `PATCH /workouts/{workout_id}`
- `DELETE /workouts/{workout_id}`
- `GET /v1/workouts/{user_id}`
- `GET /v1/workout/{workout_id}`

### Athlete and Fueling Profiles

- `POST /users/{user_id}/athlete-profile`
- `GET /users/{user_id}/athlete-profile`
- `GET /athlete-profiles/{profile_id}`
- `PATCH /athlete-profiles/{profile_id}`
- `DELETE /athlete-profiles/{profile_id}`
- `POST /users/{user_id}/fueling-profile`
- `GET /users/{user_id}/fueling-profile`
- `GET /fueling-profiles/{profile_id}`
- `PATCH /fueling-profiles/{profile_id}`
- `DELETE /fueling-profiles/{profile_id}`
- `GET /v1/fueling-profile/{user_id}`

### Recommendations

- `POST /users/{user_id}/recommendations`
- `GET /users/{user_id}/recommendations`
- `GET /recommendations/{recommendation_id}`
- `PATCH /recommendations/{recommendation_id}`
- `DELETE /recommendations/{recommendation_id}`
- `GET /v1/recommendations/{user_id}`

### Strava OAuth Scaffold

- `GET /v1/strava/connect/start`
- `GET /v1/strava/connect/callback`

The Strava routes are scaffolding only right now:

- `connect/start` builds an authorization URL when the Strava env vars are set.
- `connect/callback` returns `501 Not Implemented` because token exchange and
  persistence are not wired yet.

## Notes

- `table_creation.sql` is still the database source of truth.
- `StravaDataPullRequirements.md` is the working checklist for the next Strava
  integration milestone.
- The current code intentionally keeps raw SQL and avoids adding an ORM during
  this cleanup pass.
