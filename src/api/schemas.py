from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional

class HealthResponse(BaseModel):
    status: str = "ONLINE"
    version: str = "v1.0.0-production"

class SystemStatusResponse(BaseModel):
    system_status: str
    agents: List[Dict[str, Any]]
    models: Dict[str, Any]
    cache: Dict[str, Any]
    database: Dict[str, Any]
    active_tasks: int

class AgentRunRequest(BaseModel):
    agent: str = Field(..., description="Target agent (browser, computer, research, facebook, university, media)")
    task: str = Field(..., description="Task prompt or action payload")
    params: Optional[Dict[str, Any]] = Field(default_factory=dict)

class AgentRunResponse(BaseModel):
    status: str
    agent: str
    result: Any
    execution_time_ms: float

class WorkflowRunRequest(BaseModel):
    goal: str = Field(..., description="Complex user goal to execute")
    params: Optional[Dict[str, Any]] = Field(default_factory=dict)

class WorkflowRunResponse(BaseModel):
    status: str
    goal: str
    model_assigned: str
    result: Any
    execution_time_sec: float

class MemoryStoreRequest(BaseModel):
    content: str = Field(..., description="Memory content text")
    category: str = Field(default="general", description="Category tag")
    importance: float = Field(default=1.0, description="Importance level 0.0-1.0")

class MemorySearchRequest(BaseModel):
    query: str = Field(..., description="Search query")
    category: Optional[str] = None

class MemoryForgetRequest(BaseModel):
    memory_id: int = Field(..., description="ID of memory to delete")

