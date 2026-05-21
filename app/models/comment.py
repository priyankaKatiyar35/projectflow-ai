"""
app/models/comment.py
Comments on project tasks — for team discussion, status updates,
and CMMI traceability of decisions.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from app.database import Base


class Comment(Base):
    __tablename__ = "comments"

    id              = Column(Integer, primary_key=True, index=True)
    project_task_id = Column(Integer, ForeignKey("project_tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    author_id       = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    body            = Column(Text, nullable=False)
    created_at      = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    author = relationship("User", foreign_keys=[author_id])
    task   = relationship("ProjectTask", foreign_keys=[project_task_id])