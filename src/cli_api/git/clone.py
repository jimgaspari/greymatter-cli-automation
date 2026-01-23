from __future__ import annotations
from typing import Tuple, Dict, Optional
import logging

from cli_api.schemas import GitConfig
from cli_api.runner import run_cmd
from cli_api.config import settings
from cli_api.paths import safe_work_path

def git_clone_https(
    repo_https_url: str,
    dest_dir: str,
    branch: Optional[str],
    depth: int,
    env: dict,
    timeout_s: int = 180,
) -> tuple[str, dict]:
    dest_path = safe_work_path(settings.workdir, dest_dir)

    logging.info("Cloning Git Repo %s", repo_https_url)

    argv = ["git", "clone"]
    if depth:
        argv += ["--depth", str(depth)]
    if branch:
        argv += ["--branch", branch]
    argv += [repo_https_url, dest_path]

    result = run_cmd(argv, timeout_s=timeout_s, env=env, cwd=settings.workdir, check=False)
    return dest_path, result

def git_clone_ssh(
    repo_ssh_url: str,
    dest_dir: str,
    branch: Optional[str],
    depth: int,
    env: dict,
    timeout_s: int = 180,
) -> tuple[str, dict]:
    dest_path = safe_work_path(settings.workdir, dest_dir)

    logging.info("Cloning Git Repo %s", repo_ssh_url)

    # Build base clone args
    base_argv = ["git", "clone"]
    if depth:
        base_argv += ["--depth", str(depth)]

    # Attempt clone with branch (if provided)
    if branch:
        argv = base_argv + ["--branch", branch, repo_ssh_url, dest_path]
        res = run_cmd(argv, timeout_s=timeout_s, env=env, cwd=settings.workdir, check=False)

        if res.get("returncode", 1) == 0:
            return dest_path, res

        # If branch doesn't exist, fall back to default branch clone
        stderr = (res.get("stderr") or "")
        if "Remote branch" in stderr and "not found" in stderr:
            logging.info("Branch %s not found; retrying clone without --branch", branch)
        else:
            # Not a missing-branch error → return the failure
            return dest_path, res

    # Fallback/default clone
    argv = base_argv + [repo_ssh_url, dest_path]
    res2 = run_cmd(argv, timeout_s=timeout_s, env=env, cwd=settings.workdir, check=False)
    return dest_path, res2


def clone_repo(
    *, 
    git: GitConfig, 
    dest_dir: str, 
    env: dict, 
    timeout_s: int = 180
) -> Tuple[str, Dict]:
    if git.type == "ssh":
        return git_clone_ssh(
            repo_ssh_url=git.repo_url, 
            dest_dir=dest_dir, 
            branch=git.base_branch, 
            depth=git.depth, 
            env=env, 
            timeout_s=timeout_s
        )
    return git_clone_https(
        repo_https_url=git.repo_url, 
        dest_dir=dest_dir, 
        branch=git.base_branch, 
        depth=git.depth, 
        env=env, 
        timeout_s=timeout_s
    )


