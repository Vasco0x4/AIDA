#!/usr/bin/env bash
# ==============================================================================
# AIDA - Stop Services
# ==============================================================================
# Stops all AIDA containers. Data is preserved.
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

section "AIDA - Stopping Services"

# Stop folder opener
if pkill -f "folder_opener.py" 2>/dev/null; then
    log "Stopped Folder Opener"
fi

# Check current state
RUNNING=$($COMPOSE_CMD ps --status running -q 2>/dev/null | wc -l | tr -d ' ')
STOPPED=$($COMPOSE_CMD ps --status exited -q 2>/dev/null | wc -l | tr -d ' ')
TOTAL=$((RUNNING + STOPPED))

if [[ "$TOTAL" -eq 0 ]]; then
    warn "No AIDA containers found"
    echo ""
    echo "To start AIDA: ./start.sh"
    exit 0
fi

if [[ "$RUNNING" -eq 0 ]]; then
    warn "Containers already stopped"
    $COMPOSE_CMD ps --format "table {{.Name}}\t{{.Status}}"
    exit 0
fi

# Stop containers
log "Stopping $RUNNING container(s)..."
$COMPOSE_CMD stop

# Verify
echo ""
log "All containers stopped"
$COMPOSE_CMD ps --format "table {{.Name}}\t{{.Status}}"
echo ""
log "Data preserved. To restart: ./start.sh"
echo ""
