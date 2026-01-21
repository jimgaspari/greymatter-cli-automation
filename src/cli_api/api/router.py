# cli_api/api/router.py
from fastapi import APIRouter

from .routes.runs import router as run_router
from .routes.bootstrap_core import router as bootstrap_core_router
from .routes.bootstrap_tenant import router as bootstrap_tenant_router

api_router = APIRouter()
api_router.include_router(run_router)
api_router.include_router(bootstrap_core_router)
api_router.include_router(bootstrap_tenant_router)
