"""
Phase 15.1 Test Suite: Content Intelligence Persistence & Collector.
Validates:
1. Table & index creation in SQLite.
2. Idempotent table initialization.
3. Valid ingestion and metric retrieval.
4. Rejection of non-existent job_id (JOB_NOT_FOUND).
5. Rejection of negative metric values.
6. Validation of retention_rate (0.0 to 1.0).
7. Validation of CTR (0.0 to 1.0).
8. Deterministic calculation of performance_score.
9. Idempotent deduplication by metric_id.
10. Query by job_id.
11. Query by channel.
12. Timestamps.
13. SQLite error handling & DLQ resilience.
14. DLQ entry retrieval.
15. Absence of PII.
16. Compatibility with Phase 14 JobStore.
"""
import pytest
import sqlite3
from unittest.mock import patch

from src.storage.content_metrics_store import ContentMetricsStore, content_metrics_store
from src.core.content_intelligence import (
    ContentIntelligenceCollector,
    ContentPerformanceEvent,
    ContentIntelligenceError,
    calculate_performance_score,
    content_intelligence
)
from src.storage.storage_layer import storage

@pytest.fixture
def temp_metrics_store(tmp_path):
    db_file = tmp_path / "test_metrics.db"
    return ContentMetricsStore(db_path=str(db_file))

@pytest.fixture
def temp_collector(temp_metrics_store):
    return ContentIntelligenceCollector(metrics_store=temp_metrics_store)

# 1. Creación de tabla e índices
def test_1_table_and_indexes_creation(temp_metrics_store):
    temp_metrics_store._ensure_db()
    with sqlite3.connect(temp_metrics_store.db_path) as conn:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(content_metrics);")
        cols = [r[1] for r in cur.fetchall()]
        assert "metric_id" in cols
        assert "job_id" in cols
        assert "channel" in cols
        assert "performance_score" in cols
        
        cur.execute("PRAGMA index_list(content_metrics);")
        indexes = [r[1] for r in cur.fetchall()]
        assert "idx_content_metrics_job_id" in indexes
        assert "idx_content_metrics_channel" in indexes

# 2. Migración idempotente
def test_2_idempotent_migration(temp_metrics_store):
    temp_metrics_store._ensure_db()
    temp_metrics_store._ensure_db()  # Repeated execution should not error
    assert temp_metrics_store._db_initialized is True

# 3. Inserción válida
def test_3_valid_insertion(temp_collector):
    # Register job in JobStore first
    job_id = "job_pi_test_001"
    storage.job_store.create_job({
        "job_id": job_id,
        "status": "COMPLETED",
        "workflow_name": "flux2_klein_txt2img",
        "created_at": "2026-08-28T00:00:00Z"
    })

    res = temp_collector.ingest_performance_event({
        "metric_id": "metric_001",
        "job_id": job_id,
        "channel": "facebook",
        "views": 1000,
        "likes": 50,
        "shares": 10,
        "comments": 5,
        "retention_rate": 0.65,
        "ctr": 0.04
    })
    assert res["status"] == "SUCCESS"
    assert res["metric_id"] == "metric_001"
    assert res["performance_score"] > 0.0
    assert res["is_duplicate"] is False

# 4. Rechazo de job_id inexistente
def test_4_rejection_nonexistent_job(temp_collector):
    with pytest.raises(ContentIntelligenceError) as excinfo:
        temp_collector.ingest_performance_event({
            "job_id": "completely_ghost_job_999",
            "channel": "instagram",
            "views": 100
        }, enforce_job_exists=True)
    assert excinfo.value.error_code == "JOB_NOT_FOUND"

# 5. Rechazo de métricas negativas
def test_5_rejection_negative_metrics(temp_collector):
    job_id = "job_pi_test_002"
    storage.job_store.create_job({"job_id": job_id, "status": "COMPLETED", "workflow_name": "wf"})

    with pytest.raises(ContentIntelligenceError) as excinfo:
        temp_collector.ingest_performance_event({
            "job_id": job_id,
            "channel": "facebook",
            "views": -50
        })
    assert excinfo.value.error_code == "INVALID_METRIC"

# 6. Validación de retention_rate
def test_6_retention_rate_bounds(temp_collector):
    job_id = "job_pi_test_003"
    storage.job_store.create_job({"job_id": job_id, "status": "COMPLETED", "workflow_name": "wf"})

    # Greater than 1.0
    with pytest.raises(ContentIntelligenceError) as excinfo:
        temp_collector.ingest_performance_event({
            "job_id": job_id,
            "channel": "youtube",
            "views": 100,
            "retention_rate": 1.5
        })
    assert excinfo.value.error_code == "INVALID_METRIC"

    # Negative
    with pytest.raises(ContentIntelligenceError) as excinfo2:
        temp_collector.ingest_performance_event({
            "job_id": job_id,
            "channel": "youtube",
            "views": 100,
            "retention_rate": -0.1
        })
    assert excinfo2.value.error_code == "INVALID_METRIC"

