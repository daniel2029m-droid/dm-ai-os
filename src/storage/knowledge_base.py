"""
KnowledgeLayer - SQLite + Vector Memory for structured project records and semantic retrieval.
"""

import sqlite3
import os
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

log = logging.getLogger("knowledge_base")

class KnowledgeBase:
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
        """Lazy database creation and table initialization."""
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
        """Initialize SQLite schema for structured knowledge persistence."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS semantic_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tags TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS system_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    message TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.commit()

    def save_record(self, category: str, title: str, content: str, tags: List[str] = None) -> int:
        """Store a structured knowledge record into SQLite."""
        self._ensure_db()
        tags_str = ",".join(tags) if tags else ""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO semantic_records (category, title, content, tags) VALUES (?, ?, ?, ?)",
                (category, title, content, tags_str)
            )
            conn.commit()
            log.info(f"[KnowledgeBase] Saved record '{title}' under category '{category}'")
            return cursor.lastrowid

    def search_records(self, query: str, category: str = None) -> List[Dict[str, Any]]:
        """Query structured records matching substring or category."""
        self._ensure_db()
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if category:
                cursor.execute(
                    "SELECT * FROM semantic_records WHERE category = ? AND (title LIKE ? OR content LIKE ?)",
                    (category, f"%{query}%", f"%{query}%")
                )
            else:
                cursor.execute(
                    "SELECT * FROM semantic_records WHERE title LIKE ? OR content LIKE ?",
                    (f"%{query}%", f"%{query}%")
                )
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

# Lazy Singleton
kb = KnowledgeBase()
