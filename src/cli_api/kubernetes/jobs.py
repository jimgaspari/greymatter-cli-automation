# cli_api/kubernetes/jobs.py

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from ..runner import run_cmd


def _dns1123(name: str, max_len: int = 63) -> str:
    """
    K8s name sanitizer (good enough for job names).
    """
    name = name.lower()
    name = re.sub(r"[^a-z0-9-]+", "-", name).strip("-")
    if not name:
        name = "run"
    return name[:max_len].rstrip("-")


def _kubectl_apply_obj(obj: Dict[str, Any], *, timeout_s: int = 60) -> Dict[str, Any]:
    """
    kubectl apply -f - using JSON (kubectl accepts JSON manifests).
    """
    manifest_json = json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
    return run_cmd(
        ["kubectl", "apply", "-f", "-"],
        input=manifest_json,
        timeout_s=timeout_s,
        check=False,
    )


def _kubectl_get_json(argv: List[str], *, timeout_s: int = 30) -> Dict[str, Any]:
    """
    Runs kubectl ... -o json and returns dict with parsed JSON in ["json"].
    """
    res = run_cmd(argv + ["-o", "json"], timeout_s=timeout_s, check=False)
    if res.get("returncode", 1) != 0:
        return res
    try:
        res["json"] = json.loads(res.get("stdout") or "{}")
    except Exception as e:
        res["json_error"] = str(e)
    return res


