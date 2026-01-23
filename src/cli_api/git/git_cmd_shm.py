# src/cli_api/git_cmd.py (shim)
from cli_api.git.clone import clone_repo
from cli_api.git.branch import ensure_branch
from cli_api.git.identity import ensure_git_identity
from cli_api.git.commit import git_has_changes, git_commit_and_push
from cli_api.git.auth import prepare_ssh_auth, prepare_https_auth

