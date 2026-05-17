"""
app/routes/projects.py
Projects + ProjectTasks API.

Admin (PM):  full CRUD on projects and tasks
Employee:    can list projects assigned to them; can ONLY update
             actual_start_date, actual_end_date, actual_effort, status, remarks
"""
from typing import List, Optional
from datetime import date, datetime
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.database import get_db
from app.models import Project, ProjectTask, User
from app.routes.auth import current_user


router = APIRouter(prefix="/api/projects", tags=["projects"])


# ============ Pydantic schemas ============

class ProjectIn(BaseModel):
    name: str
    description: Optional[str] = None
    status: Optional[str] = "not_started"


class ProjectTaskIn(BaseModel):
    milestone_phase: Optional[str] = None
    category: Optional[str] = None
    task_description: str
    planned_start_date: Optional[date] = None
    planned_end_date: Optional[date] = None
    planned_effort: float = 0.0
    action_item: Optional[str] = None
    remarks: Optional[str] = None
    status: Optional[str] = "not_started"
    assignee_ids: List[int] = []


class ProjectTaskActualUpdate(BaseModel):
    """Fields an employee is allowed to change."""
    actual_start_date: Optional[date] = None
    actual_end_date: Optional[date] = None
    actual_effort: Optional[float] = None
    status: Optional[str] = None
    remarks: Optional[str] = None


def _user_dict(u: User) -> dict:
    return {"id": u.id, "full_name": u.full_name, "email": u.email}


def _task_dict(t: ProjectTask) -> dict:
    return {
        "id": t.id,
        "project_id": t.project_id,
        "milestone_phase": t.milestone_phase,
        "category": t.category,
        "task_description": t.task_description,
        "planned_start_date": t.planned_start_date.isoformat() if t.planned_start_date else None,
        "planned_end_date":   t.planned_end_date.isoformat()   if t.planned_end_date   else None,
        "actual_start_date":  t.actual_start_date.isoformat()  if t.actual_start_date  else None,
        "actual_end_date":    t.actual_end_date.isoformat()    if t.actual_end_date    else None,
        "planned_effort": t.planned_effort,
        "actual_effort":  t.actual_effort,
        "action_item": t.action_item,
        "remarks": t.remarks,
        "status": t.status,
        "assignees": [_user_dict(u) for u in t.assignees],
        "days_delayed": t.days_delayed,
        "effort_variance_pct": t.effort_variance_pct,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


def _project_dict(p: Project, include_tasks: bool = False) -> dict:
    d = {
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "status": p.status,
        "created_by": p.created_by,
        "creator_name": p.creator.full_name if p.creator else None,
        "task_count": len(p.tasks),
        "completed_count": sum(1 for t in p.tasks if t.status == "completed"),
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }
    if include_tasks:
        d["tasks"] = [_task_dict(t) for t in p.tasks]
    return d


# ============ Projects ============

@router.get("")
def list_projects(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Admin sees all projects. Employee sees only projects with tasks assigned to them."""
    if user.role == "admin":
        projects = db.query(Project).order_by(Project.created_at.desc()).all()
    else:
        # Projects where the employee has at least one assigned task
        projects = (
            db.query(Project)
            .join(ProjectTask, ProjectTask.project_id == Project.id)
            .join(ProjectTask.assignees)
            .filter(User.id == user.id)
            .distinct()
            .all()
        )
    return [_project_dict(p) for p in projects]


@router.post("")
def create_project(payload: ProjectIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.role != "admin":
        raise HTTPException(403, "Only admins can create projects")
    p = Project(name=payload.name, description=payload.description, status=payload.status or "not_started", created_by=user.id)
    db.add(p)
    db.commit()
    db.refresh(p)
    return _project_dict(p)


@router.get("/{project_id}")
def get_project(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(404, "Project not found")
    # Employee permission: only if at least one of their tasks is in this project
    if user.role != "admin":
        has_task = any(user.id in [a.id for a in t.assignees] for t in p.tasks)
        if not has_task:
            raise HTTPException(403, "Not assigned to this project")
        # Employees see only their own tasks within the project
        result = _project_dict(p, include_tasks=False)
        result["tasks"] = [
            _task_dict(t) for t in p.tasks if user.id in [a.id for a in t.assignees]
        ]
        return result
    return _project_dict(p, include_tasks=True)


@router.patch("/{project_id}")
def update_project(project_id: int, payload: ProjectIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.role != "admin":
        raise HTTPException(403, "Only admins can edit projects")
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(404, "Project not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(p, k, v)
    db.commit()
    db.refresh(p)
    return _project_dict(p)


@router.delete("/{project_id}")
def delete_project(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.role != "admin":
        raise HTTPException(403, "Only admins can delete projects")
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(404, "Project not found")
    db.delete(p)
    db.commit()
    return {"ok": True, "deleted_id": project_id}


# ============ Project Tasks ============

@router.post("/{project_id}/tasks")
def create_task(project_id: int, payload: ProjectTaskIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.role != "admin":
        raise HTTPException(403, "Only admins can create project tasks")
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(404, "Project not found")
    data = payload.model_dump(exclude={"assignee_ids"})
    t = ProjectTask(project_id=project_id, **data)
    if payload.assignee_ids:
        users = db.query(User).filter(User.id.in_(payload.assignee_ids)).all()
        t.assignees = users
    db.add(t)
    db.commit()
    db.refresh(t)
    return _task_dict(t)


@router.patch("/tasks/{task_id}")
def update_task(task_id: int, payload: dict, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """
    Admin: can update any field. Body matches ProjectTaskIn (plus assignee_ids).
    Employee: only allowed to set actual_start_date, actual_end_date, actual_effort, status, remarks.
    """
    t = db.query(ProjectTask).filter(ProjectTask.id == task_id).first()
    if not t:
        raise HTTPException(404, "Task not found")

    if user.role == "admin":
        # Allow all fields
        allowed = {"milestone_phase", "category", "task_description",
                   "planned_start_date", "planned_end_date", "planned_effort",
                   "actual_start_date", "actual_end_date", "actual_effort",
                   "action_item", "remarks", "status"}
        for k, v in payload.items():
            if k in allowed:
                if k.endswith("_date") and isinstance(v, str):
                    try: v = date.fromisoformat(v)
                    except: v = None
                setattr(t, k, v)
        if "assignee_ids" in payload:
            users = db.query(User).filter(User.id.in_(payload["assignee_ids"])).all()
            t.assignees = users
    else:
        # Employee: must be assigned to this task
        if user.id not in [a.id for a in t.assignees]:
            raise HTTPException(403, "Not assigned to this task")
        allowed = {"actual_start_date", "actual_end_date", "actual_effort", "status", "remarks"}
        for k, v in payload.items():
            if k in allowed:
                if k.endswith("_date") and isinstance(v, str):
                    try: v = date.fromisoformat(v)
                    except: v = None
                setattr(t, k, v)

    db.commit()
    db.refresh(t)
    return _task_dict(t)


@router.delete("/tasks/{task_id}")
def delete_task(task_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.role != "admin":
        raise HTTPException(403, "Only admins can delete tasks")
    t = db.query(ProjectTask).filter(ProjectTask.id == task_id).first()
    if not t:
        raise HTTPException(404, "Task not found")
    db.delete(t)
    db.commit()
    return {"ok": True, "deleted_id": task_id}
