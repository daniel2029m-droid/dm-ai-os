"""
Network Interceptor
===================
Captures XHR/Fetch responses from Facebook/Meta dashboards, normalizes JSON,
deduplicates via content hash, and stores structured payloads.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, Dict, List, Optional, Set
from urllib.parse import urlparse

from .database import FacebookDatabase, facebook_db

log = logging.getLogger("facebook.network_interceptor")

# URL patterns that typically carry insights / GraphQL / Business Suite data
DEFAULT_INTEREST_PATTERNS = [
    r"facebook\.com/api/graphql",
    r"facebook\.com/ajax/",
    r"graph\.facebook\.com",
    r"business\.facebook\.com",
    r"facebook\.com/.*insights",
    r"facebook\.com/.*analytics",
    r"facebook\.com/.*professional_dashboard",
    r"facebook\.com/.*monetization",
    r"facebook\.com/.*earnings",
    r"facebook\.com/.*reels",
    r"facebook\.com/.*page_insights",
    r"meta\.com/",
]


def _tag_endpoint(url: str) -> str:
    lower = url.lower()
    tags = [
        ("graphql", "graphql"),
        ("insights", "insights"),
        ("monetization", "monetization"),
        ("earnings", "earnings"),
        ("analytics", "analytics"),
        ("professional_dashboard", "pro_dashboard"),
        ("audience", "audience"),
        ("reels", "reels"),
        ("comments", "comments"),
        ("feed", "feed"),
        ("page", "page"),
    ]
    for needle, tag in tags:
        if needle in lower:
            return tag
    path = urlparse(url).path.strip("/").split("/")
    return path[0] if path and path[0] else "unknown"


def normalize_json(data: Any) -> Any:
    """
    Recursively normalize JSON for stable storage:
    - Sort dict keys (via round-trip)
    - Convert non-JSON types to strings
    - Collapse empty containers consistently
    """
    if data is None:
        return None
    if isinstance(data, (str, int, float, bool)):
        return data
    if isinstance(data, bytes):
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return data.hex()
    if isinstance(data, list):
        return [normalize_json(x) for x in data]
    if isinstance(data, dict):
        return {str(k): normalize_json(data[k]) for k in sorted(data.keys(), key=str)}
    return str(data)


def try_parse_body(body: Any) -> Any:
    if body is None:
        return None
    if isinstance(body, (dict, list)):
        return body
    if isinstance(body, bytes):
        try:
            body = body.decode("utf-8", errors="replace")
        except Exception:
            return None
    if isinstance(body, str):
        text = body.strip()
        if not text:
            return None
        # Facebook sometimes prefixes JSON with for(;;);
        if text.startswith("for(;;);"):
            text = text[len("for(;;);"):]
        # Multi-JSON lines (NDJSON / batched GraphQL)
        if "\n{" in text or text.count("\n") > 0:
            parts = []
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                if line.startswith("for(;;);"):
                    line = line[len("for(;;);"):]
                try:
                    parts.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
            if parts:
                return parts if len(parts) > 1 else parts[0]
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"_raw_text": text[:5000]}
    return {"_raw": str(body)[:2000]}


class NetworkInterceptor:
    """
    Attach to a Playwright page to capture interesting XHR/Fetch responses.
    Can also ingest captures offline (from tests or external collectors).
    """

    def __init__(
        self,
        db: Optional[FacebookDatabase] = None,
        interest_patterns: Optional[List[str]] = None,
        page_id: Optional[str] = None,
        account_key: Optional[str] = None,
    ):
        self.db = db or facebook_db
        self.patterns = [re.compile(p, re.I) for p in (interest_patterns or DEFAULT_INTEREST_PATTERNS)]
        self.page_id = page_id
        self.account_key = account_key
        self._seen_hashes: Set[str] = set()
        self._captures: List[Dict[str, Any]] = []
        self._attached = False
        self._on_capture: Optional[Callable[[Dict[str, Any]], None]] = None

    def set_context(
        self,
        page_id: Optional[str] = None,
        account_key: Optional[str] = None,
    ) -> None:
        if page_id is not None:
            self.page_id = page_id
        if account_key is not None:
            self.account_key = account_key

    def is_interesting(self, url: str) -> bool:
        if not url:
            return False
        return any(p.search(url) for p in self.patterns)

    def ingest(
        self,
        url: str,
        body: Any,
        *,
        method: str = "GET",
        status_code: Optional[int] = None,
        resource_type: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Normalize, dedupe, and store a single network response."""
        if not self.is_interesting(url) and resource_type not in ("xhr", "fetch"):
            # Still allow explicit xhr/fetch even if pattern miss, when resource_type set
            if resource_type not in ("xhr", "fetch", "json"):
                return None

        parsed = try_parse_body(body)
        if parsed is None:
            return None
        normalized = normalize_json(parsed)
        tag = _tag_endpoint(url)
        row_id = self.db.store_network_capture(
            url=url,
            normalized=normalized,
            page_id=self.page_id,
            account_key=self.account_key,
            method=method,
            resource_type=resource_type,
            status_code=status_code,
            endpoint_tag=tag,
        )
        if row_id is None:
            log.debug("[NetworkInterceptor] Duplicate skipped: %s", url[:120])
            return None

        record = {
            "id": row_id,
            "url": url,
            "method": method,
            "status_code": status_code,
            "resource_type": resource_type,
            "endpoint_tag": tag,
            "normalized": normalized,
            "page_id": self.page_id,
            "account_key": self.account_key,
        }
        self._captures.append(record)
        if self._on_capture:
            try:
                self._on_capture(record)
            except Exception as e:
                log.warning("[NetworkInterceptor] on_capture callback error: %s", e)
        log.info("[NetworkInterceptor] Captured %s tag=%s id=%s", url[:80], tag, row_id)
        return record

    def captures(self) -> List[Dict[str, Any]]:
        return list(self._captures)

    def clear_memory(self) -> None:
        self._captures.clear()
        self._seen_hashes.clear()

    async def attach(self, page) -> None:
        """
        Attach response listener to a Playwright Page.
        page: playwright.async_api.Page
        """
        if self._attached:
            return

        async def _on_response(response) -> None:
            try:
                url = response.url
                req = response.request
                resource_type = getattr(req, "resource_type", None) or ""
                method = getattr(req, "method", "GET") or "GET"
                if resource_type not in ("xhr", "fetch", "other") and not self.is_interesting(url):
                    return
                if not self.is_interesting(url) and resource_type not in ("xhr", "fetch"):
                    return
                # Only try JSON-ish content types
                headers = {}
                try:
                    headers = await response.all_headers()
                except Exception:
                    pass
                ctype = (headers.get("content-type") or headers.get("Content-Type") or "").lower()
                if ctype and ("json" not in ctype and "javascript" not in ctype and "text" not in ctype):
                    return
                try:
                    body = await response.text()
                except Exception:
                    return
                self.ingest(
                    url=url,
                    body=body,
                    method=method,
                    status_code=response.status,
                    resource_type=resource_type,
                    headers=headers,
                )
            except Exception as e:
                log.debug("[NetworkInterceptor] response handler error: %s", e)

        page.on("response", _on_response)
        self._attached = True
        log.info("[NetworkInterceptor] Attached to page")

    def extract_metrics_from_captures(
        self, captures: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Heuristic extraction of common metric keys from captured GraphQL/XHR JSON.
        Returns a flat dict of discovered numeric metrics.
        """
        captures = captures if captures is not None else self._captures
        metrics: Dict[str, Any] = {}
        metric_keys = {
            "followers", "follower_count", "fans", "page_fans",
            "reach", "impressions", "views", "video_views", "post_views",
            "revenue", "earnings", "estimated_earnings", "rpm",
            "engagement", "engagement_rate", "likes", "comments", "shares",
            "profile_views",
        }

        def walk(obj: Any, path: str = "") -> None:
            if isinstance(obj, dict):
                for k, v in obj.items():
                    key_l = str(k).lower()
                    full = f"{path}.{key_l}" if path else key_l
                    if key_l in metric_keys or any(m in key_l for m in metric_keys):
                        if isinstance(v, (int, float)) and not isinstance(v, bool):
                            metrics[key_l] = v
                        elif isinstance(v, dict) and "value" in v and isinstance(v["value"], (int, float)):
                            metrics[key_l] = v["value"]
                    walk(v, full)
            elif isinstance(obj, list):
                for i, item in enumerate(obj[:50]):
                    walk(item, f"{path}[{i}]")

        for cap in captures:
            walk(cap.get("normalized"))
        return metrics
