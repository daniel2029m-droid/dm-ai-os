"""
BrowserAgent - Cognitive Web Browser Automation (Phase 2 Priority #1).
Reuses DOM perception & Playwright engine from agent_bot/agent_browser.py.
Enforces explicit human approval for form submissions, publishing, and destructive actions.

FASE B — Browser Use Integration:
When BROWSER_USE_ENABLED=true and browser-use is installed, search_web() delegates
to BrowserUseAdapter for cognitive multi-step browsing (semantic DOM, session memory).
Fallback to DuckDuckGo HTML if Browser Use is unavailable or disabled.
BrainPipeline, MCP Server, and all callers are unchanged.
"""

import re
import json
import time
import asyncio
import logging
from typing import Dict, Any, List, Optional
from playwright.async_api import async_playwright

from ..core.event_bus import bus
from ..core.plugin_manager import BasePlugin, plugin_manager
from ..providers.capability_selector import capability_selector

log = logging.getLogger("browser_agent")

DESTRUCTIVE_KEYWORDS = ["submit", "publish", "delete", "remove", "buy", "pay", "send", "confirm"]

class BrowserAgent(BasePlugin):
    def __init__(self, session_id: str = "default"):
        self.session_id = session_id
        self.history: List[Dict[str, Any]] = []

    @property
    def plugin_name(self) -> str:
        return "browser"

    @property
    def description(self) -> str:
        return "Cognitive browser automation agent powered by Playwright and local LLM perception."

    async def initialize(self) -> bool:
        log.info("[BrowserAgent] Initialized.")
        return True

    def parse_perception(self, raw_dom_elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter and format DOM elements for LLM perception."""
        parsed = []
        for el in raw_dom_elements:
            role = el.get("role", "element")
            text = el.get("text", "").strip()[:50]
            el_type = el.get("type", "")
            if text or role in ["button", "input", "a"]:
                parsed.append({"role": role, "text": text, "type": el_type})
        return parsed

    def requires_human_approval(self, action: str, target: str) -> bool:
        """Check if action is destructive or involves form submission/publishing."""
        text_check = f"{action} {target}".lower()
        for kw in DESTRUCTIVE_KEYWORDS:
            if kw in text_check:
                return True
        return False

    async def decide_action(self, goal: str, dom_summary: str) -> Dict[str, Any]:
        """Ask Capability Selector (LLM) for next cognitive web action."""
        prompt = (
            f"GOAL: {goal}\n\n"
            f"DOM ELEMENTS: {dom_summary}\n\n"
            f"RECENT HISTORY: {self.history[-3:]}\n\n"
            "Return JSON action: {'action': 'click|type|wait|submit|done|error', 'target': 'text', 'value': 'optional'}"
        )
        
        system_prompt = (
            "You are a Browser Automation Agent. Respond strictly in JSON format. "
            "Prioritize visible text on buttons and input fields."
        )

        res = capability_selector.generate(
            prompt=prompt,
            capability="reasoning",
            system_prompt=system_prompt
        )

        try:
            return json.loads(res)
        except Exception:
            return {"action": "wait", "reason": "Failed to parse LLM JSON", "raw": res}

    async def search_web(self, query: str) -> Dict[str, Any]:
        # ── Step 0: Try BrowserUseAdapter (optional — cognitive search) ─────────
        try:
            from src.adapters.browser_use_adapter import browser_use_adapter
            if browser_use_adapter._is_enabled() and browser_use_adapter._is_available():
                log.info(f"[BrowserAgent] Browser Use enabled — delegating search: '{query}'")
                bu_result = await browser_use_adapter.search(query)
                if bu_result and bu_result.get("results"):
                    return bu_result
                log.warning("[BrowserAgent] Browser Use returned no results, falling back to DuckDuckGo")
        except Exception as e:
            log.warning(f"[BrowserAgent] BrowserUseAdapter failed: {e}. Using DuckDuckGo.")

        # ── Step 1: DuckDuckGo HTML (current behavior — always available) ────
        # Clean search query for DuckDuckGo
        clean_q = re.sub(r'^(investiga|busca|encuentra|dame|muéstrame|cuáles son|qué hay de|novedades de|últimas noticias sobre|noticias sobre)\s*', '', query, flags=re.IGNORECASE).strip()
        clean_q = re.sub(r'^(las|los|sobre|de|el|la)\s*', '', clean_q, flags=re.IGNORECASE).strip()
        clean_q = re.sub(r'^(novedades|noticias|avances)\s+(de\s+|sobre\s+)?', '', clean_q, flags=re.IGNORECASE).strip()
        clean_q = re.sub(r'\s+(de esta semana|esta semana|recientes|de hoy)$', '', clean_q, flags=re.IGNORECASE).strip()
        if not clean_q:
            clean_q = query

        is_news_query = any(w in query.lower() for w in ["novedad", "noticia", "esta semana", "reciente", "última", "hoy", "actualidad"])
        if is_news_query:
            if clean_q.upper() in ["IA", "AI"]:
                search_query = "inteligencia artificial anuncios lanzamientos noticias"
            else:
                search_query = f"{clean_q} inteligencia artificial anuncios lanzamientos noticias"
        else:
            search_query = clean_q

        log.info(f"[BrowserAgent] Performing web search for: '{search_query}' (original: '{query}')")
        try:
            import httpx
            import html
            import urllib.parse
            url = "https://html.duckduckgo.com/html/"
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                resp = await client.post(url, data={"q": search_query, "kl": "es-es"}, headers=headers)
                if resp.status_code == 200:
                    raw_html = resp.text
                    titles = re.findall(
                        r'class=["\']result__title["\'][^>]*>.*?<a[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
                        raw_html, re.DOTALL | re.IGNORECASE
                    )
                    snippets = re.findall(
                        r'class=["\']result__snippet["\'][^>]*>(.*?)</a>',
                        raw_html, re.DOTALL | re.IGNORECASE
                    )
                    
                    generic_portal_patterns = [
                        "todas las noticias sobre",
                        "consulta todas las noticias",
                        "te informamos sobre las",
                        "lee artículos completos",
                        "descubre qué está pasando",
                        "información, novedades y última hora",
                        "manténgase actualizado sobre"
                    ]

                    raw_items = []
                    for i in range(min(len(titles), len(snippets))):
                        href, title_html = titles[i]
                        clean_title = html.unescape(re.sub(r'<[^>]+>', '', title_html)).strip()
                        clean_title = re.sub(r'\s+', ' ', clean_title)
                        
                        if 'uddg=' in href:
                            m = re.search(r'uddg=([^&]+)', href)
                            url_val = urllib.parse.unquote(m.group(1)) if m else href
                        else:
                            url_val = href
                        url_val = html.unescape(url_val)
                        
                        snip_val = html.unescape(re.sub(r'<[^>]+>', '', snippets[i])).strip()
                        snip_val = re.sub(r'\s+', ' ', snip_val)
                        
                        if clean_title and len(snip_val) > 15:
                            is_gen = any(pat in snip_val.lower() for pat in generic_portal_patterns)
                            raw_items.append((clean_title, url_val, snip_val, is_gen))

                    # Prioritize specific news article snippets over generic portal landing pages
                    raw_items.sort(key=lambda x: 1 if x[3] else 0)

                    sources = []
                    clean_snippets = []
                    for clean_title, url_val, snip_val, _ in raw_items[:5]:
                        sources.append(f"{clean_title}: {url_val}")
                        clean_snippets.append(snip_val)

                    if clean_snippets:
                        log.info(f"[BrowserAgent] Search returned {len(clean_snippets)} snippets for '{query}'")
                        return {
                            "status": "success",
                            "query": query,
                            "results": clean_snippets[:5],
                            "sources": sources[:5],
                            "source": "duckduckgo_web"
                        }
                    log.warning(f"[BrowserAgent] Search returned no snippets for '{query}' (HTML parse miss)")
        except Exception as e:
            log.warning(f"[BrowserAgent] Direct HTTP web search failed: {e}")

        # Explicit fallback: cannot reach web — do NOT invent results
        log.warning(f"[BrowserAgent] Web search unavailable for '{query}' — returning no_internet status")
        return {
            "status": "no_internet",
            "query": query,
            "results": [],
            "sources": [],
            "source": "none",
            "error": "No se pudo consultar la web. Verifica la conexión a Internet."
        }

    async def execute_action(self, action_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Plugin entrypoint."""
        goal = payload.get("goal") or payload.get("query") or payload.get("topic") or "Navigate"
        url = payload.get("url")

        log.info(f"[BrowserAgent] Mission: {goal} | Action: {action_name} | URL: {url}")
        
        # Check safety before execution
        if self.requires_human_approval(action_name, goal):
            log.warning(f"[BrowserAgent] Safety Gate Triggered! Action '{action_name}' on '{goal}' requires human approval.")
            return {
                "status": "approval_required",
                "message": f"Action '{action_name}' on '{goal}' requires explicit user confirmation.",
                "payload": payload
            }

        if action_name in ("search", "web_search", "google"):
            return await self.search_web(goal)

        return {"status": "success", "session": self.session_id, "goal": goal, "url": url}

# Register plugin instance
browser_agent_instance = BrowserAgent()
plugin_manager.register_plugin(browser_agent_instance)
