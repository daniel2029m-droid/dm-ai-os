import math
import hashlib
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
import httpx

log = logging.getLogger("embedding_engine")

class EmbeddingEngine:
    def __init__(self, provider: str = "ollama", model: str = "nomic-embed-text"):
        self.provider = provider
        self.model = model
        self.host = "http://localhost:11434"
        self.dim = 768

    def generate_embedding(self, text: str) -> List[float]:
        if not text:
            return [0.0] * self.dim
            
        if self.provider == "ollama":
            try:
                resp = httpx.post(
                    f"{self.host}/api/embeddings",
                    json={"model": self.model, "prompt": text},
                    timeout=3.0
                )
                if resp.status_code == 200:
                    emb = resp.json().get("embedding")
                    if emb and isinstance(emb, list):
                        return emb
            except Exception as e:
                log.debug(f"[EmbeddingEngine] Ollama embedding fallback for '{text[:20]}...': {e}")
                
        # Deterministic pseudo-embedding fallback based on SHA-256 tokens
        return self._fallback_embedding(text)

    def _fallback_embedding(self, text: str) -> List[float]:
        words = text.lower().split()
        vector = [0.0] * self.dim
        for i, word in enumerate(words):
            h = int(hashlib.md5(word.encode()).hexdigest(), 16)
            idx = h % self.dim
            vector[idx] += 1.0 / (i + 1.0)
            
        norm = math.sqrt(sum(v * v for v in vector))
        if norm > 0:
            vector = [v / norm for v in vector]
        return vector

    @staticmethod
    def cosine_similarity(v1: List[float], v2: List[float]) -> float:
        if not v1 or not v2 or len(v1) != len(v2):
            return 0.0
        dot = sum(a * b for a, b in zip(v1, v2))
        norm1 = math.sqrt(sum(a * a for a in v1))
        norm2 = math.sqrt(sum(b * b for b in v2))
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot / (norm1 * norm2)

embedding_engine = EmbeddingEngine()
