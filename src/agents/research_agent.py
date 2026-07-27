"""
ResearchAgent - Information Gathering & Technical Research (Phase 2 Priority #3).
Uses CacheLayer to eliminate duplicate search/LLM calls, StorageLayer for records,
and CapabilityModelSelector for summarization.

FASE 13.2: conduct_research() now invokes BrowserAgent.search_web() for real web
results before falling back to LLM. Never invents information. Explicitly reports
when internet is unavailable.

FASE A — Crawl4AI Integration:
When CRAWL4AI_ENABLED=true and crawl4ai is installed, conduct_research() enriches
the LLM context with full article content instead of short DDG snippets.
Fallback to DDG snippets if Crawl4AI is unavailable or a crawl fails.
The public API and BrainPipeline integration are unchanged.
"""

import asyncio
import logging
from typing import Dict, Any, List

from ..core.plugin_manager import BasePlugin, plugin_manager
from ..storage.storage_layer import storage
from ..providers.capability_selector import capability_selector

log = logging.getLogger("research_agent")

class ResearchAgent(BasePlugin):
    @property
    def plugin_name(self) -> str:
        return "research"

    @property
    def description(self) -> str:
        return "Technical research, document analysis, and topic summarization agent."

    async def initialize(self) -> bool:
        log.info("[ResearchAgent] Initialized.")
        return True

    async def conduct_research(self, topic: str) -> Dict[str, Any]:
        """Perform research on a topic using real web search via BrowserAgent.
        
        Flow:
          1. Check cache (SHA-256 key) to avoid duplicate work.
          2. Invoke BrowserAgent.search_web() for real DuckDuckGo results.
          3. If web results found: summarize with LLM + append sources.
          4. If no internet: respond explicitly without inventing data.
        """
        # ── Step 0: Check cache (bypass for temporal news queries) ───────────
        is_temporal = any(
            kw in topic.lower()
            for kw in ["novedad", "noticia", "esta semana", "reciente", "última", "hoy", "actualidad"]
        )
        cache_key = f"research_{topic.lower()}"
        if not is_temporal:
            cached = storage.get_cache("research", cache_key)
            if cached:
                log.info(f"[ResearchAgent] Cache HIT for topic '{topic}'")
                return {"status": "success", "source": "cache", "report": cached}

        log.info(f"[ResearchAgent] Starting fresh research for '{topic}' (temporal={is_temporal})...")

        # ── Step 1: Real web search via BrowserAgent ──────────────────────────
        web_results: List[str] = []
        web_sources: List[str] = []
        web_status = "no_internet"
        try:
            from ..agents.browser_agent import browser_agent_instance
            log.info(f"[ResearchAgent] Invoking BrowserAgent.search_web('{topic}')")
            search_result = await browser_agent_instance.search_web(topic)
            web_status = search_result.get("status", "no_internet")
            web_results = search_result.get("results", [])
            web_sources = search_result.get("sources", [])
            log.info(
                f"[ResearchAgent] BrowserAgent returned status='{web_status}' "
                f"with {len(web_results)} results"
            )
        except Exception as e:
            log.warning(f"[ResearchAgent] BrowserAgent.search_web() failed: {e}")

        # ── Step 2: No web results → respond honestly, never invent ──────────
        if not web_results:
            report = (
                f"No se pudo consultar la web para investigar: '{topic}'.\n"
                "Verifica la conexión a Internet e intenta nuevamente.\n"
                "DM AI OS no genera información inventada sobre temas de actualidad."
            )
            return {
                "status": "no_internet",
                "source": "none",
                "report": report,
                "sources": [],
            }

        # ── Step 2a: Enrich with Crawl4AI (optional — full article content) ──
        web_context = ""
        try:
            from src.adapters.crawl4ai_adapter import crawl4ai_adapter
            if crawl4ai_adapter._is_enabled() and crawl4ai_adapter._is_available():
                log.info(f"[ResearchAgent] Crawl4AI enabled — crawling top {min(len(web_sources), 3)} URLs...")
                crawled = await crawl4ai_adapter.crawl_urls(web_sources, max_urls=3)
                web_context = crawl4ai_adapter.build_enriched_context(
                    web_results, web_sources, crawled
                )
                log.info(f"[ResearchAgent] Crawl4AI enriched context: {len(web_context)} chars")
        except Exception as e:
            log.warning(f"[ResearchAgent] Crawl4AI enrichment failed: {e}. Using DDG snippets.")

        # ── Step 2b: Fallback to DDG snippets if Crawl4AI not used ─────────
        if not web_context:
            formatted_items = []
            for i in range(min(len(web_results), len(web_sources))):
                formatted_items.append(
                    f"[Resultado Web {i+1}]\n"
                    f"Fuente_URL: {web_sources[i]}\n"
                    f"Texto: {web_results[i]}"
                )
            web_context = "\n\n".join(formatted_items) if formatted_items else "\n\n".join(
                [f"Resultado {i+1}: {r}" for i, r in enumerate(web_results)]
            )

        system_prompt = (
            "Eres un Agente de Investigación (ResearchAgent) técnico y riguroso. Tu función es sintetizar noticias y novedades tecnológicas a partir EXCLUSIVAMENTE de los datos de búsqueda web provistos.\n\n"
            "REGLAS STRICTAS DE CALIDAD Y ANTI-ALUCINACIÓN:\n"
            "1. IDIOMA 100% ESPAÑOL: Toda la respuesta DEBE estar redactada 100% EN ESPAÑOL. Traduce al español cualquier extracto o título que esté en otro idioma (inglés, portugués, etc.). Prohibido incluir palabras en portugués o inglés en la respuesta.\n"
            "2. NOTICIAS REALES Y CONCRETAS: Extrae hechos tecnológicos concretos o anuncios informados en los fragmentos web. NUNCA describas portales web (ej. NO escribas 'Xataka ofrece noticias...').\n"
            "3. ENTIDAD PRINCIPAL ÚNICA POR NOTICIA (REGLA CRÍTICA):\n"
            "   - El campo 'Empresa/organización:' debe contener ÚNICAMENTE la entidad o empresa protagonista del anuncio o hecho.\n"
            "   - NO agregues competidores ni menciones secundarias. NO uses la barra '/' para unir entidades (ej. PROHIBIDO 'Google / OpenAI', 'Microsoft / Google' o 'CES 2026 / RPP Noticias').\n"
            "   - Si la noticia es sobre Google y menciona a OpenAI como competidor, escribe ÚNICAMENTE 'Google'.\n"
            "4. ANTI-ALUCINACIÓN ABSOLUTA (CERO DATOS INVENTADOS):\n"
            "   - Usa ÚNICAMENTE los hechos explícitamente redactados en los extractos web provistos.\n"
            "   - QUEDA ESTRICTAMENTE PROHIBIDO inventar declaraciones, alianzas, cancelaciones, cambios de proveedor, empresas, porcentajes, fechas o impactos no citados en los datos.\n"
            "   - Si un campo (como Impacto o Fecha) NO figura de forma explícita en el texto del fragmento web, DEBES escribir exactamente 'No especificado en la fuente'. NUNCA deduzcas ni inventes un impacto.\n"
            "5. NO USAR MEMORIA DE USUARIO NI CONTEXTO INTERNO: NO utilices datos del contexto personal del usuario, ni proyectos internos (tales como DM AI OS, DMORALESLLC, CapCut, n8n, Ollama, etc.), salvo que aparezcan explícitamente en los resultados web como noticias externas.\n"
            "6. FORMATO RIGUROSO Y COMPLETO PARA CADA NOTICIA:\n"
            "Para CADA noticia encontrada, DEBES redactar los siguientes 7 campos exactos sin omitir ninguno:\n\n"
            "Título: <Título de la noticia en español>\n"
            "Qué ocurrió: <Descripción textual del hecho o anuncio en español>\n"
            "Empresa/organización: <Única entidad o empresa protagonista principal>\n"
            "Fecha: <Fecha exacta indicada o 'No especificada en la fuente'>\n"
            "Impacto: <Impacto citado textualmente en la fuente, o 'No especificado en la fuente'>\n"
            "Fuente: <Nombre del medio>\n"
            "URL: <URL del enlace provisto para esta noticia especificamente>\n\n"
            "7. PROHIBICIÓN ABSOLUTA DE SALUDOS Y TEXTO RESIDUAL:\n"
            "   - NUNCA incluyas saludos ('Hola Daniel', etc.).\n"
            "   - NUNCA incluyas frases de ayuda, conclusiones o recomendaciones al final.\n"
            "   - Inicia DIRECTAMENTE con 'Título:'."
        )

        summary_prompt = (
            f"Consulta de investigación: {topic}\n\n"
            f"DATOS VERIFICADOS OBTENIDOS DE LA BÚSQUEDA WEB:\n{web_context}\n\n"
            "INSTRUCCIÓN: Basándote ÚNICAMENTE en la información de los datos web anteriores, redacta la lista de noticias. Para cada noticia incluye los 7 campos. CADA NOTICIA DEBE TENER UNA SOLA ENTIDAD PRINCIPAL EN 'Empresa/organización:' (PROHIBIDO usar '/', unir empresas o listar competidores). SI UN DATO O IMPACTO NO FIGURA EN EL TEXTO, ESCRIBE 'No especificado en la fuente'."
        )

        report = capability_selector.generate(
            prompt=summary_prompt,
            capability="summarization",
            system_prompt=system_prompt
        )

        # Post-process report to eliminate residual text, internal leaks, trailing conclusions, and multiple entities
        import re
        prohibited_phrases = [
            "¡Hola Daniel Morales!", "Hola Daniel Morales",
            "¡Hola Daniel!", "Hola Daniel",
            "Estoy aquí para ayudarte.", "Estoy aquí para ayudarte",
            "¿Cómo puedo ayudarte?",
            "dm-autonomous-brain", "🔊 Escuchar"
        ]
        for phrase in prohibited_phrases:
            report = report.replace(phrase, "")

        # Post-process Empresa/organización lines to strictly enforce single primary entity
        def _clean_entity_line(match):
            prefix = match.group(1)
            val = match.group(2).strip()
            if "/" in val:
                val = val.split("/")[0].strip()
            return f"{prefix}{val}"

        report = re.sub(r'^(Empresa/organización:\s*)(.+)$', _clean_entity_line, report, flags=re.MULTILINE)

        # Strip trailing conclusions, recommendations or sign-offs
        report = re.sub(r'\n+(Finalmente|En conclusión|Te recomiendo|Esperamos|Para obtener más información|Te recomendamos).*$', '', report, flags=re.DOTALL | re.IGNORECASE)
        report = report.strip()

        if not is_temporal:
            storage.set_cache("research", cache_key, report)
        storage.save_record("research_report", topic[:40], report)

        return {
            "status": "success",
            "source": "duckduckgo_web",
            "report": report,
            "sources": web_sources,
            "results_count": len(web_results),
        }

    async def execute_action(self, action_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if action_name == "research":
            topic = payload.get("topic", "General AI")
            return await self.conduct_research(topic)
        
        return {"status": "error", "message": f"Unknown action '{action_name}'."}

# Register plugin
research_agent_instance = ResearchAgent()
plugin_manager.register_plugin(research_agent_instance)
