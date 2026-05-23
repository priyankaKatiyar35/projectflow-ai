"""
app/routes/okrs.py
OKRs (Objectives & Key Results) API.

Endpoints:
  GET    /api/objectives                       -> list (filter by period, owner, status)
  POST   /api/objectives                       -> create
  GET    /api/objectives/{id}                  -> single + nested KRs
  PATCH  /api/objectives/{id}                  -> edit
  DELETE /api/objectives/{id}                  -> delete

  POST   /api/objectives/{id}/key-results      -> add KR
  PATCH  /api/key-results/{id}                 -> edit KR (incl. update current_value)
  DELETE /api/key-results/{id}                 -> delete KR

  POST   /api/key-results/{id}/checkin         -> weekly check-in
  GET    /api/key-results/{id}/checkins        -> list check-ins

  GET    /api/okrs/summary                     -> dashboard stats by period
  GET    /api/okrs/periods                     -> list of periods that exist
  GET    /api/okrs/export.csv                  -> CSV export

Permissions:
  - List/view: anyone (company objectives) or owner+admin (private)
  - Create/Edit/Delete: admin OR objective owner
  - Check-in on KR: KR owner, objective owner, or admin
  - Update current_value: same as check-in (usually paired)
"""
import csv
import io
from datetime import date, datetime
from typing import List, Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc, func

from app.database import get_db
from app.models import Objective, KeyResult, KRCheckin, User, Notification
from app.routes.auth import current_user
from app.routes.notifications import notify, notify_many


router = APIRouter(prefix="/api", tags=["okrs"])


# ============================================================
# Pydantic models
# ============================================================

class KeyResultIn(BaseModel):
    title: str
    kr_type: str = "numeric"  # numeric | percent | boolean | milestone
    unit: Optional[str] = None
    start_value: float = 0.0
    target_value: float
    current_value: float = 0.0
    owner_id: Optional[int] = None
    sort_order: int = 0


class ObjectiveIn(BaseModel):
    title: str
    description: Optional[str] = None
    category: Optional[str] = None
    period_label: str
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    owner_id: int
    visibility: str = "company"
    status_override: Optional[str] = None
    key_results: List[KeyResultIn] = []


