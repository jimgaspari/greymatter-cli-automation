# cli_api/kubernetes/spire.py
from __future__ import annotations
from typing import Any, Dict
import logging
from cli_api.runner import run_cmd


def check_spire_installed() -> Dict[str, Any]:
    """
    Detect SPIRE installation using server StatefulSet presence.
    Only returns detailed diagnostics if SPIRE *is* installed.
    """
    checks: Dict[str, Any] = {}

    # 1) Preferred: Helm-labeled SPIRE server StatefulSet
    sts = run_cmd(
        [
            "kubectl", "get", "sts", "-A",
            "-l", "app.kubernetes.io/instance=spire",
            "-o", "name",
        ],
        check=False,
        timeout_s=30,
    )
    checks["spire_server_sts_by_instance"] = sts

    if sts.get("returncode", 1) == 0 and (sts.get("stdout") or "").strip():
        return {
            "returncode": 0,
            "installed": True,
            "method": "statefulset(instance=spire)",
        }

    # 2) Fallback: common app labels
    sts_alt = run_cmd(
        [
            "kubectl", "get", "sts", "-A",
            "-l", "app=spire-server",
            "-o", "name",
        ],
        check=False,
        timeout_s=30,
    )
    checks["spire_server_sts_by_app"] = sts_alt

    if sts_alt.get("returncode", 1) == 0 and (sts_alt.get("stdout") or "").strip():
        return {
            "returncode": 0,
            "installed": True,
            "method": "statefulset(app=spire-server)",
        }

    # 3) Optional fallback: CRDs
    crds = run_cmd(
        ["kubectl", "get", "crd", "-o", "name"],
        check=False,
        timeout_s=30,
    )
    checks["crds_list"] = crds

    if crds.get("returncode", 1) == 0:
        spire_crds = [
            l for l in (crds.get("stdout") or "").splitlines()
            if ".spire.spiffe.io" in l
        ]
        if spire_crds:
            checks["spire_crds"] = spire_crds
            return {
                "returncode": 0,
                "installed": True,
                "method": "spire_crds_present",
            }

    # Success case: NOT installed → quiet
    return {
        "returncode": 0,
        "installed": False,
    }

def check_greymatter_installed(namespace: str) -> Dict[str, Any]:
    validate: Dict[str, Any] = {}
    logging.info("Checking for installed Greymatter Operator in %s namespace", namespace)
    po = run_cmd(
        [
            "kubectl", "get", "deploy", 
            "-n", namespace,
            "greymatter-po", "-o", "name"
        ],
        check=False,
        timeout_s=30,
    )
    validate["greymatter_po_deploy_by_instance"] = po
    if po.get("returncode", 1) == 0 and (po.get("stdout") or "").strip():
        return {
            "returncode": 0,
            "gm_installed": True,
            "method": "greymatter_po_deployed"
        }
    return {
        "returncode": 0,
        "gm_installed": False,
    }