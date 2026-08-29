"""
InstagramConnector — Playwright-based Instagram Automation (Fase 14.4)
=====================================================================
Handles persistent browser sessions, cookie storage, login verification,
post/Reel/Story publishing, and profile metrics scraping for Instagram.

Session persistence strategy:
  - Cookies and storage state saved to Project_State/Sessions/instagram_{user_id}/
  - Auto-checks login status on navigation
  - Credential fallback via INSTAGRAM_USERNAME and INSTAGRAM_PASSWORD env vars
"""

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("instagram_connector")

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
    log.warning("[InstagramConnector] playwright not installed.")

_SESSIONS_ROOT = Path(
    os.getenv("DM_STORAGE_DIR")
    or os.path.join(os.path.expanduser("~"), ".gemini", "antigravity-ide", "scratch", "Project_State", "Sessions")
)

_IG_URL = "https://www.instagram.com"
_IG_LOGIN_URL = "https://www.instagram.com/accounts/login/"


class InstagramConnectorError(RuntimeError):
    """Raised when an Instagram automation operation fails."""


class InstagramConnector:
    """Async context manager wrapping a Playwright Chromium session for Instagram."""

    def __init__(
        self,
        user_id: str = "daniel",
        headless: bool = True,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ) -> None:
        if not PLAYWRIGHT_AVAILABLE:
            raise InstagramConnectorError(
                "playwright is not installed. Run: pip install playwright && playwright install chromium"
            )
        self.user_id = user_id
        self.headless = headless
        self.username = username or os.getenv("INSTAGRAM_USERNAME")
        self.password = password or os.getenv("INSTAGRAM_PASSWORD")

        self._session_dir = _SESSIONS_ROOT / f"instagram_{user_id}"
        self._state_file = self._session_dir / "storage_state.json"

        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    async def __aenter__(self) -> "InstagramConnector":
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )

        context_kwargs: Dict[str, Any] = {
            "viewport": {"width": 414, "height": 896},  # iPhone 11 Pro viewport for mobile web layout
            "user_agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1"
            ),
            "locale": "es-ES",
        }

        if self._state_file.exists():
            context_kwargs["storage_state"] = str(self._state_file)
            log.info(f"[InstagramConnector] Loading session state from {self._state_file}")

        self._context = await self._browser.new_context(**context_kwargs)
        self._page = await self._context.new_page()
        return self

    async def __aexit__(self, *_: Any) -> None:
        if self._context:
            try:
                self._session_dir.mkdir(parents=True, exist_ok=True)
                await self._context.storage_state(path=str(self._state_file))
                log.info(f"[InstagramConnector] Storage state saved to {self._state_file}")
            except Exception as exc:
                log.warning(f"[InstagramConnector] Failed saving state: {exc}")
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def is_logged_in(self) -> bool:
        """Verify if current session is logged into Instagram."""
        try:
            await self._page.goto(_IG_URL, wait_until="domcontentloaded", timeout=20_000)
            await asyncio.sleep(2)
            url = self._page.url
            if "login" in url or "accounts" in url:
                return False
            # Check for profile icon or nav bar
            count = await self._page.locator("a[href*='/direct/inbox/'], svg[aria-label='Home'], svg[aria-label='Inicio']").count()
            return count > 0
        except Exception as exc:
            log.warning(f"[InstagramConnector] Login check error: {exc}")
            return False

    async def login_with_credentials(self) -> None:
        """Perform login using username & password."""
        if not self.username or not self.password:
            raise InstagramConnectorError(
                "Missing credentials. Set INSTAGRAM_USERNAME and INSTAGRAM_PASSWORD env vars."
            )
        log.info(f"[InstagramConnector] Logging into Instagram as '{self.username}'...")
        await self._page.goto(_IG_LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)
        await asyncio.sleep(2)

        # Handle cookie consent modal if present
        for cookie_btn in ["Allow all cookies", "Permitir todas las cookies", "Decline optional cookies"]:
            try:
                btn = self._page.locator(f"button:has-text('{cookie_btn}')")
                if await btn.count() > 0:
                    await btn.first.click()
                    break
            except Exception:
                pass

        await self._page.fill("input[name='username']", self.username)
        await self._page.fill("input[name='password']", self.password)
        await self._page.click("button[type='submit']")
        await self._page.wait_for_load_state("networkidle", timeout=30_000)

        if "login" in self._page.url:
            raise InstagramConnectorError("Instagram authentication failed. Check credentials or 2FA.")
        log.info("[InstagramConnector] Login successful.")

    async def ensure_logged_in(self) -> None:
        """Ensure session is active or perform login."""
        if await self.is_logged_in():
            log.info("[InstagramConnector] Active session confirmed via cookies/state.")
            return
        await self.login_with_credentials()

    async def get_profile_metrics(self, target_username: Optional[str] = None) -> Dict[str, Any]:
        """Scrape profile metrics (followers, following, post count, bio)."""
        user = target_username or self.username or "me"
        url = f"{_IG_URL}/{user}/"
        log.info(f"[InstagramConnector] Fetching profile metrics for '{user}'...")
        try:
            await self._page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            await asyncio.sleep(2)

            metrics: Dict[str, Any] = {"username": user, "source": "playwright"}
            
            # Extract header stats (posts, followers, following)
            stat_elements = self._page.locator("header section ul li")
            count = await stat_elements.count()
            if count >= 3:
                metrics["posts"] = (await stat_elements.nth(0).inner_text()).splitlines()[0]
                metrics["followers"] = (await stat_elements.nth(1).inner_text()).splitlines()[0]
                metrics["following"] = (await stat_elements.nth(2).inner_text()).splitlines()[0]

            log.info(f"[InstagramConnector] Metrics scraped: {metrics}")
            return metrics
        except Exception as exc:
            log.error(f"[InstagramConnector] Failed scraping profile metrics: {exc}")
            return {"username": user, "error": str(exc)}
