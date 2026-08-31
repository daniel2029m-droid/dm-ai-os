"""
DM AI OS v1.5.2 — Real Antigravity Agent Runtime Adapter
"""
import logging
from pathlib import Path
from typing import Dict, Any

from .models import (
    AntigravitySession,
    AntigravityAction,
    AntigravityResponse,
)
from .orchestrator import orchestrator

log = logging.getLogger("antigravity_adapter")


class AntigravityRuntimeAdapter:
    """
    Executes real tasks through AntigravityOrchestrator under strict permission gating.
    """

    async def execute_prompt(
        self,
        prompt: str,
        session: AntigravitySession
    ) -> AntigravityResponse:
        return await orchestrator.route_request(prompt, session)

    async def execute_approved_action(
        self,
        session: AntigravitySession,
        action: AntigravityAction
    ) -> Dict[str, Any]:
        return await orchestrator.execute_approval(
            session_id=session.session_id,
            action_id=action.action_id,
            decision="APPROVE"
        )


antigravity_adapter = AntigravityRuntimeAdapter()
