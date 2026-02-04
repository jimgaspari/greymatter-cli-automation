from fastapi import APIRouter, Header, HTTPException
from typing import Optional, Any, Dict, List
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

from cli_api.schemas.project import BootstrapTenantReq
from cli_api.schemas.git import GitConfig
from cli_api.config import settings
from cli_api.api.deps import (
    require_token,
    _utc_run_id,
    _jobs_namespace,
    _runner_image,
    _runner_sa,
)
from cli_api.kubernetes.input_secrets import (
    create_run_input_secret,
    delete_run_input_secret,
)
from cli_api.kubernetes.jobs import (
    create_workflow_job,
    wait_for_job_completion,
    read_result_secret,
    get_job_logs,
)

router = APIRouter(prefix="/workflows", tags=["workflows"])

def _as_dict(x):
    if x is None:
        return {}
    if isinstance(x, dict):
        # drop None values from plain dicts too
        return {k: v for k, v in x.items() if v is not None}
    if hasattr(x, "model_dump"):
        return x.model_dump(exclude_unset=True, exclude_none=True)
    d = dict(x)
    return {k: v for k, v in d.items() if v is not None}


@router.post("/bootstrap-tenant")
def api_bootstrap_tenant(req: BootstrapTenantReq, x_api_token: Optional[str] = Header(default=None)):
    require_token(x_api_token)
    logging.info("Boostrapping tenant")
    jobs_ns = _jobs_namespace()

    # ---- validate top-level ----
    if not req.tenants:
        raise HTTPException(status_code=400, detail="tenants[] must contain at least one tenant")

    core_namespace = (req.core_namespace or "").strip()
    if not core_namespace:
        raise HTTPException(status_code=400, detail="core_namespace is required")

    base_git_overrides = _as_dict(req.git)
    base_kubernetes = _as_dict(req.kubernetes)
    base_prom = _as_dict(req.prometheus_check)

    # ---- normalize + validate tenants ----
    normalized_tenants: List[Dict[str, Any]] = []
    
    for idx, tenant in enumerate(req.tenants):
        ns = (tenant.namespace or "").strip()
        if not ns:
            raise HTTPException(status_code=400, detail=f"tenants[{idx}].namespace is required")

        tenant_overrides = _as_dict(getattr(tenant, "git", None))

        # validate merged config here (so API catches errors)
        merged_git = {**base_git_overrides, **tenant_overrides}
        merged_git = _as_dict(merged_git)  # drops None
        try:
            GitConfig(**merged_git)
        except Exception as e:
            raise HTTPException(...)

        # and log repo_url
        logging.info("tenant=%s merged_repo_url=%s", ns, merged_git.get("repo_url"))

        # repo_url MUST be present
        if not (merged_git.get("repo_url") or "").strip():
            raise HTTPException(status_code=400, detail=f"git.repo_url is required (missing for tenants[{idx}]={ns})")

        # validate merged git config (enforces ssh key rules, etc.)
        try:
            merged_git = GitConfig(**merged_git).model_dump()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"git config invalid for tenants[{idx}]={ns}: {str(e)}")

        # Per-tenant script config comes from tenant.script
        script_cfg = tenant.script
        script_enabled = bool(script_cfg.enabled)

        if script_enabled and not (script_cfg.configmap_name or "").strip():
            raise HTTPException(
                status_code=400,
                detail=f"tenants[{idx}].script.enabled=true requires tenants[{idx}].script.configmap_name",
            )
        tenant_env = _as_dict(getattr(tenant, "env_vars", None))

        # enforce k8s env var name rules (optional but recommended)
        import re
        bad_keys = [k for k in tenant_env.keys() if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", k)]
        if bad_keys:
            raise HTTPException(status_code=400, detail=f"tenants[{idx}].env_vars has invalid keys: {bad_keys}")

        normalized_tenants.append({
            "namespace": ns,
            "project_settings": _as_dict(getattr(tenant, "project_settings", {})),
            "git_overrides": tenant_overrides,
            "env_vars": tenant_env,
            "script": {
                "enabled": script_enabled,
                "configmap_name": script_cfg.configmap_name,
                "script_key": script_cfg.script_key,
                "mount_dir": script_cfg.mount_dir,
                "filename": script_cfg.filename,
            },
        })

    # ---- fan-out: create secrets + jobs ----
    spawned: List[Dict[str, str]] = []

    for t in normalized_tenants:
        tenant_ns = t["namespace"]
        run_id = _utc_run_id(f"tenant-{tenant_ns}")

        global_defaults = dict(base_git_overrides)
        global_defaults.pop("repo_url", None)  # global should NOT set repo_url

        job_payload = {
            "workspace_name": getattr(req, "workspace_name", None),
            "core_namespace": core_namespace,
            "git": global_defaults,                 # global defaults only
            "kubernetes": base_kubernetes,
            "prometheus_check": base_prom,
            "tenants": [{
                "namespace": tenant_ns,
                "project_settings": t["project_settings"],
                "script": t["script"],
                "git": t["git_overrides"],
                "env_vars": t["env_vars"],
            }],
        }

        secret_res = create_run_input_secret(
            jobs_namespace=jobs_ns,
            run_id=run_id,
            request_obj=job_payload,
            secret_name=tenant_ns,
        )
        if secret_res.get("returncode", 1) != 0:
            raise HTTPException(status_code=500, detail={"step": "create_run_input_secret", "tenant": tenant_ns, "detail": secret_res})

        script = t["script"]
        script_cm = script["configmap_name"] if script["enabled"] else None

        job_res = create_workflow_job(
            jobs_namespace=jobs_ns,
            run_id=run_id,
            secret_name=secret_res["secret_name"],
            runner_image=_runner_image(),
            service_account_name=_runner_sa(),
            extra_env={
                "CLI_API_WORKDIR": "/work",
                "CLI_API_JOBS_NAMESPACE": jobs_ns,
                "WORKFLOW_NAME": "bootstrap-tenant",
                **t["env_vars"],
            },
            ttl_seconds_after_finished=3600,
            script_configmap_name=script_cm,
            script_key=script.get("script_key", "bootstrap.sh"),
            script_mount_dir=script.get("mount_dir", "/scripts"),
            script_filename=script.get("filename", "bootstrap.sh"),
        )
        if job_res.get("returncode", 1) != 0:
            delete_run_input_secret(jobs_namespace=jobs_ns, secret_name=secret_res["secret_name"])
            raise HTTPException(status_code=500, detail={"step": "create_workflow_job", "tenant": tenant_ns, "detail": job_res})

        spawned.append({
            "tenant": tenant_ns,
            "run_id": run_id,
            "job_name": job_res["job_name"],
            "secret_name": secret_res["secret_name"],
        })

    # ---- parallel wait/read results ----
    def _wait_one(item: Dict[str, str]) -> Dict[str, Any]:
        job_name = item["job_name"]
        run_id = item["run_id"]

        wait_res = wait_for_job_completion(
            namespace=jobs_ns,
            job_name=job_name,
            timeout_s=getattr(settings, "job_wait_timeout_s", 900),
            poll_s=2.0,
        )
        logs_res = get_job_logs(jobs_namespace=jobs_ns, job_name=job_name, tail_lines=400)
        logs = logs_res.get("stdout") if logs_res.get("returncode", 1) == 0 else None

        if wait_res.get("returncode", 1) != 0:
            return {**item, "returncode": 1, "step": "wait_for_job_completion", "wait": wait_res, "logs": logs}

        result_res = read_result_secret(jobs_namespace=jobs_ns, run_id=run_id)
        result_obj = result_res.get("result") if result_res.get("returncode") == 0 else None

        rc = 0
        if isinstance(result_obj, dict) and result_obj.get("returncode", 0) != 0:
            rc = 1

        return {
            **item,
            "returncode": rc,
            "summary": wait_res.get("summary"),
            "result": result_obj,
            "logs": logs,
            "result_read": result_res if result_obj is None else {"returncode": 0},
        }

    results: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=min(8, max(1, len(spawned)))) as ex:
        futs = [ex.submit(_wait_one, it) for it in spawned]
        for f in as_completed(futs):
            results.append(f.result())

    # cleanup input secrets best-effort
    for it in spawned:
        delete_run_input_secret(jobs_namespace=jobs_ns, secret_name=it["secret_name"])

    # ---- tenant-config: run ONCE if all succeeded ----
    overall_rc = 0 if all(r.get("returncode", 1) == 0 for r in results) else 1
    tenant_config = None

    tenant_namespaces = [t["namespace"] for t in normalized_tenants]

    if overall_rc == 0:
        config_run_id = _utc_run_id("tenant-config")
        payload = {"core_namespace": core_namespace, "tenant_namespaces": tenant_namespaces}

        config_secret = create_run_input_secret(
            jobs_namespace=jobs_ns,
            run_id=config_run_id,
            request_obj=payload
        )
        if config_secret.get("returncode", 1) != 0:
            raise HTTPException(status_code=500, detail={"step": "create_tenant_config_input_secret", "detail": config_secret})

        config_job = create_workflow_job(
            jobs_namespace=jobs_ns,
            run_id=config_run_id,
            secret_name=config_secret["secret_name"],
            runner_image=_runner_image(),
            service_account_name=_runner_sa(),
            extra_env={
                "CLI_API_WORKDIR": "/work",
                "CLI_API_JOBS_NAMESPACE": jobs_ns,
                "WORKFLOW_NAME": "tenant-config",
            },
            ttl_seconds_after_finished=3600,
        )
        if config_job.get("returncode", 1) != 0:
            delete_run_input_secret(jobs_namespace=jobs_ns, secret_name=config_secret["secret_name"])
            raise HTTPException(status_code=500, detail={"step": "create_tenant_config_job", "detail": config_job})

        config_wait = wait_for_job_completion(
            namespace=jobs_ns,
            job_name=config_job["job_name"],
            timeout_s=getattr(settings, "job_wait_timeout_s", 900),
            poll_s=2.0,
        )
        config_result = read_result_secret(jobs_namespace=jobs_ns, run_id=config_run_id)

        tenant_config = {
            "run_id": config_run_id,
            "job_name": config_job["job_name"],
            "summary": config_wait.get("summary"),
            "result": config_result.get("result") if config_result.get("returncode", 1) == 0 else None,
            "result_read": config_result,
        }

        delete_run_input_secret(jobs_namespace=jobs_ns, secret_name=config_secret["secret_name"])

    return {
        "returncode": overall_rc,
        "jobs_namespace": jobs_ns,
        "tenants": results,
        "tenant_config": tenant_config,
    }
