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
            req = BootstrapCoreReq.model_validate(payload)  # pydantic v2
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
    return 0 if result.get("returncode", 1) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
