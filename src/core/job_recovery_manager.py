"""
JobRecoveryManager — Crash recovery, queue & execution timeout monitoring, and active polling for DM AI OS v1.5.1.
Enforces zero-job-loss across Windows restarts, process crashes, and temporary ComfyUI disconnections.
"""
import asyncio
import time
import logging
from typing import Dict, Any, List, Optional, Set
from pathlib import Path

from ..storage.storage_layer import storage
from ..adapters.comfy_adapter import comfy_adapter
from .job_state_machine import state_machine, InvalidStateTransitionError

log = logging.getLogger("job_recovery_manager")

class JobRecoveryManager:
    """
    Orchestrates recovery of non-terminal creative jobs after crashes or restarts.
    Provides controlled, non-blocking polling and timeout management.
    """

    def __init__(
        self,
        queue_timeout_sec: float = 300.0,
        execution_timeout_sec: float = 600.0,
        poll_interval_sec: float = 5.0,
        offline_backoff_sec: float = 10.0,
        max_offline_retries: int = 5
    ):
        self.queue_timeout_sec = queue_timeout_sec
        self.execution_timeout_sec = execution_timeout_sec
        self.poll_interval_sec = poll_interval_sec
        self.offline_backoff_sec = offline_backoff_sec
        self.max_offline_retries = max_offline_retries

        self._lock = asyncio.Lock()
        self._active_poll_tasks: Dict[str, asyncio.Task] = {}
        self._running_jobs: Set[str] = set()

    async def recover_orphaned_jobs(self) -> List[Dict[str, Any]]:
        """
        Scans JobStore for active (non-terminal) jobs: SUBMITTED, RUNNING, LOST.
        Evaluates their real state against remote ComfyUI backend and resolves or resumes tracking.
        Concurrency-safe: protected by asyncio.Lock.
        """
        async with self._lock:
            active_jobs = storage.job_store.find_active_jobs()
            results = []

            for job in active_jobs:
                job_id = job["job_id"]
                current_status = job.get("status", "SUBMITTED")
                log.info(f"[JobRecoveryManager] Recovering orphaned job '{job_id}' (current status: {current_status})")

                # Step 1: Mark as LOST if not already
                if current_status in ("SUBMITTED", "RUNNING"):
                    try:
                        state_machine.transition(job_id, "LOST", metadata={
                            "last_error": "Orphaned job detected on system boot"
                        })
                    except Exception as e:
                        log.warning(f"[JobRecoveryManager] Could not transition '{job_id}' to LOST: {e}")

                # Step 2: Query remote backend
                recovery_res = await self._recover_single_job(job_id)
                results.append(recovery_res)

            return results

    async def _recover_single_job(self, job_id: str) -> Dict[str, Any]:
        """Inspects remote backend for a single orphaned job and applies recovery logic."""
        job = storage.job_store.get_job(job_id)
        if not job:
            return {"job_id": job_id, "status": "NOT_FOUND", "action": "IGNORED"}

        # Check backend reachability
        try:
            status_res = await comfy_adapter.get_job_status(job_id)
        except Exception as e:
            log.warning(f"[JobRecoveryManager] Backend error polling '{job_id}': {e}")
            status_res = {"status": "UNAVAILABLE", "error": str(e)}

        remote_status = status_res.get("status", "UNKNOWN")

        # CASE A: Backend is Offline / UNAVAILABLE
        if remote_status == "UNAVAILABLE":
            log.warning(f"[JobRecoveryManager] Backend offline for job '{job_id}'. Preserving state for retry.")
            storage.job_store.update_job(job_id, {
                "last_error": "Backend offline during recovery check",
                "last_poll_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            })
            return {"job_id": job_id, "status": "LOST", "action": "PRESERVED_OFFLINE"}

        # CASE B: Job is completed on remote ComfyUI
        if remote_status == "COMPLETED":
            log.info(f"[JobRecoveryManager] Job '{job_id}' completed on remote ComfyUI. Triggering Auto-Vault.")
            try:
                # Transition LOST -> RECOVERED -> COMPLETED
                state_machine.transition(job_id, "RECOVERED")
            except Exception:
                pass

            # Lazy import of creative_engine to avoid circular imports
            from .creative_engine import creative_engine
            vault_res = await creative_engine.download_and_vault_artifact(job_id)
            if vault_res.get("status") == "COMPLETED":
                return {"job_id": job_id, "status": "COMPLETED", "action": "AUTO_VAULTED"}
            else:
                state_machine.transition(job_id, "FAILED", metadata={
                    "error_code": "VAULT_FAILED",
                    "error_message": vault_res.get("error", "Vaulting failed after recovery")
                })
                return {"job_id": job_id, "status": "FAILED", "action": "VAULT_FAILED"}

        # CASE C: Job is still in queue or executing on remote ComfyUI
        if remote_status in ("RUNNING", "SUBMITTED"):
            log.info(f"[JobRecoveryManager] Job '{job_id}' still active on ComfyUI. Resuming tracking.")
            try:
                state_machine.transition(job_id, "RECOVERED")
                state_machine.transition(job_id, "RUNNING")
            except Exception:
                pass

            # Launch background poller if not already active
            self.start_polling_task(job_id)
            return {"job_id": job_id, "status": "RUNNING", "action": "RESUMED_POLLING"}

        # CASE D: Remote ComfyUI reported execution failure
        if remote_status == "FAILED":
            log.warning(f"[JobRecoveryManager] Job '{job_id}' failed on remote ComfyUI.")
            try:
                state_machine.transition(job_id, "FAILED", metadata={
                    "error_code": "REMOTE_EXECUTION_ERROR",
                    "error_message": status_res.get("error", "Remote ComfyUI execution failed")
                })
            except Exception:
                pass
            return {"job_id": job_id, "status": "FAILED", "action": "MARKED_FAILED"}

        # CASE E: Job not found on active backend
        if remote_status in ("UNKNOWN", "NOT_FOUND"):
            log.warning(f"[JobRecoveryManager] Job '{job_id}' not found on active backend.")
            try:
                state_machine.transition(job_id, "FAILED", metadata={
                    "error_code": "JOB_NOT_FOUND_ON_BACKEND",
                    "error_message": "Job ID not recognized by remote ComfyUI history"
                })
            except Exception:
                pass
            return {"job_id": job_id, "status": "FAILED", "action": "NOT_FOUND_FAILED"}

        return {"job_id": job_id, "status": job.get("status"), "action": "NO_CHANGE"}

    def start_polling_task(self, job_id: str) -> None:
        """Launches a managed background task to poll a running job until terminal state."""
        if job_id in self._active_poll_tasks and not self._active_poll_tasks[job_id].done():
            log.debug(f"[JobRecoveryManager] Poller already running for job '{job_id}'")
            return

        task = asyncio.create_task(self._poll_job_loop(job_id))
        self._active_poll_tasks[job_id] = task

    async def _poll_job_loop(self, job_id: str) -> None:
        """Polls remote ComfyUI until job is completed, failed, or timed out."""
        self._running_jobs.add(job_id)
        start_poll_time = time.time()
        offline_count = 0

        try:
            while True:
                job = storage.job_store.get_job(job_id)
                if not job or job.get("status") in state_machine.TERMINAL_STATES:
                    break

                current_status = job.get("status", "SUBMITTED")
                elapsed = time.time() - start_poll_time

                # Check timeouts
                if current_status == "SUBMITTED" and elapsed > self.queue_timeout_sec:
                    log.warning(f"[JobRecoveryManager] Queue timeout exceeded for '{job_id}' ({elapsed:.1f}s)")
                    state_machine.transition(job_id, "TIMEOUT", metadata={
                        "error_code": "QUEUE_TIMEOUT",
                        "error_message": f"Job spent >{self.queue_timeout_sec}s in SUBMITTED queue."
                    })
                    break

                if current_status in ("RUNNING", "RECOVERED") and elapsed > self.execution_timeout_sec:
                    log.warning(f"[JobRecoveryManager] Execution timeout exceeded for '{job_id}' ({elapsed:.1f}s)")
                    state_machine.transition(job_id, "TIMEOUT", metadata={
                        "error_code": "EXECUTION_TIMEOUT",
                        "error_message": f"Job spent >{self.execution_timeout_sec}s in RUNNING state."
                    })
                    break

                # Poll backend status
                try:
                    res = await comfy_adapter.get_job_status(job_id)
                except Exception as e:
                    res = {"status": "UNAVAILABLE", "error": str(e)}

                st = res.get("status")

                if st == "COMPLETED":
                    from .creative_engine import creative_engine
                    await creative_engine.download_and_vault_artifact(job_id)
                    break

                elif st == "FAILED":
                    state_machine.transition(job_id, "FAILED", metadata={
                        "error_code": "REMOTE_FAILED",
                        "error_message": res.get("error", "ComfyUI execution failed")
                    })
                    break

                elif st == "UNAVAILABLE":
                    offline_count += 1
                    storage.job_store.update_job(job_id, {
                        "last_error": "Backend offline during poll",
                        "last_poll_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                    })
                    await asyncio.sleep(self.offline_backoff_sec)
                    continue

                offline_count = 0
                await asyncio.sleep(self.poll_interval_sec)

        except asyncio.CancelledError:
            log.info(f"[JobRecoveryManager] Poller cancelled for job '{job_id}'")
        except Exception as e:
            log.error(f"[JobRecoveryManager] Unexpected error polling job '{job_id}': {e}")
        finally:
            self._running_jobs.discard(job_id)
            self._active_poll_tasks.pop(job_id, None)

    async def cancel_job(self, job_id: str, reason: str = "User requested cancellation") -> Dict[str, Any]:
        """
        Cancels a creative job tracking and attempts remote interruption if supported.
        Enforces terminal state immutability via JobStateMachine.
        """
        job = storage.job_store.get_job(job_id)
        if not job:
            return {"status": "ERROR", "error": f"Job '{job_id}' not found."}

        current_status = job.get("status")
        if current_status in state_machine.TERMINAL_STATES:
            return {"status": "NOOP", "message": f"Job is already in terminal state '{current_status}'."}

        # Cancel poller task if active
        if job_id in self._active_poll_tasks:
            self._active_poll_tasks[job_id].cancel()

        # Execute transition to CANCELLED
        try:
            updated = state_machine.transition(job_id, "CANCELLED", metadata={
                "error_code": "USER_CANCELLED",
                "error_message": reason
            })
            return {"status": "CANCELLED", "job": updated}
        except InvalidStateTransitionError as e:
            return {"status": "ERROR", "error": str(e)}

    def start_background_recovery(self) -> asyncio.Task:
        """Non-blocking startup integration method."""
        return asyncio.create_task(self.recover_orphaned_jobs())

# Global singleton
job_recovery_manager = JobRecoveryManager()
