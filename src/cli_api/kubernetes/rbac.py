# cli_api/kubernetes/rbac.py
from __future__ import annotations
from typing import Any, Dict
import json
from cli_api.runner import run_cmd


def grant_sa_read_secret(
    *,
    target_namespace: str,
    secret_name: str,
    subject_sa_name: str,
    subject_sa_namespace: str,
    role_name: str = "cli-api-read-core-git-secret",
    rolebinding_name: str = "cli-api-read-core-git-secret",
) -> Dict[str, Any]:
    """
    Creates/updates a Role+RoleBinding in target_namespace that allows the given SA
    (in subject_sa_namespace) to get the named Secret.
    Locked to resourceNames=[secret_name].
    """
    role = {
        "apiVersion": "rbac.authorization.k8s.io/v1",
        "kind": "Role",
        "metadata": {"name": role_name, "namespace": target_namespace},
        "rules": [
            {
                "apiGroups": [""],
                "resources": ["secrets"],
                "resourceNames": [secret_name],
                "verbs": ["get"],
            }
        ],
    }

    rb = {
        "apiVersion": "rbac.authorization.k8s.io/v1",
        "kind": "RoleBinding",
        "metadata": {"name": rolebinding_name, "namespace": target_namespace},
        "subjects": [
            {
                "kind": "ServiceAccount",
                "name": subject_sa_name,
                "namespace": subject_sa_namespace,
            }
        ],
        "roleRef": {
            "apiGroup": "rbac.authorization.k8s.io",
            "kind": "Role",
            "name": role_name,
        },
    }

    # Apply both (idempotent)
    res1 = run_cmd(["kubectl", "apply", "-f", "-"], input=json.dumps(role), check=False, timeout_s=30)
    if res1.get("returncode", 1) != 0:
        return {"returncode": 1, "step": "apply_role", **res1}

    res2 = run_cmd(["kubectl", "apply", "-f", "-"], input=json.dumps(rb), check=False, timeout_s=30)
    if res2.get("returncode", 1) != 0:
        return {"returncode": 1, "step": "apply_rolebinding", **res2}

    return {"returncode": 0, "step": "grant_sa_read_secret", "stdout": "RBAC applied"}
