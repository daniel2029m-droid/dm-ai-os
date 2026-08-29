"""
Capability-Based Dynamic Model Selector.
Selects local model based on required task capability:
- reasoning / planning -> Priority: Bonsai 27B 1-bit > Qwen 3 > Qwen 2.5 1.5B
- coding               -> Qwen Code / Qwen 2.5 1.5B
- summarization / OCR  -> Qwen 2.5 0.5B / ultra-light
"""

import httpx
import logging
import os
from typing import Dict, Any, List, Optional

log = logging.getLogger("capability_selector")

# Capability mapping
CAPABILITY_MAP = {
    "reasoning":     ["qwen2.5-coder:7b", "qwen2.5-coder", "bonsai", "qwen3", "qwen2.5:1.5b"],
    "planning":      ["qwen2.5-coder:7b", "qwen2.5-coder", "bonsai", "qwen3", "qwen2.5:1.5b"],
    "coding":        ["qwen2.5-coder:7b", "qwen2.5-coder", "qwen-code", "qwen2.5:1.5b"],
    "summarization": ["qwen2.5-coder:7b", "qwen2.5:1.5b", "qwen2.5:0.5b"],
    "ocr":           ["llava", "bakllava", "llama3.2-vision", "qwen2-vl", "qwen2.5:0.5b"],
    "vision":        ["llava", "bakllava", "llama3.2-vision", "qwen2-vl", "qwen2.5:1.5b"],
    "research":      ["qwen2.5-coder:7b", "qwen2.5-coder", "qwen2.5:1.5b"],
    "general":       ["qwen2.5-coder:7b", "qwen2.5-coder", "qwen2.5:1.5b"]
}

class CapabilityModelSelector:
    def __init__(self, ollama_url: str = "http://localhost:11434"):
        self.ollama_url = ollama_url.rstrip("/")
        self.available_models: List[str] = []

    @property
    def base_ollama_url(self) -> str:
        """Public accessor used by openai_compat layer."""
        return self.ollama_url

    def probe_models(self) -> List[str]:
        try:
            r = httpx.get(f"{self.ollama_url}/api/tags", timeout=5)
            if r.status_code == 200:
                self.available_models = [m.get("name", "") for m in r.json().get("models", [])]
                return self.available_models
        except Exception as e:
            log.warning(f"[CapabilitySelector] Probe failed: {e}")
        return []

    def select_model_for_capability(self, capability: str = "general") -> str:
        """Select best available model matching requested capability."""
        installed = self.probe_models()
        candidates = CAPABILITY_MAP.get(capability.lower(), CAPABILITY_MAP["general"])

        for candidate_pattern in candidates:
            for m in installed:
                if candidate_pattern.lower() in m.lower():
                    log.info(f"[CapabilitySelector] Capability '{capability}' -> Selected model '{m}'")
                    return m

        fallback = installed[0] if installed else "qwen2.5:1.5b"
        log.info(f"[CapabilitySelector] Capability '{capability}' -> Fallback model '{fallback}'")
        return fallback

    def get_capability_matrix(self) -> Dict[str, Any]:
        """Return automatic capability matrix mapping task capabilities to local models."""
        installed = self.probe_models()
        return {
            "status": "ONLINE" if installed else "OFFLINE",
            "ollama_url": self.ollama_url,
            "installed_models": installed,
            "capabilities": {
                "texto": self.select_model_for_capability("general"),
                "razonamiento": self.select_model_for_capability("reasoning"),
                "visión": self.select_model_for_capability("vision"),
                "código": self.select_model_for_capability("coding"),
                "investigación": self.select_model_for_capability("research"),
            }
        }

    def generate(
        self,
        prompt: str,
        capability: str = "general",
        system_prompt: Optional[str] = None,
        images: Optional[List[str]] = None
    ) -> str:
        # If images provided, force capability to vision
        if images and capability == "general":
            capability = "vision"

        model = self.select_model_for_capability(capability)
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        user_msg: Dict[str, Any] = {"role": "user", "content": prompt}
        if images:
            user_msg["images"] = images
        messages.append(user_msg)

        num_ctx = int(os.getenv("OLLAMA_NUM_CTX", "32768"))
        # Coding requests need more time: 7B model on CPU takes 2-5 min for large files
        if capability == "coding":
            timeout_sec = float(os.getenv("OLLAMA_TIMEOUT_CODING", "600.0"))
        else:
            timeout_sec = float(os.getenv("OLLAMA_TIMEOUT", "120.0"))

        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "num_ctx": num_ctx
            }
        }

        try:
            r = httpx.post(f"{self.ollama_url}/api/chat", json=payload, timeout=timeout_sec)
            if r.status_code == 200:
                text = r.json().get("message", {}).get("content", "").strip()
                # Guard: never return an empty string — clients reject empty content
                if not text:
                    text = "(The model returned an empty response. Please try again.)"
                return text
            # Non-200 but reachable — return structured message, not empty
            return (
                f"The AI model responded with status {r.status_code}. "
                f"Please check that Ollama is running and the model '{model}' is available."
            )
        except Exception as e:
            log.warning(f"[CapabilitySelector] Ollama unreachable: {e}")
            # Ollama is offline — return a friendly, non-empty offline message
            return (
                "The local AI model (Ollama) is currently offline or unreachable. "
                "Please start Ollama and ensure a model is loaded, then try again. "
                f"(Attempted model: {model})"
            )

# Singleton
capability_selector = CapabilityModelSelector()

