from __future__ import annotations
from typing import Dict

from ..runner import run_cmd


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
