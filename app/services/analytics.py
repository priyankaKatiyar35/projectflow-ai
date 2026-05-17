"""
app/services/analytics.py
Replaces every count_* / aggregation function from your PHP files.
Each function takes a SQLAlchemy session + optional user_id and returns
plain dicts/numbers ready for the dashboard or charts.
"""
from datetime import datetime, date, timedelta
from typing import Optional, Dict, List
from sqlalchemy import func, and_
from sqlalchemy.orm import Session

from app.models import User, Task, Effort


# ============ Task counts (admin-wide or per-user) ============

def _task_query(db: Session, user_id: Optional[int] = None):
    q = db.query(Task)
    if user_id:
        q = q.filter(Task.assignee_id == user_id)
    return q


def count_tasks(db: Session, user_id: Optional[int] = None) -> int:
    return _task_query(db, user_id).count()


def count_by_status(db: Session, status: str, user_id: Optional[int] = None) -> int:
    return _task_query(db, user_id).filter(Task.status == status).count()


def count_overdue(db: Session, user_id: Optional[int] = None) -> int:
    now = datetime.utcnow()
    return (
        _task_query(db, user_id)
        .filter(Task.deadline.isnot(None), Task.deadline < now, Task.status != "completed")
        .count()
    )


def count_due_today(db: Session, user_id: Optional[int] = None) -> int:
    today_start = datetime.combine(date.today(), datetime.min.time())
    today_end   = datetime.combine(date.today(), datetime.max.time())
    return (
        _task_query(db, user_id)
        .filter(Task.deadline.between(today_start, today_end), Task.status != "completed")
        .count()
    )


def count_no_deadline(db: Session, user_id: Optional[int] = None) -> int:
    return _task_query(db, user_id).filter(Task.deadline.is_(None)).count()


# ============ Dashboard headline numbers ============

def dashboard_stats(db: Session, user_id: Optional[int] = None) -> Dict:
    """Returns the eight numbers the cards on top of the dashboard show."""
    return {
        "users":        db.query(User).count() if user_id is None else None,
        "total_tasks":  count_tasks(db, user_id),
        "pending":      count_by_status(db, "pending", user_id),
        "in_progress":  count_by_status(db, "in_progress", user_id),
        "completed":    count_by_status(db, "completed", user_id),
        "overdue":      count_overdue(db, user_id),
        "due_today":    count_due_today(db, user_id),
        "no_deadline":  count_no_deadline(db, user_id),
    }


# ============ Chart data ============

def effort_by_category(db: Session, user_id: Optional[int] = None) -> Dict[str, float]:
    """Aggregated effort (hours) grouped by Task.task (the category)."""
    q = (
        db.query(Task.task, func.sum(Effort.minutes))
        .join(Effort, Effort.task_id == Task.id)
        .group_by(Task.task)
    )
    if user_id:
        q = q.filter(Task.assignee_id == user_id)
    return {row[0]: round((row[1] or 0) / 60, 2) for row in q.all()}


def effort_by_subtask(db: Session, user_id: Optional[int] = None) -> Dict[str, float]:
    """Aggregated effort (hours) grouped by Task.sub_task."""
    q = (
        db.query(Task.sub_task, func.sum(Effort.minutes))
        .join(Effort, Effort.task_id == Task.id)
        .group_by(Task.sub_task)
    )
    if user_id:
        q = q.filter(Task.assignee_id == user_id)
    return {row[0]: round((row[1] or 0) / 60, 2) for row in q.all()}


def employee_progress(db: Session) -> Dict[str, Dict[str, int]]:
    """For the stacked bar chart: each employee's pending/in_progress/completed counts."""
    out: Dict[str, Dict[str, int]] = {}
    for user in db.query(User).filter(User.role != "admin").all():
        out[user.full_name] = {
            "Pending":     count_by_status(db, "pending", user.id),
            "In Progress": count_by_status(db, "in_progress", user.id),
            "Completed":   count_by_status(db, "completed", user.id),
        }
    return out


def employee_activity(db: Session) -> Dict[str, float]:
    """Total effort (hours) logged per employee."""
    rows = (
        db.query(User.full_name, func.sum(Effort.minutes))
        .join(Effort, Effort.user_id == User.id)
        .group_by(User.full_name)
        .all()
    )
    return {name: round((mins or 0) / 60, 2) for name, mins in rows}


def productivity_trend(db: Session, user_id: Optional[int] = None, days: int = 14) -> Dict:
    """Hours logged per day for the last `days` days — drives the line chart."""
    start = date.today() - timedelta(days=days - 1)
    q = db.query(Effort.log_date, func.sum(Effort.minutes)).filter(Effort.log_date >= start)
    if user_id:
        q = q.filter(Effort.user_id == user_id)
    rows = dict(q.group_by(Effort.log_date).all())

    labels, values = [], []
    for i in range(days):
        d = start + timedelta(days=i)
        labels.append(d.strftime("%b %d"))
        values.append(round((rows.get(d, 0) or 0) / 60, 2))
    return {"labels": labels, "values": values}


def online_presence(db: Session) -> Dict[str, str]:
    """Human-readable 'last seen' string per user (mirrors your PHP block)."""
    out = {}
    now = datetime.utcnow()
    for u in db.query(User).all():
        if not u.last_online:
            continue
        diff = now - u.last_online
        mins = diff.total_seconds() / 60
        if mins < 5:
            label = "Just now"
        elif mins < 60:
            label = f"{int(mins)} minutes ago"
        elif diff.days == 0:
            label = "Today at " + u.last_online.strftime("%I:%M %p").lstrip("0")
        elif diff.days == 1:
            label = "Yesterday at " + u.last_online.strftime("%I:%M %p").lstrip("0")
        else:
            label = u.last_online.strftime("%b %d at %I:%M %p").replace(" 0", " ")
        out[u.full_name] = label
    return out
