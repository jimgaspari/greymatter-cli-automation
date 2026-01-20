# cli_api/kubernetes/spire.py
from __future__ import annotations
from typing import Any, Dict, List

from ..runner import run_cmd


def check_spire_installed() -> Dict[str, Any]:
    """
    Detect SPIRE installation using server StatefulSet presence.
    Intended to run inside the job runner pod.
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
            "checks": checks,
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
            "checks": checks,
        }

    # 3) Optional fallback: CRDs (indicates SPIRE was installed at some point)
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
        checks["spire_crds"] = spire_crds
        if spire_crds:
            return {
                "returncode": 0,
                "installed": True,
                "method": "spire_crds_present",
                "checks": checks,
            }

    # Not installed
    return {
        "returncode": 0,
        "installed": False,
        "checks": checks,
    }
