"""
app/models/project.py
A Project is a container created by the PM (admin). Each Project holds
multiple ProjectTask rows. Tasks have multiple assignees (many-to-many).
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship

from app.database import Base


class Project(Base):
    __tablename__ = "projects"

    id           = Column(Integer, primary_key=True, index=True)
    name         = Column(String(200), nullable=False)
    description  = Column(Text, nullable=True)
    status       = Column(String(30), default="not_started")  # not_started | in_progress | completed | on_hold
    created_by   = Column(Integer, ForeignKey("users.id"))
    created_at   = Column(DateTime, default=datetime.utcnow)
    updated_at   = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    creator = relationship("User", foreign_keys=[created_by])
    tasks   = relationship("ProjectTask", back_populates="project", cascade="all, delete-orphan")
