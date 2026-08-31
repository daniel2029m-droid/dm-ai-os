"""
DM AI OS v1.5.2 — Antigravity Orchestrator REST Endpoints
"""
import time
import logging
from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException, Depends

from .models import (
    AntigravityChatRequest,
    AntigravityApprovalRequest,
    AntigravityResponse,
    TaskPlan,
    ProviderCapabilities,
)
from .bridge import antigravity_bridge
from .orchestrator import orchestrator
from .session import session_store

log = logging.getLogger("antigravity_routes")

antigravity_router = APIRouter(
    prefix="/api/v1/antigravity",
    tags=["Antigravity Autonomous Multi-Engine Orchestrator"]
)


@antigravity_router.post("/chat", response_model=AntigravityResponse)
async def antigravity_chat(req: AntigravityChatRequest):
    """
    Main conversational & task execution endpoint.
    Routes to real google.antigravity.Agent runtime under strict permission gates.
    """
    return await antigravity_bridge.handle_chat(req)


@antigravity_router.post("/orchestrate", response_model=AntigravityResponse)
async def antigravity_orchestrate(req: AntigravityChatRequest):
    """
    Explicit multi-step task planning and autonomous execution.
    """
    session = session_store.get_or_create_session(
        session_id=req.session_id,
        permission_mode=req.permission_mode
    )
    return await orchestrator.plan_and_execute_task(req.prompt, session)


@antigravity_router.get("/plan/{session_id}")
async def get_session_plan(session_id: str):
    """
    Returns the active multi-step plan for a session.
    """
    plan = session_store.get_plan_by_session(session_id)
    if not plan:
        raise HTTPException(status_code=404, detail="No task plan found for this session.")
    return plan


@antigravity_router.get("/audit/{session_id}")
async def get_session_audit_log(session_id: str, limit: int = 50):
    """
    Returns audit log entries for reconstructed task execution telemetry.
    """
    return session_store.get_audit_log(session_id=session_id, limit=limit)


@antigravity_router.get("/health")
async def get_orchestrator_health():
    """
    Independent component health checks (SDK, Harness, Ollama, MCP, Workspace).
    """
    return await orchestrator.get_health_report()


@antigravity_router.get("/capabilities", response_model=ProviderCapabilities)
async def get_capabilities():
    """
    Returns verified real-time capabilities of the agent runtime.
    """
    return await orchestrator.antigravity_provider.capabilities()


@antigravity_router.post("/approve")
async def approve_action(req: AntigravityApprovalRequest):
    """
    Approves a pending mutating action and executes it with physical verification.
    """
    return await antigravity_bridge.handle_approval(req)


@antigravity_router.post("/reject")
async def reject_action(req: AntigravityApprovalRequest):
    """
    Rejects a pending mutating action, leaving the workspace intact.
    """
    req.decision = "REJECT"
    return await antigravity_bridge.handle_approval(req)


@antigravity_router.get("/status")
async def get_status():
    """
    Returns operational status of the Antigravity Remote Bridge.
    """
    return await antigravity_bridge.get_status()


@antigravity_router.get("/session/{session_id}")
async def get_session(session_id: str):
    """
    Retrieves full session history and current state.
    """
    sess = session_store.get_or_create_session(session_id=session_id)
    return sess
