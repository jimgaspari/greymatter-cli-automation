from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from typing import Optional
import tempfile
from cli_api.config import settings
from cli_api.runner import run_cmd

router = APIRouter(prefix="/kubectl", tags=["kubectl"])

def require_token(x_api_token: Optional[str]):
    if not settings.api_token:
        return
    if x_api_token != settings.api_token:
        raise HTTPException(status_code=401, detail="Unauthorized")

class KubectlApplyReq(BaseModel):
    namespace: str = "default"
    manifest_yaml: str
    validate: bool = True

@router.post("/apply")
def apply(req: KubectlApplyReq, x_api_token: Optional[str] = Header(default=None)):
    require_token(x_api_token)

    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        f.write(req.manifest_yaml)
        path = f.name

    argv = ["kubectl", "apply", "-n", req.namespace, "-f", path]
    if not req.validate:
        argv += ["--validate=false"]

    result = run_cmd(argv, timeout_s=120)
    if result["exit_code"] != 0:
        raise HTTPException(status_code=500, detail=result)
    return result
