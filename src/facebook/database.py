"""
Facebook Intelligence Database
==============================
Normalized SQLite schema with versioned migrations, indexes, and automatic backups.

Schema version is tracked in schema_migrations. Backups are written to
Project_State/Facebook/backups/ before each migration and on demand.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .paths import get_backups_dir, get_facebook_db_path

log = logging.getLogger("facebook.database")

SCHEMA_VERSION = 1

# ── Migrations (ordered, irreversible forward-only) ──────────────────────────

MIGRATIONS: Dict[int, str] = {
    1: """
-- Schema versioning
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     INTEGER PRIMARY KEY,
    applied_at  TEXT    NOT NULL,
    description TEXT
);

-- Persistent browser sessions / cookies
CREATE TABLE IF NOT EXISTS fb_sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    account_key     TEXT    NOT NULL UNIQUE,
    page_id         TEXT,
    page_name       TEXT,
    storage_state   TEXT    NOT NULL DEFAULT '{}',
    cookies_json    TEXT    NOT NULL DEFAULT '[]',
    user_agent      TEXT,
    is_valid        INTEGER NOT NULL DEFAULT 1,
    last_login_at   TEXT,
    last_used_at    TEXT,
    last_error      TEXT,
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fb_sessions_valid ON fb_sessions(is_valid);

-- Profile-level insights (snapshots over time)
CREATE TABLE IF NOT EXISTS fb_profile_insights (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    page_id         TEXT    NOT NULL,
    snapshot_at     TEXT    NOT NULL,
    followers       INTEGER,
    following       INTEGER,
    reach           REAL,
    views           REAL,
    impressions     REAL,
    revenue         REAL,
    rpm             REAL,
    earnings        REAL,
    engagement_rate REAL,
    raw_json        TEXT    NOT NULL DEFAULT '{}',
    source          TEXT    DEFAULT 'api',
    content_hash    TEXT    NOT NULL,
    UNIQUE(page_id, content_hash)
);
CREATE INDEX IF NOT EXISTS idx_fb_profile_page_time
    ON fb_profile_insights(page_id, snapshot_at DESC);

-- Audience demographics
CREATE TABLE IF NOT EXISTS fb_audience (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    page_id         TEXT    NOT NULL,
    snapshot_at     TEXT    NOT NULL,
    age_bucket      TEXT,
    gender          TEXT,
    country         TEXT,
    city            TEXT,
    percentage      REAL,
    absolute_count  INTEGER,
    active_hour     INTEGER,
    active_day      INTEGER,
    metric_type     TEXT    NOT NULL DEFAULT 'demographic',
    raw_json        TEXT    NOT NULL DEFAULT '{}',
    content_hash    TEXT    NOT NULL,
    UNIQUE(page_id, content_hash)
);
CREATE INDEX IF NOT EXISTS idx_fb_audience_page
    ON fb_audience(page_id, snapshot_at DESC);
CREATE INDEX IF NOT EXISTS idx_fb_audience_geo
    ON fb_audience(page_id, country, city);

-- Content / publications
CREATE TABLE IF NOT EXISTS fb_content (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    page_id         TEXT    NOT NULL,
    post_id         TEXT    NOT NULL,
    post_type       TEXT    DEFAULT 'post',
    prompt          TEXT,
    ai_model        TEXT,
    character_id    TEXT,
    publish_date    TEXT,
    publish_hour    INTEGER,
    caption         TEXT,
    cta             TEXT,
    hashtags        TEXT,
    style           TEXT,
    image_type      TEXT,
    reach           REAL,
    views           REAL,
    comments_count  INTEGER DEFAULT 0,
    shares          INTEGER DEFAULT 0,
    likes           INTEGER DEFAULT 0,
    revenue         REAL,
    rpm             REAL,
    engagement_rate REAL,
    permalink       TEXT,
    raw_json        TEXT    NOT NULL DEFAULT '{}',
    content_hash    TEXT    NOT NULL,
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL,
    UNIQUE(page_id, post_id)
);
CREATE INDEX IF NOT EXISTS idx_fb_content_page_date
    ON fb_content(page_id, publish_date DESC);
CREATE INDEX IF NOT EXISTS idx_fb_content_rpm
    ON fb_content(page_id, rpm DESC);
CREATE INDEX IF NOT EXISTS idx_fb_content_revenue
    ON fb_content(page_id, revenue DESC);
CREATE INDEX IF NOT EXISTS idx_fb_content_hour
    ON fb_content(page_id, publish_hour);

-- Comments with NLP labels
CREATE TABLE IF NOT EXISTS fb_comments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    page_id         TEXT    NOT NULL,
    post_id         TEXT    NOT NULL,
    comment_id      TEXT    NOT NULL,
    author_name     TEXT,
    author_id       TEXT,
    body            TEXT    NOT NULL,
    created_at_fb   TEXT,
    like_count      INTEGER DEFAULT 0,
    sentiment       TEXT,
    sentiment_score REAL,
    topics          TEXT,
    is_question     INTEGER DEFAULT 0,
    intent          TEXT,
    is_spam         INTEGER DEFAULT 0,
    cluster_id      TEXT,
    raw_json        TEXT    NOT NULL DEFAULT '{}',
    content_hash    TEXT    NOT NULL,
    analyzed_at     TEXT,
    UNIQUE(page_id, comment_id)
);
CREATE INDEX IF NOT EXISTS idx_fb_comments_post
    ON fb_comments(page_id, post_id);
