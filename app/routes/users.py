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
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.routes.auth import current_user, hash_password
from app.services.audit_service import log_audit, diff_dict, snapshot_user
from app.models.audit_log import CATEGORY_ADMIN, CATEGORY_SECURITY


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
def create_user(payload: UserCreate, request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
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

    log_audit(
        db, request=request, actor=admin,
        action="created",
        category=CATEGORY_ADMIN,
        entity_type="user",
        entity_id=u.id,
        entity_label=u.full_name,
        summary=f"Created user {u.full_name} ({u.email}) as {u.role}",
        details={"after": snapshot_user(u)},
        commit=True,
    )
    return u


@router.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: int, payload: UserUpdate, request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
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

    # Password change -> hash it (audit separately)
    password_changed = False
    if "password" in data:
        if data["password"]:
            if len(data["password"]) < 6:
                raise HTTPException(400, "Password must be at least 6 characters")
            u.password_hash = hash_password(data["password"])
            password_changed = True
        del data["password"]

    # Don't let an admin demote themselves if they're the last admin
    if "role" in data and data["role"] == "employee" and u.id == admin.id:
        admin_count = db.query(User).filter(User.role == "admin").count()
        if admin_count <= 1:
            raise HTTPException(400, "Cannot demote yourself — you are the only admin")

    # Snapshot before for diff
    before = snapshot_user(u)
    role_change = "role" in data and data["role"] != u.role

    for key, value in data.items():
        setattr(u, key, value)

    db.commit()
    db.refresh(u)

    after = snapshot_user(u)
    changes = diff_dict(before, after)

    if changes:
        log_audit(
            db, request=request, actor=admin,
            action="role_changed" if role_change else "updated",
            category=CATEGORY_SECURITY if role_change else CATEGORY_ADMIN,
            entity_type="user", entity_id=u.id, entity_label=u.full_name,
            summary=("Changed role of " if role_change else "Updated user ") + f"{u.full_name}",
            details={"before": before, "after": after, "fields_changed": list(changes.keys())},
        )
    if password_changed:
        log_audit(
            db, request=request, actor=admin,
            action="password_changed",
            category=CATEGORY_SECURITY,
            entity_type="user", entity_id=u.id, entity_label=u.full_name,
            summary=f"Admin changed password for {u.full_name}",
            is_sensitive=True,
        )
    db.commit()
    return u


@router.delete("/{user_id}")
def delete_user(user_id: int, request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
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

    snapshot = snapshot_user(u)
    label = u.full_name
    deleted_id = u.id

    db.delete(u)
    db.commit()

    log_audit(
        db, request=request, actor=admin,
        action="deleted",
        category=CATEGORY_ADMIN,
        entity_type="user", entity_id=deleted_id, entity_label=label,
        summary=f"Deleted user {label}",
        details={"before": snapshot},
        is_sensitive=True,
        commit=True,
    )

    return {"ok": True, "deleted_id": deleted_id}