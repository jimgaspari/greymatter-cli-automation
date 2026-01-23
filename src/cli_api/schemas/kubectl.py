from pydantic import BaseModel, Field
from typing import Optional

class ImagePullSecret(BaseModel):
    docker_server: str = "oci.download.greymatter.io"
    docker_username: str
    docker_password: str
    secret_name: str = "greymatter-image-pull"

class RepoSecret(BaseModel):
    secret_name: str = "greymatter-core-repo"

class EdgeIngressTLSSecret(BaseModel):
    enabled: bool = False
    secret_name: str = Field(default="greymatter-edge-ingress", min_length=1)

    # PEM strings
    tls_crt: Optional[str] = None
    tls_key: Optional[str] = None
    ca_crt: Optional[str] = None


class KubernetesSecrets(BaseModel):
    namespace: Optional[str] = None
    image_pull: ImagePullSecret
    create_repo_secret: bool = True
    edge_ingress_tls_secret: EdgeIngressTLSSecret = Field(default_factory=EdgeIngressTLSSecret)
