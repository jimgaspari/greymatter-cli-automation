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
from cli_api.schemas import BootstrapCoreReq, BootstrapTenantReq
from cli_api.services.core import bootstrap_core_impl
from cli_api.services.tenant import bootstrap_tenant_impl
from cli_api.kubernetes.spire import check_spire_installed

RESULT_PATH = os.getenv("CLI_API_RESULT_PATH", "/outputs/result.json")
JOBS_NS = os.getenv("CLI_API_JOBS_NAMESPACE", "cli-api-jobs")


def _read_json_file(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_result_file(result: Dict[str, Any]) -> None:
    p = Path(RESULT_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    logging.warning("Wrote result file: %s (%d bytes)", str(p), p.stat().st_size)


def log_result_summary(result: Dict[str, Any]) -> None:
    rc = result.get("returncode", 1)
    step = result.get("step") or result.get("workflow_step") or "unknown"
    msg = result.get("stderr") or ""
    if rc == 0:
        logging.warning("Job succeeded. step=%s", step)
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


def main() -> int:
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(levelname)s:%(name)s:%(message)s",
    )

    payload_path = os.getenv("WORKFLOW_PAYLOAD_PATH", "/inputs/request.json")
    run_id = os.getenv("WORKFLOW_RUN_ID", "").strip()
    workflow = os.getenv("WORKFLOW_NAME", "bootstrap-core").strip().lower()

    logging.warning("Job runner starting. run_id=%s workflow=%s payload_path=%s", run_id, workflow, payload_path)

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
            job_steps = []

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
            result = bootstrap_tenant_impl(req)

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
                    logging.warning("Wrote result secret: cli-api-result-%s", run_id)
            except Exception:
                logging.exception("Failed to write result secret")
        else:
            logging.warning("WORKFLOW_RUN_ID is empty; skipping result secret write")

        log_result_summary(result)

    return 0 if result.get("returncode", 1) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
