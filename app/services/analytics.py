"""
app/services/analytics.py
Dashboard stats backed by ProjectTask (the real data model).
"""
from datetime import datetime, date, timedelta
from typing import Optional, Dict, List
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models import User, Project, ProjectTask


def _scope_tasks(db: Session, user_id: Optional[int] = None):
    q = db.query(ProjectTask)
    if user_id is not None:
        q = q.filter(ProjectTask.assignees.any(User.id == user_id))
    return q


def dashboard_stats(db: Session, user_id: Optional[int] = None) -> Dict:
    today = date.today()
    base = _scope_tasks(db, user_id)

    total = base.count()
    completed = base.filter(ProjectTask.status == "completed").count()
    in_progress = base.filter(ProjectTask.status == "in_progress").count()
    not_started = base.filter(or_(ProjectTask.status == "not_started", ProjectTask.status.is_(None))).count()
    delayed = base.filter(
        ProjectTask.status != "completed",
        ProjectTask.planned_end_date < today,
        ProjectTask.planned_end_date.isnot(None),
    ).count()

    rows = base.all()
    planned_effort = sum((t.planned_effort or 0) for t in rows)
    actual_effort  = sum((t.actual_effort or 0) for t in rows)

    if user_id is None:
        total_users = db.query(User).count()
        total_projects = db.query(Project).count()
    else:
        total_users = 0
        total_projects = (
            db.query(Project).join(ProjectTask)
            .filter(ProjectTask.assignees.any(User.id == user_id))
            .distinct().count()
        )

    return {
        "total_tasks": total,
        "completed_tasks": completed,
        "in_progress_tasks": in_progress,
        "not_started_tasks": not_started,
        "delayed_tasks": delayed,
        "completion_pct": round((completed / total) * 100, 1) if total else 0,
        "planned_effort_hours": round(planned_effort, 1),
        "actual_effort_hours": round(actual_effort, 1),
        "effort_variance_pct": round(((actual_effort - planned_effort) / planned_effort) * 100, 1) if planned_effort else 0,
        "total_users": total_users,
        "total_projects": total_projects,
    }


def status_breakdown(db: Session, user_id: Optional[int] = None) -> List[Dict]:
    rows = _scope_tasks(db, user_id).all()
    counts = {}
    for t in rows:
        s = t.status or "not_started"
        counts[s] = counts.get(s, 0) + 1
    label_map = {
        "completed":   ("Completed",   "#10b981"),
        "in_progress": ("In progress", "#3b82f6"),
        "not_started": ("Not started", "#94a3b8"),
        "blocked":     ("Blocked",     "#ef4444"),
    }
    out = []
    for status, count in counts.items():
        label, color = label_map.get(status, (status, "#64748b"))
        out.append({"status": status, "label": label, "count": count, "color": color})
    return out


def productivity_trend(db: Session, user_id: Optional[int] = None, days: int = 14) -> List[Dict]:
    today = date.today()
    start = today - timedelta(days=days - 1)
    rows = _scope_tasks(db, user_id).filter(
        ProjectTask.actual_end_date >= start,
        ProjectTask.actual_end_date <= today,
        ProjectTask.status == "completed",
    ).all()

    counts_by_day = {}
    for t in rows:
        if t.actual_end_date:
            counts_by_day[t.actual_end_date] = counts_by_day.get(t.actual_end_date, 0) + 1

    series = []
    for i in range(days):
        d = start + timedelta(days=i)
        series.append({
            "date": d.isoformat(),
            "label": d.strftime("%b %d"),
            "completed": counts_by_day.get(d, 0),
        })
    return series


def effort_by_category(db: Session, user_id: Optional[int] = None) -> List[Dict]:
    rows = _scope_tasks(db, user_id).all()
    by_cat = {}
    for t in rows:
        cat = t.category or "Uncategorized"
        if cat not in by_cat:
            by_cat[cat] = {"actual": 0, "planned": 0}
        by_cat[cat]["actual"] += (t.actual_effort or 0)
        by_cat[cat]["planned"] += (t.planned_effort or 0)
    return [
        {"category": cat, "actual_hours": round(v["actual"], 1), "planned_hours": round(v["planned"], 1)}
        for cat, v in by_cat.items()
    ]


def employee_activity(db: Session) -> List[Dict]:
    users = db.query(User).filter(User.role == "employee").all()
    now = datetime.utcnow()
    out = []
    for u in users:
        assigned = db.query(ProjectTask).filter(ProjectTask.assignees.any(User.id == u.id)).count()
        in_progress = db.query(ProjectTask).filter(
            ProjectTask.assignees.any(User.id == u.id),
            ProjectTask.status == "in_progress",
        ).count()
        done_recent = db.query(ProjectTask).filter(
            ProjectTask.assignees.any(User.id == u.id),
            ProjectTask.status == "completed",
            ProjectTask.actual_end_date >= (date.today() - timedelta(days=7)),
        ).count()
        is_online = False
        minutes_ago = None
        if u.last_online:
            delta = now - u.last_online
            minutes_ago = int(delta.total_seconds() // 60)
            is_online = minutes_ago < 15
        out.append({
            "id": u.id, "name": u.full_name, "email": u.email,
            "is_online": is_online, "minutes_ago": minutes_ago,
            "assigned_count": assigned, "in_progress_count": in_progress,
            "completed_last_7d": done_recent,
        })
    return out


def employee_progress(db: Session) -> List[Dict]:
    users = db.query(User).filter(User.role == "employee").all()
    out = []
    for u in users:
        total = db.query(ProjectTask).filter(ProjectTask.assignees.any(User.id == u.id)).count()
        done  = db.query(ProjectTask).filter(
            ProjectTask.assignees.any(User.id == u.id),
            ProjectTask.status == "completed",
        ).count()
        out.append({
            "id": u.id, "name": u.full_name,
            "completed": done, "total": total,
            "pct": round((done / total) * 100, 1) if total else 0,
        })
    out.sort(key=lambda x: -x["pct"])
    return out


def recent_activity(db: Session, limit: int = 10) -> List[Dict]:
    rows = db.query(ProjectTask).order_by(ProjectTask.id.desc()).limit(limit).all()
    return [
        {
            "id": t.id,
            "task_description": t.task_description,
            "project_name": t.project.name if t.project else "(no project)",
            "project_id": t.project_id,
            "status": t.status,
            "assignees": [a.full_name for a in t.assignees],
            "due_date": t.planned_end_date.isoformat() if t.planned_end_date else None,
            "is_overdue": (t.planned_end_date and t.planned_end_date < date.today() and t.status != "completed"),
        }
        for t in rows
    ]