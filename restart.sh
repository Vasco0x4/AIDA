#!/usr/bin/env bash
# ==============================================================================
# AIDA — restart the platform (same as `aida restart`). All data is kept.
# Options are passed to start.sh (e.g. --dev).
# ==============================================================================

set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
"$DIR/stop.sh"
exec "$DIR/start.sh" "$@"
