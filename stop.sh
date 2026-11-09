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

# Stop host helper
if pkill -f "tools/helper.py" 2>/dev/null; then
    log "Stopped Host Helper"
fi
pkill -f "folder_opener.py" 2>/dev/null || true  # legacy name

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

# Detect active mode by container name (works for running AND stopped):
#   aida_caddy exists           → TLS prod
#   aida_frontend bound to 31337 → local prod
#   otherwise                    → dev
ALL_NAMES=$(docker ps -a --format "{{.Names}}" 2>/dev/null || true)

if echo "$ALL_NAMES" | grep -q "^aida_caddy$"; then
    log "TLS prod stack detected — stopping with prod + tls compose files..."
    STOP_FILES="-f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.tls.yml"
elif echo "$ALL_NAMES" | grep -q "^aida_frontend$" \
     && docker inspect aida_frontend --format '{{json .HostConfig.PortBindings}}' 2>/dev/null | grep -q "31337"; then
    log "Local prod stack detected — stopping with prod compose files..."
    STOP_FILES="-f docker-compose.yml -f docker-compose.prod.yml"
else
    STOP_FILES=""
fi

# Include custom Caddy port overrides if present
if [[ -f "$SCRIPT_DIR/.aida/docker-compose.caddy-reset.yml" && -f "$SCRIPT_DIR/.aida/docker-compose.caddy-ports.yml" ]]; then
    STOP_FILES="$STOP_FILES -f .aida/docker-compose.caddy-reset.yml -f .aida/docker-compose.caddy-ports.yml"
fi

log "Stopping $RUNNING container(s)..."
# Use 'stop' (not 'down') — containers are kept, volumes untouched, data safe
$COMPOSE_CMD $STOP_FILES stop

# Verify
echo ""
log "All containers stopped — data preserved"
$COMPOSE_CMD $STOP_FILES ps --format "table {{.Name}}\t{{.Status}}"
echo ""
log "To restart:      ./start.sh"
log "To restart LAN:  ./start.sh --lan"
log "To restart dev:  ./start.sh --dev"
echo ""
