"""
DM AI OS v1.5.2 — Antigravity Remote Bridge Orchestrator
"""
import time
import logging
from typing import Dict, Any, Optional

from .models import (
    AntigravityChatRequest,
    AntigravityApprovalRequest,
    AntigravityResponse,
    SessionStatus,
    PermissionMode,
)
from .session import session_store
from .adapter import antigravity_adapter

log = logging.getLogger("antigravity_bridge")

class AntigravityRemoteBridge:
    def __init__(self):
        self._is_online = True

    def get_status(self) -> Dict[str, Any]:
        return {
            "status": "ONLINE" if self._is_online else "OFFLINE",
            "runtime": "Google Antigravity Agent Runtime v0.1.15",
            "default_permission_mode": PermissionMode.READ_ONLY.value,
            "active_sessions_count": len(session_store._memory_cache),
            "timestamp": time.time()
        }

    def set_online(self, online: bool):
        self._is_online = online

    async def handle_chat(self, req: AntigravityChatRequest) -> AntigravityResponse:
        if not self._is_online:
            return AntigravityResponse(
                session_id=req.session_id or "default",
                status=SessionStatus.OFFLINE,
                permission_mode=req.permission_mode or PermissionMode.READ_ONLY,
                response_text="🟡 Antigravity OFFLINE. El runtime de agente local no está disponible."
            )

        session = session_store.get_or_create_session(
            session_id=req.session_id,
            permission_mode=req.permission_mode
        )

        resp = await antigravity_adapter.execute_prompt(req.prompt, session)
        
        # Update session history
        session.history.append({
            "prompt": req.prompt,
            "response": resp.response_text,
            "timestamp": time.time()
        })
        session_store.save_session(session)
        return resp

    async def handle_approval(self, req: AntigravityApprovalRequest) -> Dict[str, Any]:
        session = session_store.get_or_create_session(session_id=req.session_id)
        if not session.pending_action or session.pending_action.action_id != req.action_id:
            return {
                "status": "ERROR",
                "message": "No se encontró ninguna acción pendiente que coincida con el action_id."
            }

        if req.decision.upper() == "APPROVE":
            result = await antigravity_adapter.execute_approved_action(session, session.pending_action)
            session_store.save_session(session)
            return result
        else:
            action = session.pending_action
            action.status = "REJECTED"
            session.status = SessionStatus.COMPLETED
            session.pending_action = None
            session_store.save_session(session)
            return {
                "status": "REJECTED",
                "action_id": req.action_id,
                "message": "Acción cancelada por el usuario."
            }

antigravity_bridge = AntigravityRemoteBridge()
