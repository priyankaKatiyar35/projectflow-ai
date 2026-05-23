"""
app/routes/audit.py
Audit log API and viewer page.

Endpoints:
  GET    /api/audit            -> filtered list (paginated)
  GET    /api/audit/{id}       -> single entry with full details
  GET    /api/audit/stats      -> aggregate counts for dashboard
  GET    /api/audit/export.csv -> CSV download
  GET    /audit                -> HTML viewer page (admin only)

All audit endpoints require admin role.
"""
import csv
import io
import json
from datetime import datetime, date, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc, and_, or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AuditLog, User
from app.routes.auth import current_user, current_user_or_redirect


router = APIRouter(tags=["audit"])
templates = Jinja2Templates(directory="templates")


def _require_admin(user: User):
    if user.role != "admin":
        raise HTTPException(403, "Admin only — audit log access is restricted")


def _entry_dict(e: AuditLog) -> dict:
    details = None
    if e.details_json:
        try:
            details = json.loads(e.details_json)
        except Exception:
            details = None
    return {
        "id": e.id,
        "created_at": e.created_at.isoformat() if e.created_at else None,
        "created_at_short": e.created_at.strftime("%Y-%m-%d %H:%M:%S") if e.created_at else "",
        "actor_id": e.actor_id,
        "actor_name": e.actor_name or "(system)",
        "actor_email": e.actor_email,
        "actor_role": e.actor_role,
        "ip_address": e.ip_address,
        "user_agent": (e.user_agent or "")[:80] + ("..." if e.user_agent and len(e.user_agent) > 80 else ""),
        "action": e.action,
        "category": e.category,
        "entity_type": e.entity_type,
        "entity_id": e.entity_id,
        "entity_label": e.entity_label,
        "summary": e.summary,
        "details": details,
        "is_sensitive": bool(e.is_sensitive),
    }


# ============================================================
# API: List with filters
# ============================================================

@router.get("/api/audit")
def list_audit(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    actor_id: Optional[int] = None,
    action: Optional[str] = None,
    category: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    sensitive_only: bool = False,
    q: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    _require_admin(user)

    qry = db.query(AuditLog)
    if actor_id:
        qry = qry.filter(AuditLog.actor_id == actor_id)
    if action:
        qry = qry.filter(AuditLog.action == action)
    if category:
        qry = qry.filter(AuditLog.category == category)
    if entity_type:
        qry = qry.filter(AuditLog.entity_type == entity_type)
    if entity_id:
        qry = qry.filter(AuditLog.entity_id == entity_id)
    if date_from:
        qry = qry.filter(AuditLog.created_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        qry = qry.filter(AuditLog.created_at <= datetime.combine(date_to, datetime.max.time()))
    if sensitive_only:
        qry = qry.filter(AuditLog.is_sensitive == 1)
    if q:
        pattern = f"%{q}%"
        qry = qry.filter(or_(
            AuditLog.summary.ilike(pattern),
            AuditLog.entity_label.ilike(pattern),
            AuditLog.actor_name.ilike(pattern),
        ))

    total = qry.count()
    rows = qry.order_by(desc(AuditLog.created_at)).offset(offset).limit(limit).all()

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "entries": [_entry_dict(e) for e in rows],
    }


# ============================================================
# CSV export — MUST come BEFORE /{audit_id} route or FastAPI matches "export.csv" as an ID
# ============================================================

@router.get("/api/audit/export.csv")
def export_csv(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    entity_type: Optional[str] = None,
    actor_id: Optional[int] = None,
    sensitive_only: bool = False,
):
    _require_admin(user)
    qry = db.query(AuditLog)
    if date_from:
        qry = qry.filter(AuditLog.created_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        qry = qry.filter(AuditLog.created_at <= datetime.combine(date_to, datetime.max.time()))
    if entity_type:
        qry = qry.filter(AuditLog.entity_type == entity_type)
    if actor_id:
        qry = qry.filter(AuditLog.actor_id == actor_id)
    if sensitive_only:
        qry = qry.filter(AuditLog.is_sensitive == 1)

    rows = qry.order_by(desc(AuditLog.created_at)).limit(10000).all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "Timestamp (UTC)", "Actor", "Email", "Role", "Action", "Category",
        "Entity Type", "Entity ID", "Entity Label", "Summary", "IP", "Sensitive",
    ])
    for e in rows:
        writer.writerow([
            e.created_at.strftime("%Y-%m-%d %H:%M:%S") if e.created_at else "",
            e.actor_name or "",
            e.actor_email or "",
            e.actor_role or "",
            e.action,
            e.category,
            e.entity_type or "",
            e.entity_id or "",
            e.entity_label or "",
            e.summary or "",
            e.ip_address or "",
            "YES" if e.is_sensitive else "no",
        ])

    buf.seek(0)
    label = "audit_log"
    if date_from and date_to:
        label += f"_{date_from.isoformat()}_to_{date_to.isoformat()}"

    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{label}.csv"'},
    )


@router.get("/api/audit/stats")
def audit_stats(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    days: int = Query(30, ge=1, le=365),
):
    _require_admin(user)
    cutoff = datetime.utcnow() - timedelta(days=days)
    qry = db.query(AuditLog).filter(AuditLog.created_at >= cutoff)

    total = qry.count()
    sensitive = qry.filter(AuditLog.is_sensitive == 1).count()

    by_category = {}
    by_action = {}
    by_actor = {}
    for e in qry.all():
        by_category[e.category] = by_category.get(e.category, 0) + 1
        by_action[e.action] = by_action.get(e.action, 0) + 1
        if e.actor_name:
            by_actor[e.actor_name] = by_actor.get(e.actor_name, 0) + 1

    top_actors = sorted(by_actor.items(), key=lambda x: -x[1])[:5]

    return {
        "window_days": days,
        "total_events": total,
        "sensitive_events": sensitive,
        "by_category": by_category,
        "by_action": by_action,
        "top_actors": [{"name": n, "count": c} for n, c in top_actors],
    }


@router.get("/api/audit/{audit_id}")
def get_one(audit_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _require_admin(user)
    e = db.query(AuditLog).filter(AuditLog.id == audit_id).first()
    if not e:
        raise HTTPException(404, "Audit entry not found")
    return _entry_dict(e)


# ============================================================
# HTML page (admin viewer)
# ============================================================

@router.get("/audit", response_class=HTMLResponse)
def audit_page(request: Request, db: Session = Depends(get_db)):
    user = current_user_or_redirect(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    if user.role != "admin":
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(request, "audit.html", {"user": user})