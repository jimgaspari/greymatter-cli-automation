# cli_api/kubernetes/jobs.py

from __future__ import annotations
from typing import Any, Dict, List, Optional
import json
import re
import time
import base64

from cli_api.runner import run_cmd


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
    script_configmap_name: Optional[str] = None,
    script_key: str = "bootstrap.sh",
    script_mount_dir: str = "/scripts",
    script_filename: str = "bootstrap.sh",
) -> Dict[str, Any]:
    """
    Creates/updates a Job that mounts the given Secret at /inputs/request.json.

    Optionally mounts a ConfigMap containing a bash script (default key bootstrap.sh)
    at script_mount_dir (default /scripts). If command is not provided and
    script_configmap_name is set, the Job runs the script via bash -lc.
    """
    job_name = _dns1123(f"cli-api-{run_id}")

    # Build env list
    env_list = [
        {"name": "WORKFLOW_RUN_ID", "value": run_id},
        {"name": "WORKFLOW_PAYLOAD_PATH", "value": "/inputs/request.json"},
    ]
    if extra_env:
        for k, v in extra_env.items():
            env_list.append({"name": str(k), "value": str(v)})

    # Volumes + mounts (base)
    volume_mounts: List[Dict[str, Any]] = [
        {"name": "inputs", "mountPath": "/inputs", "readOnly": True},
        {"name": "work", "mountPath": "/work"},
        {"name": "outputs", "mountPath": "/outputs"},
    ]

    volumes: List[Dict[str, Any]] = [
        {
            "name": "inputs",
            "secret": {
                "secretName": secret_name,
                "items": [{"key": "request.json", "path": "request.json"}],
            },
        },
        {"name": "work", "emptyDir": {}},
        {"name": "outputs", "emptyDir": {}},
    ]

    # Optional script ConfigMap mount
    if script_configmap_name:
        volume_mounts.append(
            {"name": "tenant-script", "mountPath": script_mount_dir, "readOnly": True}
        )
        volumes.append(
            {
                "name": "tenant-script",
                "configMap": {
                    "name": script_configmap_name,
                    # 0755 so the script is executable even if it has a shebang
                    "defaultMode": 0o755,
                    "items": [{"key": script_key, "path": script_filename}],
                },
            }
        )

    # Default command behavior
    command = ["python", "-m", "cli_api.job_main"]

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
                            "volumeMounts": volume_mounts,
                        }
                    ],
                    "volumes": volumes,
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

def get_job(namespace: str, job_name: str) -> Dict[str, Any]:
    """
    Fetch a Job as JSON.
    NOTE: Signature intentionally matches callers like wait_for_job_completion().
    """
    res = run_cmd(
        ["kubectl", "-n", namespace, "get", "job", job_name, "-o", "json"],
        check=False,
        timeout_s=30,
    )
    if res.get("returncode", 1) != 0:
        return {"returncode": 1, "step": "kubectl get job", **res}

    try:
        job = json.loads(res.get("stdout") or "{}")
    except Exception as e:
        return {"returncode": 1, "step": "parse job json", "stderr": str(e), **res}

    return {"returncode": 0, "job": job}


def get_job_status(*, jobs_namespace: str, job_name: str) -> Dict[str, Any]:
    """
    Returns a friendly status summary plus raw job JSON.
    """
    res = get_job(jobs_namespace=jobs_namespace, job_name=job_name)
    if res.get("returncode", 1) != 0:
        return res

    job = res.get("job") or {}
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

    state = "unknown"
    if status["succeeded"]:
        state = "succeeded"
    elif status["failed"]:
        state = "failed"
    elif status["active"]:
        state = "running"
    else:
        state = "pending"

    status["state"] = state
    return {"returncode": 0, "status": status, "job": job}

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

def get_job_pod_name(*, jobs_namespace: str, job_name: str) -> Dict[str, Any]:
    """
    Returns newest pod name for a job (structured result).
    """
    res = run_cmd(
        [
            "kubectl", "-n", jobs_namespace, "get", "pods",
            "-l", f"job-name={job_name}",
            "-o", "jsonpath={.items[-1:].metadata.name}",
        ],
        check=False,
        timeout_s=30,
    )
    if res.get("returncode", 1) != 0:
        return {"returncode": 1, "step": "kubectl get pod name", **res}

    pod_name = (res.get("stdout") or "").strip()
    if not pod_name:
        return {"returncode": 1, "step": "kubectl get pod name", "stderr": "No pod found for job"}

    return {"returncode": 0, "pod_name": pod_name}

