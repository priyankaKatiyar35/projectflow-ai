"""
app/routes/users.py
Admin-only API for managing users:
  GET    /api/users          - list all users
  GET    /api/users/{id}     - one user
  POST   /api/users          - create new user
  PATCH  /api/users/{id}     - edit user
  DELETE /api/users/{id}     - remove user
"""
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, EmailStr
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.routes.auth import current_user, hash_password


router = APIRouter(prefix="/api/users", tags=["users"])


# ---- Pydantic schemas (kept local to this file for simplicity) ----

class UserCreate(BaseModel):
    full_name: str
    email: EmailStr
    password: str
    role: str = "employee"   # admin | employee


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    password: Optional[str] = None   # only if changing
    role: Optional[str] = None


class UserOut(BaseModel):
    id: int
    full_name: str
    email: EmailStr
    role: str
    last_online: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


# ---- Helper: require admin ----

def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(403, "Admins only")
    return user


# ---- Routes ----

@router.get("", response_model=List[UserOut])
def list_users(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return db.query(User).order_by(User.created_at.desc()).all()


@router.get("/{user_id}", response_model=UserOut)
def get_user(user_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(404, "User not found")
    return u


@router.post("", response_model=UserOut)
def create_user(payload: UserCreate, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    # Duplicate email check
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(400, "A user with this email already exists")

    if payload.role not in ("admin", "employee"):
        raise HTTPException(400, "Role must be 'admin' or 'employee'")
    if len(payload.password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")

    u = User(
        full_name=payload.full_name,
        email=payload.email,
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@router.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: int, payload: UserUpdate, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(404, "User not found")

    data = payload.model_dump(exclude_unset=True)

    # Email uniqueness if changing
    if "email" in data and data["email"] != u.email:
        if db.query(User).filter(User.email == data["email"]).first():
            raise HTTPException(400, "Another user already has this email")

    # Role validation
    if "role" in data and data["role"] not in ("admin", "employee"):
        raise HTTPException(400, "Role must be 'admin' or 'employee'")

    # Password change -> hash it
    if "password" in data:
        if data["password"]:
            if len(data["password"]) < 6:
                raise HTTPException(400, "Password must be at least 6 characters")
            u.password_hash = hash_password(data["password"])
        del data["password"]

    # Don't let an admin demote themselves if they're the last admin
    if "role" in data and data["role"] == "employee" and u.id == admin.id:
        admin_count = db.query(User).filter(User.role == "admin").count()
        if admin_count <= 1:
            raise HTTPException(400, "Cannot demote yourself — you are the only admin")

    for key, value in data.items():
        setattr(u, key, value)

    db.commit()
    db.refresh(u)
    return u


@router.delete("/{user_id}")
def delete_user(user_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(404, "User not found")

    # Safety: cannot delete yourself
    if u.id == admin.id:
        raise HTTPException(400, "You cannot delete your own account")

    # Safety: never leave the system with zero admins
    if u.role == "admin":
        admin_count = db.query(User).filter(User.role == "admin").count()
        if admin_count <= 1:
            raise HTTPException(400, "Cannot delete the last admin")

    db.delete(u)
    db.commit()
    return {"ok": True, "deleted_id": user_id}
