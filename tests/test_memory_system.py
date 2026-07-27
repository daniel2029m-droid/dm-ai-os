import pytest
from src.memory.memory_manager import memory_manager

def test_store_and_retrieve_memory():
    res = memory_manager.store_memory(
        content="El usuario Daniel es desarrollador de automatizaciones con Ollama local.",
        category="preference",
        importance=1.0
    )
    assert res["status"] == "SUCCESS"
    mem_id = res["memory_id"]

    memories = memory_manager.search_memory("Ollama local")
    assert len(memories) > 0
    assert any("Daniel" in m["content"] for m in memories)

    # Retrieval relevance
    relevant = memory_manager.retrieve_memory("desarrollador Ollama")
    assert len(relevant) > 0

    # Clean up
    forget_res = memory_manager.forget_memory(mem_id)
    assert forget_res["status"] == "SUCCESS"

def test_summarize_context():
    context = memory_manager.summarize_context(user_id="daniel", query="desarrollo AI")
    assert "[User Profile]" in context
    assert "Daniel" in context
