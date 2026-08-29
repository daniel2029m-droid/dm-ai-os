"""
ContentMetricsStore — Persistent SQLite storage for content performance telemetry in DM AI OS v1.5.1.
Supports idempotent ingestion, job metrics indexing, channel analytics, and local DLQ resilience.
"""
import sqlite3
import os
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

log = logging.getLogger("content_metrics_store")

class ContentMetricsStore:
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
        self._db_initialized = False

    def _ensure_db(self):
        if self._db_initialized:
            return
        db_dir = os.path.dirname(self.db_path)
        try:
            os.makedirs(db_dir, exist_ok=True)
        except Exception:
            db_dir = "/tmp/Project_State/Storage"
            os.makedirs(db_dir, exist_ok=True)
            self.db_path = os.path.join(db_dir, "knowledge.db")

        self._init_db()
        self._db_initialized = True

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS content_metrics (
                    metric_id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    views INTEGER DEFAULT 0,
                    likes INTEGER DEFAULT 0,
                    shares INTEGER DEFAULT 0,
                    comments INTEGER DEFAULT 0,
                    retention_rate REAL,
                    ctr REAL,
                    performance_score REAL,
                    source TEXT DEFAULT 'manual',
                    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS metrics_dead_letter_queue (
                    dlq_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    error_message TEXT,
                    attempt_count INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_content_metrics_job_id ON content_metrics(job_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_content_metrics_channel ON content_metrics(channel);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_content_metrics_recorded ON content_metrics(recorded_at);")
            conn.commit()

    def record_metric(self, metric_data: Dict[str, Any]) -> Dict[str, Any]:
        """Idempotently records a performance metric entry."""
        self._ensure_db()
        metric_id = metric_data.get("metric_id")
        
        # Check if already exists for idempotency
        existing = self.get_metric(metric_id)
        if existing:
            log.info(f"[ContentMetricsStore] Idempotent hit: metric '{metric_id}' already stored.")
            existing["is_duplicate"] = True
            return existing

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO content_metrics (
                    metric_id, job_id, channel, views, likes, shares, comments,
                    retention_rate, ctr, performance_score, source, recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                metric_id,
                metric_data.get("job_id"),
                metric_data.get("channel"),
                metric_data.get("views", 0),
                metric_data.get("likes", 0),
                metric_data.get("shares", 0),
                metric_data.get("comments", 0),
                metric_data.get("retention_rate"),
                metric_data.get("ctr"),
                metric_data.get("performance_score"),
                metric_data.get("source", "manual"),
                metric_data.get("recorded_at")
            ))
            conn.commit()

        metric_data["is_duplicate"] = False
        return metric_data

    def get_metric(self, metric_id: str) -> Optional[Dict[str, Any]]:
        self._ensure_db()
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM content_metrics WHERE metric_id = ?", (metric_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return dict(row)

    def get_metrics_by_job(self, job_id: str) -> List[Dict[str, Any]]:
        self._ensure_db()
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM content_metrics WHERE job_id = ? ORDER BY recorded_at DESC", (job_id,))
            return [dict(r) for r in cursor.fetchall()]

    def get_metrics_by_channel(self, channel: str, limit: int = 50) -> List[Dict[str, Any]]:
        self._ensure_db()
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM content_metrics WHERE channel = ? ORDER BY recorded_at DESC LIMIT ?",
                (channel, limit)
            )
            return [dict(r) for r in cursor.fetchall()]

    def list_metrics(self, limit: int = 50) -> List[Dict[str, Any]]:
        self._ensure_db()
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM content_metrics ORDER BY recorded_at DESC LIMIT ?", (limit,))
            return [dict(r) for r in cursor.fetchall()]

    def push_dlq(self, payload: Dict[str, Any], error_message: str) -> str:
        """Pushes unprocessable or temporarily failed metric event to Dead Letter Queue."""
        self._ensure_db()
        import uuid
        dlq_id = f"dlq_{uuid.uuid4().hex[:12]}"
        payload_str = json.dumps(payload, ensure_ascii=False)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO metrics_dead_letter_queue (dlq_id, payload_json, error_message)
                VALUES (?, ?, ?)
            """, (dlq_id, payload_str, error_message))
            conn.commit()
        log.warning(f"[ContentMetricsStore] Pushed event to DLQ ({dlq_id}): {error_message}")
        return dlq_id

    def get_dlq_entries(self) -> List[Dict[str, Any]]:
        self._ensure_db()
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM metrics_dead_letter_queue ORDER BY created_at DESC")
            entries = []
            for r in cursor.fetchall():
                d = dict(r)
                try:
                    d["payload"] = json.loads(d.pop("payload_json", "{}"))
                except Exception:
                    d["payload"] = {}
                entries.append(d)
            return entries

# Global singleton
content_metrics_store = ContentMetricsStore()
