from typing import Dict, Any, List
from .registry import mcp_registry
from src.core.plugin_manager import plugin_manager
from src.providers.capability_selector import capability_selector
from src.storage.storage_layer import storage
from src.core.context_manager import context_mgr
from src.core.dag_engine import TaskDAG

# Import agents
import src.agents.browser_agent
import src.agents.computer_agent
import src.agents.research_agent
import src.agents.facebook_agent
import src.agents.university_agent
import src.agents.media_agent

async def system_status(**kwargs) -> Dict[str, Any]:
    await plugin_manager.initialize_all()
    plugins = plugin_manager.list_plugins()
    models = capability_selector.probe_models()
    return {
        "status": "ONLINE",
        "registered_plugins": len(plugins),
        "models": models,
        "active_tasks": len(context_mgr.active_tasks),
        "db_path": str(storage.sqlite_db.db_path)
    }

async def list_agents(**kwargs) -> List[Dict[str, Any]]:
    await plugin_manager.initialize_all()
    return plugin_manager.list_plugins()

async def run_agent(agent: str, task: str, **kwargs) -> Dict[str, Any]:
    await plugin_manager.initialize_all()
    agent_name = agent.lower()
    if agent_name not in plugin_manager.plugins:
        return {"status": "FAILED", "error": f"Agent '{agent_name}' not registered"}
    
    action_name = kwargs.get("action", agent_name if agent_name != "browser" else "navigate")
    payload = {"topic": task, "prompt": task, "concept": task, "command": task, "goal": task}
    payload.update(kwargs)
    return await plugin_manager.invoke(agent_name, action_name, payload)

async def run_workflow(goal: str, **kwargs) -> Dict[str, Any]:
    await plugin_manager.initialize_all()
    dag = TaskDAG("mcp_workflow_dag")
    
    async def step_research():
        return await plugin_manager.invoke("research", "research", {"topic": goal})
        
    async def step_content():
        return await plugin_manager.invoke("facebook", "create_post", {"topic": goal})
        
    dag.add_node("research", step_research)
    dag.add_node("content", step_content, dependencies=["research"])
    
    dag_res = await dag.execute_parallel()
    return {
        "status": "SUCCESS",
        "goal": goal,
        "results": dag_res["node_results"]
    }

from src.memory.memory_manager import memory_manager

async def get_user_profile(user_id: str = "daniel", **kwargs) -> Dict[str, Any]:
    return memory_manager.get_user_profile(user_id=user_id)

async def remember(content: str, category: str = "general", importance: float = 1.0, **kwargs) -> Dict[str, Any]:
    return memory_manager.store_memory(content=content, category=category, importance=importance)

async def search_memory(query: str, category: str = None, **kwargs) -> List[Dict[str, Any]]:
    return memory_manager.search_memory(query=query, category=category)

async def update_memory(key: str, value: Any, user_id: str = "daniel", **kwargs) -> Dict[str, Any]:
    return memory_manager.update_user_profile(key=key, value=value, user_id=user_id)

async def forget_memory(memory_id: int, **kwargs) -> Dict[str, Any]:
    return memory_manager.forget_memory(memory_id=memory_id)

async def get_context(user_id: str = "daniel", query: str = "", **kwargs) -> str:
    return memory_manager.summarize_context(user_id=user_id, query=query)

async def get_artifacts(**kwargs) -> List[str]:
    if storage.artifacts_dir.exists():
        return [f.name for f in storage.artifacts_dir.iterdir() if f.is_file()]
    return []

from src.documents.document_pipeline import document_pipeline

async def index_document(file_path: str = None, filename: str = "doc.txt", content: str = None, **kwargs) -> Dict[str, Any]:
    if content:
        source_bytes = content.encode("utf-8")
    elif file_path:
        source_bytes = file_path
    else:
        return {"status": "FAILED", "error": "Must provide file_path or content"}
    return document_pipeline.index_document(source_bytes, filename=filename)

async def search_documents(query: str, top_k: int = 5, **kwargs) -> List[Dict[str, Any]]:
    return document_pipeline.query_documents(query, top_k=top_k)

async def web_search(query: str, **kwargs) -> Dict[str, Any]:
    await plugin_manager.initialize_all()
    return await plugin_manager.invoke("browser", "search", {"goal": query, "query": query})

async def get_capability_matrix(**kwargs) -> Dict[str, Any]:
    return capability_selector.get_capability_matrix()

# Register all MCP tools
def register_all_tools():
    mcp_registry.register_tool("system_status", "Get system health and state diagnostics", system_status)
    mcp_registry.register_tool("list_agents", "List all registered specialized agents", list_agents)
    mcp_registry.register_tool("run_agent", "Execute a specific agent task", run_agent)
    mcp_registry.register_tool("run_workflow", "Execute an end-to-end multi-agent workflow DAG", run_workflow)
    mcp_registry.register_tool("search_memory", "Search persistent SQLite knowledge memory", search_memory)
    mcp_registry.register_tool("get_artifacts", "List generated artifact files", get_artifacts)
    mcp_registry.register_tool("get_user_profile", "Get user identity and preference profile", get_user_profile)
    mcp_registry.register_tool("remember", "Store a new long-term memory", remember)
    mcp_registry.register_tool("update_memory", "Update user preference or memory entry", update_memory)
    mcp_registry.register_tool("forget_memory", "Remove a specific long-term memory entry", forget_memory)
    mcp_registry.register_tool("get_context", "Retrieve contextual memory prompt for query", get_context)
    mcp_registry.register_tool("index_document", "Parse and index PDF, DOCX, or TXT documents into long-term memory", index_document)
    mcp_registry.register_tool("search_documents", "Query indexed document memory chunks", search_documents)
    mcp_registry.register_tool("web_search", "Perform cognitive web search via Browser Agent", web_search)
    mcp_registry.register_tool("get_capability_matrix", "Get Ollama local models and dynamic capability matrix", get_capability_matrix)

register_all_tools()

