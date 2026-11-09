# Mac mini operations

## Active deployment

- Source: `/path/to/AIDA`
- Compose project: `aida-prod`
- UI: `http://localhost:31337`
- Direct backend: `127.0.0.1:18080` on the Mac mini
- Services: frontend, backend, PostgreSQL, Docker socket proxy and production pentest container

The launch agent `com.aida.autostart` invokes `~/.aida-docker/autostart.sh`. It starts Colima and this production project at user login. It is a login agent, not a guarantee of service before any user logs in.

```sh
export PATH="$HOME/.aida-docker/bin:$HOME/.local/bin:$PATH"
cd /path/to/AIDA
docker compose -p aida-prod --env-file backend/.env -f docker-compose.prod.yml ps
docker compose -p aida-prod --env-file backend/.env -f docker-compose.prod.yml up -d
curl -f http://127.0.0.1:18080/health
```

The source edition's `./start.sh` now uses this production Compose file and preserves `backend/.env`. See [Quick Start](QUICK_START.md). Do not replace it with the old upstream launcher, which may create another project and conflicting ports. The removed AIDA and AIDA-dev source folders are not deployment targets.

## Backups and updates

Before changing images or source, save the current source manifest, environment file and PostgreSQL dump in a protected directory under `backups`. Include evidence volumes in the site's broader backup policy. A database dump alone is not a full evidence backup. Keep secrets and database backups off public repositories.

Build and test changes before changing image references. Update `BACKEND_IMAGE` and/or `FRONTEND_IMAGE` in `backend/.env`, then use Compose with `--wait`. Check health, login, Board, Scheduler and actual runner state. Do not enable the runner merely to verify a new UI.

The Kanban/UTC UI changes do not require a new database migration. Other changes may; inspect Alembic revisions and back up before applying them.

## Rollback

Restore `backend/.env` from the selected release backup and recreate the application containers:

```sh
docker compose -p aida-prod --env-file backend/.env -f docker-compose.prod.yml up -d --no-deps --wait backend frontend
```

Restore changed source files from the same backup before further development. Do not blindly restore a database dump over live data. Old images are retained for rollback. A source restore and an image restore are separate steps.

## Consolidation

Obsolete `aida` and `aida-dev` containers and source trees are removed only after inspecting mounts, networks and Compose labels. Shared `aida_prod_evidence` and `aida_prod_backend_logs` volumes are preserved. Old databases and source/configuration are archived before cleanup. Never use a broad `docker system prune --volumes` or `compose down -v` for this consolidation.

## Diagnostics

Inspect service health and recent backend logs. Distinguish a stopped runner, a paused schedule, an active overlapping run, provider authentication failure and an unhealthy container. Treat API errors as failures to investigate, not as empty successful results. For a stale browser after deployment, reload once; HTML is revalidated while hashed assets are cached.

Run backend tests against a separate test database. Frontend verification uses `npm test` and `npm run build`. Do not point destructive test fixtures at production.

## Building the interface

The UI uses same-origin `/api` by default. When building directly, use `VITE_API_URL=/api VITE_MCP_PORT=18080 npm run build` for this installation. Never embed a visitor-local `localhost:8000` API URL in a LAN build. After editing the canonical handbook files in `Docs`, run `npm run docs:sync` from `frontend` and commit the generated `src/guide-content` snapshots. This keeps the frontend-only Docker build context self-contained.