def create_workflow_job(
    *,
    jobs_namespace: str,
    run_id: str,
    secret_name: str,
    runner_image: str,
    service_account_name: str,
    command: Optional[List[str]] = None,
    extra_env: Optional[Dict[str, str]] = None,
    backoff_limit: int = 0,
    ttl_seconds_after_finished: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Creates/updates a Job that mounts the given Secret at /inputs/request.json
    and runs the workflow entrypoint.

    The Secret should contain a key "request.json".
    """
    job_name = _dns1123(f"cli-api-{run_id}")

    if command is None:
        command = ["python", "-m", "cli_api.job_main"]

    env_list = [
        {"name": "WORKFLOW_RUN_ID", "value": run_id},
        {"name": "WORKFLOW_PAYLOAD_PATH", "value": "/inputs/request.json"},
    ]
    if extra_env:
        for k, v in extra_env.items():
            env_list.append({"name": str(k), "value": str(v)})

    job: Dict[str, Any] = {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {
            "name": job_name,
            "namespace": jobs_namespace,
            "labels": {
                "app": "cli-api",
                "cli-api-run-id": run_id,
            },
        },
        "spec": {
            "backoffLimit": backoff_limit,
            "template": {
                "metadata": {
                    "labels": {
                        "job-name": job_name,
                        "app": "cli-api",
                        "cli-api-run-id": run_id,
                    }
                },
                "spec": {
                    "serviceAccountName": service_account_name,
                    "restartPolicy": "Never",
                    "containers": [
                        {
                            "name": "runner",
                            "image": runner_image,
                            "imagePullPolicy": "IfNotPresent",
                            "command": command,
                            "env": env_list,
                            "volumeMounts": [
                                {"name": "inputs", "mountPath": "/inputs", "readOnly": True},
                                {"name": "work", "mountPath": "/work"},
                            ],
                        }
                    ],
                    "volumes": [
                        {
                            "name": "inputs",
                            "secret": {
                                "secretName": secret_name,
                                "items": [
                                    {"key": "request.json", "path": "request.json"},
                                ],
                            },
                        },
                        {"name": "work", "emptyDir": {}},
                    ],
                },
            },
        },
    }

    if ttl_seconds_after_finished is not None:
        job["spec"]["ttlSecondsAfterFinished"] = int(ttl_seconds_after_finished)

    applied = _kubectl_apply_obj(job, timeout_s=60)
    applied["job_name"] = job_name
    applied["namespace"] = jobs_namespace
    return applied


def get_job(
    *,
    jobs_namespace: str,
    job_name: str,
) -> Dict[str, Any]:
    return _kubectl_get_json(
        ["kubectl", "-n", jobs_namespace, "get", "job", job_name],
        timeout_s=30,
    )


def get_job_status(
    *,
    jobs_namespace: str,
    job_name: str,
) -> Dict[str, Any]:
    """
    Returns a friendly status summary plus raw job JSON.
    """
    res = get_job(jobs_namespace=jobs_namespace, job_name=job_name)
    if res.get("returncode", 1) != 0:
        return res

    job = res.get("json") or {}
    st = job.get("status", {}) or {}
    spec = job.get("spec", {}) or {}

    status = {
        "job_name": job_name,
        "namespace": jobs_namespace,
        "active": st.get("active", 0),
        "succeeded": st.get("succeeded", 0),
        "failed": st.get("failed", 0),
        "startTime": st.get("startTime"),
        "completionTime": st.get("completionTime"),
        "backoffLimit": spec.get("backoffLimit"),
        "conditions": st.get("conditions", []),
    }

    # A simple high-level state
    state = "unknown"
    if status["succeeded"]:
        state = "succeeded"
    elif status["failed"]:
        state = "failed"
    elif status["active"]:
        state = "running"

    status["state"] = state
    res["status"] = status
    return res


def list_job_pods(
    *,
    jobs_namespace: str,
    job_name: str,
) -> Dict[str, Any]:
    """
    Lists pods belonging to a Job (by label selector).
    """
    return _kubectl_get_json(
        ["kubectl", "-n", jobs_namespace, "get", "pods", "-l", f"job-name={job_name}"],
        timeout_s=30,
    )


def get_job_pod_name(
    *,
    jobs_namespace: str,
    job_name: str,
) -> Dict[str, Any]:
    """
    Returns one pod name for the job (prefers most recent by creationTimestamp).
    """
    res = list_job_pods(jobs_namespace=jobs_namespace, job_name=job_name)
    if res.get("returncode", 1) != 0:
        return res

    items = (res.get("json") or {}).get("items", []) or []
    if not items:
        return {"returncode": 1, "stderr": f"No pods found for job {job_name}", "stdout": ""}

    # pick newest pod
    items.sort(key=lambda p: (p.get("metadata", {}) or {}).get("creationTimestamp", ""))
    pod = items[-1]
    pod_name = (pod.get("metadata", {}) or {}).get("name")
    return {"returncode": 0, "pod_name": pod_name, "pod": pod}


def get_pod_logs(
    *,
    jobs_namespace: str,
    pod_name: str,
    container: str = "runner",
    tail_lines: int = 200,
) -> Dict[str, Any]:
    return run_cmd(
        ["kubectl", "-n", jobs_namespace, "logs", pod_name, "-c", container, "--tail", str(tail_lines)],
        timeout_s=30,
        check=False,
    )


def get_job_logs(
    *,
    jobs_namespace: str,
    job_name: str,
    container: str = "runner",
    tail_lines: int = 200,
) -> Dict[str, Any]:
    """
    Convenience: find pod for job then return logs.
    """
    pod_res = get_job_pod_name(jobs_namespace=jobs_namespace, job_name=job_name)
    if pod_res.get("returncode", 1) != 0:
        return pod_res

    return get_pod_logs(
        jobs_namespace=jobs_namespace,
        pod_name=pod_res["pod_name"],
        container=container,
        tail_lines=tail_lines,
    )


def delete_job(
    *,
    jobs_namespace: str,
    job_name: str,
    wait: bool = False,
) -> Dict[str, Any]:
    argv = ["kubectl", "-n", jobs_namespace, "delete", "job", job_name]
    if wait:
        argv.append("--wait=true")
    else:
        argv.append("--wait=false")
    return run_cmd(argv, timeout_s=30, check=False)
