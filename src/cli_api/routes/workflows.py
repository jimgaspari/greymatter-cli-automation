# src/cli_api/routes/workflows.py
from fastapi import APIRouter, Header
from typing import Optional

from ..schemas import BootstrapCoreReq, BootstrapTenantReq
from ..services.common import require_token
from ..services.core import bootstrap_core_impl
from ..services.tenant import bootstrap_tenant_impl

router = APIRouter(prefix="/workflows", tags=["workflows"])

@router.post("/bootstrap-core")
def bootstrap_core(req: BootstrapCoreReq, x_api_token: Optional[str] = Header(default=None)):
    require_token(x_api_token)
    return bootstrap_core_impl(req)

@router.post("/bootstrap-tenant")
def bootstrap_tenant(req: BootstrapTenantReq, x_api_token: Optional[str] = Header(default=None)):
    require_token(x_api_token)
    return bootstrap_tenant_impl(req)
