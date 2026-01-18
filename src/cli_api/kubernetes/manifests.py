from pathlib import Path
import logging

from ..runner import run_cmd

def apply_platform_operator_manifest(repo_path: str, namespace: str, *, git_env: dict) -> dict:
    """
    Apply platform-operator.yaml from the repo.
    """
    # Adjust if the file lives somewhere else in the repo
    manifest = Path(repo_path) / "platform-operator.yaml"
    if not manifest.exists():
        logging.warning("platform-operator.yaml not found; generating via greymatter CLI")

        gen = run_cmd(
            ["greymatter", "create", "operator"],
            cwd=repo_path,
            env=git_env,
            check=False,
            timeout_s=180,
        )

        if gen.get("returncode", 1) != 0:
            return {
                "returncode": gen["returncode"],
                "step": "greymatter create operator",
                "steps": {"generate_operator": gen},
            }

        # After generation, the file MUST exist
        manifest = Path(repo_path) / "platform-operator.yaml"
        if not manifest.exists():
            return {
                "returncode": 1,
                "step": "apply platform-operator",
                "stderr": "greymatter create operator succeeded but platform-operator.yaml was not created",
            }

    logging.warning("Applying platform operator manifest: %s", str(manifest))

    # If your manifest is namespace-scoped resources, -n is fine.
    # If it contains cluster-scoped resources (CRDs, ClusterRole, etc),
    # kubectl will ignore -n for those objects anyway.
    return run_cmd(
        ["kubectl", "apply", "-f", str(manifest), "-n", namespace],
        cwd=repo_path,
        env=git_env,   # env not required for kubectl, but harmless
        check=False,   # don't throw; return stderr/stdout so API can report
        timeout_s=180,
    )
