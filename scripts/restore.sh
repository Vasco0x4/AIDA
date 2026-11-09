#!/usr/bin/env bash
# ==============================================================================
# AIDA — restore
#
# Restores a backup created by scripts/backup.sh into the target stack's
# Postgres. DESTRUCTIVE: drops and recreates the target database.
#
# Usage:
#   ./scripts/restore.sh backups/aida-20260818-120000
#   ./scripts/restore.sh --yes backups/aida-...      # skip confirmation
#   AIDA_DB=mydb ./scripts/restore.sh <dir>          # restore into other db
#
# The backend is NOT stopped (schema objects are dropped and recreated under
# it; open connections may block DROP DATABASE — stop the backend first if
# that happens:  docker compose -f docker-compose.prod.yml stop backend)
# ==============================================================================
set -euo pipefail

ASSUME_YES=false
ARGS=()
while [[ $# -gt 0 ]]; do
    case $1 in
        --yes|-y) ASSUME_YES=true; shift ;;
        *) ARGS+=("$1"); shift ;;
    esac
done
[[ ${#ARGS[@]} -eq 1 ]] || { echo "usage: $0 [--yes] <backup-dir>" >&2; exit 1; }
BACKUP_DIR="${ARGS[0]}"

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"

ENV_ARGS=()
[[ -f backend/.env ]] && ENV_ARGS=(--env-file backend/.env)

PGUSER="${POSTGRES_USER:-aida}"
PGDB="${AIDA_DB:-${POSTGRES_DB:-aida_assessments}}"
DUMP="$BACKUP_DIR/db.dump"

[[ -f "$DUMP" ]] || { echo "ERROR: $DUMP not found"; exit 1; }

# Integrity check first, if the manifest is present.
if [[ -f "$BACKUP_DIR/manifest.txt" ]]; then
    EXPECTED=$(grep '^db_dump_sha256=' "$BACKUP_DIR/manifest.txt" | cut -d= -f2)
    ACTUAL=$(shasum -a 256 "$DUMP" | awk '{print $1}')
    [[ "$EXPECTED" == "$ACTUAL" ]] || { echo "ERROR: checksum mismatch — dump corrupted"; exit 1; }
    echo "[✓] checksum ok"
fi

if [[ "$ASSUME_YES" != true ]]; then
    echo "About to DROP and RESTORE database '$PGDB' in $COMPOSE_FILE"
    echo "from $DUMP ($(wc -c < "$DUMP" | tr -d ' ') bytes). This cannot be undone."
    read -rp "Type the database name to confirm: " CONFIRM
    [[ "$CONFIRM" == "$PGDB" ]] || { echo "aborted"; exit 1; }
fi

PSQL() { docker compose "${ENV_ARGS[@]}" -f "$COMPOSE_FILE" exec -T postgres "$@"; }

echo "[1/3] recreating database $PGDB..."
PSQL psql -U "$PGUSER" -d postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='$PGDB' AND pid<>pg_backend_pid();" >/dev/null
PSQL psql -U "$PGUSER" -d postgres -c "DROP DATABASE IF EXISTS $PGDB;"
PSQL psql -U "$PGUSER" -d postgres -c "CREATE DATABASE $PGDB;"

echo "[2/3] pg_restore..."
# Stream the dump into the container via stdin — the host path is not
# visible inside the postgres container.
PSQL pg_restore -U "$PGUSER" -d "$PGDB" --no-owner < "$DUMP"

echo "[3/3] done. Restart the backend to clear its connection pool:"
echo "    docker compose -f $COMPOSE_FILE restart backend"
[[ -f "$BACKUP_DIR/evidence.tar" ]] && echo "(evidence.tar present — extract it into the evidence volume/host dir manually if needed)"
