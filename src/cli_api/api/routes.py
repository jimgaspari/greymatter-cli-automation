from fastapi import APIRouter, Header, HTTPException
from typing import Optional, Any, Dict
import datetime as dt

from ..config import settings
from ..schemas import BootstrapCoreReq, BootstrapTenantReq

from ..kubernetes.input_secrets import create_run_input_secret, delete_run_input_secret
from ..kubernetes.jobs import create_workflow_job, get_job_status, get_job_logs


router = APIRouter()


def require_token(x_api_token: Optional[str]):
    if not settings.api_token:
        return
    if x_api_token != settings.api_token:
        raise HTTPException(status_code=401, detail="Unauthorized")


def _utc_run_id(prefix: str) -> str:
    return f"{prefix}-{dt.datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}"


def _jobs_namespace() -> str:
    # Prefer configured jobs namespace; fall back to default
    return getattr(settings, "jobs_namespace", None) or "cli-api-jobs"


def _runner_image() -> str:
    # Prefer dedicated runner image if configured, else use API image
    return getattr(settings, "runner_image", None) or "cli-api:dev"


def _runner_sa() -> str:
    # The privileged SA that actually performs kubectl/cluster changes
    return getattr(settings, "runner_service_account", None) or "cli-api-job-runner"


@router.post("/workflows/bootstrap-core")
def api_bootstrap_core(req: BootstrapCoreReq, x_api_token: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    require_token(x_api_token)

    run_id = _utc_run_id("core")
    jobs_ns = _jobs_namespace()

    # Store the full request payload (incl ssh key/known_hosts/docker creds) in a Secret
    secret_res = create_run_input_secret(
        jobs_namespace=jobs_ns,
        run_id=run_id,
        request_obj=req.model_dump(),  # pydantic v2; if v1 use req.dict()
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

    # Create the runner Job
    job_res = create_workflow_job(
        jobs_namespace=jobs_ns,
        run_id=run_id,
        secret_name=secret_res["secret_name"],
        runner_image=_runner_image(),
        service_account_name=_runner_sa(),
        extra_env={
            "CLI_API_WORKDIR": "/work",
            "CLI_API_JOBS_NAMESPACE": jobs_ns,
            # optional: let job_main choose which workflow to run
            "WORKFLOW_NAME": "bootstrap-core",
        },
        ttl_seconds_after_finished=3600,
    )

    if job_res.get("returncode", 1) != 0:
        # best-effort cleanup secret if job create fails
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


@router.post("/workflows/bootstrap-tenant")
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


@router.get("/runs/{run_id}")
def api_run_status(run_id: str, x_api_token: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    require_token(x_api_token)
    jobs_ns = _jobs_namespace()

    # Must match jobs.py naming: _dns1123(f"cli-api-{run_id}")
    job_name = f"cli-api-{run_id}".lower()

    st = get_job_status(jobs_namespace=jobs_ns, job_name=job_name)
    if st.get("returncode", 1) != 0:
        raise HTTPException(
            status_code=404,
            detail={
                "step": "get job status",
                "stdout": st.get("stdout", ""),
                "stderr": st.get("stderr", ""),
                "returncode": st.get("returncode", 1),
            },
        )

    return st["status"]


@router.get("/runs/{run_id}/logs")
def api_run_logs(run_id: str, tail: int = 200, x_api_token: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    require_token(x_api_token)
    jobs_ns = _jobs_namespace()
    job_name = f"cli-api-{run_id}".lower()

    logs = get_job_logs(jobs_namespace=jobs_ns, job_name=job_name, tail_lines=tail)
    if logs.get("returncode", 1) != 0:
        raise HTTPException(
            status_code=404,
            detail={
                "step": "get job logs",
                "stdout": logs.get("stdout", ""),
                "stderr": logs.get("stderr", ""),
                "returncode": logs.get("returncode", 1),
            },
        )

    return {"run_id": run_id, "job_name": job_name, "logs": logs.get("stdout", "")}
