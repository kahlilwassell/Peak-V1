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

### Running the Application

Start the FastAPI server:
```bash
uvicorn main:app --reload
```

The API will be available at `http://localhost:8000`

### API Endpoints

- `GET /` - Root endpoint
- `GET /health` - Health check endpoint
- `GET /docs` - Interactive API documentation (Swagger UI)
- `GET /redoc` - Alternative API documentation (ReDoc)

### Development

The application runs in development mode with auto-reload enabled when using the `--reload` flag.

### Deployment

This application is designed to be deployed on Railway or similar platforms. Make sure to:
1. Set the appropriate environment variables
2. Configure the start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
