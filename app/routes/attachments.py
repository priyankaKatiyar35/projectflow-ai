"""
app/routes/attachments.py
File attachments on project tasks.

Endpoints:
  GET    /api/tasks/{task_id}/attachments         -> list
  POST   /api/tasks/{task_id}/attachments         -> upload (multipart/form-data)
  GET    /api/attachments/{att_id}/download       -> download file
  GET    /api/attachments/{att_id}/preview        -> inline view (images)
  DELETE /api/attachments/{att_id}                -> remove (uploader or admin)

Permissions:
  - Upload: admin OR task assignee
  - Download/preview: admin OR task assignee
  - Delete: admin OR original uploader
"""
import os
import uuid
import mimetypes
from pathlib import Path
from datetime import datetime
from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Request
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Attachment, ProjectTask, User
from app.routes.auth import current_user
from app.routes.notifications import notify_many


router = APIRouter(prefix="/api", tags=["attachments"])

# Storage configuration
UPLOAD_DIR = Path("data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

# Forbidden extensions (security)
BLOCKED_EXTENSIONS = {".exe", ".bat", ".cmd", ".sh", ".com", ".scr", ".dll", ".msi"}


# ============================================================
# Helpers
# ============================================================

def _can_access_task(task: ProjectTask, user: User) -> bool:
    """Admin always; assignees only otherwise."""
    if user.role == "admin":
        return True
    return user.id in [a.id for a in task.assignees]


def _att_dict(a: Attachment) -> dict:
    return {
        "id": a.id,
        "project_task_id": a.project_task_id,
        "uploader_id": a.uploader_id,
        "uploader_name": a.uploader.full_name if a.uploader else "(unknown)",
        "original_name": a.original_name,
        "mime_type": a.mime_type,
        "size_bytes": a.size_bytes,
        "size_human": a.size_human,
        "is_image": a.is_image,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "download_url": f"/api/attachments/{a.id}/download",
        "preview_url": f"/api/attachments/{a.id}/preview" if a.is_image else None,
    }


# ============================================================
# List
# ============================================================

@router.get("/tasks/{task_id}/attachments")
def list_attachments(task_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    task = db.query(ProjectTask).filter(ProjectTask.id == task_id).first()
    if not task:
        raise HTTPException(404, "Task not found")
    if not _can_access_task(task, user):
        raise HTTPException(403, "Not authorized")

    atts = sorted(task.attachments, key=lambda a: -a.id)
    return [_att_dict(a) for a in atts]


# ============================================================
# Upload
# ============================================================

@router.post("/tasks/{task_id}/attachments")
async def upload_attachment(
    task_id: int,
    request: Request,
    file: UploadFile = File(...),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    task = db.query(ProjectTask).filter(ProjectTask.id == task_id).first()
    if not task:
        raise HTTPException(404, "Task not found")
    if not _can_access_task(task, user):
        raise HTTPException(403, "Not authorized to upload to this task")

    # Security: filename and extension check
    if not file.filename:
        raise HTTPException(400, "No file name provided")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext in BLOCKED_EXTENSIONS:
        raise HTTPException(400, f"File type {ext} is not allowed for security reasons")

    # Read in chunks to avoid memory issues
    contents = await file.read()
    size = len(contents)

    if size == 0:
        raise HTTPException(400, "File is empty")
    if size > MAX_FILE_SIZE:
        raise HTTPException(400, f"File too large (max {MAX_FILE_SIZE // (1024*1024)} MB)")

    # Generate UUID-based stored name (preserves extension)
    stored_name = f"{uuid.uuid4().hex}{ext}"
    file_path = UPLOAD_DIR / stored_name

    # Write to disk
    with open(file_path, "wb") as f:
        f.write(contents)

    # Detect mime
    mime_type = file.content_type or mimetypes.guess_type(file.filename)[0] or "application/octet-stream"

    # Save metadata
    att = Attachment(
        project_task_id=task_id,
        uploader_id=user.id,
        original_name=file.filename,
        stored_name=stored_name,
        mime_type=mime_type,
        size_bytes=size,
    )
    db.add(att)
    db.commit()
    db.refresh(att)

    # Audit log
    try:
        from app.services.audit_service import log_audit
        log_audit(
            db, request=request, actor=user,
            action="created",
            entity_type="attachment", entity_id=att.id, entity_label=file.filename,
            summary=f"Uploaded '{file.filename}' ({att.size_human}) to task '{(task.task_description or '')[:40]}'",
            details={"task_id": task_id, "size_bytes": size, "mime_type": mime_type},
            commit=True,
        )
    except Exception:
        pass

    # Notify other assignees that a file was added
    try:
        other_assignees = [a.id for a in task.assignees if a.id != user.id]
        if other_assignees:
            notify_many(
                db, user_ids=other_assignees,
                title=f"📎 New attachment: {file.filename[:60]}",
                body=f"{user.full_name} uploaded a file to '{(task.task_description or '')[:60]}'",
                type="comment",
                link=f"/projects/{task.project_id}",
            )
            db.commit()
    except Exception:
        pass

    return _att_dict(att)


# ============================================================
# Download
# ============================================================

@router.get("/attachments/{att_id}/download")
def download_attachment(att_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    att = db.query(Attachment).filter(Attachment.id == att_id).first()
    if not att:
        raise HTTPException(404, "Attachment not found")
    if not _can_access_task(att.project_task, user):
        raise HTTPException(403, "Not authorized")

    file_path = UPLOAD_DIR / att.stored_name
    if not file_path.exists():
        raise HTTPException(410, "File missing from storage")

    return FileResponse(
        path=str(file_path),
        filename=att.original_name,
        media_type=att.mime_type or "application/octet-stream",
    )


@router.get("/attachments/{att_id}/preview")
def preview_attachment(att_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Inline preview (for images). Same auth as download but doesn't force download."""
    att = db.query(Attachment).filter(Attachment.id == att_id).first()
    if not att:
        raise HTTPException(404, "Attachment not found")
    if not _can_access_task(att.project_task, user):
        raise HTTPException(403, "Not authorized")

    file_path = UPLOAD_DIR / att.stored_name
    if not file_path.exists():
        raise HTTPException(410, "File missing from storage")

    # Read and stream inline (so images render in browser)
    with open(file_path, "rb") as f:
        content = f.read()

    return Response(
        content=content,
        media_type=att.mime_type or "application/octet-stream",
        headers={"Content-Disposition": f'inline; filename="{att.original_name}"'},
    )


# ============================================================
# Delete
# ============================================================

@router.delete("/attachments/{att_id}")
def delete_attachment(att_id: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    att = db.query(Attachment).filter(Attachment.id == att_id).first()
    if not att:
        raise HTTPException(404, "Attachment not found")

    # Permission: admin OR original uploader
    if user.role != "admin" and att.uploader_id != user.id:
        raise HTTPException(403, "Only the uploader or admin can delete attachments")

    # Snapshot for audit log
    filename = att.original_name
    size = att.size_human
    task_id = att.project_task_id
    stored_name = att.stored_name
    deleted_id = att.id

    # Delete file from disk (ignore if missing)
    try:
        file_path = UPLOAD_DIR / stored_name
        if file_path.exists():
            file_path.unlink()
    except Exception:
        pass

    db.delete(att)
    db.commit()

    # Audit log
    try:
        from app.services.audit_service import log_audit
        log_audit(
            db, request=request, actor=user,
            action="deleted",
            entity_type="attachment", entity_id=deleted_id, entity_label=filename,
            summary=f"Deleted attachment '{filename}' ({size})",
            details={"task_id": task_id, "filename": filename},
            is_sensitive=True,
            commit=True,
        )
    except Exception:
        pass

    return {"ok": True, "deleted_id": deleted_id}