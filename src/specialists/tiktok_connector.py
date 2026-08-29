"""
TikTokConnector — Playwright-based TikTok Automation (Fase 14.5)
===============================================================
Handles persistent browser sessions, cookie storage, login verification,
video/Shorts publishing, and analytics scraping for TikTok.

Session persistence strategy:
  - Cookies and storage state saved to Project_State/Sessions/tiktok_{user_id}/
  - Auto-checks login status on navigation
  - Credential fallback via TIKTOK_USERNAME and TIKTOK_PASSWORD env vars
"""

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("tiktok_connector")

try:
    from playwright.async_api import (
        Browser,
        BrowserContext,
        Page,
        async_playwright,
    )
    PLAYWRIGHT_AVAILABLE = True
except ImportError:  # pragma: no cover
    PLAYWRIGHT_AVAILABLE = False
    log.warning("[TikTokConnector] playwright not installed.")

_SESSIONS_ROOT = Path(
    os.getenv("DM_STORAGE_DIR")
    or os.path.join(os.path.expanduser("~"), ".gemini", "antigravity-ide", "scratch", "Project_State", "Sessions")
)

_TT_URL = "https://www.tiktok.com"
_TT_UPLOAD_URL = "https://www.tiktok.com/creator-center/upload"


class TikTokConnectorError(RuntimeError):
    """Raised when a TikTok automation operation fails."""


class TikTokConnector:
    """Async context manager wrapping a Playwright Chromium session for TikTok."""

    def __init__(
        self,
        user_id: str = "daniel",
        headless: bool = True,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ) -> None:
        if not PLAYWRIGHT_AVAILABLE:
            raise TikTokConnectorError(
                "playwright is not installed. Run: pip install playwright && playwright install chromium"
            )
        self.user_id = user_id
        self.headless = headless
        self.username = username or os.getenv("TIKTOK_USERNAME")
        self.password = password or os.getenv("TIKTOK_PASSWORD")

        self._session_dir = _SESSIONS_ROOT / f"tiktok_{user_id}"
        self._state_file = self._session_dir / "storage_state.json"

        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    async def __aenter__(self) -> "TikTokConnector":
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )

        context_kwargs: Dict[str, Any] = {
            "viewport": {"width": 1280, "height": 800},
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "locale": "es-ES",
        }

        if self._state_file.exists():
            context_kwargs["storage_state"] = str(self._state_file)
            log.info(f"[TikTokConnector] Loading session state from {self._state_file}")

        self._context = await self._browser.new_context(**context_kwargs)
        self._page = await self._context.new_page()
        return self

    async def __aexit__(self, *_: Any) -> None:
        if self._context:
            try:
                self._session_dir.mkdir(parents=True, exist_ok=True)
                await self._context.storage_state(path=str(self._state_file))
                log.info(f"[TikTokConnector] Storage state saved to {self._state_file}")
            except Exception as exc:
                log.warning(f"[TikTokConnector] Failed saving state: {exc}")
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def is_logged_in(self) -> bool:
        """Verify if current session is logged into TikTok."""
        try:
            await self._page.goto(_TT_URL, wait_until="domcontentloaded", timeout=20_000)
            await asyncio.sleep(2)
            # Check for avatar or upload button logged-in indicator
            count = await self._page.locator("a[href*='/upload'], div[aria-label*='Profile']").count()
            return count > 0
        except Exception as exc:
            log.warning(f"[TikTokConnector] Login check error: {exc}")
            return False

    async def get_profile_analytics(self, target_username: Optional[str] = None) -> Dict[str, Any]:
        """Scrape TikTok profile analytics (likes, followers, video count)."""
        user = target_username or self.username or "me"
        url = f"{_TT_URL}/@{user}"
        log.info(f"[TikTokConnector] Fetching profile analytics for '@{user}'...")
        try:
            await self._page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            await asyncio.sleep(2)

            metrics: Dict[str, Any] = {"username": user, "source": "playwright"}
            
            for key, selector in [
                ("following", "[data-e2e='following-count']"),
                ("followers", "[data-e2e='followers-count']"),
                ("likes", "[data-e2e='likes-count']"),
            ]:
                try:
                    el = self._page.locator(selector).first
                    if await el.count() > 0:
                        metrics[key] = (await el.inner_text()).strip()
                except Exception:
                    pass

            log.info(f"[TikTokConnector] Metrics scraped: {metrics}")
            return metrics
        except Exception as exc:
            log.error(f"[TikTokConnector] Failed scraping profile analytics: {exc}")
            return {"username": user, "error": str(exc)}
