# src/cli_api/services/core.py
from __future__ import annotations

from typing import Dict, Any
from pathlib import Path

from ..runner import run_cmd
from ..cli_options import build_gm_create_platform_argv, build_gm_create_operator_argv

from .common import (
    create_workspace,
    build_git_env,
    do_clone,
    do_branch,
    do_identity,
    do_commit_push,
    ensure_file_exists,
    fail,
)

def bootstrap_core_impl(req) -> Dict[str, Any]:
    response: Dict[str, Any] = {
        "workflow": "bootstrap-core",
        "repo": req.clone.repo_url,
        "steps": [],
    }

    run_id, workspace_path = create_workspace("core", req.workspace_name)
    response["workspace"] = {"name": run_id, "path": workspace_path}

    git_env = build_git_env(req, workspace_path=workspace_path)

    dest_path, clone_step = do_clone(req, run_id=run_id, git_env=git_env, subdir="repo")
    response["steps"].append(clone_step)
    if clone_step["exit_code"] != 0:
        fail("git clone", clone_step)

    br_step = do_branch(req, dest_path=dest_path, git_env=git_env)
    if br_step:
        response["steps"].append(br_step)
        if br_step["exit_code"] != 0:
            fail("ensure branch", br_step)

    id_step = do_identity(req, dest_path=dest_path, git_env=git_env)
    response["steps"].append(id_step)
    if id_step["exit_code"] != 0:
        fail("git identity", id_step)

    # greymatter create platform
    gm_platform_argv = build_gm_create_platform_argv(req.create_platform)
    gm_platform = run_cmd(gm_platform_argv, timeout_s=600, cwd=dest_path)
    response["steps"].append({"name": "greymatter_create_platform", **gm_platform})
    if gm_platform["exit_code"] != 0:
        fail("greymatter create platform", gm_platform)

    # greymatter create operator (same working dir)
    gm_operator_argv = build_gm_create_operator_argv()
    gm_operator = run_cmd(gm_operator_argv, timeout_s=600, cwd=dest_path)
    response["steps"].append({"name": "greymatter_create_operator", **gm_operator})
    if gm_operator["exit_code"] != 0:
        fail("greymatter create operator", gm_operator)

    # Verify .greymatter file
    gm_file = Path(dest_path) / ".greymatter"
    ensure_file_exists(gm_file, step_name="post_check")

    # Commit + push (optional)
    commit_step = do_commit_push(req, dest_path=dest_path, git_env=git_env, message="chore: bootstrap greymatter core")
    response["steps"].append(commit_step)
    if commit_step.get("exit_code") not in (None, 0):
        fail("git commit & push", commit_step)

    response["artifacts"] = {
        ".greymatter": {"path": str(gm_file), "size_bytes": gm_file.stat().st_size}
    }
    response["result"] = {"platform_created": True, "repo_path": dest_path}
    return response

# Public entrypoint
def bootstrap_core(req):
    return bootstrap_core_impl(req)
