from __future__ import annotations

import json
from typing import Dict, Any, Optional

from cli_api.runner import run_cmd


def apply_service(
    *,
    namespace: str,
    name: str,
    port: int,
    target_port: int,
    selector: Dict[str, str],
    service_type: str = "ClusterIP",
) -> Dict[str, Any]:
    """
    Idempotently creates/updates a Service via `kubectl apply -f -`.
    """
    manifest: Dict[str, Any] = {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {
            "name": name,
            "namespace": namespace,
            "labels": {
                "app": "cli-api",
                "cli-api.greymatter.io/kind": "bootstrap",
            },
        },
        "spec": {
            "type": service_type,
            "ports": [
                {
                    "protocol": "TCP",
                    "port": port,
                    "targetPort": target_port,
                }
            ],
            "selector": selector,
        },
    }

    return run_cmd(
        ["kubectl", "apply", "-f", "-"],
        input=json.dumps(manifest),
        check=False,
        timeout_s=30,
    )


def ensure_prometheus_service(
    *,
    namespace: str,
    name: str = "prometheus",
    port: int = 9090,
    target_port: int = 9090,
    selector: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Creates a ClusterIP service named 'prometheus' pointing at pods with label app=prometheus by default.
    """
    selector = selector or {"app": "prometheus"}
    return apply_service(
        namespace=namespace,
        name=name,
        port=port,
        target_port=target_port,
        selector=selector,
        service_type="ClusterIP",
    )
