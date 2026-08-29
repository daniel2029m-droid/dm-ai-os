"""
Facebook Connector
==================
Playwright automation for Facebook Business Suite & Professional Dashboard.

Features:
- Persistent login via storage_state
- Automatic session recovery
- Business Suite navigation
- Professional Dashboard navigation
- Infinite scroll / lazy loading helpers
- Automatic retries
- Network interception hook
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .database import FacebookDatabase, facebook_db
from .network_interceptor import NetworkInterceptor
from .ocr_extractor import FacebookOCRExtractor, facebook_ocr
from .session_manager import FacebookSessionManager, facebook_session_manager

log = logging.getLogger("facebook.connector")

BUSINESS_SUITE_URL = "https://business.facebook.com/"
PROFESSIONAL_DASHBOARD_URL = "https://www.facebook.com/{page}/professional_dashboard"
PAGE_INSIGHTS_URL = "https://www.facebook.com/{page}/insights"
REELS_URL = "https://www.facebook.com/{page}/reels_tab"
LOGIN_URL = "https://www.facebook.com/login"

DEFAULT_VIEWPORT = {"width": 1440, "height": 900}
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)
MAX_RETRIES = 3
NAV_TIMEOUT_MS = 60_000
SCROLL_PAUSE_MS = 800


class FacebookConnector:
    """
    High-level Playwright connector for Facebook/Meta creator surfaces.
    Does not auto-publish; focuses on authenticated data collection.
    """

    def __init__(
        self,
        session_manager: Optional[FacebookSessionManager] = None,
        db: Optional[FacebookDatabase] = None,
        ocr: Optional[FacebookOCRExtractor] = None,
        headless: Optional[bool] = None,
    ):
        self.session_manager = session_manager or facebook_session_manager
        self.db = db or facebook_db
        self.ocr = ocr or facebook_ocr
        if headless is None:
            headless = os.getenv("FB_HEADLESS", "true").lower() in ("1", "true", "yes")
        self.headless = headless
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._account_key: Optional[str] = None
        self._interceptor: Optional[NetworkInterceptor] = None

    @staticmethod
    def playwright_available() -> bool:
        try:
            import playwright  # noqa: F401
            return True
        except ImportError:
            return False

    async def start(
        self,
        account_key: str,
        *,
        page_id: Optional[str] = None,
        proxy: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Launch browser with restored session if available."""
        if not self.playwright_available():
            return {
                "status": "error",
                "message": "playwright is not installed. Run: pip install playwright && playwright install chromium",
            }

        from playwright.async_api import async_playwright

        self._account_key = account_key
        self._playwright = await async_playwright().start()

        launch_args: Dict[str, Any] = {
            "headless": self.headless,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        }
        if proxy:
            launch_args["proxy"] = {"server": proxy}

        self._browser = await self._playwright.chromium.launch(**launch_args)

        session = self.session_manager.load_session(account_key)
        context_kwargs: Dict[str, Any] = {
            "viewport": DEFAULT_VIEWPORT,
            "user_agent": (session or {}).get("user_agent") or DEFAULT_UA,
            "locale": "es-ES",
        }
        if session and session.get("storage_state"):
            context_kwargs["storage_state"] = session["storage_state"]

        self._context = await self._browser.new_context(**context_kwargs)
        self._page = await self._context.new_page()
        self._page.set_default_timeout(NAV_TIMEOUT_MS)

        self._interceptor = NetworkInterceptor(
            db=self.db,
            page_id=page_id or (session or {}).get("page_id"),
            account_key=account_key,
        )
        await self._interceptor.attach(self._page)

        logged_in = await self._check_logged_in()
        if logged_in:
            self.session_manager.mark_used(account_key)
            await self._persist_current_state(page_id=page_id)

        return {
            "status": "success",
            "account_key": account_key,
            "logged_in": logged_in,
            "session_restored": bool(session),
            "page_id": page_id or (session or {}).get("page_id"),
        }

    async def stop(self) -> None:
        """Close browser resources and persist session if possible."""
        try:
            if self._context and self._account_key:
                await self._persist_current_state()
        except Exception as e:
            log.debug("[Connector] persist on stop failed: %s", e)
        for closer, name in (
            (self._page, "page"),
            (self._context, "context"),
            (self._browser, "browser"),
        ):
            if closer is not None:
                try:
                    await closer.close()
                except Exception as e:
                    log.debug("[Connector] close %s: %s", name, e)
        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception:
                pass
        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None
        self._interceptor = None

    async def _persist_current_state(self, page_id: Optional[str] = None) -> None:
        if not self._context or not self._account_key:
            return
        state = await self._context.storage_state()
        self.session_manager.save_session(
            self._account_key,
            state,
            page_id=page_id,
            user_agent=DEFAULT_UA,
            mark_login=False,
        )

    async def _check_logged_in(self) -> bool:
        if not self._page:
            return False
        try:
            await self._page.goto("https://www.facebook.com/", wait_until="domcontentloaded")
            await self._page.wait_for_timeout(1500)
            url = self._page.url.lower()
            if "login" in url or "checkpoint" in url:
                return False
            # c_user cookie is the strongest signal
            cookies = await self._context.cookies()
            names = {c.get("name") for c in cookies}
            return "c_user" in names
        except Exception as e:
            log.warning("[Connector] login check failed: %s", e)
            return False

    async def ensure_session(self, account_key: str, page_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Start browser and recover session. If invalid, attempt recovery navigation.
        """
        start_res = await self.start(account_key, page_id=page_id)
        if start_res.get("status") != "success":
            return start_res
        if start_res.get("logged_in"):
            return {**start_res, "recovered": False}

        # Attempt recovery: reload storage, soft re-navigate
        recovered = await self.recover_session(account_key, page_id=page_id)
        return {
            **start_res,
            "logged_in": recovered.get("logged_in", False),
            "recovered": recovered.get("recovered", False),
            "recovery": recovered,
        }

    async def recover_session(
        self,
        account_key: str,
        page_id: Optional[str] = None,
        max_attempts: int = MAX_RETRIES,
    ) -> Dict[str, Any]:
        """Automatic session recovery with retries."""
        last_error = None
        for attempt in range(1, max_attempts + 1):
            try:
                log.info("[Connector] Session recovery attempt %s/%s", attempt, max_attempts)
                if self._page is None:
                    await self.start(account_key, page_id=page_id)

                # Soft recovery: visit home, then business suite
                await self._page.goto("https://www.facebook.com/", wait_until="domcontentloaded")
                await self._page.wait_for_timeout(1200)
                logged_in = await self._check_logged_in()
                if logged_in:
                    await self._persist_current_state(page_id=page_id)
                    return {
                        "status": "success",
                        "recovered": True,
                        "logged_in": True,
                        "attempt": attempt,
                    }

                # Try Business Suite which sometimes keeps longer sessions
                await self._retry_goto(BUSINESS_SUITE_URL)
                await self._page.wait_for_timeout(1500)
                logged_in = await self._check_logged_in()
                if logged_in:
                    await self._persist_current_state(page_id=page_id)
                    return {
                        "status": "success",
                        "recovered": True,
                        "logged_in": True,
                        "attempt": attempt,
                    }
            except Exception as e:
                last_error = str(e)
                log.warning("[Connector] recovery attempt %s failed: %s", attempt, e)
                await asyncio.sleep(1.5 * attempt)

        self.session_manager.invalidate(account_key, reason=last_error or "recovery_failed")
        return {
            "status": "login_required",
            "recovered": False,
            "logged_in": False,
            "message": "Automatic session recovery failed. Manual login required.",
            "last_error": last_error,
        }

    async def interactive_login(
        self,
        account_key: str,
        *,
        email: Optional[str] = None,
        password: Optional[str] = None,
        wait_for_manual_seconds: int = 120,
        page_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Perform login. If email/password provided, attempt form fill.
        Otherwise open login page and wait for manual completion (headed mode).
        """
        if self._page is None:
            # Force headed for manual login if no credentials
            if not email or not password:
                self.headless = False
            start = await self.start(account_key, page_id=page_id)
            if start.get("status") != "success":
                return start

        await self._retry_goto(LOGIN_URL)
        await self._page.wait_for_timeout(1000)

        if email and password:
            try:
                email_sel = 'input[name="email"], input#email, input[type="text"]'
                pass_sel = 'input[name="pass"], input#pass, input[type="password"]'
                await self._page.fill(email_sel, email, timeout=10_000)
                await self._page.fill(pass_sel, password, timeout=10_000)
                await self._page.click('button[name="login"], button[type="submit"]')
                await self._page.wait_for_timeout(4000)
            except Exception as e:
                log.warning("[Connector] auto-fill login failed: %s", e)

        # Wait until logged in or timeout (supports 2FA / checkpoint manual resolve)
        deadline = asyncio.get_event_loop().time() + wait_for_manual_seconds
        while asyncio.get_event_loop().time() < deadline:
            if await self._check_logged_in():
                await self._persist_current_state(page_id=page_id)
                state = await self._context.storage_state()
                saved = self.session_manager.save_session(
                    account_key,
                    state,
                    page_id=page_id,
                    user_agent=DEFAULT_UA,
                    mark_login=True,
                )
                return {
                    "status": "success",
                    "logged_in": True,
                    "session": saved,
                }
            await self._page.wait_for_timeout(2000)

        return {
            "status": "timeout",
            "logged_in": False,
            "message": f"Login not completed within {wait_for_manual_seconds}s",
        }

    async def _retry_goto(self, url: str, retries: int = MAX_RETRIES) -> None:
        last_err = None
        for attempt in range(1, retries + 1):
            try:
                await self._page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
                return
            except Exception as e:
                last_err = e
                log.warning("[Connector] goto %s attempt %s failed: %s", url, attempt, e)
                await asyncio.sleep(1.0 * attempt)
        raise RuntimeError(f"Failed to navigate to {url}: {last_err}")

    async def infinite_scroll(
        self,
        max_scrolls: int = 15,
        pause_ms: int = SCROLL_PAUSE_MS,
        stable_rounds: int = 3,
    ) -> Dict[str, Any]:
        """
        Scroll page to trigger lazy loading. Stops when height stabilizes
        or max_scrolls reached.
        """
        if not self._page:
            return {"status": "error", "message": "Browser not started"}

        stable = 0
        last_height = 0
        scrolls = 0
        for i in range(max_scrolls):
            height = await self._page.evaluate("document.body.scrollHeight")
            await self._page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await self._page.wait_for_timeout(pause_ms)
            # Nudge lazy loaders
            await self._page.evaluate("window.scrollBy(0, -200)")
            await self._page.wait_for_timeout(200)
            await self._page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await self._page.wait_for_timeout(pause_ms // 2)
            new_height = await self._page.evaluate("document.body.scrollHeight")
            scrolls += 1
            if new_height <= last_height:
                stable += 1
                if stable >= stable_rounds:
                    break
            else:
                stable = 0
            last_height = new_height

        return {
            "status": "success",
            "scrolls": scrolls,
            "final_height": last_height,
        }

    async def navigate_business_suite(self, page_id: Optional[str] = None) -> Dict[str, Any]:
        """Open Meta Business Suite home / insights area."""
        if not self._page:
            return {"status": "error", "message": "Browser not started"}
        if not await self._check_logged_in():
            rec = await self.recover_session(self._account_key or "default", page_id=page_id)
            if not rec.get("logged_in"):
                return {"status": "login_required", "message": "Session invalid", "recovery": rec}

        await self._retry_goto(BUSINESS_SUITE_URL)
        await self._page.wait_for_timeout(2000)
        await self.infinite_scroll(max_scrolls=5)

        ocr_result = await self.ocr.extract_from_page(self._page, label="business_suite")
        net_metrics = self._interceptor.extract_metrics_from_captures() if self._interceptor else {}
        metrics = self.ocr.normalize_and_merge(ocr_result.get("metrics") or {}, net_metrics)

        if page_id and metrics:
            self.db.store_profile_insight(page_id, {**metrics, "snapshot_at": _now()}, source="business_suite")

        return {
            "status": "success",
            "url": self._page.url,
            "metrics": metrics,
            "ocr": {"source": ocr_result.get("source"), "raw_text": (ocr_result.get("raw_text") or "")[:500]},
            "network_captures": len(self._interceptor.captures()) if self._interceptor else 0,
        }

    async def navigate_professional_dashboard(
        self,
        page_slug: str,
        page_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Open Professional Dashboard for a page."""
        if not self._page:
            return {"status": "error", "message": "Browser not started"}
        if not await self._check_logged_in():
            rec = await self.recover_session(self._account_key or "default", page_id=page_id)
            if not rec.get("logged_in"):
                return {"status": "login_required", "recovery": rec}

        url = PROFESSIONAL_DASHBOARD_URL.format(page=page_slug.lstrip("/"))
        await self._retry_goto(url)
        await self._page.wait_for_timeout(2500)
        await self.infinite_scroll(max_scrolls=8)

        ocr_result = await self.ocr.extract_from_page(self._page, label="pro_dashboard", full_page=True)
        net_metrics = self._interceptor.extract_metrics_from_captures() if self._interceptor else {}
        metrics = self.ocr.normalize_and_merge(ocr_result.get("metrics") or {}, net_metrics)

        pid = page_id or page_slug
        if metrics:
            self.db.store_profile_insight(pid, {**metrics, "snapshot_at": _now()}, source="pro_dashboard")
            for name, val in metrics.items():
                self.db.store_growth_point(pid, name, float(val))

        return {
            "status": "success",
            "url": self._page.url,
            "page_slug": page_slug,
            "metrics": metrics,
            "ocr_source": ocr_result.get("source"),
            "network_captures": len(self._interceptor.captures()) if self._interceptor else 0,
        }

    async def navigate_insights(self, page_slug: str, page_id: Optional[str] = None) -> Dict[str, Any]:
        if not self._page:
            return {"status": "error", "message": "Browser not started"}
        url = PAGE_INSIGHTS_URL.format(page=page_slug.lstrip("/"))
        await self._retry_goto(url)
        await self._page.wait_for_timeout(2000)
        await self.infinite_scroll(max_scrolls=6)
        ocr_result = await self.ocr.extract_from_page(self._page, label="insights")
        net_metrics = self._interceptor.extract_metrics_from_captures() if self._interceptor else {}
        metrics = self.ocr.normalize_and_merge(ocr_result.get("metrics") or {}, net_metrics)
        pid = page_id or page_slug
        if metrics:
            self.db.store_profile_insight(pid, {**metrics, "snapshot_at": _now()}, source="insights")
        return {
            "status": "success",
            "url": self._page.url,
            "metrics": metrics,
            "network_captures": len(self._interceptor.captures()) if self._interceptor else 0,
        }

    async def collect_visible_posts(
        self,
        page_slug: str,
        page_id: Optional[str] = None,
        max_scrolls: int = 12,
    ) -> Dict[str, Any]:
        """
        Navigate to page feed, scroll, and extract post-like structures from DOM + network.
        """
        if not self._page:
            return {"status": "error", "message": "Browser not started"}
        pid = page_id or page_slug
        url = f"https://www.facebook.com/{page_slug.lstrip('/')}"
        await self._retry_goto(url)
        await self._page.wait_for_timeout(2000)
        await self.infinite_scroll(max_scrolls=max_scrolls)

        posts = await self._page.evaluate(
            """() => {
                const results = [];
                const articles = document.querySelectorAll('[role="article"]');
                articles.forEach((el, idx) => {
                    const text = (el.innerText || '').slice(0, 2000);
                    const timeEl = el.querySelector(
                        'a[href*="/posts/"], a[href*="/permalink"], a[href*="/reel/"], a[href*="story_fbid"]'
                    );
                    const link = timeEl ? timeEl.href : null;
                    let postId = null;
                    if (link) {
                        const m = link.match(/\\/posts\\/([^\\/?]+)/)
                            || link.match(/story_fbid=(\\d+)/)
                            || link.match(/\\/reel\\/([^\\/?]+)/);
                        if (m) postId = m[1];
                    }
                    if (!postId) {
                        postId = 'dom_' + idx + '_' + (text.slice(0, 24).replace(/\\s+/g, '_'));
                    }
                    results.push({
                        post_id: postId,
                        caption: text,
                        permalink: link,
                        post_type: (link && link.includes('/reel/')) ? 'reel' : 'post'
                    });
                });
                return results;
            }"""
        )

        stored = 0
        for p in posts or []:
            try:
                self.db.upsert_content(pid, {
                    "post_id": p.get("post_id"),
                    "caption": p.get("caption"),
                    "permalink": p.get("permalink"),
                    "post_type": p.get("post_type", "post"),
                    "publish_date": _now()[:10],
                })
                stored += 1
            except Exception as e:
                log.debug("[Connector] store post failed: %s", e)

        return {
            "status": "success",
            "page_slug": page_slug,
            "posts_found": len(posts or []),
            "posts_stored": stored,
            "posts": posts or [],
            "network_captures": len(self._interceptor.captures()) if self._interceptor else 0,
        }

    async def collect_page_snapshot(
        self,
        account_key: str,
        page_slug: str,
        page_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Full collection pass: ensure session → Business Suite → Pro Dashboard → Insights → Feed.
        """
        pid = page_id or page_slug
        ens = await self.ensure_session(account_key, page_id=pid)
        if not ens.get("logged_in") and ens.get("status") == "error":
            return ens

        results: Dict[str, Any] = {"session": ens, "steps": {}}
        try:
            results["steps"]["business_suite"] = await self.navigate_business_suite(page_id=pid)
            results["steps"]["professional_dashboard"] = await self.navigate_professional_dashboard(
                page_slug, page_id=pid
            )
            results["steps"]["insights"] = await self.navigate_insights(page_slug, page_id=pid)
            results["steps"]["posts"] = await self.collect_visible_posts(page_slug, page_id=pid)
            results["status"] = "success"
        except Exception as e:
            log.exception("[Connector] collect_page_snapshot failed")
            results["status"] = "partial"
            results["error"] = str(e)
        finally:
            await self._persist_current_state(page_id=pid)
        return results

    @property
    def interceptor(self) -> Optional[NetworkInterceptor]:
        return self._interceptor

    @property
    def page(self):
        return self._page


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


facebook_connector = FacebookConnector()
