"""
Automated Test for Browser Agent (Phase 2 Priority #1).
Tests DOM perception, safety gate confirmation, and action execution.
"""

import sys
import os
import asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from src.agents.browser_agent import BrowserAgent

@pytest.mark.asyncio
async def test_browser_agent_perception_and_safety():
    agent = BrowserAgent(session_id="test_session")
    
    # 1. Verify perception parser
    mock_dom = [
        {"role": "button", "text": "Submit Form", "type": "submit"},
        {"role": "input", "text": "Username", "type": "text"}
    ]
    
    parsed = agent.parse_perception(mock_dom)
    assert len(parsed) == 2
    assert parsed[0]["role"] == "button"

    # 2. Verify safety gate for form submission / destructive actions
    requires_approval = agent.requires_human_approval("submit", "Submit Form")
    assert requires_approval is True

    safe_action = agent.requires_human_approval("click", "View Product")
    assert safe_action is False

    print("[OK] Test Passed: perception parsing & safety approval gate verified.")

if __name__ == "__main__":
    asyncio.run(test_browser_agent_perception_and_safety())