CREATE INDEX IF NOT EXISTS idx_fb_comments_sentiment
    ON fb_comments(page_id, sentiment);
CREATE INDEX IF NOT EXISTS idx_fb_comments_cluster
    ON fb_comments(page_id, cluster_id);
CREATE INDEX IF NOT EXISTS idx_fb_comments_spam
    ON fb_comments(page_id, is_spam);

-- Captured network XHR/Fetch payloads (deduplicated)
CREATE TABLE IF NOT EXISTS fb_network_captures (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    page_id         TEXT,
    account_key     TEXT,
    url             TEXT    NOT NULL,
    method          TEXT    DEFAULT 'GET',
    resource_type   TEXT,
    status_code     INTEGER,
    normalized_json TEXT    NOT NULL,
    content_hash    TEXT    NOT NULL UNIQUE,
    captured_at     TEXT    NOT NULL,
    endpoint_tag    TEXT
);
CREATE INDEX IF NOT EXISTS idx_fb_net_page_time
    ON fb_network_captures(page_id, captured_at DESC);
CREATE INDEX IF NOT EXISTS idx_fb_net_tag
    ON fb_network_captures(endpoint_tag);

-- Prompt performance ranking
CREATE TABLE IF NOT EXISTS fb_prompt_intel (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    page_id         TEXT    NOT NULL,
    prompt_text     TEXT    NOT NULL,
    prompt_hash     TEXT    NOT NULL,
    ai_model        TEXT,
    character_id    TEXT,
    style           TEXT,
    sample_count    INTEGER DEFAULT 0,
    total_revenue   REAL    DEFAULT 0,
    total_reach     REAL    DEFAULT 0,
    total_views     REAL    DEFAULT 0,
    avg_rpm         REAL    DEFAULT 0,
    avg_engagement  REAL    DEFAULT 0,
    score           REAL    DEFAULT 0,
    variants_json   TEXT    DEFAULT '[]',
    updated_at      TEXT    NOT NULL,
    UNIQUE(page_id, prompt_hash)
);
CREATE INDEX IF NOT EXISTS idx_fb_prompt_score
    ON fb_prompt_intel(page_id, score DESC);

-- Monetization analysis snapshots
CREATE TABLE IF NOT EXISTS fb_monetization (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    page_id         TEXT    NOT NULL,
    analysis_at     TEXT    NOT NULL,
    rpm_current     REAL,
    rpm_previous    REAL,
    rpm_delta_pct   REAL,
    rpm_drop_reasons    TEXT,
    rpm_rise_reasons    TEXT,
    highest_earning_post_id TEXT,
    lowest_earning_post_id  TEXT,
    best_hours_json TEXT,
    best_categories_json TEXT,
    summary         TEXT,
    raw_json        TEXT    NOT NULL DEFAULT '{}',
    content_hash    TEXT    NOT NULL,
    UNIQUE(page_id, content_hash)
);
CREATE INDEX IF NOT EXISTS idx_fb_monetization_page
    ON fb_monetization(page_id, analysis_at DESC);

-- Daily recommendations
CREATE TABLE IF NOT EXISTS fb_recommendations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    page_id         TEXT    NOT NULL,
    generated_at    TEXT    NOT NULL,
    rec_date        TEXT    NOT NULL,
    category        TEXT    NOT NULL,
    priority        INTEGER DEFAULT 5,
    title           TEXT    NOT NULL,
    body            TEXT    NOT NULL,
    evidence_json   TEXT    DEFAULT '{}',
    status          TEXT    DEFAULT 'pending',
    content_hash    TEXT    NOT NULL,
    UNIQUE(page_id, content_hash)
);
CREATE INDEX IF NOT EXISTS idx_fb_recs_page_date
    ON fb_recommendations(page_id, rec_date DESC, priority ASC);

-- Competitor pages & public metrics
CREATE TABLE IF NOT EXISTS fb_competitors (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    page_id         TEXT    NOT NULL,
    competitor_id   TEXT    NOT NULL,
    competitor_name TEXT,
    competitor_url  TEXT,
    followers       INTEGER,
    posts_sampled   INTEGER DEFAULT 0,
    avg_engagement  REAL,
    top_topics_json TEXT    DEFAULT '[]',
    trend_signals   TEXT    DEFAULT '[]',
    comparison_json TEXT    DEFAULT '{}',
    recommendations TEXT    DEFAULT '[]',
    snapshot_at     TEXT    NOT NULL,
    raw_json        TEXT    NOT NULL DEFAULT '{}',
    content_hash    TEXT    NOT NULL,
    UNIQUE(page_id, competitor_id, content_hash)
);
CREATE INDEX IF NOT EXISTS idx_fb_competitors_page
    ON fb_competitors(page_id, snapshot_at DESC);

