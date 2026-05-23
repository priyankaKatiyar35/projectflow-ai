"""
app/models/password_reset.py
Secure tokens for password reset.

Each token is:
  - linked to one user
  - valid for 1 hour from creation
  - single-use (used_at flag set after use)
  - opaque random string (32+ characters, safe to share via URL)
"""
import secrets
from datetime import datetime, timedelta
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from app.database import Base


TOKEN_VALID_HOURS = 1


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id         = Column(Integer, primary_key=True, index=True)
    user_id    = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token      = Column(String(128), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    used_at    = Column(DateTime, nullable=True)  # null = not yet used
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", foreign_keys=[user_id])

    @staticmethod
    def generate_token() -> str:
        """Create a URL-safe random token."""
        return secrets.token_urlsafe(48)

    @property
    def is_valid(self) -> bool:
        return self.used_at is None and self.expires_at > datetime.utcnow()

    @staticmethod
    def expiry_time() -> datetime:
        return datetime.utcnow() + timedelta(hours=TOKEN_VALID_HOURS)