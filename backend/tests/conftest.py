"""
Test configuration — an isolated Postgres database per test run.

The suite runs inside the backend container (or CI with a Postgres service):
- engine/session bind to TEST_DATABASE_URL (default: the app's DB server with
  the database name swapped to ``aida_test``), so the dev data is never touched.
- schema is created once per session from the models (create_all); every test
  starts from truncated tables.
- ``runtime_sessions`` yields a session factory the agent runtime can use with
  its module-level ``SessionLocal`` patched onto it (see test_agent_e2e).
"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

TEST_DB_NAME = os.environ.get("TEST_DATABASE_DB", "aida_test")


def _base_url() -> str:
    """App DB URL without the database name (…/postgres host part)."""
    explicit = os.environ.get("TEST_DATABASE_URL")
    if explicit:
        url = explicit
    else:
        from config import settings

        url = settings.DATABASE_URL
    if url.startswith("postgresql+asyncpg://"):
        url = url.replace("postgresql+asyncpg://", "postgresql://", 1)
    url = url.split("?", 1)[0]
    return url.rsplit("/", 1)[0]


@pytest.fixture(scope="session")
def engine():
    base = _base_url()
    # Create the test database if missing (connect to a maintenance DB first).
    admin = create_engine(base + "/postgres", pool_pre_ping=True, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": TEST_DB_NAME}
        ).scalar()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
    admin.dispose()

    eng = create_engine(base + "/" + TEST_DB_NAME, pool_pre_ping=True)
    from database import Base

    import models  # noqa: F401 — registers every model on Base.metadata

    Base.metadata.create_all(bind=eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def db(engine):
    """Fresh session; all tables truncated before the test."""
    conn = engine.connect()
    conn.execute(text("BEGIN"))
    conn.execute(text(
        'TRUNCATE TABLE {} RESTART IDENTITY CASCADE'.format(
            ", ".join(f'"{t.name}"' for t in reversed(__import__("database").Base.metadata.sorted_tables)))
    ))
    conn.commit()
    conn.close()
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    s = Session()
    yield s
    s.rollback()
    s.close()


@pytest.fixture()
def runtime_sessions(engine):
    """Session factory for code that creates its own sessions via the module
    ``SessionLocal`` (the agent runtime) — bind it to the TEST database."""
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


# --- HTTP API harness -----------------------------------------------------------
#
# Full-stack router tests through fastapi.testclient: the real app, the real
# RBAC middleware (its SessionLocal patched to the test DB), real JWTs, and
# `get_db` overridden to the test engine. The TestClient is deliberately NOT
# used as a context manager, so the app lifespan (agent runner, telegram bot,
# scheduler, MCP task group) never starts inside a test.


@pytest.fixture()
def api_app(monkeypatch, runtime_sessions):
    from database import get_db
    from middleware import rbac as rbac_mod
    import main as main_mod

    monkeypatch.setattr(rbac_mod, "SessionLocal", runtime_sessions)

    def _test_get_db():
        s = runtime_sessions()
        try:
            yield s
        finally:
            s.close()

    main_mod.app.dependency_overrides[get_db] = _test_get_db
    yield main_mod.app
    main_mod.app.dependency_overrides.clear()


@pytest.fixture()
def client(api_app):
    from fastapi.testclient import TestClient
    # No `with` → no lifespan startup (runner/telegram/scheduler stay down).
    return TestClient(api_app)


def make_user(db, username="admin", role="admin", password="Sup3rSecret!x"):
    """Insert a user row and return it (password hash included)."""
    from auth import hash_password
    from models.user import User
    u = User(username=username, email=f"{username}@aida.local",
             hashed_password=hash_password(password), is_active=True,
             role=role)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture()
def admin_user(db):
    return make_user(db, "admin", "admin")


@pytest.fixture()
def admin_headers(admin_user):
    from auth import create_access_token
    return {"Authorization":
            f"Bearer {create_access_token(admin_user.id, admin_user.username)}"}


@pytest.fixture()
def viewer_user(db):
    return make_user(db, "viewer", "viewer")


@pytest.fixture()
def viewer_headers(viewer_user):
    from auth import create_access_token
    return {"Authorization":
            f"Bearer {create_access_token(viewer_user.id, viewer_user.username)}"}
