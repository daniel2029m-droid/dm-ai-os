"""Path helpers for Facebook intelligence storage (aligned with Project_State layout)."""

from __future__ import annotations

import os
from pathlib import Path


def get_project_state_root() -> Path:
    """Resolve Project_State root following DM AI OS conventions."""
    base = os.getenv("DM_STORAGE_DIR") or os.getenv("DM_DATA_DIR")
    if base:
        root = Path(base)
    elif os.getenv("VERCEL"):
        root = Path("/tmp/Project_State")
    else:
        root = Path(__file__).resolve().parent.parent.parent / "Project_State"
    try:
        root.mkdir(parents=True, exist_ok=True)
    except Exception:
        root = Path("/tmp/Project_State")
        root.mkdir(parents=True, exist_ok=True)
    return root


def get_facebook_dir() -> Path:
    d = get_project_state_root() / "Facebook"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_facebook_db_path() -> Path:
    return get_facebook_dir() / "facebook_intelligence.db"


def get_sessions_dir() -> Path:
    d = get_facebook_dir() / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_screenshots_dir() -> Path:
    d = get_facebook_dir() / "screenshots"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_backups_dir() -> Path:
    d = get_facebook_dir() / "backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_network_capture_dir() -> Path:
    d = get_facebook_dir() / "network_captures"
    d.mkdir(parents=True, exist_ok=True)
    return d
