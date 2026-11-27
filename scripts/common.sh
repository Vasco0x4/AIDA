# shellcheck shell=bash
# Shared helpers for AIDA's shell entry points (aida, start.sh, stop.sh,
# restart.sh). Source it, don't run it.

AIDA_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AIDA_STATE_DIR="$AIDA_ROOT/.aida"
# Web UI port: AIDA_PORT if set, else the one remembered by the last
# `AIDA_PORT=... aida start`, else 31337.
AIDA_PORT="${AIDA_PORT:-$(cat "$AIDA_STATE_DIR/port" 2>/dev/null || echo 31337)}"
AIDA_SETUP_CODE_FILE="$AIDA_STATE_DIR/setup-code"
AIDA_BACKEND_URL="http://127.0.0.1:8000"

# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
    RED=$'\033[0;31m'; GREEN=$'\033[0;32m'; YELLOW=$'\033[1;33m'
    BLUE=$'\033[0;34m'; BOLD=$'\033[1m'; DIM=$'\033[2m'; NC=$'\033[0m'
else
    RED=""; GREEN=""; YELLOW=""; BLUE=""; BOLD=""; DIM=""; NC=""
fi

log()     { echo "${GREEN}✓${NC} $*"; }
warn()    { echo "${YELLOW}!${NC} $*"; }
error()   { echo "${RED}✗${NC} $*" >&2; }
hint()    { echo "  ${DIM}→${NC} $*"; }
section() { echo; echo "${BOLD}${BLUE}==>${NC} ${BOLD}$*${NC}"; }
die()     { error "$1"; shift; for h in "$@"; do hint "$h"; done; exit 1; }

# ---------------------------------------------------------------------------
# Docker
# ---------------------------------------------------------------------------

# Exits with an explanation if Docker is missing or not running.
require_docker() {
    if ! command -v docker >/dev/null 2>&1; then
        case "$(uname -s)" in
            Darwin) die "Docker is not installed." \
                "Install Docker Desktop (https://www.docker.com/products/docker-desktop/) or OrbStack (https://orbstack.dev), start it, then run this again." ;;
            *)      die "Docker is not installed." \
                "Install it with: curl -fsSL https://get.docker.com | sudo sh" \
                "Then let your user run it: sudo usermod -aG docker \$USER (and log out / back in)." ;;
        esac
    fi

    local out
    if ! out=$(docker info 2>&1); then
        if echo "$out" | grep -qi "permission denied"; then
            die "Your user is not allowed to use Docker." \
                "Run: sudo usermod -aG docker \$USER, then log out and back in."
        fi
        case "$(uname -s)" in
            Darwin) die "Docker is installed but not running." \
                "Open Docker Desktop (or OrbStack), wait until it says it is running, then run this again." ;;
            *)      die "Docker is installed but not running." \
                "Start it with: sudo systemctl start docker" ;;
        esac
    fi
}

# Sets COMPOSE to the Compose v2 command (array). AIDA needs v2.
detect_compose() {
    if docker compose version >/dev/null 2>&1; then
        COMPOSE_BIN=(docker compose)
    elif command -v docker-compose >/dev/null 2>&1 \
        && docker-compose version --short 2>/dev/null | grep -qE '^v?2\.'; then
        COMPOSE_BIN=(docker-compose)
    else
        die "Docker Compose v2 is missing." \
            "Docker Desktop and OrbStack include it. On Linux: sudo apt install docker-compose-plugin (or your distro's equivalent)."
    fi
    COMPOSE=("${COMPOSE_BIN[@]}" --project-directory "$AIDA_ROOT" -f "$AIDA_ROOT/docker-compose.yml")
}

# Runs docker compose on the main stack: compose ps, compose logs, ...
compose() { "${COMPOSE[@]}" "$@"; }

container_state() {
    docker inspect -f '{{.State.Status}}' "$1" 2>/dev/null || true
}

container_health() {
    docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$1" 2>/dev/null || true
}

# Prints the name of the process listening on a TCP port, unless it is a
# Docker runtime forwarding a container port (that's us, or another stack).
port_owner() {
    local port=$1 proc=""
    if command -v lsof >/dev/null 2>&1; then
        proc=$(lsof -nP -iTCP:"$port" -sTCP:LISTEN 2>/dev/null | awk 'NR==2 {print $1}')
    elif command -v ss >/dev/null 2>&1; then
        proc=$(ss -tlnpH "sport = :$port" 2>/dev/null | sed -n 's/.*users:(("\([^"]*\)".*/\1/p' | head -1)
    fi
    if [[ -n "$proc" ]] && ! echo "$proc" | grep -qiE 'orbstack|com\.docke|docker|vpnkit|rootlessk'; then
        echo "$proc"
    fi
}

# ---------------------------------------------------------------------------
# Network / platform state
# ---------------------------------------------------------------------------

# Best-effort LAN IP of this machine (empty if none found).
lan_ip() {
    local ip=""
    if command -v ipconfig >/dev/null 2>&1; then          # macOS
        for iface in en0 en1 en2 en3; do
            ip=$(ipconfig getifaddr "$iface" 2>/dev/null || true)
            [[ -n "$ip" ]] && { echo "$ip"; return; }
        done
    fi
    if command -v ip >/dev/null 2>&1; then                # Linux
        ip=$(ip -4 route get 1.1.1.1 2>/dev/null | sed -n 's/.* src \([0-9.]*\).*/\1/p' | head -1)
        [[ -n "$ip" ]] && { echo "$ip"; return; }
    fi
    hostname -I 2>/dev/null | awk '{print $1}' || true
}

# "true" / "false" / "" (backend unreachable).
setup_required() {
    local body
    body=$(curl -fsS --max-time 5 "$AIDA_BACKEND_URL/api/auth/setup-status" 2>/dev/null) || return 0
    if echo "$body" | grep -q '"setup_required": *true'; then echo true; else echo false; fi
}

# Waits until a command succeeds. Usage: wait_until <seconds> <cmd...>
wait_until() {
    local timeout=$1; shift
    local i=0
    until "$@" >/dev/null 2>&1; do
        i=$((i + 1))
        [[ $i -ge $timeout ]] && return 1
        sleep 1
    done
}

# Prints the URLs where the web UI can be reached.
print_urls() {
    local ip
    ip=$(lan_ip)
    echo "  Web UI     ${BOLD}https://localhost:${AIDA_PORT}${NC}"
    if [[ -n "$ip" && "${AIDA_BIND:-0.0.0.0}" == "0.0.0.0" ]]; then
        echo "  Network    https://${ip}:${AIDA_PORT}"
    fi
}

# Prints the setup code block while the first admin account doesn't exist.
# $1: web UI address (default: the HTTPS one).
print_setup_code() {
    [[ "$(setup_required)" == "true" && -f "$AIDA_SETUP_CODE_FILE" ]] || return 0
    local code ui="${1:-https://localhost:${AIDA_PORT}}"
    code=$(cat "$AIDA_SETUP_CODE_FILE")
    echo
    echo "  Setup code ${BOLD}${YELLOW}${code}${NC}   (asked when you create the admin account)"
    echo "  ${DIM}Or open ${ui}/#code=${code} to have it filled in.${NC}"
}
