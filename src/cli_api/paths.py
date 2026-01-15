from __future__ import annotations
from pathlib import Path

def safe_work_path(workdir: str, relative: str) -> str:
    """
    Resolve 'relative' under workdir and prevent path traversal.
    Returns an absolute path as string.
    """
    base = Path(workdir).resolve()
    target = (base / relative).resolve()
    if base != target and base not in target.parents:
        raise ValueError("dest_dir escapes WORKDIR")
    return str(target)
