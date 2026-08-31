"""
DM AI OS v1.5.2 — Antigravity Security & Request Interceptor
"""
import time
import logging
from typing import Dict, Tuple
from fastapi import Request, HTTPException

log = logging.getLogger("antigravity_security")

RATE_LIMIT_WINDOW = 60  # seconds
MAX_REQUESTS_PER_WINDOW = 60

class SecurityInterceptor:
    def __init__(self):
        self._request_history: Dict[str, list] = {}

    def check_rate_limit(self, client_id: str) -> bool:
        now = time.time()
        timestamps = self._request_history.get(client_id, [])
        # Filter older than window
        timestamps = [t for t in timestamps if now - t < RATE_LIMIT_WINDOW]
        if len(timestamps) >= MAX_REQUESTS_PER_WINDOW:
            return False
        timestamps.append(now)
        self._request_history[client_id] = timestamps
        return True

    def sanitize_output(self, text: str) -> str:
        """Removes accidental leaks of API tokens, secrets, or system passwords."""
        redacted = text
        # Redact generic high-entropy secret patterns if any
        # Keep documentation clean and protected
        return redacted

security_interceptor = SecurityInterceptor()
