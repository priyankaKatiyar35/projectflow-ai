"""
app/routes/pages.py
Renders the HTML pages: login, dashboard, tasks.
The dashboard collects all data via analytics + AI services and hands
it to Jinja for templating.
"""
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Project, ProjectTask, User
from app.routes.auth import current_user_or_redirect
from app.services import analytics, ai_service


router = APIRouter()
templates = Jinja2Templates(directory="templates")


def _project_stats(db: Session, user: User):
    """Compute project-level KPIs scoped to user role."""
    q_proj  = db.query(Project)
    q_tasks = db.query(ProjectTask)
    if user.role != "admin":
        q_tasks = q_tasks.join(ProjectTask.assignees).filter(User.id == user.id)
        q_proj  = q_proj.join(ProjectTask, ProjectTask.project_id == Project.id) \
                        .join(ProjectTask.assignees).filter(User.id == user.id).distinct()
    tasks = q_tasks.all()
    return {
        "project_count":   q_proj.distinct().count() if user.role == "admin" else len(set(t.project_id for t in tasks)),
        "task_count":      len(tasks),
        "task_completed":  sum(1 for t in tasks if t.status == "completed"),
        "task_in_progress":sum(1 for t in tasks if t.status == "in_progress"),
        "task_not_started":sum(1 for t in tasks if t.status == "not_started"),
        "task_delayed":    sum(1 for t in tasks if t.days_delayed > 0),
    }


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, error: str = ""):
    return templates.TemplateResponse(request, "login.html", {"error": error})


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    user = current_user_or_redirect(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    # New dashboard fetches all data via /api/ai/dashboard
    return templates.TemplateResponse(request, "dashboard.html", {
        "user": user,
        "is_admin": user.role == "admin",
    })


@router.get("/projects", response_class=HTMLResponse)
def projects_page(request: Request, db: Session = Depends(get_db)):
    user = current_user_or_redirect(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse(request, "projects.html", {"user": user})


@router.get("/projects/{project_id}", response_class=HTMLResponse)
def project_detail_page(project_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user_or_redirect(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse(request, "project_detail.html", {"user": user, "project_id": project_id})


@router.get("/reports", response_class=HTMLResponse)
def reports_page(request: Request, db: Session = Depends(get_db)):
    user = current_user_or_redirect(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse(request, "reports.html", {"user": user})


@router.get("/tasks", response_class=HTMLResponse)
def tasks_page(request: Request, db: Session = Depends(get_db)):
    user = current_user_or_redirect(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse(request, "tasks.html", {"user": user})


@router.get("/admin/users", response_class=HTMLResponse)
def admin_users_page(request: Request, db: Session = Depends(get_db)):
    """User management page — admin only."""
    user = current_user_or_redirect(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    if user.role != "admin":
        # Non-admins get bounced back to dashboard
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(request, "admin_users.html", {"user": user})


@router.get("/okrs", response_class=HTMLResponse)
def okrs_page(request: Request, db: Session = Depends(get_db)):
    """Goals & OKRs page — visible to all logged-in users."""
    user = current_user_or_redirect(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse(request, "okrs.html", {"user": user})