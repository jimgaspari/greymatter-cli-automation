from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Tuple
import requests


@dataclass(frozen=True)
class PromEndpoint:
    url: str
    service_name: str
    scheme: str
    port: int
    path_prefix: str


def _join(prefix: str, path: str) -> str:
    p = (prefix or "").strip()
    if not p:
        return path
    if not p.startswith("/"):
        p = "/" + p
    p = p.rstrip("/")
    return f"{p}{path}"


def resolve_prometheus_endpoint_for_namespace(
    *,
    gm_namespace: str,
    scheme: str = "http",
    port: int = 9090,
    service_name: str = "prometheus",
    path_prefix: str = "",
    probe: bool = False,
    probe_timeout_s: float = 2.0,
) -> Tuple[Optional[PromEndpoint], Dict[str, Any]]:
    """
    Deterministically resolves the Prometheus endpoint based on namespace.
    Assumes a Service named `service_name` exists (or will exist) in that namespace.
    """
    host = f"{service_name}.{gm_namespace}.svc"
    targets_path = _join(path_prefix, "/api/v1/targets")
    url = f"{scheme}://{host}:{port}{targets_path}"

    meta: Dict[str, Any] = {
        "attempts": [{"url": url}],
        "probe": probe,
    }

    ep = PromEndpoint(
        url=url,
        service_name=service_name,
        scheme=scheme,
        port=port,
        path_prefix=path_prefix,
    )

    if not probe:
        return ep, meta

    # Optional quick probe (NOT a wait loop)
    try:
        r = requests.get(url, timeout=probe_timeout_s)
        meta["attempts"][0]["http_status"] = r.status_code
        # don't require status=success here; checker will handle it
        return ep, meta
    except Exception as e:
        meta["attempts"][0]["error"] = str(e)
        # Still return the endpoint; the wait-loop checker will retry
        return ep, meta
