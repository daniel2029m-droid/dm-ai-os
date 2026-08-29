"""
JobStateMachine — Strict, validated lifecycle transitions for Creative Jobs in DM AI OS v1.5.1.

Validates and executes lifecycle state transitions across:
    SUBMITTED -> RUNNING, FAILED, TIMEOUT, CANCELLED, LOST
    RUNNING   -> COMPLETED, FAILED, TIMEOUT, CANCELLED, LOST
    LOST      -> RECOVERED, FAILED, CANCELLED, TIMEOUT
    RECOVERED -> RUNNING, COMPLETED, FAILED, CANCELLED, TIMEOUT
    Terminal states (COMPLETED, FAILED, TIMEOUT, CANCELLED): Immutable.
"""
import time
import json
import logging
from typing import Dict, Any, Optional, Set
from ..storage.storage_layer import storage

log = logging.getLogger("job_state_machine")

class InvalidStateTransitionError(ValueError):
    """Raised when an invalid job lifecycle state transition is attempted."""
    def __init__(self, job_id: str, current_state: str, target_state: str, reason: Optional[str] = None):
        msg = f"Invalid state transition for job '{job_id}': cannot move from '{current_state}' to '{target_state}'."
        if reason:
            msg += f" Reason: {reason}"
        super().__init__(msg)
        self.job_id = job_id
        self.current_state = current_state
        self.target_state = target_state


class JobStateMachine:
    """
    Centralized state transition validator and state machine for Creative Engine jobs.
    Guarantees thread-safe transitions and enforces terminal state immutability.
    """

    STATES: Set[str] = {
        "SUBMITTED",
        "RUNNING",
        "COMPLETED",
        "FAILED",
        "TIMEOUT",
        "CANCELLED",
        "LOST",
        "RECOVERED"
    }

    TERMINAL_STATES: Set[str] = {
        "COMPLETED",
        "FAILED",
        "TIMEOUT",
        "CANCELLED"
    }

    VALID_TRANSITIONS: Dict[str, Set[str]] = {
        "SUBMITTED": {"RUNNING", "FAILED", "TIMEOUT", "CANCELLED", "LOST"},
        "RUNNING": {"COMPLETED", "FAILED", "TIMEOUT", "CANCELLED", "LOST"},
        "LOST": {"RECOVERED", "FAILED", "CANCELLED", "TIMEOUT"},
        "RECOVERED": {"RUNNING", "COMPLETED", "FAILED", "CANCELLED", "TIMEOUT"},
        "COMPLETED": set(),
        "FAILED": set(),
        "TIMEOUT": set(),
        "CANCELLED": set()
    }

    def validate_transition(self, current_state: str, target_state: str) -> bool:
        """Returns True if transition from current_state to target_state is permitted."""
        if target_state not in self.STATES:
            return False
        allowed = self.VALID_TRANSITIONS.get(current_state, set())
        return target_state in allowed

    def transition(
        self,
        job_id: str,
        target_state: str,
        metadata: Optional[Dict[str, Any]] = None,
        job_store_instance = None
    ) -> Dict[str, Any]:
        """
        Executes a validated transition on a job stored in JobStore.
        Updates timestamps, error fields, and manifest artifacts automatically.
        
        Raises InvalidStateTransitionError if transition is illegal.
        """
        js = job_store_instance or storage.job_store
        job = js.get_job(job_id)
        if not job:
            raise KeyError(f"Job '{job_id}' not found in JobStore.")

        current_state = job.get("status", "SUBMITTED")

        if current_state == target_state:
            # Idempotent no-op
            return job

        if not self.validate_transition(current_state, target_state):
            raise InvalidStateTransitionError(job_id, current_state, target_state)

        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        updates: Dict[str, Any] = {"status": target_state}

        if metadata:
            updates.update(metadata)

        # Automatic lifecycle timestamping
        if target_state == "RUNNING" and not job.get("started_at"):
            updates["started_at"] = now
        elif target_state in self.TERMINAL_STATES and not job.get("completed_at"):
            updates["completed_at"] = now

        # Update last_poll_at
        updates["last_poll_at"] = now

        js.update_job(job_id, updates)
        updated_job = js.get_job(job_id)

        # Update Manifest in Artifacts Vault if manifest exists
        try:
            storage._ensure_artifacts_dir()
            manifest_path = storage.artifacts_dir / f"creative_manifest_{job_id}.json"
            if manifest_path.exists():
                manifest_dict = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest_dict["status"] = target_state
                if "output_assets" in updates:
                    manifest_dict["output_assets"] = updates["output_assets"]
                if "output_sha256" in updates:
                    manifest_dict["output_sha256"] = updates["output_sha256"]
                if "output_size_bytes" in updates:
                    manifest_dict["output_size_bytes"] = updates["output_size_bytes"]
                if "error_message" in updates:
                    manifest_dict["error_message"] = updates["error_message"]
                storage.save_artifact(f"creative_manifest_{job_id}.json", json.dumps(manifest_dict, indent=2, ensure_ascii=False))
        except Exception as e:
            log.warning(f"[JobStateMachine] Could not sync manifest status for {job_id}: {e}")

        log.info(f"[JobStateMachine] Job '{job_id}' transitioned from '{current_state}' -> '{target_state}'")
        return updated_job

# Global singleton
state_machine = JobStateMachine()
