"""
BrowserUseAdapter — P1 Open Source Integration (Fase B)
========================================================
Wraps browser-use (https://github.com/browser-use/browser-use) as an optional
cognitive browsing backend for BrowserAgent.

browser-use permite que LLMs naveguen la web autonomamente usando Playwright con:
- Percepcion semantica del DOM (sin regex fragil)
- Razonamiento y memoria de sesion
- Navegacion multi-step (formularios, flujos, login)
- Compatible con Ollama /v1/chat/completions

Patron DM AI OS:
- _is_available() verifica instalacion antes de invocar.
- Si no disponible: retorna None y BrowserAgent usa DuckDuckGo HTML actual.
- BROWSER_USE_ENABLED=true en .env para activar (opt-in).
- BrainPipeline NO cambia: sigue invocando plugin_manager.invoke("browser", ...).

Flujo:
  BrainPipeline.process()
    -> plugin_manager.invoke("browser", "search", payload)
         -> BrowserAgent.search_web()
              -> [SI browser-use disponible] BrowserUseAdapter.search()
              -> [FALLBACK]                  DuckDuckGo HTML actual

NO modifica BrainPipeline, PluginManager, MCP Server ni ninguna capa congelada.
"""

import os
import asyncio
import logging
from typing import Optional, Dict, Any, List

log = logging.getLogger("browser_use_adapter")

# Max results to extract per search
_DEFAULT_MAX_RESULTS = 5
# Timeout for a complete browser-use task
_DEFAULT_TASK_TIMEOUT = 45  # seconds


