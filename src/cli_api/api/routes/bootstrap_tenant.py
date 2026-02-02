from fastapi import APIRouter, Header, HTTPException
from typing import Optional, Any, Dict

from cli_api.schemas import BootstrapTenantReq
from cli_api.config import settings
from cli_api.runner import run_cmd
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
    wait_for_result_secret
)

router = APIRouter(prefix="/workflows", tags=["workflows"])

@router.post("/bootstrap-tenant")
def api_bootstrap_tenant(req: BootstrapTenantReq, x_api_token: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    require_token(x_api_token)

    run_id = _utc_run_id("tenant")
    jobs_ns = _jobs_namespace()

    # 1) Create input secret
    secret_res = create_run_input_secret(
        jobs_namespace=jobs_ns,
        run_id=run_id,
        request_obj=req.model_dump(),
        secret_name=req.namespace
    )
    if secret_res.get("returncode", 1) != 0:
        raise HTTPException(
            status_code=500,
            detail={
                "step": "create_run_input_secret",
                "stdout": secret_res.get("stdout", ""),
                "stderr": secret_res.get("stderr", ""),
                "returncode": secret_res.get("returncode", 1),
            },
        )

    # 2) Create job
    cp = req.create_project
    script_cfg = cp.script

    script_cm = None
    script_key = "bootstrap.sh"
    script_mount_dir = "/scripts"
    script_filename = "bootstrap.sh"

    if script_cfg.enabled:
        if not script_cfg.configmap_name:
            raise HTTPException(
                status_code=400,
                detail="create_project.script.enabled=true requires create_project.script.configmap_name",
            )
        script_cm = script_cfg.configmap_name
        script_key = script_cfg.script_key
        script_mount_dir = script_cfg.mount_dir
        script_filename = script_cfg.filename


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
            },
            ttl_seconds_after_finished=3600,

            script_configmap_name=script_cm,
            script_key=script_key,
            script_mount_dir=script_mount_dir,
            script_filename=script_filename,
        )


    if job_res.get("returncode", 1) != 0:
        delete_run_input_secret(jobs_namespace=jobs_ns, secret_name=secret_res["secret_name"])
        raise HTTPException(
            status_code=500,
            detail={
                "step": "create_workflow_job",
                "stdout": job_res.get("stdout", ""),
                "stderr": job_res.get("stderr", ""),
                "returncode": job_res.get("returncode", 1),
            },
        )
    
    job_name = job_res["job_name"]
    input_secret_name = secret_res["secret_name"]
    try:
        wait_res = wait_for_job_completion(
            namespace=jobs_ns,
            job_name=job_name,
            timeout_s=getattr(settings, "job_wait_timeout_s", 900),
            poll_s=2.0,
        )

        # Best-effort logs (don’t fail the request just because logs aren’t available)
        logs_res = get_job_logs(jobs_namespace=jobs_ns, job_name=job_name, tail_lines=400)
        logs = logs_res.get("stdout") if logs_res.get("returncode", 1) == 0 else None

        if wait_res.get("returncode", 1) != 0:
            # timed out or couldn't query status — do NOT try to read/delete result secret here
            raise HTTPException(
                status_code=504,
                detail={
                    "returncode": 1,
                    "step": "wait for job completion",
                    "run_id": run_id,
                    "jobs_namespace": jobs_ns,
                    "job_name": job_name,
                    "secret_name": secret_res["secret_name"],
                    "detail": wait_res,
                    "logs": logs,
                },
            )

        # Job completed: now read result secret with retries
        result_res = read_result_secret(
            jobs_namespace=jobs_ns,
            run_id=run_id
        )
        result_obj = result_res["result"] if result_res.get("returncode") == 0 else None

        # Determine returncode (prefer result_obj; fallback to job phase)
        if isinstance(result_obj, dict):
            rc = 0 if result_obj.get("returncode", 1) == 0 else 1
        else:
            phase = wait_res["summary"]["phase"]
            rc = 0 if phase == "succeeded" else 1
        
        tenant_config = None
        if rc == 0:
            core_namespace = (req.create_project.core_namespace or "").strip()
            if not core_namespace:
                raise HTTPException(status_code=400, detail="create_project.core_namespace is required to spawn tenant-config job")

            config_run_id = _utc_run_id("tenant-config")

            config_payload = {
                "namespace": req.namespace,
                "core_namespace": core_namespace,
            }

            config_secret = create_run_input_secret(
                jobs_namespace=jobs_ns,
                run_id=config_run_id,
                request_obj=config_payload,
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
                    "TENANT_NAMESPACE": req.namespace,
                    "CORE_NAMESPACE": core_namespace,
                },
                ttl_seconds_after_finished=3600,
            )
            if config_job.get("returncode", 1) != 0:
                raise HTTPException(status_code=500, detail={"step": "create_tenant_config_job", "detail": config_job})

            config_wait = wait_for_job_completion(
                namespace=jobs_ns,
                job_name=config_job["job_name"],
                timeout_s=getattr(settings, "job_wait_timeout_s", 900),
                poll_s=2.0,
            )
            if config_wait.get("returncode", 1) != 0:
                raise HTTPException(status_code=504, detail={"step": "wait_tenant_config_job", "detail": config_wait})

            config_result = wait_for_result_secret(jobs_namespace=jobs_ns, run_id=config_run_id, timeout_s=30, poll_s=1.0)

            tenant_config = {
                "run_id": config_run_id,
                "job_name": config_job["job_name"],
                "summary": config_wait.get("summary"),
                "result": config_result.get("result") if config_result.get("returncode", 1) == 0 else None,
                "result_read": config_result,
            }


        return {
            "returncode": rc,
            "run_id": run_id,
            "jobs_namespace": jobs_ns,
            "job_name": job_name,
            "secret_name": secret_res["secret_name"],
            "summary": wait_res["summary"],
            "result": result_obj,
            "logs": logs,
            # Optional: include this to help debug when result_obj is None
            "result_read": result_res if result_obj is None else {"returncode": 0},
        }
    finally:
        delete_run_input_secret(jobs_namespace=jobs_ns, secret_name=input_secret_name)
