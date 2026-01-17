from __future__ import annotations
from typing import Dict
from pathlib import Path
import tempfile

from ..runner import run_cmd

from typing import Dict

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
    namespace: str,
    secret_name: str,
    repo_url: str,
    branch: str,
    known_hosts: str,
    ssh_key: str,
) -> Dict:
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        kh = td_path / "known_hosts"
        key = td_path / "ssh_private_key"

        kh.write_text(known_hosts)
        key.write_text(ssh_key)
        key.chmod(0o600)

        argv = [
            "kubectl", "create", "secret", "generic", secret_name,
            "--type=greymatter.io/repo",
            f"--from-literal=url={repo_url}",
            f"--from-literal=branch={branch}",
            "--from-literal=auth_type=ssh",
            f"--from-file=known_hosts={kh}",
            f"--from-file=ssh_private_key={key}",
            "-n", namespace,
            "--dry-run=client", "-o", "yaml",
        ]

        secret_yaml = run_cmd(argv)
        if secret_yaml["returncode"] != 0:
            return secret_yaml

        apply = run_cmd(["kubectl", "apply", "-f", "-"], input=secret_yaml["stdout"])
        return apply