-- Learning loop run log
CREATE TABLE IF NOT EXISTS fb_learning_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    page_id         TEXT    NOT NULL,
    started_at      TEXT    NOT NULL,
    finished_at     TEXT,
    stage           TEXT    NOT NULL,
    status          TEXT    NOT NULL DEFAULT 'running',
    metrics_json    TEXT    DEFAULT '{}',
    error           TEXT
);
CREATE INDEX IF NOT EXISTS idx_fb_learning_page
    ON fb_learning_runs(page_id, started_at DESC);

-- Growth trends time series
CREATE TABLE IF NOT EXISTS fb_growth_trends (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    page_id         TEXT    NOT NULL,
    metric_name     TEXT    NOT NULL,
    metric_value    REAL    NOT NULL,
    recorded_at     TEXT    NOT NULL,
    period          TEXT    DEFAULT 'daily',
    content_hash    TEXT    NOT NULL,
    UNIQUE(page_id, metric_name, content_hash)
);
CREATE INDEX IF NOT EXISTS idx_fb_growth_page_metric
    ON fb_growth_trends(page_id, metric_name, recorded_at DESC);
"""
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _content_hash(*parts: Any) -> str:
    payload = json.dumps(parts, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:40]


class FacebookDatabase:
    """Versioned SQLite store for all Facebook intelligence entities."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path) if db_path else get_facebook_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL, description TEXT)"
            )
            current = conn.execute(
                "SELECT COALESCE(MAX(version), 0) FROM schema_migrations"
            ).fetchone()[0]

        for version in sorted(MIGRATIONS.keys()):
            if version > current:
                self.backup(label=f"pre_migration_v{version}")
                with self._connect() as conn:
                    conn.executescript(MIGRATIONS[version])
                    conn.execute(
                        "INSERT OR REPLACE INTO schema_migrations "
                        "(version, applied_at, description) VALUES (?, ?, ?)",
                        (version, _utc_now(), f"Migration v{version}"),
                    )
                    conn.commit()
                log.info("[FacebookDB] Applied migration v%s", version)

    # ── Backups ──────────────────────────────────────────────────────────────

    def backup(self, label: str = "manual") -> Optional[str]:
        """Copy DB to backups dir. Returns backup path or None if DB missing."""
        if not self.db_path.exists():
            return None
        backup_dir = get_backups_dir()
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        dest = backup_dir / f"facebook_intelligence_{label}_{ts}.db"
        try:
            shutil.copy2(str(self.db_path), str(dest))
            # Keep last 20 backups
            backups = sorted(backup_dir.glob("facebook_intelligence_*.db"), key=lambda p: p.stat().st_mtime)
            for old in backups[:-20]:
                try:
                    old.unlink()
                except OSError:
                    pass
            log.info("[FacebookDB] Backup created: %s", dest.name)
            return str(dest)
        except Exception as e:
            log.warning("[FacebookDB] Backup failed: %s", e)
            return None

    def schema_version(self) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(version), 0) FROM schema_migrations"
            ).fetchone()
            return int(row[0])

    # ── Sessions ─────────────────────────────────────────────────────────────

    def upsert_session(
        self,
        account_key: str,
        storage_state: Dict[str, Any],
        cookies: Optional[List[Dict[str, Any]]] = None,
        page_id: Optional[str] = None,
        page_name: Optional[str] = None,
        user_agent: Optional[str] = None,
        is_valid: bool = True,
        last_error: Optional[str] = None,
        mark_login: bool = False,
    ) -> int:
        now = _utc_now()
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT id FROM fb_sessions WHERE account_key=?", (account_key,)
            ).fetchone()
            if existing:
                conn.execute(
                    """UPDATE fb_sessions SET
                        storage_state=?, cookies_json=?, page_id=COALESCE(?, page_id),
                        page_name=COALESCE(?, page_name), user_agent=COALESCE(?, user_agent),
                        is_valid=?, last_error=?, last_used_at=?,
                        last_login_at=CASE WHEN ? THEN ? ELSE last_login_at END,
                        updated_at=?
                    WHERE account_key=?""",
                    (
                        json.dumps(storage_state),
                        json.dumps(cookies or storage_state.get("cookies", [])),
                        page_id,
                        page_name,
                        user_agent,
                        1 if is_valid else 0,
                        last_error,
                        now,
                        1 if mark_login else 0,
                        now,
                        now,
                        account_key,
                    ),
                )
                conn.commit()
                return int(existing["id"])
            cur = conn.execute(
                """INSERT INTO fb_sessions
                   (account_key, page_id, page_name, storage_state, cookies_json,
                    user_agent, is_valid, last_login_at, last_used_at, last_error,
                    created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    account_key,
                    page_id,
                    page_name,
                    json.dumps(storage_state),
                    json.dumps(cookies or storage_state.get("cookies", [])),
                    user_agent,
                    1 if is_valid else 0,
                    now if mark_login else None,
                    now,
                    last_error,
                    now,
                    now,
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def get_session(self, account_key: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM fb_sessions WHERE account_key=?", (account_key,)
            ).fetchone()
        if not row:
            return None
        data = dict(row)
        data["storage_state"] = json.loads(data.get("storage_state") or "{}")
        data["cookies_json"] = json.loads(data.get("cookies_json") or "[]")
        data["is_valid"] = bool(data.get("is_valid"))
        return data

    def invalidate_session(self, account_key: str, error: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE fb_sessions SET is_valid=0, last_error=?, updated_at=? WHERE account_key=?",
                (error, _utc_now(), account_key),
            )
            conn.commit()

    # ── Network captures ─────────────────────────────────────────────────────

    def store_network_capture(
        self,
        url: str,
        normalized: Any,
        *,
        page_id: Optional[str] = None,
        account_key: Optional[str] = None,
        method: str = "GET",
        resource_type: Optional[str] = None,
        status_code: Optional[int] = None,
        endpoint_tag: Optional[str] = None,
    ) -> Optional[int]:
        payload = json.dumps(normalized, sort_keys=True, default=str, ensure_ascii=False)
        ch = _content_hash(url, method, payload)
        try:
            with self._connect() as conn:
                cur = conn.execute(
                    """INSERT INTO fb_network_captures
                       (page_id, account_key, url, method, resource_type, status_code,
                        normalized_json, content_hash, captured_at, endpoint_tag)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (
                        page_id,
                        account_key,
                        url,
                        method,
                        resource_type,
                        status_code,
                        payload,
                        ch,
                        _utc_now(),
                        endpoint_tag,
                    ),
                )
                conn.commit()
                return int(cur.lastrowid)
        except sqlite3.IntegrityError:
            return None  # duplicate

    def list_network_captures(
        self, page_id: Optional[str] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            if page_id:
                rows = conn.execute(
                    "SELECT * FROM fb_network_captures WHERE page_id=? "
                    "ORDER BY captured_at DESC LIMIT ?",
                    (page_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM fb_network_captures ORDER BY captured_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["normalized_json"] = json.loads(d.get("normalized_json") or "{}")
            result.append(d)
        return result

    # ── Profile insights ─────────────────────────────────────────────────────

    def store_profile_insight(self, page_id: str, metrics: Dict[str, Any], source: str = "api") -> Optional[int]:
        snapshot_at = metrics.get("snapshot_at") or _utc_now()
        ch = _content_hash(
            page_id,
            metrics.get("followers"),
            metrics.get("reach"),
            metrics.get("views"),
            metrics.get("revenue"),
            metrics.get("rpm"),
            snapshot_at[:10],  # daily granularity for dedup
        )
        try:
            with self._connect() as conn:
                cur = conn.execute(
                    """INSERT INTO fb_profile_insights
                       (page_id, snapshot_at, followers, following, reach, views,
                        impressions, revenue, rpm, earnings, engagement_rate,
                        raw_json, source, content_hash)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        page_id,
                        snapshot_at,
                        metrics.get("followers"),
                        metrics.get("following"),
                        metrics.get("reach"),
                        metrics.get("views"),
                        metrics.get("impressions"),
                        metrics.get("revenue"),
                        metrics.get("rpm"),
                        metrics.get("earnings"),
                        metrics.get("engagement_rate"),
                        json.dumps(metrics, default=str),
                        source,
                        ch,
                    ),
                )
                conn.commit()
                return int(cur.lastrowid)
        except sqlite3.IntegrityError:
            return None

    def get_profile_insights(self, page_id: str, limit: int = 30) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM fb_profile_insights WHERE page_id=? "
                "ORDER BY snapshot_at DESC LIMIT ?",
                (page_id, limit),
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["raw_json"] = json.loads(d.get("raw_json") or "{}")
            out.append(d)
        return out

    def latest_profile_insight(self, page_id: str) -> Optional[Dict[str, Any]]:
        rows = self.get_profile_insights(page_id, limit=1)
        return rows[0] if rows else None

    # ── Audience ─────────────────────────────────────────────────────────────

    def store_audience_row(self, page_id: str, row: Dict[str, Any]) -> Optional[int]:
        snapshot_at = row.get("snapshot_at") or _utc_now()
        ch = _content_hash(
            page_id,
            row.get("metric_type", "demographic"),
            row.get("age_bucket"),
            row.get("gender"),
            row.get("country"),
            row.get("city"),
            row.get("active_hour"),
            row.get("percentage"),
            snapshot_at[:10],
        )
        try:
            with self._connect() as conn:
                cur = conn.execute(
                    """INSERT INTO fb_audience
                       (page_id, snapshot_at, age_bucket, gender, country, city,
                        percentage, absolute_count, active_hour, active_day,
                        metric_type, raw_json, content_hash)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        page_id,
                        snapshot_at,
                        row.get("age_bucket"),
                        row.get("gender"),
                        row.get("country"),
                        row.get("city"),
                        row.get("percentage"),
                        row.get("absolute_count"),
                        row.get("active_hour"),
                        row.get("active_day"),
                        row.get("metric_type", "demographic"),
                        json.dumps(row, default=str),
                        ch,
                    ),
                )
                conn.commit()
                return int(cur.lastrowid)
        except sqlite3.IntegrityError:
            return None

    def get_audience(self, page_id: str, metric_type: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            if metric_type:
                rows = conn.execute(
                    "SELECT * FROM fb_audience WHERE page_id=? AND metric_type=? "
                    "ORDER BY snapshot_at DESC LIMIT ?",
                    (page_id, metric_type, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM fb_audience WHERE page_id=? ORDER BY snapshot_at DESC LIMIT ?",
                    (page_id, limit),
                ).fetchall()
        return [dict(r) for r in rows]

    # ── Content ──────────────────────────────────────────────────────────────

    def upsert_content(self, page_id: str, post: Dict[str, Any]) -> int:
        now = _utc_now()
        post_id = str(post.get("post_id") or post.get("id") or "")
        if not post_id:
            raise ValueError("post_id is required")
        ch = _content_hash(page_id, post_id, post.get("caption"), post.get("reach"), post.get("revenue"))
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT id FROM fb_content WHERE page_id=? AND post_id=?",
                (page_id, post_id),
            ).fetchone()
            fields = (
                page_id,
                post_id,
                post.get("post_type", "post"),
                post.get("prompt"),
                post.get("ai_model"),
                post.get("character_id"),
                post.get("publish_date"),
                post.get("publish_hour"),
                post.get("caption"),
                post.get("cta"),
                json.dumps(post.get("hashtags") or [], ensure_ascii=False)
                if not isinstance(post.get("hashtags"), str)
                else post.get("hashtags"),
                post.get("style"),
                post.get("image_type"),
                post.get("reach"),
                post.get("views"),
                post.get("comments_count", post.get("comments", 0)),
                post.get("shares", 0),
                post.get("likes", 0),
                post.get("revenue"),
                post.get("rpm"),
                post.get("engagement_rate"),
                post.get("permalink"),
                json.dumps(post, default=str, ensure_ascii=False),
                ch,
                now,
            )
            if existing:
                conn.execute(
                    """UPDATE fb_content SET
                        post_type=?, prompt=?, ai_model=?, character_id=?,
                        publish_date=?, publish_hour=?, caption=?, cta=?, hashtags=?,
                        style=?, image_type=?, reach=?, views=?, comments_count=?,
                        shares=?, likes=?, revenue=?, rpm=?, engagement_rate=?,
                        permalink=?, raw_json=?, content_hash=?, updated_at=?
                    WHERE page_id=? AND post_id=?""",
                    fields[2:] + (now, page_id, post_id),
                )
                conn.commit()
                return int(existing["id"])
            cur = conn.execute(
                """INSERT INTO fb_content
                   (page_id, post_id, post_type, prompt, ai_model, character_id,
                    publish_date, publish_hour, caption, cta, hashtags, style,
                    image_type, reach, views, comments_count, shares, likes,
                    revenue, rpm, engagement_rate, permalink, raw_json,
                    content_hash, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                fields + (now,),
            )
            conn.commit()
            return int(cur.lastrowid)

    def list_content(
        self,
        page_id: str,
        limit: int = 100,
        order_by: str = "publish_date",
    ) -> List[Dict[str, Any]]:
        allowed = {
            "publish_date": "publish_date DESC",
            "revenue": "revenue DESC",
            "rpm": "rpm DESC",
            "reach": "reach DESC",
            "views": "views DESC",
        }
        order = allowed.get(order_by, "publish_date DESC")
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM fb_content WHERE page_id=? ORDER BY {order} LIMIT ?",
                (page_id, limit),
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["hashtags"] = json.loads(d.get("hashtags") or "[]")
            except (json.JSONDecodeError, TypeError):
                d["hashtags"] = d.get("hashtags") or []
            d["raw_json"] = json.loads(d.get("raw_json") or "{}")
            out.append(d)
        return out

    def get_content(self, page_id: str, post_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM fb_content WHERE page_id=? AND post_id=?",
                (page_id, post_id),
            ).fetchone()
        if not row:
            return None
        d = dict(row)
        try:
            d["hashtags"] = json.loads(d.get("hashtags") or "[]")
        except (json.JSONDecodeError, TypeError):
            pass
        d["raw_json"] = json.loads(d.get("raw_json") or "{}")
        return d

    # ── Comments ─────────────────────────────────────────────────────────────

    def upsert_comment(self, page_id: str, comment: Dict[str, Any]) -> int:
        comment_id = str(comment.get("comment_id") or comment.get("id") or "")
        if not comment_id:
            raise ValueError("comment_id is required")
        post_id = str(comment.get("post_id") or "")
        body = comment.get("body") or comment.get("text") or ""
        ch = _content_hash(page_id, comment_id, body)
        now = _utc_now()
        topics = comment.get("topics")
        if isinstance(topics, list):
            topics = json.dumps(topics, ensure_ascii=False)
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT id FROM fb_comments WHERE page_id=? AND comment_id=?",
                (page_id, comment_id),
            ).fetchone()
            values = (
                page_id,
                post_id,
                comment_id,
                comment.get("author_name"),
                comment.get("author_id"),
                body,
                comment.get("created_at_fb") or comment.get("created_at"),
                comment.get("like_count", 0),
                comment.get("sentiment"),
                comment.get("sentiment_score"),
                topics,
                1 if comment.get("is_question") else 0,
                comment.get("intent"),
                1 if comment.get("is_spam") else 0,
                comment.get("cluster_id"),
                json.dumps(comment, default=str, ensure_ascii=False),
                ch,
                now if comment.get("sentiment") else None,
            )
            if existing:
                conn.execute(
                    """UPDATE fb_comments SET
                        post_id=?, author_name=?, author_id=?, body=?, created_at_fb=?,
                        like_count=?, sentiment=?, sentiment_score=?, topics=?,
                        is_question=?, intent=?, is_spam=?, cluster_id=?,
                        raw_json=?, content_hash=?, analyzed_at=COALESCE(?, analyzed_at)
                    WHERE page_id=? AND comment_id=?""",
                    values[1:] + (page_id, comment_id),
                )
                conn.commit()
                return int(existing["id"])
            cur = conn.execute(
                """INSERT INTO fb_comments
                   (page_id, post_id, comment_id, author_name, author_id, body,
                    created_at_fb, like_count, sentiment, sentiment_score, topics,
                    is_question, intent, is_spam, cluster_id, raw_json,
                    content_hash, analyzed_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                values,
            )
            conn.commit()
            return int(cur.lastrowid)

    def list_comments(
        self,
        page_id: str,
        post_id: Optional[str] = None,
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            if post_id:
                rows = conn.execute(
                    "SELECT * FROM fb_comments WHERE page_id=? AND post_id=? LIMIT ?",
                    (page_id, post_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM fb_comments WHERE page_id=? LIMIT ?",
                    (page_id, limit),
                ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["topics"] = json.loads(d.get("topics") or "[]")
            except (json.JSONDecodeError, TypeError):
                d["topics"] = []
            out.append(d)
        return out

    # ── Prompt intel ─────────────────────────────────────────────────────────

    def upsert_prompt_intel(self, page_id: str, record: Dict[str, Any]) -> int:
        prompt_text = record.get("prompt_text") or record.get("prompt") or ""
        prompt_hash = record.get("prompt_hash") or _content_hash(prompt_text.strip().lower())
        now = _utc_now()
        variants = record.get("variants_json") or record.get("variants") or []
        if not isinstance(variants, str):
            variants = json.dumps(variants, ensure_ascii=False)
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT id FROM fb_prompt_intel WHERE page_id=? AND prompt_hash=?",
                (page_id, prompt_hash),
            ).fetchone()
            if existing:
                conn.execute(
                    """UPDATE fb_prompt_intel SET
                        prompt_text=?, ai_model=?, character_id=?, style=?,
                        sample_count=?, total_revenue=?, total_reach=?, total_views=?,
                        avg_rpm=?, avg_engagement=?, score=?, variants_json=?, updated_at=?
                    WHERE page_id=? AND prompt_hash=?""",
                    (
                        prompt_text,
                        record.get("ai_model"),
                        record.get("character_id"),
                        record.get("style"),
                        record.get("sample_count", 0),
                        record.get("total_revenue", 0),
                        record.get("total_reach", 0),
                        record.get("total_views", 0),
                        record.get("avg_rpm", 0),
                        record.get("avg_engagement", 0),
                        record.get("score", 0),
                        variants,
                        now,
                        page_id,
                        prompt_hash,
                    ),
                )
                conn.commit()
                return int(existing["id"])
            cur = conn.execute(
                """INSERT INTO fb_prompt_intel
                   (page_id, prompt_text, prompt_hash, ai_model, character_id, style,
                    sample_count, total_revenue, total_reach, total_views,
                    avg_rpm, avg_engagement, score, variants_json, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    page_id,
                    prompt_text,
                    prompt_hash,
                    record.get("ai_model"),
                    record.get("character_id"),
                    record.get("style"),
                    record.get("sample_count", 0),
                    record.get("total_revenue", 0),
                    record.get("total_reach", 0),
                    record.get("total_views", 0),
                    record.get("avg_rpm", 0),
                    record.get("avg_engagement", 0),
                    record.get("score", 0),
                    variants,
                    now,
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def rank_prompts(self, page_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM fb_prompt_intel WHERE page_id=? ORDER BY score DESC LIMIT ?",
                (page_id, limit),
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["variants_json"] = json.loads(d.get("variants_json") or "[]")
            except (json.JSONDecodeError, TypeError):
                d["variants_json"] = []
            out.append(d)
        return out

    # ── Monetization ─────────────────────────────────────────────────────────

    def store_monetization(self, page_id: str, analysis: Dict[str, Any]) -> Optional[int]:
        analysis_at = analysis.get("analysis_at") or _utc_now()
        ch = _content_hash(page_id, analysis_at[:16], analysis.get("rpm_current"), analysis.get("summary"))
        try:
            with self._connect() as conn:
                cur = conn.execute(
                    """INSERT INTO fb_monetization
                       (page_id, analysis_at, rpm_current, rpm_previous, rpm_delta_pct,
                        rpm_drop_reasons, rpm_rise_reasons, highest_earning_post_id,
                        lowest_earning_post_id, best_hours_json, best_categories_json,
                        summary, raw_json, content_hash)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        page_id,
                        analysis_at,
                        analysis.get("rpm_current"),
                        analysis.get("rpm_previous"),
                        analysis.get("rpm_delta_pct"),
                        json.dumps(analysis.get("rpm_drop_reasons") or [], ensure_ascii=False),
                        json.dumps(analysis.get("rpm_rise_reasons") or [], ensure_ascii=False),
                        analysis.get("highest_earning_post_id"),
                        analysis.get("lowest_earning_post_id"),
                        json.dumps(analysis.get("best_hours") or analysis.get("best_hours_json") or [], ensure_ascii=False),
                        json.dumps(analysis.get("best_categories") or analysis.get("best_categories_json") or [], ensure_ascii=False),
                        analysis.get("summary"),
                        json.dumps(analysis, default=str, ensure_ascii=False),
                        ch,
                    ),
                )
                conn.commit()
                return int(cur.lastrowid)
        except sqlite3.IntegrityError:
            return None

    def latest_monetization(self, page_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM fb_monetization WHERE page_id=? ORDER BY analysis_at DESC LIMIT 1",
                (page_id,),
            ).fetchone()
        if not row:
            return None
        d = dict(row)
        for key in ("rpm_drop_reasons", "rpm_rise_reasons", "best_hours_json", "best_categories_json", "raw_json"):
            try:
                d[key] = json.loads(d.get(key) or ("{}" if key == "raw_json" else "[]"))
            except (json.JSONDecodeError, TypeError):
                pass
        return d

    # ── Recommendations ──────────────────────────────────────────────────────

    def store_recommendation(self, page_id: str, rec: Dict[str, Any]) -> Optional[int]:
        generated_at = rec.get("generated_at") or _utc_now()
        rec_date = rec.get("rec_date") or generated_at[:10]
        ch = _content_hash(page_id, rec_date, rec.get("category"), rec.get("title"), rec.get("body"))
        try:
            with self._connect() as conn:
                cur = conn.execute(
                    """INSERT INTO fb_recommendations
                       (page_id, generated_at, rec_date, category, priority,
                        title, body, evidence_json, status, content_hash)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (
                        page_id,
                        generated_at,
                        rec_date,
                        rec.get("category", "general"),
                        int(rec.get("priority", 5)),
                        rec.get("title", "Recommendation"),
                        rec.get("body", ""),
                        json.dumps(rec.get("evidence") or rec.get("evidence_json") or {}, default=str),
                        rec.get("status", "pending"),
                        ch,
                    ),
                )
                conn.commit()
                return int(cur.lastrowid)
        except sqlite3.IntegrityError:
            return None

    def list_recommendations(
        self, page_id: str, rec_date: Optional[str] = None, limit: int = 50
    ) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            if rec_date:
                rows = conn.execute(
                    "SELECT * FROM fb_recommendations WHERE page_id=? AND rec_date=? "
                    "ORDER BY priority ASC, generated_at DESC LIMIT ?",
                    (page_id, rec_date, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM fb_recommendations WHERE page_id=? "
                    "ORDER BY generated_at DESC, priority ASC LIMIT ?",
                    (page_id, limit),
                ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["evidence_json"] = json.loads(d.get("evidence_json") or "{}")
            except (json.JSONDecodeError, TypeError):
                d["evidence_json"] = {}
            out.append(d)
        return out

    # ── Competitors ──────────────────────────────────────────────────────────

    def store_competitor(self, page_id: str, data: Dict[str, Any]) -> Optional[int]:
        snapshot_at = data.get("snapshot_at") or _utc_now()
        competitor_id = str(data.get("competitor_id") or data.get("id") or "")
        if not competitor_id:
            raise ValueError("competitor_id is required")
        ch = _content_hash(page_id, competitor_id, snapshot_at[:10], data.get("followers"), data.get("avg_engagement"))
        try:
            with self._connect() as conn:
                cur = conn.execute(
                    """INSERT INTO fb_competitors
                       (page_id, competitor_id, competitor_name, competitor_url,
                        followers, posts_sampled, avg_engagement, top_topics_json,
                        trend_signals, comparison_json, recommendations,
                        snapshot_at, raw_json, content_hash)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        page_id,
                        competitor_id,
                        data.get("competitor_name") or data.get("name"),
                        data.get("competitor_url") or data.get("url"),
                        data.get("followers"),
                        data.get("posts_sampled", 0),
                        data.get("avg_engagement"),
                        json.dumps(data.get("top_topics") or [], ensure_ascii=False),
                        json.dumps(data.get("trend_signals") or [], ensure_ascii=False),
                        json.dumps(data.get("comparison") or {}, default=str),
                        json.dumps(data.get("recommendations") or [], ensure_ascii=False),
                        snapshot_at,
                        json.dumps(data, default=str, ensure_ascii=False),
                        ch,
                    ),
                )
                conn.commit()
                return int(cur.lastrowid)
        except sqlite3.IntegrityError:
            return None

    def list_competitors(self, page_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM fb_competitors WHERE page_id=? ORDER BY snapshot_at DESC LIMIT ?",
                (page_id, limit),
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            for key in ("top_topics_json", "trend_signals", "comparison_json", "recommendations", "raw_json"):
                try:
                    d[key] = json.loads(d.get(key) or ("{}" if "json" in key and key != "top_topics_json" else "[]"))
                except (json.JSONDecodeError, TypeError):
                    pass
            out.append(d)
        return out

    # ── Growth trends ────────────────────────────────────────────────────────

    def store_growth_point(
        self,
        page_id: str,
        metric_name: str,
        metric_value: float,
        recorded_at: Optional[str] = None,
        period: str = "daily",
    ) -> Optional[int]:
        recorded_at = recorded_at or _utc_now()
        ch = _content_hash(page_id, metric_name, recorded_at[:10], period, metric_value)
        try:
            with self._connect() as conn:
                cur = conn.execute(
                    """INSERT INTO fb_growth_trends
                       (page_id, metric_name, metric_value, recorded_at, period, content_hash)
                       VALUES (?,?,?,?,?,?)""",
                    (page_id, metric_name, float(metric_value), recorded_at, period, ch),
                )
                conn.commit()
                return int(cur.lastrowid)
        except sqlite3.IntegrityError:
            return None

    def get_growth_series(
        self, page_id: str, metric_name: str, limit: int = 90
    ) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM fb_growth_trends WHERE page_id=? AND metric_name=? "
                "ORDER BY recorded_at ASC LIMIT ?",
                (page_id, metric_name, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    # ── Learning runs ────────────────────────────────────────────────────────

    def start_learning_run(self, page_id: str, stage: str = "collect") -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO fb_learning_runs
                   (page_id, started_at, stage, status) VALUES (?,?,?,?)""",
                (page_id, _utc_now(), stage, "running"),
            )
            conn.commit()
            return int(cur.lastrowid)

    def update_learning_run(
        self,
        run_id: int,
        stage: Optional[str] = None,
        status: Optional[str] = None,
        metrics: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        finished: bool = False,
    ) -> None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT stage, status, metrics_json FROM fb_learning_runs WHERE id=?",
                (run_id,),
            ).fetchone()
            if not row:
                return
            new_stage = stage or row["stage"]
            new_status = status or row["status"]
            if metrics is not None:
                metrics_json = json.dumps(metrics, default=str)
            else:
                metrics_json = row["metrics_json"]
            finished_at = _utc_now() if finished else None
            if finished and not status:
                new_status = "completed" if not error else "failed"
            conn.execute(
                """UPDATE fb_learning_runs SET
                    stage=?, status=?, metrics_json=?, error=?,
                    finished_at=COALESCE(?, finished_at)
                WHERE id=?""",
                (new_stage, new_status, metrics_json, error, finished_at, run_id),
            )
            conn.commit()

    def list_learning_runs(self, page_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM fb_learning_runs WHERE page_id=? ORDER BY started_at DESC LIMIT ?",
                (page_id, limit),
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["metrics_json"] = json.loads(d.get("metrics_json") or "{}")
            except (json.JSONDecodeError, TypeError):
                d["metrics_json"] = {}
            out.append(d)
        return out

    # ── Aggregates for intelligence ──────────────────────────────────────────

    def content_aggregates(self, page_id: str) -> Dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                """SELECT
                    COUNT(*) as post_count,
                    COALESCE(SUM(revenue), 0) as total_revenue,
                    COALESCE(AVG(rpm), 0) as avg_rpm,
                    COALESCE(AVG(reach), 0) as avg_reach,
                    COALESCE(AVG(views), 0) as avg_views,
                    COALESCE(AVG(engagement_rate), 0) as avg_engagement,
                    COALESCE(SUM(comments_count), 0) as total_comments,
                    COALESCE(SUM(shares), 0) as total_shares
                FROM fb_content WHERE page_id=?""",
                (page_id,),
            ).fetchone()
        return dict(row) if row else {}

    def best_posting_hours(self, page_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT publish_hour as hour,
                          COUNT(*) as posts,
                          COALESCE(AVG(revenue), 0) as avg_revenue,
                          COALESCE(AVG(rpm), 0) as avg_rpm,
                          COALESCE(AVG(engagement_rate), 0) as avg_engagement
                   FROM fb_content
                   WHERE page_id=? AND publish_hour IS NOT NULL
                   GROUP BY publish_hour
                   ORDER BY avg_revenue DESC, avg_engagement DESC
                   LIMIT ?""",
                (page_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def content_by_category_proxy(self, page_id: str) -> List[Dict[str, Any]]:
        """Group by style/image_type/post_type as content categories."""
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT
                      COALESCE(NULLIF(style, ''), NULLIF(image_type, ''), post_type, 'unknown') as category,
                      COUNT(*) as posts,
                      COALESCE(SUM(revenue), 0) as total_revenue,
                      COALESCE(AVG(rpm), 0) as avg_rpm,
                      COALESCE(AVG(engagement_rate), 0) as avg_engagement
                   FROM fb_content WHERE page_id=?
                   GROUP BY category
                   ORDER BY total_revenue DESC""",
                (page_id,),
            ).fetchall()
        return [dict(r) for r in rows]


# Module-level singleton
facebook_db = FacebookDatabase()
