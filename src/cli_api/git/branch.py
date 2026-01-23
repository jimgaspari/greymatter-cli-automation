from __future__ import annotations
from typing import Dict, Optional
import logging

from cli_api.runner import run_cmd


def ensure_branch(
    *,
    base_branch: str,
    target_branch: str,
    repo_path: str,
    git_env: Optional[dict] = None,
    push_to_remote: bool = False,
) -> Dict:
    """
    Behavior:
      - If remote branch exists: fetch it and check out from origin/<target_branch>
      - Else if local branch exists: check out local
      - Else: create local branch from origin/<base_branch> (or local base fallback)
      - If push_to_remote: push -u origin <target_branch> (sets upstream)
    """

    # Keep remote refs current (safe even if branch missing)
    run_cmd(["git", "fetch", "--prune", "origin"], cwd=repo_path, env=git_env, check=True)

    # Check remote existence on the server (not local refs)
    remote_exists = run_cmd(
        ["git", "ls-remote", "--exit-code", "--heads", "origin", target_branch],
        cwd=repo_path,
        env=git_env,
        check=False,
    ).get("returncode", 1) == 0

    # Check local existence
    local_exists = run_cmd(
        ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{target_branch}"],
        cwd=repo_path,
        env=git_env,
        check=False,
    ).get("returncode", 1) == 0

    if remote_exists:
        logging.info("Remote branch exists: %s", target_branch)

        # Fetch the exact branch ref so origin/<target_branch> is guaranteed to exist locally
        run_cmd(
            ["git", "fetch", "origin",
             f"+refs/heads/{target_branch}:refs/remotes/origin/{target_branch}"],
            cwd=repo_path,
            env=git_env,
            check=True,
        )

        co = run_cmd(
            ["git", "checkout", "-B", target_branch, f"origin/{target_branch}"],
            cwd=repo_path,
            env=git_env,
            check=True,
        )

        # Upstream should exist in this case; set it (idempotent)
        run_cmd(
            ["git", "branch", "--set-upstream-to", f"origin/{target_branch}", target_branch],
            cwd=repo_path,
            env=git_env,
            check=False,
        )
        return co

    if local_exists:
        logging.info("Remote branch missing; using local branch: %s", target_branch)
        return run_cmd(
            ["git", "checkout", target_branch],
            cwd=repo_path,
            env=git_env,
            check=True,
        )

    # Neither remote nor local exists: create from base
    logging.info("Branch %s does not exist; creating from base %s", target_branch, base_branch)

    run_cmd(["git", "fetch", "origin", base_branch], cwd=repo_path, env=git_env, check=False)

    base_ref = f"origin/{base_branch}"
    base_ref_exists = run_cmd(
        ["git", "rev-parse", "--verify", "--quiet", base_ref],
        cwd=repo_path,
        env=git_env,
        check=False,
    ).get("returncode", 1) == 0
    if not base_ref_exists:
        base_ref = base_branch

    co = run_cmd(
        ["git", "checkout", "-B", target_branch, base_ref],
        cwd=repo_path,
        env=git_env,
        check=True,
    )

    if push_to_remote:
        # This creates the remote branch and sets upstream in one shot
        run_cmd(
            ["git", "push", "-u", "origin", target_branch],
            cwd=repo_path,
            env=git_env,
            check=True,
        )

    return co
