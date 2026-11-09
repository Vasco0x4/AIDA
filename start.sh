#!/usr/bin/env bash
# Install this source edition. Existing configuration and data are preserved.
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
if [[ -x "$HOME/.aida-docker/bin/docker" ]]; then
    export PATH="$HOME/.aida-docker/bin:$PATH"
fi
BUILD=false
CHECK=false
while [[ $# -gt 0 ]]; do
    case "$1" in
        --build) BUILD=true ;;
        --check) CHECK=true ;;
        --help|-h)
            cat <<'HELP'
Usage: ./start.sh [--build | --check]

  ./start.sh          Create private configuration on first use, build missing
                      application images from this source, and start AIDA.
  ./start.sh --build  Rebuild backend and frontend after updating the source.
  ./start.sh --check  Check Docker/configuration without starting services.

Dashboard: http://localhost:31337
Requires running Docker Desktop, or Docker Engine with Compose v2.
On Windows use WSL2 or Git Bash. Host Python and Node are not required.
Existing backend/.env is kept. Complete first-admin setup in the browser.
For development, TLS and host execution, see Docs/QUICK_START.md.
HELP
            exit 0 ;;
        *) printf 'Unknown option: %s. Run ./start.sh --help.\n' "$1" >&2; exit 2 ;;
    esac
    shift
done
command -v docker >/dev/null 2>&1 || { echo 'Install and start Docker Desktop.' >&2; exit 1; }
docker info >/dev/null 2>&1 || { echo 'Docker is not running. Start Docker Desktop or your Docker daemon.' >&2; exit 1; }
docker compose version >/dev/null 2>&1 || { echo 'Docker Compose v2 is required.' >&2; exit 1; }
COMPOSE_HELP="$(docker compose up --help)"
[[ "$COMPOSE_HELP" == *--wait-timeout* ]] || { echo 'Update Compose: health-check waiting is required.' >&2; exit 1; }
if $CHECK; then
    if [[ -f backend/.env ]]; then
        docker compose --env-file backend/.env -f docker-compose.prod.yml config --quiet
        echo 'Docker and existing configuration are ready.'
    else
        echo 'Docker is ready. ./start.sh will create backend/.env on first startup.'
    fi
    exit 0
fi
if [[ ! -f backend/.env ]]; then
    echo 'Creating private local configuration...'
    if command -v python3 >/dev/null 2>&1; then
        python3 scripts/bootstrap_install.py
    else
        MSYS_NO_PATHCONV=1 docker run --rm -i --user "$(id -u):$(id -g)" \
            -e AIDA_PROJECT_NAME -e FRONTEND_PORT -e BACKEND_PORT \
            -v "$SCRIPT_DIR/backend:/bootstrap" \
            python:3.11-slim-bookworm python - /bootstrap < scripts/bootstrap_install.py
    fi
fi
COMPOSE=(docker compose --env-file backend/.env -f docker-compose.prod.yml)
"${COMPOSE[@]}" config --quiet
if ! $BUILD; then
    while IFS= read -r image; do
        [[ -z "$image" ]] && continue
        if ! docker image inspect "$image" >/dev/null 2>&1; then BUILD=true; break; fi
    done < <("${COMPOSE[@]}" config --images backend frontend)
fi
if $BUILD; then
    echo 'Building this edition from source (the first build can take several minutes)...'
    "${COMPOSE[@]}" build backend frontend
fi
echo 'Starting AIDA and waiting for service health...'
"${COMPOSE[@]}" up -d --no-build --wait --wait-timeout 240
ADDRESS="$("${COMPOSE[@]}" port frontend 8080)"
printf '\nAIDA is ready: http://%s\n' "$ADDRESS"
echo 'On a new installation, create your administrator account in the browser.'
echo 'After source updates, run ./start.sh --build. Configuration and data are kept.'
