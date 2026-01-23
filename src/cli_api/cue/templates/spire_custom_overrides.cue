package greymatter

import (
    "encoding/yaml"
)

internals:spire:helm:overrides_config: "spire_with_customizations"
spire_with_customizations: yaml.Marshal({spire_overrides & {
    "spire-agent": {
        image: {
            registry: defaults.image_repository
            repository: "spiffe/spire-agent"
            tag: "1.13.0"
        }
        fsGroupFix: {
            image: {
                registry: defaults.image_repository
                repository: "chainguard/bash"
                tag: "latest"
            }
        }
        socketAlternate: {
            image: {
                registry: defaults.image_repository
                repository: "chainguard/bash"
                tag: "latest"
            }
        }
    }
    "spiffe-csi-driver": {
        image: {
            registry: defaults.image_repository
            repository: "spiffe/spiffe-csi-driver"
            tag: "0.2.7"
        }
        nodeDriverRegistrar: {
            image: {
                registry: defaults.image_repository
                repository: "sig-storage/csi-node-driver-registrar"
                tag: "v2.9.4"
            }
        }
        selinux: {
            image: {
                registry: defaults.image_repository
                repository: "ubi9"
                tag: "latest"
            }
        }
    }
    "spire-server": {
        image: {
            registry: defaults.image_repository
            repository: "spiffe/spire-server"
            tag: "1.13.0"
        }
        tools: {
            kubectl: {
                image: {
                    registry: defaults.image_repository
                    repository: "rancher/kubectl"
                    tag: "v1.27.0-internal"
                }
            }
        }
        controllerManager: {
            image: {
                registry: defaults.image_repository
                repository: "spiffe/spire-controller-manager"
                tag: "0.6.2"
            }
        }
    }
}})