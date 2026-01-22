from __future__ import annotations
from typing import Dict
from pathlib import Path
import tempfile

from ..runner import run_cmd

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
