"""
app/models/user.py
The User table — holds employees and admins.
Replaces your PHP `users` table with a clean SQLAlchemy version.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.orm import relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id            = Column(Integer, primary_key=True, index=True)
    full_name     = Column(String(120), nullable=False)
    email         = Column(String(120), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role          = Column(String(20), nullable=False, default="employee")  # admin | employee
    last_online   = Column(DateTime, nullable=True)
    created_at    = Column(DateTime, default=datetime.utcnow)

    # Relationships
    tasks   = relationship("Task", back_populates="assignee", cascade="all, delete-orphan")
    efforts = relationship("Effort", back_populates="user", cascade="all, delete-orphan")
