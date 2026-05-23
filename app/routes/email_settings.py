"""
app/routes/email_settings.py

User-facing preference management for email notifications.

Endpoints:
  GET  /email-settings       -> HTML page
  GET  /api/email-settings   -> current preferences (JSON)
  POST /api/email-settings   -> save preferences
"""
from pydantic import BaseModel
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.routes.auth import current_user, current_user_or_redirect
from app.services.email_service import is_configured as email_configured


router = APIRouter()
templates = Jinja2Templates(directory="templates")


class EmailPrefs(BaseModel):
    email_enabled: bool = True
    email_for_assigned: bool = True
    email_for_edited: bool = True
    email_for_deadline: bool = True
    email_for_comment: bool = True
    email_for_role_change: bool = True
    email_for_password: bool = True


@router.get("/email-settings", response_class=HTMLResponse)
def email_settings_page(request: Request, db: Session = Depends(get_db)):
    user = current_user_or_redirect(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse(request, "email_settings.html", {
        "user": user,
        "smtp_configured": email_configured(),
    })


@router.get("/api/email-settings")
def get_prefs(user: User = Depends(current_user)):
    return {
        "email_enabled":         bool(user.email_enabled),
        "email_for_assigned":    bool(user.email_for_assigned),
        "email_for_edited":      bool(user.email_for_edited),
        "email_for_deadline":    bool(user.email_for_deadline),
        "email_for_comment":     bool(user.email_for_comment),
        "email_for_role_change": bool(user.email_for_role_change),
        "email_for_password":    bool(user.email_for_password),
        "smtp_configured":       email_configured(),
        "user_email":            user.email,
    }


@router.post("/api/email-settings")
def save_prefs(prefs: EmailPrefs, user: User = Depends(current_user), db: Session = Depends(get_db)):
    user.email_enabled         = int(prefs.email_enabled)
    user.email_for_assigned    = int(prefs.email_for_assigned)
    user.email_for_edited      = int(prefs.email_for_edited)
    user.email_for_deadline    = int(prefs.email_for_deadline)
    user.email_for_comment     = int(prefs.email_for_comment)
    user.email_for_role_change = int(prefs.email_for_role_change)
    user.email_for_password    = int(prefs.email_for_password)
    db.commit()
    return {"ok": True}


@router.post("/api/email-settings/test")
def send_test_email(user: User = Depends(current_user)):
    """Sends a test email to the user to verify SMTP works."""
    from app.services.email_service import send_email
    ok = send_email(
        to_email=user.email,
        to_name=user.full_name,
        subject="✅ Test email from Timesheet AI",
        body_html="<p>If you're reading this, email notifications are working perfectly! 🎉</p><p>You can now receive updates when tasks are assigned to you, deadlines approach, and more.</p>",
        link_url=None,
    )
    return {"ok": ok, "configured": email_configured()}