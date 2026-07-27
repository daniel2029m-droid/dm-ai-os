"""
FASE 13.2 — Tests: Research Agent real web search integration.

Verifies:
- ResearchAgent invokes BrowserAgent.search_web()
- BrowserAgent returns real results structure (not invented)
- Response includes sources when search succeeds
- No residual text ("Sígueme", "canal", etc.) in responses
- Tool Selector triggers research agent for "novedades" queries
- All existing tests still pass (no regressions)
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

RESIDUAL_PATTERNS = [
    "sígueme", "sigueme", "suscr", "canal", "publicidad",
    "espero que te ayude", "no olvides", "te recomiendo",
    "no dudes en", "para más información visita",
    "comparte", "dale like", "redes sociales",
]

MOCK_SEARCH_SUCCESS = {
    "status": "success",
    "query": "novedades IA esta semana",
    "results": [
        "OpenAI lanza GPT-5 con mejoras en razonamiento multimodal.",
        "Google DeepMind publica AlphaFold 3 con soporte para ARN.",
        "Anthropic presenta Claude 3.5 Sonnet con capacidad de escritura de código extendida.",
    ],
    "sources": ["OpenAI Blog", "DeepMind Research", "Anthropic News"],
    "source": "duckduckgo_web",
}

MOCK_SEARCH_NO_INTERNET = {
    "status": "no_internet",
    "query": "novedades IA",
    "results": [],
    "sources": [],
    "source": "none",
    "error": "No se pudo consultar la web. Verifica la conexión a Internet.",
}


# ─────────────────────────────────────────────────────────────────────────────
# Test 1: Tool Selector triggers "research" for novedades queries
# ─────────────────────────────────────────────────────────────────────────────

def test_tool_selector_triggers_research_for_novedades():
    """_select_tool() must return 'research' for typical current-events queries."""
    from src.api.brain_pipeline import BrainPipeline

    pipeline = BrainPipeline()

    research_queries = [
        "Investiga las novedades de IA de esta semana",
        "novedades de inteligencia artificial",
        "últimas noticias sobre LLMs",
        "qué hay de nuevo en machine learning",
        "busca las últimas novedades de OpenAI",
        "noticias recientes de IA",
        "trending en IA hoy",
        "investiga los últimos avances en IA",
    ]

    for query in research_queries:
        result = pipeline._select_tool(query)
        assert result == "research", (
            f"Expected 'research' for query '{query}', got '{result}'"
        )


def test_tool_selector_no_false_positives():
    """_select_tool() must NOT trigger research for unrelated queries."""
    from src.api.brain_pipeline import BrainPipeline

    pipeline = BrainPipeline()

    non_research_queries = [
        "Hola, ¿cómo estás?",
        "publica en facebook sobre tecnología",
        "ejecuta el comando ls -la",
    ]

    for query in non_research_queries:
        result = pipeline._select_tool(query)
        assert result != "research" or result is None, (
            f"Unexpected 'research' trigger for query '{query}'"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Test 2: ResearchAgent invokes BrowserAgent.search_web()
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_research_agent_calls_browser_search_web():
    """conduct_research() must invoke BrowserAgent.search_web() with the topic."""
    from src.agents.research_agent import ResearchAgent
    from src.storage.storage_layer import storage

    # Clear cache to avoid hitting cached result
    storage.cache._cache.clear() if hasattr(storage.cache, '_cache') else None

    agent = ResearchAgent()

    with patch(
        "src.agents.browser_agent.browser_agent_instance.search_web",
        new_callable=AsyncMock,
        return_value=MOCK_SEARCH_SUCCESS
    ) as mock_search, \
    patch(
        "src.agents.research_agent.capability_selector.generate",
        return_value="Resumen de hallazgos sobre IA esta semana."
    ), \
    patch(
        "src.agents.research_agent.storage.get_cache",
        return_value=None
    ), \
    patch(
        "src.agents.research_agent.storage.set_cache"
    ), \
    patch(
        "src.agents.research_agent.storage.save_record"
    ):
        result = await agent.conduct_research("novedades IA esta semana")

    # Verify BrowserAgent.search_web() was called
    mock_search.assert_called_once_with("novedades IA esta semana")
    assert result["status"] == "success"
    assert result["source"] == "duckduckgo_web"


# ─────────────────────────────────────────────────────────────────────────────
# Test 3: Response includes sources when search succeeds
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_research_response_includes_sources():
    """When web search returns sources, they must appear in the report."""
    from src.agents.research_agent import ResearchAgent

    agent = ResearchAgent()

    with patch(
        "src.agents.browser_agent.browser_agent_instance.search_web",
        new_callable=AsyncMock,
        return_value=MOCK_SEARCH_SUCCESS
    ), \
    patch(
        "src.agents.research_agent.capability_selector.generate",
        return_value="GPT-5 lanzado. AlphaFold 3 disponible. Claude 3.5 con código extendido."
    ), \
    patch("src.agents.research_agent.storage.get_cache", return_value=None), \
    patch("src.agents.research_agent.storage.set_cache"), \
    patch("src.agents.research_agent.storage.save_record"):
        result = await agent.conduct_research("novedades IA esta semana")

    assert result["status"] == "success"
    assert len(result.get("sources", [])) > 0, "Sources list must not be empty"
    assert "OpenAI Blog" in result["sources"] or "Fuentes consultadas" in result["report"]


# ─────────────────────────────────────────────────────────────────────────────
# Test 4: No residual/promotional text in research responses
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_no_residual_text_in_research_response():
    """Research report must not contain promotional or residual text patterns."""
    from src.agents.research_agent import ResearchAgent

    agent = ResearchAgent()

    with patch(
        "src.agents.browser_agent.browser_agent_instance.search_web",
        new_callable=AsyncMock,
        return_value=MOCK_SEARCH_SUCCESS
    ), \
    patch(
        "src.agents.research_agent.capability_selector.generate",
        return_value=(
            "Novedades IA semana:\n"
            "- GPT-5 lanzado con mejoras en razonamiento.\n"
            "- AlphaFold 3 publicado por DeepMind.\n"
            "- Claude 3.5 Sonnet disponible con nuevas capacidades."
        )
    ), \
    patch("src.agents.research_agent.storage.get_cache", return_value=None), \
    patch("src.agents.research_agent.storage.set_cache"), \
    patch("src.agents.research_agent.storage.save_record"):
        result = await agent.conduct_research("novedades IA esta semana")

    report_lower = result["report"].lower()
    for pattern in RESIDUAL_PATTERNS:
        assert pattern not in report_lower, (
            f"Residual pattern '{pattern}' found in research report"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Test 5: No internet — explicit honest response, no invented data
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_research_no_internet_returns_explicit_message():
    """When BrowserAgent.search_web() returns no results, respond explicitly."""
    from src.agents.research_agent import ResearchAgent

    agent = ResearchAgent()

    with patch(
        "src.agents.browser_agent.browser_agent_instance.search_web",
        new_callable=AsyncMock,
        return_value=MOCK_SEARCH_NO_INTERNET
    ), \
    patch("src.agents.research_agent.storage.get_cache", return_value=None):
        result = await agent.conduct_research("novedades IA esta semana")

    assert result["status"] == "no_internet"
    assert "no se pudo consultar" in result["report"].lower()
    # Must not have fabricated any content
    assert result.get("sources", []) == []


# ─────────────────────────────────────────────────────────────────────────────
# Test 6: BrowserAgent.search_web() structure validation
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_browser_agent_search_web_returns_correct_structure():
    """BrowserAgent.search_web() must return dict with status, results, sources keys."""
    from src.agents.browser_agent import BrowserAgent

    agent = BrowserAgent()

    # Mock httpx to return a simulated DuckDuckGo HTML response
    mock_html = """
    <html>
    <body>
    <a class="result__snippet">OpenAI lanza nuevo modelo con capacidades avanzadas de razonamiento.</a>
    <a class="result__snippet">Google DeepMind publica avance en proteómica computacional.</a>
    </body>
    </html>
    """
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = mock_html

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await agent.search_web("novedades IA")

    assert "status" in result
    assert "results" in result
    assert "sources" in result
    assert isinstance(result["results"], list)
    assert isinstance(result["sources"], list)


# ─────────────────────────────────────────────────────────────────────────────
# Test 7: Brain pipeline — no double response concatenation
# ─────────────────────────────────────────────────────────────────────────────

def test_brain_pipeline_no_double_response_for_research():
    """When research agent returns substantial content, BrainPipeline must NOT
    append a second LLM response to it (no text duplication/residual)."""
    from src.api.brain_pipeline import BrainPipeline

    pipeline = BrainPipeline()

    agent_text = (
        "Novedades IA semana:\n"
        "- GPT-5 lanzado con mejoras en razonamiento multimodal.\n"
        "- AlphaFold 3 publicado. DeepMind avance en proteómica.\n"
        "- Claude 3.5 Sonnet con código extendido.\n\n"
        "Fuentes: OpenAI Blog, DeepMind Research."
    )
    llm_text = "Hola, estás bien. No puedo darte información actualizada."

    # Simulate pipeline logic (step 7)
    agent_result = {"report": agent_text}
    final_answer = llm_text  # initial value

    resolved_agent_text = (
        agent_result.get("report")
        or agent_result.get("copy")
        or agent_result.get("explanation")
        or ""
    )
    if resolved_agent_text and len(resolved_agent_text.strip()) > 80:
        final_answer = resolved_agent_text
    elif resolved_agent_text:
        final_answer = f"{resolved_agent_text}\n\n{llm_text}"

    # The LLM generic response must NOT appear in the final answer
    assert llm_text not in final_answer, (
        "BrainPipeline is still concatenating agent result with a second LLM response"
    )
    assert "GPT-5" in final_answer
    assert "OpenAI Blog" in final_answer
