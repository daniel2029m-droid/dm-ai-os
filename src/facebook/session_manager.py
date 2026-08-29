"""
Facebook Session Manager
========================
Persistent login state via Playwright storage_state + encrypted-at-rest cookie files.
Supports automatic session recovery and validity checks.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .database import FacebookDatabase, facebook_db
from .paths import get_sessions_dir

log = logging.getLogger("facebook.session_manager")

# Domains that indicate a live Facebook session
_FB_COOKIE_NAMES = {"c_user", "xs", "datr", "sb", "fr"}


class FacebookSessionManager:
    """Manages persistent Facebook login sessions for Playwright automation."""

    def __init__(self, db: Optional[FacebookDatabase] = None, sessions_dir: Optional[Path] = None):
        self.db = db or facebook_db
        self.sessions_dir = sessions_dir or get_sessions_dir()
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def _state_path(self, account_key: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in account_key)
        return self.sessions_dir / f"{safe}_storage_state.json"

    def save_session(
        self,
        account_key: str,
        storage_state: Dict[str, Any],
        *,
        page_id: Optional[str] = None,
        page_name: Optional[str] = None,
        user_agent: Optional[str] = None,
        mark_login: bool = True,
    ) -> Dict[str, Any]:
        """Persist storage_state to disk and database."""
        path = self._state_path(account_key)
        path.write_text(
            json.dumps(storage_state, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        cookies = storage_state.get("cookies") or []
        is_valid = self._cookies_look_valid(cookies)
        sid = self.db.upsert_session(
            account_key=account_key,
            storage_state=storage_state,
            cookies=cookies,
            page_id=page_id,
            page_name=page_name,
            user_agent=user_agent,
            is_valid=is_valid,
            mark_login=mark_login,
        )
        log.info(
            "[SessionManager] Saved session account=%s id=%s valid=%s path=%s",
            account_key, sid, is_valid, path.name,
        )
        return {
            "status": "success",
            "account_key": account_key,
            "session_id": sid,
            "is_valid": is_valid,
            "path": str(path),
            "cookie_count": len(cookies),
        }

    def load_session(self, account_key: str) -> Optional[Dict[str, Any]]:
        """Load storage_state preferring disk file, falling back to DB."""
        path = self._state_path(account_key)
        if path.exists():
            try:
                state = json.loads(path.read_text(encoding="utf-8"))
                record = self.db.get_session(account_key) or {}
                return {
                    "account_key": account_key,
                    "storage_state": state,
                    "is_valid": record.get("is_valid", self._cookies_look_valid(state.get("cookies", []))),
                    "page_id": record.get("page_id"),
                    "page_name": record.get("page_name"),
                    "user_agent": record.get("user_agent"),
                    "source": "disk",
                }
            except (json.JSONDecodeError, OSError) as e:
                log.warning("[SessionManager] Disk session corrupt for %s: %s", account_key, e)

        record = self.db.get_session(account_key)
        if not record:
            return None
        state = record.get("storage_state") or {"cookies": record.get("cookies_json") or []}
        # Rehydrate disk cache
        try:
            path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
        return {
            "account_key": account_key,
            "storage_state": state,
            "is_valid": record.get("is_valid", False),
            "page_id": record.get("page_id"),
            "page_name": record.get("page_name"),
            "user_agent": record.get("user_agent"),
            "source": "database",
        }

    def has_valid_session(self, account_key: str) -> bool:
        session = self.load_session(account_key)
        if not session:
            return False
        if not session.get("is_valid"):
            return False
        return self._cookies_look_valid(session.get("storage_state", {}).get("cookies", []))

    def invalidate(self, account_key: str, reason: str = "session_expired") -> None:
        self.db.invalidate_session(account_key, reason)
        log.warning("[SessionManager] Invalidated session %s: %s", account_key, reason)

    def mark_used(self, account_key: str) -> None:
        record = self.db.get_session(account_key)
        if not record:
            return
        self.db.upsert_session(
            account_key=account_key,
            storage_state=record.get("storage_state") or {},
            cookies=record.get("cookies_json") or [],
            page_id=record.get("page_id"),
            page_name=record.get("page_name"),
            user_agent=record.get("user_agent"),
            is_valid=bool(record.get("is_valid")),
            mark_login=False,
        )

    def export_cookies(self, account_key: str) -> List[Dict[str, Any]]:
        session = self.load_session(account_key)
        if not session:
            return []
        return list(session.get("storage_state", {}).get("cookies") or [])

    def import_cookies(
        self,
        account_key: str,
        cookies: List[Dict[str, Any]],
        *,
        page_id: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Import raw cookie list into a storage_state."""
        # Normalize cookie fields for Playwright
        normalized = []
        for c in cookies:
            entry = {
                "name": c.get("name"),
                "value": c.get("value"),
                "domain": c.get("domain") or ".facebook.com",
                "path": c.get("path") or "/",
            }
            if c.get("expires") is not None:
                entry["expires"] = c["expires"]
            if c.get("httpOnly") is not None:
                entry["httpOnly"] = c["httpOnly"]
            if c.get("secure") is not None:
                entry["secure"] = c["secure"]
            if c.get("sameSite"):
                entry["sameSite"] = c["sameSite"]
            if entry["name"] and entry["value"] is not None:
                normalized.append(entry)
        state = {"cookies": normalized, "origins": []}
        return self.save_session(
            account_key,
            state,
            page_id=page_id,
            user_agent=user_agent,
            mark_login=True,
        )

    def list_accounts(self) -> List[str]:
        """List account keys that have session files or DB rows."""
        keys = set()
        for p in self.sessions_dir.glob("*_storage_state.json"):
            keys.add(p.name.replace("_storage_state.json", ""))
        # Also scan DB via direct query
        try:
            with self.db._connect() as conn:
                rows = conn.execute("SELECT account_key FROM fb_sessions").fetchall()
                for r in rows:
                    keys.add(r["account_key"])
        except Exception:
            pass
        return sorted(keys)

    @staticmethod
    def _cookies_look_valid(cookies: List[Dict[str, Any]]) -> bool:
        if not cookies:
            return False
        names = {c.get("name") for c in cookies if isinstance(c, dict)}
        # c_user + xs is the classic authenticated pair
        if "c_user" in names and "xs" in names:
            # Check expiry if present
            now = time.time()
            for c in cookies:
                if c.get("name") in ("c_user", "xs"):
                    exp = c.get("expires")
                    if exp is not None and exp > 0 and exp < now:
                        return False
            return True
        # Partial overlap still may work for some Business Suite flows
        overlap = names & _FB_COOKIE_NAMES
        return len(overlap) >= 2

    def session_health(self, account_key: str) -> Dict[str, Any]:
        session = self.load_session(account_key)
        if not session:
            return {
                "account_key": account_key,
                "status": "missing",
                "is_valid": False,
                "message": "No session stored. Login required.",
            }
        cookies = session.get("storage_state", {}).get("cookies") or []
        valid = self._cookies_look_valid(cookies) and session.get("is_valid", False)
        return {
            "account_key": account_key,
            "status": "valid" if valid else "expired",
            "is_valid": valid,
            "cookie_count": len(cookies),
            "page_id": session.get("page_id"),
            "page_name": session.get("page_name"),
            "source": session.get("source"),
            "message": "Session ready" if valid else "Session expired or incomplete. Re-login required.",
        }


facebook_session_manager = FacebookSessionManager()
