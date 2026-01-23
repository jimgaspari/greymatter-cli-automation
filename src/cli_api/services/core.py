# src/cli_api/services/core.py
from __future__ import annotations
from typing import Dict, Any
from pathlib import Path
import logging
from importlib import resources

from cli_api.cue.edit_config import update_mesh_metadata_name
from cli_api.runner import run_cmd
from cli_api.greymatter.core_argv import build_gm_create_platform_argv, build_gm_create_operator_argv
from cli_api.services.common import (
    create_workspace,
    build_git_env,
    do_clone,
    do_branch,
    do_identity,
    do_commit_push,
    ensure_file_exists,
    fail,
    check_existing_greymatter_repo
)
from cli_api.kubernetes.secrets import (
    create_namespace,
    create_image_pull_secret,
    create_repo_secret,
    apply_edge_ingress_tls_secret
)
from cli_api.kubernetes.manifests import apply_platform_operator_manifest
from cli_api.prometheus.resolve import resolve_prometheus_endpoint_for_namespace
from cli_api.prometheus.targets import check_prometheus_targets
from cli_api.kubernetes.services import ensure_prometheus_service

def load_spire_overrides_template() -> str:
    return resources.files("cli_api.cue.templates") \
        .joinpath("spire_custom_overrides.cue") \
        .read_text(encoding="utf-8")

