# Backend Dockerfile - FastAPI (auto-detects dev/prod via ENVIRONMENT env var)
FROM python:3.11-slim

# Install system dependencies including Docker CLI and WeasyPrint libs
# Docker CLI is required for the ContainerService to run docker exec commands
# libpango, libcairo, libgdk-pixbuf are required by WeasyPrint for PDF generation
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    gnupg \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Install Docker CLI from official Docker repository
RUN install -m 0755 -d /etc/apt/keyrings && \
    curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc && \
    chmod a+r /etc/apt/keyrings/docker.asc && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian bookworm stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null && \
    apt-get update && \
    apt-get install -y --no-install-recommends docker-ce-cli && \
    rm -rf /var/lib/apt/lists/*

# Install Node.js 20 + Claude Code CLI — powers UI-initiated headless agent
# runs. Auth comes from CLAUDE_CODE_OAUTH_TOKEN env (generated once on the
# host via `claude setup-token`) so the Max subscription works from inside
# the container without access to the macOS Keychain.
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y --no-install-recommends nodejs util-linux && \
    npm install -g @anthropic-ai/claude-code && \
    npm cache clean --force && \
    rm -rf /var/lib/apt/lists/*

# Claude CLI refuses `--dangerously-skip-permissions` (our bypassPermissions
# mode) when invoked as root. uvicorn itself still needs root for the volume
# mounts, so we only drop privileges for the `claude` subprocess via a thin
# wrapper that re-execs under a dedicated non-root user. setpriv is used
# (not runuser) because runuser runs PAM session setup, which swallows the
# stdin/stdout pipes the SDK needs for its JSON protocol. HOME must be set
# explicitly so claude can write its session state under the new uid.
RUN useradd -u 1000 -m -s /bin/bash aida && \
    install -d -o aida -g aida /home/aida/.claude && \
    CLAUDE_REAL="$(readlink -f /usr/bin/claude)" && \
    mv "$CLAUDE_REAL" "${CLAUDE_REAL}.real" && \
    { \
      echo '#!/bin/sh'; \
      echo 'if [ "$(id -u)" = "0" ]; then'; \
      echo "  exec setpriv --reuid=1000 --regid=1000 --init-groups env HOME=/home/aida ${CLAUDE_REAL}.real \"\$@\""; \
      echo 'else'; \
      echo "  exec ${CLAUDE_REAL}.real \"\$@\""; \
      echo 'fi'; \
    } > "$CLAUDE_REAL" && \
    chmod +x "$CLAUDE_REAL"

# Set working directory
WORKDIR /app

# Copy requirements first for better layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
# Note: In development, this will be overridden by volume mount for hot reload
COPY . .

# Create logs directory
RUN mkdir -p logs

# Expose backend port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Production by default; --reload enabled only when ENVIRONMENT=development
ENV ENVIRONMENT=production
CMD ["sh", "-c", "\
  if [ \"$ENVIRONMENT\" = 'development' ]; then \
    exec uvicorn main:app --host 0.0.0.0 --port 8000 --reload; \
  else \
    exec uvicorn main:app --host 0.0.0.0 --port 8000; \
  fi"]
