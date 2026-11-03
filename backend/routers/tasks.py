"""Task CRUD endpoints."""

import sqlite3
from typing import Optional

from fastapi import APIRouter, Depends, Query

from ..dependencies import get_current_user, get_db
from ..models import TaskCreate, TaskUpdate
from ..services.task_service import (
    claim_legacy_tasks,
    create_task,
    delete_task,
    get_legacy_task_count,
    list_tasks,
    update_task,
)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("/legacy-count")
def legacy_count(
    user: dict = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db),
):
    return {"unclaimed_count": get_legacy_task_count(db)}


@router.post("/claim-legacy")
def claim_legacy(
    user: dict = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db),
):
    claimed = claim_legacy_tasks(db, user["id"])
    return {"claimed_count": claimed, "message": f"Successfully claimed {claimed} legacy task(s)"}


@router.get("")
def get_tasks(
    search: Optional[str] = Query(None, description="Search task text"),
    status: Optional[str] = Query(None, description="Filter by status"),
    priority: Optional[str] = Query(None, description="Filter by priority"),
    sort_by: str = Query("created_at", description="Sort field"),
    limit: int = Query(50, ge=1, le=200, description="Page size"),
    offset: int = Query(0, ge=0, description="Page offset"),
    user: dict = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db),
):
    return list_tasks(db, user["id"], search, status, priority, sort_by, limit, offset)


@router.post("", status_code=201)
def post_task(
    task: TaskCreate,
    user: dict = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db),
):
    return create_task(db, user["id"], task)


@router.patch("/{task_id}")
def patch_task(
    task_id: str,
    changes: TaskUpdate,
    user: dict = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db),
):
    return update_task(db, user["id"], task_id, changes)


@router.delete("/{task_id}", status_code=204)
def remove_task(
    task_id: str,
    user: dict = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db),
):
    return delete_task(db, user["id"], task_id)
