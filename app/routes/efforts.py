"""
app/routes/efforts.py
JSON API for time-logging.
"""
from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Effort, Task, User
from app.schemas.schemas import EffortCreate
from app.routes.auth import current_user


router = APIRouter(prefix="/api/efforts", tags=["efforts"])


@router.post("")
def log_effort(payload: EffortCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == payload.task_id).first()
    if not task:
        raise HTTPException(404, "Task not found")
    if user.role != "admin" and task.assignee_id != user.id:
        raise HTTPException(403, "Not your task")
    effort = Effort(
        task_id=payload.task_id,
        user_id=user.id,
        minutes=payload.minutes,
        log_date=payload.log_date or date.today(),
        notes=payload.notes,
    )
    db.add(effort)
    db.commit()
    db.refresh(effort)
    return {"id": effort.id, "minutes": effort.minutes}


@router.get("/by-task/{task_id}")
def efforts_for_task(task_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.query(Effort).filter(Effort.task_id == task_id).all()
    return [{"id": r.id, "minutes": r.minutes, "log_date": str(r.log_date), "notes": r.notes} for r in rows]
