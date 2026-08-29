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

from src.adapters.higgsfield_adapter import higgsfield_adapter
from src.core.creative_engine import creative_engine
from src.adapters.comfy_adapter import comfy_adapter

async def higgsfield_generate_video(prompt: str, duration: int = 5, resolution: str = "720p", mode: str = "cinema", aspect_ratio: str = "16:9", **kwargs) -> Dict[str, Any]:
    return await higgsfield_adapter.generate_video(prompt=prompt, duration=duration, resolution=resolution, mode=mode, aspect_ratio=aspect_ratio)

async def higgsfield_generate_image(prompt: str, aspect_ratio: str = "1:1", style: str = "soul", **kwargs) -> Dict[str, Any]:
    return await higgsfield_adapter.generate_image(prompt=prompt, aspect_ratio=aspect_ratio, style=style)

async def higgsfield_image_to_video(image_url: str, prompt: str, motion_strength: float = 0.8, **kwargs) -> Dict[str, Any]:
    return await higgsfield_adapter.image_to_video(image_url=image_url, prompt=prompt, motion_strength=motion_strength)

async def higgsfield_status(**kwargs) -> Dict[str, Any]:
    return {"mcp_url": higgsfield_adapter.mcp_url, "available": higgsfield_adapter._is_available(), "tools": higgsfield_adapter.list_mcp_tools()}

# Creative Engine / Comfy MCP Tools
async def creative_status(**kwargs) -> Dict[str, Any]:
    return {
        "backend": comfy_adapter.get_backend_info(),
        "templates_count": len(creative_engine.list_templates()),
        "templates": [t["name"] for t in creative_engine.list_templates()]
    }

async def creative_list_workflows(**kwargs) -> List[Dict[str, Any]]:
    return creative_engine.list_templates()

async def creative_run_workflow(template: str, prompt: str, **kwargs) -> Dict[str, Any]:
    return await creative_engine.run_workflow(template_name_or_path=template, prompt=prompt, parameters=kwargs)

async def creative_generate_image(prompt: str, template: str = "flux2_klein_txt2img", **kwargs) -> Dict[str, Any]:
    return await creative_engine.run_workflow(template_name_or_path=template, prompt=prompt, parameters=kwargs)

async def creative_generate_video(prompt: str, template: str = "wan22_i2v", **kwargs) -> Dict[str, Any]:
    return await creative_engine.run_workflow(template_name_or_path=template, prompt=prompt, parameters=kwargs)

from src.core.job_recovery_manager import job_recovery_manager
from src.core.job_state_machine import state_machine

# --- Phase 14.4 MCP API v2 Tools ---

