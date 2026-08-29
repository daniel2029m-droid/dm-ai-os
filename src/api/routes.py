import time
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Security, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from .mobile_web import get_mobile_html
from .schemas import (
    HealthResponse,
    SystemStatusResponse,
    AgentRunRequest,
    AgentRunResponse,
    WorkflowRunRequest,
    WorkflowRunResponse,
    MemoryStoreRequest,
    MemorySearchRequest,
    MemoryForgetRequest,
    MediaImageRequest,
    MediaVideoRequest
)
from .auth import verify_api_key

from src.core.plugin_manager import plugin_manager
from src.providers.capability_selector import capability_selector
from src.storage.storage_layer import storage
from src.core.context_manager import context_mgr
from src.core.dag_engine import TaskDAG
from src.memory.memory_manager import memory_manager
from src.api.brain_pipeline import brain_pipeline
from src.adapters.higgsfield_adapter import higgsfield_adapter

# Import agents to ensure registration
import src.agents.browser_agent
import src.agents.computer_agent
import src.agents.research_agent
import src.agents.facebook_agent
import src.agents.university_agent
import src.agents.media_agent


router = APIRouter()

@router.get("/", response_class=HTMLResponse)
@router.get("/connect", response_class=HTMLResponse)
async def connect_page(request: Request):
    # Extract host to form base url dynamically if accessed via tunnel
    base_url = f"https://{request.url.hostname}" if request.url.hostname and "trycloudflare.com" in request.url.hostname else f"http://{request.url.hostname}:{request.url.port}"
    api_url = f"{base_url}/v1"
    html_content = get_mobile_html(api_url=api_url, tunnel_url=base_url)
    return HTMLResponse(content=html_content, headers={
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0"
    })

@router.get("/manifest.json")
async def get_pwa_manifest():
    manifest = {
        "name": "DM AI OS — iPhone Remote Terminal",
        "short_name": "DM AI OS",
        "start_url": "/connect",
        "display": "standalone",
        "theme_color": "#0f172a",
        "background_color": "#0f172a",
        "icons": [
            {
                "src": "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><rect width='100' height='100' rx='20' fill='%230f172a'/><text x='50' y='65' font-size='50' text-anchor='middle' fill='%2338bdf8'>DM</text></svg>",
                "sizes": "192x192",
                "type": "image/svg+xml"
            }
        ]
    }
    return JSONResponse(content=manifest)

@router.get("/sw.js")
async def get_service_worker():
    sw_code = """
    self.addEventListener('install', (e) => {
        self.skipWaiting();
    });
    self.addEventListener('activate', (e) => {
        e.waitUntil(clients.claim());
    });
    self.addEventListener('fetch', (e) => {
        e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
    });
    """
    return Response(content=sw_code, media_type="application/javascript", headers={
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0"
    })

@router.get("/health", response_model=HealthResponse)
async def get_health():
    return HealthResponse(status="ONLINE", version="v1.0.0-production")

@router.get("/system/status", response_model=SystemStatusResponse, dependencies=[Depends(verify_api_key)])
async def get_system_status():
    await plugin_manager.initialize_all()
    plugins = plugin_manager.list_plugins()
    models = capability_selector.probe_models()
    
    return SystemStatusResponse(
        system_status="ONLINE",
        agents=plugins,
        models={"ollama_models": models},
        cache={"directory": str(storage.cache.cache_dir)},
        database={"path": str(storage.sqlite_db.db_path)},
        active_tasks=len(context_mgr.active_tasks)
    )

@router.get("/agents", dependencies=[Depends(verify_api_key)])
async def list_agents():
    await plugin_manager.initialize_all()
    return plugin_manager.list_plugins()

@router.post("/agent/run", response_model=AgentRunResponse, dependencies=[Depends(verify_api_key)])
async def run_agent(req: AgentRunRequest):
    await plugin_manager.initialize_all()
    t0 = time.perf_counter()
    
    agent_name = req.agent.lower()
    if agent_name not in plugin_manager.plugins:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")
        
    action_name = req.params.get("action", agent_name if agent_name != "browser" else "navigate")
    payload = {"topic": req.task, "prompt": req.task, "concept": req.task, "command": req.task, "goal": req.task}
    payload.update(req.params)
    
    res = await plugin_manager.invoke(agent_name, action_name, payload)
    elapsed = round((time.perf_counter() - t0) * 1000, 2)
    
    return AgentRunResponse(
        status="SUCCESS" if res.get("status") != "FAILED" else "FAILED",
        agent=agent_name,
        result=res,
        execution_time_ms=elapsed
    )

