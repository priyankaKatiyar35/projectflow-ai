"""
app/schemas/schemas.py
Pydantic models that validate incoming JSON and shape outgoing JSON.
Keeps the API layer type-safe and gives auto-generated OpenAPI docs.
"""
from datetime import datetime, date
from typing import Optional, List
from pydantic import BaseModel, EmailStr


# ---------- Auth ----------
class LoginIn(BaseModel):
    email: EmailStr
    password: str


# ---------- Task ----------
class TaskCreate(BaseModel):
    task: str
    sub_task: str
    description: Optional[str] = None
    status: str = "pending"
    priority: str = "medium"
    deadline: Optional[datetime] = None
    estimated_hours: float = 0.0
    assignee_id: int


class TaskUpdate(BaseModel):
    task: Optional[str] = None
    sub_task: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    deadline: Optional[datetime] = None
    estimated_hours: Optional[float] = None
    assignee_id: Optional[int] = None


class TaskOut(BaseModel):
    id: int
    task: str
    sub_task: str
    description: Optional[str]
    status: str
    priority: str
    deadline: Optional[datetime]
    estimated_hours: float
    assignee_id: int

    class Config:
        from_attributes = True


# ---------- Effort ----------
class EffortCreate(BaseModel):
    task_id: int
    minutes: int
    log_date: Optional[date] = None
    notes: Optional[str] = None


# ---------- AI ----------
class AIChatIn(BaseModel):
    message: str


class AIChatOut(BaseModel):
    reply: str
    sources: List[str] = []


class NLTaskIn(BaseModel):
    text: str  # "Design login page for Priya by Friday, high priority, ~6 hours"


class NLTaskOut(BaseModel):
    task: str
    sub_task: str
    priority: str
    estimated_hours: float
    deadline: Optional[datetime]
    assignee_name: Optional[str]
    raw_input: str
