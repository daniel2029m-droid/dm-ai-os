"""
FacebookConnector — Playwright-based Facebook Automation (Fase 14.2)
====================================================================
Handles persistent browser session, authentication, content publishing
and basic page metrics collection for the FacebookSpecialist.

Session persistence strategy:
  - Browser context is stored in Project_State/Sessions/facebook_{user_id}/
  - On first run: navigates to Facebook, waits for manual login, then saves cookies
  - On subsequent runs: loads saved cookies, verifies session is valid
  - Falls back to credential-based login if cookies are expired

Usage:
    connector = FacebookConnector(user_id="daniel")
    async with connector:
        await connector.ensure_logged_in()
        post_id = await connector.publish_post(message="Hello!", image_path=None)
        metrics = await connector.get_page_metrics(page_id="me")
"""

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

log = logging.getLogger("facebook_connector")

# ---------------------------------------------------------------------------
# Optional Playwright import — fail gracefully when not installed
# ---------------------------------------------------------------------------
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
    log.warning(
        "[FacebookConnector] playwright not installed. "
        "Run: pip install playwright && playwright install chromium"
    )


_SESSIONS_ROOT = Path(
    os.getenv("DM_STORAGE_DIR")
    or os.path.join(os.path.expanduser("~"), ".gemini", "antigravity-ide", "scratch", "Project_State", "Sessions")
)

_FB_URL = "https://www.facebook.com"
_FB_LOGIN_URL = "https://www.facebook.com/login"
_FB_HOME_CHECK = "https://www.facebook.com/"


class FacebookConnectorError(RuntimeError):
    """Raised when a Facebook automation step fails unrecoverably."""


