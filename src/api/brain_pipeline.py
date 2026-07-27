"""
Brain Pipeline — Central orchestrator for every request entering the DM AI Platform.

Flow for every incoming request (from any client: Grok Build, Open WebUI, LibreChat, Cursor, etc.):

  1. IdentityManager   → identify user and load profile
  2. MemoryRetriever   → fetch relevant long-term memories
  3. ContextBuilder    → inject identity + memories into prompt
  4. ToolSelector      → decide which agents/tools to use
  5. AgentOrchestrator → invoke agents via TaskDAG / PluginManager
  6. PromptBuilder     → build final enriched prompt for Ollama
  7. LLM (Ollama)      → generate response (LLM is just one more component)
  8. CacheLayer        → store result to avoid repeated LLM calls
  9. MemoryWriter      → persist conversation to long-term memory

The LLM is NOT the brain. The BrainPipeline IS the brain.
"""

import hashlib
import logging
import time
from typing import Dict, Any, List, Optional

from src.memory.memory_manager import memory_manager
from src.core.plugin_manager import plugin_manager
from src.providers.capability_selector import capability_selector
from src.storage.storage_layer import storage

import src.agents.research_agent  # noqa: ensure agents are registered
import src.agents.computer_agent
import src.agents.facebook_agent
import src.agents.university_agent
import src.agents.media_agent
import src.agents.browser_agent

log = logging.getLogger("brain_pipeline")

# Keywords that trigger agent routing instead of direct LLM response
AGENT_TRIGGERS: Dict[str, List[str]] = {
    "research":    [
        "busca", "investiga", "research", "encuentra", "buscar",
        "novedades", "noticias", "news", "últimas", "recientes",
        "esta semana", "trending", "qué hay de nuevo", "actualidad",
        "hoy en", "últimos avances", "reciente", "novedad",
    ],
    "facebook":    ["facebook", "publica", "post", "hashtag", "publicar"],
    "computer":    ["ejecuta", "run", "comando", "system", "info del sistema"],
    "university":  ["explica", "explain", "concepto", "estudia", "study guide"],
    "media":       ["imagen", "image", "video", "genera imagen", "generate image"],
    "browser":     ["navega", "abre", "website", "url", "browser"],
}


