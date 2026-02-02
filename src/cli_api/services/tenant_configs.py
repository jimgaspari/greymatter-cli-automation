from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from cli_api.runner import run_cmd
from cli_api.services.common import (
    create_workspace,
    build_git_env,
    do_clone,
    do_branch,
    do_identity,
    do_commit_push,
    fail,
)
from cli_api.cue.edit_config import update_tenant_namespaces


def _b64_to_str(b64val: Optional[str]) -> Optional[str]:
    if not b64val:
        return None
    try:
        return base64.b64decode(b64val).decode("utf-8")
    except Exception:
        return None


def _load_core_repo_secret(
    *,
    core_namespace: str,
    secret_name: str = "greymatter-core-repo",
) -> Dict[str, Any]:
    """
    Reads greymatter-core-repo in core_namespace.
    Expects keys:
      auth_type, branch, http_password, http_username, tls_insecure_verify, url
    """
    res = run_cmd(
        ["kubectl", "-n", core_namespace, "get", "secret", secret_name, "-o", "json"],
        check=False,
        timeout_s=30,
    )
    if res.get("returncode", 1) != 0:
        return {"returncode": 1, "step": "kubectl_get_core_repo_secret", **res}

    try:
        secret_obj = json.loads(res.get("stdout") or "{}")
    except Exception as e:
        return {"returncode": 1, "step": "parse_core_repo_secret_json", "stderr": str(e)}

    data = secret_obj.get("data") or {}
    if not isinstance(data, dict):
        return {"returncode": 1, "step": "read_core_repo_secret_data", "stderr": "Secret .data missing/invalid"}

    auth_type = (_b64_to_str(data.get("auth_type")) or "").strip().lower()
    branch = (_b64_to_str(data.get("branch")) or "").strip() or "main"
    url = (_b64_to_str(data.get("url")) or "").strip()

    http_username = (_b64_to_str(data.get("http_username")) or "").strip() or "oauth2"
    http_password = (_b64_to_str(data.get("http_password")) or "").strip()

    tls_insecure_verify_raw = (_b64_to_str(data.get("tls_insecure_verify")) or "false").strip().lower()
    tls_insecure_verify = tls_insecure_verify_raw in ("1", "true", "yes", "y")

    if not url:
        return {"returncode": 1, "step": "validate_core_repo_secret", "stderr": "core repo secret missing url"}

    if auth_type not in ("https", "ssh"):
        auth_type = "https" if url.startswith("http") else "ssh"

    if auth_type == "https" and not http_password:
        return {"returncode": 1, "step": "validate_core_repo_secret", "stderr": "core repo secret missing http_password"}

    return {
        "returncode": 0,
        "auth_type": auth_type,
        "url": url,
        "branch": branch,
        "http_username": http_username,
        "http_password": http_password,
        "tls_insecure_verify": tls_insecure_verify,
        "secret_name": secret_name,
        "core_namespace": core_namespace,
    }


def tenant_config_impl(*, payload: Dict[str, Any], jobs_namespace: str) -> Dict[str, Any]:
    core_ns = (payload.get("core_namespace") or "").strip()
    tenant_ns = (payload.get("tenant_namespace") or payload.get("namespace") or "").strip()

    resp: Dict[str, Any] = {
        "returncode": 1,
        "workflow": "tenant-config",
        "step": "start",
        "core_namespace": core_ns,
        "tenant_namespace": tenant_ns,
        "steps": [],
    }

    if not core_ns or not tenant_ns:
        resp["step"] = "validate_payload"
        resp["stderr"] = "core_namespace and tenant_namespace are required"
        return resp

    # 1) Read core repo secret from the core namespace
    core_repo = _load_core_repo_secret(core_namespace=core_ns, secret_name="greymatter-core-repo")
    resp["steps"].append({"name": "read_core_repo_secret", **core_repo})
    if core_repo.get("returncode", 1) != 0:
        resp["step"] = "read_core_repo_secret"
        resp["stderr"] = core_repo.get("stderr", "failed to read core repo secret")
        return resp

    repo_url = core_repo["url"]
    branch = core_repo["branch"]
    git_type = core_repo["auth_type"]
    tls_insecure = bool(core_repo.get("tls_insecure_verify", False))

    # 2) Workspace + clone
    run_id, workspace_path = create_workspace("tenant-config", tenant_ns)
    resp["workspace"] = {"name": run_id, "path": workspace_path}
    logging.warning("tenant-config job %s starting", run_id)

    # Shim req.git so your existing helpers work
    class _Git:
        def __init__(self) -> None:
            self.repo_url = repo_url
            self.type = git_type
            self.base_branch = branch
            self.target_branch = branch
            self.depth = 1
            self.create_branch_if_missing = True
            self.push_branch_to_remote = True
            self.push_changes = True
            self.insecure_skip_tls_verify = tls_insecure
            self.author_name = "Greymatter Automation"
            self.author_email = "greymatter-bot@greymatter.io"
            
            if git_type == "https":
                self.username = core_repo.get("http_username") or "oauth2"
                self.token = core_repo.get("http_password")
                self.password = None
                
            else:
                # If you ever use ssh secrets later, wire those keys in here
                self.username = None
                self.known_hosts = None
                self.ssh_private_key = None

    class _Req:
        def __init__(self) -> None:
            self.git = _Git()
            self.workspace_name = tenant_ns

    req = _Req()
    git_env = build_git_env(req, workspace_path=workspace_path)

    dest_path, clone_step = do_clone(req, run_id=run_id, git_env=git_env, subdir="repo")
    resp["steps"].append(clone_step)
    if clone_step.get("returncode", 1) != 0:
        return fail("git clone", clone_step, response=resp)

    br_step = do_branch(req, dest_path=dest_path, git_env=git_env)
    if br_step:
        resp["steps"].append(br_step)
        if br_step.get("returncode", 1) != 0:
            return fail("ensure branch", br_step, response=resp)

    id_step = do_identity(req, dest_path=dest_path, git_env=git_env)
    resp["steps"].append(id_step)
    if id_step.get("returncode", 1) != 0:
        return fail("git identity", id_step, response=resp)

    # 3) Edit config.cue
    config_path = Path(dest_path) / "config.cue"
    edit_step = update_tenant_namespaces(config_path, tenant_ns)
    resp["steps"].append({"name": "edit_config_cue_tenant_namespaces", **edit_step})
    if edit_step.get("returncode", 1) != 0:
        return fail("edit config.cue tenant_namespaces", edit_step, response=resp)

    # 4) Commit + push
    commit_step = do_commit_push(
        req,
        dest_path=dest_path,
        git_env=git_env,
        message=f"chore: add tenant namespace {tenant_ns}",
    )
    resp["steps"].append(commit_step)
    if commit_step.get("returncode") not in (None, 0):
        return fail("git commit & push", commit_step, response=resp)

    resp["step"] = "tenant_config_done"
    resp["result"] = {"core_namespace": core_ns, "repo_url": repo_url, "branch": branch, "tenant_added": tenant_ns}
    resp["returncode"] = 0
    return resp
