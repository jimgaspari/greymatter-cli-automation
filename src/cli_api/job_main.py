# cli_api/job_main.py
from __future__ import annotations

import base64
import json
import logging
import os
import sys
import traceback
from pathlib import Path
from typing import Any, Dict, Optional

from cli_api.runner import run_cmd
from cli_api.config import settings
from cli_api.schemas import BootstrapCoreReq, BootstrapTenantReq, GitConfig
from cli_api.services.core import bootstrap_core_impl
from cli_api.services.tenant import bootstrap_tenant_impl
from cli_api.services.tenant_configs import tenant_config_impl
from cli_api.kubernetes.check_installs import check_spire_installed, check_greymatter_installed
from cli_api.git.repo import ensure_gitea_repo, parse_git_repo_url

RESULT_PATH = os.getenv("CLI_API_RESULT_PATH", "/outputs/result.json")
JOBS_NS = os.getenv("CLI_API_JOBS_NAMESPACE", "cli-api-jobs")


def _read_json_file(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_result_file(result: Dict[str, Any]) -> None:
    p = Path(RESULT_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    logging.info("Wrote result file: %s (%d bytes)", str(p), p.stat().st_size)


def log_result_summary(result: Dict[str, Any]) -> None:
    rc = result.get("returncode", 1)
    step = result.get("step") or result.get("workflow_step") or "unknown"
    msg = result.get("stderr") or ""
    if rc == 0:
        logging.info("Job succeeded. step=%s", step)
    else:
        logging.error("Job failed. step=%s stderr=%s", step, msg)


def write_result_secret(*, jobs_namespace: str, run_id: str, result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Persist the full result JSON to a Secret so the API can read it even after the pod is gone.
    """
    name = f"cli-api-result-{run_id}".lower()

    payload = json.dumps(result, indent=2).encode("utf-8")
    b64 = base64.b64encode(payload).decode("utf-8")

    manifest = {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {
            "name": name,
            "namespace": jobs_namespace,
            "labels": {
                "app": "cli-api",
                "cli-api.greymatter.io/run-id": run_id,
                "cli-api.greymatter.io/kind": "result",
            },
        },
        "type": "Opaque",
        "data": {
            "result.json": b64,
        },
    }

    return run_cmd(
        ["kubectl", "apply", "-f", "-"],
        input=json.dumps(manifest),
        check=False,
        timeout_s=30,
    )


def _infer_returncode(result: Dict[str, Any]) -> int:
    rc = result.get("returncode")
    if rc in (0, 1):
        return int(rc)

    steps = result.get("steps")
    if isinstance(steps, list) and steps:
        return 0 if all((s.get("returncode", 1) == 0) for s in steps) else 1

    return 1

def _as_dict(x):
    if x is None:
        return {}
    if isinstance(x, dict):
        # drop None values from plain dicts too
        return {k: v for k, v in x.items() if v is not None}
    if hasattr(x, "model_dump"):
        return x.model_dump(exclude_unset=True, exclude_none=True)
    d = dict(x)
    return {k: v for k, v in d.items() if v is not None}

def main() -> int:
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.warning("ENV CLI_API_WORKDIR=%r", os.environ.get("CLI_API_WORKDIR"))
    logging.warning("settings.workdir=%r", getattr(settings, "workdir", None))
    
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(levelname)s:%(name)s:%(message)s",
    )

    payload_path = os.getenv("WORKFLOW_PAYLOAD_PATH", "/inputs/request.json")
    run_id = os.getenv("WORKFLOW_RUN_ID", "").strip()
    workflow = os.getenv("WORKFLOW_NAME", "bootstrap-core").strip().lower()

    logging.info("Job runner starting. run_id=%s workflow=%s payload_path=%s", run_id, workflow, payload_path)

    # We ALWAYS produce a result object and ALWAYS persist it
    result: Dict[str, Any] = {
        "returncode": 1,
        "workflow": workflow,
        "step": "job_start",
        "stderr": "Job did not complete",
    }

    try:
        payload = _read_json_file(payload_path)



        if workflow in ("bootstrap-core", "core"):
            req = BootstrapCoreReq.model_validate(payload)

            info = parse_git_repo_url(req.git.repo_url)

            # Token source depends on your schema; pick the correct field
            token = getattr(req.git, "token", None)
            if not token:
                # If you're using SSH clone and no token is provided, you cannot create repos via API
                result = {
                    "returncode": 1,
                    "workflow": workflow,
                    "step": "ensure_repo_exists",
                    "stderr": "Missing clone.token for Gitea API repo creation",
                }
                # write_result_file/result_secret happens in finally
                return 1  # or set result and fall through

            ensure_repo = ensure_gitea_repo(
                base_url=info["base_url"],
                owner=info["owner"],
                repo=info["repo"],
                token=token,
                verify_ssl=not req.git.insecure_skip_tls_verify,
            )

            if ensure_repo.get("returncode", 1) != 0:
                result = {
                    "returncode": 1,
                    "workflow": workflow,
                    "step": "ensure_repo_exists",
                    "stderr": ensure_repo.get("stderr", "failed to ensure repo"),
                    "detail": ensure_repo,
                }
                # write_result_file/result_secret happens in finally
                return 1
            
            job_steps = []

            greymatter_namespace = req.namespace
            greymatter_deployed = check_greymatter_installed(namespace=greymatter_namespace)
            if greymatter_deployed.get("gm_installed"):
                logging.info("Greymatter has been installed")
                job_steps.append({"name": "preflight_greymatter_installed", **greymatter_deployed})
                result = {
                        "returncode": 1,
                        "workflow": workflow,
                        "step": "preflight_greymatter_installed",
                        "stderr": "Greymatter has been installed to this namespace",
                        "steps": job_steps,
                    }
                return 1
            else:
                logging.info("Greymatter has not been installed in the %s namespace", greymatter_namespace)

            security = (getattr(req.create_platform, "security", None) or "").strip().lower()
            no_managed = bool(getattr(req.create_platform, "no_managed_spire", False))

            if security == "spire":
                spire = check_spire_installed()
                installed = bool(spire.get("installed", False))

                # no_managed_spire=true but SPIRE missing
                if no_managed and not installed:
                    job_steps.append({"name": "preflight_spire_installed", **spire})  # include diagnostics on failure
                    result = {
                        "returncode": 1,
                        "workflow": workflow,
                        "step": "preflight_spire_installed",
                        "stderr": "no_managed_spire=true but SPIRE is not installed on this cluster",
                        "steps": job_steps,
                    }
                # SPIRE installed but no_managed_spire is false
                elif installed and not no_managed:
                    job_steps.append({"name": "preflight_spire_installed", **spire})  # include diagnostics on failure
                    result = {
                        "returncode": 1,
                        "workflow": workflow,
                        "step": "preflight_spire_installed",
                        "stderr": "SPIRE is already installed on this cluster. Set no_managed_spire=true to continue.",
                        "steps": job_steps,
                    }
                else:
                    # proceed
                    result = bootstrap_core_impl(req)
                    result.setdefault("steps", [])
                    result["steps"] = job_steps + result["steps"]
            else:
                # not spire security mode: just proceed
                result = bootstrap_core_impl(req)

        elif workflow in ("bootstrap-tenant", "tenant"):
            req = BootstrapTenantReq.model_validate(payload)

            if not req.tenants or len(req.tenants) != 1:
                result = {
                    "returncode": 1,
                    "workflow": workflow,
                    "step": "validate_payload",
                    "stderr": f"bootstrap-tenant job expects exactly 1 tenant in tenants[], got {0 if not req.tenants else len(req.tenants)}",
                }
                return 1

            tenant = req.tenants[0]
            logging.warning("JOB PAYLOAD KEYS: %s", sorted(payload.keys()))
            logging.warning("JOB PAYLOAD git: %r", payload.get("git"))
            logging.warning("JOB PAYLOAD tenants[0].git: %r", (payload.get("tenants") or [{}])[0].get("git"))
            logging.warning("MODEL req.git: %r", getattr(req, "git", None))
            logging.warning("MODEL tenant.git: %r", getattr(tenant, "git", None))

            base = _as_dict(req.git)
            over = _as_dict(tenant.git)
            merged = {**base, **over}

            logging.warning("MERGE base=%r", base)
            logging.warning("MERGE over=%r", over)
            logging.warning("MERGE merged=%r", merged)

            # hard guard BEFORE building GitConfig
            repo_url = (merged.get("repo_url") or "").strip()
            if not repo_url:
                result = {
                    "returncode": 1,
                    "workflow": workflow,
                    "step": "validate_git",
                    "stderr": "git.repo_url missing after merge",
                    "detail": {"base": base, "over": over, "merged": merged},
                }
                return 1

            git = GitConfig(**merged)  # <-- this MUST be the only assignment to git
            logging.warning("GITCONFIG after validate: %r", git.model_dump())
            
            info = parse_git_repo_url(git.repo_url)
            token = git.token
            if not token:
                result = {
                    "returncode": 1,
                    "workflow": workflow,
                    "step": "ensure_repo_exists",
                    "stderr": "Missing git.token for Gitea API repo creation",
                }
                return 1

            ensure_repo = ensure_gitea_repo(
                base_url=info["base_url"],
                owner=info["owner"],
                repo=info["repo"],
                token=token,
                verify_ssl=not git.insecure_skip_tls_verify,
            )
            if ensure_repo.get("returncode", 1) != 0:
                result = {
                    "returncode": 1,
                    "workflow": workflow,
                    "step": "ensure_repo_exists",
                    "stderr": ensure_repo.get("stderr", "failed to ensure repo"),
                    "detail": ensure_repo,
                }
                return 1

            # IMPORTANT: pass merged git into whatever your impl expects
            result = bootstrap_tenant_impl(
                req=req,
                tenant=tenant,
                git=git,
            )


        elif workflow in ("tenant-config", "configure-tenant"):
            payload = _read_json_file(payload_path)
            result = tenant_config_impl(payload=payload, jobs_namespace=JOBS_NS)

        else:
            result = {
                "returncode": 1,
                "workflow": workflow,
                "step": "select_workflow",
                "stderr": f"Unknown WORKFLOW_NAME: {workflow}",
            }

    except Exception as e:
        logging.exception("Workflow crashed")
        result = {
            "returncode": 1,
            "workflow": workflow,
            "step": "workflow_exception",
            "stderr": str(e),
            "traceback": traceback.format_exc(),
        }

    finally:
        # Always normalize returncode
        result["returncode"] = _infer_returncode(result)

        # Always write result artifacts
        try:
            write_result_file(result)
        except Exception:
            logging.exception("Failed to write result file to %s", RESULT_PATH)

        if run_id:
            try:
                sec_res = write_result_secret(jobs_namespace=JOBS_NS, run_id=run_id, result=result)
                if sec_res.get("returncode", 1) != 0:
                    logging.error("Failed to write result secret: %s", sec_res.get("stderr", ""))
                else:
                    logging.info("Wrote result secret: cli-api-result-%s", run_id)
            except Exception:
                logging.exception("Failed to write result secret")
        else:
            logging.info("WORKFLOW_RUN_ID is empty; skipping result secret write")

        log_result_summary(result)

    return 0 if result.get("returncode", 1) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
