from pydantic import BaseModel
from typing import Optional

class ImagePullSecret(BaseModel):
    docker_server: str = "oci.download.greymatter.io"
    docker_username: str
    docker_password: str
    secret_name: str = "greymatter-image-pull"

class RepoSecret(BaseModel):
    secret_name: str = "greymatter-core-repo"

class KubernetesSecrets(BaseModel):
    namespace: Optional[str] = None
    image_pull: ImagePullSecret
    create_repo_secret: bool = True