def bootstrap_core_impl(req) -> Dict[str, Any]:
    response: Dict[str, Any] = {
        "returncode": 1,  # default to failure until we finish cleanly
        "workflow": "bootstrap-core",
        "repo": req.git.repo_url,
        "steps": [],
    }

    run_id, workspace_path = create_workspace("core", req.workspace_name)
    response["workspace"] = {"name": run_id, "path": workspace_path}

    logging.info("Starting job %s", run_id)

    git_env = build_git_env(req, workspace_path=workspace_path)

    dest_path, clone_step = do_clone(req, run_id=run_id, git_env=git_env, subdir="repo")
    response["steps"].append(clone_step)
    if clone_step["returncode"] != 0:
        return fail("git clone", clone_step, response=response)

    br_step = do_branch(req, dest_path=dest_path, git_env=git_env)
    if br_step:
        response["steps"].append(br_step)
        if br_step["returncode"] != 0:
            return fail("ensure branch", br_step, response=response)

    existing = check_existing_greymatter_repo(dest_path)
    response["steps"].append(existing)

    if existing.get("exists"):
        response["result"] = {
            "skipped": True,
            "reason": "existing_greymatter_repo",
            "message": existing["message"],
            "repo_path": dest_path,
        }
        response["returncode"] = 0
        return response

    id_step = do_identity(req, dest_path=dest_path, git_env=git_env)
    response["steps"].append(id_step)
    if id_step["returncode"] != 0:
        return fail("git identity", id_step, response=response)

    # greymatter create platform
    gm_platform_argv = build_gm_create_platform_argv(req.create_platform)
    gm_platform = run_cmd(gm_platform_argv, timeout_s=600, cwd=dest_path, check=False)
    response["steps"].append({"name": "greymatter_create_platform", **gm_platform})
    if gm_platform["returncode"] != 0:
        return fail("greymatter create platform", gm_platform, response=response)


    config_path = Path(dest_path) / "config.cue"
    edit_res = update_mesh_metadata_name(config_path, req.create_platform.mesh_name)  # or whatever field you want
    response["steps"].append({"name": "edit_config_cue", **edit_res})
    if edit_res["returncode"] != 0:
        return fail("edit config.cue", edit_res, response=response)

    # Conditionally add SPIRE overrides when using a non-default registry
    image_repo = getattr(req.create_platform, "image_repository", "").strip()
    image_host = image_repo.split("/")[0] if image_repo else ""

    if image_host and not image_host.endswith(".download.greymatter.io"):
        overrides_path = Path(dest_path) / "spire_custom_overrides.cue"

        if not overrides_path.exists():
            overrides_content = load_spire_overrides_template()
            overrides_path.write_text(overrides_content, encoding="utf-8")

            response["steps"].append({
                "name": "write_spire_custom_overrides_cue",
                "returncode": 0,
                "stdout": f"Added SPIRE overrides for custom image repository: {image_host}",
                "path": str(overrides_path),
            })
        else:
            response["steps"].append({
                "name": "write_spire_custom_overrides_cue",
                "returncode": 0,
                "stdout": "SPIRE overrides already present; skipping",
                "path": str(overrides_path),
            })

    logging.info("Greymatter Core has been Created")

    # greymatter create operator (same working dir)
    gm_operator_argv = build_gm_create_operator_argv()
    gm_operator = run_cmd(gm_operator_argv, timeout_s=600, cwd=dest_path, check=False)
    response["steps"].append({"name": "greymatter_create_operator", **gm_operator})
    if gm_operator["returncode"] != 0:
        return fail("greymatter create operator", gm_operator, response=response)

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
        return fail("kubectl create namespace", ns_res, response=response)

    # Step: ensure prometheus service exists (ClusterIP)
    prom_svc_res = ensure_prometheus_service(namespace=ns)
    response["steps"].append({"name": "kubectl_apply_prometheus_service", **prom_svc_res})
    if prom_svc_res.get("returncode", 1) != 0:
        return fail("kubectl apply prometheus service", prom_svc_res, response=response)

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
        return fail("kubectl image pull secret", img_res, response=response)

    # Step: repo secret (SSH only for now)
    if k8s.create_repo_secret:
        secret_name = k8s.image_pull.secret_name.replace("image-pull", "core-repo")

        if req.git.type == "ssh":
            repo_res = create_repo_secret(
                namespace=ns,
                secret_name=secret_name,
                repo_url=req.git.repo_url,
                branch=req.git.target_branch or req.git.base_branch,
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
                repo_url=req.git.repo_url,
                branch=req.git.target_branch or req.git.base_branch,
                auth_type="https",
                http_username=http_username,
                http_password=http_password,
                tls_insecure_verify=getattr(req.git, "insecure_skip_tls_verify", False),
            )

        response["steps"].append({"name": "kubectl_repo_secret", **repo_res})
        if repo_res.get("returncode", 1) != 0:
            return fail("kubectl repo secret", repo_res, response=response)

    # Commit + push (optional)
    commit_step = do_commit_push(req, dest_path=dest_path, git_env=git_env, message="chore: bootstrap greymatter core")
    response["steps"].append(commit_step)
    if commit_step.get("returncode") not in (None, 0):
        return fail("git commit & push", commit_step, response=response)

    operator_apply = apply_platform_operator_manifest(dest_path, ns, git_env=git_env)
    response["steps"].append(operator_apply)
    if operator_apply.get("returncode", 1) != 0:
        return fail("apply platform operator manifest", operator_apply, response=response)

        # --- Prometheus targets check (late/post-deploy) ---
    pc = getattr(req, "prometheus_check", None)
    if pc and getattr(pc, "enabled", False):
        # Resolve the Prometheus endpoint based on the Greymatter namespace (ns)
        endpoint, meta = resolve_prometheus_endpoint_for_namespace(
            gm_namespace=ns,
            scheme=getattr(pc, "scheme", "http"),
            port=getattr(pc, "port", 9090),
            service_name=getattr(pc, "service_name", "prometheus"),
            path_prefix=getattr(pc, "path_prefix", ""),
            probe=bool(getattr(pc, "probe", False)),
            probe_timeout_s=float(getattr(pc, "probe_timeout_s", 2.0)),
        )

        if not endpoint:
            resolve_step = {
                "name": "prometheus_resolve_endpoint",
                "returncode": 1,
                "stderr": f"Could not resolve a reachable Prometheus /api/v1/targets endpoint in namespace {ns}",
                "namespace": ns,
                **meta,
            }
            response["steps"].append(resolve_step)
            return fail("prometheus resolve endpoint", resolve_step, response=response)

        resolve_step = {
            "name": "prometheus_resolve_endpoint",
            "returncode": 0,
            "stdout": f"Resolved Prometheus endpoint: {endpoint.url}",
            "namespace": ns,
            "service_name": endpoint.service_name,
            "scheme": endpoint.scheme,
            "port": endpoint.port,
            "path_prefix": endpoint.path_prefix,
            **meta,
        }
        response["steps"].append(resolve_step)

        targets_step = check_prometheus_targets(
            namespace=ns,
            service_name="prometheus",   
            require_all_up=True,
            timeout_s=300,               
            poll_interval_s=5,
            min_active_targets=10
        )

        # Ensure it has a step name for your UI/step viewer
        targets_step.setdefault("name", "prometheus_targets_check")
        response["steps"].append(targets_step)

        if targets_step.get("returncode", 1) != 0:
            return fail("prometheus targets check", targets_step, response=response)

    response["artifacts"] = {
        ".greymatter": {"path": str(gm_file), "size_bytes": gm_file.stat().st_size}
    }
    response["result"] = {"platform_created": True, "repo_path": dest_path}

    response["returncode"] = 0
    return response


# Public entrypoint
def bootstrap_core(req):
    return bootstrap_core_impl(req)
