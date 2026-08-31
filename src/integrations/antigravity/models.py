"""
DM AI OS v1.5.2 — Antigravity Models & Schemas
"""
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
import time
import uuid

class PermissionMode(str, Enum):
    READ_ONLY = "READ_ONLY"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    AUTONOMOUS = "AUTONOMOUS"

class SessionStatus(str, Enum):
    IDLE = "IDLE"
    CONNECTING = "CONNECTING"
    ONLINE = "ONLINE"
    BUSY = "BUSY"
    PENDING_USER_APPROVAL = "PENDING_USER_APPROVAL"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    OFFLINE = "OFFLINE"

class AntigravityAction(BaseModel):
    action_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tool_name: str
    target_path: Optional[str] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)
    summary: str
    diff_preview: Optional[str] = None
    status: str = "PENDING"  # PENDING, APPROVED, REJECTED, EXECUTED, BLOCKED
    created_at: float = Field(default_factory=time.time)

class AntigravitySession(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = "daniel"
    status: SessionStatus = SessionStatus.ONLINE
    permission_mode: PermissionMode = PermissionMode.READ_ONLY
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    pending_action: Optional[AntigravityAction] = None
    history: List[Dict[str, Any]] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

class AntigravityChatRequest(BaseModel):
    prompt: str
    session_id: Optional[str] = None
    permission_mode: Optional[PermissionMode] = None

class AntigravityApprovalRequest(BaseModel):
    session_id: str
    action_id: str
    decision: str  # "APPROVE" or "REJECT"
    comments: Optional[str] = None

class AntigravityResponse(BaseModel):
    session_id: str
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    status: SessionStatus
    permission_mode: PermissionMode
    response_text: str
    pending_action: Optional[AntigravityAction] = None
    executed_tools: List[Dict[str, Any]] = Field(default_factory=list)
    latency_ms: float = 0.0
