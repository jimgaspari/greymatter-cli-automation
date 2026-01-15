from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List, Literal
from pathlib import Path

from ..config import settings
from ..git_ops import git_clone_with_ephemeral_key, git_clone_https
from ..runner import run_cmd
from ..workflow_utils import make_run_id, ensure_workspace
from ..schemas import CloneSpec, CreatePlatformOptions
from ..cli_options import build_gm_create_platform_argv
from ..git_cmd import git_has_changes, git_commit_and_push

router = APIRouter(prefix="/workflows", tags=["workflows"])

def require_token(x_api_token: Optional[str]):
    if not settings.api_token:
        return  # dev only
    if x_api_token != settings.api_token:
        raise HTTPException(status_code=401, detail="Unauthorized")

class WorkflowBaseReq(BaseModel):
    clone: CloneSpec
    branch: Optional[str] = "main"
    depth: int = 1

class BootstrapCoreReq(WorkflowBaseReq):
    # Optional: allow caller to set a stable name; otherwise we generate
    workspace_name: Optional[str] = None
    create_platform: CreatePlatformOptions = Field(default_factory=CreatePlatformOptions)

class BootstrapTenantReq(WorkflowBaseReq):
    workspace_name: Optional[str] = None
    tenant_name: str = Field(min_length=1, description="Tenant identifier/name")
    # Add more tenant params as needed later

def fail(step: str, result: Dict[str, Any]):
    raise HTTPException(status_code=500, detail={"step": step, **result})

@router.post("/bootstrap-core")
def bootstrap_core(req: BootstrapCoreReq, x_api_token: Optional[str] = Header(default=None)):
    require_token(x_api_token)

    response: Dict[str, Any] = {
        "workflow": "bootstrap-core",
        "repo": req.repo_ssh_url,
        "branch": req.branch,
        "depth": req.depth,
    }

    # Step 0: Create unique workspace
    run_id = req.workspace_name or make_run_id("core")
    try:
        workspace_path = ensure_workspace(settings.workdir, run_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileExistsError:
        raise HTTPException(status_code=409, detail="workspace already exists; choose a different workspace_name")

    response["workspace"] = {"name": run_id, "path": workspace_path}

    # Step 1: Clone repo into workspace_path/repo
    dest_dir = f"{run_id}/repo"

    dest_path, clone_result = clone_repo(
        clone=req.clone,
        dest_dir=dest_dir,
        branch=req.branch,
        depth=req.depth,
    )
    response["steps"].append({"name": "git_clone", **clone_result, "dest_path": dest_path})
    if clone_result["exit_code"] != 0:
        fail("git clone", clone_result)

    # Step 2: greymatter create platform
    gm_argv = build_gm_create_platform_argv(req.create_platform)
    gm_result = run_cmd(gm_argv, timeout_s=600, cwd=dest_path)
    response["steps"].append({"name": "greymatter_create_platform", **gm_result})
    if gm_result["exit_code"] != 0:
        fail("greymatter create platform", gm_result)
    
    # Step 3: Verify the .greymatter file
    gm_file = Path(dest_path) / ".greymatter"

    if not gm_file.exists():
        raise HTTPException(
            status_code=500,
            detail={
                "step": "post_check",
                "error": "Expected .greymatter file was not created",
                "expected_path": str(gm_file),
            },
        )
    # Step4: git commit + push (if changes exist)
    if git_has_changes(dest_path):
        commit_msg = "chore: bootstrap greymatter core"

        git_push_result = git_commit_and_push(
            repo_path=dest_path,
            message=commit_msg,
            env=git_env,  # <- reuse clone credentials
        )

        response["steps"].append({
            "name": "git_commit_push",
            **git_push_result,
        })

        if git_push_result.get("exit_code") != 0:
            fail("git commit & push", git_push_result)
    else:
        response["steps"].append({
            "name": "git_commit_push",
            "skipped": True,
            "reason": "no changes detected",
        })

    # Optional: basic metadata (safe)
    response["artifacts"] = {
        ".greymatter": {
            "path": str(gm_file),
            "size_bytes": gm_file.stat().st_size,
        }
    }
    response["result"] = {"platform_created": True, "repo_path": dest_path}
    return response

@router.post("/bootstrap-tenant")
def bootstrap_tenant(req: BootstrapTenantReq, x_api_token: Optional[str] = Header(default=None)):
    require_token(x_api_token)

    response: Dict[str, Any] = {
        "workflow": "bootstrap-tenant",
        "repo": req.repo_ssh_url,
        "dest_dir": req.dest_dir,
        "tenant_name": req.tenant_name,
    }

    # Step 1: clone
    dest_dir = f"{run_id}/tenant"

    dest_path, clone_result = clone_repo(
        clone=req.clone,
        dest_dir=dest_dir,
        branch=req.branch,
        depth=req.depth,
    )
    response["steps"].append({"name": "git_clone", **clone_result, "dest_path": dest_path})
    if clone_result["exit_code"] != 0:
        fail("git clone", clone_result)
    # Step 2: greymatter create tenant <name>
    # Adjust argv if your CLI uses a different syntax.
    gm_argv = ["greymatter", "create", "project", req.tenant_name]
    gm_result = run_cmd(gm_argv, timeout_s=300, cwd=dest_path)
    response["greymatter_create_project"] = gm_result
    if gm_result["exit_code"] != 0:
        _fail("greymatter create project", gm_result)

    return response
