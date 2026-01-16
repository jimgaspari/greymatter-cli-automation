from pydantic import BaseModel, Field
from typing import Optional

from .git import CloneSpec, GitBehavior
from .greymatter import CreatePlatformOptions

class WorkflowBaseReq(BaseModel):
    clone: CloneSpec
    branch: Optional[str] = "main"
    depth: int = 1

class BootstrapCoreReq(WorkflowBaseReq):
    # Optional: allow caller to set a stable name; otherwise we generate
    workspace_name: Optional[str] = None
    create_platform: CreatePlatformOptions = Field(default_factory=CreatePlatformOptions)
    git: GitBehavior = Field(default_factory=GitBehavior)

class BootstrapTenantReq(WorkflowBaseReq):
    workspace_name: Optional[str] = None
    tenant_name: str = Field(min_length=1, description="Tenant identifier/name")
    git: GitBehavior = Field(default_factory=GitBehavior)
