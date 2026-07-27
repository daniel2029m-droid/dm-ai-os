# INSTALLED COMPONENTS & AGENT REGISTRY
**Last Updated:** 2026-07-23T13:20:00-03:00 | **Source:** Phase 2 Completion

> Rule: All agents are registered in PluginManager (`src/core/plugin_manager.py`) and independently testable.

---

## Specialized Agent Roster (Phase 2 Complete)

| Agent Name | Module File | Test Suite | Safety Gate | Status |
|---|---|---|---|---|
| **Browser Agent** | `src/agents/browser_agent.py` | `tests/test_browser_agent.py` | ✅ Yes (Submissions / publishing) | `READY` |
| **Computer Agent** | `src/agents/computer_agent.py` | `tests/test_computer_agent.py` | ✅ Yes (Destructive CLI commands) | `READY` |
| **Research Agent** | `src/agents/research_agent.py` | `tests/test_research_agent.py` | — (Read-only search) | `READY` |
| **Facebook Agent** | `src/agents/facebook_agent.py` | `tests/test_facebook_agent.py` | ✅ Yes (Mandatory approval on post) | `READY` |
| **University Agent** | `src/agents/university_agent.py` | `tests/test_university_agent.py` | — (Read-only tutoring) | `READY` |
| **Media Agent** | `src/agents/media_agent.py` | `tests/test_media_agent.py` | ✅ Yes (RunPod $10 budget cap check) | `READY` |
