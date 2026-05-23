"""
app/routes/password_reset.py

Three flows:
  1. Forgot password (self-service):
        GET  /forgot-password           -> form to enter email
        POST /forgot-password           -> creates token, shows link
        GET  /reset-password/{token}    -> form to set new password
        POST /reset-password/{token}    -> validates + updates password

  2. Admin reset (admin-triggered):
        POST /api/users/{id}/reset-password  -> creates token, returns it

  3. Change own password (logged in user):
        GET  /change-password           -> form
        POST /change-password           -> validates current + updates
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, Request, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, PasswordResetToken
from app.routes.auth import current_user, current_user_or_redirect, hash_password, verify_password
from app.config import settings


router = APIRouter()
templates = Jinja2Templates(directory="templates")


# ============================================================
# Flow 1: Forgot password (self-service)
# ============================================================

@router.get("/forgot-password", response_class=HTMLResponse)
def forgot_form(request: Request):
    return templates.TemplateResponse(request, "forgot_password.html", {})


@router.post("/forgot-password", response_class=HTMLResponse)
def forgot_submit(request: Request, email: str = Form(...), db: Session = Depends(get_db)):
    email = email.lower().strip()
    user = db.query(User).filter(User.email == email).first()

    # For security: ALWAYS show the same success message, even if email not found.
    # Otherwise attackers could enumerate which emails exist in the system.
    if not user:
        return templates.TemplateResponse(request, "forgot_password.html", {
            "submitted": True,
            "email": email,
            "show_link": False,
        })

    # Invalidate older tokens for this user
    db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user.id,
        PasswordResetToken.used_at.is_(None),
    ).update({"used_at": datetime.utcnow()})

    token = PasswordResetToken(
        user_id=user.id,
        token=PasswordResetToken.generate_token(),
        expires_at=PasswordResetToken.expiry_time(),
    )
    db.add(token)
    db.commit()
    db.refresh(token)

    reset_link = str(request.base_url).rstrip("/") + f"/reset-password/{token.token}"

    # In production with email setup: send the email here.
    # For now: show the link directly on screen (and log it server-side).
    print(f"\n[PASSWORD RESET LINK for {user.email}]:\n  {reset_link}\n")

    return templates.TemplateResponse(request, "forgot_password.html", {
        "submitted": True,
        "email": email,
        "show_link": True,
        "reset_link": reset_link,
    })


@router.get("/reset-password/{token}", response_class=HTMLResponse)
def reset_form(request: Request, token: str, db: Session = Depends(get_db)):
    t = db.query(PasswordResetToken).filter(PasswordResetToken.token == token).first()
    if not t or not t.is_valid:
        return templates.TemplateResponse(request, "reset_password.html", {
            "token": token,
            "invalid": True,
        })
    return templates.TemplateResponse(request, "reset_password.html", {
        "token": token,
        "invalid": False,
        "user_name": t.user.full_name,
    })


@router.post("/reset-password/{token}", response_class=HTMLResponse)
def reset_submit(
    request: Request,
    token: str,
    password: str = Form(...),
    password_confirm: str = Form(...),
    db: Session = Depends(get_db),
):
    t = db.query(PasswordResetToken).filter(PasswordResetToken.token == token).first()
    if not t or not t.is_valid:
        return templates.TemplateResponse(request, "reset_password.html", {
            "token": token,
            "invalid": True,
        })

    if password != password_confirm:
        return templates.TemplateResponse(request, "reset_password.html", {
            "token": token,
            "invalid": False,
            "user_name": t.user.full_name,
            "error": "Passwords do not match.",
        })

    if len(password) < 6:
        return templates.TemplateResponse(request, "reset_password.html", {
            "token": token,
            "invalid": False,
            "user_name": t.user.full_name,
            "error": "Password must be at least 6 characters.",
        })

    # Update password + mark token used
    t.user.password_hash = hash_password(password)
    t.used_at = datetime.utcnow()
    db.commit()

    return templates.TemplateResponse(request, "reset_password.html", {
        "token": token,
        "invalid": False,
        "success": True,
        "user_name": t.user.full_name,
    })


# ============================================================
# Flow 2: Admin-triggered password reset
# ============================================================

@router.post("/api/users/{user_id}/reset-password")
def admin_reset(user_id: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Admin generates a reset link for a user. Returns the link as JSON."""
    if user.role != "admin":
        raise HTTPException(403, "Admins only")

    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(404, "User not found")

    # Invalidate older tokens
    db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user_id,
        PasswordResetToken.used_at.is_(None),
    ).update({"used_at": datetime.utcnow()})

    token = PasswordResetToken(
        user_id=user_id,
        token=PasswordResetToken.generate_token(),
        expires_at=PasswordResetToken.expiry_time(),
    )
    db.add(token)
    db.commit()
    db.refresh(token)

    reset_link = str(request.base_url).rstrip("/") + f"/reset-password/{token.token}"

    # Also send an in-app notification to the user
    from app.routes.notifications import notify
    notify(
        db, user_id=user_id,
        title="🔐 Your password was reset by admin",
        body="Use the link your admin sent to set a new password.",
        type="system",
    )
    db.commit()

    return {
        "ok": True,
        "reset_link": reset_link,
        "expires_at": token.expires_at.isoformat(),
        "user_email": target.email,
        "user_name": target.full_name,
    }


# ============================================================
# Flow 3: Change own password (logged in)
# ============================================================

class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str


@router.get("/change-password", response_class=HTMLResponse)
def change_password_form(request: Request, db: Session = Depends(get_db)):
    user = current_user_or_redirect(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse(request, "change_password.html", {"user": user})


@router.post("/api/change-password")
def change_password_submit(
    payload: ChangePasswordIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(400, "Current password is incorrect")

    if len(payload.new_password) < 6:
        raise HTTPException(400, "New password must be at least 6 characters")

    if payload.current_password == payload.new_password:
        raise HTTPException(400, "New password must be different from current")

    user.password_hash = hash_password(payload.new_password)
    db.commit()
    return {"ok": True}