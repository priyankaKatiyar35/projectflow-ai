"""
app/routes/ai.py
HTTP endpoints for every AI feature. The frontend hits these via fetch().
"""
from datetime import datetime, date, timedelta
from collections import defaultdict
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models import User, Task, Effort
from app.schemas.schemas import AIChatIn, AIChatOut, NLTaskIn, NLTaskOut
from app.routes.auth import current_user
from app.services import analytics
from app.services import ai_service


router = APIRouter(prefix="/api/ai", tags=["ai"])


# ----- 1) AI chat with your data -----
@router.post("/chat", response_model=AIChatOut)
def chat(payload: AIChatIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    is_admin = user.role == "admin"
    scope_uid = None if is_admin else user.id
    context = {
        "viewer_role": user.role,
        "stats": analytics.dashboard_stats(db, scope_uid),
        "employee_activity": analytics.employee_activity(db) if is_admin else None,
        "employee_progress": analytics.employee_progress(db) if is_admin else None,
        "effort_by_category": analytics.effort_by_category(db, scope_uid),
    }
    # Recent tasks (slim view)
    tasks = (
        db.query(Task)
        .filter((Task.assignee_id == user.id) if not is_admin else True)
        .order_by(Task.updated_at.desc())
        .limit(20)
        .all()
    )
    context["recent_tasks"] = [
        {
            "task": t.task, "sub_task": t.sub_task, "status": t.status,
            "priority": t.priority, "assignee_id": t.assignee_id,
            "deadline": str(t.deadline) if t.deadline else None,
        }
        for t in tasks
    ]
    reply = ai_service.chat_with_data(payload.message, context)
    return AIChatOut(reply=reply, sources=[])


# ----- 2) Auto reports / standups -----
@router.post("/report/{scope}")
def report(scope: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if scope not in {"daily_standup", "weekly_summary", "employee_review"}:
        raise HTTPException(400, "Unknown scope")

    is_admin = user.role == "admin"
    uid = None if is_admin else user.id
    data = {
        "date": str(date.today()),
        "stats": analytics.dashboard_stats(db, uid),
        "trend": analytics.productivity_trend(db, uid, 7),
    }
    if is_admin:
        data["employee_activity"] = analytics.employee_activity(db)

    text = ai_service.generate_report(scope, data)
    return {"report": text, "generated_at": datetime.utcnow().isoformat()}


# ----- 3) Natural language task entry -----
@router.post("/parse-task", response_model=NLTaskOut)
def parse_task(payload: NLTaskIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    users = [{"id": u.id, "full_name": u.full_name} for u in db.query(User).all()]
    parsed = ai_service.parse_natural_task(payload.text, users)
    return NLTaskOut(**parsed)


# ----- 4) Workload balancer -----
@router.get("/workload")
def workload(user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.role != "admin":
        raise HTTPException(403, "Admins only")
    activity = analytics.employee_activity(db)
    insights = ai_service.detect_workload_issues(activity)
    return {"insights": insights, "activity": activity}


# ----- 5) Burnout detector -----
@router.get("/burnout")
def burnout(user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.role != "admin":
        raise HTTPException(403, "Admins only")
    # Build daily hours for last 7 days per user
    cutoff = date.today() - timedelta(days=7)
    rows = (
        db.query(User.full_name, Effort.log_date, func.sum(Effort.minutes))
        .join(Effort, Effort.user_id == User.id)
        .filter(Effort.log_date >= cutoff)
        .group_by(User.full_name, Effort.log_date)
        .all()
    )
    by_user: dict[str, list[float]] = defaultdict(list)
    for name, _d, mins in rows:
        by_user[name].append((mins or 0) / 60.0)
    insights = ai_service.detect_burnout(by_user)
    return {"insights": insights}


# ----- 6) Deadline risk -----
@router.get("/deadline-risk/{task_id}")
def deadline_risk(task_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(404, "Task not found")
    if user.role != "admin" and task.assignee_id != user.id:
        raise HTTPException(403, "Not your task")
    total_min = (
        db.query(func.coalesce(func.sum(Effort.minutes), 0))
        .filter(Effort.task_id == task_id)
        .scalar()
    )
    task_dict = {
        "deadline": task.deadline,
        "status": task.status,
        "estimated_hours": task.estimated_hours,
    }
    return ai_service.predict_deadline_risk(task_dict, total_min)


# ----- 7) Effort forecast -----
@router.post("/forecast-effort")
def forecast_effort(payload: AIChatIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    # Build history from completed tasks with effort
    rows = (
        db.query(Task.sub_task, func.sum(Effort.minutes))
        .join(Effort, Effort.task_id == Task.id)
        .group_by(Task.id)
        .limit(50)
        .all()
    )
    history = [{"sub_task": s, "hours_logged": (m or 0) / 60.0} for s, m in rows]
    result = ai_service.forecast_effort(payload.message, history)
    return result
