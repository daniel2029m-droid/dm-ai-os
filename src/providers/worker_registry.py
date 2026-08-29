"""
DM AI OS — Persistent Remote Worker Registry
============================================
Manages remote compute workers (e.g. Google Colab Tesla T4, RunPod, Local).
Persists worker state in SQLite so worker registration survives server restarts.

Distinguishes:
  - worker_id: Permanent logical identifier (e.g. "colab-comfy-primary")
  - session_id: Ephemeral Colab runtime session (e.g. "colab-rt-20260828-01")

Worker States:
  - READY: Worker alive, tunnel reachable, ComfyUI /system_stats responsive, GPU verified.
  - DEGRADED: Worker heartbeat active but ComfyUI health probe sluggish or models missing.
  - RECONNECTING: Heartbeat recently lost (< 90s), awaiting handshake or session renewal.
  - OFFLINE: Heartbeat or health probe expired (> 90s), no active endpoint.
"""

import os
import json
import time
import sqlite3
import logging
from enum import Enum
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

log = logging.getLogger("worker_registry")


class WorkerStatus(str, Enum):
    READY = "ready"
    DEGRADED = "degraded"
    RECONNECTING = "reconnecting"
    OFFLINE = "offline"


class T4Compatibility(str, Enum):
    T4_NATIVE = "t4_native"
    T4_WITH_OFFLOAD = "t4_with_offload"
    T4_EXPERIMENTAL = "t4_experimental"
    T4_UNSUPPORTED = "t4_unsupported"


