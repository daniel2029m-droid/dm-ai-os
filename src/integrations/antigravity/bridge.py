"""
DM AI OS v1.5.2 — Antigravity Remote Bridge & Orchestration Router
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
    EngineType,
)
from .session import session_store
from .orchestrator import orchestrator

log = logging.getLogger("antigravity_bridge")


class AntigravityRemoteBridge:
    def __init__(self):
        self._is_online = True

    async def get_status(self) -> Dict[str, Any]:
        health = await orchestrator.get_health_report()
        health["status"] = "ONLINE" if self._is_online else "OFFLINE"
        health["runtime"] = "Google Antigravity Agent Runtime v0.1.15"
        health["default_permission_mode"] = PermissionMode.READ_ONLY.value
        return health

    def set_online(self, online: bool):
        self._is_online = online
        orchestrator.antigravity_provider.is_online = online

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

        prompt_lower = req.prompt.lower()
        # Multi-step task detection
        is_multistep = any(w in prompt_lower for w in [
            "analizá el estado", "analiza el estado", "proponé un plan", "propone un plan",
            "detectá problemas", "detecta problemas", "planificá", "planifica"
        ])

        if is_multistep:
            resp = await orchestrator.plan_and_execute_task(req.prompt, session)
        else:
            engine_pref = req.engine_type or EngineType.AUTO
            resp = await orchestrator.route_request(req.prompt, session, engine_preference=engine_pref)

        # Update session history
        session.history.append({
            "prompt": req.prompt,
            "response": resp.response_text,
            "timestamp": time.time()
        })
        session_store.save_session(session)
        return resp

    async def handle_approval(self, req: AntigravityApprovalRequest) -> Dict[str, Any]:
        return await orchestrator.execute_approval(
            session_id=req.session_id,
            action_id=req.action_id,
            decision=req.decision
        )


antigravity_bridge = AntigravityRemoteBridge()
