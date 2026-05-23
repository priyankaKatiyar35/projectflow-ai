"""
app/models/attachment.py
File attachments on project tasks.

Files are stored on disk under data/uploads/ with UUID-based names.
The DB stores metadata only (original filename, size, mime, uploader, timestamps).
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, BigInteger
from sqlalchemy.orm import relationship, backref

from app.database import Base


class Attachment(Base):
    __tablename__ = "attachments"

    id              = Column(Integer, primary_key=True, index=True)
    project_task_id = Column(Integer, ForeignKey("project_tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    uploader_id     = Column(Integer, ForeignKey("users.id"), nullable=False)

    # File metadata
    original_name   = Column(String(300), nullable=False)  # what the user uploaded
    stored_name     = Column(String(300), nullable=False)  # UUID-based name on disk
    mime_type       = Column(String(100), nullable=True)
    size_bytes      = Column(BigInteger, nullable=False, default=0)

    created_at      = Column(DateTime, default=datetime.utcnow, index=True)

    # Relationships
    project_task = relationship("ProjectTask", backref=backref("attachments", cascade="all, delete-orphan"))
    uploader     = relationship("User", foreign_keys=[uploader_id])

    @property
    def is_image(self) -> bool:
        return bool(self.mime_type and self.mime_type.startswith("image/"))

    @property
    def size_human(self) -> str:
        """Returns size like '2.3 MB' or '450 KB'."""
        size = self.size_bytes
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024:
                return f"{size:.1f} {unit}" if unit != "B" else f"{size} {unit}"
            size /= 1024
        return f"{size:.1f} TB"