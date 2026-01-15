from fastapi import APIRouter, Header, HTTPException
from typing import Optional

from ..config import settings
from ..schemas import BootstrapCoreReq, BootstrapTenantReq
from ..services.workflows import bootstrap_core, bootstrap_tenant

router = APIRouter()

def require_token(x_api_token: Optional[str]):
    if not settings.api_token:
        return
    if x_api_token != settings.api_token:
        raise HTTPException(status_code=401, detail="Unauthorized")

@router.post("/workflows/bootstrap-core")
def api_bootstrap_core(req: BootstrapCoreReq, x_api_token: Optional[str] = Header(default=None)):
    require_token(x_api_token)
    return bootstrap_core(req, x_api_token)

@router.post("/workflows/bootstrap-tenant")
def api_bootstrap_tenant(req: BootstrapTenantReq, x_api_token: Optional[str] = Header(default=None)):
    require_token(x_api_token)
    return bootstrap_tenant(req, x_api_token)
