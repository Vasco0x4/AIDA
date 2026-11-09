"""
Build the extra-context block the agent reads for a task: user comments and the
text of attached files. For a child sub-task, the PARENT audit's comments/files
are included too (they belong to the same engagement).

The Kanban board is a LIVE control surface (Hermes-style): comments added while
the agent is running — or while a task sits stopped/queued — are picked up
mid-run via build_context_update() and handed to the model as new instructions.
"""
from __future__ import annotations

from models.task import Task
from models.task_comment import TaskComment
from models.task_file import TaskFile

_PER_FILE_CHARS = 8000
_TOTAL_CHARS = 20000


def _task_ids(task: Task) -> list[int]:
    ids = [task.id]
    if task.parent_task_id:
        ids.append(task.parent_task_id)
    return ids


def collect_context(db, task: Task) -> tuple[list, list]:
    """All comments+files for the task (and its parent audit), oldest first."""
    ids = _task_ids(task)
    comments = (
        db.query(TaskComment)
        .filter(TaskComment.task_id.in_(ids))
        .order_by(TaskComment.created_at.asc(), TaskComment.id.asc())
        .all()
    )
    files = (
        db.query(TaskFile)
        .filter(TaskFile.task_id.in_(ids))
        .order_by(TaskFile.created_at.asc(), TaskFile.id.asc())
        .all()
    )
    return comments, files


def context_ids(db, task: Task) -> tuple[list[int], list[int]]:
    """Ids of every comment/file currently on the task (the 'seen' snapshot)."""
    comments, files = collect_context(db, task)
    return [c.id for c in comments], [f.id for f in files]


def build_task_context(db, task: Task) -> str:
    """Full context block (used to prime a fresh run)."""
    comments, files = collect_context(db, task)
    if not comments and not files:
        return ""

    parts = []
    if comments:
        parts.append("USER COMMENTS / INSTRUCTIONS ON THIS TASK:")
        for c in comments:
            parts.append(f"- [{c.author}] {c.body}")
    if files:
        parts.append("\nATTACHED CONTEXT FILES (read and use as needed):")
        for f in files:
            txt = (f.extracted_text or "").strip()
            if txt:
                parts.append(f"\n--- FILE: {f.filename} ---\n{txt[:_PER_FILE_CHARS]}")
            else:
                parts.append(f"\n--- FILE: {f.filename} (binary/no text) ---")

    block = "\n".join(parts)
    return block[:_TOTAL_CHARS]


def build_context_update(db, task: Task, seen_comment_ids: set,
                         seen_file_ids: set) -> tuple[str, list[int], list[int]]:
    """Comments/files the agent has NOT seen yet — operator steering added on
    the Kanban board since the last step. Returns (instruction_block,
    new_comment_ids, new_file_ids); the block is '' when nothing is new."""
    comments, files = collect_context(db, task)
    new_comments = [c for c in comments if c.id not in seen_comment_ids]
    new_files = [f for f in files if f.id not in seen_file_ids]
    if not new_comments and not new_files:
        return "", [], []

    parts = []
    if new_comments:
        parts.append(
            "NEW OPERATOR COMMENTS (added on the Kanban board — direct "
            "instructions from the human operator; adjust course now):")
        for c in new_comments:
            parts.append(f"- [{c.author}] {c.body}")
    if new_files:
        parts.append("\nNEW ATTACHED FILES (read and use as needed):")
        for f in new_files:
            txt = (f.extracted_text or "").strip()
            if txt:
                parts.append(f"\n--- FILE: {f.filename} ---\n{txt[:_PER_FILE_CHARS]}")
            else:
                parts.append(f"\n--- FILE: {f.filename} (binary/no text) ---")

    block = "\n".join(parts)
    return (block[:_TOTAL_CHARS],
            [c.id for c in new_comments],
            [f.id for f in new_files])
