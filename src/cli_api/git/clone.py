from __future__ import annotations
from typing import Tuple, Dict, Optional, List

from ..schemas import CloneSpec
from ..runner import run_cmd
from ..config import settings
from ..paths import safe_work_path

def git_clone_https(
    *,
    repo_https_url: str,
    dest_dir: str,
    branch: Optional[str],
    depth: int,
    env: dict,
    timeout_s: int = 180,
) -> Tuple[str, Dict]:
    if not repo_https_url.startswith("https://"):
        raise ValueError("repo_https_url must start with https://")

    dest_path = safe_work_path(settings.workdir, dest_dir)

    argv: List[str] = ["git", "clone"]
    if depth:
        argv += ["--depth", str(depth)]
    if branch:
        argv += ["--branch", branch]
    argv += [repo_https_url, dest_path]

    result = run_cmd(argv, timeout_s=timeout_s, env=env, cwd=settings.workdir)
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

    argv = ["git", "clone"]
    if depth:
        argv += ["--depth", str(depth)]
    if branch:
        argv += ["--branch", branch]
    argv += [repo_ssh_url, dest_path]

    result = run_cmd(argv, timeout_s=timeout_s, env=env, cwd=settings.workdir)
    return dest_path, result

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
