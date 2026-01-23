# schemas/workflows.py
from __future__ import annotations

from pydantic import BaseModel, Field, model_validator
from pydantic.config import ConfigDict
from typing import Optional

from .git import GitConfig
from .greymatter import CreatePlatformOptions
from .kubectl import KubernetesSecrets
from .prometheus import PrometheusCheckConfig

class WorkflowBaseReq(BaseModel):
    git: GitConfig
    workspace_name: Optional[str] = None

class BootstrapCoreReq(WorkflowBaseReq):
    model_config = ConfigDict(populate_by_name=True)

    namespace: str | None = None

    create_platform: CreatePlatformOptions = Field(default_factory=CreatePlatformOptions)

    kubernetes: KubernetesSecrets = Field(
        default_factory=KubernetesSecrets,
        alias="kubectl",
    )
    prometheus_check: PrometheusCheckConfig = Field(default_factory=PrometheusCheckConfig)

    @model_validator(mode="after")
    def normalize_namespace(self):
        ns = (self.namespace or "").strip() or None

        k_ns = getattr(self.kubernetes, "namespace", None)
        p_ns = getattr(self.create_platform, "namespace", None)

        if ns:
            if not k_ns:
                self.kubernetes.namespace = ns
            if not p_ns:
                self.create_platform.namespace = ns

        if not self.kubernetes.namespace:
            raise ValueError("namespace is required (top-level or kubernetes.namespace)")
        if not self.create_platform.namespace:
            raise ValueError("namespace is required (top-level or create_platform.namespace)")

        if self.kubernetes.namespace != self.create_platform.namespace:
            raise ValueError(
                f"namespace mismatch: kubernetes.namespace={self.kubernetes.namespace} "
                f"create_platform.namespace={self.create_platform.namespace}"
            )

        self.namespace = self.kubernetes.namespace
        return self

class BootstrapTenantReq(WorkflowBaseReq):
    tenant_name: str = Field(min_length=1, description="Tenant identifier/name")
    namespace: str | None = None
    prometheus_check: PrometheusCheckConfig = Field(default_factory=PrometheusCheckConfig)

    @model_validator(mode="after")
    def require_namespace(self):
        ns = (self.namespace or "").strip() or None
        if not ns:
            raise ValueError("namespace is required for bootstrap-tenant")
        self.namespace = ns
        return self