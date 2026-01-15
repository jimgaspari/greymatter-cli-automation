from __future__ import annotations
import os
import base64
from typing import Tuple, Dict, Optional
from pathlib import Path

from .git_ops import git_clone_https, git_clone_ssh
from .schemas import CloneSpec, SshAuth
from .runner import run_cmd

def clone_repo(
    *,
    clone: CloneSpec,
    dest_dir: str,
    branch: Optional[str],
    depth: int,
    env: dict,
) -> Tuple[str, Dict]:
    if clone.type == "ssh":
        # NOTE: SSH auth already prepared in workflow and env contains GIT_SSH_COMMAND
        return git_clone_ssh(
            repo_ssh_url=clone.repo_url,
            dest_dir=dest_dir,
            branch=branch,
            depth=depth,
            env=env,
        )

    # HTTPS auth already prepared in workflow OR clone is public
    return git_clone_https(
        repo_https_url=clone.repo_url,
        dest_dir=dest_dir,
        branch=branch,
        depth=depth,
        env=env,
        username=getattr(clone, "username", None),
        password=getattr(clone, "password", None),
        token=getattr(clone, "token", None),
    )

def git_has_changes(repo_path: str) -> bool:
    result = run_cmd(
        ["git", "status", "--porcelain"],
        cwd=repo_path,
        timeout_s=30,
    )
    return bool(result["stdout"].strip())

def git_commit_and_push(
    repo_path: str,
    message: str,
    env: Optional[dict] = None,
) -> Dict:
    env = env or os.environ.copy()

    steps = {}

    add = run_cmd(["git", "add", "-A"], cwd=repo_path, env=env)
    steps["add"] = add
    if add["exit_code"] != 0:
        return {"step": "git add", **add}

    commit = run_cmd(
        ["git", "commit", "-m", message],
        cwd=repo_path,
        env=env,
    )
    steps["commit"] = commit
    if commit["exit_code"] != 0:
        return {"step": "git commit", **commit}

    push = run_cmd(
        ["git", "push"],
        cwd=repo_path,
        env=env,
        timeout_s=120,
    )
    steps["push"] = push
    if push["exit_code"] != 0:
        return {"step": "git push", **push}

    return {
        "exit_code": 0,
        "steps": steps,
    }

def ensure_branch(repo_path: str, git_env: dict, target_branch: str, push_to_remote: bool) -> Dict:
    steps: Dict = {}

    # Make sure refs are up-to-date
    fetch = run_cmd(["git", "fetch", "origin", "--prune"], cwd=repo_path, env=git_env, timeout_s=60)
    steps["fetch"] = fetch
    if fetch["exit_code"] != 0:
        return {"exit_code": fetch["exit_code"], "step": "git fetch", "steps": steps}

    # Detect if branch exists on origin
    ls = run_cmd(["git", "ls-remote", "--heads", "origin", target_branch],
                 cwd=repo_path, env=git_env, timeout_s=30)
    steps["ls_remote"] = ls
    if ls["exit_code"] != 0:
        return {"exit_code": ls["exit_code"], "step": "git ls-remote", "steps": steps}

    remote_exists = bool(ls["stdout"].strip())

    if remote_exists:
        # Track the remote branch
        co = run_cmd(["git", "checkout", "-B", target_branch, f"origin/{target_branch}"],
                     cwd=repo_path, env=git_env, timeout_s=30)
        steps["checkout"] = co
        if co["exit_code"] != 0:
            return {"exit_code": co["exit_code"], "step": "git checkout remote", "steps": steps}
        return {"exit_code": 0, "remote_exists": True, "steps": steps}

    # Remote branch doesn't exist -> create locally from current HEAD
    co = run_cmd(["git", "checkout", "-b", target_branch],
                 cwd=repo_path, env=git_env, timeout_s=30)
    steps["checkout"] = co
    if co["exit_code"] != 0:
        return {"exit_code": co["exit_code"], "step": "git checkout -b", "steps": steps}

    if push_to_remote:
        push = run_cmd(["git", "push", "-u", "origin", target_branch],
                       cwd=repo_path, env=git_env, timeout_s=120)
        steps["push_branch"] = push
        if push["exit_code"] != 0:
            return {"exit_code": push["exit_code"], "step": "git push -u", "steps": steps}

    return {"exit_code": 0, "remote_exists": False, "pushed_branch": push_to_remote, "steps": steps}

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

def ensure_git_identity(
    repo_path: str,
    env: dict,
    name: str,
    email: str,
) -> Dict:
    steps = {}

    name_res = run_cmd(
        ["git", "config", "user.name", name],
        cwd=repo_path,
        env=env,
    )
    steps["user.name"] = name_res
    if name_res["exit_code"] != 0:
        return {"exit_code": name_res["exit_code"], "steps": steps}

    email_res = run_cmd(
        ["git", "config", "user.email", email],
        cwd=repo_path,
        env=env,
    )
    steps["user.email"] = email_res
    if email_res["exit_code"] != 0:
        return {"exit_code": email_res["exit_code"], "steps": steps}

    return {"exit_code": 0, "steps": steps}
