from fastapi import APIRouter, Header, HTTPException
from typing import Optional, Any, Dict
import datetime as dt

from cli_api.api.deps import (
    require_token, 
    _jobs_namespace, 
)

from cli_api.runner import run_cmd 

router = APIRouter(prefix="/runs", tags=["runs"])

@router.get("/{run_id}")
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
                "step": "get job logs",
                "stdout": logs.get("stdout", ""),
                "stderr": logs.get("stderr", ""),
                "returncode": logs.get("returncode", 1),
            },
        )

    return {"run_id": run_id, "job_name": job_name, "logs": logs.get("stdout", "")}
