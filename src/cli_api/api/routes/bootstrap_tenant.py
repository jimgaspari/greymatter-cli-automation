from fastapi import APIRouter, Header, HTTPException
from typing import Optional, Any, Dict
import datetime as dt

from cli_api.schemas import BootstrapTenantReq
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
    create_workflow_job,
)
from cli_api.runner import run_cmd 

router = APIRouter(prefix="/workflows", tags=["workflows"])

@router.post("/bootstrap-tenant")
def api_bootstrap_tenant(req: BootstrapTenantReq, x_api_token: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    require_token(x_api_token)

    run_id = _utc_run_id("tenant")
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
                "step": "create run input secret",
                "stdout": secret_res.get("stdout", ""),
                "stderr": secret_res.get("stderr", ""),
                "returncode": secret_res.get("returncode", 1),
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
            "WORKFLOW_NAME": "bootstrap-tenant",
        },
        ttl_seconds_after_finished=3600,
    )

    if job_res.get("returncode", 1) != 0:
        delete_run_input_secret(jobs_namespace=jobs_ns, secret_name=secret_res["secret_name"])
        raise HTTPException(
            status_code=500,
            detail={
                "step": "create workflow job",
                "stdout": job_res.get("stdout", ""),
                "stderr": job_res.get("stderr", ""),
                "returncode": job_res.get("returncode", 1),
            },
        )

    return {
        "run_id": run_id,
        "jobs_namespace": jobs_ns,
        "job_name": job_res["job_name"],
        "secret_name": secret_res["secret_name"],
    }

