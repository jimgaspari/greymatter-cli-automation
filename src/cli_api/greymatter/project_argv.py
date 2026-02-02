from typing import List


def build_gm_create_project_argv(*, namespace: str, create_project) -> list[str]:
    argv = ["greymatter", "create", "project", namespace]
    if getattr(create_project, "openshift", False):
        argv.append("--openshift")
    sec = getattr(create_project, "security", "spire")
    if sec:
        argv += ["--security", sec]
    return argv