@router.post("/workflow/run", response_model=WorkflowRunResponse, dependencies=[Depends(verify_api_key)])
async def run_workflow(req: WorkflowRunRequest):
    await plugin_manager.initialize_all()
    t0 = time.perf_counter()
    
    model_assigned = capability_selector.select_model_for_capability("planning")
    
    dag = TaskDAG("api_workflow_dag")
    
    async def step_research():
        return await plugin_manager.invoke("research", "research", {"topic": req.goal})
        
    async def step_content():
        return await plugin_manager.invoke("facebook", "create_post", {"topic": req.goal})
        
    dag.add_node("research", step_research)
    dag.add_node("content", step_content, dependencies=["research"])
    
    dag_res = await dag.execute_parallel()
    elapsed = round(time.perf_counter() - t0, 2)
    
    return WorkflowRunResponse(
        status="SUCCESS",
        goal=req.goal,
        model_assigned=model_assigned,
        result=dag_res["node_results"],
        execution_time_sec=elapsed
    )


@router.get("/memory/profile", dependencies=[Depends(verify_api_key)])
async def get_memory_profile(user_id: str = "daniel"):
    return memory_manager.get_user_profile(user_id=user_id)

@router.post("/memory/store", dependencies=[Depends(verify_api_key)])
async def store_memory_endpoint(req: MemoryStoreRequest):
    return memory_manager.store_memory(content=req.content, category=req.category, importance=req.importance)

@router.post("/memory/search", dependencies=[Depends(verify_api_key)])
async def search_memory_endpoint(req: MemorySearchRequest):
    return memory_manager.search_memory(query=req.query, category=req.category)

@router.post("/memory/forget", dependencies=[Depends(verify_api_key)])
async def forget_memory_endpoint(req: MemoryForgetRequest):
    return memory_manager.forget_memory(memory_id=req.memory_id)

@router.get("/memory/context", dependencies=[Depends(verify_api_key)])
async def get_memory_context(user_id: str = "daniel", query: str = ""):
    return {"context": memory_manager.summarize_context(user_id=user_id, query=query)}

# ─────────────────────────────────────────────────────────────────────────────
# Official Media API Endpoints (Higgsfield & Multi-Provider Integration)
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/api/media/image", dependencies=[Depends(verify_api_key)])
async def create_media_image(req: MediaImageRequest):
    await plugin_manager.initialize_all()
    payload = {
        "prompt": req.prompt,
        "provider": req.provider,
        "resolution": req.resolution,
        "aspect_ratio": req.aspect_ratio,
        "style": req.style
    }
    return await plugin_manager.invoke("media", "generate_image", payload)

@router.post("/api/media/video", dependencies=[Depends(verify_api_key)])
async def create_media_video(req: MediaVideoRequest):
    await plugin_manager.initialize_all()
    payload = {
        "prompt": req.prompt,
        "image_url": req.image_url,
        "image_filename": req.image_url or "image.png",
        "provider": req.provider,
        "duration": req.duration,
        "resolution": req.resolution,
        "mode": req.mode
    }
    return await plugin_manager.invoke("media", "generate_video", payload)

@router.get("/api/media/jobs/{job_id}", dependencies=[Depends(verify_api_key)])
async def get_media_job_status(job_id: str):
    return await higgsfield_adapter.get_job_status(job_id)

# ─────────────────────────────────────────────────────────────────────────────
# Phase 9: OpenAI-compatible routes moved to src/api/openai_compat/
#
# GET  /v1/models          → src/api/openai_compat/models_router.py
# POST /v1/chat/completions → src/api/openai_compat/chat_completions_router.py
# POST /v1/responses        → src/api/openai_compat/responses_router.py
#
# All previous routes above remain unchanged.
# ─────────────────────────────────────────────────────────────────────────────

