from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from cli_api.config import settings
from cli_api.runner import run_cmd

router = APIRouter(prefix="/gm", tags=["greymatter"])

def require_token(x_api_token: Optional[str]):
    if not settings.api_token:
        return
    if x_api_token != settings.api_token:
        raise HTTPException(status_code=401, detail="Unauthorized")

class GreymatterCmdReq(BaseModel):
    args: List[str]
    timeout_s: int = 300

@router.post("/run")
def run(req: GreymatterCmdReq, x_api_token: Optional[str] = Header(default=None)):
    require_token(x_api_token)

    if not req.args:
        raise HTTPException(status_code=400, detail="args required")

    # Tighten this to exactly what you allow
    allowed_first = {"deploy", "apply", "diff", "status", "validate", "generate"}
    if req.args[0] not in allowed_first:
        raise HTTPException(status_code=400, detail=f"Unsupported greymatter command: {req.args[0]}")

    argv = ["greymatter"] + req.args
    result = run_cmd(argv, timeout_s=req.timeout_s)
    if result["exit_code"] != 0:
        raise HTTPException(status_code=500, detail=result)
    return result
