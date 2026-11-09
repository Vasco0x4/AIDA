# Backend Dockerfile - FastAPI (auto-detects dev/prod via ENVIRONMENT env var)
FROM python:3.11-slim-bookworm

# Install system dependencies including Docker CLI and WeasyPrint libs
# Docker CLI is required for the ContainerService to run docker exec commands
# libpango, libcairo, libgdk-pixbuf are required by WeasyPrint for PDF generation
RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources && \
    apt-get update && \
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

# Set working directory
WORKDIR /app

# Copy requirements first for better layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Dev/test dependencies (pytest, ruff) — opt-in via build arg, keeps prod slim.
COPY requirements-dev.txt .
ARG INSTALL_DEV=false
RUN if [ "$INSTALL_DEV" = "true" ]; then \
      pip install --no-cache-dir -r requirements-dev.txt; \
    fi

# Dedicated non-root runtime user (E5 hardening). Fixed uid/gid so bind mounts
# and k8s fsGroup produce predictable ownership. The app never needs root: the
# Docker CLI talks to a TCP socket proxy / DinD sidecar, not the local socket.
RUN groupadd -g 10001 aida && useradd -u 10001 -g 10001 -m -s /bin/bash aida

# Copy application code
# Note: In development, this will be overridden by volume mount for hot reload
COPY --chown=aida:aida . .

# Writable runtime dirs (bind mounts override these in compose)
RUN mkdir -p logs /evidence && chown -R aida:aida /app/logs /evidence

# Expose backend port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run as the unprivileged user from here on (dev bind mounts override /app
# content but not the USER).
USER aida

# Production by default; --reload enabled only when ENVIRONMENT=development
ENV ENVIRONMENT=production
CMD ["sh", "-c", "\
  if [ \"$ENVIRONMENT\" = 'development' ]; then \
    exec uvicorn main:app --host 0.0.0.0 --port 8000 --reload; \
  else \
    exec uvicorn main:app --host 0.0.0.0 --port 8000; \
  fi"]
