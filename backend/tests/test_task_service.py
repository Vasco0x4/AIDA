"""Kanban task-service semantics: insert-with-shift, dense renumbering,
cross-column moves, deletion compaction. These encode the board contract the
frontend drag-and-drop relies on."""
import pytest

from models.task import Task
from services.task_service import TaskService


def mk(service, name, status="backlog"):
    return service.create(title=f"T-{name}", authorized_scope="127.0.0.1",
                          status=status, source="api")


def col(service, status):
    rows = service.db.query(Task).filter(Task.status == status) \
        .order_by(Task.position, Task.id).all()
    return [(r.id, r.position) for r in rows]


@pytest.fixture()
def svc(db):
    return TaskService(db)


class TestCreate:
    def test_dense_positions(self, svc):
        a, b, c = mk(svc, "a"), mk(svc, "b"), mk(svc, "c")
        assert col(svc, "backlog") == [(a.id, 0), (b.id, 1), (c.id, 2)]

    def test_no_scope_refused_by_contract(self, svc):
        row = svc.create(title="T-noscope", source="api")
        assert row.authorized_scope is None  # runtime refuses to act on it


class TestMove:
    def test_reorder_within_column_shifts(self, svc):
        a, b, c, d = mk(svc, "a"), mk(svc, "b"), mk(svc, "c"), mk(svc, "d")
        svc.move(c.id, "backlog", 0)
        assert col(svc, "backlog") == [(c.id, 0), (a.id, 1), (b.id, 2), (d.id, 3)]

    def test_move_to_end_via_large_index_clamps(self, svc):
        a, b, c = mk(svc, "a"), mk(svc, "b"), mk(svc, "c")
        svc.move(a.id, "backlog", 99)
        assert col(svc, "backlog") == [(b.id, 0), (c.id, 1), (a.id, 2)]

    def test_cross_column_renumbers_both(self, svc):
        a, b, c = mk(svc, "a"), mk(svc, "b"), mk(svc, "c")
        svc.move(c.id, "queued", 0)
        assert col(svc, "backlog") == [(a.id, 0), (b.id, 1)]
        assert col(svc, "queued") == [(c.id, 0)]

    def test_insert_middle_of_populated_column(self, svc):
        a, b = mk(svc, "a"), mk(svc, "b")
        q1 = mk(svc, "q1", status="queued")
        q2 = mk(svc, "q2", status="queued")
        svc.move(a.id, "queued", 1)  # between q1 and q2
        assert col(svc, "queued") == [(q1.id, 0), (a.id, 1), (q2.id, 2)]
        assert col(svc, "backlog") == [(b.id, 0)]

    def test_dense_renumber_repair_after_tie(self, svc):
        # Simulate legacy corruption: two tasks sharing a position.
        a, b, c = mk(svc, "a"), mk(svc, "b"), mk(svc, "c")
        a.position = 0
        b.position = 0
        c.position = 5
        svc.db.commit()
        svc.move(c.id, "queued", 0)  # any move renumbers the vacated column
        assert col(svc, "backlog") == [(a.id, 0), (b.id, 1)]

    def test_lifecycle_stamps(self, svc):
        a = mk(svc, "a")
        svc.move(a.id, "done", 0)
        assert a.completed_at is not None
        b = mk(svc, "b")
        svc.move(b.id, "queued", 0)
        svc.move(b.id, "done", 0)
        svc.move(b.id, "backlog", 0)  # reopen keeps original completed_at
        assert b.completed_at is not None


class TestUpdateStatusChange:
    def test_status_via_update_appends_dense(self, svc):
        a, b = mk(svc, "a"), mk(svc, "b")
        q1 = mk(svc, "q1", status="queued")
        svc.update(b.id, status="queued")
        assert col(svc, "queued") == [(q1.id, 0), (b.id, 1)]
        assert col(svc, "backlog") == [(a.id, 0)]


class TestDelete:
    def test_delete_compacts_column(self, svc):
        a, b, c = mk(svc, "a"), mk(svc, "b"), mk(svc, "c")
        assert svc.delete(b.id)
        assert col(svc, "backlog") == [(a.id, 0), (c.id, 1)]

    def test_delete_cascades_children_in_code(self, svc):
        parent = mk(svc, "parent")
        child = svc.create(title="T-child", authorized_scope="127.0.0.1",
                           status="queued", source="api", )
        child.parent_task_id = parent.id
        svc.db.commit()
        assert svc.delete(parent.id)
        assert svc.db.query(Task).filter(Task.parent_task_id == parent.id).count() == 0

    def test_delete_missing_returns_false(self, svc):
        assert not svc.delete(99999)