async def creative_get_job(job_id: str, **kwargs) -> Dict[str, Any]:
    """Retrieves status, progress, manifest, and output assets for a creative job."""
    job = storage.job_store.get_job(job_id)
    if not job:
        return {
            "status": "ERROR",
            "error_code": "JOB_NOT_FOUND",
            "error": f"Job '{job_id}' not found in JobStore."
        }

    manifest_dict = {}
    manifest_file = storage.artifacts_dir / f"creative_manifest_{job_id}.json"
    if manifest_file.exists():
        try:
            import json
            manifest_dict = json.loads(manifest_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    st = job.get("status", "UNKNOWN")
    return {
        "job_id": job_id,
        "status": st,
        "progress": 100 if st == "COMPLETED" else (50 if st in ("RUNNING", "RECOVERED") else 0),
        "manifest": manifest_dict,
        "outputs": job.get("output_assets", []),
        "output_sha256": job.get("output_sha256"),
        "created_at": job.get("created_at"),
        "completed_at": job.get("completed_at"),
        "error_message": job.get("error_message")
    }

async def creative_download_asset(job_id: str, auto_vault: bool = True, **kwargs) -> Dict[str, Any]:
    """Downloads and retrieves the vaulted local media asset for a completed job."""
    job = storage.job_store.get_job(job_id)
    if not job:
        return {
            "status": "ERROR",
            "error_code": "JOB_NOT_FOUND",
            "error": f"Job '{job_id}' not found in JobStore."
        }

    # If already vaulted with local output file
    if job.get("output_assets") and job.get("output_sha256"):
        local_path = job["output_assets"][0]
        return {
            "status": "SUCCESS",
            "job_id": job_id,
            "local_path": local_path,
            "sha256": job["output_sha256"],
            "size_bytes": job.get("output_size_bytes", 0),
            "vault_status": "VAULTED"
        }

    # If not yet vaulted, attempt Auto-Vaulting via CreativeEngine
    vault_res = await creative_engine.download_and_vault_artifact(job_id)
    if vault_res.get("status") == "COMPLETED":
        assets = vault_res.get("output_assets", [])
        return {
            "status": "SUCCESS",
            "job_id": job_id,
            "local_path": assets[0] if assets else "",
            "sha256": vault_res.get("output_sha256", ""),
            "size_bytes": vault_res.get("output_size_bytes", 0),
            "vault_status": "VAULTED"
        }
    else:
        return {
            "status": "ERROR",
            "error_code": "ASSET_NOT_READY",
            "error": vault_res.get("error", "Asset not ready for download or remote ComfyUI offline.")
        }

async def creative_cancel_job(job_id: str, reason: str = "User requested cancellation", **kwargs) -> Dict[str, Any]:
    """Cancels an active creative job adhering strictly to the JobStateMachine."""
    job = storage.job_store.get_job(job_id)
    if not job:
        return {
            "status": "ERROR",
            "error_code": "JOB_NOT_FOUND",
            "error": f"Job '{job_id}' not found in JobStore."
        }

    if job.get("status") == "COMPLETED":
        return {
            "status": "ERROR",
            "error_code": "JOB_ALREADY_COMPLETED",
            "error": f"Job '{job_id}' is already COMPLETED and cannot be cancelled."
        }

    return await job_recovery_manager.cancel_job(job_id, reason=reason)

async def creative_list_history(limit: int = 20, status: str = None, **kwargs) -> List[Dict[str, Any]]:
    """Lists persistent creative job execution history from JobStore."""
    clean_limit = max(1, min(int(limit), 100))
    valid_status = status if status in state_machine.STATES else None
    jobs = storage.job_store.list_jobs(limit=clean_limit, status=valid_status)

    summaries = []
    for j in jobs:
        summaries.append({
            "job_id": j.get("job_id"),
            "workflow_name": j.get("workflow_name"),
            "status": j.get("status"),
            "created_at": j.get("created_at"),
            "completed_at": j.get("completed_at"),
            "model_checkpoint": j.get("model_checkpoint"),
            "output_assets": j.get("output_assets", []),
            "prompt": j.get("prompt")
        })
    return summaries

# ─── Phase 15.5 MCP API v3 Tools ───────────────────────────────────────────

async def creative_record_metrics(job_id: str, metrics: Dict[str, Any] = None, **kwargs) -> Dict[str, Any]:
    """Records audience engagement and performance telemetry for a creative job."""
    from ..core.content_intelligence import content_intelligence, ContentIntelligenceError
    if not job_id:
        return {"status": "ERROR", "error_code": "INVALID_JOB_ID", "error": "job_id is required."}

    payload = dict(metrics or {})
    payload["job_id"] = job_id
    if "channel" not in payload and "channel" in kwargs:
        payload["channel"] = kwargs["channel"]

    try:
        res = content_intelligence.ingest_performance_event(payload)
        return res
    except ContentIntelligenceError as ce:
        return {"status": "ERROR", "error_code": ce.error_code, "error": str(ce), "details": ce.details}
    except Exception as e:
        return {"status": "ERROR", "error_code": "INGESTION_FAILED", "error": str(e)}

async def creative_analyze_patterns(category: str = None, limit: int = 10, **kwargs) -> List[Dict[str, Any]]:
    """Analyzes high-performing and underperforming creative patterns backed by audience metrics."""
    from ..core.creative_memory import creative_memory
    clean_limit = max(1, min(int(limit), 50))
    return creative_memory.get_top_patterns(category=category, limit=clean_limit)

async def creative_create_experiment(
    name: str,
    base_template: str,
    base_prompt: str,
    variable_tested: str,
    control_value: Any,
    variant_values: List[Any],
    hypothesis: str = None,
    **kwargs
) -> Dict[str, Any]:
    """Designs controlled multivariate creative experiments without executing unapproved dispatches."""
    from ..core.experiment_engine import experiment_engine, ExperimentError
    try:
        exp = experiment_engine.create_experiment(
            name=name,
            base_template=base_template,
            base_prompt=base_prompt,
            variable_tested=variable_tested,
            control_value=control_value,
            variant_values=variant_values,
            hypothesis=hypothesis,
            fixed_parameters=kwargs.get("fixed_parameters")
        )
        return {"status": "SUCCESS", "experiment": exp}
    except ExperimentError as ee:
        return {"status": "ERROR", "error_code": ee.error_code, "error": str(ee), "details": ee.details}
    except Exception as e:
        return {"status": "ERROR", "error_code": "EXPERIMENT_CREATION_FAILED", "error": str(e)}

async def creative_get_strategy_brief(topic: str = None, **kwargs) -> Dict[str, Any]:
    """Synthesizes historical memory, pattern statistics, and evidence into an optimal Creative Brief."""
    from ..core.strategy_engine import strategy_engine, StrategyError
    try:
        if topic:
            brief = strategy_engine.create_brief(
                topic=topic,
                target_channel=kwargs.get("target_channel"),
                base_template=kwargs.get("base_template"),
                model_name=kwargs.get("model_name"),
                custom_hypothesis=kwargs.get("hypothesis"),
                parameters=kwargs.get("parameters")
            )
            return {"status": "SUCCESS", "brief": brief}
        else:
            briefs = strategy_engine.list_briefs(limit=10)
            return {"status": "SUCCESS", "briefs": briefs}
    except StrategyError as se:
        return {"status": "ERROR", "error_code": se.error_code, "error": str(se), "details": se.details}
    except Exception as e:
        return {"status": "ERROR", "error_code": "STRATEGY_BRIEF_FAILED", "error": str(e)}

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
    mcp_registry.register_tool("higgsfield_generate_video", "Generate cinematic AI video using Higgsfield AI MCP connector", higgsfield_generate_video)
    mcp_registry.register_tool("higgsfield_generate_image", "Generate photorealistic AI image using Higgsfield AI MCP connector", higgsfield_generate_image)
    mcp_registry.register_tool("higgsfield_image_to_video", "Animate static image into video clip using Higgsfield AI MCP connector", higgsfield_image_to_video)
    mcp_registry.register_tool("higgsfield_status", "Check status of Higgsfield AI MCP connector", higgsfield_status)
    mcp_registry.register_tool("creative_status", "Check status and active backend of Creative Engine / Comfy MCP", creative_status)
    mcp_registry.register_tool("creative_list_workflows", "List all reproducible ComfyUI workflow templates", creative_list_workflows)
    mcp_registry.register_tool("creative_run_workflow", "Execute a reproducible ComfyUI workflow template", creative_run_workflow)
    mcp_registry.register_tool("creative_generate_image", "Generate image using ComfyUI creative workflow", creative_generate_image)
    mcp_registry.register_tool("creative_generate_video", "Generate video using ComfyUI creative workflow", creative_generate_video)
    # Phase 14.4 MCP v2 tools
    mcp_registry.register_tool("creative_get_job", "Get status, progress and manifest of a creative job", creative_get_job)
    mcp_registry.register_tool("creative_download_asset", "Download and retrieve vaulted asset for a completed creative job", creative_download_asset)
    mcp_registry.register_tool("creative_cancel_job", "Cancel an active creative job", creative_cancel_job)
    mcp_registry.register_tool("creative_list_history", "List creative generation history from JobStore", creative_list_history)
    # Phase 15.5 MCP v3 tools
    mcp_registry.register_tool("creative_record_metrics", "Record audience engagement and performance telemetry for a creative job", creative_record_metrics)
    mcp_registry.register_tool("creative_analyze_patterns", "Analyze high-performing creative patterns backed by audience metrics", creative_analyze_patterns)
    mcp_registry.register_tool("creative_create_experiment", "Design controlled multivariate creative experiments", creative_create_experiment)
    mcp_registry.register_tool("creative_get_strategy_brief", "Synthesize actionable creative strategy briefs from memory and evidence", creative_get_strategy_brief)

register_all_tools()




