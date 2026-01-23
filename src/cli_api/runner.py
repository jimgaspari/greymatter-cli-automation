import subprocess
from typing import Any, Mapping, Optional, Sequence, Union


def run_cmd(
    cmd: Sequence[str],
    *,
    input: Optional[Union[str, bytes]] = None,
    cwd: Optional[str] = None,
    env: Optional[Mapping[str, str]] = None,
    timeout_s: Optional[float] = None,
    check: bool = True,
    text: bool = True,
) -> dict[str, Any]:
    """
    Run a command and return {'stdout','stderr','returncode'}.

    Supports:
      - input: str|bytes passed to stdin
      - timeout_s: seconds before timing out
      - cwd/env/check/text similar to subprocess.run
    """
    # If bytes input is provided, force text=False unless caller already did.
    if isinstance(input, (bytes, bytearray)) and text:
        text = False

    try:
        r = subprocess.run(
            list(cmd),
            input=input,
            cwd=cwd,
            env=dict(env) if env is not None else None,
            capture_output=True,
            text=text,
            timeout=timeout_s,
            check=False,  # we raise ourselves to keep stdout/stderr
        )
    except subprocess.TimeoutExpired as e:
        # Normalize timeout error into same dict shape and raise if check=True
        out = {
            "stdout": (e.stdout.decode() if isinstance(e.stdout, (bytes, bytearray)) else (e.stdout or "")),
            "stderr": (e.stderr.decode() if isinstance(e.stderr, (bytes, bytearray)) else (e.stderr or "")),
            "returncode": -1,
        }
        if check:
            raise
        return out

    out = {"stdout": r.stdout or "", "stderr": r.stderr or "", "returncode": r.returncode}

    if check and r.returncode != 0:
        raise subprocess.CalledProcessError(
            r.returncode,
            list(cmd),
            output=out["stdout"],
            stderr=out["stderr"],
        )

    return out
