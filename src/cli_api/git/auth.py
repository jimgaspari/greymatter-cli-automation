from __future__ import annotations
import os
from typing import Optional, Dict
from pathlib import Path
from cli_api.schemas import SshAuth

def prepare_ssh_auth(
    *,
    workspace_path: str,
    ssh_private_key: str,
    known_hosts: Optional[str],
    strict_host_key_checking: bool,
):
    ssh_dir = Path(workspace_path) / ".ssh"
    ssh_dir.mkdir(parents=True, exist_ok=True)

    key_path = ssh_dir / "id_key"
    key_path.write_text(ssh_private_key, encoding="utf-8")
    key_path.chmod(0o600)

    known_hosts_path = None
    if known_hosts:
        known_hosts_path = ssh_dir / "known_hosts"
        known_hosts_path.write_text(known_hosts, encoding="utf-8")
        known_hosts_path.chmod(0o600)

    ssh_opts = [
        "-i", str(key_path),
        "-o", "IdentitiesOnly=yes",
        "-o", "BatchMode=yes",
        "-o", "PasswordAuthentication=no",
        "-o", "KbdInteractiveAuthentication=no",
    ]

    if strict_host_key_checking:
        if not known_hosts_path:
            raise ValueError("known_hosts required when strict_host_key_checking=true")
        ssh_opts += [
            "-o", f"UserKnownHostsFile={known_hosts_path}",
            "-o", "StrictHostKeyChecking=yes",
        ]
    else:
        ssh_opts += ["-o", "StrictHostKeyChecking=accept-new"]
        if known_hosts_path:
            ssh_opts += ["-o", f"UserKnownHostsFile={known_hosts_path}"]

    env = os.environ.copy()
    env["GIT_SSH_COMMAND"] = "ssh " + " ".join(ssh_opts)

    return SshAuth(env=env, key_path=str(key_path), known_hosts_path=str(known_hosts_path) if known_hosts_path else None)

def prepare_https_auth(
    *,
    workspace_path: str,
    username: Optional[str] = None,
    password: Optional[str] = None,
    token: Optional[str] = None,
    insecure_skip_tls_verify: bool = False,
) -> Dict[str, str]:
    env = os.environ.copy()

    # Allow self-signed certs for git over HTTPS (opt-in)
    if insecure_skip_tls_verify:
        env["GIT_SSL_NO_VERIFY"] = "true"

    # No auth needed
    if not (password or token):
        return env

    secret_password = token if token is not None else (password or "")
    secret_username = username or ""

    # If token provided and no username, use a common placeholder
    # (GitLab uses "oauth2"; GitHub can be anything; Gitea accepts token as password too)
    if token and not secret_username:
        secret_username = "oauth2"

    # Put askpass in a workflow-scoped location so it survives the process lifetime
    auth_dir = Path(workspace_path) / ".git-auth"
    auth_dir.mkdir(parents=True, exist_ok=True)
    askpass_path = auth_dir / "askpass.sh"

    script = f"""#!/bin/sh
case "$1" in
  *sername*|*Username*) echo "{secret_username}" ;;
  *assword*|*Password*) echo "{secret_password}" ;;
  *) echo "" ;;
esac
"""
    askpass_path.write_text(script, encoding="utf-8")
    os.chmod(askpass_path, 0o700)

    env["GIT_ASKPASS"] = str(askpass_path)
    env["GIT_TERMINAL_PROMPT"] = "0"

    # These two are not used by git directly, but can help debugging or wrappers.
    env["GIT_USERNAME"] = secret_username
    env["GIT_PASSWORD"] = secret_password

    return env
