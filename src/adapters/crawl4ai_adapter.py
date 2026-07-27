"""
Crawl4AIAdapter — P2 Open Source Integration (Fase A)
======================================================
Wraps Crawl4AI as an optional web crawling backend for ResearchAgent.

Crawl4AI extrae contenido web estructurado limpio (markdown, tablas) optimizado
para LLMs. Elimina publicidad y boilerplate. Hasta 6x mas rapido que BeautifulSoup.

Patron DM AI OS:
- _is_available() verifica instalacion antes de invocar.
- Si no disponible: retorna None y ResearchAgent usa snippets DDG actuales.
- CRAWL4AI_ENABLED=true en .env para activar (opt-in).
- Timeout de 15s por URL. Solo top 3 URLs por consulta.
- Articulos crawleados se cachean via CacheLayer para evitar re-crawling.

NO modifica ningun modulo congelado. ResearchAgent.conduct_research() lo invoca
opcionalmente DESPUES de obtener URLs de BrowserAgent.

Referencia: https://github.com/unclecode/crawl4ai
"""

import os
import asyncio
import logging
from typing import Optional, List, Dict, Any

log = logging.getLogger("crawl4ai_adapter")

# Configuration constants
_DEFAULT_TIMEOUT = 15          # seconds per URL
_DEFAULT_MAX_URLS = 3          # top N URLs to crawl per research query
_DEFAULT_MAX_CONTENT = 8000    # max chars per article (token budget)


class Crawl4AIAdapter:
    """Thin adapter that wraps Crawl4AI as a content extraction backend for research."""

    _ENABLED_ENV = "CRAWL4AI_ENABLED"

    @staticmethod
    def _is_available() -> bool:
        """Check if Crawl4AI library is installed."""
        try:
            import crawl4ai  # noqa: F401
            return True
        except ImportError:
            return False

    @staticmethod
    def _is_enabled() -> bool:
        """Check CRAWL4AI_ENABLED env var (defaults to False — opt-in)."""
        return os.getenv("CRAWL4AI_ENABLED", "false").lower() in ("true", "1", "yes")

    async def crawl_url(
        self,
        url: str,
        timeout: int = _DEFAULT_TIMEOUT,
        max_content: int = _DEFAULT_MAX_CONTENT,
    ) -> Optional[str]:
        """
        Crawl a single URL and return clean markdown content optimized for LLMs.

        Returns:
            str  — Clean markdown text of the article (truncated to max_content).
            None — If Crawl4AI unavailable, disabled, or crawl fails.
                   Caller must fall back to snippet-based context.

        Args:
            url: Target URL to crawl.
            timeout: Max seconds to wait for the crawl (default: 15).
            max_content: Max characters of content to return (default: 8000).
        """
        if not self._is_enabled():
            log.debug("[Crawl4AIAdapter] Disabled (CRAWL4AI_ENABLED != true). Using fallback.")
            return None

        if not self._is_available():
            log.warning(
                "[Crawl4AIAdapter] crawl4ai not installed. "
                "Install with: pip install crawl4ai. Falling back to DDG snippets."
            )
            return None

        try:
            return await self._do_crawl(url, timeout, max_content)
        except asyncio.TimeoutError:
            log.warning(f"[Crawl4AIAdapter] Timeout ({timeout}s) crawling: {url}")
            return None
        except Exception as e:
            log.warning(f"[Crawl4AIAdapter] Crawl failed for '{url}': {e}")
            return None

    async def _do_crawl(self, url: str, timeout: int, max_content: int) -> Optional[str]:
        """Perform the actual Crawl4AI extraction."""
        from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode

        browser_cfg = BrowserConfig(headless=True, verbose=False)
        run_cfg = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,  # We handle caching externally via CacheLayer
            word_count_threshold=10,       # Skip near-empty pages
            excluded_tags=["nav", "footer", "header", "aside", "form", "script", "style"],
            remove_overlay_elements=True,
        )

        async with AsyncWebCrawler(config=browser_cfg) as crawler:
            result = await asyncio.wait_for(
                crawler.arun(url=url, config=run_cfg),
                timeout=timeout
            )

        if not result.success:
            log.warning(f"[Crawl4AIAdapter] Crawl unsuccessful for '{url}': {result.error_message}")
            return None

        content = result.markdown_v2.raw_markdown if result.markdown_v2 else result.markdown
        if not content:
            log.warning(f"[Crawl4AIAdapter] No content extracted from '{url}'")
            return None

        # Truncate to budget
        if len(content) > max_content:
            content = content[:max_content] + "\n[... contenido truncado ...]"

        log.info(f"[Crawl4AIAdapter] Crawled '{url}' -> {len(content)} chars")
        return content

    async def crawl_urls(
        self,
        urls: List[str],
        max_urls: int = _DEFAULT_MAX_URLS,
        timeout: int = _DEFAULT_TIMEOUT,
        max_content: int = _DEFAULT_MAX_CONTENT,
    ) -> Dict[str, Optional[str]]:
        """
        Crawl multiple URLs concurrently and return a url -> content mapping.

        Args:
            urls: List of URLs to crawl.
            max_urls: Maximum number of URLs to process (default: 3).
            timeout: Max seconds per URL.
            max_content: Max characters per article.

        Returns:
            Dict mapping url -> markdown_content (or None if crawl failed).
        """
        if not self._is_enabled() or not self._is_available():
            return {}

        target_urls = urls[:max_urls]
        log.info(f"[Crawl4AIAdapter] Crawling {len(target_urls)} URLs concurrently...")

        tasks = [
            self.crawl_url(url, timeout=timeout, max_content=max_content)
            for url in target_urls
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        output: Dict[str, Optional[str]] = {}
        for url, result in zip(target_urls, results):
            if isinstance(result, Exception):
                log.warning(f"[Crawl4AIAdapter] Exception crawling '{url}': {result}")
                output[url] = None
            else:
                output[url] = result

        successful = sum(1 for v in output.values() if v is not None)
        log.info(f"[Crawl4AIAdapter] Crawl complete: {successful}/{len(target_urls)} successful")
        return output

    def build_enriched_context(
        self,
        web_results: List[str],
        web_sources: List[str],
        crawled_content: Dict[str, Optional[str]],
    ) -> str:
        """
        Build an enriched research context combining DDG snippets with full article content.

        If crawled content is available for a source, uses the full article.
        Falls back to DDG snippet for sources that failed to crawl.

        Args:
            web_results: DDG snippets (current ResearchAgent behavior).
            web_sources: URLs corresponding to web_results.
            crawled_content: url -> content dict from crawl_urls().

        Returns:
            Enriched context string ready for LLM summarization prompt.
        """
        formatted_items = []
        for i in range(min(len(web_results), len(web_sources))):
            url = web_sources[i]
            snippet = web_results[i]
            full_content = crawled_content.get(url)

            if full_content:
                formatted_items.append(
                    f"[Resultado Web {i+1}] — CONTENIDO COMPLETO DEL ARTICULO\n"
                    f"Fuente_URL: {url}\n"
                    f"Texto:\n{full_content}"
                )
            else:
                formatted_items.append(
                    f"[Resultado Web {i+1}] — EXTRACTO DDG\n"
                    f"Fuente_URL: {url}\n"
                    f"Texto: {snippet}"
                )

        return "\n\n---\n\n".join(formatted_items) if formatted_items else ""


# Module-level singleton
crawl4ai_adapter = Crawl4AIAdapter()
