# Messenger Backend

FastAPI asynchronous backend for the Messenger application.

## Tech Stack
- Python 3.11
- FastAPI
- SQLAlchemy (Async)
- PostgreSQL
- WebSockets for real-time updates
- JWT Authentication

## Setup & Running

### Using Docker (Recommended)
1. Copy `.env.example` to `.env` (if provided) or ensure your environment variables are set.
2. Run:
   ```bash
   docker compose up --build
   ```
The API will be available at `http://localhost:8000`.

### Local Development
1. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Set environment variables (see `.env`) and run:
   ```bash
   uvicorn app.main:app --reload
   ```

### Admin Access
To grant admin privileges to a user, run:
```bash
python set_admin.py <username>
```
(Ensure your database is running and environment variables are set).

## Structure
- `app/`: Main application code
  - `routers/`: API endpoints
  - `services/`: Business logic layer
  - `models.py`: Database models
  - `schemas.py`: Pydantic validation schemas
  - `websockets.py`: WebSocket connection manager
- `migrations/`: Alembic migrations (if any)
