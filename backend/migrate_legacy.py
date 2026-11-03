"""CLI utility to safely assign unowned legacy tasks to a specific user.

Usage:
    python -m backend.migrate_legacy <username>
"""

import sys
from pathlib import Path

from .database import DEFAULT_DATABASE, connect
from .services.task_service import claim_legacy_tasks, get_legacy_task_count


def migrate_legacy(username: str, database_path: Path = DEFAULT_DATABASE) -> int:
    conn = connect(database_path)
    try:
        user = conn.execute(
            "SELECT id, username FROM users WHERE username = ?", (username,)
        ).fetchone()
        if not user:
            print(f"Error: User '{username}' does not exist.")
            return 1

        unclaimed = get_legacy_task_count(conn)
        if unclaimed == 0:
            print("No unowned legacy tasks found in database.")
            return 0

        claimed = claim_legacy_tasks(conn, user["id"])
        print(f"Successfully migrated {claimed} legacy task(s) to user '{username}' (ID: {user['id']}).")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m backend.migrate_legacy <username>")
        sys.exit(1)

    username_arg = sys.argv[1].strip()
    sys.exit(migrate_legacy(username_arg))