class ObjectivePatch(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    period_label: Optional[str] = None
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    owner_id: Optional[int] = None
    visibility: Optional[str] = None
    status_override: Optional[str] = None


class KRPatch(BaseModel):
    title: Optional[str] = None
    kr_type: Optional[str] = None
    unit: Optional[str] = None
    start_value: Optional[float] = None
    target_value: Optional[float] = None
    current_value: Optional[float] = None
    owner_id: Optional[int] = None
    sort_order: Optional[int] = None


class CheckinIn(BaseModel):
    value_at_checkin: float
    confidence: Optional[str] = None  # high | medium | low
    note: Optional[str] = None


# ============================================================
# Permission helpers
# ============================================================

def _can_view(obj: Objective, user: User) -> bool:
    if user.role == "admin":
        return True
    if obj.visibility == "company":
        return True
    return obj.owner_id == user.id


def _can_edit(obj: Objective, user: User) -> bool:
    return user.role == "admin" or obj.owner_id == user.id


def _can_checkin(kr: KeyResult, user: User) -> bool:
    if user.role == "admin":
        return True
    if kr.objective and kr.objective.owner_id == user.id:
        return True
    if kr.owner_id == user.id:
        return True
    return False


def _obj_dict(obj: Objective) -> dict:
    return {
        "id": obj.id,
        "title": obj.title,
        "description": obj.description,
        "category": obj.category,
        "period_label": obj.period_label,
        "period_start": obj.period_start.isoformat() if obj.period_start else None,
        "period_end": obj.period_end.isoformat() if obj.period_end else None,
        "owner_id": obj.owner_id,
        "owner_name": obj.owner.full_name if obj.owner else "(unknown)",
        "visibility": obj.visibility,
        "status": obj.computed_status,
        "status_override": obj.status_override,
        "progress_pct": obj.progress_pct,
        "kr_count": len(obj.key_results),
        "key_results": [_kr_dict(kr) for kr in obj.key_results],
        "created_at": obj.created_at.isoformat() if obj.created_at else None,
        "updated_at": obj.updated_at.isoformat() if obj.updated_at else None,
    }


def _kr_dict(kr: KeyResult) -> dict:
    return {
        "id": kr.id,
        "objective_id": kr.objective_id,
        "title": kr.title,
        "kr_type": kr.kr_type,
        "unit": kr.unit,
        "start_value": kr.start_value,
        "target_value": kr.target_value,
        "current_value": kr.current_value,
        "progress_pct": kr.progress_pct,
        "owner_id": kr.owner_id,
        "owner_name": kr.owner.full_name if kr.owner else None,
        "sort_order": kr.sort_order,
        "checkin_count": len(kr.checkins) if kr.checkins else 0,
    }


def _checkin_dict(ch: KRCheckin) -> dict:
    return {
        "id": ch.id,
        "key_result_id": ch.key_result_id,
        "author_id": ch.author_id,
        "author_name": ch.author.full_name if ch.author else "(unknown)",
        "value_at_checkin": ch.value_at_checkin,
        "confidence": ch.confidence,
        "note": ch.note,
        "created_at": ch.created_at.isoformat() if ch.created_at else None,
    }


# ============================================================
# Objectives CRUD
# ============================================================

@router.get("/objectives")
def list_objectives(
    period: Optional[str] = None,
    owner_id: Optional[int] = None,
    status: Optional[str] = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    q = db.query(Objective)
    if period:
        q = q.filter(Objective.period_label == period)
    if owner_id:
        q = q.filter(Objective.owner_id == owner_id)

    rows = q.order_by(desc(Objective.created_at)).all()
    # Visibility filter (employees can't see others' private OKRs)
    visible = [o for o in rows if _can_view(o, user)]
    out = [_obj_dict(o) for o in visible]
    if status:
        out = [o for o in out if o["status"] == status]
    return out


@router.post("/objectives")
def create_objective(payload: ObjectiveIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.role != "admin" and payload.owner_id != user.id:
        raise HTTPException(403, "You can only create objectives for yourself (unless admin)")

    # Validate owner exists
    owner = db.query(User).filter(User.id == payload.owner_id).first()
    if not owner:
        raise HTTPException(400, "Invalid owner_id")

    obj = Objective(
        title=payload.title,
        description=payload.description,
        category=payload.category,
        period_label=payload.period_label,
        period_start=payload.period_start,
        period_end=payload.period_end,
        owner_id=payload.owner_id,
        visibility=payload.visibility,
        status_override=payload.status_override,
    )
    db.add(obj)
    db.flush()

    for kr in payload.key_results:
        if kr.target_value is None:
            continue
        db.add(KeyResult(
            objective_id=obj.id,
            title=kr.title,
            kr_type=kr.kr_type,
            unit=kr.unit,
            start_value=kr.start_value,
            target_value=kr.target_value,
            current_value=kr.current_value,
            owner_id=kr.owner_id,
            sort_order=kr.sort_order,
        ))

    # Notify owner if not the creator
    if owner.id != user.id:
        notify(db, user_id=owner.id,
               title=f"🎯 You're the owner of a new objective",
               body=f'"{obj.title[:80]}" ({obj.period_label})',
               type="assigned",
               link="/okrs")

    db.commit()
    db.refresh(obj)
    return _obj_dict(obj)


@router.get("/objectives/{obj_id}")
def get_objective(obj_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    obj = db.query(Objective).filter(Objective.id == obj_id).first()
    if not obj:
        raise HTTPException(404, "Objective not found")
    if not _can_view(obj, user):
        raise HTTPException(403, "Not visible to you")
    return _obj_dict(obj)


@router.patch("/objectives/{obj_id}")
def update_objective(obj_id: int, payload: ObjectivePatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    obj = db.query(Objective).filter(Objective.id == obj_id).first()
    if not obj:
        raise HTTPException(404, "Objective not found")
    if not _can_edit(obj, user):
        raise HTTPException(403, "Only the owner or admin can edit")

    old_owner = obj.owner_id
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(obj, k, v)

    db.commit()
    db.refresh(obj)

    # Notify new owner if owner changed
    if "owner_id" in data and data["owner_id"] != old_owner and data["owner_id"] != user.id:
        notify(db, user_id=data["owner_id"],
               title="🎯 You're now the owner of an objective",
               body=f'"{obj.title[:80]}"',
               type="role_change",
               link="/okrs")
        db.commit()

    return _obj_dict(obj)


@router.delete("/objectives/{obj_id}")
def delete_objective(obj_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    obj = db.query(Objective).filter(Objective.id == obj_id).first()
    if not obj:
        raise HTTPException(404, "Objective not found")
    if not _can_edit(obj, user):
        raise HTTPException(403, "Only the owner or admin can delete")
    db.delete(obj)
    db.commit()
    return {"ok": True}


# ============================================================
# Key Results
# ============================================================

@router.post("/objectives/{obj_id}/key-results")
def add_key_result(obj_id: int, payload: KeyResultIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    obj = db.query(Objective).filter(Objective.id == obj_id).first()
    if not obj:
        raise HTTPException(404, "Objective not found")
    if not _can_edit(obj, user):
        raise HTTPException(403, "Only the owner or admin can add KRs")

    kr = KeyResult(
        objective_id=obj_id,
        title=payload.title,
        kr_type=payload.kr_type,
        unit=payload.unit,
        start_value=payload.start_value,
        target_value=payload.target_value,
        current_value=payload.current_value,
        owner_id=payload.owner_id,
        sort_order=payload.sort_order,
    )
    db.add(kr)
    db.commit()
    db.refresh(kr)

    # Notify KR owner if set and different
    if kr.owner_id and kr.owner_id != user.id:
        notify(db, user_id=kr.owner_id,
               title="📊 You own a new key result",
               body=f'"{kr.title[:80]}" on objective "{obj.title[:50]}"',
               type="assigned",
               link="/okrs")
        db.commit()

    return _kr_dict(kr)


@router.patch("/key-results/{kr_id}")
def update_key_result(kr_id: int, payload: KRPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    kr = db.query(KeyResult).filter(KeyResult.id == kr_id).first()
    if not kr:
        raise HTTPException(404, "Key result not found")

    # Just updating current_value? Anyone who can check-in.
    data = payload.model_dump(exclude_unset=True)
    only_current = set(data.keys()) <= {"current_value"}
    if only_current:
        if not _can_checkin(kr, user):
            raise HTTPException(403, "Cannot update this KR")
    else:
        if not _can_edit(kr.objective, user):
            raise HTTPException(403, "Only the owner or admin can edit KR structure")

    for k, v in data.items():
        setattr(kr, k, v)
    db.commit()
    db.refresh(kr)
    return _kr_dict(kr)


@router.delete("/key-results/{kr_id}")
def delete_key_result(kr_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    kr = db.query(KeyResult).filter(KeyResult.id == kr_id).first()
    if not kr:
        raise HTTPException(404, "Key result not found")
    if not _can_edit(kr.objective, user):
        raise HTTPException(403, "Only the objective owner or admin can delete KRs")
    db.delete(kr)
    db.commit()
    return {"ok": True}


# ============================================================
# Check-ins
# ============================================================

@router.post("/key-results/{kr_id}/checkin")
def add_checkin(kr_id: int, payload: CheckinIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    kr = db.query(KeyResult).filter(KeyResult.id == kr_id).first()
    if not kr:
        raise HTTPException(404, "Key result not found")
    if not _can_checkin(kr, user):
        raise HTTPException(403, "You cannot check in on this KR")

    ch = KRCheckin(
        key_result_id=kr_id,
        author_id=user.id,
        value_at_checkin=payload.value_at_checkin,
        confidence=payload.confidence,
        note=payload.note,
    )
    db.add(ch)
    # Also update KR current value
    kr.current_value = payload.value_at_checkin
    db.commit()
    db.refresh(ch)

    # Notify objective owner if not the checker
    if kr.objective and kr.objective.owner_id != user.id:
        notify(db, user_id=kr.objective.owner_id,
               title=f"📈 KR check-in on {kr.title[:50]}",
               body=f'Value: {payload.value_at_checkin}{kr.unit or ""} ({kr.progress_pct}%)',
               type="comment",
               link="/okrs")
        db.commit()

    return _checkin_dict(ch)


@router.get("/key-results/{kr_id}/checkins")
def list_checkins(kr_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    kr = db.query(KeyResult).filter(KeyResult.id == kr_id).first()
    if not kr:
        raise HTTPException(404, "Key result not found")
    if not _can_view(kr.objective, user):
        raise HTTPException(403, "Not visible to you")
    return [_checkin_dict(c) for c in kr.checkins]


# ============================================================
# Dashboard / summary endpoints
# ============================================================

@router.get("/okrs/summary")
def summary(period: Optional[str] = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Aggregate stats for OKRs dashboard."""
    q = db.query(Objective)
    if period:
        q = q.filter(Objective.period_label == period)
    objs = [o for o in q.all() if _can_view(o, user)]

    by_status = {"on_track": 0, "at_risk": 0, "off_track": 0, "done": 0, "paused": 0}
    total_progress = 0.0
    for o in objs:
        st = o.computed_status
        by_status[st] = by_status.get(st, 0) + 1
        total_progress += o.progress_pct

    avg_progress = round(total_progress / len(objs), 1) if objs else 0.0

    by_category = {}
    for o in objs:
        cat = o.category or "Uncategorized"
        if cat not in by_category:
            by_category[cat] = {"count": 0, "avg_progress": 0.0, "total": 0.0}
        by_category[cat]["count"] += 1
        by_category[cat]["total"] += o.progress_pct
    for cat in by_category.values():
        cat["avg_progress"] = round(cat["total"] / cat["count"], 1)
        del cat["total"]

    return {
        "period": period,
        "total_objectives": len(objs),
        "avg_progress_pct": avg_progress,
        "by_status": by_status,
        "by_category": by_category,
    }


@router.get("/okrs/periods")
def list_periods(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """List all period labels that have any objective."""
    rows = db.query(Objective.period_label).distinct().all()
    periods = sorted({r[0] for r in rows}, reverse=True)
    return {"periods": periods}


@router.get("/okrs/export.csv")
def export_csv(period: Optional[str] = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Export OKRs as CSV - one row per key result."""
    q = db.query(Objective)
    if period:
        q = q.filter(Objective.period_label == period)
    objs = [o for o in q.order_by(desc(Objective.period_label)).all() if _can_view(o, user)]

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "Period", "Objective", "Category", "Objective Owner", "Status", "Objective Progress %",
        "Key Result", "KR Owner", "Type", "Start", "Current", "Target", "Unit", "KR Progress %",
    ])
    for o in objs:
        if not o.key_results:
            writer.writerow([
                o.period_label, o.title, o.category or "", o.owner.full_name if o.owner else "",
                o.computed_status, o.progress_pct,
                "(no key results)", "", "", "", "", "", "", "",
            ])
        for kr in o.key_results:
            writer.writerow([
                o.period_label, o.title, o.category or "", o.owner.full_name if o.owner else "",
                o.computed_status, o.progress_pct,
                kr.title, kr.owner.full_name if kr.owner else "",
                kr.kr_type, kr.start_value, kr.current_value, kr.target_value,
                kr.unit or "", kr.progress_pct,
            ])

    buf.seek(0)
    label = period or "all"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="okrs_{label}.csv"'},
    )