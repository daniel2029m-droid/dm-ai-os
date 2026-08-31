from typing import Dict, Any, List, Tuple
from src.providers.base_adapter import BaseProviderAdapter, ProviderCapability, ProviderStatus
from .bridge import antigravity_bridge
from .models import AntigravityChatRequest, PermissionMode


class AntigravityProviderAdapter(BaseProviderAdapter):
    id = "antigravity"
    display_name = "🧠 Antigravity (Local Agent Bridge)"
    capabilities = [ProviderCapability.CHAT]
    is_local = True

    def is_configured(self) -> bool:
        return True

    def get_account_info(self) -> str:
        return "Antigravity Local Engine (Active)"

    async def health_check(self) -> Tuple[ProviderStatus, float, str]:
        st = antigravity_bridge.get_status()
        if st["status"] == "ONLINE":
            return (ProviderStatus.AVAILABLE, 1.0, "Antigravity Bridge Online")
        return (ProviderStatus.UNAVAILABLE, 1.0, "Antigravity Bridge Offline")

    async def get_models(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": "antigravity_readonly",
                "name": "🧠 Antigravity (READ_ONLY: Inspección y Análisis)",
                "free": True,
                "local": True,
                "status": "available"
            },
            {
                "id": "antigravity_approval",
                "name": "🛡️ Antigravity (APPROVAL_REQUIRED: Modificaciones con Aprobación)",
                "free": True,
                "local": True,
                "status": "available"
            },
            {
                "id": "antigravity_autonomous",
                "name": "⚡ Antigravity (AUTONOMOUS: Operación Autónoma Autorizada)",
                "free": True,
                "local": True,
                "status": "available"
            }
        ]

    async def chat(self, messages: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
        prompt = messages[-1].get("content", "") if messages else ""
        model_req = kwargs.get("model", "")
        mode = PermissionMode.READ_ONLY
        if "approval" in str(model_req).lower():
            mode = PermissionMode.APPROVAL_REQUIRED
        elif "autonomous" in str(model_req).lower():
            mode = PermissionMode.AUTONOMOUS

        chat_req = AntigravityChatRequest(
            prompt=prompt,
            session_id=kwargs.get("session_id"),
            permission_mode=mode
        )
        resp = await antigravity_bridge.handle_chat(chat_req)
        
        # Build standard OpenAI format
        content_text = resp.response_text
        if resp.pending_action:
            action = resp.pending_action
            content_text += (
                f"\n\n```json\n"
                f"{{\n"
                f'  "action_id": "{action.action_id}",\n'
                f'  "tool": "{action.tool_name}",\n'
                f'  "target": "{action.target_path}",\n'
                f'  "status": "PENDING_APPROVAL"\n'
                f"}}\n"
                f"```"
            )

        return {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": content_text
                }
            }],
            "session_id": resp.session_id,
            "status": resp.status.value,
            "pending_action": resp.pending_action.model_dump() if resp.pending_action else None,
            "latency_ms": resp.latency_ms,
            "_provider_used": "antigravity"
        }
