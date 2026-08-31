"""
DM AI OS v1.5.2 — Antigravity Bridge FastAPI Router
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any

from .models import (
    AntigravityChatRequest,
    AntigravityApprovalRequest,
    AntigravityResponse,
)
from .bridge import antigravity_bridge
from .session import session_store

antigravity_router = APIRouter(prefix="/api/v1/antigravity", tags=["Antigravity Remote Bridge"])

@antigravity_router.get("/status")
async def get_antigravity_status():
    """Returns the operational status of the local Antigravity runtime."""
    return antigravity_bridge.get_status()

@antigravity_router.post("/chat", response_model=AntigravityResponse)
async def antigravity_chat(req: AntigravityChatRequest):
    """Dispatches a chat instruction or code exploration prompt to Antigravity."""
    try:
        return await antigravity_bridge.handle_chat(req)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@antigravity_router.post("/approve")
async def antigravity_approve(req: AntigravityApprovalRequest):
    """Approves a pending mutating action requested by Antigravity."""
    return await antigravity_bridge.handle_approval(req)

@antigravity_router.post("/reject")
async def antigravity_reject(req: AntigravityApprovalRequest):
    """Rejects a pending mutating action."""
    req.decision = "REJECT"
    return await antigravity_bridge.handle_approval(req)

@antigravity_router.get("/session/{session_id}")
async def get_session_state(session_id: str):
    """Retrieves state and history of an active session."""
    sess = session_store.get_or_create_session(session_id=session_id)
    return sess
