"""Authentication endpoints: register, login, logout, current user."""

import sqlite3
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from ..auth import create_access_token, hash_password, verify_password
from ..dependencies import get_current_user, get_db
from ..models import TokenResponse, UserCreate, UserLogin, UserResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", status_code=201, response_model=UserResponse)
def register(
    user_data: UserCreate,
    db: sqlite3.Connection = Depends(get_db),
):
    existing = db.execute(
        "SELECT id FROM users WHERE username = ?", (user_data.username,)
    ).fetchone()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already taken",
        )

    user_id = str(uuid4())
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    pw_hash = hash_password(user_data.password)

    db.execute(
        "INSERT INTO users (id, username, password_hash, created_at) VALUES (?, ?, ?, ?)",
        (user_id, user_data.username, pw_hash, created_at),
    )
    db.commit()

    return UserResponse(id=user_id, username=user_data.username, created_at=created_at)


@router.post("/login", response_model=TokenResponse)
def login(
    credentials: UserLogin,
    db: sqlite3.Connection = Depends(get_db),
):
    row = db.execute(
        "SELECT id, password_hash FROM users WHERE username = ?",
        (credentials.username,),
    ).fetchone()
    if row is None or not verify_password(credentials.password, row["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    token = create_access_token(row["id"])
    return TokenResponse(access_token=token)


@router.post("/logout")
def logout():
    # JWT is stateless — the client simply discards the token.
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=UserResponse)
def me(user: dict = Depends(get_current_user)):
    return UserResponse(**user)
