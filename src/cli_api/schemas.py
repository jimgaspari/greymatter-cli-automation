from pydantic import BaseModel, Field
from typing import Optional, Literal, Union, List

class CloneViaSSH(BaseModel):
    type: Literal["ssh"] = "ssh"
    repo_url: str = Field(description="git@host:owner/repo.git")
    ssh_private_key_b64: str
    known_hosts: Optional[str] = None
    strict_host_key_checking: bool = True

class CloneViaHTTPS(BaseModel):
    type: Literal["https"] = "https"
    repo_url: str = Field(description="https://host/owner/repo.git")

    # Optional auth (public repos need none)
    username: Optional[str] = Field(default=None, description="Basic auth username")
    password: Optional[str] = Field(default=None, description="Basic auth password")
    token: Optional[str] = Field(default=None, description="Personal access token")

CloneSpec = Union[CloneViaSSH, CloneViaHTTPS]

SecurityType = Literal["plaintext", "spire", "pki"]

class CreatePlatformOptions(BaseModel):
    # Audits Options
    elasticsearch_address: Optional[str] = Field(default=None, description="Host:Port of external ElasticSearch")
    no_elasticsearch_tls_verify: bool = Field(default=False, description="Disable TLS verification for ElasticSearch client")

    # Image Options
    image_pull_secret: Optional[str] = Field(default=None, description='Kubernetes secret for OCI creds (default "greymatter-image-pull")')
    image_repository: Optional[str] = Field(default=None, description='OCI repository URI (default "oci.download.greymatter.io")')

    # PKI Options
    pki_cert: Optional[str] = Field(default=None, description='Kubernetes secret for PKI mTLS certificate (default "(edge-cert)")')

    # Platform Options
    display_name: Optional[str] = Field(default=None, description='Mesh display name (default "Greymatter Mesh")')
    namespace: Optional[str] = Field(default=None, description='Install namespace (default "greymatter")')
    tenant_namespace: Optional[List[str]] = Field(default=None, description="Tenant project namespace(s)")
    openshift: bool = Field(default=False, description="Enable OpenShift support")
    no_gitops_fips: bool = Field(default=False, description="Disable FIPS 140-3 for GitOps requests")
    security: Optional[SecurityType] = Field(default=None, description='Mesh security type: plaintext|spire|pki')

    # Prometheus Options
    prometheus_address: Optional[str] = Field(default=None, description="Host:Port of external Prometheus")

    # Spire Options
    no_managed_spire: bool = Field(default=False, description="Do not deploy/maintain Spire")
    spire_namespace: Optional[str] = Field(default=None, description='Spire namespace (default "spire")')

class WorkflowBaseReq(BaseModel):
    clone: CloneSpec
    branch: Optional[str] = "main"
    depth: int = 1

class BootstrapCoreReq(WorkflowBaseReq):
    # Optional: allow caller to set a stable name; otherwise we generate
    workspace_name: Optional[str] = None
    create_platform: CreatePlatformOptions = Field(default_factory=CreatePlatformOptions)

class BootstrapTenantReq(WorkflowBaseReq):
    workspace_name: Optional[str] = None
    tenant_name: str = Field(min_length=1, description="Tenant identifier/name")
    # Add more tenant params as needed later