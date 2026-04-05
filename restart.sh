#!/usr/bin/env bash
# ==============================================================================
# AIDA - Restart Services
# ==============================================================================
# Restarts all containers and waits for them to be healthy.
# ==============================================================================

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log()     { echo -e "${GREEN}[✓]${NC} $*"; }
warn()    { echo -e "${YELLOW}[!]${NC} $*"; }
error()   { echo -e "${RED}[✗]${NC} $*"; }
section() { echo -e "\n${BLUE}══════════════════════════════════════${NC}\n${BLUE}  $*${NC}\n${BLUE}══════════════════════════════════════${NC}"; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Docker Compose: prefer plugin, fallback to standalone (Kali)
if docker compose version &>/dev/null; then
    COMPOSE_CMD="docker compose"
elif command -v docker-compose &>/dev/null; then
    COMPOSE_CMD="docker-compose"
else
    COMPOSE_CMD="docker compose"
fi

section "AIDA - Restarting Services"

# Check if containers exist at all
RUNNING=$($COMPOSE_CMD ps --status running -q 2>/dev/null | wc -l | tr -d ' ')
STOPPED=$($COMPOSE_CMD ps --status exited -q 2>/dev/null | wc -l | tr -d ' ')
TOTAL=$((RUNNING + STOPPED))

if [[ "$TOTAL" -eq 0 ]]; then
    warn "No AIDA containers found"
    echo ""
    echo "Use ./start.sh to start AIDA for the first time"
    exit 1
fi

# Restart folder opener
pkill -f "folder_opener.py" 2>/dev/null || true
if [[ -f "$SCRIPT_DIR/tools/folder_opener.py" ]]; then
    python3 "$SCRIPT_DIR/tools/folder_opener.py" &>/dev/null &
    log "Restarted Folder Opener"
fi

# Restart containers
log "Restarting containers..."
$COMPOSE_CMD restart

# Wait for services
section "Waiting for Services"

wait_for_service() {
    local name=$1
    local check_cmd=$2
    local max_wait=${3:-30}
    local i=0

    printf "  %-12s " "$name..."
    while ! eval "$check_cmd" &>/dev/null; do
        ((i++))
        if [[ $i -ge $max_wait ]]; then
            echo -e "${RED}TIMEOUT${NC}"
            return 1
        fi
        sleep 1
    done
    echo -e "${GREEN}Ready${NC}"
}

wait_for_service "PostgreSQL" "$COMPOSE_CMD exec -T postgres pg_isready -U aida"
wait_for_service "Backend" "curl -sf http://localhost:8001/health"
wait_for_service "Frontend" "curl -sf http://localhost:5174"

# Success
section "AIDA Restarted"

echo ""
$COMPOSE_CMD ps --format "table {{.Name}}\t{{.Status}}"
echo ""
log "Frontend:  http://localhost:5174"
log "Backend:   http://localhost:8001"
echo ""
