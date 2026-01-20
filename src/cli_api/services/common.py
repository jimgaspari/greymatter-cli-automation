# src/cli_api/services/common.py
from __future__ import annotations
from typing import Dict, Any, Optional
from fastapi import HTTPException
from pathlib import Path

from ..config import settings
from ..workflow_utils import make_run_id, ensure_workspace
from ..git.git_cmd_shm import (
    prepare_ssh_auth,
    prepare_https_auth,
    clone_repo,
    ensure_branch,
    ensure_git_identity,
    git_has_changes,
    git_commit_and_push
)

def require_token(x_api_token: Optional[str]):
    if not settings.api_token:
        return
    if x_api_token != settings.api_token:
        raise HTTPException(status_code=401, detail="Unauthorized")

def fail(
    step: str,
    result: Dict[str, Any],
    *,
    response: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Build a structured failure response.

    - Does NOT raise.
    - Always returns a dict with returncode != 0.
    - Can merge into an existing response object.
    """

    failure = {
        "returncode": result.get("returncode", result.get("exit_code", 1) or 1),
        "step": step,
        "stdout": result.get("stdout"),
        "stderr": result.get("stderr"),
        "argv": result.get("argv"),
    }

    # Preserve nested step detail if present
    if "steps" in result:
        failure["steps"] = result["steps"]

    # If caller passed a response object, merge into it
    if response is not None:
        response.update(failure)
        return response

    return failure

def create_workspace(prefix: str, workspace_name: Optional[str]) -> tuple[str, str]:
    run_id = workspace_name or make_run_id(prefix)
    try:
        workspace_path = ensure_workspace(settings.workdir, run_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileExistsError:
        raise HTTPException(status_code=409, detail="workspace already exists; choose a different workspace_name")
    return run_id, workspace_path

def build_git_env(req, workspace_path: str) -> dict:
    if req.clone.type == "ssh":
        ssh_auth = prepare_ssh_auth(
            workspace_path=workspace_path,
            ssh_private_key=req.clone.ssh_private_key,
            known_hosts=req.clone.known_hosts,
            strict_host_key_checking=req.clone.strict_host_key_checking,
        )
        return ssh_auth.env

    # HTTPS (whatever you renamed this to)
    return prepare_https_auth(
        username=req.clone.username,
        password=req.clone.password,
        token=req.clone.token,
    )


def do_clone(req, run_id: str, git_env: dict, subdir: str = "repo") -> tuple[str, Dict[str, Any]]:
    dest_dir = f"{run_id}/{subdir}"
    dest_path, clone_result = clone_repo(
        clone=req.clone,
        dest_dir=dest_dir,
        branch=req.git.base_branch,
        depth=req.depth,
        env=git_env,
    )
    step = {"name": "git_clone", **clone_result, "dest_path": dest_path}
    return dest_path, step

def do_branch(req, dest_path: str, git_env: dict) -> Optional[Dict[str, Any]]:
    if not getattr(req.git, "target_branch", None):
        return None

    br = ensure_branch(
        repo_path=dest_path,
        git_env=git_env,
        base_branch=req.git.base_branch,
        target_branch=req.git.target_branch,
        push_to_remote=req.git.push_branch_to_remote,
    )
    return {"name": "git_ensure_branch", **br}

def do_identity(req, dest_path: str, git_env: dict) -> Dict[str, Any]:
    # allow UI overrides; fallback to defaults
    name = getattr(req.git, "author_name", None) or "Greymatter Automation"
    email = getattr(req.git, "author_email", None) or "greymatter-bot@greymatter.io"

    git_id = ensure_git_identity(
        repo_path=dest_path,
        env=git_env,
        name=name,
        email=email,
    )
    return {"name": "git_identity", **git_id}

def do_commit_push(req, dest_path: str, git_env: dict, message: str) -> Dict[str, Any]:
    # Only push if requested
    if not req.git.push_changes:
        return {"name": "git_commit_push", "skipped": True, "reason": "push_changes=false"}

    if not git_has_changes(dest_path):
        return {"name": "git_commit_push", "skipped": True, "reason": "no changes detected"}

    res = git_commit_and_push(
        repo_path=dest_path,
        message=message,
        env=git_env,
    )
    return {"name": "git_commit_push", **res}

def ensure_file_exists(path: Path, step_name: str):
    if not path.exists():
        raise HTTPException(
            status_code=500,
            detail={
                "step": step_name,
                "error": f"Expected file was not created: {path.name}",
                "expected_path": str(path),
            },
        )
