# =============================================================================
# AIDA Agent Container
# The aida-pentest toolbox plus Claude Code, so the agent runs *inside* the
# sandbox instead of on the host. One container is created per assessment by
# `aida run <assessment>` (see aida.py).
#
# Published as vasco0x4/aida-agent (amd64 + arm64) by
# .github/workflows/docker-publish.yml, FROM the aida-pentest image of the
# same version; `aida run` downloads it and only builds this file as a
# fallback (or with --rebuild).
#
#   - Claude Code (npm) + Node.js
#   - tmux: the Claude session survives detach / terminal close
#   - non-root user `aida`, without sudo or any setuid binary: the agent
#     can't become root or change the system (`pip install --user` works)
#   - nmap gets the raw-socket capability, so SYN/OS scans work as `aida`
# =============================================================================
ARG BASE_IMAGE=vasco0x4/aida-pentest:latest
FROM ${BASE_IMAGE}

ARG NODE_MAJOR=22
ARG CLAUDE_CODE_VERSION=latest
# Match the host user's UID on Linux so files in the bind-mounted workspace
# stay owned by you (Docker Desktop / OrbStack on macOS remap this anyway).
ARG AIDA_UID=1000
ARG AIDA_GID=1000

ENV DEBIAN_FRONTEND=noninteractive

# -----------------------------------------------------------------------------
# 1. Node.js + agent tooling
# -----------------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
        tmux procps libcap2-bin ncurses-term \
    && curl -fsSL "https://deb.nodesource.com/setup_${NODE_MAJOR}.x" | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# -----------------------------------------------------------------------------
# 2. Claude Code — installed globally as root, so the in-app auto-updater
#    can't write there; rebuild the image to upgrade instead.
# -----------------------------------------------------------------------------
RUN npm install -g "@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}" \
    && npm cache clean --force

# -----------------------------------------------------------------------------
# 3. Non-root user
# -----------------------------------------------------------------------------
# The GID may already exist in the base image (e.g. a host group id passed
# through on Linux) — reuse it rather than failing.
RUN if ! getent group "${AIDA_GID}" >/dev/null; then groupadd -g "${AIDA_GID}" aida; fi \
    && useradd -m -u "${AIDA_UID}" -g "${AIDA_GID}" -s /bin/bash aida \
    && mkdir -p /home/aida/.claude /home/aida/.aida /workspace \
    && chown -R "aida:${AIDA_GID}" /home/aida /workspace
# `aida run` reads these to tell whether the agent user matches yours (Linux).
LABEL aida.uid="${AIDA_UID}" aida.gid="${AIDA_GID}"

# nmap needs raw sockets for SYN/OS scans. `aida run` starts the container
# with --cap-drop ALL --cap-add NET_RAW, so NET_RAW is the only capability
# a file can grant here (any user may already bind ports < 1024 in a
# container). This is also why the container doesn't use no-new-privileges:
# it makes the kernel ignore file capabilities, and SYN scans then fail.
RUN setcap cap_net_raw+eip "$(command -v nmap)"
ENV NMAP_PRIVILEGED=1
# Tools installed with `pip install --user` (there is no sudo).
ENV PATH=${PATH}:/home/aida/.local/bin

# -----------------------------------------------------------------------------
# 4. Launcher + tmux config
# -----------------------------------------------------------------------------
COPY aida-claude /usr/local/bin/aida-claude
COPY tmux.conf /etc/tmux.conf
RUN chmod 0755 /usr/local/bin/aida-claude

# Claude Code keeps credentials, settings and .claude.json under this dir.
# `aida run` mounts a volume of the assessment's own here
# (aida-agent-claude-<id>): logins, settings and conversations are never
# shared between assessments.
ENV CLAUDE_CONFIG_DIR=/home/aida/.claude
ENV DISABLE_AUTOUPDATER=1
ENV TERM=xterm-256color

# -----------------------------------------------------------------------------
# 5. Lock down: no setuid/setgid binaries (su, passwd, mount...), so nothing
#    in the container can switch to root. With --cap-drop ALL --cap-add
#    NET_RAW, no process here, root included, holds more than NET_RAW.
# -----------------------------------------------------------------------------
RUN find / -xdev -perm /6000 -type f -exec chmod a-s {} +
# `aida run` checks this to refuse images made for older, looser settings
# (sudo, nmap needing NET_ADMIN). Bump it with AGENT_SANDBOX_VERSION in aida.py.
LABEL aida.sandbox="2"

USER aida
WORKDIR /workspace

# Keep the container alive — Claude runs in a tmux session started by
# `docker exec`, and the backend's execute() tool also uses `docker exec`.
CMD ["sleep", "infinity"]
