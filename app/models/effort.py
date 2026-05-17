"""
app/models/effort.py
The Effort table — every time-log entry against a task.
Replaces your PHP `efforts.start_time` (HH:MM string). Here we store
minutes as an integer for clean math — no parsing required.
"""
from datetime import datetime, date
from sqlalchemy import Column, Integer, Date, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship

from app.database import Base


class Effort(Base):
    __tablename__ = "efforts"

    id          = Column(Integer, primary_key=True, index=True)
    task_id     = Column(Integer, ForeignKey("tasks.id"), nullable=False)
    user_id     = Column(Integer, ForeignKey("users.id"), nullable=False)
    minutes     = Column(Integer, nullable=False, default=0)
    log_date    = Column(Date, default=date.today)
    notes       = Column(Text, nullable=True)
    created_at  = Column(DateTime, default=datetime.utcnow)

    task = relationship("Task", back_populates="efforts")
    user = relationship("User", back_populates="efforts")
