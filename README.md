# Little List — Full-Stack Task Management Application

Little List is a secure, responsive, and minimalist task management application built with **FastAPI**, **SQLite**, and **vanilla JavaScript**. It features multi-user authentication, task prioritization, due date tracking, inline editing, search, filtering, and productivity analytics.

---

## Features

- **Multi-User Authentication**: Secure user registration, login, and stateless JWT token authentication with bcrypt password hashing.
- **Strict Data Isolation**: Each user can only view, edit, or delete their own tasks.
- **Full CRUD with Inline Editing**: Add tasks with Enter, edit inline with Enter to save and Esc to cancel, and delete with two-step confirmation.
- **Priorities & Deadlines**: Low, Medium, and High priority labels with optional due dates, visual overdue badges, and upcoming deadline warnings.
- **Productivity Dashboard**: Real-time stats display total tasks, completed, pending, overdue, completion percentage, and tasks completed today.
- **Search, Filters & Sorting**: Live debounced text search, status filters (All, To Do, In Progress, Done), priority filters, and multi-field sorting (newest, due date, priority, status).
- **Graceful Legacy Migration**: Automated, version-tracked database migration that preserves all pre-existing records and allows claiming legacy tasks through the UI or CLI.
- **Production Ready**: Containerized with multi-stage Docker build, health checks (`/health`), WAL-mode SQLite, and GitHub Actions CI.

---

## Architecture & Directory Structure

```text
little-list/
├── .github/
│   └── workflows/
│       └── ci.yml             # GitHub Actions CI workflow
├── backend/
│   ├── __init__.py
│   ├── main.py                # FastAPI application factory & routes
│   ├── database.py            # SQLite connection pool & versioned migrations
│   ├── models.py              # Pydantic v2 schemas and validation
│   ├── auth.py                # Bcrypt hashing & JWT token encode/decode
│   ├── dependencies.py        # Database and authentication dependencies
│   ├── migrate_legacy.py      # CLI migration tool for legacy tasks
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── auth.py            # Auth routes (/api/auth)
│   │   ├── tasks.py           # Task CRUD routes (/api/tasks)
│   │   └── stats.py           # Dashboard stats route (/api/stats)
│   ├── services/
│   │   ├── __init__.py
│   │   └── task_service.py    # Business logic & parameterized queries
│   └── tasks.db               # SQLite database file (auto-migrated)
├── tests/
│   ├── __init__.py
│   ├── test_api.py            # CRUD, validation, and error tests
│   ├── test_auth.py           # Authentication, authorization & isolation tests
│   ├── test_database.py       # Migrations, persistence & isolation tests
│   └── test_features.py       # Filters, sorting, search, stats & claiming tests
├── .dockerignore
├── .env.example               # Environment variables template
├── .gitignore
├── Dockerfile                 # Container image specification with healthcheck
├── index.html                 # Single-page vanilla JavaScript frontend
├── README.md                  # Project documentation
└── requirements.txt           # Python dependencies
```

---

## Prerequisites

- **Python 3.10+** (tested on 3.10, 3.11, 3.12, 3.15)
- **Docker** (optional, for containerized deployment)

---

## Local Setup

### 1. Clone & create virtual environment

```powershell
# Windows PowerShell
py -m venv venv
.\venv\Scripts\Activate.ps1

# Linux / macOS
python3 -m venv venv
source venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Environment configuration (optional)

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | `dev-secret-change-in-production` | Secret key for JWT signing |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` (24h) | Token lifetime in minutes |
| `DATABASE_PATH` | `backend/tasks.db` | Custom filesystem path for SQLite DB |
| `LOG_LEVEL` | `INFO` | Application log level (`DEBUG`, `INFO`, etc.) |

---

## Running the Application

Start the development server with hot-reload:

```powershell
# Windows PowerShell
python -m uvicorn backend.main:app --reload

# Or specifying host and port:
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

- **Web Application**: <http://127.0.0.1:8000>
- **Swagger UI (Interactive API Docs)**: <http://127.0.0.1:8000/docs>
- **ReDoc**: <http://127.0.0.1:8000/redoc>
- **Health Check**: <http://127.0.0.1:8000/health>

---

## Database Migrations & Legacy Data

The database uses an automated, version-tracked migration system (`backend/database.py`).
On startup, migrations 1 through 4 run automatically, checking the `schema_version` table:

1. **Migration 1**: Initial `tasks` table.
2. **Migration 2**: Add `priority`, `due_date`, `status`, `updated_at`, `user_id` columns and sync status.
3. **Migration 3**: Create `users` table with unique lowercase usernames.
4. **Migration 4**: Create indexes on `user_id`, `status`, `priority`, and `due_date`.

### Legacy Task Migration

Existing records in `backend/tasks.db` created prior to authentication are safely preserved with `user_id = NULL`.

To assign legacy tasks to an account:
1. **Via Web UI**: Log in and click **"Import to my list"** on the notification banner.
2. **Via CLI**: Run:
   ```bash
   python -m backend.migrate_legacy <username>
   ```

---

## Running Tests

All 24 automated tests run against isolated temporary databases and never modify `backend/tasks.db`.

```powershell
# Run with pytest (recommended)
pytest tests/ -v

# Run with standard library unittest
python -m unittest discover -s tests -v
```

---

## API Reference

### Health
- `GET /health` — Service health check.

### Authentication
- `POST /api/auth/register` — Register a new account (`username`, `password`).
- `POST /api/auth/login` — Authenticate and receive a JWT bearer token.
- `POST /api/auth/logout` — Stateless logout.
- `GET /api/auth/me` — Retrieve current authenticated user profile.

### Tasks (Protected — requires `Authorization: Bearer <token>`)
- `GET /api/tasks` — List paginated tasks for the current user.
  - Query parameters:
    - `search` (string): Search text substring.
    - `status` (`todo`, `in_progress`, `done`).
    - `priority` (`low`, `medium`, `high`).
    - `sort_by` (`created_at`, `due_date`, `priority`, `status`).
    - `limit` (int, default: 50, max: 200).
    - `offset` (int, default: 0).
- `POST /api/tasks` — Create task (`text`, optional `priority`, optional `due_date`).
- `PATCH /api/tasks/{task_id}` — Update task (`text`, `completed`, `priority`, `due_date`, `status`).
- `DELETE /api/tasks/{task_id}` — Delete task.
- `GET /api/tasks/legacy-count` — Count unassigned legacy tasks.
- `POST /api/tasks/claim-legacy` — Assign all unowned legacy tasks to the logged-in user.

### Statistics (Protected)
- `GET /api/stats` — Return user task metrics (`total`, `completed`, `pending`, `overdue`, `completion_percentage`, `completed_today`).
- `GET /api/stats/trends?months=12` — Return monthly task creation vs. completion history, completion velocity rates, priority distribution, and deadline on-time delivery rates.

---

## Docker Deployment

Build and run with persistent database storage:

```bash
# Build the Docker image
docker build -t little-list .

# Run with a persistent volume for SQLite
docker run -d \
  -p 8000:8000 \
  -e SECRET_KEY="your-production-secret-key" \
  -v little_list_data:/data \
  --name little-list-app \
  little-list

# Check container health
docker inspect --format='{{json .State.Health.Status}}' little-list-app
```

---

## Deployment Considerations & SQLite Limitations

1. **Write Concurrency**: SQLite serializes write operations via database-level locking. Running with `--workers 1` in Uvicorn ensures serialized writes and prevents lock contention.
2. **Multi-Instance Deployments**: SQLite files cannot be shared across multiple distributed nodes or serverless containers. For multi-replica horizontal scaling, migrate database connections to PostgreSQL.
3. **Database Backups**: Use SQLite's online backup API or `sqlite3 backend/tasks.db ".backup backup.sqlite3"` to create consistent snapshots without stopping the server.
4. **HTTPS / Reverse Proxy**: Place Little List behind a reverse proxy (Caddy, NGINX, or Traefik) to terminate TLS and manage SSL certificates.
