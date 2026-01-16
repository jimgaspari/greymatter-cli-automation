from pydantic import BaseModel, Field
from typing import Optional, Literal, Union, Dict
from dataclasses import dataclass

# Git Schemas
class CloneViaSSH(BaseModel):
    type: Literal["ssh"] = "ssh"
    repo_url: str = Field(description="git@host:owner/repo.git")
    ssh_private_key: str = Field(
        description="Raw SSH private key (PEM format)"
    )
    known_hosts: Optional[str] = None
    strict_host_key_checking: bool = True

class CloneViaHTTPS(BaseModel):
    type: Literal["https"] = "https"
    repo_url: str = Field(description="https://host/owner/repo.git")

    # Optional auth (public repos need none)
    username: Optional[str] = Field(default=None, description="Basic auth username")
    password: Optional[str] = Field(default=None, description="Basic auth password")
    token: Optional[str] = Field(default=None, description="Personal access token")

class GitBehavior(BaseModel):
    base_branch: str = "main"                 # branch we can safely clone
    target_branch: Optional[str] = None       # branch we want to work on (e.g. "test1")
    create_branch_if_missing: bool = True     # create locally if not found remotely
    push_branch_to_remote: bool = False       # create remote branch if it doesn't exist
    push_changes: bool = False                # push commits after greymatter runs

CloneSpec = Union[CloneViaSSH, CloneViaHTTPS]

@dataclass
class SshAuth:
    env: Dict[str, str]
    key_path: str
    known_hosts_path: Optional[str]