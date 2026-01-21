from pydantic import BaseModel, Field, model_validator
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
    namespace: str | None = None
    workspace_name: Optional[str] = None
    create_platform: CreatePlatformOptions = Field(default_factory=CreatePlatformOptions)
    git: GitBehavior = Field(default_factory=GitBehavior)
    kubernetes: KubernetesSecrets = Field(
        default_factory=KubernetesSecrets,
        alias="kubectl",
    )
    
    @model_validator(mode="after")
    def normalize_namespace(self):
        ns = (self.namespace or "").strip() or None

        k_ns = getattr(self.kubernetes, "namespace", None)
        p_ns = getattr(self.create_platform, "namespace", None)

        # If top-level namespace is provided, fill missing children
        if ns:
            if not k_ns:
                self.kubernetes.namespace = ns
            if not p_ns:
                self.create_platform.namespace = ns

        # If still missing anywhere, fail
        if not self.kubernetes.namespace:
            raise ValueError("namespace is required (top-level or kubernetes.namespace)")
        if not self.create_platform.namespace:
            raise ValueError("namespace is required (top-level or create_platform.namespace)")

        # If both exist and conflict, fail
        if self.kubernetes.namespace != self.create_platform.namespace:
            raise ValueError(
                f"namespace mismatch: kubernetes.namespace={self.kubernetes.namespace} "
                f"create_platform.namespace={self.create_platform.namespace}"
            )

        # Optionally: set top-level to the normalized value
        self.namespace = self.kubernetes.namespace
        return self
class BootstrapTenantReq(WorkflowBaseReq):
    workspace_name: Optional[str] = None
    tenant_name: str = Field(min_length=1, description="Tenant identifier/name")
    git: GitBehavior = Field(default_factory=GitBehavior)
    namespace: str | None = None
