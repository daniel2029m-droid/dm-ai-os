"""
DM AI OS — Provider Usage History
===================================
Records every AI provider call: provider, model, account, cost, result.
Stored in SQLite via the existing storage layer (no new DB).
"""

import json
import time
import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("provider_history")

_DB_PATH = Path(__file__).parent.parent.parent / "logs" / "provider_history.db"


class ProviderHistory:
    """Lightweight history log for provider usage."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or _DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS provider_history (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts          REAL    NOT NULL,
                    provider    TEXT    NOT NULL,
                    model       TEXT,
                    account     TEXT,
                    capability  TEXT,
                    prompt      TEXT,
                    result_url  TEXT,
                    cost_cents  REAL,
                    duration_ms REAL,
                    status      TEXT,
                    error       TEXT
                )
            """)
            conn.commit()

    def record(
        self,
        provider: str,
        capability: str,
        prompt: str,
        *,
        model: str = None,
        account: str = None,
        result_url: str = None,
        cost_cents: float = None,
        duration_ms: float = None,
        status: str = "ok",
        error: str = None,
    ):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO provider_history
                   (ts, provider, model, account, capability, prompt, result_url, cost_cents, duration_ms, status, error)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (time.time(), provider, model, account, capability,
                 prompt[:500] if prompt else None,
                 result_url, cost_cents, duration_ms, status, error)
            )
            conn.commit()

    def get_recent(self, limit: int = 50) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM provider_history ORDER BY ts DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_by_provider(self, provider: str, limit: int = 20) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM provider_history WHERE provider=? ORDER BY ts DESC LIMIT ?",
                (provider, limit)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_stats(self) -> Dict[str, Any]:
        with sqlite3.connect(self.db_path) as conn:
            total = conn.execute("SELECT COUNT(*) FROM provider_history").fetchone()[0]
            by_provider = conn.execute(
                "SELECT provider, COUNT(*) as calls FROM provider_history GROUP BY provider"
            ).fetchall()
            total_cost = conn.execute(
                "SELECT SUM(cost_cents) FROM provider_history WHERE cost_cents IS NOT NULL"
            ).fetchone()[0]
        return {
            "total_calls": total,
            "by_provider": {row[0]: row[1] for row in by_provider},
            "total_cost_cents": total_cost or 0,
        }


# Module-level singleton
provider_history = ProviderHistory()
