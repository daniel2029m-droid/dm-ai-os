"""
DynamicSlotInjector — Type-safe, declarative workflow slot substitution for DM AI OS v1.5.1.

Performs recursive placeholder substitution within ComfyUI workflow JSON graphs
WITHOUT evaluating code, accessing filesystem arbitrarily, or modifying the stored workflow.

Supported slots:
    {{PROMPT}}           -> str  (required when present)
    {{NEGATIVE_PROMPT}}  -> str  (default: "")
    {{SEED}}             -> int  (default: random 1..2^32-1)
    {{STEPS}}            -> int  (default: 20)
    {{CFG}}              -> float (default: 7.0)
    {{WIDTH}}            -> int  (default: 512)
    {{HEIGHT}}           -> int  (default: 512)
    {{DENOISE}}          -> float (default: 1.0)
    {{INPUT_IMAGE}}      -> str | None (default: None)
    {{LORA_NAME}}        -> str | None (default: None)
    {{LORA_STRENGTH}}    -> float (default: 1.0)
"""
import json
import copy
import hashlib
import random
import re
import logging
from typing import Any, Dict, List, Optional, Set, Tuple

log = logging.getLogger("dynamic_slot_injector")

# ─── Slot Registry ────────────────────────────────────────────────────────────

SLOT_REGISTRY: Dict[str, Dict[str, Any]] = {
    "PROMPT":          {"type": str,   "default": None,  "required": True},
    "NEGATIVE_PROMPT": {"type": str,   "default": "",    "required": False},
    "SEED":            {"type": int,   "default": None,  "required": False},  # None = auto-random
    "STEPS":           {"type": int,   "default": 20,    "required": False,  "min": 1,   "max": 10000},
    "CFG":             {"type": float, "default": 7.0,   "required": False,  "min": 0.0, "max": 30.0},
    "WIDTH":           {"type": int,   "default": 512,   "required": False,  "min": 64,  "max": 8192},
    "HEIGHT":          {"type": int,   "default": 512,   "required": False,  "min": 64,  "max": 8192},
    "DENOISE":         {"type": float, "default": 1.0,   "required": False,  "min": 0.0, "max": 1.0},
    "INPUT_IMAGE":     {"type": str,   "default": None,  "required": False},
    "LORA_NAME":       {"type": str,   "default": None,  "required": False},
    "LORA_STRENGTH":   {"type": float, "default": 1.0,   "required": False,  "min": -10.0, "max": 10.0},
}

SLOT_PATTERN = re.compile(r"\{\{([A-Z_]+)\}\}")

# ─── Errors ───────────────────────────────────────────────────────────────────

class SlotInjectionError(ValueError):
    """Raised when slot injection fails validation or typing."""
    def __init__(self, message: str, slot: Optional[str] = None, error_code: Optional[str] = None):
        super().__init__(message)
        self.slot = slot
        self.error_code = error_code or "SLOT_INJECTION_ERROR"


# ─── Core Injector ───────────────────────────────────────────────────────────

