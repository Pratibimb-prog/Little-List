"""Statistics endpoint."""

import sqlite3

from fastapi import APIRouter, Depends

from ..dependencies import get_current_user, get_db
from ..services.task_service import get_productivity_trends, get_stats

router = APIRouter(prefix="/api", tags=["stats"])


@router.get("/stats")
def stats(
    user: dict = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db),
):
    return get_stats(db, user["id"])


@router.get("/stats/trends")
def trends(
    months: int = 12,
    user: dict = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db),
):
    return get_productivity_trends(db, user["id"], months_limit=months)
