# src/cli_api/services/tenant.py
from __future__ import annotations
from typing import Dict, Any
from pathlib import Path
import logging

from cli_api.runner import run_cmd
from cli_api.schemas import BootstrapTenantReq, GitConfig, TenantItem
from cli_api.greymatter.project_argv import build_gm_create_project_argv
from cli_api.services.common import (
    create_workspace,
    build_git_env,
    do_clone,
    do_branch,
    do_identity,
    do_commit_push,
    fail,
    ensure_file_exists
)
from cli_api.kubernetes.secrets import (
    create_namespace,
    create_repo_secret,
    apply_edge_ingress_tls_secret
)

def bootstrap_tenant_impl(*, req: BootstrapTenantReq, tenant: TenantItem, git: GitConfig) -> dict:
    """
    Bootstrap a Greymatter tenant by running:
        greymatter create project <namespace> [--openshift] [--security <...>]

    NOTE: <namespace> is the authoritative tenant name.
    """
    response: Dict[str, Any] = {
        "returncode": 1,  # default to failure until done
        "workflow": "bootstrap-tenant",
        "repo": req.git.repo_url,
        "steps": [],
    }

    # Namespace is the tenant name (per your requirement)
    tenant_ns = (tenant.namespace or "").strip()
    logging.info("Tenant Namespace is %s", tenant_ns)
    if not tenant_ns:
        step = {"returncode": 1, "stderr": "namespace is required for bootstrap-tenant"}
        response["steps"].append({"name": "validate_namespace", **step})
        return fail("validate namespace", step, response=response)

    response["tenant"] = {
        "name": tenant_ns,
        "namespace": tenant_ns,
        "security": getattr(req, "security", "spire"),
        "openshift": bool(getattr(req, "openshift", False)),
    }
    
    req = req.model_copy(update={"git": git})

    run_id, workspace_path = create_workspace("tenant", req.workspace_name)
    response["workspace"] = {"name": run_id, "path": workspace_path}
    logging.info("Starting job %s", run_id)

    git_env = build_git_env(req, workspace_path=workspace_path)

    dest_path, clone_step = do_clone(req, run_id=run_id, git_env=git_env, subdir="repo")
    response["steps"].append(clone_step)
    if clone_step.get("returncode", 1) != 0:
        return fail("git clone", clone_step, response=response)
    logging.info("STEP git_clone rc=%s", clone_step.get("returncode"))

    br_step = do_branch(req, dest_path=dest_path, git_env=git_env)
    if br_step:
        response["steps"].append(br_step)
        if br_step.get("returncode", 1) != 0:
            return fail("ensure branch", br_step, response=response)

    id_step = do_identity(req, dest_path=dest_path, git_env=git_env)
    response["steps"].append(id_step)
    if id_step.get("returncode", 1) != 0:
        return fail("git identity", id_step, response=response)
    
    # Build argv: greymatter create project <namespace> [--openshift] [--security ...]
    cp = getattr(req, "create_project", None)
    gm_argv = build_gm_create_project_argv(namespace=tenant_ns, create_project=cp)

    gm_res = run_cmd(gm_argv, timeout_s=600, cwd=dest_path, check=False)
    response["steps"].append({"name": "greymatter_create_project", "argv": gm_argv, **gm_res})
    if gm_res.get("returncode", 1) != 0:
        return fail("greymatter create project", gm_res, response=response)
    logging.info("STEP greymatter_create_project rc=%s", gm_res.get("returncode"))

    # Verify .greymatter file
    gm_file = Path(dest_path) / ".greymatter"
    ensure_file_exists(gm_file, step_name="post_check")

        # Optional: run mounted tenant script (ConfigMap volume mounted at /scripts)
    script_cfg = getattr(getattr(req, "create_project", None), "script", None)
    if script_cfg and bool(getattr(script_cfg, "enabled", False)):
        script_mount_dir = str(getattr(script_cfg, "mount_dir", "/scripts") or "/scripts")
        script_filename = str(getattr(script_cfg, "filename", "bootstrap.sh") or "bootstrap.sh")
        script_path = str(Path(script_mount_dir) / script_filename)

        # Ensure the file is present in the container
        ls_step = run_cmd(
            ["bash", "-lc", f"ls -la {script_mount_dir} && test -f {script_path}"],
            timeout_s=30,
            cwd=dest_path,   # keep context in repo root
            check=False,
        )
        response["steps"].append({"name": "tenant_script_verify_mount", "script_path": script_path, **ls_step})
        if ls_step.get("returncode", 1) != 0:
            return fail("verify tenant script mount", ls_step, response=response)

        # Execute the script from the repo root so `.greymatter` is found
        run_step = run_cmd(
            ["bash", "-lc", script_path],
            timeout_s=1800,  # adjust as needed
            cwd=dest_path,
            check=False,
        )
        response["steps"].append({"name": "tenant_script_execute", "script_path": script_path, **run_step})
        if run_step.get("returncode", 1) != 0:
            return fail("execute tenant script", run_step, response=response)
        
    commit_step = do_commit_push(
        req,
        dest_path=dest_path,
        git_env=git_env,
        message=f"chore: bootstrap tenant {tenant_ns}",
    )
    response["steps"].append(commit_step)
    if commit_step.get("returncode") not in (None, 0):
        return fail("git commit & push", commit_step, response=response)
    logging.info("STEP git_push rc=%s", commit_step.get("returncode"))

    ns = tenant_ns
    k8s = req.kubernetes
    # Step: create namespace
    ns_res = create_namespace(ns)
    response["steps"].append({"name": "kubectl_create_namespace", **ns_res})
    if ns_res["returncode"] != 0:
        return fail("kubectl create namespace", ns_res, response=response)
    
    # Optional: create greymatter-edge-ingress TLS secret
    edge = getattr(k8s, "edge_ingress_tls_secret", None)
    if edge and getattr(edge, "enabled", False):
        missing = []
        if not getattr(edge, "tls_crt", None):
            missing.append("tls_crt")
        if not getattr(edge, "tls_key", None):
            missing.append("tls_key")
        if missing:
            step = {
                "returncode": 1,
                "stderr": f"edge_ingress_tls_secret.enabled=true but missing: {', '.join(missing)}",
            }
            response["steps"].append({"name": "kubectl_apply_edge_ingress_tls_secret", **step})
            return fail("apply edge ingress tls secret", step, response=response)

        sec_res = apply_edge_ingress_tls_secret(
            namespace=ns,
            secret_name=edge.secret_name,
            tls_crt_pem=edge.tls_crt,
            tls_key_pem=edge.tls_key,
            ca_crt_pem=getattr(edge, "ca_crt", None),
        )
        
        # IMPORTANT: do not include PEMs in response
        response["steps"].append({"name": "kubectl_apply_edge_ingress_tls_secret", **sec_res})
        if sec_res.get("returncode", 1) != 0:
            return fail("apply edge ingress tls secret", sec_res, response=response)

    if k8s.create_repo_secret:
        secret_name = "greymatter-admin-sync"

        if git.type == "ssh":
            repo_res = create_repo_secret(
                namespace=ns,
                secret_name=secret_name,
                repo_url=git.repo_url,
                branch=git.target_branch or git.base_branch,
                auth_type="ssh",
                known_hosts=req.git.known_hosts,
                ssh_key=req.git.ssh_private_key,
            )
        else:
            # HTTPS (token preferred; password fallback)
            http_password = req.git.token or req.git.password
            http_username = req.git.username or ("oauth2" if req.git.token else "")

            if not http_password:
                return fail(
                    "kubectl repo secret",
                    {
                        "returncode": 1,
                        "stderr": "HTTPS clone selected but no clone.token or clone.password provided",
                        "step": "kubectl repo secret",
                    },
                    response=response,
                )

            repo_res = create_repo_secret(
                namespace=ns,
                secret_name=secret_name,
                repo_url=git.repo_url,
                branch=git.target_branch or git.base_branch,
                auth_type="https",
                http_username=http_username,
                http_password=http_password,
                tls_insecure_verify=getattr(req.git, "insecure_skip_tls_verify", False),
            )
    
    response["result"] = {"tenant_created": True, "repo_path": dest_path, "tenant": tenant_ns}
    response["returncode"] = 0
    return response


# Public entrypoint (kept for compatibility with existing imports)
def bootstrap_tenant(req):
    return bootstrap_tenant_impl(req)
