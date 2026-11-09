#!/usr/bin/env bash
# ==============================================================================
# AIDA — backup
#
# Creates a timestamped backup directory containing:
#   db.dump      — full database dump (pg_dump custom format, compressed)
#   evidence.tar — evidence mirror (PoC videos / screenshots / submission PDFs;
#                  the DB already stores these as artifacts — this preserves
#                  the convenient on-disk copies)
#   manifest.txt — metadata (host, db, sizes, checksums)
#
# Usage:
#   ./scripts/backup.sh                          # prod stack (docker-compose.prod.yml)
#   ./scripts/backup.sh -f docker-compose.yml    # dev stack
#   AIDA_DB=mydb ./scripts/backup.sh             # non-default database
#
# Output: ./backups/aida-YYYYMMDD-HHMMSS/
# Restore with: ./scripts/restore.sh <backup-dir>
# ==============================================================================
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
while [[ $# -gt 0 ]]; do
    case $1 in
        -f|--file) COMPOSE_FILE="$2"; shift 2 ;;
        -h|--help) grep '^#' "$0" | sed '1,2d'; exit 0 ;;
        *) echo "unknown arg: $1" >&2; exit 1 ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"

# Compose interpolation source (POSTGRES_* values) — same convention as prod.
ENV_ARGS=()
[[ -f backend/.env ]] && ENV_ARGS=(--env-file backend/.env)

PGUSER="${POSTGRES_USER:-aida}"
PGDB="${AIDA_DB:-${POSTGRES_DB:-aida_assessments}}"
OUT="backups/aida-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$OUT"

PSQL() { docker compose "${ENV_ARGS[@]}" -f "$COMPOSE_FILE" exec -T postgres "$@"; }

echo "[*] Backup target: $PGDB @ $COMPOSE_FILE -> $OUT"

echo "[1/3] pg_dump (custom format)..."
PSQL pg_dump -U "$PGUSER" -Fc -d "$PGDB" > "$OUT/db.dump"
[[ -s "$OUT/db.dump" ]] || { echo "ERROR: db.dump is empty — aborting"; exit 1; }

echo "[2/3] evidence volume..."
# Evidence lives in the aida_evidence volume mounted at /evidence in the
# backend container (compose prod) — tar it from there. Dev stack has the
# host ./evidence dir instead.
if [[ "$COMPOSE_FILE" == "docker-compose.yml" && -d evidence ]]; then
    tar -cf "$OUT/evidence.tar" evidence
else
    BE_ID=$(docker compose "${ENV_ARGS[@]}" -f "$COMPOSE_FILE" ps -q backend)
    if [[ -n "$BE_ID" ]] && docker exec "$BE_ID" test -d /evidence; then
        docker exec "$BE_ID" tar -cf - -C /evidence . > "$OUT/evidence.tar"
    else
        echo "(no evidence found — skipping)"
    fi
fi

echo "[3/3] manifest..."
{
    echo "created=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "compose_file=$COMPOSE_FILE"
    echo "database=$PGDB"
    echo "db_dump_bytes=$(wc -c < "$OUT/db.dump" | tr -d ' ')"
    [[ -f "$OUT/evidence.tar" ]] && echo "evidence_tar_bytes=$(wc -c < "$OUT/evidence.tar" | tr -d ' ')"
    echo "db_dump_sha256=$(shasum -a 256 "$OUT/db.dump" | awk '{print $1}')"
} > "$OUT/manifest.txt"

cat "$OUT/manifest.txt"
echo "[✓] Backup complete: $OUT"
echo "    Verify before relying on it:  pg_restore --list $OUT/db.dump | head"
