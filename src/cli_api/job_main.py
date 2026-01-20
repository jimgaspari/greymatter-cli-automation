# cli_api/job_main.py

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any, Dict

from cli_api.schemas import BootstrapCoreReq, BootstrapTenantReq
from cli_api.services.core import bootstrap_core_impl
from cli_api.services.tenant import bootstrap_tenant_impl
from cli_api.kubernetes.spire import check_spire_installed


def _read_json_file(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _print_result(obj: Dict[str, Any]) -> None:
    # Always emit JSON so API can read logs
    print(json.dumps(obj, indent=2, ensure_ascii=False))


def main() -> int:
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(levelname)s:%(name)s:%(message)s",
    )

    payload_path = os.getenv("WORKFLOW_PAYLOAD_PATH", "/inputs/request.json")
    run_id = os.getenv("WORKFLOW_RUN_ID", "")
    workflow = os.getenv("WORKFLOW_NAME", "bootstrap-core").strip().lower()

    logging.warning("Job runner starting. run_id=%s workflow=%s payload_path=%s", run_id, workflow, payload_path)

    try:
        payload = _read_json_file(payload_path)
    except Exception as e:
        _print_result({"returncode": 1, "step": "read payload", "stderr": str(e), "payload_path": payload_path})
        return 1

    try:
        if workflow in ("bootstrap-core", "core"):
            req = BootstrapCoreReq.model_validate(payload)
            job_steps = []

            def _security_is_spire(req) -> bool:
                sec = (getattr(req.create_platform, "security", None) or "").strip().lower()
                return sec == "spire"

            def _no_managed_spire(req) -> bool:
                return bool(getattr(req.create_platform, "no_managed_spire", False))


            security_spire = _security_is_spire(req)
            no_managed = _no_managed_spire(req)

            if security_spire:
                spire = check_spire_installed()
                job_steps.append({"name": "preflight_spire_installed", **spire})

                installed = bool(spire.get("installed", False))

                if no_managed and not installed:
                    result = {
                        "returncode": 1,
                        "workflow": workflow,
                        "step": "preflight_spire_installed",
                        "stderr": "no_managed_spire=true but SPIRE is not installed on this cluster",
                        "steps": job_steps,
                    }
                    _print_result(result)
                    return 1

                if installed and not no_managed:
                    result = {
                        "returncode": 1,
                        "workflow": workflow,
                        "step": "preflight_spire_installed",
                        "stderr": (
                            "SPIRE is already installed on this cluster."
                        ),
                        "steps": job_steps,
                    }
                    _print_result(result)
                    return 1

            result = bootstrap_core_impl(req)

        elif workflow in ("bootstrap-tenant", "tenant"):
            req = BootstrapTenantReq.model_validate(payload)
            result = bootstrap_tenant_impl(req)

        else:
            _print_result({"returncode": 1, "step": "select workflow", "stderr": f"Unknown WORKFLOW_NAME: {workflow}"})
            return 1

    except Exception as e:
        logging.exception("Workflow crashed")
        _print_result({"returncode": 1, "step": "workflow exception", "stderr": repr(e)})
        return 1

    _print_result(result)

    rc = result.get("returncode", None)

    # If workflow forgot to provide returncode, infer from steps
    if rc is None:
        steps = result.get("steps")
        if isinstance(steps, list) and steps:
            rc = 0 if all((s.get("returncode", 1) == 0) for s in steps) else 1
        else:
            rc = 1  # no returncode + no steps => treat as failure

    return 0 if rc == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
