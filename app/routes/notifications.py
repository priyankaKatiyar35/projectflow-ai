"""
app/routes/notifications.py
Notifications API.

Endpoints:
  GET    /api/notifications              -> list of current user's notifications
  GET    /api/notifications/unread_count -> just the unread number (lightweight)
  POST   /api/notifications/{id}/read    -> mark one as read
  POST   /api/notifications/read_all     -> mark all as read
  DELETE /api/notifications/{id}         -> remove one
  DELETE /api/notifications              -> clear all read ones

Plus a helper function `notify()` other routes can use to create
notifications when something happens (e.g. task assigned).
"""
from datetime import datetime, timedelta
from typing import List, Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.database import get_db
from app.models import Notification, User
from app.routes.auth import current_user


router = APIRouter(prefix="/api/notifications", tags=["notifications"])


# ---------- Pydantic ----------

class NotificationOut(BaseModel):
    id: int
    type: str
    title: str
    body: Optional[str]
    link: Optional[str]
    is_read: bool
    created_at_iso: str
    time_ago: str

    class Config:
        from_attributes = True


def _time_ago(dt: datetime) -> str:
    """Human-friendly relative time string."""
    if not dt:
        return ""
    delta = datetime.utcnow() - dt
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    if days < 7:
        return f"{days}d ago"
    return dt.strftime("%b %d")


def _to_dict(n: Notification) -> dict:
    return {
        "id": n.id,
        "type": n.type,
        "title": n.title,
        "body": n.body,
        "link": n.link,
        "is_read": n.read_at is not None,
        "created_at_iso": n.created_at.isoformat() if n.created_at else "",
        "time_ago": _time_ago(n.created_at),
    }


# ---------- Endpoints ----------

@router.get("")
def list_notifications(limit: int = 50, user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = (
        db.query(Notification)
        .filter(Notification.user_id == user.id)
        .order_by(desc(Notification.created_at))
        .limit(limit)
        .all()
    )
    return [_to_dict(n) for n in rows]


@router.get("/unread_count")
def unread_count(user: User = Depends(current_user), db: Session = Depends(get_db)):
    count = (
        db.query(Notification)
        .filter(Notification.user_id == user.id, Notification.read_at.is_(None))
        .count()
    )
    return {"count": count}


@router.post("/{notif_id}/read")
def mark_read(notif_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    n = db.query(Notification).filter(
        Notification.id == notif_id, Notification.user_id == user.id
    ).first()
    if not n:
        raise HTTPException(404, "Notification not found")
    if n.read_at is None:
        n.read_at = datetime.utcnow()
        db.commit()
    return {"ok": True}


@router.post("/read_all")
def mark_all_read(user: User = Depends(current_user), db: Session = Depends(get_db)):
    now = datetime.utcnow()
    db.query(Notification).filter(
        Notification.user_id == user.id, Notification.read_at.is_(None)
    ).update({"read_at": now})
    db.commit()
    return {"ok": True}


@router.delete("/{notif_id}")
def delete_one(notif_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    n = db.query(Notification).filter(
        Notification.id == notif_id, Notification.user_id == user.id
    ).first()
    if not n:
        raise HTTPException(404, "Notification not found")
    db.delete(n)
    db.commit()
    return {"ok": True}


@router.delete("")
def clear_read(user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.query(Notification).filter(
        Notification.user_id == user.id, Notification.read_at.isnot(None)
    ).delete()
    db.commit()
    return {"ok": True}


# ============================================================
# Helper used by other routes to create notifications
# ============================================================

def notify(
    db: Session,
    user_id: int,
    title: str,
    body: Optional[str] = None,
    type: str = "system",
    link: Optional[str] = None,
    send_email: bool = True,
):
    """Create one notification + optionally send email. Caller must `db.commit()` after.

    Example use inside another route:
        from app.routes.notifications import notify
        notify(db, user_id=task.assignee_id,
               title="New task assigned",
               body=f"You were assigned: {task.task_description}",
               type="assigned",
               link=f"/projects/{task.project_id}")
        db.commit()
    """
    n = Notification(
        user_id=user_id,
        type=type,
        title=title,
        body=body,
        link=link,
    )
    db.add(n)

    # ----- Send email if user wants it for this type -----
    if send_email:
        try:
            from app.services.email_service import send_notification_email
            recipient = db.query(User).filter(User.id == user_id).first()
            if recipient and recipient.wants_email_for(type):
                send_notification_email(
                    to_email=recipient.email,
                    to_name=recipient.full_name,
                    title=title,
                    body=body or "",
                    link_path=link,
                    notification_type=type,
                )
        except Exception as e:
            # Email failure must never break the notification itself
            print(f"[notify] Email send failed for user {user_id}: {e}")

    return n


def notify_many(db: Session, user_ids: List[int], **kwargs):
    """Create the same notification for multiple users at once."""
    for uid in set(user_ids):  # dedupe
        notify(db, user_id=uid, **kwargs)


# ============================================================
# Scheduled-style endpoint: scan tasks for upcoming deadlines
# ============================================================

@router.post("/scan_deadlines")
def scan_deadlines(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """
    Admin-only: scans all project tasks with deadlines within 2 days
    and creates 'deadline' notifications for their assignees.
    Avoids duplicates by checking for an unread deadline notif in the
    last 24 hours per (user, task).
    """
    if user.role != "admin":
        raise HTTPException(403, "Admins only")

    from app.models import ProjectTask, Project  # local import to avoid cycles

    soon = datetime.utcnow().date() + timedelta(days=2)
    yesterday = datetime.utcnow() - timedelta(hours=24)

    tasks = (
        db.query(ProjectTask)
        .filter(
            ProjectTask.planned_end_date.isnot(None),
            ProjectTask.planned_end_date <= soon,
            ProjectTask.status != "completed",
        )
        .all()
    )

    created = 0
    for t in tasks:
        days_left = (t.planned_end_date - datetime.utcnow().date()).days
        for assignee in t.assignees:
            # Skip if we already notified them about this task recently
            existing = (
                db.query(Notification)
                .filter(
                    Notification.user_id == assignee.id,
                    Notification.type == "deadline",
                    Notification.title.like(f"%{t.task_description[:30]}%"),
                    Notification.created_at >= yesterday,
                )
                .first()
            )
            if existing:
                continue

            project_name = t.project.name if t.project else "your project"
            if days_left < 0:
                title = f"⚠️ Overdue: {t.task_description[:60]}"
                body = f"From {project_name}. Was due {abs(days_left)} day(s) ago."
            elif days_left == 0:
                title = f"📅 Due today: {t.task_description[:60]}"
                body = f"From {project_name}. Deadline is today."
            else:
                title = f"⏰ Due in {days_left}d: {t.task_description[:60]}"
                body = f"From {project_name}. Deadline approaching."

            notify(
                db, user_id=assignee.id,
                title=title, body=body,
                type="deadline",
                link=f"/projects/{t.project_id}",
            )
            created += 1
    db.commit()
    return {"created": created}