"""
app/routes/comments.py
Comments on project tasks.

Endpoints:
  GET    /api/comments/task/{task_id}  -> list comments on a task
  POST   /api/comments/task/{task_id}  -> add comment
  PATCH  /api/comments/{id}            -> edit own comment
  DELETE /api/comments/{id}            -> delete own (or any if admin)

Permissions:
  - Admins can see/post/edit/delete any comment
  - Employees can only see/post on tasks they're assigned to
  - Anyone can edit/delete their own comments
"""
import re
from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Comment, ProjectTask, User
from app.routes.auth import current_user
from app.routes.notifications import notify_many, notify


router = APIRouter(prefix="/api/comments", tags=["comments"])


# ---------- Pydantic ----------

class CommentIn(BaseModel):
    body: str


def _time_ago(dt: datetime) -> str:
    if not dt:
        return ""
    delta = datetime.utcnow() - dt
    s = int(delta.total_seconds())
    if s < 60:   return "just now"
    if s < 3600: return f"{s // 60}m ago"
    if s < 86400:return f"{s // 3600}h ago"
    if s < 604800: return f"{s // 86400}d ago"
    return dt.strftime("%b %d")


def _to_dict(c: Comment) -> dict:
    return {
        "id": c.id,
        "task_id": c.project_task_id,
        "author_id": c.author_id,
        "author_name": c.author.full_name if c.author else "(unknown)",
        "body": c.body,
        "created_at": c.created_at.isoformat() if c.created_at else "",
        "updated_at": c.updated_at.isoformat() if c.updated_at else "",
        "time_ago": _time_ago(c.created_at),
        "edited": c.updated_at and c.created_at and (c.updated_at - c.created_at).total_seconds() > 5,
    }


def _can_see_task(user: User, task: ProjectTask) -> bool:
    """User can see comments if admin OR assigned to the task."""
    if user.role == "admin":
        return True
    return user.id in [a.id for a in task.assignees]


def _extract_mentions(body: str, all_users: list) -> list:
    """Find @username mentions in comment body. Returns list of matched user IDs.

    Matches the first word of full_name case-insensitively, e.g. @Priya matches "Priya Patel".
    """
    mentioned_ids = []
    found_words = set(re.findall(r"@([A-Za-z][A-Za-z0-9_-]*)", body))
    if not found_words:
        return []
    found_lower = {w.lower() for w in found_words}
    for u in all_users:
        first = u.full_name.split()[0].lower() if u.full_name else ""
        full  = u.full_name.lower() if u.full_name else ""
        if first in found_lower or full in found_lower:
            mentioned_ids.append(u.id)
    return mentioned_ids


# ---------- Endpoints ----------

@router.get("/task/{task_id}")
def list_comments(task_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    task = db.query(ProjectTask).filter(ProjectTask.id == task_id).first()
    if not task:
        raise HTTPException(404, "Task not found")
    if not _can_see_task(user, task):
        raise HTTPException(403, "You can only see comments on tasks assigned to you")

    rows = (
        db.query(Comment)
        .filter(Comment.project_task_id == task_id)
        .order_by(Comment.created_at.asc())
        .all()
    )
    return [_to_dict(c) for c in rows]


@router.post("/task/{task_id}")
def add_comment(task_id: int, payload: CommentIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    task = db.query(ProjectTask).filter(ProjectTask.id == task_id).first()
    if not task:
        raise HTTPException(404, "Task not found")
    if not _can_see_task(user, task):
        raise HTTPException(403, "You can only comment on tasks assigned to you")

    body = payload.body.strip()
    if not body:
        raise HTTPException(400, "Comment cannot be empty")
    if len(body) > 5000:
        raise HTTPException(400, "Comment too long (max 5000 chars)")

    c = Comment(
        project_task_id=task_id,
        author_id=user.id,
        body=body,
    )
    db.add(c)
    db.commit()
    db.refresh(c)

    # Build the link for notifications
    link = f"/projects/{task.project_id}"
    short = body[:60] + ("..." if len(body) > 60 else "")
    task_label = task.task_description[:40] if task.task_description else "a task"

    # Notify everyone involved in the task (except commenter themselves)
    recipients = {a.id for a in task.assignees} - {user.id}
    if recipients:
        notify_many(
            db, user_ids=list(recipients),
            title=f"💬 {user.full_name} commented on {task_label}",
            body=short,
            type="comment",
            link=link,
        )

    # Process @mentions — extra notification for tagged users
    all_users = db.query(User).all()
    mentioned_ids = _extract_mentions(body, all_users)
    mentioned_ids = [mid for mid in mentioned_ids if mid != user.id and mid not in recipients]
    if mentioned_ids:
        notify_many(
            db, user_ids=mentioned_ids,
            title=f"🏷️ {user.full_name} mentioned you in {task_label}",
            body=short,
            type="comment",
            link=link,
        )

    db.commit()
    return _to_dict(c)


@router.patch("/{comment_id}")
def edit_comment(comment_id: int, payload: CommentIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = db.query(Comment).filter(Comment.id == comment_id).first()
    if not c:
        raise HTTPException(404, "Comment not found")
    if c.author_id != user.id and user.role != "admin":
        raise HTTPException(403, "You can only edit your own comments")

    body = payload.body.strip()
    if not body:
        raise HTTPException(400, "Comment cannot be empty")
    c.body = body
    db.commit()
    db.refresh(c)
    return _to_dict(c)


@router.delete("/{comment_id}")
def delete_comment(comment_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = db.query(Comment).filter(Comment.id == comment_id).first()
    if not c:
        raise HTTPException(404, "Comment not found")
    if c.author_id != user.id and user.role != "admin":
        raise HTTPException(403, "You can only delete your own comments")
    db.delete(c)
    db.commit()
    return {"ok": True, "deleted_id": comment_id}


# Lightweight count endpoint for showing badge on tasks
@router.get("/count/{task_id}")
def comment_count(task_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    task = db.query(ProjectTask).filter(ProjectTask.id == task_id).first()
    if not task:
        return {"count": 0}
    if not _can_see_task(user, task):
        return {"count": 0}
    count = db.query(Comment).filter(Comment.project_task_id == task_id).count()
    return {"count": count}