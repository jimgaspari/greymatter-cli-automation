# syntax=docker/dockerfile:1.6
FROM python:3.12-slim

# ---- OS deps: git, curl, ca-certs (kubectl download), tini (optional but good) ----
RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl ca-certificates tini \
    && rm -rf /var/lib/apt/lists/*

# ---- kubectl (pin the version; override at build time with --build-arg) ----
ARG KUBECTL_VERSION=v1.29.0
RUN curl -fsSL -o /usr/local/bin/kubectl \
    "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/amd64/kubectl" \
    && chmod +x /usr/local/bin/kubectl \
    && kubectl version --client=true --short || true

# ---- Greymatter CLI install ----
# You MUST replace ONE of the options below with your real install method.
#
# Option A: Copy a prebuilt greymatter binary from your repo:
#   COPY greymatter /usr/local/bin/greymatter
#   RUN chmod +x /usr/local/bin/greymatter
#
# Option B: Download from an internal URL/artifact registry:
#   ARG GM_CLI_URL
#   RUN curl -fsSL "$GM_CLI_URL" -o /usr/local/bin/greymatter && chmod +x /usr/local/bin/greymatter
#
# Option C: Install from pip (ONLY if Greymatter CLI is actually distributed that way):
#   RUN pip install --no-cache-dir greymatter-cli

# ---- Create non-root user + directories ----
RUN useradd -m -u 10001 appuser \
    && mkdir -p /app /work \
    && chown -R appuser:appuser /app /work

ENV WORKDIR=/work
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# ---- Install Python deps from pyproject.toml ----
# Copy only packaging files first for better Docker layer caching.
COPY pyproject.toml README.md /app/

# If you have a lockfile, copy it too (recommended):
# - uv: uv.lock
# - poetry: poetry.lock
# - pdm: pdm.lock
# COPY uv.lock /app/

RUN pip install --no-cache-dir -U pip \
    && pip install --no-cache-dir .

# ---- Copy the rest of the app code ----
COPY src/ /app/src/

# Re-install in editable? No—containers should be immutable.
# Install the package again now that src/ is present.
RUN pip install --no-cache-dir .

# ---- Drop privileges ----
USER appuser

EXPOSE 8080

# tini helps reap zombie processes when running subprocesses
ENTRYPOINT ["/usr/bin/tini", "--"]

# Production server command
CMD ["uvicorn", "cli_api.app:app", "--host", "0.0.0.0", "--port", "8080"]
