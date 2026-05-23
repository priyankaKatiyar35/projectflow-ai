"""
app/routes/search.py
Global search across projects, tasks, users, and comments.

GET /api/search?q=...  -> categorized results

Permission rules:
  - Admins see everything
  - Employees see:
      * Projects they have tasks in
      * Tasks assigned to them
      * Comments on tasks they're assigned to
      * No user listings
"""
from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, Project, ProjectTask, Comment, Objective, KeyResult
from app.routes.auth import current_user


router = APIRouter(prefix="/api/search", tags=["search"])


MAX_PER_CATEGORY = 8  # Limit results per category to keep UI fast and clean


def _highlight(text: str, query: str) -> str:
    """Return a short snippet showing where match was found."""
    if not text or not query:
        return text or ""
    lower_text = text.lower()
    lower_query = query.lower()
    pos = lower_text.find(lower_query)
    if pos == -1:
        # No exact match (maybe matched a different field) — return first 80 chars
        return text[:80] + ("..." if len(text) > 80 else "")
    # Center window around the match
    start = max(0, pos - 30)
    end = min(len(text), pos + len(query) + 50)
    snippet = text[start:end]
    if start > 0:
        snippet = "..." + snippet
    if end < len(text):
        snippet = snippet + "..."
    return snippet


@router.get("")
def search(q: str = "", user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = q.strip()
    if len(q) < 2:
        return {"query": q, "results": [], "total": 0}

    pattern = f"%{q}%"
    results = []

    # ========== PROJECTS ==========
    project_query = db.query(Project).filter(
        or_(
            Project.name.ilike(pattern),
            Project.description.ilike(pattern),
        )
    )
    if user.role != "admin":
        # Employees: only projects where they have an assigned task
        user_project_ids = select(ProjectTask.project_id).where(
            ProjectTask.assignees.any(User.id == user.id)
        ).distinct()
        project_query = project_query.filter(Project.id.in_(user_project_ids))

    for p in project_query.limit(MAX_PER_CATEGORY).all():
        results.append({
            "type": "project",
            "id": p.id,
            "title": p.name,
            "snippet": _highlight(p.description or "No description", q),
            "link": f"/projects/{p.id}",
            "icon": "folder",
            "color": "blue",
            "category": "Projects",
        })

    # ========== PROJECT TASKS ==========
    task_query = db.query(ProjectTask).filter(
        or_(
            ProjectTask.task_description.ilike(pattern),
            ProjectTask.milestone_phase.ilike(pattern),
            ProjectTask.action_item.ilike(pattern),
            ProjectTask.category.ilike(pattern),
        )
    )
    if user.role != "admin":
        task_query = task_query.filter(ProjectTask.assignees.any(User.id == user.id))

    for t in task_query.limit(MAX_PER_CATEGORY).all():
        snippet_parts = []
        if t.milestone_phase: snippet_parts.append(t.milestone_phase)
        if t.action_item: snippet_parts.append(t.action_item)
        if t.status: snippet_parts.append(f"Status: {t.status}")
        snippet = " · ".join(snippet_parts) or "Task"
        results.append({
            "type": "task",
            "id": t.id,
            "title": t.task_description or "Untitled task",
            "snippet": _highlight(snippet, q),
            "link": f"/projects/{t.project_id}",
            "icon": "check-square",
            "color": "purple",
            "category": "Tasks",
            "project_name": t.project.name if t.project else "",
        })

    # ========== USERS (admin only) ==========
    if user.role == "admin":
        users = (
            db.query(User)
            .filter(or_(User.full_name.ilike(pattern), User.email.ilike(pattern)))
            .limit(MAX_PER_CATEGORY)
            .all()
        )
        for u in users:
            results.append({
                "type": "user",
                "id": u.id,
                "title": u.full_name,
                "snippet": f"{u.email} · {u.role}",
                "link": "/admin/users",
                "icon": "user",
                "color": "emerald",
                "category": "Users",
            })

    # ========== COMMENTS ==========
    comment_query = db.query(Comment).filter(Comment.body.ilike(pattern))
    if user.role != "admin":
        # Employees can only see comments on tasks they're assigned to
        my_task_ids = select(ProjectTask.id).where(
            ProjectTask.assignees.any(User.id == user.id)
        )
        comment_query = comment_query.filter(Comment.project_task_id.in_(my_task_ids))

    for c in comment_query.order_by(Comment.created_at.desc()).limit(MAX_PER_CATEGORY).all():
        author_name = c.author.full_name if c.author else "Unknown"
        task_desc = c.task.task_description if c.task else ""
        results.append({
            "type": "comment",
            "id": c.id,
            "title": f'"{_highlight(c.body, q)}"',
            "snippet": f"{author_name} on {task_desc[:40]}",
            "link": f"/projects/{c.task.project_id}" if c.task else "/",
            "icon": "message-circle",
            "color": "amber",
            "category": "Comments",
        })

    # ========== OBJECTIVES / OKRs ==========
    obj_query = db.query(Objective).filter(
        or_(
            Objective.title.ilike(pattern),
            Objective.description.ilike(pattern),
            Objective.category.ilike(pattern),
            Objective.period_label.ilike(pattern),
        )
    )
    if user.role != "admin":
        # Non-admins only see company-visible or their own private objectives
        obj_query = obj_query.filter(
            or_(Objective.visibility == "company", Objective.owner_id == user.id)
        )

    for o in obj_query.limit(MAX_PER_CATEGORY).all():
        results.append({
            "type": "objective",
            "id": o.id,
            "title": o.title,
            "snippet": f"{o.period_label} · {o.category or 'Uncategorized'} · {int(o.progress_pct)}% complete",
            "link": "/okrs",
            "icon": "target",
            "color": "rose",
            "category": "Objectives",
        })

    # Order: projects > tasks > objectives > users > comments
    type_order = {"project": 0, "task": 1, "objective": 2, "user": 3, "comment": 4}
    results.sort(key=lambda r: type_order.get(r["type"], 9))

    return {
        "query": q,
        "results": results,
        "total": len(results),
    }