class BrowserUseAdapter:
    """
    Thin adapter that wraps browser-use as a cognitive browsing backend.

    When BROWSER_USE_ENABLED=true and browser-use is installed, BrowserAgent
    can delegate search and multi-step navigation to this adapter.
    """

    _ENABLED_ENV = "BROWSER_USE_ENABLED"

    @staticmethod
    def _is_available() -> bool:
        """Check if browser-use library is installed."""
        try:
            import browser_use  # noqa: F401
            return True
        except ImportError:
            return False

    @staticmethod
    def _is_enabled() -> bool:
        """Check BROWSER_USE_ENABLED env var (defaults to False — opt-in)."""
        return os.getenv("BROWSER_USE_ENABLED", "false").lower() in ("true", "1", "yes")

    def _get_llm(self):
        """
        Build an LLM client compatible with browser-use.

        Priority:
          1. Ollama local (OLLAMA_BASE_URL or default http://localhost:11434)
          2. OpenAI-compatible endpoint via OPENAI_API_BASE + OPENAI_API_KEY
        """
        ollama_base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        model = os.getenv("BROWSER_USE_MODEL", "qwen2.5:7b")

        try:
            # browser-use uses langchain-style LLM objects
            from langchain_openai import ChatOpenAI
            llm = ChatOpenAI(
                model=model,
                base_url=f"{ollama_base}/v1",
                api_key="ollama",  # Ollama does not validate API key
                temperature=0.0,
            )
            log.debug(f"[BrowserUseAdapter] LLM: Ollama {model} at {ollama_base}")
            return llm
        except ImportError:
            log.warning("[BrowserUseAdapter] langchain_openai not found. Install: pip install langchain-openai")
            return None

    async def search(
        self,
        query: str,
        max_results: int = _DEFAULT_MAX_RESULTS,
        timeout: int = _DEFAULT_TASK_TIMEOUT,
    ) -> Optional[Dict[str, Any]]:
        """
        Perform a cognitive web search using browser-use.

        Returns a dict matching BrowserAgent.search_web() output format:
            {
                "status": "success",
                "query": str,
                "results": [str, ...],   # text snippets or article summaries
                "sources": [str, ...],   # "Title: URL" strings
                "source": "browser_use"
            }
        Returns None if adapter is disabled, unavailable, or search fails.
        BrowserAgent MUST fall back to DuckDuckGo when None is returned.
        """
        if not self._is_enabled():
            log.debug("[BrowserUseAdapter] Disabled (BROWSER_USE_ENABLED != true).")
            return None

        if not self._is_available():
            log.warning(
                "[BrowserUseAdapter] browser-use not installed. "
                "Install: pip install browser-use. Falling back to DuckDuckGo."
            )
            return None

        llm = self._get_llm()
        if llm is None:
            return None

        try:
            return await asyncio.wait_for(
                self._do_search(query, llm, max_results),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            log.warning(f"[BrowserUseAdapter] Search timeout ({timeout}s) for: '{query}'")
            return None
        except Exception as e:
            log.warning(f"[BrowserUseAdapter] Search failed for '{query}': {e}")
            return None

    async def _do_search(self, query: str, llm, max_results: int) -> Optional[Dict[str, Any]]:
        """Perform the actual browser-use search task."""
        from browser_use import Agent

        task = (
            f"Search DuckDuckGo for: {query}\n"
            f"Extract the top {max_results} results. For each result provide:\n"
            f"1. Title\n"
            f"2. URL\n"
            f"3. A 2-3 sentence summary of the content\n"
            f"Return results as a numbered list in this format:\n"
            f"[N]. Title: <title> | URL: <url> | Summary: <summary>"
        )

        agent = Agent(task=task, llm=llm)
        result = await agent.run()

        # Parse agent output
        return self._parse_agent_output(result, query)

    def _parse_agent_output(self, result, query: str) -> Optional[Dict[str, Any]]:
        """Parse browser-use Agent output into BrowserAgent-compatible format."""
        try:
            # Get final result text
            if hasattr(result, "final_result"):
                text = result.final_result() or ""
            elif hasattr(result, "history") and result.history:
                # Extract from last action result
                text = str(result.history[-1]) if result.history else ""
            else:
                text = str(result)

            if not text:
                return None

            sources = []
            results = []

            import re
            # Parse numbered results: [N]. Title: ... | URL: ... | Summary: ...
            pattern = r'\[?\d+\]?\.\s+Title:\s*(.+?)\s*\|\s*URL:\s*(\S+)\s*\|\s*Summary:\s*(.+?)(?=\[?\d+\]?\.|$)'
            matches = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)

            for title, url, summary in matches:
                title = title.strip()
                url = url.strip()
                summary = summary.strip().replace('\n', ' ')
                sources.append(f"{title}: {url}")
                results.append(summary)

            # Fallback: if no structured results, use raw text as single result
            if not results and len(text) > 20:
                results = [text[:1000]]
                sources = [f"{query}: https://duckduckgo.com/?q={query.replace(' ', '+')}"]

            if results:
                log.info(
                    f"[BrowserUseAdapter] Search '{query}' -> "
                    f"{len(results)} results via browser-use"
                )
                return {
                    "status": "success",
                    "query": query,
                    "results": results[:5],
                    "sources": sources[:5],
                    "source": "browser_use",
                }

        except Exception as e:
            log.warning(f"[BrowserUseAdapter] Failed to parse agent output: {e}")

        return None

    async def navigate(
        self,
        goal: str,
        url: Optional[str] = None,
        timeout: int = _DEFAULT_TASK_TIMEOUT,
    ) -> Optional[Dict[str, Any]]:
        """
        Execute a multi-step navigation task using browser-use.

        Unlike search(), this supports complex flows: login, form submission,
        content extraction from specific pages, etc.

        Returns:
            {"status": "success", "result": str, "source": "browser_use"}
            or None if unavailable/disabled/failed.
        """
        if not self._is_enabled() or not self._is_available():
            return None

        llm = self._get_llm()
        if llm is None:
            return None

        task = goal
        if url:
            task = f"Navigate to {url} and then: {goal}"

        try:
            from browser_use import Agent
            agent = Agent(task=task, llm=llm)
            result = await asyncio.wait_for(agent.run(), timeout=timeout)

            final = ""
            if hasattr(result, "final_result"):
                final = result.final_result() or str(result)
            else:
                final = str(result)

            log.info(f"[BrowserUseAdapter] Navigation task completed: '{goal[:60]}'")
            return {
                "status": "success",
                "goal": goal,
                "result": final,
                "source": "browser_use",
            }
        except asyncio.TimeoutError:
            log.warning(f"[BrowserUseAdapter] Navigation timeout ({timeout}s): '{goal[:60]}'")
            return None
        except Exception as e:
            log.warning(f"[BrowserUseAdapter] Navigation failed: {e}")
            return None


# Module-level singleton
browser_use_adapter = BrowserUseAdapter()
