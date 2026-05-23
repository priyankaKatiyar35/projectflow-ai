"""
app/services/audit_service.py

Helper functions other routes use to log audit events.

Example:
    from app.services.audit_service import log_audit, diff_dict
    log_audit(db, request, user,
              action="updated",
              entity_type="project",
              entity_id=project.id,
              entity_label=project.name,
              summary=f"Renamed project from '{old}' to '{new}'",
              details={"before": {"name": old}, "after": {"name": new}})

For updates, use `diff_dict(before, after)` to get a clean diff.
"""
import json
from typing import Optional, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session

from app.models import AuditLog, User
from app.models.audit_log import (
    CATEGORY_DATA, CATEGORY_AUTH, CATEGORY_SECURITY, CATEGORY_ADMIN,
)


# Actions that are auto-classified as sensitive
SENSITIVE_ACTIONS = {
    "deleted", "role_changed", "password_reset", "password_changed",
    "login_failed",
}


def log_audit(
    db: Session,
    request=None,
    actor: Optional[User] = None,
    action: str = "",
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    entity_label: Optional[str] = None,
    summary: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    category: str = CATEGORY_DATA,
    is_sensitive: Optional[bool] = None,
    commit: bool = False,
):
    """Create an audit log entry. By default does NOT commit (caller commits with rest of transaction)."""
    ip = ""
    ua = ""
    if request is not None:
        try:
            ip = request.client.host if request.client else ""
            ua = request.headers.get("user-agent", "")[:300]
        except Exception:
            pass

    if is_sensitive is None:
        is_sensitive = (action in SENSITIVE_ACTIONS) or (category == CATEGORY_SECURITY)

    entry = AuditLog(
        actor_id=actor.id if actor else None,
        actor_name=actor.full_name if actor else None,
        actor_email=actor.email if actor else None,
        actor_role=actor.role if actor else None,
        ip_address=ip,
        user_agent=ua,
        action=action,
        category=category,
        entity_type=entity_type,
        entity_id=entity_id,
        entity_label=(entity_label or "")[:300],
        summary=(summary or "")[:500],
        details_json=json.dumps(details, default=str) if details else None,
        is_sensitive=1 if is_sensitive else 0,
    )
    db.add(entry)
    if commit:
        db.commit()
    return entry


def diff_dict(before: dict, after: dict, ignore: tuple = ()) -> dict:
    """Calculate a clean diff between two dicts. Returns {field: {before, after}}.

    Ignore fields like 'updated_at' that change automatically.
    """
    default_ignore = ("updated_at", "created_at")
    skip = set(default_ignore) | set(ignore)
    diff = {}
    keys = set(before.keys()) | set(after.keys())
    for k in keys:
        if k in skip:
            continue
        b = before.get(k)
        a = after.get(k)
        # Normalize datetimes/dates to strings for comparison
        if hasattr(b, "isoformat"):
            b = b.isoformat()
        if hasattr(a, "isoformat"):
            a = a.isoformat()
        if b != a:
            diff[k] = {"before": b, "after": a}
    return diff


def snapshot_user(u: User) -> dict:
    return {"id": u.id, "full_name": u.full_name, "email": u.email, "role": u.role}


def snapshot_project(p) -> dict:
    return {
        "id": p.id, "name": p.name,
        "description": p.description, "status": p.status,
    }


def snapshot_project_task(t) -> dict:
    return {
        "id": t.id,
        "milestone_phase": t.milestone_phase,
        "category": t.category,
        "task_description": t.task_description,
        "action_item": t.action_item,
        "planned_start_date": t.planned_start_date,
        "planned_end_date": t.planned_end_date,
        "planned_effort": t.planned_effort,
        "actual_start_date": t.actual_start_date,
        "actual_end_date": t.actual_end_date,
        "actual_effort": t.actual_effort,
        "status": t.status,
        "remarks": t.remarks,
        "assignee_ids": sorted([a.id for a in (t.assignees or [])]),
    }


def snapshot_objective(o) -> dict:
    return {
        "id": o.id, "title": o.title, "description": o.description,
        "category": o.category, "period_label": o.period_label,
        "owner_id": o.owner_id, "visibility": o.visibility,
        "status_override": o.status_override,
    }