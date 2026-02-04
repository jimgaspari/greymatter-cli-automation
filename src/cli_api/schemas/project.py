# schemas/workflows.py
from __future__ import annotations
import logging
from pydantic import BaseModel, Field, model_validator
from typing import Any, Dict, List, Optional

from cli_api.schemas.git import GitConfig, GitOverrides
from cli_api.schemas.kubectl import KubernetesSecrets
from cli_api.schemas.prometheus import PrometheusCheckConfig


class CreateProjectScript(BaseModel):
    enabled: bool = False
    configmap_name: Optional[str] = Field(default=None, min_length=1)
    script_key: str = Field(default="bootstrap.sh", min_length=1)
    mount_dir: str = Field(default="/scripts", min_length=1)
    filename: str = Field(default="bootstrap.sh", min_length=1)

class CreateProjectSettings(BaseModel):
    openshift: bool = Field(
        default=False,
        description="Enable OpenShift support",
    )

    security: str = Field(
        default="spire",
        description="Mesh security type",
        pattern="^(plaintext|spire|pki)$",
    )

class TenantItem(BaseModel):
    namespace: str = Field(min_length=1)
    project_settings: CreateProjectSettings = Field(default_factory=CreateProjectSettings)  # reuse your existing CreateProjectReq if you prefer
    script: CreateProjectScript = Field(default_factory=CreateProjectScript)
    git: GitOverrides = Field(default_factory=GitOverrides)
    env_vars: Dict[str, str] = Field(default_factory=dict)

class BootstrapTenantReq(BaseModel):
    workspace_name: Optional[str] = None
    core_namespace: str = Field(min_length=1)
    
    # job uses concrete configs (already merged/validated by API)
    git: GitOverrides = Field(default_factory=GitOverrides)
    kubernetes: KubernetesSecrets
    prometheus_check: PrometheusCheckConfig

    tenants: List[TenantItem] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_merged_git(self):
        base = self.git.model_dump(exclude_unset=True)

        for i, t in enumerate(self.tenants):
            merged = {**base, **t.git.model_dump(exclude_unset=True)}

            # repo_url must exist after merge
            if not (merged.get("repo_url") or "").strip():
                raise ValueError(f"tenants[{i}].git.repo_url is required (or provide git.repo_url globally)")

            # this enforces ssh key rules, etc.
            try:
                GitConfig(**merged)
            except Exception as e:
                raise ValueError(f"tenants[{i}].git invalid after merge: {e}")

        return self