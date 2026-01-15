from __future__ import annotations
import os
from typing import Tuple, Dict, Optional
from .git_ops import git_clone_with_ephemeral_key, git_clone_https
from .schemas import CloneSpec
from .runner import run_cmd

def clone_repo(clone: CloneSpec, dest_dir: str, branch: str | None, depth: int) -> Tuple[str, Dict]:
    if clone.type == "ssh":
        return git_clone_with_ephemeral_key(
            repo_ssh_url=clone.repo_url,
            dest_dir=dest_dir,
            branch=branch,
            depth=depth,
            ssh_private_key_b64=clone.ssh_private_key_b64,
            known_hosts=clone.known_hosts,
            strict_host_key_checking=clone.strict_host_key_checking,
        )
    else:
        return git_clone_https(...)
    # HTTPS
    return git_clone_https(
        repo_https_url=clone.repo_url,
        dest_dir=dest_dir,
        branch=branch,
        depth=depth,
        username=clone.username,
        password=clone.password,
        token=clone.token,
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
