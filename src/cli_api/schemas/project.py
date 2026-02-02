# schemas/workflows.py
from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Optional

from cli_api.schemas.git import GitConfig
from cli_api.schemas.kubectl import KubernetesSecrets
from cli_api.schemas.prometheus import PrometheusCheckConfig


class CreateProjectScript(BaseModel):
    enabled: bool = False
    configmap_name: Optional[str] = Field(default=None, min_length=1)
    script_key: str = Field(default="bootstrap.sh", min_length=1)
    mount_dir: str = Field(default="/scripts", min_length=1)
    filename: str = Field(default="bootstrap.sh", min_length=1)

class CreateProjectReq(BaseModel):
    core_namespace: str = Field(
        min_length=1,
        description="Namespace where Greymatter core is installed (contains greymatter-core-repo secret)",
    )

    openshift: bool = Field(
        default=False,
        description="Enable OpenShift support",
    )

    security: str = Field(
        default="spire",
        description="Mesh security type",
        pattern="^(plaintext|spire|pki)$",
    )
    script: CreateProjectScript = Field(default_factory=CreateProjectScript)

class BootstrapTenantReq(BaseModel):

    workspace_name: Optional[str] = None
    create_project: CreateProjectReq = Field(default_factory=CreateProjectReq)
    kubernetes: KubernetesSecrets
    git: GitConfig
    prometheus_check: PrometheusCheckConfig = Field(default_factory=PrometheusCheckConfig)
    namespace: str = Field(
        min_length=1,
        description="Tenant namespace (also used as Greymatter project name)",
    )

    
