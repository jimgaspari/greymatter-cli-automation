from pydantic import BaseModel, Field 
from pydantic.config import ConfigDict

from typing import Optional

from .git import CloneSpec, GitBehavior
from .greymatter import CreatePlatformOptions
from .kubectl import KubernetesSecrets

class WorkflowBaseReq(BaseModel):
    clone: CloneSpec
    branch: Optional[str] = "main"
    depth: int = 1

class BootstrapCoreReq(WorkflowBaseReq):
    model_config = ConfigDict(populate_by_name=True)

    workspace_name: Optional[str] = None
    create_platform: CreatePlatformOptions = Field(default_factory=CreatePlatformOptions)
    git: GitBehavior = Field(default_factory=GitBehavior)
    kubernetes: KubernetesSecrets = Field(
        default_factory=KubernetesSecrets,
        alias="kubectl",
    )

class BootstrapTenantReq(WorkflowBaseReq):
    workspace_name: Optional[str] = None
    tenant_name: str = Field(min_length=1, description="Tenant identifier/name")
    git: GitBehavior = Field(default_factory=GitBehavior)
