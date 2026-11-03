"""Task business logic for Little List."""

import sqlite3
from datetime import date, datetime, timezone
from typing import Optional
from uuid import uuid4

from fastapi import HTTPException, Response


def serialize_task(row: sqlite3.Row) -> dict:
    """Convert a database row to an API-friendly dict."""
    return {
        "id": row["id"],
        "text": row["text"],
        "completed": bool(row["completed"]),
        "priority": row["priority"] or "medium",
        "due_date": row["due_date"],
        "status": row["status"] or ("done" if row["completed"] else "todo"),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"] if "updated_at" in row.keys() else None,
    }


def list_tasks(
    db: sqlite3.Connection,
    user_id: str,
    search: Optional[str] = None,
    task_status: Optional[str] = None,
    priority: Optional[str] = None,
    sort_by: str = "created_at",
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """Return paginated, filtered, sorted tasks for a user."""
    conditions = ["user_id = ?"]
    params: list = [user_id]

    if search:
        conditions.append("text LIKE ?")
        params.append(f"%{search}%")
    if task_status:
        conditions.append("status = ?")
        params.append(task_status)
    if priority:
        conditions.append("priority = ?")
        params.append(priority)

    where = " AND ".join(conditions)

    sort_clauses = {
        "created_at": "created_at DESC, rowid DESC",
        "due_date": (
            "CASE WHEN due_date IS NULL THEN 1 ELSE 0 END, "
            "due_date ASC, created_at DESC"
        ),
        "priority": (
            "CASE priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 "
            "WHEN 'low' THEN 2 END, created_at DESC"
        ),
        "status": (
            "CASE status WHEN 'todo' THEN 0 WHEN 'in_progress' THEN 1 "
            "WHEN 'done' THEN 2 END, created_at DESC"
        ),
    }
    order = sort_clauses.get(sort_by, sort_clauses["created_at"])

    rows = db.execute(
        f"SELECT id, text, completed, priority, due_date, status, "
        f"created_at, updated_at FROM tasks "
        f"WHERE {where} ORDER BY {order} LIMIT ? OFFSET ?",
        (*params, limit, offset),
    ).fetchall()

    total = db.execute(
        f"SELECT COUNT(*) AS cnt FROM tasks WHERE {where}", params
    ).fetchone()["cnt"]

    return {
        "tasks": [serialize_task(r) for r in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def create_task(db: sqlite3.Connection, user_id: str, task) -> dict:
    """Insert a new task and return it."""
    task_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    due_str = task.due_date.isoformat() if task.due_date else None
    priority_val = task.priority.value if hasattr(task.priority, "value") else task.priority

    db.execute(
        "INSERT INTO tasks "
        "(id, text, completed, priority, due_date, status, created_at, updated_at, user_id) "
        "VALUES (?, ?, 0, ?, ?, 'todo', ?, ?, ?)",
        (task_id, task.text, priority_val, due_str, now, now, user_id),
    )
    db.commit()

    row = db.execute(
        "SELECT id, text, completed, priority, due_date, status, "
        "created_at, updated_at FROM tasks WHERE id = ?",
        (task_id,),
    ).fetchone()
    return serialize_task(row)


def update_task(
    db: sqlite3.Connection, user_id: str, task_id: str, changes
) -> dict:
    """Apply partial updates and return the updated task."""
    existing = db.execute(
        "SELECT id, user_id FROM tasks WHERE id = ?", (task_id,)
    ).fetchone()
    if existing is None or existing["user_id"] != user_id:
        raise HTTPException(status_code=404, detail="Task not found")

    fields = changes.model_dump(exclude_unset=True)

    # Keep completed ↔ status in sync
    if "completed" in fields and "status" not in fields:
        fields["status"] = "done" if fields["completed"] else "todo"
    elif "status" in fields and "completed" not in fields:
        status_val = fields["status"].value if hasattr(fields["status"], "value") else fields["status"]
        fields["completed"] = status_val == "done"
    elif "status" in fields and "completed" in fields:
        status_val = fields["status"].value if hasattr(fields["status"], "value") else fields["status"]
        fields["completed"] = status_val == "done"

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    fields["updated_at"] = now

    # Prepare values for the database
    db_fields: dict = {}
    for key, value in fields.items():
        if key == "completed":
            db_fields[key] = int(value) if value is not None else value
        elif key in ("priority", "status"):
            db_fields[key] = value.value if hasattr(value, "value") else value
        elif key == "due_date":
            db_fields[key] = value.isoformat() if isinstance(value, date) else value
        else:
            db_fields[key] = value

    assignments = ", ".join(f"{k} = ?" for k in db_fields)
    values = list(db_fields.values())

    db.execute(
        f"UPDATE tasks SET {assignments} WHERE id = ?", (*values, task_id)
    )
    db.commit()

    row = db.execute(
        "SELECT id, text, completed, priority, due_date, status, "
        "created_at, updated_at FROM tasks WHERE id = ?",
        (task_id,),
    ).fetchone()
    return serialize_task(row)


def delete_task(
    db: sqlite3.Connection, user_id: str, task_id: str
) -> Response:
    """Delete a task after verifying ownership."""
    existing = db.execute(
        "SELECT id, user_id FROM tasks WHERE id = ?", (task_id,)
    ).fetchone()
    if existing is None or existing["user_id"] != user_id:
        raise HTTPException(status_code=404, detail="Task not found")

    db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    db.commit()
    return Response(status_code=204)


def get_stats(db: sqlite3.Connection, user_id: str) -> dict:
    """Return aggregate statistics for a user's tasks."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    row = db.execute(
        """
        SELECT
            COUNT(*)                                                          AS total,
            SUM(CASE WHEN completed = 1 THEN 1 ELSE 0 END)                   AS completed,
            SUM(CASE WHEN completed = 0 THEN 1 ELSE 0 END)                   AS pending,
            SUM(CASE WHEN completed = 0 AND due_date IS NOT NULL
                      AND due_date < ? THEN 1 ELSE 0 END)                    AS overdue,
            SUM(CASE WHEN completed = 1 AND updated_at LIKE ? || '%%'
                      THEN 1 ELSE 0 END)                                     AS completed_today
        FROM tasks
        WHERE user_id = ?
        """,
        (today, today, user_id),
    ).fetchone()

    total = row["total"] or 0
    completed = row["completed"] or 0
    pending = row["pending"] or 0
    overdue = row["overdue"] or 0
    completed_today = row["completed_today"] or 0
    percentage = round(completed / total * 100) if total > 0 else 0

    return {
        "total": total,
        "completed": completed,
        "pending": pending,
        "overdue": overdue,
        "completion_percentage": percentage,
        "completed_today": completed_today,
    }


def get_productivity_trends(db: sqlite3.Connection, user_id: str, months_limit: int = 6) -> dict:
    """Return historical monthly task creation & completion trends, plus priority/status breakdowns."""
    # 1. Monthly creation & completion aggregations (past N months)
    # SQLite strftime('%Y-%m', created_at) and strftime('%Y-%m', updated_at)
    created_rows = db.execute(
        """
        SELECT
            strftime('%Y-%m', created_at) AS month,
            COUNT(*) AS total_created
        FROM tasks
        WHERE user_id = ? AND created_at IS NOT NULL
        GROUP BY strftime('%Y-%m', created_at)
        ORDER BY month DESC
        LIMIT ?
        """,
        (user_id, months_limit),
    ).fetchall()

    completed_rows = db.execute(
        """
        SELECT
            strftime('%Y-%m', updated_at) AS month,
            COUNT(*) AS total_completed
        FROM tasks
        WHERE user_id = ? AND completed = 1 AND updated_at IS NOT NULL
        GROUP BY strftime('%Y-%m', updated_at)
        ORDER BY month DESC
        LIMIT ?
        """,
        (user_id, months_limit),
    ).fetchall()

    # Collect distinct months and sort chronologically
    all_months = sorted(list(set(
        [r["month"] for r in created_rows if r["month"]] +
        [r["month"] for r in completed_rows if r["month"]]
    )))
    # If no data, default to current month
    if not all_months:
        now_month = datetime.now(timezone.utc).strftime("%Y-%m")
        all_months = [now_month]

    created_map = {r["month"]: r["total_created"] for r in created_rows}
    completed_map = {r["month"]: r["total_completed"] for r in completed_rows}

    monthly_data = []
    for m in all_months:
        c_created = created_map.get(m, 0)
        c_completed = completed_map.get(m, 0)
        pct = round(c_completed / c_created * 100) if c_created > 0 else 0
        monthly_data.append({
            "month": m,
            "created": c_created,
            "completed": c_completed,
            "rate": pct,
        })

    # 2. Priority breakdown
    priority_rows = db.execute(
        """
        SELECT priority, COUNT(*) AS count
        FROM tasks
        WHERE user_id = ?
        GROUP BY priority
        """,
        (user_id,),
    ).fetchall()
    priority_breakdown = {r["priority"]: r["count"] for r in priority_rows}
    for p in ["low", "medium", "high"]:
        priority_breakdown.setdefault(p, 0)

    # 3. Status breakdown
    status_rows = db.execute(
        """
        SELECT status, COUNT(*) AS count
        FROM tasks
        WHERE user_id = ?
        GROUP BY status
        """,
        (user_id,),
    ).fetchall()
    status_breakdown = {r["status"]: r["count"] for r in status_rows}
    for s in ["todo", "in_progress", "done"]:
        status_breakdown.setdefault(s, 0)

    # 4. Completion speed / on-time performance
    on_time_row = db.execute(
        """
        SELECT
            SUM(CASE WHEN completed = 1 AND due_date IS NOT NULL AND substr(updated_at, 1, 10) <= due_date THEN 1 ELSE 0 END) AS on_time,
            SUM(CASE WHEN completed = 1 AND due_date IS NOT NULL AND substr(updated_at, 1, 10) > due_date THEN 1 ELSE 0 END) AS late,
            SUM(CASE WHEN completed = 1 AND due_date IS NULL THEN 1 ELSE 0 END) AS no_deadline
        FROM tasks
        WHERE user_id = ?
        """,
        (user_id,),
    ).fetchone()

    return {
        "monthly": monthly_data,
        "priority_breakdown": priority_breakdown,
        "status_breakdown": status_breakdown,
        "delivery": {
            "on_time": on_time_row["on_time"] or 0,
            "late": on_time_row["late"] or 0,
            "no_deadline": on_time_row["no_deadline"] or 0,
        }
    }


def get_legacy_task_count(db: sqlite3.Connection) -> int:
    """Return number of tasks with no owner (legacy pre-auth tasks)."""
    row = db.execute("SELECT COUNT(*) AS cnt FROM tasks WHERE user_id IS NULL").fetchone()
    return row["cnt"] if row else 0


def claim_legacy_tasks(db: sqlite3.Connection, user_id: str) -> int:
    """Assign all unowned legacy tasks to the given user."""
    cursor = db.execute(
        "UPDATE tasks SET user_id = ? WHERE user_id IS NULL", (user_id,)
    )
    db.commit()
    return cursor.rowcount

