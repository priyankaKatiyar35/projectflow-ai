"""
app/models/notification.py
A notification is a message shown to a user — like task assignments,
deadline warnings, or system events.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship

from app.database import Base


class Notification(Base):
    __tablename__ = "notifications"

    id          = Column(Integer, primary_key=True, index=True)
    user_id     = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Type categorises the notification (used for icon & color)
    # assigned | edited | deadline | comment | report | system | role_change
    type        = Column(String(30), nullable=False, default="system")

    title       = Column(String(200), nullable=False)
    body        = Column(Text, nullable=True)

    # Optional URL to take user when they click the notification
    link        = Column(String(500), nullable=True)

    read_at     = Column(DateTime, nullable=True)   # null = unread
    created_at  = Column(DateTime, default=datetime.utcnow, index=True)

    user = relationship("User", foreign_keys=[user_id])