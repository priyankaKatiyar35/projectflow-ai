"""
app/routes/auth.py
Login, logout, and the `current_user` dependency used by every protected route.
Uses Starlette's signed session middleware - no external auth lib needed.
"""
from datetime import datetime
from fastapi import APIRouter, Request, Depends, HTTPException, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
import bcrypt

from app.database import get_db
from app.models import User


router = APIRouter()


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Dependency: returns the logged-in User or raises 401/redirects."""
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    # Touch last-online
    user.last_online = datetime.utcnow()
    db.commit()
    return user


def current_user_or_redirect(request: Request, db: Session = Depends(get_db)):
    """Same as current_user but redirects to /login instead of raising 401."""
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.last_online = datetime.utcnow()
        db.commit()
    return user


@router.post("/login")
def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    from app.services.audit_service import log_audit
    from app.models.audit_log import CATEGORY_AUTH, CATEGORY_SECURITY

    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.password_hash):
        # Log failed login attempt — sensitive event
        log_audit(
            db, request=request, actor=None,
            action="login_failed",
            category=CATEGORY_SECURITY,
            entity_type="user",
            entity_label=email,
            summary=f"Failed login attempt for {email}",
            is_sensitive=True,
            commit=True,
        )
        return RedirectResponse(url="/login?error=Invalid+credentials", status_code=303)

    request.session["user_id"] = user.id
    request.session["role"] = user.role
    user.last_online = datetime.utcnow()

    # Log successful login
    log_audit(
        db, request=request, actor=user,
        action="login",
        category=CATEGORY_AUTH,
        entity_type="user",
        entity_id=user.id,
        entity_label=user.full_name,
        summary=f"{user.full_name} logged in",
    )

    db.commit()
    return RedirectResponse(url="/", status_code=303)


@router.get("/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    from app.services.audit_service import log_audit
    from app.models.audit_log import CATEGORY_AUTH

    user_id = request.session.get("user_id")
    if user_id:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            log_audit(
                db, request=request, actor=user,
                action="logout",
                category=CATEGORY_AUTH,
                entity_type="user",
                entity_id=user.id,
                entity_label=user.full_name,
                summary=f"{user.full_name} logged out",
                commit=True,
            )
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)