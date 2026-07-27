"""
Automated Test for Computer Agent (Phase 2 Priority #2).
Tests OS environment diagnostics, command safety checks, and plugin execution.
"""

import sys
import os
import asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from src.agents.computer_agent import ComputerAgent

@pytest.mark.asyncio
async def test_computer_agent_safety_and_exec():
    agent = ComputerAgent()
    
    # 1. Check system info retrieval
    sys_info = agent.get_system_info()
    assert sys_info["os"] == "Windows"
    assert "cpu_count" in sys_info

    # 2. Check safety approval gate for destructive commands
    assert agent.requires_human_approval("rmdir /s /q C:\\Important") is True
    assert agent.requires_human_approval("del /f /q C:\\file.txt") is True
    assert agent.requires_human_approval("dir C:\\Users") is False

    # 3. Test safe execution
    res = await agent.execute_action("run_command", {"command": "echo ComputerAgent_OK"})
    assert res["status"] == "success"
    assert "ComputerAgent_OK" in res["output"]

    print("[OK] Test Passed: ComputerAgent system info, safety gate, and command execution verified.")

if __name__ == "__main__":
    asyncio.run(test_computer_agent_safety_and_exec())
