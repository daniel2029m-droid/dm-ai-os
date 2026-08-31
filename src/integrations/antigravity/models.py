"""
DM AI OS v1.5.2 — Antigravity Orchestrator Models & Schemas
"""
from typing import List, Dict, Any, Optional
from enum import Enum
import uuid
import time
from pydantic import BaseModel, Field


class PermissionMode(str, Enum):
    READ_ONLY = "READ_ONLY"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    AUTONOMOUS = "AUTONOMOUS"


class SessionStatus(str, Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    PENDING_USER_APPROVAL = "PENDING_USER_APPROVAL"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    OFFLINE = "OFFLINE"


class EngineType(str, Enum):
    ANTIGRAVITY = "ANTIGRAVITY"
    OLLAMA = "OLLAMA"
    AUTO = "AUTO"


class StepStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"


class ProviderCapabilities(BaseModel):
    provider: str
    status: str
    model: str
    filesystem: bool = True
    mcp: bool = True
    web: bool = False
    command_execution: bool = True
    file_write: bool = True
    streaming: bool = True
    planning: bool = True


class AntigravityAction(BaseModel):
    action_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tool_name: str
    target_path: Optional[str] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)
    summary: str
    diff_preview: Optional[str] = None
    created_at: float = Field(default_factory=time.time)
    status: str = "PENDING"  # PENDING, APPROVED, REJECTED, EXECUTED, FAILED


class PlanStep(BaseModel):
    step_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    step_index: int
    title: str
    description: str
    tool_name: Optional[str] = None
    status: StepStatus = StepStatus.PENDING
    result: Optional[str] = None
    verification_status: Optional[str] = None
    error: Optional[str] = None


class TaskPlan(BaseModel):
    plan_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    task_prompt: str
    steps: List[PlanStep] = Field(default_factory=list)
    current_step_index: int = 0
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    status: StepStatus = StepStatus.PENDING


class OrchestratorAuditEntry(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = Field(default_factory=time.time)
    session_id: str
    task_id: Optional[str] = None
    step_id: Optional[str] = None
    provider: str = "google.antigravity.Agent"
    model: str = "qwen2.5:1.5b"
    tool: Optional[str] = None
    action: Optional[str] = None
    permission_mode: str = "READ_ONLY"
    approval_id: Optional[str] = None
    result: Optional[str] = None
    verification: Optional[str] = None
    duration_ms: float = 0.0
    error: Optional[str] = None



class AntigravitySession(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    permission_mode: PermissionMode = PermissionMode.READ_ONLY
    status: SessionStatus = SessionStatus.IDLE
    current_plan: Optional[TaskPlan] = None
    pending_action: Optional[AntigravityAction] = None
    history: List[Dict[str, Any]] = Field(default_factory=list)



class AntigravityChatRequest(BaseModel):
    prompt: str
    session_id: Optional[str] = None
    permission_mode: Optional[PermissionMode] = None
    engine_type: Optional[EngineType] = EngineType.AUTO
    model_preference: Optional[str] = None


class AntigravityApprovalRequest(BaseModel):
    session_id: str
    action_id: str
    decision: str  # "APPROVE" or "REJECT"


class AntigravityResponse(BaseModel):
    session_id: str
    status: SessionStatus
    permission_mode: PermissionMode
    response_text: str
    engine_used: Optional[str] = "google.antigravity.Agent"
    model_used: Optional[str] = "qwen2.5:1.5b"
    executed_tools: List[Dict[str, Any]] = Field(default_factory=list)
    pending_action: Optional[AntigravityAction] = None
    plan: Optional[TaskPlan] = None
    verification: Optional[str] = None
    latency_ms: float = 0.0
