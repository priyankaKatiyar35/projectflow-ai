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

    is_admin = user.role == "admin"
    uid = None if is_admin else user.id

    stats = analytics.dashboard_stats(db, uid)
    trend = analytics.productivity_trend(db, uid, 14)
    cat   = analytics.effort_by_category(db, uid)
    sub   = analytics.effort_by_subtask(db, uid)
    online = analytics.online_presence(db) if is_admin else {}
    emp_prog   = analytics.employee_progress(db) if is_admin else {}
    emp_act    = analytics.employee_activity(db) if is_admin else {}

    # AI insights inline (cheap rule-based ones - won't block on API)
    ai_insights = []
    if is_admin:
        ai_insights += ai_service.detect_workload_issues(emp_act)
    # Status sanity insight (works for both roles)
    if stats["overdue"] > 0:
        ai_insights.append({
            "type": "danger",
            "title": "Overdue tasks need attention",
            "body": f"{stats['overdue']} task(s) are past their deadline."
        })
    if stats["completed"] > 0 and (stats["pending"] + stats["in_progress"] + stats["completed"]) > 0:
        total = stats["pending"] + stats["in_progress"] + stats["completed"]
        rate = round((stats["completed"] / total) * 100)
        if rate >= 60:
            ai_insights.append({
                "type": "success",
                "title": "Healthy completion rate",
                "body": f"{rate}% of tasks are complete — strong momentum."
            })

    return templates.TemplateResponse(request, "dashboard.html", {
        "user": user,
        "is_admin": is_admin,
        "stats": stats,
        "project_stats": _project_stats(db, user),
        "trend": trend,
        "effort_by_category": cat,
        "effort_by_subtask": sub,
        "online_presence": online,
        "employee_progress": emp_prog,
        "employee_activity": emp_act,
        "ai_insights": ai_insights,
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
