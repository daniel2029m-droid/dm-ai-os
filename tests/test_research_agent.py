"""
Automated Test for Research Agent (Phase 2 Priority #3).
Tests research topic querying, cache hit on repeat research, and report generation.
"""

import sys
import os
import asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from src.agents.research_agent import ResearchAgent

@pytest.mark.asyncio
async def test_research_agent():
    agent = ResearchAgent()
    
    # 1. Execute research task
    res1 = await agent.execute_action("research", {"topic": "AI Operating System Architecture"})
    assert res1["status"] in ["success", "no_internet"]
    assert "report" in res1
    # Source can be: "duckduckgo_web" (real search), "cache" (hit), "no_internet" (offline)
    assert res1["source"] in ["llm", "cache", "duckduckgo_web", "no_internet"]

    # 2. Re-execute same research task to test Cache Layer hit
    res2 = await agent.execute_action("research", {"topic": "AI Operating System Architecture"})
    assert res2["status"] in ["success", "no_internet"]
    assert res2["source"] == "cache"


    print("[OK] Test Passed: ResearchAgent topic research, summary, and CacheLayer hit verified.")

if __name__ == "__main__":
    asyncio.run(test_research_agent())
