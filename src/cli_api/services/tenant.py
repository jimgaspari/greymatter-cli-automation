# src/cli_api/services/tenant.py
from __future__ import annotations

from typing import Dict, Any

from ..runner import run_cmd

from .common import (
    create_workspace,
    build_git_env,
    do_clone,
    do_branch,
    do_identity,
    do_commit_push,
    fail,
)

def bootstrap_tenant_impl(req) -> Dict[str, Any]:
    response: Dict[str, Any] = {
        "workflow": "bootstrap-tenant",
        "repo": req.clone.repo_url,
        "tenant_name": req.tenant_name,
        "steps": [],
    }

    run_id, workspace_path = create_workspace("tenant", req.workspace_name)
    response["workspace"] = {"name": run_id, "path": workspace_path}

    git_env = build_git_env(req, workspace_path=workspace_path)

    dest_path, clone_step = do_clone(req, run_id=run_id, git_env=git_env, subdir="repo")
    response["steps"].append(clone_step)
    if clone_step["returncode"] != 0:
        fail("git clone", clone_step)

    br_step = do_branch(req, dest_path=dest_path, git_env=git_env)
    if br_step:
        response["steps"].append(br_step)
        if br_step["returncode"] != 0:
            fail("ensure branch", br_step)

    id_step = do_identity(req, dest_path=dest_path, git_env=git_env)
    response["steps"].append(id_step)
    if id_step["returncode"] != 0:
        fail("git identity", id_step)

    # TODO: replace this with the real tenant command you want.
    # You had: greymatter create project <tenant_name>
    gm_argv = ["greymatter", "create", "project", req.tenant_name]
    gm_result = run_cmd(gm_argv, timeout_s=600, cwd=dest_path)
    response["steps"].append({"name": "greymatter_create_project", **gm_result})
    if gm_result["returncode"] != 0:
        fail("greymatter create project", gm_result)

    commit_step = do_commit_push(req, dest_path=dest_path, git_env=git_env, message=f"chore: bootstrap tenant {req.tenant_name}")
    response["steps"].append(commit_step)
    if commit_step.get("returncode") not in (None, 0):
        fail("git commit & push", commit_step)

    response["result"] = {"tenant_created": True, "repo_path": dest_path}
    return response

def bootstrap_tenant(req):
    return bootstrap_tenant_impl(req)
