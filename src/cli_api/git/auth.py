
from __future__ import annotations
import os, tempfile
import base64
from typing import Optional, Dict
from pathlib import Path
from ..schemas import  SshAuth

def prepare_ssh_auth(
    workspace_path: str,
    ssh_private_key_b64: str,
    known_hosts: Optional[str],
    strict_host_key_checking: bool,
) -> SshAuth:
    ws = Path(workspace_path)
    ssh_dir = ws / ".ssh"
    ssh_dir.mkdir(parents=True, exist_ok=True)

    key_path = ssh_dir / "id_key"
    key_text = base64.b64decode(ssh_private_key_b64).decode("utf-8")
    key_path.write_text(key_text, encoding="utf-8")
    os.chmod(key_path, 0o600)

    known_hosts_path = None
    if known_hosts:
        known_hosts_path = ssh_dir / "known_hosts"
        known_hosts_path.write_text(known_hosts, encoding="utf-8")
        os.chmod(known_hosts_path, 0o600)

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
    username: Optional[str] = None,
    password: Optional[str] = None,
    token: Optional[str] = None,
) -> Dict[str, str]:
    env = os.environ.copy()

    # No auth needed
    if not (password or token):
        return env

    secret_password = token if token is not None else (password or "")
    secret_username = username or ""

    # If token provided and no username, pick a common placeholder
    if token and not username:
        secret_username = "oauth2"

    # IMPORTANT: Askpass path must persist for workflow duration.
    # Put it somewhere stable (workspace .git-auth) if you want. For now we'll still
    # use a temp file approach, but it MUST be workflow-scoped, not function-scoped.
    td = tempfile.mkdtemp(prefix="git-askpass-")
    askpass_path = os.path.join(td, "askpass.sh")

    script = f"""#!/bin/sh
case "$1" in
  *sername*|*Username*) echo "{secret_username}" ;;
  *assword*|*Password*) echo "{secret_password}" ;;
  *) echo "" ;;
esac
"""
    with open(askpass_path, "w", encoding="utf-8") as f:
        f.write(script)
    os.chmod(askpass_path, 0o700)

    env["GIT_ASKPASS"] = askpass_path
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_USERNAME"] = secret_username
    env["GIT_PASSWORD"] = secret_password
    return env
