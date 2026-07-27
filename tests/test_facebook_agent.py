"""
Automated Test for Facebook Agent (Phase 2 Priority #4).
Tests strategy & copy generation, hashtag generation, and MANDATORY human approval safety gate on publishing.
"""

import sys
import os
import asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from src.agents.facebook_agent import FacebookAgent

@pytest.mark.asyncio
async def test_facebook_agent():
    agent = FacebookAgent()
    
    # 1. Generate post strategy & copy
    res = await agent.execute_action("create_post", {"topic": "AI Automation Strategies for Small Business"})
    assert res["status"] == "success"
    assert "copy" in res
    assert "hashtags" in res

    # 2. Test publishing safety gate (MUST require human approval)
    pub_res = await agent.execute_action("publish_post", {"post_id": "123", "copy": res["copy"]})
    assert pub_res["status"] == "approval_required"
    assert "requires explicit user confirmation" in pub_res["message"]

    print("[OK] Test Passed: FacebookAgent copy/hashtag generation and MANDATORY publishing safety gate verified.")

if __name__ == "__main__":
    asyncio.run(test_facebook_agent())
