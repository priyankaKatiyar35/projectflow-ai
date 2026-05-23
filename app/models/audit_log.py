"""
app/models/audit_log.py
Audit log entries for CMMI compliance.

EVERY important state change creates a row here:
  - user creation / edit / delete / role change
  - project / task / objective CRUD
  - comments posted / edited / deleted
  - login attempts (success and failure)
  - password resets and changes

Design principles:
  - Append-only (we never UPDATE or DELETE rows in this table)
  - Self-contained: stores user name and entity name at time of action
    so even if user/entity is later deleted, the audit trail stays readable
  - Stores JSON diff of before/after for updates
  - Indexed on entity + timestamp for fast filtering
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Index

from app.database import Base


# Common action constants (for autocomplete and consistency)
ACTION_CREATED  = "created"
ACTION_UPDATED  = "updated"
ACTION_DELETED  = "deleted"
ACTION_LOGIN    = "login"
ACTION_LOGOUT   = "logout"
ACTION_LOGIN_FAILED = "login_failed"
ACTION_PASSWORD_RESET   = "password_reset"
ACTION_PASSWORD_CHANGED = "password_changed"
ACTION_ROLE_CHANGED    = "role_changed"
ACTION_REASSIGNED      = "reassigned"
ACTION_STATUS_CHANGED  = "status_changed"
ACTION_CHECKIN         = "checkin"
ACTION_COMMENT_POSTED  = "comment_posted"

# Categories for filtering
CATEGORY_DATA     = "data"      # CRUD on business entities
CATEGORY_AUTH     = "auth"      # login/logout/password
CATEGORY_SECURITY = "security"  # role changes, sensitive ops, failures
CATEGORY_ADMIN    = "admin"     # admin-only ops


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id          = Column(Integer, primary_key=True, index=True)

    # When
    created_at  = Column(DateTime, default=datetime.utcnow, index=True, nullable=False)

    # Who (snapshot - kept even if user later deleted)
    actor_id        = Column(Integer, nullable=True, index=True)  # null = system / anonymous
    actor_name      = Column(String(150), nullable=True)
    actor_email     = Column(String(150), nullable=True)
    actor_role      = Column(String(30), nullable=True)

    # From where
    ip_address      = Column(String(50), nullable=True)
    user_agent      = Column(String(300), nullable=True)

    # What action
    action          = Column(String(50), nullable=False, index=True)
    category        = Column(String(30), nullable=False, default=CATEGORY_DATA, index=True)

    # On what entity
    entity_type     = Column(String(50), nullable=True, index=True)  # user, project, project_task, objective, kr, comment
    entity_id       = Column(Integer, nullable=True, index=True)
    entity_label    = Column(String(300), nullable=True)  # human-readable label snapshot

    # Free-text summary like "Bob Smith assigned to task #12"
    summary         = Column(String(500), nullable=True)

    # JSON diff of changes (for updates) and additional context
    # Format: {"before": {...}, "after": {...}, "fields_changed": ["x","y"], ...}
    details_json    = Column(Text, nullable=True)

    # For sensitive/security events flag
    is_sensitive    = Column(Integer, default=0, nullable=False)  # 0 or 1


# Composite indexes for common queries
Index("ix_audit_entity", AuditLog.entity_type, AuditLog.entity_id, AuditLog.created_at.desc())
Index("ix_audit_actor_time", AuditLog.actor_id, AuditLog.created_at.desc())