class WorkerRegistry:
    """
    Persistent SQLite-backed registry for remote ComfyUI compute workers.
    """

    def __init__(self, db_path: Optional[str] = None):
        if not db_path:
            db_dir_env = os.getenv("DM_STORAGE_DIR") or os.getenv("DM_DATA_DIR")
            if db_dir_env:
                db_dir = os.path.join(db_dir_env, "Storage")
            elif os.getenv("VERCEL"):
                db_dir = "/tmp/Project_State/Storage"
            else:
                db_dir = os.path.join(
                    os.path.expanduser("~"),
                    ".gemini", "antigravity-ide", "scratch", "Project_State", "Storage"
                )
            db_path = os.path.join(db_dir, "knowledge.db")

        self.db_path = db_path
        self.heartbeat_ttl_sec = float(os.getenv("DM_WORKER_HEARTBEAT_TTL_SEC", "90.0"))
        self.health_probe_ttl_sec = float(os.getenv("DM_WORKER_HEALTH_PROBE_TTL_SEC", "60.0"))
        self._ensure_table()

    def _ensure_table(self):
        """Creates the workers table if it does not exist."""
        try:
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS remote_workers (
                        worker_id TEXT PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        backend TEXT NOT NULL,
                        provider TEXT NOT NULL,
                        endpoint TEXT NOT NULL,
                        tunnel_endpoint TEXT,
                        gpu_name TEXT NOT NULL,
                        vram_gb REAL NOT NULL,
                        comfy_version TEXT,
                        models_json TEXT,
                        custom_nodes_json TEXT,
                        capabilities_json TEXT,
                        registered_at REAL NOT NULL,
                        last_heartbeat REAL NOT NULL,
                        last_health_check REAL NOT NULL,
                        health_status TEXT NOT NULL,
                        status TEXT NOT NULL,
                        error_message TEXT
                    );
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_workers_status ON remote_workers(status);")
                conn.commit()
        except Exception as e:
            log.error(f"[WorkerRegistry] Error initializing SQLite workers table: {e}")

    def register_worker(
        self,
        worker_id: str,
        session_id: str,
        backend: str,
        provider: str,
        endpoint: str,
        gpu_name: str,
        vram_gb: float,
        tunnel_endpoint: Optional[str] = None,
        comfy_version: Optional[str] = None,
        models: Optional[List[str]] = None,
        custom_nodes: Optional[List[str]] = None,
        capabilities: Optional[List[str]] = None,
        health_status: str = "healthy",
        status: str = WorkerStatus.READY.value
    ) -> Dict[str, Any]:
        """
        Registers or updates a worker session idempotently.
        """
        self._ensure_table()
        now = time.time()
        endpoint_clean = endpoint.rstrip("/")
        tunnel_clean = (tunnel_endpoint or endpoint).rstrip("/")

        models_json = json.dumps(models or ["flux2_klein", "sd15_base"], ensure_ascii=False)
        nodes_json = json.dumps(custom_nodes or [], ensure_ascii=False)
        caps_json = json.dumps(capabilities or ["image", "video"], ensure_ascii=False)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO remote_workers (
                    worker_id, session_id, backend, provider, endpoint, tunnel_endpoint,
                    gpu_name, vram_gb, comfy_version, models_json, custom_nodes_json,
                    capabilities_json, registered_at, last_heartbeat, last_health_check,
                    health_status, status, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(worker_id) DO UPDATE SET
                    session_id = excluded.session_id,
                    backend = excluded.backend,
                    provider = excluded.provider,
                    endpoint = excluded.endpoint,
                    tunnel_endpoint = excluded.tunnel_endpoint,
                    gpu_name = excluded.gpu_name,
                    vram_gb = excluded.vram_gb,
                    comfy_version = excluded.comfy_version,
                    models_json = excluded.models_json,
                    custom_nodes_json = excluded.custom_nodes_json,
                    capabilities_json = excluded.capabilities_json,
                    last_heartbeat = excluded.last_heartbeat,
                    last_health_check = excluded.last_health_check,
                    health_status = excluded.health_status,
                    status = excluded.status,
                    error_message = NULL;
            """, (
                worker_id, session_id, backend, provider, endpoint_clean, tunnel_clean,
                gpu_name, vram_gb, comfy_version, models_json, nodes_json,
                caps_json, now, now, now, health_status, status, None
            ))
            conn.commit()

        log.info(f"[WorkerRegistry] Registered worker '{worker_id}' (Session: {session_id}, GPU: {gpu_name} {vram_gb}GB, URL: {endpoint_clean})")
        return self.get_worker(worker_id) or {}

    def record_heartbeat(
        self,
        worker_id: str,
        session_id: Optional[str] = None,
        gpu_utilization_pct: Optional[float] = None,
        vram_used_gb: Optional[float] = None
    ) -> bool:
        """
        Updates last_heartbeat timestamp and keeps worker in READY / RECONNECTING state.
        """
        self._ensure_table()
        now = time.time()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            if session_id:
                cursor.execute("""
                    UPDATE remote_workers
                    SET last_heartbeat = ?,
                        status = CASE WHEN status = 'offline' THEN 'reconnecting' ELSE status END
                    WHERE worker_id = ? AND session_id = ?
                """, (now, worker_id, session_id))
            else:
                cursor.execute("""
                    UPDATE remote_workers
                    SET last_heartbeat = ?,
                        status = CASE WHEN status = 'offline' THEN 'reconnecting' ELSE status END
                    WHERE worker_id = ?
                """, (now, worker_id))
            conn.commit()
            return cursor.rowcount > 0

    def update_health_status(
        self,
        worker_id: str,
        health_status: str,
        status: WorkerStatus,
        error_message: Optional[str] = None
    ) -> bool:
        """Updates health probe outcome and overall status."""
        self._ensure_table()
        now = time.time()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE remote_workers
                SET last_health_check = ?,
                    health_status = ?,
                    status = ?,
                    error_message = ?
                WHERE worker_id = ?
            """, (now, health_status, status.value, error_message, worker_id))
            conn.commit()
            return cursor.rowcount > 0

    def get_worker(self, worker_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a single worker and evaluates its current expiration state."""
        self._ensure_table()
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM remote_workers WHERE worker_id = ?", (worker_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._format_worker_row(row)

    def list_workers(self) -> List[Dict[str, Any]]:
        """Lists all registered workers with evaluated health states."""
        self._ensure_table()
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM remote_workers ORDER BY last_heartbeat DESC")
            rows = cursor.fetchall()
            return [self._format_worker_row(r) for r in rows]

    def get_active_worker(self, capability: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Returns the primary healthy READY worker that matches the requested capability.
        Automatically marks expired workers as OFFLINE.
        """
        workers = self.list_workers()
        for w in workers:
            if w.get("status") == WorkerStatus.READY.value:
                if capability:
                    caps = w.get("capabilities", [])
                    if capability not in caps and "all" not in caps:
                        continue
                return w
        return None

    def _format_worker_row(self, row: sqlite3.Row) -> Dict[str, Any]:
        d = dict(row)
        now = time.time()
        last_hb = d.get("last_heartbeat", 0.0)
        elapsed_hb = now - last_hb

        # Parse JSON fields
        for field in ("models_json", "custom_nodes_json", "capabilities_json"):
            key = field.replace("_json", "")
            raw = d.pop(field, None)
            try:
                d[key] = json.loads(raw) if raw else []
            except Exception:
                d[key] = []

        # Dynamic state evaluation based on Heartbeat TTL
        current_status = d.get("status", WorkerStatus.OFFLINE.value)
        if elapsed_hb > self.heartbeat_ttl_sec:
            if current_status != WorkerStatus.OFFLINE.value:
                d["status"] = WorkerStatus.OFFLINE.value
                # Update in DB
                self._set_status_sync(d["worker_id"], WorkerStatus.OFFLINE.value, "Heartbeat expired")
        elif elapsed_hb > (self.heartbeat_ttl_sec / 2):
            if current_status == WorkerStatus.READY.value:
                d["status"] = WorkerStatus.DEGRADED.value

        d["heartbeat_age_sec"] = round(elapsed_hb, 1)
        return d

    def _set_status_sync(self, worker_id: str, status: str, error: Optional[str] = None):
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "UPDATE remote_workers SET status = ?, error_message = ? WHERE worker_id = ?",
                    (status, error, worker_id)
                )
                conn.commit()
        except Exception:
            pass


# Global singleton
worker_registry = WorkerRegistry()
