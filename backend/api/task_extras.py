"""
Task comments + context file attachments.

Both are agent-consumable: comments are instructions/hints the agent reads on its
next run; files (txt/pdf/html/md/…) are context material whose text is extracted
and fed to the agent. See services/agent/context.py for how they're injected.
"""
import io
import re
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime

from database import get_db
from auth import get_current_user
from models.user import User
from models.task import Task
from models.task_comment import TaskComment
from models.task_file import TaskFile
from websocket.manager import manager
from websocket.events import create_event, EventType

router = APIRouter(prefix="/tasks", tags=["task-extras"])

MAX_FILE_BYTES = 15 * 1024 * 1024


# ------------------------------------------------------------------ helpers
def extract_text(filename: str, content_type: str, data: bytes) -> str:
    """Best-effort plain-text extraction for the agent to read."""
    name = (filename or "").lower()
    ctype = (content_type or "").lower()

    def _dec():
        for enc in ("utf-8", "latin-1"):
            try:
                return data.decode(enc)
            except Exception:
                continue
        return ""

    if name.endswith((".txt", ".md", ".csv", ".json", ".log", ".yaml", ".yml", ".ini", ".conf", ".xml")) \
            or ctype.startswith("text/") or "json" in ctype:
        text = _dec()
        if name.endswith(".html") or name.endswith(".htm") or "html" in ctype:
            return _strip_html(text)
        return text
    if name.endswith((".html", ".htm")) or "html" in ctype:
        return _strip_html(_dec())
    if name.endswith(".pdf") or "pdf" in ctype:
        return _pdf_text(data)
    # Unknown/binary → try a decode, else empty.
    return _dec()[:0]


def _strip_html(html: str) -> str:
    html = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    text = re.sub(r"&nbsp;", " ", text)
    return re.sub(r"[ \t]*\n\s*\n\s*", "\n\n", re.sub(r"[ \t]+", " ", text)).strip()


def _pdf_text(data: bytes) -> str:
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        return "\n".join((p.extract_text() or "") for p in reader.pages).strip()
    except Exception:
        return "(PDF text extraction unavailable)"


def _require_task(db: Session, task_id: int) -> Task:
    t = db.query(Task).filter(Task.id == task_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Task not found")
    return t


# ------------------------------------------------------------------ comments
class CommentCreate(BaseModel):
    body: str


class CommentResponse(BaseModel):
    id: int
    task_id: int
    author: str
    body: str
    created_at: Optional[datetime]

    class Config:
        from_attributes = True


@router.get("/{task_id}/comments", response_model=List[CommentResponse])
def list_comments(task_id: int, db: Session = Depends(get_db)):
    return (
        db.query(TaskComment)
        .filter(TaskComment.task_id == task_id)
        .order_by(TaskComment.created_at.asc())
        .all()
    )


@router.post("/{task_id}/comments", response_model=CommentResponse, status_code=201)
async def add_comment(task_id: int, body: CommentCreate,
                      db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _require_task(db, task_id)
    row = TaskComment(task_id=task_id, author=getattr(user, "username", "user"),
                      body=body.body.strip())
    db.add(row)
    db.commit()
    db.refresh(row)
    await manager.broadcast(create_event(
        EventType.TASK_UPDATED, {"task_id": task_id, "comment_added": True}))
    return row


@router.delete("/comments/{comment_id}", status_code=204)
def delete_comment(comment_id: int, db: Session = Depends(get_db)):
    row = db.query(TaskComment).filter(TaskComment.id == comment_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Comment not found")
    db.delete(row)
    db.commit()


# ------------------------------------------------------------------ files
class FileMeta(BaseModel):
    id: int
    task_id: int
    filename: str
    content_type: str
    size_bytes: Optional[int]
    has_text: bool = False

    class Config:
        from_attributes = True


@router.get("/{task_id}/files", response_model=List[FileMeta])
def list_files(task_id: int, db: Session = Depends(get_db)):
    rows = (
        db.query(TaskFile)
        .filter(TaskFile.task_id == task_id)
        .order_by(TaskFile.created_at.asc())
        .all()
    )
    return [FileMeta(id=r.id, task_id=r.task_id, filename=r.filename,
                     content_type=r.content_type, size_bytes=r.size_bytes,
                     has_text=bool(r.extracted_text)) for r in rows]


@router.post("/{task_id}/files", response_model=FileMeta, status_code=201)
async def upload_file(task_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    _require_task(db, task_id)
    data = await file.read()
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 15 MB)")
    if not data:
        raise HTTPException(status_code=422, detail="Empty file")
    text = extract_text(file.filename, file.content_type or "", data)
    row = TaskFile(
        task_id=task_id, filename=file.filename or "file",
        content_type=file.content_type or "application/octet-stream",
        size_bytes=len(data), extracted_text=(text or "")[:200000], data=data,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    await manager.broadcast(create_event(
        EventType.TASK_UPDATED, {"task_id": task_id, "file_added": True}))
    return FileMeta(id=row.id, task_id=row.task_id, filename=row.filename,
                    content_type=row.content_type, size_bytes=row.size_bytes,
                    has_text=bool(row.extracted_text))


@router.get("/files/{file_id}/content")
def get_file(file_id: int, db: Session = Depends(get_db)):
    row = db.query(TaskFile).filter(TaskFile.id == file_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="File not found")
    return StreamingResponse(
        io.BytesIO(row.data), media_type=row.content_type,
        headers={"Content-Disposition": f'inline; filename="{row.filename}"'})


@router.delete("/files/{file_id}", status_code=204)
def delete_file(file_id: int, db: Session = Depends(get_db)):
    row = db.query(TaskFile).filter(TaskFile.id == file_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="File not found")
    db.delete(row)
    db.commit()
