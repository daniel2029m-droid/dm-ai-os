"""
Dynamic Model Selector & Provider Abstraction.
Probes local inference backends (Ollama, llama.cpp, LM Studio) and dynamically
selects the best available model based on priority:
1. Bonsai 27B 1-bit
2. Qwen 3
3. Qwen 2.5 (qwen2.5:1.5b, qwen2.5:0.5b)
4. Ultra-light fallback models
"""

import httpx
import logging
import json
import os
from typing import Dict, Any, List, Optional

log = logging.getLogger("model_selector")

PRIORITY_CASCADE = [
    {"name_pattern": "qwen2.5-coder:7b", "display": "Qwen 2.5 Coder 7B"},
    {"name_pattern": "qwen2.5-coder", "display": "Qwen 2.5 Coder"},
    {"name_pattern": "bonsai", "display": "Bonsai 27B 1-bit"},
    {"name_pattern": "qwen3", "display": "Qwen 3"},
    {"name_pattern": "qwen2.5:1.5b", "display": "Qwen 2.5 1.5B"},
    {"name_pattern": "qwen2.5:0.5b", "display": "Qwen 2.5 0.5B"},
    {"name_pattern": "qwen2.5", "display": "Qwen 2.5 (Generic)"},
]

class DynamicModelSelector:
    def __init__(self, ollama_url: str = "http://localhost:11434"):
        self.ollama_url = ollama_url.rstrip("/")
        self.active_model: Optional[str] = None
        self.available_models: List[str] = []

    def probe_ollama_models(self) -> List[str]:
        """Fetch list of models loaded into local Ollama."""
        try:
            r = httpx.get(f"{self.ollama_url}/api/tags", timeout=5)
            if r.status_code == 200:
                models_data = r.json().get("models", [])
                self.available_models = [m.get("name", "") for m in models_data]
                log.info(f"[ModelSelector] Ollama available models: {self.available_models}")
                return self.available_models
        except Exception as e:
            log.warning(f"[ModelSelector] Could not query Ollama at {self.ollama_url}: {e}")
        return []

    def select_best_model(self) -> str:
        """Select highest priority model available on system."""
        installed = self.probe_ollama_models()

        for candidate in PRIORITY_CASCADE:
            pattern = candidate["name_pattern"]
            for m in installed:
                if pattern.lower() in m.lower():
                    self.active_model = m
                    log.info(f"[ModelSelector] Selected active model: '{m}' ({candidate['display']})")
                    return m

        # Fallback if installed list not empty
        if installed:
            self.active_model = installed[0]
            log.warning(f"[ModelSelector] No priority match. Fallback to: '{installed[0]}'")
            return installed[0]

        # Default static fallback
        self.active_model = "qwen2.5:1.5b"
        log.warning(f"[ModelSelector] Default fallback model: '{self.active_model}'")
        return self.active_model

    def chat_completion(self, messages: List[Dict[str, str]], system_prompt: str = None, temperature: float = 0.7) -> str:
        """Provider-agnostic chat completion request."""
        model = self.active_model or self.select_best_model()
        
        all_messages = []
        if system_prompt:
            all_messages.append({"role": "system", "content": system_prompt})
        all_messages.extend(messages)

        num_ctx = int(os.getenv("OLLAMA_NUM_CTX", "32768"))
        timeout_sec = float(os.getenv("OLLAMA_TIMEOUT", "120.0"))

        payload = {
            "model": model,
            "messages": all_messages,
            "stream": False,
            "options": {"temperature": temperature, "num_ctx": num_ctx}
        }

        try:
            r = httpx.post(f"{self.ollama_url}/api/chat", json=payload, timeout=timeout_sec)
            if r.status_code == 200:
                return r.json().get("message", {}).get("content", "").strip()
            else:
                log.error(f"[ModelSelector] API error {r.status_code}: {r.text}")
                return f"Error: Model request failed with status {r.status_code}"
        except Exception as e:
            log.error(f"[ModelSelector] Connection error: {e}")
            return f"Error: Local model backend unavailable ({e})"

# Singleton
model_selector = DynamicModelSelector()
