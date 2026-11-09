"""
Config env handling (E5): the DATABASE_URL builder must survive
Kubernetes-style injected env vars.

A Service named `postgres` in the pod's namespace makes the kubelet inject
docker-link env — POSTGRES_PORT=tcp://<cluster-ip>:5432 — which must not leak
into the SQLAlchemy URL (it crashes create_engine with
ValueError: invalid literal for int() ... 'tcp:').
"""
from __future__ import annotations

from config import Settings


def _make(**env) -> Settings:
    import os
    saved = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    try:
        return Settings()
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_k8s_tcp_port_env_is_normalized():
    s = _make(POSTGRES_HOST="postgres",
              POSTGRES_PORT="tcp://10.43.123.99:5432",
              POSTGRES_USER="aida", POSTGRES_PASSWORD="pw",
              POSTGRES_DB="aida_assessments")
    assert s.DATABASE_URL == "postgresql://aida:pw@postgres:5432/aida_assessments"


def test_plain_port_env_passthrough():
    s = _make(POSTGRES_HOST="postgres", POSTGRES_PORT="5433",
              POSTGRES_USER="aida", POSTGRES_PASSWORD="pw",
              POSTGRES_DB="aida_assessments")
    assert s.DATABASE_URL == "postgresql://aida:pw@postgres:5433/aida_assessments"
