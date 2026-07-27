"""
Scheduler - Async task queue, retries, and execution throttling between Planner and Tool Router.
"""

import asyncio
import logging
import time
from typing import Callable, Any, Dict, List, Optional
from dataclasses import dataclass, field

log = logging.getLogger("scheduler")

@dataclass
class ScheduledTask:
    task_id: str
    action: Callable
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)
    max_retries: int = 3
    retry_delay_sec: float = 2.0
    current_attempt: int = 0
    status: str = "PENDING"
    result: Any = None
    error: Optional[str] = None

class Scheduler:
    def __init__(self):
        self.queue: asyncio.Queue = asyncio.Queue()
        self.task_history: Dict[str, ScheduledTask] = {}
        self._worker_task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self):
        """Start async background worker loop."""
        if not self._worker_task or self._worker_task.done():
            self._running = True
            self._worker_task = asyncio.create_task(self._worker_loop())
            log.info("[Scheduler] Async worker loop started.")

    async def stop(self):
        """Gracefully stop the worker loop."""
        self._running = False
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        self._worker_task = None
        log.info("[Scheduler] Worker loop stopped.")

    async def submit(self, task_id: str, action: Callable, *args, max_retries: int = 3, **kwargs) -> str:
        """Submit a task to the queue."""
        task = ScheduledTask(
            task_id=task_id,
            action=action,
            args=args,
            kwargs=kwargs,
            max_retries=max_retries
        )
        self.task_history[task_id] = task
        await self.queue.put(task)
        log.info(f"[Scheduler] Task '{task_id}' queued.")
        return task_id

    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Query the status of a submitted task."""
        task = self.task_history.get(task_id)
        if not task:
            return None
        return {
            "task_id": task.task_id,
            "status": task.status,
            "attempt": task.current_attempt,
            "max_retries": task.max_retries,
            "result": task.result,
            "error": task.error
        }

    async def _worker_loop(self):
        while self._running:
            try:
                task: ScheduledTask = await asyncio.wait_for(self.queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            task.status = "RUNNING"
            log.info(f"[Scheduler] Executing task '{task.task_id}' (attempt {task.current_attempt + 1}/{task.max_retries})")

            try:
                if asyncio.iscoroutinefunction(task.action):
                    res = await task.action(*task.args, **task.kwargs)
                else:
                    res = task.action(*task.args, **task.kwargs)

                task.status = "SUCCESS"
                task.result = res
                log.info(f"[Scheduler] Task '{task.task_id}' SUCCESS.")
            except Exception as e:
                task.error = str(e)
                task.current_attempt += 1
                if task.current_attempt < task.max_retries:
                    log.warning(f"[Scheduler] Task '{task.task_id}' failed: {e}. Retrying in {task.retry_delay_sec}s...")
                    await asyncio.sleep(task.retry_delay_sec)
                    await self.queue.put(task)
                else:
                    task.status = "FAILED"
                    log.error(f"[Scheduler] Task '{task.task_id}' FAILED permanently after {task.max_retries} attempts.")
            finally:
                self.queue.task_done()

# Singleton
scheduler = Scheduler()

