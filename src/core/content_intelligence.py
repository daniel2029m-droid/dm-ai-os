"""
ContentIntelligenceCollector — Ingestion, validation, normalization, and performance scoring for DM AI OS v1.5.1.
Connects creative execution artifacts with real-world audience telemetry.
"""
import time
import math
import uuid
import logging
from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional, List

from ..storage.storage_layer import storage
from ..storage.content_metrics_store import content_metrics_store, ContentMetricsStore

log = logging.getLogger("content_intelligence")

class ContentIntelligenceError(ValueError):
    """Raised when performance telemetry validation fails."""
    def __init__(self, message: str, error_code: str = "INVALID_METRIC", details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.error_code = error_code
        self.details = details or {}


@dataclass
class ContentPerformanceEvent:
    metric_id: str
    job_id: str
    channel: str
    views: int = 0
    likes: int = 0
    shares: int = 0
    comments: int = 0
    retention_rate: Optional[float] = None
    ctr: Optional[float] = None
    performance_score: Optional[float] = None
    source: str = "manual"
    recorded_at: Optional[str] = None

    def __post_init__(self):
        if not self.recorded_at:
            self.recorded_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def calculate_performance_score(
    views: int,
    likes: int,
    shares: int,
    comments: int,
    retention_rate: Optional[float] = None,
    ctr: Optional[float] = None
) -> float:
    """
    Computes a deterministic, normalized composite performance score (0.0 to 100.0).
    
    Formula components:
    - Engagement Rate (30% weight): (likes*1 + comments*2 + shares*3) / max(views, 1)
    - Retention Rate (40% weight): retention_rate [0.0 - 1.0]
    - CTR (30% weight): ctr [0.0 - 1.0]
    """
    safe_views = max(int(views), 1)
    
    # Weighted engagement interactions
    engagement_points = (likes * 1.0) + (comments * 2.0) + (shares * 3.0)
    raw_engagement_rate = engagement_points / safe_views
    # Normalize engagement rate (10% engagement = 1.0 normalized)
    norm_engagement = min(raw_engagement_rate * 10.0, 1.0)

    # Retention factor
    norm_retention = float(retention_rate) if retention_rate is not None else 0.0
    norm_retention = max(0.0, min(norm_retention, 1.0))

    # CTR factor
    norm_ctr = float(ctr) if ctr is not None else 0.0
    # Normalize CTR (10% CTR = 1.0 normalized)
    norm_ctr_scaled = min(norm_ctr * 10.0, 1.0)

    # Composite weighted score out of 100
    composite = (norm_retention * 0.40) + (norm_engagement * 0.30) + (norm_ctr_scaled * 0.30)
    return round(composite * 100.0, 2)


class ContentIntelligenceCollector:
    """
    Validates, normalizes, scores, and persists real-world content performance metrics.
    """

    def __init__(self, metrics_store: Optional[ContentMetricsStore] = None):
        self.store = metrics_store or content_metrics_store

    def validate_event_data(self, data: Dict[str, Any], enforce_job_exists: bool = True) -> Dict[str, Any]:
        """Validates all incoming metric fields against strict schema constraints."""
        job_id = data.get("job_id")
        if not job_id or not isinstance(job_id, str) or not job_id.strip():
            raise ContentIntelligenceError("Missing or invalid 'job_id'.", error_code="INVALID_METRIC")

        if enforce_job_exists:
            job = storage.job_store.get_job(job_id)
            if not job:
                raise ContentIntelligenceError(
                    f"Job '{job_id}' does not exist in JobStore.",
                    error_code="JOB_NOT_FOUND",
                    details={"job_id": job_id}
                )

        channel = data.get("channel")
        if not channel or not isinstance(channel, str) or not channel.strip():
            raise ContentIntelligenceError("Missing or empty 'channel'.", error_code="INVALID_CHANNEL")

        # Non-negative integer metric checks
        for metric_name in ("views", "likes", "shares", "comments"):
            val = data.get(metric_name, 0)
            if not isinstance(val, (int, float)) or math.isnan(val) or math.isinf(val) or val < 0:
                raise ContentIntelligenceError(
                    f"Metric '{metric_name}' must be a non-negative integer, got {val}.",
                    error_code="INVALID_METRIC",
                    details={"field": metric_name, "value": val}
                )

        # Range checks for rates
        for rate_name in ("retention_rate", "ctr"):
            r_val = data.get(rate_name)
            if r_val is not None:
                if not isinstance(r_val, (int, float)) or math.isnan(r_val) or math.isinf(r_val) or r_val < 0.0 or r_val > 1.0:
                    raise ContentIntelligenceError(
                        f"Rate '{rate_name}' must be between 0.0 and 1.0, got {r_val}.",
                        error_code="INVALID_METRIC",
                        details={"field": rate_name, "value": r_val}
                    )

        return data

    def ingest_performance_event(
        self,
        raw_data: Dict[str, Any],
        enforce_job_exists: bool = True
    ) -> Dict[str, Any]:
        """
        Main ingestion entrypoint:
        1. Validates inputs.
        2. Computes deterministic performance_score if missing.
        3. Persists idempotently to ContentMetricsStore.
        4. Recovers via DLQ if transient database error occurs.
        """
        try:
            valid_data = self.validate_event_data(raw_data, enforce_job_exists=enforce_job_exists)
        except ContentIntelligenceError:
            raise
        except Exception as e:
            log.error(f"[ContentIntelligenceCollector] Validation error: {e}")
            raise ContentIntelligenceError(f"Validation failure: {e}", error_code="INVALID_METRIC")

        metric_id = valid_data.get("metric_id") or f"metric_{uuid.uuid4().hex[:12]}"
        job_id = valid_data["job_id"]
        channel = valid_data["channel"].lower().strip()
        views = int(valid_data.get("views", 0))
        likes = int(valid_data.get("likes", 0))
        shares = int(valid_data.get("shares", 0))
        comments = int(valid_data.get("comments", 0))
        retention = valid_data.get("retention_rate")
        ctr = valid_data.get("ctr")
        source = valid_data.get("source", "manual")
        recorded_at = valid_data.get("recorded_at") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        # Calculate performance score if not provided
        score = valid_data.get("performance_score")
        if score is None:
            score = calculate_performance_score(
                views=views,
                likes=likes,
                shares=shares,
                comments=comments,
                retention_rate=retention,
                ctr=ctr
            )

        event = ContentPerformanceEvent(
            metric_id=metric_id,
            job_id=job_id,
            channel=channel,
            views=views,
            likes=likes,
            shares=shares,
            comments=comments,
            retention_rate=retention,
            ctr=ctr,
            performance_score=score,
            source=source,
            recorded_at=recorded_at
        )

        try:
            persisted = self.store.record_metric(asdict(event))
            return {
                "status": "SUCCESS",
                "metric_id": metric_id,
                "job_id": job_id,
                "performance_score": score,
                "is_duplicate": persisted.get("is_duplicate", False),
                "recorded_at": recorded_at
            }
        except Exception as e:
            log.error(f"[ContentIntelligenceCollector] Storage error for metric '{metric_id}': {e}")
            dlq_id = self.store.push_dlq(asdict(event), str(e))
            return {
                "status": "QUEUED_DLQ",
                "metric_id": metric_id,
                "dlq_id": dlq_id,
                "error": str(e)
            }

    def get_job_metrics(self, job_id: str) -> List[Dict[str, Any]]:
        """Retrieves all telemetry events recorded for a job."""
        return self.store.get_metrics_by_job(job_id)

    def get_channel_metrics(self, channel: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieves telemetry events by marketing/publishing channel."""
        return self.store.get_metrics_by_channel(channel, limit=limit)

# Global singleton
content_intelligence = ContentIntelligenceCollector()
