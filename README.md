# Peak-V1
This is the v1 version of the Peak backend API and Database

## Getting Started

### Prerequisites
- Python 3.8 or higher
- pip (Python package installer)

### Installation

1. Clone the repository:
```bash
git clone https://github.com/kahlilwassell/Peak-V1.git
cd Peak-V1
```

2. Create a virtual environment (recommended):
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create/update tables in your Postgres database:
```bash
psql "$DATABASE_URL" -f table_creation.sql
```

### Running the Application

Start the FastAPI server:
```bash
uvicorn main:app --reload
```

The API will be available at `http://localhost:8000`

If you want to test database connectivity locally, set:
```bash
export DATABASE_URL="postgresql://<user>:<password>@<host>:<port>/<db>"
```

Set an API key for request authentication:
```bash
export PEAK_API_KEY="your-long-random-secret"
```

Call endpoints with your key:
```bash
curl -H "X-API-Key: $PEAK_API_KEY" http://localhost:8000/health
```

### API Endpoints

- `GET /` - Root endpoint
- `GET /health` - Health check endpoint
- `GET /health/db` - Database connectivity check (`SELECT 1`)
- `POST /users` - Create user
- `GET /users` - List users
- `GET /users/{user_id}` - Get user by id
- `PATCH /users/{user_id}` - Update user
- `DELETE /users/{user_id}` - Delete user
- `POST /users/{user_id}/connections` - Create user connection
- `GET /users/{user_id}/connections` - List user connections
- `GET /connections/{connection_id}` - Get connection by id
- `PATCH /connections/{connection_id}` - Update connection
- `DELETE /connections/{connection_id}` - Delete connection
- `POST /users/{user_id}/workouts` - Create workout
- `GET /users/{user_id}/workouts` - List user workouts
- `GET /workouts/{workout_id}` - Get workout by id
- `PATCH /workouts/{workout_id}` - Update workout
- `DELETE /workouts/{workout_id}` - Delete workout
- `GET /docs` - Interactive API documentation (Swagger UI)
- `GET /redoc` - Alternative API documentation (ReDoc)

### Development

The application runs in development mode with auto-reload enabled when using the `--reload` flag.

### Deployment

This application is designed to be deployed on Railway or similar platforms. Make sure to:
1. Set the appropriate environment variables (`DATABASE_URL`, `PEAK_API_KEY`, `PORT`)
2. Configure the start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
