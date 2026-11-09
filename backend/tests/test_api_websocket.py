"""
WebSocket API + ConnectionManager.

The endpoint is public at the RBAC layer (token validated inside the handler):
bad/missing tokens are rejected with a policy-violation close, good tokens get
the connected → ping/pong → error-event protocol. The manager itself is tested
with fake sockets — room routing, global fan-in, and dead-connection cleanup.
"""
from __future__ import annotations

import json

import pytest
from starlette.testclient import TestClient  # noqa: F401 — via `client` fixture
from starlette.websockets import WebSocketDisconnect

from api import websocket as ws_api
from websocket import manager as manager_mod
from websocket.manager import ConnectionManager
from websocket.events import EventType, create_event


@pytest.fixture()
def ws_client(client, monkeypatch, runtime_sessions):
    """API client with the WS handler's own DB session pointed at the test DB."""
    monkeypatch.setattr(ws_api, "SessionLocal", runtime_sessions)
    # Isolate the global manager's state between tests.
    manager_mod.manager.active_connections.clear()
    manager_mod.manager.global_connections.clear()
    manager_mod.manager.assessment_connections.clear()
    return client


def _token(user):
    from auth import create_access_token
    return create_access_token(user.id, user.username)


# --- auth gate -------------------------------------------------------------------

def test_ws_rejects_missing_token(ws_client):
    with pytest.raises(WebSocketDisconnect):
        with ws_client.websocket_connect("/api/ws"):
            pass


def test_ws_rejects_garbage_token(ws_client):
    with pytest.raises(WebSocketDisconnect):
        with ws_client.websocket_connect("/api/ws?token=not.a.jwt"):
            pass


def test_ws_rejects_inactive_user(ws_client, db, monkeypatch, runtime_sessions):
    from conftest import make_user
    monkeypatch.setattr(ws_api, "SessionLocal", runtime_sessions)
    user = make_user(db, "ghost", "viewer")
    db.refresh(user)
    user.is_active = False
    db.commit()

    with pytest.raises(WebSocketDisconnect):
        with ws_client.websocket_connect(f"/api/ws?token={_token(user)}"):
            pass


# --- live protocol ----------------------------------------------------------------

def test_ws_global_flow(ws_client, admin_user):
    with ws_client.websocket_connect(f"/api/ws?token={_token(admin_user)}") as ws:
        connected = ws.receive_json()
        assert connected["type"] == EventType.CONNECTED.value
        assert connected["data"]["message"]

        ws.send_text(json.dumps({"type": "ping"}))
        pong = ws.receive_json()
        assert pong["type"] == EventType.PONG.value
        assert pong["data"]["message"] == "pong"

        ws.send_text("this is not json")
        err = ws.receive_json()
        assert err["type"] == EventType.ERROR.value
        assert "Invalid JSON" in err["data"]["message"]


def test_ws_assessment_room_flow(ws_client, admin_user):
    with ws_client.websocket_connect(
            f"/api/ws/assessment/42?token={_token(admin_user)}") as ws:
        connected = ws.receive_json()
        assert connected["type"] == EventType.CONNECTED.value
        assert connected["assessment_id"] == 42
        assert connected["data"]["assessment_id"] == 42

        ws.send_text(json.dumps({"type": "ping"}))
        assert ws.receive_json()["type"] == EventType.PONG.value


# --- ConnectionManager with fake sockets -------------------------------------------

class FakeWS:
    """Minimal async stand-in for a Starlette WebSocket."""

    def __init__(self, fail_sends=False):
        self.sent: list[str] = []
        self.fail_sends = fail_sends
        self.accepted = False

    async def accept(self):
        self.accepted = True

    async def send_text(self, message: str):
        if self.fail_sends:
            raise RuntimeError("connection closed")
        self.sent.append(message)


@pytest.fixture()
def mgr():
    return ConnectionManager()


async def test_manager_registration_and_counts(mgr):
    g, a1, a2 = FakeWS(), FakeWS(), FakeWS()
    await mgr.connect(g)
    await mgr.connect(a1, assessment_id=1)
    await mgr.connect(a2, assessment_id=1)

    assert mgr.get_connection_count() == 3
    assert mgr.get_connection_count(assessment_id=1) == 2
    assert mgr.get_connection_count(assessment_id=99) == 0
    assert g.accepted and a1.accepted

    mgr.disconnect(a1)
    assert mgr.get_connection_count() == 2
    assert mgr.get_connection_count(assessment_id=1) == 1

    mgr.disconnect(a2)
    # The now-empty room is deleted, not left behind.
    assert 1 not in mgr.assessment_connections
    assert mgr.get_connection_count(assessment_id=1) == 0


async def test_manager_disconnect_is_idempotent(mgr):
    ws = FakeWS()
    await mgr.connect(ws)
    mgr.disconnect(ws)
    mgr.disconnect(ws)  # second call must be a no-op
    assert mgr.get_connection_count() == 0


async def test_manager_broadcast_targets_room_and_globals(mgr):
    room, other, glob = FakeWS(), FakeWS(), FakeWS()
    await mgr.connect(room, assessment_id=7)
    await mgr.connect(other, assessment_id=8)
    await mgr.connect(glob)

    event = create_event(EventType.TASK_UPDATED, {"task_id": 1}, assessment_id=7)
    await mgr.broadcast(event, assessment_id=7)

    assert json.loads(room.sent[0])["type"] == EventType.TASK_UPDATED.value
    assert json.loads(glob.sent[0])["data"]["task_id"] == 1
    assert other.sent == []          # different room: not addressed


async def test_manager_broadcast_global_hits_everyone(mgr):
    room, glob = FakeWS(), FakeWS()
    await mgr.connect(room, assessment_id=7)
    await mgr.connect(glob)

    await mgr.broadcast(create_event(EventType.TASK_CREATED, {"task": {}}))

    assert len(room.sent) == 1
    assert len(glob.sent) == 1


async def test_manager_broadcast_cleans_dead_connections(mgr):
    dead, alive = FakeWS(fail_sends=True), FakeWS()
    await mgr.connect(dead)
    await mgr.connect(alive)

    await mgr.broadcast(create_event(EventType.PING, {}))

    assert mgr.get_connection_count() == 1
    assert mgr.active_connections == [alive]


async def test_manager_send_personal_cleans_closed_socket(mgr):
    dead = FakeWS(fail_sends=True)
    await mgr.connect(dead)

    await mgr.send_personal(dead, create_event(EventType.PONG, {}))

    assert mgr.get_connection_count() == 0
