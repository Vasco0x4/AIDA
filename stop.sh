#!/usr/bin/env bash
# ==============================================================================
# AIDA — stop the platform (same as `aida stop`). All data is kept.
# ==============================================================================

set -euo pipefail
# shellcheck source=scripts/common.sh
source "$(cd "$(dirname "$0")" && pwd)/scripts/common.sh"
cd "$AIDA_ROOT"

require_docker
detect_compose

section "Stopping AIDA"
# The dev overlay only changes existing services, so the main file is
# enough to stop either mode.
compose down --timeout 15 --remove-orphans
pkill -f "tools/helper.py" 2>/dev/null || true

echo
log "AIDA stopped. Assessments, findings and workspaces are kept."
hint "Start again with: aida start"
