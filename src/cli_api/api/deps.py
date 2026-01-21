from fastapi import Header, HTTPException
from typing import Optional
import datetime as dt

from ..config import settings

def require_token(x_api_token: Optional[str]):
    if not settings.api_token:
        return
    if x_api_token != settings.api_token:
        raise HTTPException(status_code=401, detail="Unauthorized")

def token_header(x_api_token: Optional[str] = Header(default=None)) -> Optional[str]:
    # Helper so we can use Depends(token_header)
    return x_api_token

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
