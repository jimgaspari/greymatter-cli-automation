from __future__ import annotations
# from dataclasses import dataclass
from datetime import datetime, timezone
from fastapi import HTTPException
import os
import re
from pathlib import Path

SAFE_NAME_RE = re.compile(r"^[a-zA-Z0-9._-]+$")

def make_run_id(prefix: str = "core") -> str:
    # e.g. core-20260115T183012Z
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}-{ts}"

def ensure_workspace(workdir: str, workspace_name: str) -> str:
    if not SAFE_NAME_RE.match(workspace_name):
        raise ValueError("workspace_name contains invalid characters (allowed: letters, numbers, . _ -)")
    base = Path(workdir).resolve()
    ws = (base / workspace_name).resolve()
    if base != ws and base not in ws.parents:
        raise ValueError("workspace escapes WORKDIR")
    os.makedirs(ws, exist_ok=False)  # fail if exists; avoids accidental overwrite
    return str(ws)
