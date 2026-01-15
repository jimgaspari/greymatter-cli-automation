from __future__ import annotations
import base64
import os
import tempfile
from typing import Dict, Optional, Tuple, List

from .config import settings
from .runner import run_cmd
from .paths import safe_work_path

def git_clone_with_ephemeral_key(
    repo_ssh_url: str,
    dest_dir: str,
    branch: Optional[str],
    depth: int,
    ssh_private_key_b64: str,
    known_hosts: Optional[str],
    strict_host_key_checking: bool,
    timeout_s: int = 180,
) -> Tuple[str, Dict]:
    """
    Clones repo_ssh_url into WORKDIR/dest_dir using a private key provided at runtime.
    Returns (dest_path, result_dict). Raises ValueError for bad inputs.
    """
    if not repo_ssh_url.startswith("git@") and "@" not in repo_ssh_url:
        raise ValueError("repo_ssh_url must be an SSH-style URL (git@host:owner/repo.git)")

    dest_path = safe_work_path(settings.workdir, dest_dir)

    try:
        key_text = base64.b64decode(ssh_private_key_b64).decode("utf-8")
    except Exception:
        raise ValueError("Invalid ssh_private_key_b64 (must be base64-encoded UTF-8 private key)")

    with tempfile.TemporaryDirectory() as td:
        key_path = os.path.join(td, "id_key")
        with open(key_path, "w", encoding="utf-8") as f:
            f.write(key_text)
        os.chmod(key_path, 0o600)

        known_hosts_path = os.path.join(td, "known_hosts")
        if known_hosts:
            with open(known_hosts_path, "w", encoding="utf-8") as f:
                f.write(known_hosts)
            os.chmod(known_hosts_path, 0o600)

        ssh_opts: List[str] = [
            "-i", key_path,
            "-o", "IdentitiesOnly=yes",
            "-o", "BatchMode=yes",
            "-o", "PasswordAuthentication=no",
            "-o", "KbdInteractiveAuthentication=no",
        ]

        if strict_host_key_checking:
            if not known_hosts:
                raise ValueError("known_hosts required when strict_host_key_checking=true")
            ssh_opts += [
                "-o", f"UserKnownHostsFile={known_hosts_path}",
                "-o", "StrictHostKeyChecking=yes",
            ]
        else:
            ssh_opts += ["-o", "StrictHostKeyChecking=accept-new"]
            if known_hosts:
                ssh_opts += ["-o", f"UserKnownHostsFile={known_hosts_path}"]

        env = os.environ.copy()
        env["GIT_SSH_COMMAND"] = "ssh " + " ".join(ssh_opts)

        argv = ["git", "clone"]
        if depth:
            argv += ["--depth", str(depth)]
        if branch:
            argv += ["--branch", branch]
        argv += [repo_ssh_url, dest_path]

        result = run_cmd(argv, timeout_s=timeout_s, env=env, cwd=settings.workdir)
        return dest_path, result, env

def git_clone_https(
    repo_https_url: str,
    dest_dir: str,
    branch: Optional[str],
    depth: int,
    username: Optional[str] = None,
    password: Optional[str] = None,
    token: Optional[str] = None,
    timeout_s: int = 180,
) -> Tuple[str, Dict]:
    """
    Clone an HTTPS repo. Supports:
      - public repo (no auth)
      - basic auth (username/password)
      - token auth via username + token, or token-only using username='oauth2'/'x-access-token'
    Uses GIT_ASKPASS so secrets aren't placed in argv or URL.
    """
    if not repo_https_url.startswith("https://"):
        raise ValueError("repo_https_url must start with https://")

    dest_path = safe_work_path(settings.workdir, dest_dir)

    # If token provided and no username, pick a common placeholder
    if token and not username:
        # Works for many Git servers; adjust if your server expects different
        username = "oauth2"

    # Build argv
    argv: List[str] = ["git", "clone"]
    if depth:
        argv += ["--depth", str(depth)]
    if branch:
        argv += ["--branch", branch]
    argv += [repo_https_url, dest_path]

    env = os.environ.copy()

    # If no auth, just clone
    if not (password or token):
        result = run_cmd(argv, timeout_s=timeout_s, env=env, cwd=settings.workdir)
        return dest_path, result

    # For auth, use a temporary askpass script
    secret_password = token if token is not None else (password or "")
    secret_username = username or ""

    with tempfile.TemporaryDirectory() as td:
        askpass_path = os.path.join(td, "askpass.sh")
        # Askpass prints username or password depending on prompt content.
        # Keep it simple and robust for Git's prompts.
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
        env["GIT_TERMINAL_PROMPT"] = "0"  # fail instead of prompting
        # Some git versions also honor these:
        env["GIT_USERNAME"] = secret_username
        env["GIT_PASSWORD"] = secret_password

        result = run_cmd(argv, timeout_s=timeout_s, env=env, cwd=settings.workdir)
        return dest_path, result, env
