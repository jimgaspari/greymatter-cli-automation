from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Optional, List


class PrometheusCheckConfig(BaseModel):
    enabled: bool = False
    require_all_up: bool = True
    job_allowlist: Optional[List[str]] = None

    # optional overrides (only if you want escape hatches)
    scheme: str = "http"
    port: int = 9090
    service_candidates: Optional[List[str]] = None
    path_prefix_candidates: Optional[List[str]] = None
    timeout_s: float = 10.0
