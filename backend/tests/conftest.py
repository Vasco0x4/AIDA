"""
Test setup: a real Postgres (the models use ARRAY columns), wiped before and
after the run, and helpers to create users, assessments and API keys.

    docker run -d --rm --name aida-test-pg -p 127.0.0.1:55432:5432 \
        -e POSTGRES_USER=aida -e POSTGRES_PASSWORD=aida -e POSTGRES_DB=aida_test \
        postgres:16-alpine
    AIDA_TEST_DATABASE_URL=postgresql://aida:aida@127.0.0.1:55432/aida_test \
        python -m pytest backend/tests

The database name must contain "test": every table in it is dropped.
"""
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import pytest

TEST_DATABASE_URL = os.environ.get(
    "AIDA_TEST_DATABASE_URL", "postgresql://aida:aida@127.0.0.1:5432/aida_test"
)
if "test" not in (urlparse(TEST_DATABASE_URL).path or ""):
    raise RuntimeError(
        f"Refusing to run the tests against {TEST_DATABASE_URL!r}: they drop every "
        "table. Point AIDA_TEST_DATABASE_URL at a database whose name contains 'test'."
    )

# Before any backend import: config.py / auth.py read these at import time.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault("SECRET_KEY", "tests-only-secret-key-0123456789abcdef")
os.environ["LOG_FILE_ENABLED"] = "false"
os.environ["LOG_CONSOLE_ENABLED"] = "false"
# The MCP service would otherwise look for pentest containers with `docker ps`.
os.environ["AIDA_DEPLOYMENT_MODE"] = "localhost"
os.environ.pop("AIDA_TOKEN", None)

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import text  # noqa: E402

import models  # noqa: E402,F401  (registers every table)
from auth import generate_api_key, hash_password  # noqa: E402
from database import Base, SessionLocal, engine  # noqa: E402
from models.api_key import ApiKey  # noqa: E402
from models.assessment import Assessment  # noqa: E402
from models.platform_settings import PlatformSettings  # noqa: E402
from models.user import User  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _schema():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture(autouse=True)
def _clean_tables(_schema):
    yield
    names = ", ".join(t.name for t in reversed(Base.metadata.sorted_tables))
    with engine.begin() as conn:
        # No RESTART IDENTITY: the HTTP MCP app caches client contexts by
        # API key id, and ids are never reused in a real database either.
        conn.execute(text(f"TRUNCATE {names} CASCADE"))


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


class Factory:
    """Create rows the tests need, committed so the app's own sessions see them."""

    def __init__(self, session):
        self.db = session
        self._n = 0

    def _next(self) -> int:
        self._n += 1
        return self._n

    def user(self, username=None, active=True, role="user") -> User:
        user = User(
            username=username or f"user{self._next()}",
            hashed_password=hash_password("password123"),
            is_active=active,
            role=role,
        )
        self.db.add(user)
        self.db.commit()
        return user

    def assessment(self, name=None) -> Assessment:
        assessment = Assessment(name=name or f"assessment-{self._next()}", status="active")
        self.db.add(assessment)
        self.db.commit()
        return assessment

    def api_key(self, owner: User, scope="mcp", assessment: Assessment = None,
                revoked=False) -> str:
        """Create a key and return its plaintext."""
        from datetime import datetime, timezone

        full, prefix, hashed = generate_api_key()
        self.db.add(ApiKey(
            name=f"key{self._next()}",
            key_prefix=prefix,
            key_hash=hashed,
            owner_user_id=owner.id,
            scope=scope,
            assessment_id=assessment.id if assessment else None,
            revoked_at=datetime.now(timezone.utc) if revoked else None,
        ))
        self.db.commit()
        return full

    def setting(self, key: str, value: str) -> None:
        row = self.db.query(PlatformSettings).filter(PlatformSettings.key == key).first()
        if row:
            row.value = value
        else:
            self.db.add(PlatformSettings(key=key, value=value))
        self.db.commit()


@pytest.fixture
def make(db) -> Factory:
    return Factory(db)
