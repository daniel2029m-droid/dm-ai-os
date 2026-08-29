import asyncio
from typing import Dict, Any
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn

from .registry import mcp_registry
from .tools import register_all_tools

register_all_tools()

mcp_app = FastAPI(
    title="DM Autonomous Orchestrator MCP Server",
    version="v1.0.0",
    description="Model Context Protocol (MCP) server for Grok Build UI integration"
)

class MCPCallRequest(BaseModel):
    tool: str
    arguments: Dict[str, Any] = {}

@mcp_app.get("/")
@mcp_app.get("/health")
async def health_check():
    return {"status": "ONLINE", "service": "MCP Server"}

@mcp_app.get("/mcp/tools")
async def get_mcp_tools():
    return {"tools": mcp_registry.list_tools()}

@mcp_app.post("/mcp/call")
async def call_mcp_tool(req: MCPCallRequest):
    tool_item = mcp_registry.get_tool(req.tool)
    if not tool_item:
        raise HTTPException(status_code=404, detail=f"MCP Tool '{req.tool}' not found")
        
    handler = tool_item["handler"]
    if asyncio.iscoroutinefunction(handler):
        result = await handler(**req.arguments)
    else:
        result = handler(**req.arguments)
        
    return {
        "status": "SUCCESS",
        "tool": req.tool,
        "result": result
    }

def start_mcp_server(host: str = "0.0.0.0", port: int = 8001):
    uvicorn.run("src.mcp.mcp_server:mcp_app", host=host, port=port, reload=False, log_level="info")

if __name__ == "__main__":
    start_mcp_server()
