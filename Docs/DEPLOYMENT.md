# AIDA — Deployment Guide

Two supported deployment paths:

| | Single host (Docker Compose) | Kubernetes |
|---|---|---|
| Files | `docker-compose.prod.yml` (+ profiles) | `k8s/` (kustomize) |
| Pentest execution | host Docker via filtered socket proxy | Docker-in-Docker sidecar in the backend pod |
| Scale out | — | frontend only; **backend must stay at 1 replica** |
| TLS | Caddy profile / `./start.sh --domain` | Ingress + cert-manager |

The dev stack (`docker-compose.yml`, ports 8001/5174/5433) is for development
only — never expose it.

---

## 1. Single host — docker-compose.prod.yml

A self-contained production stack: Postgres 16, hardened backend (non-root
uid 10001, no dev deps), Nginx frontend (unprivileged uid 101), a filtered
Docker socket proxy for the pentest executor, and the pentest container.

### First run

```bash
cp backend/.env.example backend/.env
# EDIT backend/.env — set POSTGRES_PASSWORD (required, compose refuses to
# start without it). SECRET_KEY is auto-generated on first start if unset,
# but pin it explicitly so JWTs survive redeployments.
docker compose --env-file backend/.env -f docker-compose.prod.yml up -d
```

Default host ports (all loopback-bound unless overridden):

| Service  | Port | Override |
|----------|------|----------|
| Frontend | 31337 | `FRONTEND_PORT`, `FRONTEND_BIND` |
| Backend  | 8000  | `BACKEND_PORT`, `BACKEND_BIND` |
| Postgres | not published | — (use `docker compose ... exec postgres psql`) |

Create the first admin:

```bash
docker compose --env-file backend/.env -f docker-compose.prod.yml exec -T backend python -c "
import asyncio
from database import SessionLocal
from models.user import User
from auth import hash_password
s = SessionLocal()
s.add(User(username='admin', email='admin@example.com',
           hashed_password=hash_password('CHANGE_ME_NOW'), role='admin', is_active=True))
s.commit(); print('admin created')"
```

(Or use your OIDC provider — see Settings → SSO; JIT-provisioned users get the
`auditor` role.)

### TLS

```bash
mkdir -p .aida && cp deploy/Caddyfile.example .aida/Caddyfile   # edit host
docker compose --env-file backend/.env -f docker-compose.prod.yml --profile tls up -d
```

Set `BACKEND_CORS_ORIGINS=https://your-domain` in `backend/.env`.
`./start.sh --domain your.domain` wraps the same thing with Caddyfile
generation + Let's Encrypt.

### Monitoring

`--profile monitoring` starts Prometheus scraping the backend `/metrics`
(config: `deploy/prometheus.yml`). `/metrics` is unauthenticated like
`/health` — keep it behind the edge or off the public network.

### Images

Defaults: `vasco0x4/aida-backend`, `vasco0x4/aida-pentest` from Docker Hub,
frontend built locally from `frontend/Dockerfile.prod` (it bakes
`VITE_API_URL=/api`). Hub images are **linux/amd64** — on arm64 hosts build
locally:

```bash
docker compose --env-file backend/.env -f docker-compose.prod.yml build
```

Override with `BACKEND_IMAGE` / `FRONTEND_IMAGE` / `PENTEST_IMAGE` env vars.

### Security notes

- The backend reaches the host Docker daemon through
  `tecnativa/docker-socket-proxy` with only `containers` + `exec` enabled —
  no image builds, no host mounts, no root-equivalent API. That is the whole
  attack surface the agent's executor gets.
- If another AIDA stack shares the daemon, override BOTH
  `PENTEST_CONTAINER_NAME` and `DEFAULT_CONTAINER_NAME` (they are a pair).

---

## 2. Kubernetes — k8s/ (kustomize)

Requires cluster ≥ 1.29 (native sidecar containers) and an ingress
controller for public access (or use `kubectl port-forward`).

### Apply

```bash
cp k8s/secret.example.yaml k8s/secret.yaml    # edit — real values, gitignored
kubectl apply -k k8s/
kubectl -n aida get pods                       # backend 2/2, frontend n/n, postgres 1/1
```

Access without ingress:

