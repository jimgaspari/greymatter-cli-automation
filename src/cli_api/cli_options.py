from pydantic import BaseModel, Field
from typing import Optional, Literal, Union, List
from .schemas import CreatePlatformOptions



def build_gm_create_platform_argv(opts: CreatePlatformOptions) -> list[str]:
    argv: list[str] = ["greymatter", "create", "platform"]

    # Audits
    if opts.elasticsearch_address:
        argv += ["--elasticsearch-address", opts.elasticsearch_address]
    if opts.no_elasticsearch_tls_verify:
        argv += ["--no-elasticsearch-tls-verify"]

    # Image
    if opts.image_pull_secret:
        argv += ["--image-pull-secret", opts.image_pull_secret]
    if opts.image_repository:
        argv += ["--image-repository", opts.image_repository]

    # PKI
    if opts.pki_cert:
        argv += ["--pki-cert", opts.pki_cert]

    # Platform
    if opts.display_name:
        argv += ["--display-name", opts.display_name]
    if opts.namespace:
        argv += ["--namespace", opts.namespace]
    if opts.no_gitops_fips:
        argv += ["--no-gitops-fips"]
    if opts.openshift:
        argv += ["--openshift"]
    if opts.security:
        argv += ["--security", opts.security]

    if opts.tenant_namespace:
        for ns in opts.tenant_namespace:
            argv += ["--tenant-namespace", ns]

    # Prometheus
    if opts.prometheus_address:
        argv += ["--prometheus-address", opts.prometheus_address]

    # Spire
    if opts.no_managed_spire:
        argv += ["--no-managed-spire"]
    if opts.spire_namespace:
        argv += ["--spire-namespace", opts.spire_namespace]

    return argv

def build_gm_create_operator_argv() -> list[str]:
    return ["greymatter", "create", "operator"]