class FacebookConnector:
    """
    Async context-manager that wraps a persistent Playwright Chromium session
    pointed at Facebook.
    """

    def __init__(
        self,
        user_id: str = "daniel",
        headless: bool = True,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ) -> None:
        if not PLAYWRIGHT_AVAILABLE:
            raise FacebookConnectorError(
                "playwright is not installed. Run: pip install playwright && playwright install chromium"
            )
        self.user_id = user_id
        self.headless = headless
        self.username = username or os.getenv("FACEBOOK_USERNAME")
        self.password = password or os.getenv("FACEBOOK_PASSWORD")

        self._session_dir = _SESSIONS_ROOT / f"facebook_{user_id}"
        self._cookies_file = self._session_dir / "cookies.json"

        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    # ── Async context manager ────────────────────────────────────────────────

    async def __aenter__(self) -> "FacebookConnector":
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        self._context = await self._browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            locale="es-ES",
        )
        await self._load_cookies()
        self._page = await self._context.new_page()
        log.info(f"[FacebookConnector:{self.user_id}] Browser context ready.")
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self._save_cookies()
        if self._page and not self._page.is_closed():
            await self._page.close()
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        log.info(f"[FacebookConnector:{self.user_id}] Browser closed, session saved.")

    # ── Session persistence ──────────────────────────────────────────────────

    async def _load_cookies(self) -> None:
        if self._cookies_file.exists():
            try:
                cookies = json.loads(self._cookies_file.read_text(encoding="utf-8"))
                await self._context.add_cookies(cookies)
                log.info(f"[FacebookConnector] Loaded {len(cookies)} cookies from {self._cookies_file}")
            except Exception as exc:
                log.warning(f"[FacebookConnector] Failed to load cookies: {exc}")

    async def _save_cookies(self) -> None:
        if self._context is None:
            return
        try:
            self._session_dir.mkdir(parents=True, exist_ok=True)
            cookies = await self._context.cookies()
            self._cookies_file.write_text(
                json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            log.info(f"[FacebookConnector] Saved {len(cookies)} cookies to {self._cookies_file}")
        except Exception as exc:
            log.warning(f"[FacebookConnector] Failed to save cookies: {exc}")

    # ── Login ────────────────────────────────────────────────────────────────

    async def is_logged_in(self) -> bool:
        """Return True if the current session appears to be authenticated."""
        try:
            await self._page.goto(_FB_HOME_CHECK, wait_until="domcontentloaded", timeout=20_000)
            # Facebook redirects unauthenticated users back to /login or shows login wall
            url = self._page.url
            if "login" in url or "checkpoint" in url:
                return False
            # Check for a known authenticated element (profile / messenger icon)
            logged_in = await self._page.locator("[data-testid='blue_bar_profile_link']").count()
            if logged_in == 0:
                # Fallback: look for the main feed nav bar
                logged_in = await self._page.locator("div[role='navigation']").count()
            return logged_in > 0
        except Exception as exc:
            log.warning(f"[FacebookConnector] is_logged_in check failed: {exc}")
            return False

    async def _login_with_credentials(self) -> None:
        """Attempt programmatic login using USERNAME/PASSWORD environment variables."""
        if not self.username or not self.password:
            raise FacebookConnectorError(
                "No credentials available. Set FACEBOOK_USERNAME and FACEBOOK_PASSWORD "
                "environment variables or provide them in the payload."
            )
        log.info(f"[FacebookConnector] Logging in as '{self.username}'...")
        await self._page.goto(_FB_LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)
        await self._page.fill("#email", self.username)
        await self._page.fill("#pass", self.password)
        await self._page.click("[name='login']")
        await self._page.wait_for_load_state("networkidle", timeout=30_000)
        if "login" in self._page.url:
            raise FacebookConnectorError(
                "Login failed. Check your credentials or handle 2FA manually by setting "
                "headless=False and using ensure_logged_in() in interactive mode."
            )
        log.info("[FacebookConnector] Login successful.")

    async def ensure_logged_in(self) -> None:
        """
        Ensure the browser session is authenticated.
        Tries cookie session first, falls back to credential login.
        Raises FacebookConnectorError if neither method works.
        """
        if await self.is_logged_in():
            log.info("[FacebookConnector] Session already authenticated (cookies valid).")
            return
        log.info("[FacebookConnector] Session expired or not found — attempting credential login.")
        await self._login_with_credentials()
        if not await self.is_logged_in():
            raise FacebookConnectorError(
                "Could not authenticate with Facebook. "
                "If 2FA is enabled, set headless=False and log in manually once."
            )

    # ── Publishing ───────────────────────────────────────────────────────────

    async def publish_post(
        self,
        message: str,
        image_path: Optional[str] = None,
        page_id: str = "me",
    ) -> Dict[str, Any]:
        """
        Publish a text (+ optional image) post to the authenticated profile or page.

        Args:
            message:    Post text content.
            image_path: Local path to an image file to attach, or None.
            page_id:    Facebook page ID or 'me' for personal profile.

        Returns:
            Dict with 'status' and 'post_url' (best-effort).
        """
        target_url = (
            f"{_FB_URL}/{page_id}" if page_id != "me" else _FB_HOME_CHECK
        )
        log.info(f"[FacebookConnector] Navigating to {target_url} to publish post.")
        await self._page.goto(target_url, wait_until="domcontentloaded", timeout=30_000)

        # Click on "What's on your mind?" composer
        composer_selectors = [
            "[data-testid='status-attachment-mentions-input']",
            "div[role='button'][tabindex='0'][aria-label*='mente']",
            "div[data-testid='react-composer-root']",
        ]
        clicked = False
        for sel in composer_selectors:
            try:
                el = self._page.locator(sel).first
                if await el.count() > 0:
                    await el.click(timeout=5_000)
                    clicked = True
                    break
            except Exception:
                continue
        if not clicked:
            raise FacebookConnectorError(
                "Could not locate the Facebook post composer. "
                "The page layout may have changed — update composer_selectors."
            )

        await asyncio.sleep(1)
        await self._page.keyboard.type(message, delay=30)

        # Optionally attach image
        if image_path and Path(image_path).exists():
            try:
                photo_btn_selectors = [
                    "div[aria-label='Photo/video']",
                    "div[aria-label='Foto/video']",
                    "[data-testid='photo-attachment-button']",
                ]
                for sel in photo_btn_selectors:
                    try:
                        btn = self._page.locator(sel).first
                        if await btn.count() > 0:
                            await btn.click(timeout=5_000)
                            break
                    except Exception:
                        continue
                async with self._page.expect_file_chooser() as fc_info:
                    await self._page.locator("input[type='file']").first.click()
                file_chooser = await fc_info.value
                await file_chooser.set_files(image_path)
                await asyncio.sleep(2)
            except Exception as exc:
                log.warning(f"[FacebookConnector] Image attach failed (continuing text-only): {exc}")

        # Submit
        post_btn_selectors = [
            "[data-testid='react-composer-post-button']",
            "div[aria-label='Post'][role='button']",
            "div[aria-label='Publicar'][role='button']",
        ]
        for sel in post_btn_selectors:
            try:
                btn = self._page.locator(sel).first
                if await btn.count() > 0:
                    await btn.click(timeout=10_000)
                    break
            except Exception:
                continue

        await self._page.wait_for_load_state("networkidle", timeout=20_000)
        post_url = self._page.url
        log.info(f"[FacebookConnector] Post published. URL={post_url}")
        return {"status": "published", "post_url": post_url, "post_id": None}

    # ── Analytics / Metrics ──────────────────────────────────────────────────

    async def get_page_metrics(self, page_id: str = "me") -> Dict[str, Any]:
        """
        Navigate to Facebook Page Insights and scrape basic public metrics.
        Returns a dict with follower count, likes, reach (when available).
        """
        insights_url = f"{_FB_URL}/{page_id}/insights/"
        log.info(f"[FacebookConnector] Fetching insights from {insights_url}")
        try:
            await self._page.goto(insights_url, wait_until="domcontentloaded", timeout=30_000)
            await asyncio.sleep(2)

            # Attempt to extract follower count (selector varies by page type)
            metrics: Dict[str, Any] = {"page_id": page_id, "source": "playwright_scrape"}

            # Followers / Likes
            for label in ["Followers", "Seguidores", "Likes", "Me gusta"]:
                try:
                    el = self._page.locator(f"text={label}").first
                    if await el.count() > 0:
                        parent = el.locator("..").locator("..")
                        count_el = parent.locator("span").first
                        count_text = await count_el.inner_text(timeout=3_000)
                        metrics[label.lower().replace(" ", "_")] = count_text.strip()
                except Exception:
                    pass

            log.info(f"[FacebookConnector] Metrics collected: {metrics}")
            return metrics
        except Exception as exc:
            log.error(f"[FacebookConnector] get_page_metrics failed: {exc}")
            return {"page_id": page_id, "error": str(exc)}
