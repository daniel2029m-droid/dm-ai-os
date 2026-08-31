"""
DM AI OS v1.5.2 — Antigravity Persistent Session & Audit Storage
SQLite-backed persistent store for multi-turn sessions, task plans, and audit logs.
"""
import sqlite3
import json
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any

from .models import (
    AntigravitySession,
    PermissionMode,
    SessionStatus,
    AntigravityAction,
    TaskPlan,
    PlanStep,
    OrchestratorAuditEntry,
)

log = logging.getLogger("antigravity_session")

DB_DIR = Path("data")
DB_PATH = DB_DIR / "antigravity_sessions.db"


class AntigravitySessionStore:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # 1. Sessions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    created_at REAL,
                    updated_at REAL,
                    permission_mode TEXT,
                    status TEXT,
                    pending_action TEXT,
                    history_json TEXT
                )
            """)

            # 2. Plans table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS task_plans (
                    plan_id TEXT PRIMARY KEY,
                    session_id TEXT,
                    task_prompt TEXT,
                    steps_json TEXT,
                    current_step_index INTEGER,
                    status TEXT,
                    created_at REAL,
                    updated_at REAL
                )
            """)

            # 3. Audit log table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id TEXT PRIMARY KEY,
                    timestamp REAL,
                    session_id TEXT,
                    task_id TEXT,
                    step_id TEXT,
                    provider TEXT,
                    model TEXT,
                    tool TEXT,
                    action TEXT,
                    permission_mode TEXT,
                    approval_id TEXT,
                    result TEXT,
                    verification TEXT,
                    duration_ms REAL,
                    error TEXT
                )
            """)
            conn.commit()

    def get_or_create_session(
        self,
        session_id: Optional[str] = None,
        permission_mode: Optional[PermissionMode] = None
    ) -> AntigravitySession:
        if not session_id:
            sess = AntigravitySession(
                permission_mode=permission_mode or PermissionMode.READ_ONLY
            )
            self.save_session(sess)
            return sess

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT session_id, created_at, updated_at, permission_mode, status, pending_action, history_json FROM sessions WHERE session_id = ?",
                (session_id,)
            )
            row = cursor.fetchone()
            if not row:
                sess = AntigravitySession(
                    session_id=session_id,
                    permission_mode=permission_mode or PermissionMode.READ_ONLY
                )
                self.save_session(sess)
                return sess

            pending_action = None
            if row[5]:
                try:
                    pending_action = AntigravityAction.model_validate_json(row[5])
                except Exception:
                    pass

            history = []
            if row[6]:
                try:
                    history = json.loads(row[6])
                except Exception:
                    pass

            perm_mode = PermissionMode(row[3]) if row[3] else PermissionMode.READ_ONLY
            if permission_mode:
                perm_mode = permission_mode

            sess = AntigravitySession(
                session_id=row[0],
                created_at=row[1],
                updated_at=row[2],
                permission_mode=perm_mode,
                status=SessionStatus(row[4]) if row[4] else SessionStatus.IDLE,
                pending_action=pending_action,
                history=history
            )
            
            # Load active plan if exists
            plan = self.get_plan_by_session(sess.session_id)
            if plan:
                sess.current_plan = plan

            return sess

    def save_session(self, session: AntigravitySession):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            pending_action_json = session.pending_action.model_dump_json() if session.pending_action else None
            history_json = json.dumps(session.history)
            cursor.execute("""
                INSERT OR REPLACE INTO sessions 
                (session_id, created_at, updated_at, permission_mode, status, pending_action, history_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                session.session_id,
                session.created_at,
                session.updated_at,
                session.permission_mode.value,
                session.status.value,
                pending_action_json,
                history_json
            ))
            conn.commit()

    def save_plan(self, plan: TaskPlan):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            steps_data = [s.model_dump() for s in plan.steps]
            cursor.execute("""
                INSERT OR REPLACE INTO task_plans
                (plan_id, session_id, task_prompt, steps_json, current_step_index, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                plan.plan_id,
                plan.session_id,
                plan.task_prompt,
                json.dumps(steps_data),
                plan.current_step_index,
                plan.status.value,
                plan.created_at,
                plan.updated_at
            ))
            conn.commit()

    def get_plan_by_session(self, session_id: str) -> Optional[TaskPlan]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT plan_id, session_id, task_prompt, steps_json, current_step_index, status, created_at, updated_at
                FROM task_plans WHERE session_id = ? ORDER BY updated_at DESC LIMIT 1
            """, (session_id,))
            row = cursor.fetchone()
            if not row:
                return None
            try:
                steps_raw = json.loads(row[3])
                steps = [PlanStep(**s) for s in steps_raw]
                return TaskPlan(
                    plan_id=row[0],
                    session_id=row[1],
                    task_prompt=row[2],
                    steps=steps,
                    current_step_index=row[4],
                    status=row[5],
                    created_at=row[6],
                    updated_at=row[7]
                )
            except Exception as e:
                log.error(f"Error decoding plan for session {session_id}: {e}")
                return None

    def record_audit(self, entry: OrchestratorAuditEntry):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO audit_log
                (id, timestamp, session_id, task_id, step_id, provider, model, tool, action, permission_mode, approval_id, result, verification, duration_ms, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                entry.id,
                entry.timestamp,
                entry.session_id,
                entry.task_id,
                entry.step_id,
                entry.provider,
                entry.model,
                entry.tool,
                entry.action,
                entry.permission_mode,
                entry.approval_id,
                entry.result,
                entry.verification,
                entry.duration_ms,
                entry.error
            ))
            conn.commit()

    def get_audit_log(self, session_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM audit_log WHERE session_id = ? ORDER BY timestamp DESC LIMIT ?
            """, (session_id, limit))
            rows = cursor.fetchall()
            return [dict(r) for r in rows]


session_store = AntigravitySessionStore()
