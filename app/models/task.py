"""
app/models/task.py
The Task table — captures category, sub-task, status, deadline, priority.
Mirrors your PHP schema (task / sub_task) but adds priority and estimated_hours
which the AI features rely on.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Float, Text
from sqlalchemy.orm import relationship

from app.database import Base


class Task(Base):
    __tablename__ = "tasks"

    id              = Column(Integer, primary_key=True, index=True)
    task            = Column(String(160), nullable=False)            # Category (e.g. "Frontend")
    sub_task        = Column(String(255), nullable=False)            # The actual work item
    description     = Column(Text, nullable=True)
    status          = Column(String(20), default="pending")          # pending | in_progress | completed
    priority        = Column(String(20), default="medium")           # low | medium | high | urgent
    deadline        = Column(DateTime, nullable=True)
    estimated_hours = Column(Float, default=0.0)                     # Used by AI deadline predictor
    assignee_id     = Column(Integer, ForeignKey("users.id"))
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    assignee = relationship("User", back_populates="tasks")
    efforts  = relationship("Effort", back_populates="task", cascade="all, delete-orphan")
