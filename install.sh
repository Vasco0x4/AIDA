#!/usr/bin/env bash
# ==============================================================================
# AIDA installer
#
#   curl -fsSL https://raw.githubusercontent.com/Vasco0x4/AIDA/main/install.sh | bash
#
# Downloads AIDA into ~/AIDA, installs the `aida` command and starts the
# platform. Running it again updates an existing install.
#
# Needs: git and Docker (Docker Desktop or OrbStack on macOS).
#
# Options, as environment variables (put them before `bash`):
#   AIDA_DIR=~/tools/AIDA   where to install          (default: ~/AIDA)
#   AIDA_BRANCH=dev         which branch to install   (default: main)
#   AIDA_PORT=8443          web UI port               (default: 31337)
# ==============================================================================

# Everything is inside main() so a download cut halfway never runs a partial
# script.
main() {
    set -euo pipefail

    local repo="${AIDA_REPO:-https://github.com/Vasco0x4/AIDA.git}"
    local branch="${AIDA_BRANCH:-main}"
    local dir="${AIDA_DIR:-$HOME/AIDA}"

    local bold="" red="" green="" yellow="" dim="" nc=""
    if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
        bold=$'\033[1m'; red=$'\033[0;31m'; green=$'\033[0;32m'
        yellow=$'\033[1;33m'; dim=$'\033[2m'; nc=$'\033[0m'
    fi
    say()  { echo "${green}✓${nc} $*"; }
    note() { echo "${yellow}!${nc} $*"; }
    fail() {
        echo "${red}✗${nc} $1" >&2; shift
        for h in "$@"; do echo "  ${dim}→${nc} $h" >&2; done
        exit 1
    }

    echo
    echo "${bold}AIDA installer${nc} ${dim}— AI-Driven Security Assessment${nc}"
    echo

    # --- System -----------------------------------------------------------
    local os
    os=$(uname -s)
    case "$os" in
        Darwin|Linux) ;;
        MINGW*|MSYS*|CYGWIN*)
            fail "Windows is supported through WSL 2." \
                 "Install WSL (https://learn.microsoft.com/windows/wsl/install) and Docker Desktop with WSL integration, then run this command in your WSL terminal." ;;
        *) fail "Unsupported system: $os" ;;
    esac

    # --- git ----------------------------------------------------------------
    if ! command -v git >/dev/null 2>&1; then
        if [[ "$os" == Darwin ]]; then
            fail "git is not installed." "Run: xcode-select --install   (then run this installer again)"
        fi
        fail "git is not installed." "Debian/Ubuntu/Kali: sudo apt install git   ·   Fedora: sudo dnf install git   ·   Arch: sudo pacman -S git"
    fi

    # --- Docker -------------------------------------------------------------
    if ! command -v docker >/dev/null 2>&1; then
        if [[ "$os" == Darwin ]]; then
            fail "Docker is not installed." \
                 "Install Docker Desktop (https://www.docker.com/products/docker-desktop/) or OrbStack (https://orbstack.dev)," \
                 "start it, then run this installer again."
        fi
        fail "Docker is not installed." \
             "Install it: curl -fsSL https://get.docker.com | sudo sh" \
             "Allow your user: sudo usermod -aG docker \$USER, log out and back in, then run this installer again."
    fi

    local docker_out
    if ! docker_out=$(docker info 2>&1); then
        if echo "$docker_out" | grep -qi "permission denied"; then
            fail "Your user is not allowed to use Docker." \
                 "Run: sudo usermod -aG docker \$USER, log out and back in, then run this installer again."
        fi
        if [[ "$os" == Darwin ]]; then
            # Start the Docker app if we can find one, and wait for it.
            local app=""
            [[ -d /Applications/OrbStack.app ]] && app=OrbStack
            [[ -z "$app" && -d /Applications/Docker.app ]] && app=Docker
            if [[ -n "$app" ]]; then
                echo "  Starting $app..."
                open -a "$app"
                for _ in $(seq 1 90); do
                    docker info >/dev/null 2>&1 && break
                    sleep 2
                done
            fi
            docker info >/dev/null 2>&1 \
                || fail "Docker is not running." "Open Docker Desktop (or OrbStack), wait until it is running, then run this installer again."
        else
            fail "Docker is not running." "Start it: sudo systemctl start docker   (then run this installer again)"
        fi
    fi
    if ! docker compose version >/dev/null 2>&1; then
        fail "Docker Compose v2 is missing." \
             "Docker Desktop and OrbStack include it. On Linux: sudo apt install docker-compose-plugin (or your distro's equivalent)."
    fi
    say "Docker $(docker version --format '{{.Server.Version}}' 2>/dev/null) is ready"

    # --- Download / update ----------------------------------------------------
    if [[ -d "$dir/.git" ]]; then
        say "AIDA is already in $dir — updating"
        if [[ -z "$(git -C "$dir" symbolic-ref -q HEAD || true)" ]]; then
            note "Not on a branch — keeping the code as it is."
        elif [[ -n "$(git -C "$dir" status --porcelain --untracked-files=no)" ]]; then
            note "Local changes in $dir — keeping the code as it is."
        elif ! git -C "$dir" pull --ff-only --quiet; then
            note "Could not update the code (git pull failed) — keeping the current version."
        fi
        rm -f "$dir/.aida/last-pull"   # also refresh the images
    elif [[ -e "$dir" && -n "$(ls -A "$dir" 2>/dev/null)" ]]; then
        fail "$dir already exists and is not an AIDA install." \
             "Move it away, or install somewhere else: curl -fsSL https://raw.githubusercontent.com/Vasco0x4/AIDA/main/install.sh | AIDA_DIR=~/somewhere/AIDA bash"
    else
        echo "  Downloading AIDA into $dir..."
        git clone --quiet --depth 1 --branch "$branch" "$repo" "$dir" \
            || fail "Could not download AIDA from $repo." "Check your internet connection and try again."
        say "Downloaded AIDA into $dir"
    fi

    # --- The `aida` command -----------------------------------------------------
    # Link it into the first writable directory that is already in PATH.
    local bin_dir="" candidate
    for candidate in "$HOME/.local/bin" "$HOME/bin" /usr/local/bin /opt/homebrew/bin; do
        case ":$PATH:" in *":$candidate:"*) ;; *) continue ;; esac
        if [[ -d "$candidate" && -w "$candidate" ]]; then bin_dir=$candidate; break; fi
    done
    local path_hint=false
    if [[ -z "$bin_dir" ]]; then
        bin_dir="$HOME/.local/bin"
        mkdir -p "$bin_dir"
        path_hint=true
    fi
    ln -sf "$dir/aida" "$bin_dir/aida"
    say "Installed the ${bold}aida${nc} command in $bin_dir"

    # --- Start ----------------------------------------------------------------
    # stdin is this script when piped from curl: keep start.sh off it.
    "$dir/start.sh" </dev/null

    if $path_hint; then
        local rc="$HOME/.profile"
        case "${SHELL:-}" in
            */zsh)  rc="$HOME/.zshrc" ;;
            */bash) rc="$HOME/.bashrc" ;;
        esac
        note "To use the ${bold}aida${nc} command, add $bin_dir to your PATH:"
        echo "    echo 'export PATH=\"$bin_dir:\$PATH\"' >> $rc && source $rc"
        echo
    fi
}

main "$@"
