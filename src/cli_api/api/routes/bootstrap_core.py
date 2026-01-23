from fastapi import APIRouter, Header, HTTPException
from typing import Optional, Any, Dict
import datetime as dt

from cli_api.config import settings
from cli_api.schemas import BootstrapCoreReq
from cli_api.api.deps import (
    require_token, 
    _utc_run_id, 
    _jobs_namespace, 
    _runner_image, 
    _runner_sa
)

from cli_api.kubernetes.input_secrets import (
    create_run_input_secret, 
    delete_run_input_secret
)
from cli_api.kubernetes.jobs import ( 
    create_workflow_job, 
    get_job_pod_name,
    get_pod_logs,
    create_workflow_job,
    wait_for_job_completion,
    read_result_secret
)
from cli_api.runner import run_cmd 

router = APIRouter(prefix="/workflows", tags=["workflows"])

@router.post("/bootstrap-core")
def api_bootstrap_core(req: BootstrapCoreReq, x_api_token: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    require_token(x_api_token)

    run_id = _utc_run_id("core")
    jobs_ns = _jobs_namespace()

    secret_res = create_run_input_secret(
        jobs_namespace=jobs_ns,
        run_id=run_id,
        request_obj=req.model_dump(),
    )
    if secret_res.get("returncode", 1) != 0:
        raise HTTPException(
            status_code=500,
            detail={
                "returncode": 1,
                "step": "create run input secret",
                "stdout": secret_res.get("stdout", ""),
                "stderr": secret_res.get("stderr", ""),
                "detail": secret_res,
            },
        )

    job_res = create_workflow_job(
        jobs_namespace=jobs_ns,
        run_id=run_id,
        secret_name=secret_res["secret_name"],
        runner_image=_runner_image(),
        service_account_name=_runner_sa(),
        extra_env={
            "CLI_API_WORKDIR": "/work",
            "CLI_API_JOBS_NAMESPACE": jobs_ns,
            "WORKFLOW_NAME": "bootstrap-core",
        },
        ttl_seconds_after_finished=3600,
    )

    if job_res.get("returncode", 1) != 0:
        delete_run_input_secret(jobs_namespace=jobs_ns, secret_name=secret_res["secret_name"])
        raise HTTPException(
            status_code=500,
            detail={
                "returncode": 1,
                "step": "create workflow job",
                "stdout": job_res.get("stdout", ""),
                "stderr": job_res.get("stderr", ""),
                "detail": job_res,
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
        pod_name = get_job_pod_name(jobs_ns, job_name)
        logs = get_pod_logs(jobs_ns, pod_name, container="runner", tail=400) if pod_name else None

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

        # Only delete the result secret if we successfully read it
        if result_obj is not None:
            run_cmd(
                ["kubectl", "-n", jobs_ns, "delete", "secret", f"cli-api-result-{run_id}".lower()],
                check=False,
                timeout_s=30,
            )
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
