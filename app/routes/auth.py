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
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.password_hash):
        return RedirectResponse(url="/login?error=Invalid+credentials", status_code=303)
    request.session["user_id"] = user.id
    request.session["role"] = user.role
    user.last_online = datetime.utcnow()
    db.commit()
    return RedirectResponse(url="/", status_code=303)


@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)