# 7. Validación de CTR
def test_7_ctr_bounds(temp_collector):
    job_id = "job_pi_test_004"
    storage.job_store.create_job({"job_id": job_id, "status": "COMPLETED", "workflow_name": "wf"})

    with pytest.raises(ContentIntelligenceError) as excinfo:
        temp_collector.ingest_performance_event({
            "job_id": job_id,
            "channel": "ads",
            "views": 100,
            "ctr": 2.0
        })
    assert excinfo.value.error_code == "INVALID_METRIC"

# 8. Cálculo determinista de performance score
def test_8_deterministic_performance_score():
    score1 = calculate_performance_score(views=1000, likes=100, shares=20, comments=10, retention_rate=0.8, ctr=0.05)
    score2 = calculate_performance_score(views=1000, likes=100, shares=20, comments=10, retention_rate=0.8, ctr=0.05)
    assert score1 == score2
    assert 0.0 <= score1 <= 100.0

    # Higher engagement produces higher score
    lower_score = calculate_performance_score(views=1000, likes=2, shares=0, comments=0, retention_rate=0.1, ctr=0.01)
    assert score1 > lower_score

# 9. Deduplicación por metric_id (Idempotencia)
def test_9_idempotent_deduplication(temp_collector, temp_metrics_store):
    job_id = "job_pi_test_005"
    storage.job_store.create_job({"job_id": job_id, "status": "COMPLETED", "workflow_name": "wf"})

    payload = {
        "metric_id": "metric_idemp_100",
        "job_id": job_id,
        "channel": "facebook",
        "views": 500,
        "likes": 25
    }

    res1 = temp_collector.ingest_performance_event(payload)
    assert res1["status"] == "SUCCESS"
    assert res1["is_duplicate"] is False

    # Second ingestion of exact same metric_id
    res2 = temp_collector.ingest_performance_event(payload)
    assert res2["status"] == "SUCCESS"
    assert res2["is_duplicate"] is True

    # Check that database has exactly 1 entry
    entries = temp_metrics_store.get_metrics_by_job(job_id)
    assert len(entries) == 1

# 10. Consulta por job_id
def test_10_query_by_job_id(temp_collector):
    job_id = "job_pi_test_006"
    storage.job_store.create_job({"job_id": job_id, "status": "COMPLETED", "workflow_name": "wf"})

    temp_collector.ingest_performance_event({"job_id": job_id, "channel": "facebook", "views": 100})
    temp_collector.ingest_performance_event({"job_id": job_id, "channel": "instagram", "views": 200})

    metrics = temp_collector.get_job_metrics(job_id)
    assert len(metrics) == 2

# 11. Consulta por channel
def test_11_query_by_channel(temp_collector):
    job_id1 = "job_pi_test_007"
    job_id2 = "job_pi_test_008"
    storage.job_store.create_job({"job_id": job_id1, "status": "COMPLETED", "workflow_name": "wf"})
    storage.job_store.create_job({"job_id": job_id2, "status": "COMPLETED", "workflow_name": "wf"})

    temp_collector.ingest_performance_event({"job_id": job_id1, "channel": "tiktok", "views": 100})
    temp_collector.ingest_performance_event({"job_id": job_id2, "channel": "tiktok", "views": 300})

    tt_metrics = temp_collector.get_channel_metrics("tiktok")
    assert len(tt_metrics) == 2

# 12. Timestamps
def test_12_timestamps_auto_generated(temp_collector):
    job_id = "job_pi_test_009"
    storage.job_store.create_job({"job_id": job_id, "status": "COMPLETED", "workflow_name": "wf"})

    res = temp_collector.ingest_performance_event({"job_id": job_id, "channel": "facebook", "views": 10})
    assert res["recorded_at"] is not None
    assert "T" in res["recorded_at"]

# 13-14. DLQ Resilience & Retrieval
def test_13_14_dlq_resilience(temp_collector, temp_metrics_store):
    job_id = "job_pi_test_010"
    storage.job_store.create_job({"job_id": job_id, "status": "COMPLETED", "workflow_name": "wf"})

    # Simulate database error on record_metric
    with patch.object(temp_metrics_store, "record_metric", side_effect=sqlite3.OperationalError("Simulated DB lock")):
        res = temp_collector.ingest_performance_event({
            "metric_id": "metric_dlq_test",
            "job_id": job_id,
            "channel": "facebook",
            "views": 100
        })
        assert res["status"] == "QUEUED_DLQ"
        assert "dlq_id" in res

        # Retrieve DLQ entries
        dlq_items = temp_metrics_store.get_dlq_entries()
        assert len(dlq_items) >= 1
        assert dlq_items[0]["dlq_id"] == res["dlq_id"]

# 15. Ausencia de PII en schema
def test_15_absence_of_pii_in_schema(temp_metrics_store):
    temp_metrics_store._ensure_db()
    with sqlite3.connect(temp_metrics_store.db_path) as conn:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(content_metrics);")
        col_names = [r[1].lower() for r in cur.fetchall()]
        pii_keywords = ["email", "user_name", "username", "ip_address", "phone", "first_name", "last_name", "password"]
        for kw in pii_keywords:
            assert kw not in col_names, f"PII column detected: {kw}"

# 16. Compatibilidad con Phase 14 JobStore
def test_16_phase14_jobstore_compatibility():
    # Verify JobStore table is intact and operational
    jobs = storage.job_store.list_jobs(limit=5)
    assert isinstance(jobs, list)
