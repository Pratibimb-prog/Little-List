"""Pydantic request / response schemas for Little List."""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ---------- enums ----------

class Priority(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class Status(str, Enum):
    todo = "todo"
    in_progress = "in_progress"
    done = "done"


# ---------- task schemas ----------

class TaskCreate(BaseModel):
    text: str = Field(min_length=1, max_length=160)
    priority: Priority = Priority.medium
    due_date: Optional[date] = None

    @field_validator("text")
    @classmethod
    def strip_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Task text cannot be empty")
        return value


class TaskUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: Optional[str] = Field(default=None, min_length=1, max_length=160)
    completed: Optional[bool] = None
    priority: Optional[Priority] = None
    due_date: Optional[date] = None       # send null to clear
    status: Optional[Status] = None

    @field_validator("text")
    @classmethod
    def strip_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("Task text cannot be empty")
        return value

    @model_validator(mode="after")
    def require_changes(self) -> TaskUpdate:
        if not self.model_fields_set:
            raise ValueError("Provide at least one field to update")
        if "text" in self.model_fields_set and self.text is None:
            raise ValueError("Task text cannot be null")
        if "completed" in self.model_fields_set and self.completed is None:
            raise ValueError("Completed status cannot be null")
        if "priority" in self.model_fields_set and self.priority is None:
            raise ValueError("Priority cannot be null")
        if "status" in self.model_fields_set and self.status is None:
            raise ValueError("Status cannot be null")
        return self


class TaskResponse(BaseModel):
    id: str
    text: str
    completed: bool
    priority: str
    due_date: Optional[str] = None
    status: str
    created_at: str
    updated_at: Optional[str] = None


# ---------- auth schemas ----------

class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=6, max_length=128)

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Username cannot be empty")
        if not all(c.isalnum() or c in "-_" for c in value):
            raise ValueError(
                "Username may only contain letters, numbers, hyphens, and underscores"
            )
        return value


class UserLogin(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    id: str
    username: str
    created_at: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---------- stats ----------

class StatsResponse(BaseModel):
    total: int
    completed: int
    pending: int
    overdue: int
    completion_percentage: int
    completed_today: int
