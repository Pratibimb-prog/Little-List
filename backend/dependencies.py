"""FastAPI dependency injection helpers for Little List."""

import sqlite3
from typing import Generator, Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .auth import decode_access_token
from .database import connect

security = HTTPBearer(auto_error=False)


def get_db(request: Request) -> Generator[sqlite3.Connection, None, None]:
    """Yield a database connection for the duration of the request."""
    conn = connect(request.app.state.database_path)
    try:
        yield conn
    finally:
        conn.close()


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: sqlite3.Connection = Depends(get_db),
) -> dict:
    """Return the authenticated user dict or raise 401."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = decode_access_token(credentials.credentials)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    row = db.execute(
        "SELECT id, username, created_at FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return {"id": row["id"], "username": row["username"], "created_at": row["created_at"]}
