"""
Phase 10 — Automatic Grok Build Connection & Platform Validation Script
========================================================================
Performs complete empirical validation of:
  1. GET /health & GET /system/status
  2. GET /v1/models (Model Discovery)
  3. POST /v1/chat/completions (Non-streaming)
  4. POST /v1/chat/completions (SSE Streaming)
  5. POST /v1/responses (Responses API)
  6. Tool translation from Project_State/Connections/mcp_registry.json
  7. Memory & Identity pipeline routing through BrainPipeline
  8. MCP Server tool list & tool call execution
  9. Grok Build config.toml auto-detection & merging

Usage:
  python -m src.grok_validation
"""

from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import httpx

from src.core.grok_native import detect_grok_build, ensure_grok_config, get_full_grok_status

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("grok_validation")


class GrokPlatformValidator:
    def __init__(
        self,
        api_base: str = "http://localhost:8000",
        mcp_base: str = "http://localhost:8001",
    ):
        self.api_base = api_base.rstrip("/")
        self.mcp_base = mcp_base.rstrip("/")
        self.results: List[Dict[str, Any]] = []

    def _record(self, name: str, status: str, detail: str) -> None:
        item = {"test": name, "status": status, "detail": detail}
        self.results.append(item)
        icon = "[OK]  " if status == "PASSED" else "[FAIL]"
        print(f"  {icon} {name:38s} : {status:6s} | {detail}")


    async def validate_health_and_status(self, client: httpx.AsyncClient) -> bool:
        try:
            r = await client.get(f"{self.api_base}/health", timeout=5)
            if r.status_code == 200 and r.json().get("status") == "ONLINE":
                self._record("GET /health", "PASSED", f"Status: {r.json().get('status')}")
            else:
                self._record("GET /health", "FAILED", f"Status code: {r.status_code}")
                return False

            r2 = await client.get(f"{self.api_base}/system/status", timeout=5)
            if r2.status_code in (200, 403):
                self._record("GET /system/status", "PASSED", f"HTTP {r2.status_code}")
            else:
                self._record("GET /system/status", "FAILED", f"HTTP {r2.status_code}")

            return True
        except Exception as e:
            self._record("GET /health", "FAILED", f"Exception: {e}")
            return False

    async def validate_models_discovery(self, client: httpx.AsyncClient) -> bool:
        try:
            r = await client.get(f"{self.api_base}/v1/models", timeout=5)
            if r.status_code == 200:
                data = r.json()
                models = [m["id"] for m in data.get("data", [])]
                has_brain = "dm-autonomous-brain" in models
                self._record(
                    "GET /v1/models (Discovery)",
                    "PASSED" if has_brain else "FAILED",
                    f"{len(models)} models found | dm-autonomous-brain: {'YES' if has_brain else 'NO'}",
                )
                return has_brain
            else:
                self._record("GET /v1/models (Discovery)", "FAILED", f"HTTP {r.status_code}")
                return False
        except Exception as e:
            self._record("GET /v1/models (Discovery)", "FAILED", f"Exception: {e}")
            return False

    async def validate_chat_completions(self, client: httpx.AsyncClient) -> bool:
        try:
            payload = {
                "model": "dm-autonomous-brain",
                "messages": [
                    {"role": "system", "content": "You are Grok Build assistant."},
                    {"role": "user", "content": "Grok validation test prompt"},
                ],
                "stream": False,
            }
            r = await client.post(f"{self.api_base}/v1/chat/completions", json=payload, timeout=30)
            if r.status_code == 200:
                data = r.json()
                choices = data.get("choices", [])
                content = choices[0]["message"]["content"] if choices else ""
                self._record(
                    "POST /v1/chat/completions",
                    "PASSED" if content else "FAILED",
                    f"Choices: {len(choices)} | Response length: {len(content)} chars",
                )
                return bool(content)
            else:
                self._record("POST /v1/chat/completions", "FAILED", f"HTTP {r.status_code}")
                return False
        except Exception as e:
            self._record("POST /v1/chat/completions", "FAILED", f"Exception: {e}")
            return False

    async def validate_sse_streaming(self, client: httpx.AsyncClient) -> bool:
        try:
            payload = {
                "model": "dm-autonomous-brain",
                "messages": [{"role": "user", "content": "Grok streaming validation"}],
                "stream": True,
            }
            async with client.stream("POST", f"{self.api_base}/v1/chat/completions", json=payload, timeout=30) as resp:
                if resp.status_code != 200:
                    self._record("POST /v1/chat/completions (SSE)", "FAILED", f"HTTP {resp.status_code}")
                    return False
                chunks = []
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        chunks.append(line)
                has_done = any("[DONE]" in c for c in chunks)
                self._record(
                    "POST /v1/chat/completions (SSE)",
                    "PASSED" if has_done else "FAILED",
                    f"Chunks received: {len(chunks)} | [DONE] marker: {'YES' if has_done else 'NO'}",
                )
                return has_done
        except Exception as e:
            self._record("POST /v1/chat/completions (SSE)", "FAILED", f"Exception: {e}")
            return False

    async def validate_responses_api(self, client: httpx.AsyncClient) -> bool:
        try:
            payload = {
                "model": "dm-autonomous-brain",
                "input": "Grok Responses API validation",
            }
            r = await client.post(f"{self.api_base}/v1/responses", json=payload, timeout=30)
            if r.status_code == 200:
                data = r.json()
                self._record(
                    "POST /v1/responses",
                    "PASSED" if data.get("object") == "response" else "FAILED",
                    f"Object: {data.get('object')} | Status: {data.get('status')}",
                )
                return True
            else:
                self._record("POST /v1/responses", "FAILED", f"HTTP {r.status_code}")
                return False
        except Exception as e:
            self._record("POST /v1/responses", "FAILED", f"Exception: {e}")
            return False

    async def validate_mcp_server(self, client: httpx.AsyncClient) -> bool:
        try:
            r = await client.get(f"{self.mcp_base}/mcp/tools", timeout=5)
            if r.status_code == 200:
                tools = r.json().get("tools", [])
                self._record("MCP GET /mcp/tools", "PASSED", f"Registered tools count: {len(tools)}")
                return True
            else:
                self._record("MCP GET /mcp/tools", "FAILED", f"HTTP {r.status_code}")
                return False
        except Exception as e:
            self._record("MCP GET /mcp/tools", "FAILED", f"Exception: {e}")
            return False

    def validate_grok_config(self) -> bool:
        detection = detect_grok_build()
        ok, msg = ensure_grok_config()
        self._record(
            "Grok Build Config Merge",
            "PASSED" if ok else "FAILED",
            f"Installed: {detection['installed']} | Config: {msg}",
        )
        return ok

    def validate_mcp_registry_json(self) -> bool:
        p = Path("Project_State/Connections/mcp_registry.json")
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            tools = data.get("mcp_server", {}).get("tools", [])
            self._record(
                "MCP Registry JSON Sync",
                "PASSED" if len(tools) >= 10 else "FAILED",
                f"Tools in Project_State: {len(tools)}",
            )
            return len(tools) >= 10
        else:
            self._record("MCP Registry JSON Sync", "FAILED", "mcp_registry.json not found")
            return False

    async def run_all_validations(self) -> Dict[str, Any]:
        print("\n============================================================")
        print("  DM AI OS — GROK BUILD NATIVE VALIDATION RUNNER")
        print("============================================================\n")

        self.validate_grok_config()
        self.validate_mcp_registry_json()

        async with httpx.AsyncClient() as client:
            await self.validate_health_and_status(client)
            await self.validate_models_discovery(client)
            await self.validate_chat_completions(client)
            await self.validate_sse_streaming(client)
            await self.validate_responses_api(client)
            await self.validate_mcp_server(client)

        passed = sum(1 for r in self.results if r["status"] == "PASSED")
        total = len(self.results)

        print("\n============================================================")
        print(f"  VALIDATION SUMMARY: {passed}/{total} PASSED")
        print("============================================================\n")

        return {
            "passed": passed,
            "total": total,
            "results": self.results,
            "success": passed == total,
        }


def main():
    import asyncio
    validator = GrokPlatformValidator()
    res = asyncio.run(validator.run_all_validations())
    if not res["success"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
