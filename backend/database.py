"""Database connection management and schema migrations for Little List."""

import logging
import os
import sqlite3
from contextlib import closing
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_DATABASE = Path(
    os.environ.get("DATABASE_PATH", str(Path(__file__).resolve().parent / "tasks.db"))
)

# ---------- migration definitions ----------
# Each migration is a dict with "description" and "sql" (list of statements).
# Migrations are applied in order; the schema_version table tracks progress.

MIGRATIONS = {
    1: {
        "description": "Create initial tasks table",
        "sql": [
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                text TEXT NOT NULL CHECK(length(text) BETWEEN 1 AND 160),
                completed INTEGER NOT NULL DEFAULT 0 CHECK(completed IN (0, 1)),
                created_at TEXT NOT NULL
            )
            """,
        ],
    },
    2: {
        "description": "Add priority, due_date, status, updated_at, user_id to tasks",
        "sql": [
            "ALTER TABLE tasks ADD COLUMN priority TEXT NOT NULL DEFAULT 'medium'",
            "ALTER TABLE tasks ADD COLUMN due_date TEXT",
            "ALTER TABLE tasks ADD COLUMN status TEXT NOT NULL DEFAULT 'todo'",
            "ALTER TABLE tasks ADD COLUMN updated_at TEXT",
            "ALTER TABLE tasks ADD COLUMN user_id TEXT",
            # Sync status with completed for pre-existing rows
            "UPDATE tasks SET status = 'done' WHERE completed = 1",
        ],
    },
    3: {
        "description": "Create users table",
        "sql": [
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """,
        ],
    },
    4: {
        "description": "Add indexes for commonly filtered columns",
        "sql": [
            "CREATE INDEX IF NOT EXISTS idx_tasks_user_id ON tasks(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)",
            "CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority)",
            "CREATE INDEX IF NOT EXISTS idx_tasks_due_date ON tasks(due_date)",
        ],
    },
}

LATEST_VERSION = max(MIGRATIONS.keys())


def connect(database_path: Path) -> sqlite3.Connection:
    """Return a new connection with Row factory and WAL mode enabled."""
    database_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(database_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    columns = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(col["name"] == column for col in columns)


def initialize_database(database_path: Path) -> None:
    """Create or migrate the database to the latest schema version."""
    with closing(connect(database_path)) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)"
        )

        version_row = conn.execute("SELECT version FROM schema_version").fetchone()

        if version_row is None:
            # First run with version tracking — detect existing state
            if _has_table(conn, "tasks") and _has_column(conn, "tasks", "priority"):
                current_version = LATEST_VERSION  # already fully migrated
            elif _has_table(conn, "tasks"):
                current_version = 1  # legacy DB with original schema only
            else:
                current_version = 0  # fresh database
            conn.execute(
                "INSERT INTO schema_version (version) VALUES (?)",
                (current_version,),
            )
            conn.commit()
        else:
            current_version = version_row["version"]

        if current_version >= LATEST_VERSION:
            logger.info("Database schema is up to date (version %d)", current_version)
            return

        logger.info(
            "Migrating database from version %d to %d",
            current_version,
            LATEST_VERSION,
        )

        for version in range(current_version + 1, LATEST_VERSION + 1):
            migration = MIGRATIONS[version]
            logger.info(
                "Applying migration %d: %s", version, migration["description"]
            )
            for sql in migration["sql"]:
                try:
                    conn.execute(sql)
                except sqlite3.OperationalError as exc:
                    if "duplicate column" in str(exc).lower():
                        logger.warning("Column already exists, skipping: %s", exc)
                    else:
                        raise
            conn.execute("UPDATE schema_version SET version = ?", (version,))
            conn.commit()

        logger.info("Database migration complete (version %d)", LATEST_VERSION)
