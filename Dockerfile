# syntax=docker/dockerfile:1.7

############################
# Builder stage
############################
FROM python:3.12-slim AS builder

# Fail fast; no interactive apt
SHELL ["/bin/bash", "-euo", "pipefail", "-c"]
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Minimal build deps only in builder (no need to ship them)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    ca-certificates curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy only what is needed to resolve/install deps first (better cache behavior)
COPY pyproject.toml README.md /app/
COPY src/ /app/src/

# Create a virtualenv for a clean runtime boundary
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir -U pip \
    && /opt/venv/bin/pip install --no-cache-dir .

############################
# Runtime stage
############################
FROM python:3.12-slim AS runtime

SHELL ["/bin/bash", "-euo", "pipefail", "-c"]
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    WORKDIR=/work \
    PATH="/opt/venv/bin:$PATH"

# Install only what you truly need at runtime.
# - tini: proper signal handling
# - ca-certificates: TLS
# (drop git/ssh-client/curl from runtime unless your app explicitly needs them)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    ca-certificates tini \
    git openssh-client \
    && rm -rf /var/lib/apt/lists/*

# Create a locked-down user (no password, no shell)
RUN groupadd -g 10001 appuser \
    && useradd  -u 10001 -g 10001 -m -d /home/appuser -s /usr/sbin/nologin appuser

# App directories with least-privilege ownership
RUN mkdir -p /app /work \
    && chown -R 10001:10001 /app /work \
    && chmod 0755 /app /work

WORKDIR /app

# Copy venv + app code from builder (no compilers/curl in final image)
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app /app

# Copy your CLI binary with restrictive perms
COPY --chmod=0755 bin/greymatter /usr/local/bin/greymatter

# Download kubectl in runtime (or vendor it in your repo); verify integrity.
# If you can vendor kubectl internally, do that instead (best for air-gapped/secure envs).
ARG KUBECTL_VERSION=v1.29.0
ARG TARGETARCH=amd64
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && curl -fsSLo /usr/local/bin/kubectl "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/${TARGETARCH}/kubectl" \
    && curl -fsSLo /tmp/kubectl.sha256 "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/${TARGETARCH}/kubectl.sha256" \
    && echo "$(cat /tmp/kubectl.sha256)  /usr/local/bin/kubectl" | sha256sum -c - \
    && rm -f /tmp/kubectl.sha256 \
    && chmod 0755 /usr/local/bin/kubectl \
    && apt-get purge -y --auto-remove curl

# Optional but common hardening: avoid running as root
USER 10001:10001

EXPOSE 8080

# Healthcheck is helpful for orchestration (tune path/timeouts)
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health').read()" || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["uvicorn", "cli_api.app:app", "--host", "0.0.0.0", "--port", "8080"]
