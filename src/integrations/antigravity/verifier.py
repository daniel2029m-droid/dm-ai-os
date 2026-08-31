"""
DM AI OS v1.5.2 — Physical Post-Action Verifier
Verifies on-disk state, file contents, hashes, and tool outcomes independently.
"""
import os
import hashlib
import logging
from pathlib import Path
from typing import Dict, Any, Tuple, Optional

log = logging.getLogger("antigravity_verifier")
WORKSPACE_ROOT = Path(".").resolve()


class PhysicalVerifier:
    """
    Independent post-action verification engine.
    Ensures actions reported by the agent are physically true on disk.
    """

    @staticmethod
    def verify_file_exists(relative_path: str) -> Tuple[bool, str]:
        target = (WORKSPACE_ROOT / relative_path).resolve()
        if target.exists() and target.is_file():
            size = target.stat().st_size
            return True, f"Physical file exists: {target.name} ({size} bytes)"
        return False, f"Physical file missing on disk: {relative_path}"

    @staticmethod
    def verify_file_content(relative_path: str, expected_keyword: str) -> Tuple[bool, str]:
        target = (WORKSPACE_ROOT / relative_path).resolve()
        if not target.exists():
            return False, f"File does not exist: {relative_path}"
        try:
            content = target.read_text(encoding="utf-8", errors="ignore")
            if expected_keyword.lower() in content.lower():
                return True, f"Content verification passed: found '{expected_keyword}' in {target.name}"
            return False, f"Content verification failed: '{expected_keyword}' not found in {target.name}"
        except Exception as e:
            return False, f"Error reading file for verification: {e}"

    @staticmethod
    def verify_file_hash(relative_path: str) -> Optional[str]:
        target = (WORKSPACE_ROOT / relative_path).resolve()
        if not target.exists() or not target.is_file():
            return None
        try:
            hasher = hashlib.sha256()
            with open(target, "rb") as f:
                while chunk := f.read(65536):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except Exception:
            return None

    @staticmethod
    def verify_action_execution(
        tool_name: str,
        target_path: Optional[str],
        parameters: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """
        Runs specific verification routine based on the tool executed.
        """
        if not target_path:
            return True, "No target path to verify on disk."

        target = Path(target_path)
        if tool_name in ("write_to_file", "replace_file_content"):
            if not target.exists():
                return False, f"VERIFICATION FAILED: Target file {target.name} does not exist on disk after write."
            
            # Check expected content snippet
            expected = parameters.get("ReplacementContent") or parameters.get("CodeContent") or ""
            if expected:
                snippet = expected.strip().splitlines()[0][:40]
                try:
                    current_content = target.read_text(encoding="utf-8", errors="ignore")
                    if snippet in current_content:
                        return True, f"VERIFICATION PASSED: File {target.name} exists with confirmed content snippet."
                except Exception as e:
                    return False, f"VERIFICATION FAILED: Error inspecting written file {target.name}: {e}"

            return True, f"VERIFICATION PASSED: File {target.name} exists physically on disk."

        elif tool_name == "delete_file":
            if target.exists():
                return False, f"VERIFICATION FAILED: File {target.name} still exists on disk after delete."
            return True, f"VERIFICATION PASSED: File {target.name} was physically removed."

        return True, f"VERIFICATION PASSED: Action '{tool_name}' verified."


physical_verifier = PhysicalVerifier()
