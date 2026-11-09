"""
Service layer for Tasks (Kanban board + autonomous work queue).

Pure DB logic; WebSocket broadcasting is done by the API layer (mirroring the
card pattern). Ordering: `position` is maintained per column, appended on
create/move.
"""
from typing import Optional
from datetime import datetime
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from models.task import Task, TaskDependency, TaskEvent, TASK_COLUMNS
from utils.logger import get_logger
from services.metrics import TASK_CLAIMS, TASK_RECOVERIES, TASK_RETRIES

logger = get_logger(__name__)


class OptimisticLockError(ValueError):
    """The caller supplied a task version that is no longer current."""


class TaskService:
    def __init__(self, db: Session):
        self.db = db

    def list_tasks(self, status: Optional[str] = None) -> list[Task]:
        q = self.db.query(Task)
        if status:
            q = q.filter(Task.status == status)
        return q.order_by(Task.status, Task.position, Task.id).all()

    def board(self) -> dict[str, list[Task]]:
        """Return tasks grouped by column, ordered by position."""
        tasks = self.db.query(Task).order_by(Task.position, Task.id).all()
        grouped: dict[str, list[Task]] = {col: [] for col in TASK_COLUMNS}
        for t in tasks:
            grouped.setdefault(t.status, []).append(t)
        return grouped

    def get(self, task_id: int) -> Optional[Task]:
        return self.db.query(Task).filter(Task.id == task_id).first()

    def list_events(self, task_id: int, *, limit: int = 200,
                    before_id: Optional[int] = None) -> list[TaskEvent]:
        """Return one chronological page, optionally before a stable event cursor."""
        bounded = max(1, min(int(limit), 1000))
        query = self.db.query(TaskEvent).filter(TaskEvent.task_id == task_id)
        if before_id is not None:
            query = query.filter(TaskEvent.id < before_id)
        return list(reversed(
            query.order_by(TaskEvent.id.desc()).limit(bounded).all()))

    def record_event(self, task_id: int, event_type: str,
                     payload: Optional[dict] = None) -> TaskEvent:
        """Buffer an event in the caller's transaction; commit with its action."""
        event = TaskEvent(task_id=task_id, event_type=event_type, payload=payload or {})
        self.db.add(event)
        return event

    def _next_position(self, status: str, exclude_id: Optional[int] = None) -> int:
        q = self.db.query(Task).filter(Task.status == status)
        if exclude_id is not None:
            # The row being moved may already be flushed into this column with
            # its stale old-column position — never count it as a sibling.
            q = q.filter(Task.id != exclude_id)
        last = q.order_by(Task.position.desc()).first()
        return (last.position + 1) if last else 0

    def create(self, *, created_by: Optional[int] = None, _commit: bool = True, **fields) -> Task:
        status = fields.get("status", "backlog")
        row = Task(
            title=fields["title"],
            description=fields.get("description"),
            target=fields.get("target"),
            authorized_scope=fields.get("authorized_scope"),
            status=status,
            position=self._next_position(status),
            priority=fields.get("priority", "medium"),
            execution_target=fields.get("execution_target", "container"),
            model_config_id=fields.get("model_config_id"),
            token_budget=fields.get("token_budget"),
            assessment_id=fields.get("assessment_id"),
            assignee=fields.get("assignee"),
            source=fields.get("source", "ui"),
            orchestrate=fields.get("orchestrate", True),
            created_by=created_by,
            meta=fields.get("meta") or {},
        )
        self.db.add(row)
        self.db.flush()
        if fields.get("dependency_ids"):
            self._replace_dependencies(row, fields["dependency_ids"])
        self.record_event(row.id, "created", {"status": status, "title": row.title})
        if _commit:
            self.db.commit()
            self.db.refresh(row)
        else:
            # The scheduler wraps task creation and schedule advancement in a
            # single transaction while holding the schedule row lock.
            self.db.flush()
        return row

    def claim(self, task_id: int, *, owner: str, lease_seconds: int = 60) -> Optional[Task]:
        """Atomically assign one queued task and persist its fencing-token lease."""
        token = str(uuid4())
        claimed = self.db.execute(text(
            "UPDATE tasks SET status='running', assignee=:owner, lease_owner=:owner, "
            "lease_token=:token, heartbeat_at=NOW(), "
            "lease_expires_at=NOW() + (:lease_seconds * INTERVAL '1 second'), "
            "started_at=COALESCE(started_at, NOW()), completed_at=NULL, "
            "updated_at=NOW(), version=version+1 "
            "WHERE id=:task_id AND status='queued' RETURNING id"),
            {"task_id": task_id, "owner": owner, "token": token,
             "lease_seconds": max(1, int(lease_seconds))}).first()
        if claimed is None:
            self.db.rollback()
            return None
        self.record_event(task_id, "claimed", {
            "owner": owner, "lease_seconds": max(1, int(lease_seconds))})
        TASK_CLAIMS.inc()
        self.db.commit()
        self.db.expire_all()
        return self.get(task_id)

    def heartbeat(self, task_id: int, *, lease_token: str,
                  lease_seconds: int = 60) -> bool:
        """Extend a live lease only when its fencing token still matches."""
        changed = self.db.execute(text(
            "UPDATE tasks SET heartbeat_at=NOW(), "
            "lease_expires_at=NOW() + (:lease_seconds * INTERVAL '1 second'), "
            "updated_at=NOW(), version=version+1 "
            "WHERE id=:task_id AND status='running' AND lease_token=:token "
            "AND lease_expires_at > NOW()"),
            {"task_id": task_id, "token": lease_token,
             "lease_seconds": max(1, int(lease_seconds))}).rowcount
        if not changed:
            self.db.rollback()
            return False
        self.db.commit()
        return True

    def recover_stale(self, task_id: int, *, lease_token: str) -> Optional[Task]:
        """Requeue an expired lease, provided no heartbeat won the race."""
        row = self.get(task_id)
        if not row or row.status != "running":
            return None
        now = datetime.utcnow()
        meta = dict(row.meta or {})
        if meta.get("checkpoint"):
            meta["resume"] = True
        changed = self.db.query(Task).filter(
            Task.id == task_id,
            Task.status == "running",
            Task.lease_token == lease_token,
            Task.lease_expires_at <= now,
        ).update({
            Task.status: "queued",
            Task.started_at: None,
            Task.lease_owner: None,
            Task.lease_token: None,
            Task.heartbeat_at: None,
            Task.lease_expires_at: None,
            Task.meta: meta,
            Task.updated_at: now,
            Task.version: Task.version + 1,
        }, synchronize_session=False)
        if not changed:
            self.db.rollback()
            return None
        self.record_event(task_id, "recovered", {
            "manual": False, "reason": "lease_expired"})
        TASK_RECOVERIES.labels(reason="lease_expired").inc()
        self.db.commit()
        self.db.expire_all()
        return self.get(task_id)

    def recover(self, task_id: int, *, expected_version: Optional[int] = None) -> Optional[Task]:
        """Manually requeue a running task and fence off its previous worker."""
        row = self.get(task_id)
        if not row or row.status != "running":
            return None
        if expected_version is not None and row.version != expected_version:
            raise OptimisticLockError(
                f"Task version conflict: expected {expected_version}, current {row.version}")
        meta = dict(row.meta or {})
        if meta.get("checkpoint"):
            meta["resume"] = True
        owner = row.lease_owner
        row.status = "queued"
        row.position = self._next_position("queued", exclude_id=row.id)
        row.started_at = None
        row.completed_at = None
        row.lease_owner = None
        row.lease_token = None
        row.heartbeat_at = None
        row.lease_expires_at = None
        row.meta = meta
        self.record_event(task_id, "recovered", {"manual": True, "owner": owner})
        TASK_RECOVERIES.labels(reason="manual").inc()
        try:
            self.db.commit()
        except StaleDataError as exc:
            self.db.rollback()
            raise OptimisticLockError("Task version conflict") from exc
        self.db.refresh(row)
        return row

    def set_dependencies(self, task_id: int, dependency_ids: list[int],
                         expected_version: Optional[int] = None) -> Optional[Task]:
        """Replace explicit prerequisites, rejecting unknown ids and DAG cycles."""
        row = self.get(task_id)
        if not row:
            return None
        if expected_version is not None and row.version != expected_version:
            raise OptimisticLockError(
                f"Task version conflict: expected {expected_version}, current {row.version}")
        self._replace_dependencies(row, dependency_ids)
        row.updated_at = datetime.utcnow()
        self.record_event(task_id, "dependencies_updated", {
            "dependency_ids": list(dict.fromkeys(dependency_ids))})
        try:
            self.db.commit()
        except StaleDataError as exc:
            self.db.rollback()
            raise OptimisticLockError("Task version conflict") from exc
        self.db.refresh(row)
        return row

    def _replace_dependencies(self, row: Task, dependency_ids: list[int]) -> None:
        """Validate and buffer a complete dependency replacement."""
        task_id = row.id
        ids = list(dict.fromkeys(dependency_ids))
        if task_id in ids:
            raise ValueError("Dependency cycle detected")
        if ids:
            known = {value for (value,) in self.db.query(Task.id).filter(Task.id.in_(ids))}
            unknown = set(ids) - known
            if unknown:
                raise ValueError(f"Unknown task dependencies: {sorted(unknown)}")

        adjacency: dict[int, list[int]] = {}
        for edge in self.db.query(TaskDependency).all():
            adjacency.setdefault(edge.task_id, []).append(edge.depends_on_id)
        adjacency[task_id] = ids
        for start in ids:
            seen: set[int] = set()
            stack = [start]
            while stack:
                current = stack.pop()
                if current == task_id:
                    raise ValueError("Dependency cycle detected")
                if current in seen:
                    continue
                seen.add(current)
                stack.extend(adjacency.get(current, []))

        self.db.query(TaskDependency).filter(
            TaskDependency.task_id == task_id).delete(synchronize_session=False)
        for dependency_id in ids:
            self.db.add(TaskDependency(task_id=task_id, depends_on_id=dependency_id))

    def retry(self, task_id: int, *, expected_version: Optional[int] = None) -> Optional[Task]:
        """Explicitly requeue terminal/review work with a fresh retry budget."""
        row = self.get(task_id)
        if not row or row.status not in ("failed", "needs_review", "done"):
            return None
        if expected_version is not None and row.version != expected_version:
            raise OptimisticLockError(
                f"Task version conflict: expected {expected_version}, current {row.version}")
        previous = row.status
        row.status = "queued"
        row.position = self._next_position("queued", exclude_id=row.id)
        row.started_at = None
        row.completed_at = None
        row.result_summary = None
        row.lease_owner = None
        row.lease_token = None
        row.heartbeat_at = None
        row.lease_expires_at = None
        meta = dict(row.meta or {})
        meta["retry_count"] = 0
        meta.pop("retry_not_before", None)
        meta.pop("last_error", None)
        row.meta = meta
        self.record_event(task_id, "retried", {"previous_status": previous})
        TASK_RETRIES.labels(trigger="manual").inc()
        try:
            self.db.commit()
        except StaleDataError as exc:
            self.db.rollback()
            raise OptimisticLockError("Task version conflict") from exc
        self.db.refresh(row)
        return row

    def update(self, task_id: int, **fields) -> Optional[Task]:
        expected_version = fields.pop("expected_version", None)
        row = self.get(task_id)
        if not row:
            return None
        if expected_version is not None and row.version != expected_version:
            raise OptimisticLockError(
                f"Task version conflict: expected {expected_version}, current {row.version}")
        # If status changes here (not via move), re-append to the new column.
        if "status" in fields and fields["status"] and fields["status"] != row.status:
            old_status = row.status
            row.status = fields.pop("status")
            self._stamp_lifecycle(row)
            try:
                self.db.flush()  # ditto: _renumber must not see this row in the old column
            except StaleDataError as exc:
                self.db.rollback()
                raise OptimisticLockError("Task version conflict") from exc
            self._renumber(old_status)
            row.position = self._next_position(row.status, exclude_id=row.id)
        for key, value in fields.items():
            if value is not None and hasattr(row, key):
                setattr(row, key, value)
        self.record_event(task_id, "updated", {
            "fields": sorted(fields), "status": row.status})
        try:
            self.db.commit()
        except StaleDataError as exc:
            self.db.rollback()
            raise OptimisticLockError("Task version conflict") from exc
        self.db.refresh(row)
        return row

    def move(self, task_id: int, status: str, position: int,
             expected_version: Optional[int] = None) -> Optional[Task]:
        """Move a task to a column, inserting at ``position`` (0-based, among the
        tasks already there) — siblings shift down and the whole column is
        renumbered densely, so no ties and the board order is stable."""
        row = self.get(task_id)
        if not row:
            return None
        if expected_version is not None and row.version != expected_version:
            raise OptimisticLockError(
                f"Task version conflict: expected {expected_version}, current {row.version}")
        old_status = row.status
        old_position = row.position
        if old_status != status:
            row.status = status
            self._stamp_lifecycle(row)
            # Flush the column change so the sibling/renumber queries below see
            # the new membership — required in autoflush=False sessions, where
            # _renumber(old) would otherwise still see this row in the DB's old
            # column and clobber the position just assigned above.
            try:
                self.db.flush()
            except StaleDataError as exc:
                self.db.rollback()
                raise OptimisticLockError("Task version conflict") from exc
        siblings = (
            self.db.query(Task)
            .filter(Task.status == row.status, Task.id != row.id)
            .order_by(Task.position, Task.id)
            .all()
        )
        idx = max(0, min(int(position), len(siblings)))
        siblings.insert(idx, row)
        for i, t in enumerate(siblings):
            t.position = i
        if old_status != status:
            self._renumber(old_status)
        self.record_event(task_id, "moved", {
            "from_status": old_status, "to_status": status,
            "from_position": old_position, "to_position": row.position})
        try:
            self.db.commit()
        except StaleDataError as exc:
            self.db.rollback()
            raise OptimisticLockError("Task version conflict") from exc
        self.db.refresh(row)
        return row

    def _renumber(self, status: str) -> None:
        """Compact a column's positions into a dense 0..n-1 sequence."""
        rows = (
            self.db.query(Task)
            .filter(Task.status == status)
            .order_by(Task.position, Task.id)
            .all()
        )
        for i, r in enumerate(rows):
            if r.position != i:
                r.position = i

    def _stamp_lifecycle(self, row: Task) -> None:
        """Set started_at / completed_at as the task crosses stages."""
        if row.status == "running" and row.started_at is None:
            row.started_at = datetime.utcnow()
        if row.status in ("done", "failed") and row.completed_at is None:
            row.completed_at = datetime.utcnow()
        # Reopening preserves the original completion timestamp for audit
        # continuity; explicit retry() starts a fresh attempt and clears it.
        if row.status != "running":
            row.lease_owner = None
            row.lease_token = None
            row.heartbeat_at = None
            row.lease_expires_at = None

    def delete(self, task_id: int) -> bool:
        row = self.get(task_id)
        if not row:
            return False
        # Collect assessment ids referenced by this task + its children so we can
        # clean up empty auto-created assessments afterwards.
        children = self.db.query(Task).filter(Task.parent_task_id == task_id).all()
        assessment_ids = {t.assessment_id for t in ([row] + children) if t.assessment_id}
        statuses = {row.status} | {c.status for c in children}

        # Cascade to sub-tasks in code (the parent_task_id column is added via
        # ALTER without a DB-level FK, so DB cascade can't be relied on).
        self.db.query(Task).filter(Task.parent_task_id == task_id).delete(
            synchronize_session=False)
        self.db.delete(row)
        self.db.commit()

        # Keep the vacated columns densely ordered.
        for status in statuses:
            try:
                self._renumber(status)
                self.db.commit()
            except Exception:
                self.db.rollback()

        self._cleanup_empty_assessments(assessment_ids)
        return True

    def _cleanup_empty_assessments(self, assessment_ids: set) -> None:
        """Delete an auto-created assessment if nothing references it and it has
        no findings/recon/commands/credentials (i.e. it was never really used)."""
        if not assessment_ids:
            return
        from models import Assessment, Card, ReconData, CommandHistory, Credential
        from models.artifact import Artifact
        for aid in assessment_ids:
            if not aid:
                continue
            # Still referenced by another task? keep it.
            if self.db.query(Task).filter(Task.assessment_id == aid).first():
                continue
            has_data = (
                self.db.query(Card).filter(Card.assessment_id == aid).first()
                or self.db.query(ReconData).filter(ReconData.assessment_id == aid).first()
                or self.db.query(CommandHistory).filter(CommandHistory.assessment_id == aid).first()
                or self.db.query(Credential).filter(Credential.assessment_id == aid).first()
                or self.db.query(Artifact).filter(Artifact.assessment_id == aid).first()
            )
            if has_data:
                continue
            a = self.db.query(Assessment).filter(Assessment.id == aid).first()
            if a:
                self.db.delete(a)
                self.db.commit()
