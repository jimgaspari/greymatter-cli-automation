# cli_api/kubernetes/input_secrets.py

from __future__ import annotations

import base64
import json
import re
from typing import Any, Dict, Optional

from ..runner import run_cmd


def _dns1123(name: str, max_len: int = 63) -> str:
    name = name.lower()
    name = re.sub(r"[^a-z0-9-]+", "-", name).strip("-")
    if not name:
        name = "run"
    return name[:max_len].rstrip("-")


def _b64(s: str) -> str:
    return base64.b64encode(s.encode("utf-8")).decode("ascii")


def create_run_input_secret(
    *,
    jobs_namespace: str,
    run_id: str,
    request_obj: Dict[str, Any],
    secret_name: Optional[str] = None,
    labels: Optional[Dict[str, str]] = None,
    annotations: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Create/Update a Secret containing the request payload as /inputs/request.json
    (mounted by the Job).

    - Stored as Secret "data" (base64).
    - Key: request.json
    """
    if secret_name is None:
        secret_name = _dns1123(f"cli-api-run-{run_id}")

    if labels is None:
        labels = {}
    if annotations is None:
        annotations = {}

    labels = {
        "app": "cli-api",
        "cli-api-run-id": run_id,
        **labels,
    }

    # Keep JSON stable/compact; you can pretty-print if you prefer.
    request_json = json.dumps(request_obj, ensure_ascii=False)

    secret_manifest: Dict[str, Any] = {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {
            "name": secret_name,
            "namespace": jobs_namespace,
            "labels": labels,
            "annotations": annotations,
        },
        "type": "Opaque",
        "data": {
            # mounted by jobs.py via items->key "request.json"
            "request.json": _b64(request_json),
        },
    }

    applied = run_cmd(
        ["kubectl", "apply", "-f", "-"],
        input=json.dumps(secret_manifest, separators=(",", ":"), ensure_ascii=False),
        timeout_s=30,
        check=False,
    )
    applied["secret_name"] = secret_name
    applied["namespace"] = jobs_namespace
    return applied


def delete_run_input_secret(
    *,
    jobs_namespace: str,
    secret_name: str,
) -> Dict[str, Any]:
    return run_cmd(
        ["kubectl", "-n", jobs_namespace, "delete", "secret", secret_name, "--ignore-not-found=true"],
        timeout_s=30,
        check=False,
    )
