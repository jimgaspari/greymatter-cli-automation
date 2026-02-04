# schemas/git.py
from __future__ import annotations

from pydantic import BaseModel, Field, model_validator, ConfigDict
from typing import Optional, Literal, Dict
from dataclasses import dataclass

GitTransport = Literal["ssh", "https"]

class GitConfig(BaseModel):
    # Transport + remote
    type: GitTransport = Field(default="ssh", description="ssh or https")
    repo_url: Optional[str] = None

    depth: int = 1

    # Branch behavior
    base_branch: str = "main"
    target_branch: Optional[str] = None
    create_branch_if_missing: bool = True
    push_branch_to_remote: bool = False
    push_changes: bool = False

    # Commit identity
    author_name: Optional[str] = None
    author_email: Optional[str] = None

    # --- SSH auth ---
    ssh_private_key: Optional[str] = Field(default=None, description="Raw SSH private key (PEM)")
    known_hosts: Optional[str] = None
    strict_host_key_checking: bool = True

    # --- HTTPS auth ---
    username: Optional[str] = None
    password: Optional[str] = None
    token: Optional[str] = None
    insecure_skip_tls_verify: bool = False

    @model_validator(mode="after")
    def validate_auth(self):
        # SSH requires key
        if self.type == "ssh":
            if not (self.ssh_private_key or "").strip():
                raise ValueError("git.ssh_private_key is required when git.type=ssh")
            # known_hosts optional but recommended when strict on
            return self

        # HTTPS: allow anonymous clone if no password/token
        # (creation/push likely needs token/password, but don't force at schema level)
        return self

class GitOverrides(BaseModel):
    model_config = ConfigDict(extra="forbid")  # optional but recommended

    # Transport + remote
    type: Optional[GitTransport] = None
    repo_url: Optional[str] = None
    depth: Optional[int] = None

    # Branch behavior
    base_branch: Optional[str] = None
    target_branch: Optional[str] = None
    create_branch_if_missing: Optional[bool] = None
    push_branch_to_remote: Optional[bool] = None
    push_changes: Optional[bool] = None

    # Commit identity
    author_name: Optional[str] = None
    author_email: Optional[str] = None

    # --- SSH auth ---
    ssh_private_key: Optional[str] = None
    known_hosts: Optional[str] = None
    strict_host_key_checking: Optional[bool] = None

    # --- HTTPS auth ---
    username: Optional[str] = None
    password: Optional[str] = None
    token: Optional[str] = None
    insecure_skip_tls_verify: Optional[bool] = None

@dataclass
class SshAuth:
    env: Dict[str, str]
    key_path: str
    known_hosts_path: Optional[str]
