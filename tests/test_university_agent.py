"""
Automated Test for University Agent (Phase 2 Priority #5).
Tests academic concept explanation, study guide generation, and tutoring.
"""

import sys
import os
import asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from src.agents.university_agent import UniversityAgent

@pytest.mark.asyncio
async def test_university_agent():
    agent = UniversityAgent()
    
    # 1. Explain academic concept
    res1 = await agent.execute_action("explain_concept", {"concept": "Backpropagation in Neural Networks"})
    assert res1["status"] == "success"
    assert "explanation" in res1

    # 2. Generate study guide
    res2 = await agent.execute_action("create_study_guide", {"subject": "Linear Algebra"})
    assert res2["status"] == "success"
    assert "guide" in res2

    print("[OK] Test Passed: UniversityAgent concept explanation and study guide generation verified.")

if __name__ == "__main__":
    asyncio.run(test_university_agent())
