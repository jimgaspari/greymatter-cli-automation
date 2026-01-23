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

import time
import requests
from typing import Dict, Any, Optional, List


def check_prometheus_targets(
    *,
    namespace: str,
    service_name: str = "prometheus",
    scheme: str = "http",
    port: int = 9090,
    path_prefix: str = "",
    require_all_up: bool = True,
    job_allowlist: Optional[List[str]] = None,

    # TOTAL wait budget
    timeout_s: float = 300.0,

    # Polling controls
    poll_interval_s: float = 5.0,
    request_timeout_s: float = 10.0,

    # NEW: wait conditions
    min_active_targets: int = 1,             # wait until Prometheus returns at least this many active targets
    require_allowlist_match: bool = True,    # if allowlist provided, require it to match at least one active target
) -> Dict[str, Any]:
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
        "min_active_targets": min_active_targets,
    }
    if job_allowlist:
        step["job_allowlist"] = job_allowlist
        step["require_allowlist_match"] = require_allowlist_match

    deadline = time.monotonic() + timeout_s
    attempts = 0

    last_error: Optional[str] = None
    last_counts: Optional[Dict[str, int]] = None
    last_down_summary: Optional[List[Dict[str, Any]]] = None
    last_seen_jobs: Optional[List[str]] = None
    last_http_status: Optional[int] = None

    def job_name(t: Dict[str, Any]) -> str:
        labels = t.get("labels") or {}
        if isinstance(labels, dict):
            return str(labels.get("job") or "")
        return ""

    while time.monotonic() < deadline:
        attempts += 1
        try:
            r = requests.get(url, timeout=request_timeout_s)
            last_http_status = r.status_code
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            last_error = f"Failed to query Prometheus targets: {e}"
            time.sleep(poll_interval_s)
            continue

        # Expect: {status:"success", data:{activeTargets:[...]}}
        if not isinstance(data, dict) or data.get("status") != "success":
            last_error = f"Prometheus response not successful: status={data.get('status') if isinstance(data, dict) else type(data)}"
            time.sleep(poll_interval_s)
            continue

        payload = data.get("data") or {}
        active = payload.get("activeTargets") or []
        if not isinstance(active, list):
            last_error = "Prometheus response missing activeTargets list"
            time.sleep(poll_interval_s)
            continue

        # NEW: Wait until Prometheus is actually returning active targets
        if len(active) < min_active_targets:
            last_error = f"Waiting for Prometheus activeTargets >= {min_active_targets} (currently {len(active)})"
            last_counts = {"active_total": len(active), "considered": 0, "up": 0, "down": 0}
            time.sleep(poll_interval_s)
            continue

        # Compute seen jobs to help debugging / allowlist tuning
        seen_jobs = []
        for t in active[:50]:
            if isinstance(t, dict):
                j = job_name(t)
                if j:
                    seen_jobs.append(j)
        last_seen_jobs = sorted({j for j in seen_jobs if j})

        # Apply allowlist filter
        considered: List[Dict[str, Any]] = []
        for t in active:
            if not isinstance(t, dict):
                continue
            if job_allowlist:
                j = job_name(t)
                if j not in job_allowlist:
                    continue
            considered.append(t)

        # NEW: If allowlist provided, optionally wait until it matches something
        if job_allowlist and require_allowlist_match and len(considered) == 0:
            last_error = (
                "Waiting for Prometheus targets that match job_allowlist "
                f"(activeTargets={len(active)}, matched=0, seen_jobs={last_seen_jobs})"
            )
            last_counts = {"active_total": len(active), "considered": 0, "up": 0, "down": 0}
            time.sleep(poll_interval_s)
            continue

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

        # Summarize down targets (bounded)
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

        # Success condition
        if not require_all_up or len(down) == 0:
            step["returncode"] = 0
            step["stdout"] = f"Targets healthy after {attempts} attempt(s)"
            step["attempts"] = attempts
            step["http_status"] = last_http_status
            step["counts"] = last_counts
            if last_seen_jobs is not None:
                step["seen_jobs"] = last_seen_jobs
            return step

        # Not healthy yet -> keep waiting
        last_error = f"Waiting for all targets to be up (down={len(down)})"
        time.sleep(poll_interval_s)

    # Timed out
    step["returncode"] = 1
    step["attempts"] = attempts
    if last_http_status is not None:
        step["http_status"] = last_http_status
    step["stderr"] = last_error or f"Timed out after {attempts} attempt(s)"
    if last_counts is not None:
        step["counts"] = last_counts
    if last_down_summary is not None:
        step["down_targets"] = last_down_summary
    if last_seen_jobs is not None:
        step["seen_jobs"] = last_seen_jobs
    return step
