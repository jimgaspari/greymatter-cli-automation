from __future__ import annotations
import time
from typing import Any, Dict, List, Optional
import requests


def _join_prefix(prefix: str, path: str) -> str:
    p = (prefix or "").strip()
    if not p:
        return path
    if not p.startswith("/"):
        p = "/" + p
    p = p.rstrip("/")
    return f"{p}{path}"

def check_prometheus_targets(
    *,
    namespace: str,
    service_name: str = "prometheus",
    scheme: str = "http",
    port: int = 9090,
    path_prefix: str = "",
    require_all_up: bool = True,
    job_allowlist: Optional[List[str]] = None,
    timeout_s: float = 300.0,        # TOTAL wait time (5 min default)
    poll_interval_s: float = 5.0,    # how often to re-check
    request_timeout_s: float = 10.0, # per-HTTP request timeout
) -> Dict[str, Any]:
    """
    Polls Prometheus /api/v1/targets until required targets are up or timeout expires.
    """
    host = f"{service_name}.{namespace}.svc"
    path = _join_prefix(path_prefix, "/api/v1/targets")
    url = f"{scheme}://{host}:{port}{path}"

    step: Dict[str, Any] = {
        "name": "prometheus_targets_check",
        "returncode": 1,
        "url": url,
        "namespace": namespace,
        "service_name": service_name,
        "timeout_s": timeout_s,
        "poll_interval_s": poll_interval_s,
    }

    deadline = time.monotonic() + timeout_s
    attempts = 0
    last_error: Optional[str] = None
    last_counts: Optional[Dict[str, int]] = None
    last_down_summary: Optional[List[Dict[str, Any]]] = None

    def job_name(t: Dict[str, Any]) -> str:
        labels = t.get("labels") or {}
        if isinstance(labels, dict):
            return str(labels.get("job") or "")
        return ""

    while time.monotonic() < deadline:
        attempts += 1
        try:
            r = requests.get(url, timeout=request_timeout_s)
            step["http_status"] = r.status_code
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            last_error = f"Failed to query Prometheus targets: {e}"
            time.sleep(poll_interval_s)
            continue

        if not isinstance(data, dict) or data.get("status") != "success":
            last_error = f"Prometheus response not successful: status={data.get('status')}"
            time.sleep(poll_interval_s)
            continue

        payload = data.get("data") or {}
        active = payload.get("activeTargets") or []
        if not isinstance(active, list):
            last_error = "Prometheus response missing activeTargets list"
            time.sleep(poll_interval_s)
            continue

        considered: List[Dict[str, Any]] = []
        for t in active:
            if not isinstance(t, dict):
                continue
            if job_allowlist:
                j = job_name(t)
                if j not in job_allowlist:
                    continue
            considered.append(t)

        up = []
        down = []
        for t in considered:
            health = str(t.get("health") or "").lower()
            if health == "up":
                up.append(t)
            else:
                down.append(t)

        last_counts = {
            "active_total": len(active),
            "considered": len(considered),
            "up": len(up),
            "down": len(down),
        }

        # summarize down targets (bounded)
        down_summary = []
        for t in down[:50]:
            labels = t.get("labels") or {}
            down_summary.append(
                {
                    "job": labels.get("job") if isinstance(labels, dict) else None,
                    "instance": labels.get("instance") if isinstance(labels, dict) else None,
                    "health": t.get("health"),
                    "scrapeUrl": t.get("scrapeUrl"),
                    "lastError": t.get("lastError"),
                }
            )
        last_down_summary = down_summary

        if not require_all_up or len(down) == 0:
            step["stdout"] = (
                f"All Prometheus targets are up after {attempts} attempt(s)"
                if require_all_up
                else "Prometheus targets check passed"
            )
            step["returncode"] = 0
            step["attempts"] = attempts
            step["counts"] = last_counts
            return step

        # Not ready yet → wait and retry
        time.sleep(poll_interval_s)

    # --- timeout ---
    step["stderr"] = (
        last_error
        or f"Timed out waiting for Prometheus targets to become healthy after {attempts} attempt(s)"
    )
    step["attempts"] = attempts
    if last_counts:
        step["counts"] = last_counts
    if last_down_summary:
        step["down_targets"] = last_down_summary

    step["returncode"] = 1
    return step