class DynamicSlotInjector:
    """
    Performs type-safe, recursive slot substitution within ComfyUI workflow JSON.
    
    Security guarantees:
    - Pure declarative substitution; no eval(), no exec(), no code execution.
    - Does not resolve file paths or access the filesystem.
    - All substituted values are validated against typed slot registry.
    """

    def build_effective_params(
        self,
        user_params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Merges user-provided parameters with slot defaults.
        Generates a random SEED if not explicitly provided.
        Returns the complete resolved parameter set that will be used for injection.
        Includes both UPPERCASE and lowercase aliases for maximum compatibility.
        """
        params = user_params.copy() if user_params else {}

        # Normalise keys: accept lowercase user input (seed -> SEED etc.)
        normalised: Dict[str, Any] = {}
        for k, v in params.items():
            normalised[k.upper()] = v
            normalised[k.lower()] = v

        # Apply defaults for missing slots
        for slot_name, meta in SLOT_REGISTRY.items():
            if slot_name not in normalised:
                default = meta["default"]
                if slot_name == "SEED" and default is None:
                    default = random.randint(1, 2**32 - 1)
                if default is not None:
                    normalised[slot_name] = default
                    normalised[slot_name.lower()] = default

        return normalised

    def scan_slots(self, workflow: Any) -> Set[str]:
        """Scans the full workflow JSON for all {{PLACEHOLDER}} occurrences and returns their names."""
        found: Set[str] = set()
        self._scan_recursive(workflow, found)
        return found

    def _scan_recursive(self, node: Any, found: Set[str]) -> None:
        if isinstance(node, dict):
            for v in node.values():
                self._scan_recursive(v, found)
        elif isinstance(node, list):
            for item in node:
                self._scan_recursive(item, found)
        elif isinstance(node, str):
            for m in SLOT_PATTERN.finditer(node):
                found.add(m.group(1))

    def validate_params(
        self,
        workflow: Any,
        effective_params: Dict[str, Any]
    ) -> List[str]:
        """
        Validates the effective parameter set against the workflow's slot usage.
        Returns a list of error messages. Empty list = validation passed.
        """
        errors: List[str] = []
        found_slots = self.scan_slots(workflow)

        for slot_name in found_slots:
            meta = SLOT_REGISTRY.get(slot_name)

            # Detect unknown slots
            if meta is None:
                errors.append(f"Unknown slot {{{{%s}}}} found in workflow — not in registry." % slot_name)
                continue

            value = effective_params.get(slot_name)

            # Required slot missing
            if meta.get("required") and (value is None or str(value).strip() == ""):
                errors.append(f"Required slot {{{{%s}}}} has no value and no default." % slot_name)
                continue

            if value is None:
                continue

            # Type check
            expected_type = meta["type"]
            if not isinstance(value, (expected_type, type(None))):
                # Allow numeric coercions: int->float acceptable
                if expected_type is float and isinstance(value, int):
                    pass  # Coercible
                else:
                    errors.append(
                        f"Slot {{{{%s}}}}: expected %s, got %s." % (slot_name, expected_type.__name__, type(value).__name__)
                    )
                    continue

            # Range check
            if "min" in meta and value < meta["min"]:
                errors.append(f"Slot {{{{%s}}}} value %s is below minimum %s." % (slot_name, value, meta['min']))
            if "max" in meta and value > meta["max"]:
                errors.append(f"Slot {{{{%s}}}} value %s exceeds maximum %s." % (slot_name, value, meta['max']))

        return errors

    def inject(
        self,
        workflow: Any,
        effective_params: Dict[str, Any]
    ) -> Any:
        """
        Returns a deep copy of the workflow with all {{SLOT}} placeholders resolved.
        
        Type-preservation rules:
        - If a string value is EXACTLY one slot and the resolved value is not a string,
          the result is the native type (int, float, bool, None).
        - If the slot appears inside a larger string, the result is always a string.
        """
        return self._inject_recursive(copy.deepcopy(workflow), effective_params)

    def _inject_recursive(self, node: Any, params: Dict[str, Any]) -> Any:
        if isinstance(node, dict):
            return {k: self._inject_recursive(v, params) for k, v in node.items()}
        elif isinstance(node, list):
            return [self._inject_recursive(item, params) for item in node]
        elif isinstance(node, str):
            return self._substitute_string(node, params)
        return node

    def _substitute_string(self, s: str, params: Dict[str, Any]) -> Any:
        """
        Performs substitution on a string value.
        Preserves native type if the string is exactly one slot token.
        """
        # Exact match: the whole string is a single slot — preserve native type
        exact_match = SLOT_PATTERN.fullmatch(s)
        if exact_match:
            slot_name = exact_match.group(1)
            if slot_name in params:
                return params[slot_name]
            return s  # Unresolved slot — leave as-is (already validated above)

        # Partial substitution: slot embedded in a larger string — always produce str
        def replacer(m: re.Match) -> str:
            slot_name = m.group(1)
            if slot_name in params:
                val = params[slot_name]
                return "" if val is None else str(val)
            return m.group(0)  # Unresolved — leave as-is

        return SLOT_PATTERN.sub(replacer, s)

    def compute_hashes(
        self,
        template_workflow: Any,
        effective_workflow: Any
    ) -> Tuple[str, str]:
        """
        Computes both SHA-256 hashes using canonical (sorted-keys) JSON serialisation
        to guarantee deterministic results regardless of dict insertion order.

        Returns:
            (workflow_template_sha256, workflow_effective_sha256)
        """
        canonical_template = json.dumps(template_workflow, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        canonical_effective = json.dumps(effective_workflow, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        template_sha256 = hashlib.sha256(canonical_template.encode("utf-8")).hexdigest()
        effective_sha256 = hashlib.sha256(canonical_effective.encode("utf-8")).hexdigest()
        return template_sha256, effective_sha256

    def compute_idempotency_key(
        self,
        workflow_effective_sha256: str,
        model: str,
        seed: int,
        prompt: str,
        extra_params: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Computes a deterministic idempotency key for a specific creative execution.
        Identical key = same execution result — can be used to skip redundant dispatches.

        Note: different seed → different key → new execution.
        """
        parts = [
            workflow_effective_sha256,
            str(model),
            str(seed),
            prompt.strip(),
        ]
        if extra_params:
            parts.append(json.dumps(extra_params, sort_keys=True, ensure_ascii=False, separators=(",", ":")))
        combined = "|".join(parts)
        return hashlib.sha256(combined.encode("utf-8")).hexdigest()

    def process(
        self,
        template_workflow: Any,
        user_params: Optional[Dict[str, Any]] = None,
        model: str = "unknown"
    ) -> Dict[str, Any]:
        """
        Complete slot injection pipeline:
        1. Merge user params with defaults.
        2. Validate against workflow slots.
        3. Inject into deep copy.
        4. Compute template and effective hashes.
        5. Compute idempotency key.

        Returns a structured result dict. Raises SlotInjectionError on hard failures.
        """
        effective_params = self.build_effective_params(user_params)

        # Validate
        errors = self.validate_params(template_workflow, effective_params)
        if errors:
            raise SlotInjectionError(
                f"Slot validation failed ({len(errors)} error(s)):\n" + "\n".join(f"  - {e}" for e in errors),
                error_code="SLOT_VALIDATION_FAILED"
            )

        # Inject
        effective_workflow = self.inject(template_workflow, effective_params)

        # Double hash (deterministic, canonical JSON)
        template_sha256, effective_sha256 = self.compute_hashes(template_workflow, effective_workflow)

        # Idempotency key
        seed = effective_params.get("SEED", 0)
        prompt = effective_params.get("PROMPT") or ""
        idempotency_key = self.compute_idempotency_key(effective_sha256, model, seed, prompt)

        return {
            "effective_workflow": effective_workflow,
            "effective_params": effective_params,
            "workflow_template_sha256": template_sha256,
            "workflow_effective_sha256": effective_sha256,
            "idempotency_key": idempotency_key,
        }


# ─── Singleton ────────────────────────────────────────────────────────────────

slot_injector = DynamicSlotInjector()
