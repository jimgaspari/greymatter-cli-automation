# CLI API (Greymatter Bootstrap API)

The **CLI API** is a FastAPI-based service that orchestrates Greymatter platform and tenant bootstrapping workflows by running controlled Kubernetes Jobs. It acts as a thin, auditable control plane around `greymatter` CLI operations and cluster-level provisioning.

This service is designed to:

* Safely execute privileged cluster operations via Kubernetes Jobs
* Bootstrap Greymatter **core** and **tenant** environments
* Perform post-deploy health validation (Prometheus targets)
* Manage required Kubernetes secrets and configuration artifacts

---

## High-level Architecture

```
Client
  │
  │  REST API
  ▼
CLI API (FastAPI)
  │
  │  Creates input Secret + Job
  ▼
Kubernetes Job (runner)
  │
  ├─ Runs greymatter CLI
  ├─ Applies manifests
  ├─ Creates secrets/services
  ├─ Waits for Prometheus readiness
  │
  └─ Writes result.json → Kubernetes Secret
```

### Key design choices

* **Out-of-process execution**: all real work happens in Kubernetes Jobs
* **Immutable results**: every run produces a persisted result Secret
* **Deterministic workflows**: no background state inside the API pod
* **Idempotent operations** wherever possible (`kubectl apply`)

---

## Deployment Model

* The API runs as a standard Kubernetes Deployment
* Workflow execution uses a **runner image** (typically the same image)
* Jobs run under a dedicated ServiceAccount with scoped RBAC

The API itself should be considered **control-plane only**; it does not mutate the cluster directly.

---

## Authentication

Authentication is enforced via a static API token.

### Header

```
X-API-Token: <token>
```

### Configuration

```
API_TOKEN=<token>
```

If `API_TOKEN` is unset, authentication is disabled (not recommended for production).

---

## Core Concepts

### Workflow

A **workflow** is a named operation executed by the runner:

* `bootstrap-core`
* `bootstrap-tenant`

### Run ID

Each workflow execution is assigned a **run ID**, which is used to:

* Track execution
* Fetch logs
* Retrieve results

### Steps

Workflows emit a list of **steps**, each with:

* `name`
* `returncode` (0 = success, 1 = failure)
* `stdout` / `stderr`
* Optional structured metadata

---

## API Endpoints

### Health

#### `GET /health`

Returns service health.

**Response**

```json
{"status": "ok"}
```

---

## Workflow APIs

### Bootstrap Core

#### `POST /api/workflows/bootstrap-core`

Bootstraps a Greymatter core platform.

This workflow:

* Ensures the Git repository exists
* Generates Greymatter platform configuration
* Applies Kubernetes manifests
* Creates required secrets and services
* Optionally creates edge ingress TLS secrets
* Waits for Prometheus targets to become healthy
* Persists a full result object

#### Request (simplified example)

```json
{
  "git": {
    "repo_url": "https://git.example.com/greymatter/core.git",
    "token": "<git-token>"
  },
  "create_platform": {
    "mesh_name": "greymatter",
    "image_repository": "oci.example.com"
  },
  "kubernetes": {
    "namespace": "greymatter",
    "image_pull": {
      "docker_username": "user",
      "docker_password": "pass"
    },
    "edge_ingress_tls_secret": {
      "enabled": true,
      "tls_crt": "-----BEGIN CERTIFICATE-----...",
      "tls_key": "-----BEGIN PRIVATE KEY-----..."
    }
  },
  "prometheus_check": {
    "enabled": true,
    "min_active_targets": 10,
    "require_all_up": true,
    "timeout_s": 600
  }
}
```

#### Response

Returns the full workflow result:

```json
{
  "returncode": 0,
  "workflow": "bootstrap-core",
  "steps": [ ... ],
  "result": {
    "platform_created": true
  }
}
```

---

### Bootstrap Tenant

#### `POST /api/workflows/bootstrap-tenant`

Bootstraps a Greymatter tenant.

Differences from core bootstrap:

* Operates within an existing Greymatter core
* Typically does not apply cluster-wide components
* Does not block on Prometheus readiness

#### Request

```json
{
  "tenant_name": "tenant-a",
  "namespace": "tenant-a",
  "git": { ... },
  "kubernetes": { ... }
}
```

---

## Prometheus Readiness Checks

The API can optionally block until Prometheus reports healthy targets.

### Behavior

* Polls `/api/v1/targets`
* Waits until `activeTargets >= min_active_targets`
* Requires **all active targets** to be `UP`
* Times out after `timeout_s`

### Why this exists

This ensures that Greymatter components are:

* Deployed
* Discoverable
* Actively scraped

before the workflow is considered successful.

---

## Kubernetes Resources Created

Depending on configuration, workflows may create:

* Namespaces
* Image pull secrets
* Repository secrets
* TLS secrets (`greymatter-edge-ingress`)
* ClusterIP Service for Prometheus
* Kubernetes Jobs (runner)

All resources are created using `kubectl apply` for idempotency.

---

## Result Persistence

Every workflow produces:

* `/outputs/result.json` (inside the job container)
* A Kubernetes Secret named:

```
cli-api-result-<run-id>
```

This allows results to be retrieved even after the job pod is gone.

---

## Failure Semantics

* Any step with `returncode != 0` fails the workflow
* Failures are **explicit** and **auditable**
* Partial progress is preserved in `steps[]`

The API never hides failures or retries silently.

---

## Security Considerations

* The runner ServiceAccount must be tightly scoped
* Treat the API token as a cluster-admin capability
* Secrets are never logged or returned in API responses

---

## Operational Guidance

### Logs

* API logs: API pod
* Workflow logs: Kubernetes Job pod

### Debugging a failed run

1. Fetch the result Secret
2. Inspect `steps[]`
3. Inspect job pod logs

---

## Non-goals

This API intentionally does **not**:

* Maintain long-lived state
* Retry failed workflows automatically
* Act as a general-purpose job runner

---

## Summary

This API provides a controlled, auditable mechanism to bootstrap and validate Greymatter environments using Kubernetes-native primitives.

It is intentionally opinionated, explicit, and fail-fast.
