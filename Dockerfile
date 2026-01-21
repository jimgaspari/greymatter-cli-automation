FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl ca-certificates tini openssh-client \
    && rm -rf /var/lib/apt/lists/*

ARG KUBECTL_VERSION=v1.29.0
RUN curl -fsSL -o /usr/local/bin/kubectl \
    "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/amd64/kubectl" \
    && chmod +x /usr/local/bin/kubectl

COPY bin/greymatter /usr/local/bin/greymatter

RUN useradd -m -u 10001 appuser \
    && mkdir -p /app /work \
    && chown -R appuser:appuser /app /work

ENV WORKDIR=/work
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Copy project files INCLUDING src/
COPY pyproject.toml README.md /app/
COPY src/ /app/src/

RUN pip install --no-cache-dir -U pip \
    && pip install --no-cache-dir .

USER appuser

EXPOSE 8080
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["uvicorn", "cli_api.app:app", "--host", "0.0.0.0", "--port", "8080"]