def get_pod_logs(
    *,
    jobs_namespace: str,
    pod_name: str,
    container: str = "runner",
    tail_lines: int = 500,
) -> Dict[str, Any]:
    res = run_cmd(
        ["kubectl", "-n", jobs_namespace, "logs", pod_name, "-c", container, f"--tail={tail_lines}"],
        check=False,
        timeout_s=30,
    )
    return {
        "returncode": res.get("returncode", 1),
        "stdout": res.get("stdout", ""),
        "stderr": res.get("stderr", ""),
    }

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

def summarize_job(job: Dict[str, Any]) -> Dict[str, Any]:
    status = job.get("status", {}) or {}
    conditions = status.get("conditions") or []

    cond_map = {c.get("type"): c for c in conditions if isinstance(c, dict)}
    complete = cond_map.get("Complete")
    failed = cond_map.get("Failed")

    succeeded = status.get("succeeded", 0) or 0
    failed_count = status.get("failed", 0) or 0
    active = status.get("active", 0) or 0

    phase = "running"
    if failed is not None or failed_count > 0:
        phase = "failed"
    elif complete is not None or succeeded > 0:
        phase = "succeeded"
    elif active > 0:
        phase = "running"
    else:
        phase = "pending"

    return {
        "phase": phase,
        "active": active,
        "succeeded": succeeded,
        "failed": failed_count,
        "conditions": conditions,
        "startTime": status.get("startTime"),
        "completionTime": status.get("completionTime"),
    }

def wait_for_job_completion(
    namespace: str,
    job_name: str,
    timeout_s: int = 900,
    poll_s: float = 2.0,
) -> Dict[str, Any]:
    """
    Wait until job is succeeded or failed, or timeout.
    Returns a structured status summary.
    """
    deadline = time.time() + timeout_s
    last_summary: Dict[str, Any] = {}

    while time.time() < deadline:
        gj = get_job(namespace, job_name)
        if gj.get("returncode", 1) != 0:
            return {"returncode": 1, "step": "wait get job", "detail": gj}

        job = gj["job"]
        summary = summarize_job(job)
        last_summary = summary

        if summary["phase"] in ("succeeded", "failed"):
            return {"returncode": 0, "summary": summary, "job": job}

        time.sleep(poll_s)

    return {
        "returncode": 1,
        "step": "wait timeout",
        "stderr": f"Timed out waiting for job {job_name} in {namespace} after {timeout_s}s",
        "last_summary": last_summary,
    }

def get_job_result_json(namespace: str, pod_name: str, container: str = "runner") -> Dict[str, Any]:
    res = run_cmd(
        ["kubectl", "-n", namespace, "exec", pod_name, "-c", container, "--", "cat", "/outputs/result.json"],
        check=False,
        timeout_s=30,
    )
    if res.get("returncode", 1) != 0:
        return {"returncode": 1, "step": "read result.json", **res}

    try:
        parsed = json.loads(res.get("stdout") or "{}")
    except Exception as e:
        return {"returncode": 1, "step": "parse result.json", "stderr": str(e), "raw": res.get("stdout", "")}

    return {"returncode": 0, "result": parsed}

def read_result_secret(*, jobs_namespace: str, run_id: str) -> Dict[str, Any]:
    name = f"cli-api-result-{run_id}".lower()

    res = run_cmd(
        ["kubectl", "-n", jobs_namespace, "get", "secret", name, "-o", "jsonpath={.data.result\\.json}"],
        check=False,
        timeout_s=30,
    )
    if res.get("returncode", 1) != 0:
        return {"returncode": 1, "step": "get result secret", **res}

    b64 = (res.get("stdout") or "").strip()
    if not b64:
        return {"returncode": 1, "step": "get result secret", "stderr": "result.json key missing/empty"}

    try:
        decoded = base64.b64decode(b64).decode("utf-8")
        parsed = json.loads(decoded)
    except Exception as e:
        return {"returncode": 1, "step": "decode result secret", "stderr": str(e)}

    return {"returncode": 0, "result": parsed}

def wait_for_result_secret(
    *,
    jobs_namespace: str,
    run_id: str,
    timeout_s: float = 30.0,
    poll_s: float = 1.0,
) -> Dict[str, Any]:
    """
    Polls until cli-api-result-<run_id> exists and contains result.json.
    """
    deadline = time.time() + timeout_s
    last: Dict[str, Any] = {}

    while time.time() < deadline:
        res = read_result_secret(jobs_namespace=jobs_namespace, run_id=run_id)
        last = res
        if res.get("returncode", 1) == 0:
            return res
        time.sleep(poll_s)

    return {
        "returncode": 1,
        "step": "wait_for_result_secret",
        "stderr": f"Timed out waiting for result secret cli-api-result-{run_id} in ns={jobs_namespace}",
        "last": last,
    }