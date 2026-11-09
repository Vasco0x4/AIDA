# Install this edition

Prerequisites: running Docker Desktop, or Docker Engine with Docker Compose v2 supporting `up --wait-timeout`. Use a Bash terminal (macOS/Linux, WSL2 or Git Bash). Internet access is needed for the first build. Host Python and Node.js are not required for the dashboard.

Clone the repository containing this edition, then run:

```bash
git clone --branch feat/appsec-kanban-integrations https://github.com/kuffsit/AIDA.git
cd AIDA
./start.sh
```

Alternatively, extract the source archive and run the same commands. The original `Vasco0x4/AIDA` repository only supplies these changes after they have been published there; this source delivery does not publish to GitHub.

Open http://localhost:31337 and create the first administrator account. There is no preset administrator password on a fresh installation.

The launcher creates `backend/.env` with unique database and signing secrets, builds the backend and frontend from the included source, starts the execution container and waits for service health. The first build takes several minutes. Keep `.env` private and back it up alongside the database.

## Restart and update

```bash
./start.sh                 # Keep configuration and persistent data
./start.sh --check         # Validate prerequisites without starting services
./start.sh --build         # Rebuild after updating the source
```

Existing `backend/.env` files are preserved. Existing image names are respected; use `--build` to rebuild those images from updated source. Do not reuse one project's configuration for a second installation.

```bash
docker compose --env-file backend/.env -f docker-compose.prod.yml ps
docker compose --env-file backend/.env -f docker-compose.prod.yml logs --tail=100 backend
docker compose --env-file backend/.env -f docker-compose.prod.yml stop
```

Do not remove Docker volumes when updating: they contain assessments, evidence and workspaces. A startup failure returns a nonzero exit status; inspect the logs before retrying.

## Network and advanced modes

Fresh installations bind to loopback. For trusted LAN access, edit `FRONTEND_BIND=0.0.0.0` in `backend/.env`, add the browser origin to `BACKEND_CORS_ORIGINS`, and rerun `./start.sh`. Plain HTTP LAN access does not provide TLS. For TLS, configure `deploy/Caddyfile.example` and the Compose `tls` profile as described in the deployment runbook.

This edition's launcher supports `--build`, `--check` and `--help`. The upstream `--dev`, `--lan`, `--domain` and `--localhost` flags are not supported by this launcher. Development Compose and host execution are separate advanced configurations, not part of this verified default installation.

## Launch an AI client

Install the desired AI CLI and Python dependencies described in the agent documentation, then launch from the source directory:

```bash
python3 aida.py --assessment "target-corp" --cli auto
```

Only scan systems within your authorized assessment scope. Starting the dashboard itself does not launch a scan.
