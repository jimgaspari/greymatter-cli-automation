from __future__ import annotations
from typing import Dict, Optional

from cli_api.runner import run_cmd


def git_has_changes(repo_path: str, env: Optional[dict] = None) -> bool:
    env = env or {}
    result = run_cmd(
        ["git", "status", "--porcelain"],
        cwd=repo_path,
        env=env,
        timeout_s=30,
        check=False,
    )
    return bool((result.get("stdout") or "").strip())


def git_commit_and_push(
    repo_path: str,
    message: str,
    env: Optional[dict] = None,
) -> Dict:
    env = env or {}
    steps: Dict = {}

    add = run_cmd(["git", "add", "-A"], cwd=repo_path, env=env, check=False)
    steps["add"] = add
    if add.get("returncode", 1) != 0:
        return {"returncode": add["returncode"], "step": "git add", "steps": steps}

    # Commit can legitimately be a no-op ("nothing to commit")
    commit = run_cmd(["git", "commit", "-m", message], cwd=repo_path, env=env, check=False)
    steps["commit"] = commit
    if commit.get("returncode", 1) != 0:
        out = (commit.get("stdout", "") + commit.get("stderr", "")).lower()
        if "nothing to commit" not in out:
            return {"returncode": commit["returncode"], "step": "git commit", "steps": steps}

    # Determine current branch
    branch = run_cmd(
        ["git", "branch", "--show-current"],
        cwd=repo_path,
        env=env,
        check=False,
    )
    steps["current_branch"] = branch
    br = (branch.get("stdout") or "").strip()
    if branch.get("returncode", 1) != 0 or not br:
        # Fallback if detached HEAD or weird state
        branch2 = run_cmd(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_path,
            env=env,
            check=False,
        )
        steps["current_branch_fallback"] = branch2
        br = (branch2.get("stdout") or "").strip()
        if branch2.get("returncode", 1) != 0 or not br or br == "HEAD":
            return {"returncode": 1, "step": "detect branch", "steps": steps}

    # Push explicitly and set upstream (safe even if already set)
    push = run_cmd(
        ["git", "push", "-u", "origin", br],
        cwd=repo_path,
        env=env,
        timeout_s=120,
        check=False,
    )
    steps["push"] = push
    if push.get("returncode", 1) != 0:
        return {"returncode": push["returncode"], "step": "git push", "steps": steps}

    return {"returncode": 0, "steps": steps}
