"""
DM AI OS v1.5.2 — Antigravity Session Store (SQLite / In-Memory with Disk Backup)
"""
import json
import sqlite3
import time
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
from .models import AntigravitySession, SessionStatus, PermissionMode, AntigravityAction

log = logging.getLogger("antigravity_session")

DB_PATH = Path("data/antigravity_sessions.db")

class SessionStore:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._memory_cache: Dict[str, AntigravitySession] = {}
        self._init_db()

    def _init_db(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS antigravity_sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id TEXT,
                    status TEXT,
                    permission_mode TEXT,
                    created_at REAL,
                    updated_at REAL,
                    pending_action TEXT,
                    history TEXT,
                    metadata TEXT
                )
            """)
            conn.commit()

    def get_or_create_session(
        self,
        session_id: Optional[str] = None,
        permission_mode: Optional[PermissionMode] = None,
        user_id: str = "daniel"
    ) -> AntigravitySession:
        if session_id and session_id in self._memory_cache:
            sess = self._memory_cache[session_id]
            if permission_mode:
                sess.permission_mode = permission_mode
            sess.updated_at = time.time()
            return sess

        # Query SQLite
        if session_id:
            with sqlite3.connect(str(self.db_path)) as conn:
                cur = conn.cursor()
                cur.execute("SELECT * FROM antigravity_sessions WHERE session_id = ?", (session_id,))
                row = cur.fetchone()
                if row:
                    sess = AntigravitySession(
                        session_id=row[0],
                        user_id=row[1],
                        status=SessionStatus(row[2]),
                        permission_mode=PermissionMode(row[3]),
                        created_at=row[4],
                        updated_at=row[5],
                        pending_action=AntigravityAction.model_validate_json(row[6]) if row[6] else None,
                        history=json.loads(row[7]),
                        metadata=json.loads(row[8])
                    )
                    if permission_mode:
                        sess.permission_mode = permission_mode
                    self._memory_cache[sess.session_id] = sess
                    return sess

        # Create new
        new_sess = AntigravitySession(
            user_id=user_id,
            permission_mode=permission_mode or PermissionMode.READ_ONLY
        )
        self.save_session(new_sess)
        return new_sess

    def save_session(self, sess: AntigravitySession):
        sess.updated_at = time.time()
        self._memory_cache[sess.session_id] = sess
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO antigravity_sessions 
                (session_id, user_id, status, permission_mode, created_at, updated_at, pending_action, history, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                sess.session_id,
                sess.user_id,
                sess.status.value,
                sess.permission_mode.value,
                sess.created_at,
                sess.updated_at,
                sess.pending_action.model_dump_json() if sess.pending_action else None,
                json.dumps(sess.history),
                json.dumps(sess.metadata)
            ))
            conn.commit()

session_store = SessionStore()
