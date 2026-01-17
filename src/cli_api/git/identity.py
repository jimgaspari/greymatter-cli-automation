from __future__ import annotations
from typing import Dict
from pathlib import Path

from ..runner import run_cmd

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
    if name_res["returncode"] != 0:
        return {"returncode": name_res["returncode"], "steps": steps}

    email_res = run_cmd(
        ["git", "config", "user.email", email],
        cwd=repo_path,
        env=env,
    )
    steps["user.email"] = email_res
    if email_res["returncode"] != 0:
        return {"returncode": email_res["returncode"], "steps": steps}

    return {"returncode": 0, "steps": steps}
