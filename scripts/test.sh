#!/usr/bin/env bash
# Local test entrypoint: lint + tests inside the dev backend container
# (pytest/ruff are baked in via the INSTALL_DEV=true build arg).
#
#   scripts/test.sh          # ruff + pytest
#   scripts/test.sh --fast   # pytest only
set -euo pipefail
cd "$(dirname "$0")/.."

if [ "${1:-}" = "--fast" ]; then
  CMD="pytest -q"
else
  CMD="ruff check . && pytest -q"
fi

docker compose exec -T backend sh -c "cd /app && PYTHONPATH=/app $CMD"
