from __future__ import annotations
from typing import Dict
import requests
import urllib3
from urllib.parse import urlparse


def parse_git_repo_url(repo_url: str) -> Dict[str, str]:
    """
    Parse a git repo URL (https or ssh) into base_url, host, owner, repo.
    """
    repo_url = repo_url.strip()

    # SSH form: git@host:owner/repo.git
    if repo_url.startswith("git@"):
        user_host, path = repo_url.split(":", 1)
        host = user_host.split("@", 1)[1]

        owner, repo = path.split("/", 1)
        repo = repo.removesuffix(".git")

        return {
            "scheme": "ssh",
            "host": host,
            "base_url": f"https://{host}",
            "owner": owner,
            "repo": repo,
        }

    # HTTPS form
    parsed = urlparse(repo_url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Unsupported repo URL scheme: {parsed.scheme}")

    path = parsed.path.lstrip("/")
    parts = path.split("/")
    if len(parts) < 2:
        raise ValueError(f"Invalid repo URL path: {parsed.path}")

    owner = parts[0]
    repo = parts[1].removesuffix(".git")

    return {
        "scheme": parsed.scheme,
        "host": parsed.netloc,
        "base_url": f"{parsed.scheme}://{parsed.netloc}",
        "owner": owner,
        "repo": repo,
    }

def ensure_gitea_repo(
    *,
    base_url: str,
    owner: str,
    repo: str,
    token: str,
    private: bool = True,
    verify_ssl: bool = True,
) -> Dict[str, Any]:
    """
    Ensure a Gitea repository exists.
    If verify_ssl=False, self-signed certificates are allowed.
    """

    if not verify_ssl:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    headers = {
        "Authorization": f"token {token}",
        "Content-Type": "application/json",
    }

    # 1) Check if repo exists
    try:
        r = requests.get(
            f"{base_url}/api/v1/repos/{owner}/{repo}",
            headers=headers,
            timeout=10,
            verify=verify_ssl,
        )
    except Exception as e:
        return {
            "returncode": 1,
            "step": "check repo exists",
            "stderr": str(e),
        }

    if r.status_code == 200:
        return {
            "returncode": 0,
            "exists": True,
        }

    if r.status_code != 404:
        return {
            "returncode": 1,
            "step": "check repo exists",
            "stderr": r.text,
            "status_code": r.status_code,
        }

    # 2) Create repo
    try:
        r = requests.post(
            f"{base_url}/api/v1/user/repos",
            headers=headers,
            json={
                "name": repo,
                "private": private,
                "auto_init": True,
            },
            timeout=10,
            verify=verify_ssl,
        )
    except Exception as e:
        return {
            "returncode": 1,
            "step": "create repo",
            "stderr": str(e),
        }

    if r.status_code not in (200, 201):
        return {
            "returncode": 1,
            "step": "create repo",
            "stderr": r.text,
            "status_code": r.status_code,
        }

    return {
        "returncode": 0,
        "exists": False,
        "created": True,
    }
