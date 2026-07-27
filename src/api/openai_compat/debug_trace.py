"""
Phase 9 — Debug/Trace System
=============================
Records every pipeline stage for each request.

When DEBUG mode is enabled (config/openai_layer.json: "enable_debug_mode": true),
each request generates a structured execution trace that is:
  - Written to logs
  - Optionally returned in HTTP response headers (X-DM-Trace-*)
  - Available as JSON in the response body under x_dm_pipeline

The trace shows: Authentication → Cache → Identity → Memory → Knowledge →
                 Tool Selector → Workflow → DAG → Agent → LLM → Memory Writer →
                 Artifact → Audit → Formatter → Client
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("dm.openai.debug")


def _load_layer_config() -> Dict[str, Any]:
    cfg_path = Path(__file__).resolve().parents[3] / "config" / "openai_layer.json"
    try:
        if cfg_path.exists():
            return json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


@dataclass
class TraceStep:
    stage: str
    status: str  # OK | MISS | HIT | SKIP | ERROR
    detail: Optional[str] = None
    duration_ms: Optional[float] = None
    data: Optional[Dict[str, Any]] = None


@dataclass
class RequestTrace:
    request_id: str
    model: str
    user_id: str
    started_at: float = field(default_factory=time.perf_counter)
    steps: List[TraceStep] = field(default_factory=list)

    def add(
        self,
        stage: str,
        status: str = "OK",
        detail: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> None:
        elapsed = round((time.perf_counter() - self.started_at) * 1000, 2)
        step = TraceStep(stage=stage, status=status, detail=detail, duration_ms=elapsed, data=data)
        self.steps.append(step)

        _cfg = _load_layer_config()
        if _cfg.get("enable_debug_mode", False):
            log.debug(
                f"[TRACE] {self.request_id} | {stage:30s} | {status:6s} | "
                f"+{elapsed:7.1f}ms | {detail or ''}"
            )

    def to_dict(self) -> Dict[str, Any]:
        total_ms = round((time.perf_counter() - self.started_at) * 1000, 2)
        return {
            "request_id": self.request_id,
            "model": self.model,
            "user_id": self.user_id,
            "total_ms": total_ms,
            "stages": [
                {
                    "stage": s.stage,
                    "status": s.status,
                    "detail": s.detail,
                    "at_ms": s.duration_ms,
                }
                for s in self.steps
            ],
        }

    def to_headers(self) -> Dict[str, str]:
        """Return HTTP headers carrying high-level trace info."""
        _cfg = _load_layer_config()
        if not _cfg.get("debug_headers", True):
            return {}
        total_ms = round((time.perf_counter() - self.started_at) * 1000, 2)
        return {
            "X-DM-Request-Id": self.request_id,
            "X-DM-Pipeline-Ms": str(total_ms),
            "X-DM-Stages": str(len(self.steps)),
            "X-DM-Model": self.model,
            "X-DM-User": self.user_id,
        }

    def log_summary(self) -> None:
        cfg = _load_layer_config()
        if not cfg.get("enable_debug_mode", False):
            return
        total_ms = round((time.perf_counter() - self.started_at) * 1000, 2)
        stages_txt = " → ".join(
            f"{s.stage}({'✓' if s.status in ('OK','HIT') else '✗'})"
            for s in self.steps
        )
        log.info(
            f"[TRACE SUMMARY] {self.request_id} | {total_ms:.0f}ms | {stages_txt}"
        )


def is_debug_mode() -> bool:
    """Return True if debug mode is enabled in config."""
    return _load_layer_config().get("enable_debug_mode", False)
