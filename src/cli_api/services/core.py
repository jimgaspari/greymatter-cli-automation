# src/cli_api/services/core.py
from __future__ import annotations
import base64
from typing import Dict, Any
from pathlib import Path
import logging

from ..runner import run_cmd
from ..greymatter.core_argv import build_gm_create_platform_argv, build_gm_create_operator_argv
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
from ..kubernetes.secrets import (
    create_namespace,
    create_image_pull_secret,
    create_repo_secret,
)
from ..kubernetes.manifests import apply_platform_operator_manifest


def bootstrap_core_impl(req) -> Dict[str, Any]:
    response: Dict[str, Any] = {
        "workflow": "bootstrap-core",
        "repo": req.clone.repo_url,
        "steps": [],
    }

    run_id, workspace_path = create_workspace("core", req.workspace_name)
    response["workspace"] = {"name": run_id, "path": workspace_path}
    
    logging.warning("Starting job %s", run_id)
    
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

    # greymatter create platform
    gm_platform_argv = build_gm_create_platform_argv(req.create_platform)
    gm_platform = run_cmd(gm_platform_argv, timeout_s=600, cwd=dest_path)
    response["steps"].append({"name": "greymatter_create_platform", **gm_platform})
    if gm_platform["returncode"] != 0:
        fail("greymatter create platform", gm_platform)

    logging.info("Greymatter Core has been Created")

    # greymatter create operator (same working dir)
    gm_operator_argv = build_gm_create_operator_argv()
    gm_operator = run_cmd(gm_operator_argv, timeout_s=600, cwd=dest_path)
    response["steps"].append({"name": "greymatter_create_operator", **gm_operator})
    if gm_operator["returncode"] != 0:
        fail("greymatter create operator", gm_operator)
    
    logging.info("Greymatter Core Platform Operator manifest has been Created")

    # Verify .greymatter file
    gm_file = Path(dest_path) / ".greymatter"
    ensure_file_exists(gm_file, step_name="post_check")

    k8s = req.kubernetes
    ns = k8s.namespace

    # Step: create namespace
    ns_res = create_namespace(ns)
    response["steps"].append({"name": "kubectl_create_namespace", **ns_res})
    if ns_res["returncode"] != 0:
        fail("kubectl create namespace", ns_res)

    # Step: image pull secret
    img = k8s.image_pull
    img_res = create_image_pull_secret(
        namespace=ns,
        secret_name=img.secret_name,
        docker_server=img.docker_server,
        docker_username=img.docker_username,
        docker_password=img.docker_password,
    )
    response["steps"].append({"name": "kubectl_image_pull_secret", **img_res})
    if img_res["returncode"] != 0:
        fail("kubectl image pull secret", img_res)

    # Step: repo secret (SSH only for now)
    if k8s.create_repo_secret and req.clone.type == "ssh":
        repo_res = create_repo_secret(
            namespace=ns,
            secret_name=k8s.image_pull.secret_name.replace("image-pull", "core-repo"),
            repo_url=req.clone.repo_url,
            branch=req.git.target_branch or req.git.base_branch,
            known_hosts=req.clone.known_hosts,
            ssh_key=req.clone.ssh_private_key,
        )
        response["steps"].append({"name": "kubectl_repo_secret", **repo_res})
        if repo_res["returncode"] != 0:
            fail("kubectl repo secret", repo_res)

    # Commit + push (optional)
    commit_step = do_commit_push(req, dest_path=dest_path, git_env=git_env, message="chore: bootstrap greymatter core")
    response["steps"].append(commit_step)
    if commit_step.get("returncode") not in (None, 0):
        fail("git commit & push", commit_step)

    operator_apply = apply_platform_operator_manifest(dest_path, ns, git_env=git_env)
    response["steps"].append(operator_apply)
    if operator_apply.get("returncode", 1) != 0:
        fail("greymatter create operator", operator_apply)

    response["artifacts"] = {
        ".greymatter": {"path": str(gm_file), "size_bytes": gm_file.stat().st_size}
    }
    response["result"] = {"platform_created": True, "repo_path": dest_path}
    return response

# Public entrypoint
def bootstrap_core(req):
    return bootstrap_core_impl(req)
