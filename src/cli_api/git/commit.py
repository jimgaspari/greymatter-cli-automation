from __future__ import annotations
from typing import Dict, Optional

from ..runner import run_cmd


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
    env = env or {}

    steps: Dict = {}

    add = run_cmd(["git", "add", "-A"], cwd=repo_path, env=env)
    steps["add"] = add
    if add["exit_code"] != 0:
        return {"exit_code": add["exit_code"], "step": "git add", "steps": steps}

    commit = run_cmd(["git", "commit", "-m", message], cwd=repo_path, env=env)
    steps["commit"] = commit
    if commit["exit_code"] != 0:
        return {"exit_code": commit["exit_code"], "step": "git commit", "steps": steps}

    # Detect upstream
    upstream = run_cmd(
        ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
        cwd=repo_path,
        env=env,
    )
    steps["upstream_check"] = upstream

    if upstream["exit_code"] == 0:
        # Normal push
        push = run_cmd(["git", "push"], cwd=repo_path, env=env, timeout_s=120)
    else:
        # No upstream → set it
        branch = run_cmd(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_path,
            env=env,
        )
        steps["current_branch"] = branch
        if branch["exit_code"] != 0:
            return {"exit_code": branch["exit_code"], "step": "detect branch", "steps": steps}

        push = run_cmd(
            ["git", "push", "-u", "origin", branch["stdout"].strip()],
            cwd=repo_path,
            env=env,
            timeout_s=120,
        )

    steps["push"] = push
    if push["exit_code"] != 0:
        return {"exit_code": push["exit_code"], "step": "git push", "steps": steps}

    return {"exit_code": 0, "steps": steps}
