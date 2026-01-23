from __future__ import annotations
from typing import Dict, Any, Optional
from pathlib import Path
import tempfile
import json

from cli_api.runner import run_cmd

def create_namespace(namespace: str) -> Dict:
    ns_yaml = run_cmd(
        ["kubectl", "create", "namespace", namespace, "--dry-run=client", "-o", "yaml"],
        check=False,
    )
    if ns_yaml.get("returncode", 1) != 0:
        return ns_yaml

    apply = run_cmd(["kubectl", "apply", "-f", "-"], input=ns_yaml["stdout"], check=False)
    return apply


def create_image_pull_secret(
    namespace: str,
    secret_name: str,
    docker_server: str,
    docker_username: str,
    docker_password: str,
) -> Dict:
    argv = [
        "kubectl", "create", "secret", "docker-registry", secret_name,
        f"--docker-server={docker_server}",
        f"--docker-username={docker_username}",
        f"--docker-password={docker_password}",
        "-n", namespace,
        "--dry-run=client", "-o", "yaml",
    ]
    secret_yaml = run_cmd(argv)
    if secret_yaml["returncode"] != 0:
        return secret_yaml

    apply = run_cmd(["kubectl", "apply", "-f", "-"], input=secret_yaml["stdout"])
    return apply

def create_repo_secret(
    *,
    namespace: str,
    secret_name: str,
    repo_url: str,
    branch: str,
    auth_type: str,  # "ssh" or "https"
    # SSH fields
    known_hosts: Optional[str] = None,
    ssh_key: Optional[str] = None,
    # HTTPS fields
    http_username: Optional[str] = None,
    http_password: Optional[str] = None,
    tls_insecure_verify: bool = False,
) -> Dict:
    auth_type = (auth_type or "").strip().lower()
    secret_name = (secret_name or "").strip()

    if auth_type not in ("ssh", "https"):
        return {"returncode": 1, "stderr": f"Unsupported auth_type={auth_type!r}"}
    if not secret_name:
        return {"returncode": 1, "stderr": "secret_name is required"}

    def _apply_from_yaml(yaml_text: str, step: str) -> Dict:
        apply_res = run_cmd(["kubectl", "apply", "-f", "-"], input=yaml_text, check=False)
        return {"step": step, **apply_res}

    if auth_type == "https":
        if not http_username:
            return {"returncode": 1, "stderr": "http_username is required for auth_type=https"}
        if not http_password:
            return {"returncode": 1, "stderr": "http_password is required for auth_type=https"}

        argv = [
            "kubectl", "create", "secret", "generic", secret_name,
            "--type=greymatter.io/repo",
            f"--from-literal=auth_type=https",
            f"--from-literal=url={repo_url}",
            f"--from-literal=branch={branch}",
            f"--from-literal=http_username={http_username}",
            f"--from-literal=http_password={http_password}",
            f"--from-literal=tls_insecure_verify={'true' if tls_insecure_verify else 'false'}",
            "-n", namespace,
            "--dry-run=client", "-o", "yaml",
        ]

        secret_yaml = run_cmd(argv, check=False)
        if secret_yaml.get("returncode", 1) != 0:
            return {"step": "kubectl create repo secret (https)", **secret_yaml}

        return _apply_from_yaml(secret_yaml.get("stdout", ""), "kubectl apply repo secret (https)")

    # SSH
    if not known_hosts:
        return {"returncode": 1, "stderr": "known_hosts is required for auth_type=ssh"}
    if not ssh_key:
        return {"returncode": 1, "stderr": "ssh_key is required for auth_type=ssh"}

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        kh = td_path / "known_hosts"
        key = td_path / "ssh_private_key"

        kh.write_text(known_hosts, encoding="utf-8")
        key.write_text(ssh_key, encoding="utf-8")
        key.chmod(0o600)

        argv = [
            "kubectl", "create", "secret", "generic", secret_name,
            "--type=greymatter.io/repo",
            f"--from-literal=auth_type=ssh",
            f"--from-literal=url={repo_url}",
            f"--from-literal=branch={branch}",
            f"--from-file=known_hosts={kh}",
            f"--from-file=ssh_private_key={key}",
            "-n", namespace,
            "--dry-run=client", "-o", "yaml",
        ]

        secret_yaml = run_cmd(argv, check=False)
        if secret_yaml.get("returncode", 1) != 0:
            return {"step": "kubectl create repo secret (ssh)", **secret_yaml}

        return _apply_from_yaml(secret_yaml.get("stdout", ""), "kubectl apply repo secret (ssh)")

def apply_edge_ingress_tls_secret(
    *,
    namespace: str,
    secret_name: str,
    tls_crt_pem: str,
    tls_key_pem: str,
    ca_crt_pem: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Creates/updates a Kubernetes TLS secret with required tls.crt/tls.key and optional ca.crt.
    Uses stringData so we don't have to base64 encode and so kubectl does it for us.
    """
    if not tls_crt_pem or not tls_key_pem:
        return {"returncode": 1, "stderr": "tls.crt and tls.key are required"}

    string_data: Dict[str, str] = {
        "tls.crt": tls_crt_pem,
        "tls.key": tls_key_pem,
    }
    if ca_crt_pem:
        string_data["ca.crt"] = ca_crt_pem

    manifest: Dict[str, Any] = {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {
            "name": secret_name,
            "namespace": namespace,
            "labels": {
                "app": "cli-api",
                "cli-api.greymatter.io/kind": "edge-ingress-tls",
            },
        },
        # TLS secret type expects tls.crt and tls.key; extra keys like ca.crt are allowed
        "type": "kubernetes.io/tls",
        "stringData": string_data,
    }

    # IMPORTANT: Never include secret contents in logs/response (run_cmd returns stdout/stderr only)
    return run_cmd(
        ["kubectl", "apply", "-f", "-"],
        input=json.dumps(manifest),
        check=False,
        timeout_s=30,
    )