```bash
kubectl -n aida port-forward svc/frontend 8080:80
```

With ingress: edit `k8s/ingress.yaml` (host, TLS secret) and
`k8s/configmap.yaml` (`BACKEND_CORS_ORIGINS`) first.

### Architecture constraints — READ BEFORE SCALING

**The backend Deployment MUST stay at `replicas: 1` with `Recreate`.** Three
in-process singletons live in its lifespan: the agent worker pool (E3), the
engagement scheduler (E4), and the Telegram poller. A second replica would
double-fire engagements and race the pool. Scale the **frontend** Deployment
freely; if you need more backend throughput, shard by database.

### Pentest execution in k8s (DinD)

The backend pod carries a privileged Docker-in-Docker **native sidecar**
(`dind`); an init container boots `aida-pentest` inside that daemon and the
backend's `docker` CLI talks to `DOCKER_HOST=tcp://localhost:2375`.

- Images/workspaces live in an `emptyDir` — wiped on pod restart. Findings,
  evidence and reports are safe (Postgres is the system of record); pin a PVC
  to `dind-storage` if you need workspace continuity.
- Wrong arch / air-gapped cluster: put `docker save`-produced tarball on the
  node and enable the commented `preload` hostPath volume in `backend.yaml`.
- The scheduler/cron inside DinD follows pod lifetime — no cron engagements
  survive a deleted pod's workspace (they re-provision on the next run).

### Backups in k8s

```bash
kubectl apply -f k8s/backup-cronjob.yaml   # nightly pg_dump into a PVC, 7 kept
```

For real retention ship dumps off-cluster (restic/S3) — a PVC on the same
node is not a backup against node loss.

### Schema handling

There are no migration jobs: the backend provisions/patches its schema at
startup (`create_all` + `_ensure_columns`). Rollbacks to older images are
safe — added columns are ignored by older code.

---

## 3. Backup & restore (compose)

```bash
./scripts/backup.sh                          # prod stack → backups/aida-<ts>/
COMPOSE_FILE=docker-compose.yml ./scripts/backup.sh   # dev stack
./scripts/restore.sh backups/aida-<ts>       # DESTRUCTIVE: drops + restores
```

Each backup: `db.dump` (pg_dump custom format, sha256 in `manifest.txt`),
`evidence.tar`, metadata. Restore verifies the checksum first and asks you to
type the database name unless `--yes`.

---

## 4. Upgrade runbook (compose)

```bash
./scripts/backup.sh                                   # 1. backup
docker compose --env-file backend/.env -f docker-compose.prod.yml pull backend   # 2. new code
docker compose --env-file backend/.env -f docker-compose.prod.yml build frontend #    (frontend bakes at build)
docker compose --env-file backend/.env -f docker-compose.prod.yml up -d          # 3. recreate
curl -sf http://localhost:8000/health                # 4. verify
docker compose --env-file backend/.env -f docker-compose.prod.yml logs backend --tail 50
```

For the recurring-run/finding-lifecycle schema, also verify `alembic current`
(or the startup compatibility columns), exercise `/api/scan-profiles` with an
authenticated role, and run one explicitly authorized local-lab schedule before
enabling production engagements. See `RECURRING_SCAN_RUNS.md` for the data model
and smoke-test scope. Never use a production customer target as the smoke lab.

Rollback: re-pin the previous image tag (`BACKEND_IMAGE=...:v1.x`) and
`up -d`; restore the DB only if the new version wrote data you must undo.

k8s: `kubectl -n aida set image deploy/backend backend=<img>` (Recreate
strategy bounces the single pod), watch `kubectl -n aida rollout status
deploy/backend`.

---

## 5. Secrets checklist

- `backend/.env` and `k8s/secret.yaml` are gitignored — keep it that way.
- `SECRET_KEY` (JWT signing): fixed value, stored securely; rotating it
  invalidates all sessions.
- `POSTGRES_PASSWORD`: required; compose fails closed without it.
- LLM API keys, OIDC client secrets, Telegram tokens live in the DB
  (Fernet-encrypted at rest for SSO/OIDC secrets) — manage via Settings.
- Audit log (`/api/audit`, admin-only) records all privileged operations.
