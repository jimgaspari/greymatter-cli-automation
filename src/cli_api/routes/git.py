from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from cli_api.config import settings
from cli_api.runner import run_cmd

router = APIRouter(prefix="/git", tags=["git"])

def require_token(x_api_token: Optional[str]):
    if not settings.api_token:
        return  # dev mode (not recommended)
    if x_api_token != settings.api_token:
        raise HTTPException(status_code=401, detail="Unauthorized")

class GitCloneReq(BaseModel):
    repo_url: str
    dest_dir: str = Field(default="repo")
    branch: Optional[str] = None
    depth: int = 1

@router.post("/clone")
def clone(req: GitCloneReq, x_api_token: Optional[str] = Header(default=None)):
    require_token(x_api_token)

    if not (req.repo_url.startswith("https://") or req.repo_url.startswith("git@")):
        raise HTTPException(status_code=400, detail="repo_url must be https:// or git@ style")

    argv = ["git", "clone", "--depth", str(req.depth)]
    if req.branch:
        argv += ["--branch", req.branch]
    argv += [req.repo_url, req.dest_dir]

    result = run_cmd(argv, timeout_s=120)
    if result["exit_code"] != 0:
        raise HTTPException(status_code=500, detail=result)
    return result
