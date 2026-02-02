from fastapi import APIRouter, Header, HTTPException
from typing import Optional, Any, Dict

from cli_api.api.deps import require_token, _jobs_namespace
from cli_api.kubernetes.jobs import get_job_status, get_job_logs

router = APIRouter(prefix="/runs", tags=["runs"])


@router.get("/{run_id}")
def api_run_status(run_id: str, x_api_token: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    require_token(x_api_token)
    jobs_ns = _jobs_namespace()

    job_name = f"cli-api-{run_id}".lower()

    st = get_job_status(jobs_namespace=jobs_ns, job_name=job_name)
    if st.get("returncode", 1) != 0:
        raise HTTPException(
            status_code=404,
            detail={
                "step": "get_job_status",
                "stdout": st.get("stdout", ""),
                "stderr": st.get("stderr", ""),
                "returncode": st.get("returncode", 1),
            },
        )

    return st["status"]


@router.get("/{run_id}/logs")
def api_run_logs(run_id: str, tail: int = 200, x_api_token: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    require_token(x_api_token)
    jobs_ns = _jobs_namespace()

    job_name = f"cli-api-{run_id}".lower()

    logs = get_job_logs(jobs_namespace=jobs_ns, job_name=job_name, tail_lines=tail)
    if logs.get("returncode", 1) != 0:
        raise HTTPException(
            status_code=404,
            detail={
                "step": "get_job_logs",
                "stdout": logs.get("stdout", ""),
                "stderr": logs.get("stderr", ""),
                "returncode": logs.get("returncode", 1),
            },
        )

    return {
        "run_id": run_id,
        "job_name": job_name,
        "logs": logs.get("stdout", ""),
    }
