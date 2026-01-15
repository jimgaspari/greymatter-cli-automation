from __future__ import annotations
import subprocess
from typing import Dict, List, Optional
from .config import settings

def run_cmd(argv: List[str], timeout_s: int = 60, env: Optional[Dict[str, str]] = None) -> Dict:
    """
    Run a command WITHOUT shell=True. Captures stdout/stderr and returns structured result.
    """
    try:
        p = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            env=env,
            cwd=settings.workdir,
        )
        return {
            "argv": argv,
            "exit_code": p.returncode,
            "stdout": p.stdout,
            "stderr": p.stderr,
        }
    except subprocess.TimeoutExpired as e:
        return {
            "argv": argv,
            "exit_code": 124,
            "stdout": e.stdout or "",
            "stderr": (e.stderr or "") + "\nTimed out",
        }