class BrainPipeline:
    def __init__(self):
        self.cache = storage.cache

    # ── Step 1: Cache lookup ──────────────────────────────────────────────────
    def _cache_key(self, user_id: str, prompt: str) -> str:
        raw = f"{user_id}::{prompt}"
        return "brain_" + hashlib.sha256(raw.encode()).hexdigest()[:16]

    # ── Step 2: Tool / Agent selection ───────────────────────────────────────
    def _select_tool(self, prompt: str) -> Optional[str]:
        lowered = prompt.lower()
        for agent, keywords in AGENT_TRIGGERS.items():
            if any(kw in lowered for kw in keywords):
                return agent
        return None

    # ── Step 3: Prompt enrichment ─────────────────────────────────────────────
    def _build_enriched_prompt(self, user_id: str, user_prompt: str, system_identity_override: Optional[str] = None) -> str:
        context = memory_manager.summarize_context(user_id=user_id, query=user_prompt)
        system_identity = system_identity_override or (
            "Soy DM AI OS.\n"
            "Mi núcleo cognitivo es BrainPipeline.\n"
            "Grok Build es únicamente un cliente externo.\n"
            "Opero mediante memoria, herramientas MCP y agentes autónomos.\n"
            "No eres Grok ni xAI.\n"
            "No digas que eres asistente cognitivo, interfaz, producto ni plataforma.\n"
            "No digas que estás diseñado para ayudarte, ni use frases genéricas de asistente."
        )
        return (
            f"[SYSTEM DIRECTIVE — ABSOLUTE MANDATORY IDENTITY]\n"
            f"{system_identity}\n\n"
            f"[DM AI Platform — System Context]\n"
            f"{context}\n\n"
            f"[User Request]\n"
            f"{user_prompt}"
        )

    # ── Main Pipeline Entry Point ─────────────────────────────────────────────
    async def process(
        self,
        user_prompt: str,
        user_id: str = "daniel",
        system_prompt_override: Optional[str] = None,
        images: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        t0 = time.perf_counter()
        cache_key_data = f"{user_id}:{user_prompt}:{len(images or [])}"

        # 1. Cache check — avoid repeated LLM calls (bypass for temporal news queries)
        is_temporal = any(
            kw in user_prompt.lower()
            for kw in ["novedad", "noticia", "esta semana", "reciente", "última", "hoy", "actualidad"]
        )
        if not is_temporal:
            cached = self.cache.get("brain", cache_key_data)
            if cached:
                log.info(f"[BrainPipeline] Cache HIT for prompt '{user_prompt[:40]}...'")
                cached["source"] = "cache"
                return cached

        # 2. Identify user + load profile
        profile = memory_manager.get_user_profile(user_id=user_id)
        log.info(f"[IDENTITY] Resolved user_id='{user_id}' | profile_name='{profile.get('name', 'User')}'")

        # 3. Retrieve relevant long-term memories
        memories = memory_manager.retrieve_memory(user_prompt, top_k=3)
        memory_snippets = [m["content"] for m in memories]
        log.info(f"[MEMORY] Query='{user_prompt[:40]}' | Retrieved {len(memory_snippets)} memories | Snippets={memory_snippets[:2]}")

        # 4. Tool Selector — route to agent if triggered, else go to LLM
        selected_agent = self._select_tool(user_prompt)
        log.info(f"[TOOLS] ToolSelector decision: agent_selected='{selected_agent or 'none (direct LLM)'}'")
        agent_result: Optional[Dict[str, Any]] = None

        if selected_agent:
            await plugin_manager.initialize_all()
            log.info(f"[BrainPipeline] Invoking agent: '{selected_agent}' for prompt")
            action_map = {
                "research": ("research", {"topic": user_prompt}),
                "facebook": ("create_post", {"topic": user_prompt}),
                "computer": ("sys_info", {}),
                "university": ("explain_concept", {"concept": user_prompt}),
                "media": ("generate_image", {"prompt": user_prompt}),
                "browser": ("navigate", {"goal": user_prompt, "url": "https://www.google.com"}),
            }
            action, payload = action_map.get(selected_agent, ("research", {"topic": user_prompt}))
            agent_result = await plugin_manager.invoke(selected_agent, action, payload)

        agent_text = ""
        if agent_result:
            agent_text = (
                agent_result.get("report")
                or agent_result.get("copy")
                or agent_result.get("explanation")
                or ""
            ).strip()

        if agent_text:
            log.info(f"[BrainPipeline] Using agent response directly (len={len(agent_text)}) | Skipping secondary LLM call")
            final_answer = agent_text
            target_model = f"agent:{selected_agent}"
        else:
            # 5. Build enriched prompt for LLM (System Identity has MAXIMUM priority)
            system_identity = system_prompt_override or (
                "Soy DM AI OS.\n"
                "Mi núcleo cognitivo es BrainPipeline.\n"
                "Grok Build es únicamente un cliente externo.\n"
                "Opero mediante memoria, herramientas MCP y agentes autónomos.\n"
                "No eres Grok ni xAI.\n"
                "No digas que eres asistente cognitivo, interfaz, producto ni plataforma.\n"
                "No digas que estás diseñado para ayudarte, ni use frases genéricas de asistente."
            )
            enriched_prompt = self._build_enriched_prompt(user_id, user_prompt, system_identity_override=system_identity)

            # 6. LLM (Ollama) — generates the final answer (it's just a component)
            req_capability = "vision" if images else "reasoning"
            target_model = capability_selector.select_model_for_capability(req_capability)
            log.info(f"[LLM] Model selected='{target_model}' for capability='{req_capability}' | Generating response...")
            final_answer = capability_selector.generate(
                prompt=enriched_prompt,
                capability=req_capability,
                system_prompt=system_identity,
                images=images
            )

        # 8. Clean any residual conversational greetings or closing questions
        import re
        final_answer = re.sub(
            r'¡?hola,?\s*daniel!?\s*(estoy aquí para ayudarte.*|¿cómo puedo ayudarte.*?\?)?',
            '',
            final_answer,
            flags=re.IGNORECASE
        ).strip()
        final_answer = re.sub(
            r'¿?cómo puedo ayudarte.*?\??$',
            '',
            final_answer,
            flags=re.IGNORECASE
        ).strip()

        # Guarantee answer is non-empty
        if not final_answer or not final_answer.strip():
            final_answer = "Soy DM AI OS, sistema autónomo conectado correctamente."

        elapsed = round(time.perf_counter() - t0, 3)

        result = {
            "answer": final_answer,
            "user_id": user_id,
            "profile_name": profile.get("name", "User"),
            "memories_used": len(memory_snippets),
            "agent_used": selected_agent,
            "llm_model": target_model,
            "execution_time_sec": elapsed,
            "source": "live",
        }

        # 8. Store to cache
        self.cache.set("brain", cache_key_data, result)
        log.info(f"[BrainPipeline] Processed in {elapsed}s | agent={selected_agent} | memories={len(memory_snippets)}")

        # 9. Persist conversation to memory
        memory_manager.short_term.add_message("user", user_prompt)
        memory_manager.short_term.add_message("assistant", final_answer)

        return result


brain_pipeline = BrainPipeline()
