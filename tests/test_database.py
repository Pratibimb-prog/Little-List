"""Tests for database initialization, migrations, isolation, and persistence."""

import sqlite3
import tempfile
import unittest
from pathlib import Path

from backend.database import connect, initialize_database
from backend.main import create_app


class DatabaseTests(unittest.TestCase):
    def test_database_initialization_creates_schema_and_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "init_test.sqlite3"
            self.assertFalse(db_path.exists())

            initialize_database(db_path)
            self.assertTrue(db_path.exists())

            conn = connect(db_path)
            tables = [
                row["name"]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            ]
            self.assertIn("tasks", tables)
            self.assertIn("users", tables)
            self.assertIn("schema_version", tables)

            version = conn.execute("SELECT version FROM schema_version").fetchone()["version"]
            self.assertEqual(version, 4)

            # Check task columns
            columns = [
                row["name"]
                for row in conn.execute("PRAGMA table_info(tasks)").fetchall()
            ]
            for expected_col in [
                "id", "text", "completed", "created_at",
                "priority", "due_date", "status", "updated_at", "user_id"
            ]:
                self.assertIn(expected_col, columns)
            conn.close()

    def test_migration_preserves_legacy_v1_database(self):
        """Simulate an existing legacy v1 SQLite database with tasks and verify migration."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "legacy.sqlite3"

            # Create legacy v1 database
            conn = sqlite3.connect(str(db_path))
            conn.execute(
                """
                CREATE TABLE tasks (
                    id TEXT PRIMARY KEY,
                    text TEXT NOT NULL CHECK(length(text) BETWEEN 1 AND 160),
                    completed INTEGER NOT NULL DEFAULT 0 CHECK(completed IN (0, 1)),
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "INSERT INTO tasks VALUES (?, ?, ?, ?)",
                ("task-1", "Legacy active task", 0, "2026-01-01T10:00:00Z"),
            )
            conn.execute(
                "INSERT INTO tasks VALUES (?, ?, ?, ?)",
                ("task-2", "Legacy finished task", 1, "2026-01-01T11:00:00Z"),
            )
            conn.commit()
            conn.close()

            # Now run the modern migration system
            initialize_database(db_path)

            # Verify records are preserved intact with migrated defaults
            conn = connect(db_path)
            t1 = conn.execute("SELECT * FROM tasks WHERE id = 'task-1'").fetchone()
            self.assertIsNotNone(t1)
            self.assertEqual(t1["text"], "Legacy active task")
            self.assertEqual(t1["completed"], 0)
            self.assertEqual(t1["status"], "todo")
            self.assertEqual(t1["priority"], "medium")
            self.assertIsNone(t1["user_id"])

            t2 = conn.execute("SELECT * FROM tasks WHERE id = 'task-2'").fetchone()
            self.assertIsNotNone(t2)
            self.assertEqual(t2["text"], "Legacy finished task")
            self.assertEqual(t2["completed"], 1)
            self.assertEqual(t2["status"], "done")  # synced from completed=1
            self.assertEqual(t2["priority"], "medium")
            self.assertIsNone(t2["user_id"])

            # Verify users table was added
            users_table = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
            ).fetchone()
            self.assertIsNotNone(users_table)
            conn.close()

    def test_database_isolation(self):
        with tempfile.TemporaryDirectory() as tmp:
            db1 = Path(tmp) / "db1.sqlite3"
            db2 = Path(tmp) / "db2.sqlite3"

            initialize_database(db1)
            initialize_database(db2)

            c1 = connect(db1)
            c2 = connect(db2)

            c1.execute(
                "INSERT INTO tasks (id, text, completed, created_at) VALUES ('1', 'In DB1', 0, '2026-01-01')"
            )
            c1.commit()

            in_db1 = c1.execute("SELECT COUNT(*) AS cnt FROM tasks").fetchone()["cnt"]
            in_db2 = c2.execute("SELECT COUNT(*) AS cnt FROM tasks").fetchone()["cnt"]

            self.assertEqual(in_db1, 1)
            self.assertEqual(in_db2, 0)

            c1.close()
            c2.close()


if __name__ == "__main__":
    unittest.main()
