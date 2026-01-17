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
    if add["returncode"] != 0:
        return {"returncode": add["returncode"], "step": "git add", "steps": steps}

    commit = run_cmd(["git", "commit", "-m", message], cwd=repo_path, env=env)
    steps["commit"] = commit
    if commit["returncode"] != 0:
        return {"returncode": commit["returncode"], "step": "git commit", "steps": steps}

    # Detect upstream
    upstream = run_cmd(
        ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
        cwd=repo_path,
        env=env,
    )
    steps["upstream_check"] = upstream

    if upstream["returncode"] == 0:
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
        if branch["returncode"] != 0:
            return {"returncode": branch["returncode"], "step": "detect branch", "steps": steps}

        push = run_cmd(
            ["git", "push", "-u", "origin", branch["stdout"].strip()],
            cwd=repo_path,
            env=env,
            timeout_s=120,
        )

    steps["push"] = push
    if push["returncode"] != 0:
        return {"returncode": push["returncode"], "step": "git push", "steps": steps}

    return {"returncode": 0, "steps": steps}
