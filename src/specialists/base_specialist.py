"""
BaseSpecialist — Abstract Contract for Digital Employees (Fase 14.1)
====================================================================
Base class for all 20 Autonomous Business Specialist Workers.

Every specialist:
- Belongs to an isolated tenant context (TenantContext)
- Coordinates existing core agents (Browser, Research, Computer, Media, Facebook)
- Leverages mature Open Source adapters (Docling, Crawl4AI, BrowserUse, PocketFlow, Vision, VectorBackend)
- Uses MemoryManager and WorkflowEngine for persistent learning & multi-step execution
- Exposes standardized `execute_task(task_description, payload)` method
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List

from .tenant_manager import tenant_manager, TenantContext
from ..core.workflow_engine import workflow_engine
from ..memory.memory_manager import memory_manager

log = logging.getLogger("base_specialist")


class BaseSpecialist(ABC):
    """Abstract base class for autonomous business specialists."""

    def __init__(self, tenant_id: str = "daniel"):
        self.tenant_id = tenant_id
        self._tenant_context: Optional[TenantContext] = None

    @property
    def tenant(self) -> TenantContext:
        """Lazy-load isolated TenantContext."""
        if self._tenant_context is None:
            self._tenant_context = tenant_manager.get_or_create_tenant(self.tenant_id)
        return self._tenant_context

    @property
    @abstractmethod
    def specialist_id(self) -> str:
        """Unique key e.g. 'facebook_specialist'."""
        ...

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable title e.g. 'Facebook Growth Specialist'."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Role description and capabilities."""
        ...

    @abstractmethod
    async def execute_task(
        self,
        task_description: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Execute autonomous mission assigned by user.

        Args:
            task_description: High level goal e.g. "Haz crecer mi negocio de electricidad"
            payload: Optional parameters (credentials, target URLs, assets)

        Returns:
            Dict containing execution status, generated assets, reports, metrics.
        """
        ...

    def log_mission(self, message: str, level: str = "info"):
        """Log mission progress with specialist & tenant prefix."""
        full_msg = f"[{self.display_name}:{self.tenant_id}] {message}"
        if level == "warning":
            log.warning(full_msg)
        elif level == "error":
            log.error(full_msg)
        else:
            log.info(full_msg)

    def remember_result(self, topic: str, result_summary: str):
        """Store mission result in tenant's long term memory."""
        memory_manager.store_memory(
            content=f"[{self.display_name}] {topic}: {result_summary}",
            category=self.specialist_id,
            importance=1.0,
            metadata={"tenant_id": self.tenant_id, "specialist": self.specialist_id}
        )
