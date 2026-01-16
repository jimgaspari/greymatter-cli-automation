# src/cli_api/git_cmd.py (shim)
from .clone import clone_repo
from .branch import ensure_branch
from .identity import ensure_git_identity
from .commit import git_has_changes, git_commit_and_push
from .auth import prepare_ssh_auth, prepare_https_auth

