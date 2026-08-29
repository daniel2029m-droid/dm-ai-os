"""
YouTubeConnector — Playwright-based YouTube & YouTube Studio Automation (Fase 14.6)
==================================================================================
Handles persistent browser sessions, cookie storage, Studio login verification,
Shorts / Video upload automation, and channel analytics scraping.

Session persistence strategy:
  - Cookies and storage state saved to Project_State/Sessions/youtube_{user_id}/
  - Auto-checks Google / YouTube login state
"""

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("youtube_connector")

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
    log.warning("[YouTubeConnector] playwright not installed.")

_SESSIONS_ROOT = Path(
    os.getenv("DM_STORAGE_DIR")
    or os.path.join(os.path.expanduser("~"), ".gemini", "antigravity-ide", "scratch", "Project_State", "Sessions")
)

_YT_URL = "https://www.youtube.com"
_YT_STUDIO_URL = "https://studio.youtube.com"


class YouTubeConnectorError(RuntimeError):
    """Raised when a YouTube automation operation fails."""


class YouTubeConnector:
    """Async context manager wrapping a Playwright Chromium session for YouTube."""

    def __init__(
        self,
        user_id: str = "daniel",
        headless: bool = True,
        channel_handle: Optional[str] = None,
    ) -> None:
        if not PLAYWRIGHT_AVAILABLE:
            raise YouTubeConnectorError(
                "playwright is not installed. Run: pip install playwright && playwright install chromium"
            )
        self.user_id = user_id
        self.headless = headless
        self.channel_handle = channel_handle or os.getenv("YOUTUBE_CHANNEL_HANDLE")

        self._session_dir = _SESSIONS_ROOT / f"youtube_{user_id}"
        self._state_file = self._session_dir / "storage_state.json"

        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    async def __aenter__(self) -> "YouTubeConnector":
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )

        context_kwargs: Dict[str, Any] = {
            "viewport": {"width": 1440, "height": 900},
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "locale": "es-ES",
        }

        if self._state_file.exists():
            context_kwargs["storage_state"] = str(self._state_file)
            log.info(f"[YouTubeConnector] Loading session state from {self._state_file}")

        self._context = await self._browser.new_context(**context_kwargs)
        self._page = await self._context.new_page()
        return self

    async def __aexit__(self, *_: Any) -> None:
        if self._context:
            try:
                self._session_dir.mkdir(parents=True, exist_ok=True)
                await self._context.storage_state(path=str(self._state_file))
                log.info(f"[YouTubeConnector] Storage state saved to {self._state_file}")
            except Exception as exc:
                log.warning(f"[YouTubeConnector] Failed saving state: {exc}")
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def is_logged_in(self) -> bool:
        """Verify if current session is logged into YouTube / Google."""
        try:
            await self._page.goto(_YT_STUDIO_URL, wait_until="domcontentloaded", timeout=20_000)
            await asyncio.sleep(2)
            url = self._page.url
            if "accounts.google.com" in url or "signin" in url:
                return False
            # Check for YouTube Studio dashboard element
            count = await self._page.locator("#avatar-btn, ytm-studio-header, tp-yt-paper-icon-button[icon='yt-icons:create']").count()
            return count > 0
        except Exception as exc:
            log.warning(f"[YouTubeConnector] Login check error: {exc}")
            return False

    async def get_channel_metrics(self, handle: Optional[str] = None) -> Dict[str, Any]:
        """Scrape public channel metrics (subscribers, video count)."""
        target = handle or self.channel_handle or "@youtube"
        if not target.startswith("@"):
            target = f"@{target}"
        url = f"{_YT_URL}/{target}"
        log.info(f"[YouTubeConnector] Fetching channel metrics for '{target}'...")
        try:
            await self._page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            await asyncio.sleep(2)

            metrics: Dict[str, Any] = {"handle": target, "source": "playwright"}
            
            # Extract subscriber count and video count from channel header meta
            for selector in [
                "yt-formatted-string#subscriber-count",
                "yt-formatted-string#videos-count",
                ".header-content .yt-core-attributed-string",
            ]:
                try:
                    elements = self._page.locator(selector)
                    count = await elements.count()
                    for i in range(count):
                        txt = (await elements.nth(i).inner_text()).strip()
                        if "subscriptor" in txt.lower() or "subscriber" in txt.lower():
                            metrics["subscribers"] = txt
                        elif "video" in txt.lower():
                            metrics["videos"] = txt
                except Exception:
                    pass

            log.info(f"[YouTubeConnector] Metrics scraped: {metrics}")
            return metrics
        except Exception as exc:
            log.error(f"[YouTubeConnector] Failed scraping channel metrics: {exc}")
            return {"handle": target, "error": str(exc)}
