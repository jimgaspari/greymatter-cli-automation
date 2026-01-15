from __future__ import annotations
import os
import tempfile
from typing import Dict, Optional, Tuple, List

from .config import settings
from .runner import run_cmd
from .paths import safe_work_path

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

def git_clone_ssh(
    repo_ssh_url: str,
    dest_dir: str,
    branch: Optional[str],
    depth: int,
    env: dict,
    timeout_s: int = 180,
) -> tuple[str, dict]:
    dest_path = safe_work_path(settings.workdir, dest_dir)

    argv = ["git", "clone"]
    if depth:
        argv += ["--depth", str(depth)]
    if branch:
        argv += ["--branch", branch]
    argv += [repo_ssh_url, dest_path]

    result = run_cmd(argv, timeout_s=timeout_s, env=env, cwd=settings.workdir)
    return dest_path, result