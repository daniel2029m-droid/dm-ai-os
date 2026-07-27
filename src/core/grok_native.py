"""
Phase 10 — Native Grok Build Integration Core Module
=====================================================
Manages the integration between official Grok Build client and DM AI OS:

1. Detection: Scans system PATH and user directories for Grok Build CLI/UI.
2. TOML Configuration: Safely generates or merges `~/.grok/config.toml`
   registering `dm-autonomous-brain` as default model without overwriting user configs.
3. Model Catalog: Registers all 8 DM virtual models in Grok Build configuration format.
4. Diagnostics: Reports installation status, version, and config health.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger("dm.grok_native")

# All 8 DM virtual models
DM_VIRTUAL_MODELS = [
    {
        "id": "dm-autonomous-brain",
        "name": "DM Autonomous Brain",
        "context_window": 32768,
        "description": "Full autonomous orchestration: memory + agents + DAG + LLM",
        "temperature": 0.2,
    },
    {
        "id": "dm-reasoner",
        "name": "DM Reasoner",
        "context_window": 32768,
        "description": "Deep reasoning and multi-step planning model",
        "temperature": 0.2,
    },
    {
        "id": "dm-fast",
        "name": "DM Fast",
        "context_window": 8192,
        "description": "Fast summarization and rapid response model",
        "temperature": 0.5,
    },
    {
        "id": "dm-memory",
        "name": "DM Memory",
        "context_window": 32768,
        "description": "Long-term memory augmented conversational model",
        "temperature": 0.3,
    },
    {
        "id": "dm-browser",
        "name": "DM Browser Agent",
        "context_window": 16384,
        "description": "Web browsing and internet research model",
        "temperature": 0.3,
    },
    {
        "id": "dm-research",
        "name": "DM Deep Research",
        "context_window": 32768,
        "description": "Synthesis and deep academic research model",
        "temperature": 0.2,
    },
    {
        "id": "dm-media",
        "name": "DM Media Agent",
        "context_window": 8192,
        "description": "Media generation and visual assets model",
        "temperature": 0.7,
    },
    {
        "id": "dm-facebook",
        "name": "DM Social Content",
        "context_window": 8192,
        "description": "Social media content generation model",
        "temperature": 0.7,
    },
]


def detect_grok_build() -> Dict[str, Any]:
    """
    Detect if official Grok Build CLI or GUI is installed.
    Checks PATH and standard install paths.  Never downloads or installs automatically.
    """
    grok_cli = shutil.which("grok") or shutil.which("grok-build") or shutil.which("grok.exe")
    installed = bool(grok_cli)
    version = "Unknown"

    if installed and grok_cli:
        try:
            res = subprocess.run([grok_cli, "--version"], capture_output=True, text=True, timeout=5)
            if res.returncode == 0:
                version = res.stdout.strip()
        except Exception:
            version = "CLI Detected (version check skipped)"

    # Check for config directory (~/.grok)
    home_grok = Path(os.path.expanduser("~/.grok"))
    config_exists = (home_grok / "config.toml").exists() or (home_grok / "config.json").exists()

    return {
        "installed": installed,
        "cli_path": grok_cli,
        "version": version if installed else "NOT INSTALLED",
        "config_dir": str(home_grok),
        "config_exists": config_exists,
        "status_message": (
            f"DETECTED ({version})" if installed
            else "NOT INSTALLED — Ready for optional native client connection"
        )
    }


def get_grok_config_path() -> Path:
    """Return path to user's ~/.grok/config.toml."""
    home_grok = Path(os.path.expanduser("~/.grok"))
    home_grok.mkdir(parents=True, exist_ok=True)
    return home_grok / "config.toml"


def generate_dm_grok_toml_block(base_url: str = "http://localhost:8000/v1") -> str:
    """Generate the TOML block for registering all 8 DM virtual models in Grok Build."""
    lines = [
        "# ============================================================",
        "# DM AI Operating System — Native Grok Build Models",
        "# Auto-generated configuration for DM AI OS v1.3.0",
        "# ============================================================",
        "",
        "[models]",
        'default = "dm-autonomous-brain"',
        "",
    ]

    for m in DM_VIRTUAL_MODELS:
        mid = m["id"]
        mname = m["name"]
        ctx = m["context_window"]
        temp = m["temperature"]
        lines.extend([
            f"[model.{mid}]",
            f'model = "{mid}"',
            f'name = "{mname}"',
            f'base_url = "{base_url}"',
            'api_backend = "chat_completions"',
            'api_key = "dm-secret-key-v1"',
            f"context_window = {ctx}",
            f"temperature = {temp}",
            "stream_tool_calls = true",
            "",
        ])

    return "\n".join(lines)


def ensure_grok_config(base_url: str = "http://localhost:8000/v1") -> Tuple[bool, str]:
    """
    Safely creates or merges ~/.grok/config.toml.
    Preserves all existing user settings and custom models without overwriting.

    Returns:
      (success: bool, status_message: str)
    """
    config_path = get_grok_config_path()
    block = generate_dm_grok_toml_block(base_url)

    if not config_path.exists():
        try:
            config_path.write_text(block, encoding="utf-8")
            log.info(f"[GrokNative] Created new Grok configuration at {config_path}")
            return True, f"Created new {config_path}"
        except Exception as e:
            log.error(f"[GrokNative] Failed to create config: {e}")
            return False, f"Failed to create config: {e}"

    # File exists — perform safe merge
    try:
        existing_text = config_path.read_text(encoding="utf-8")

        # Check if dm-autonomous-brain is already configured
        if "[model.dm-autonomous-brain]" in existing_text:
            log.info(f"[GrokNative] config.toml at {config_path} already has DM models registered")
            return True, f"Existing configuration verified at {config_path}"

        # Safe append — merge without altering existing sections
        merged_text = existing_text.rstrip() + "\n\n" + block
        config_path.write_text(merged_text, encoding="utf-8")
        log.info(f"[GrokNative] Merged DM models into existing config at {config_path}")
        return True, f"Merged DM models into {config_path}"

    except Exception as e:
        log.error(f"[GrokNative] Failed to merge config: {e}")
        return False, f"Failed to merge config: {e}"


def get_full_grok_status() -> Dict[str, Any]:
    """
    Returns full diagnostic dictionary of Grok Build integration state.
    Used by CLI banner, API health status, and validation tests.
    """
    detection = detect_grok_build()
    cfg_path = get_grok_config_path()
    cfg_ok, cfg_msg = ensure_grok_config()

    return {
        "grok_build_installed": detection["installed"],
        "grok_build_version": detection["version"],
        "grok_cli_path": detection["cli_path"],
        "config_path": str(cfg_path),
        "config_status": cfg_msg,
        "registered_default_model": "dm-autonomous-brain",
        "registered_models_count": len(DM_VIRTUAL_MODELS),
        "models": [m["id"] for m in DM_VIRTUAL_MODELS],
        "api_base_url": "http://localhost:8000/v1",
        "mcp_server_url": "http://localhost:8001",
    }


if __name__ == "__main__":
    status = get_full_grok_status()
    print("\n=== GROK BUILD NATIVE INTEGRATION STATUS ===")
    print(json.dumps(status, indent=2))
