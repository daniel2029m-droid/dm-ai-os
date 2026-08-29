"""
Phase 15.2 Test Suite: Creative Memory & Pattern Extraction.
Covers:
1-2: Table creation and idempotent migration.
3-4: Manifest & Prompt Genome extraction.
5-9: Manifest -> Metrics association, pattern creation, update, sample_count, avg_score.
10-15: Global baseline, lift calculation, MIN_PATTERN_SAMPLES, LOW_CONFIDENCE, OUTPERFORMING, UNDERPERFORMING.
16-18: Query by category, top patterns, underperforming patterns.
19: Zero PII in schema.
20-22: Non-existent manifests, non-existent metrics, corrupted data handling.
23: Idempotency of refresh_patterns().
"""
import pytest
import sqlite3
from src.core.creative_memory import CreativeMemoryManager, creative_memory, GENOME_KEYWORDS
from src.storage.content_metrics_store import ContentMetricsStore
from src.core.content_intelligence import ContentIntelligenceCollector
from src.storage.storage_layer import storage

@pytest.fixture
def temp_memory_env(tmp_path):
    db_file = tmp_path / "test_creative_memory.db"
    store = ContentMetricsStore(db_path=str(db_file))
    collector = ContentIntelligenceCollector(metrics_store=store)
    manager = CreativeMemoryManager(db_path=str(db_file), min_pattern_samples=3, metrics_store=store)
    return {
        "db_path": str(db_file),
        "store": store,
        "collector": collector,
        "manager": manager
    }

# 1-2: Creación de tabla e índices, y migración idempotente
def test_1_2_table_and_indexes_creation(temp_memory_env):
    mgr = temp_memory_env["manager"]
    mgr._ensure_db()
    mgr._ensure_db() # idempotent test
    with sqlite3.connect(temp_memory_env["db_path"]) as conn:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(creative_patterns);")
        cols = [r[1] for r in cur.fetchall()]
        assert "pattern_id" in cols
        assert "pattern_type" in cols
        assert "descriptor" in cols
        assert "avg_performance_score" in cols
        assert "sample_count" in cols
        
        cur.execute("PRAGMA index_list(creative_patterns);")
        indexes = [r[1] for r in cur.fetchall()]
        assert "idx_creative_patterns_type" in indexes
        assert "idx_creative_patterns_score" in indexes

# 3-4: Extracción de Prompt Genome
def test_3_4_prompt_genome_extraction(temp_memory_env):
    mgr = temp_memory_env["manager"]
    prompt = "A photorealistic cyberpunk hero shot of a neon samurai, centered composition, volumetric lighting"
    genome = mgr.extract_prompt_genome(prompt)
    
    assert "photorealistic" in genome["STYLE"]
    assert "cyberpunk" in genome["STYLE"]
    assert "hero_shot" in genome["HOOK"]
    assert "centered" in genome["COMPOSITION"]
    assert "neon" in genome["LIGHTING"]
    assert "volumetric" in genome["LIGHTING"]

# 5-9: Asociación Manifest -> Metrics, Creación de Patrones y Estadísticas
def test_5_9_pattern_creation_and_stats(temp_memory_env):
    mgr = temp_memory_env["manager"]
    store = temp_memory_env["store"]
    collector = temp_memory_env["collector"]

    # Create 3 jobs with cyberpunk + neon style
    for i in range(3):
        job_id = f"job_mem_test_{i}"
        storage.job_store.create_job({
            "job_id": job_id,
            "status": "COMPLETED",
            "workflow_name": "flux2_klein_txt2img",
            "prompt": "photorealistic cyberpunk street with neon lighting",
            "created_at": "2026-08-28T00:00:00Z"
        })
        # Ingest metrics for each
        collector.ingest_performance_event({
            "job_id": job_id,
            "channel": "facebook",
            "views": 1000,
            "likes": 80 + (i * 10),
            "retention_rate": 0.8,
            "ctr": 0.05
        })

    # Refresh patterns
    res = mgr.refresh_patterns()
    assert res["status"] == "SUCCESS"
    assert res["patterns_updated"] >= 2

    # Check pattern stats
    cyber_pattern = mgr.get_pattern("pat_style_cyberpunk")
    assert cyber_pattern is not None
    assert cyber_pattern["sample_count"] == 3
    assert cyber_pattern["avg_performance_score"] > 0.0
    assert cyber_pattern["is_reliable_evidence"] is True

# 10-15: Baseline, Lift, Thresholds y Clasificación (LOW_CONFIDENCE, OUTPERFORMING, UNDERPERFORMING)
def test_10_15_baseline_lift_and_classifications(temp_memory_env):
    mgr = temp_memory_env["manager"]
    collector = temp_memory_env["collector"]

    # 1. Create a winning pattern (3 samples with high performance score)
    for i in range(3):
        j_id = f"job_win_{i}"
        storage.job_store.create_job({"job_id": j_id, "status": "COMPLETED", "prompt": "cinematic hero shot with golden hour lighting"})
        collector.ingest_performance_event({"job_id": j_id, "channel": "fb", "views": 1000, "likes": 150, "retention_rate": 0.9, "ctr": 0.1})

    # 2. Create an underperforming pattern (3 samples with low score)
    for i in range(3):
        j_id = f"job_low_{i}"
        storage.job_store.create_job({"job_id": j_id, "status": "COMPLETED", "prompt": "minimalist simple drawing"})
        collector.ingest_performance_event({"job_id": j_id, "channel": "fb", "views": 1000, "likes": 2, "retention_rate": 0.1, "ctr": 0.01})

    # 3. Create a pattern with low sample count (only 1 sample -> LOW_CONFIDENCE)
    j_id = "job_single_sample"
    storage.job_store.create_job({"job_id": j_id, "status": "COMPLETED", "prompt": "watercolor anime landscape"})
    collector.ingest_performance_event({"job_id": j_id, "channel": "fb", "views": 500, "likes": 50})

    mgr.refresh_patterns()
    baseline = mgr.get_global_baseline()
    assert baseline > 0.0

    # Verify winning pattern
    pat_win = mgr.get_pattern("pat_style_cinematic")
    assert pat_win["classification"] == "OUTPERFORMING"
    assert pat_win["lift"] > 0.0

    # Verify underperforming pattern
    pat_low = mgr.get_pattern("pat_style_minimalist")
    assert pat_low["classification"] == "UNDERPERFORMING"
    assert pat_low["lift"] < 0.0

    # Verify low confidence pattern (sample_count < 3)
    pat_single = mgr.get_pattern("pat_style_watercolor")
    assert pat_single["classification"] == "LOW_CONFIDENCE"
    assert pat_single["is_reliable_evidence"] is False

# 16-18: Consultas por categoría, Top y Underperforming patterns
def test_16_18_queries_and_categories(temp_memory_env):
    mgr = temp_memory_env["manager"]
    collector = temp_memory_env["collector"]

    # Seed data
    for i in range(3):
        j_id = f"job_cat_{i}"
        storage.job_store.create_job({"job_id": j_id, "status": "COMPLETED", "prompt": "cyberpunk anime neon lighting centered"})
        collector.ingest_performance_event({"job_id": j_id, "channel": "fb", "views": 1000, "likes": 60, "retention_rate": 0.7})

    mgr.refresh_patterns()

    # Query by category
    style_patterns = mgr.get_top_patterns(category="STYLE", limit=5)
    assert len(style_patterns) >= 1
    assert style_patterns[0]["pattern_type"] == "STYLE"

    lighting_patterns = mgr.get_top_patterns(category="LIGHTING", limit=5)
    assert len(lighting_patterns) >= 1
    assert lighting_patterns[0]["pattern_type"] == "LIGHTING"

    # Query top & underperforming lists
    top = mgr.get_top_patterns(limit=5)
    assert len(top) >= 1
    assert "lift" in top[0]

    under = mgr.get_underperforming_patterns(limit=5)
    assert isinstance(under, list)

# 19: Ausencia de PII en creative_patterns
def test_19_absence_of_pii(temp_memory_env):
    with sqlite3.connect(temp_memory_env["db_path"]) as conn:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(creative_patterns);")
        col_names = [r[1].lower() for r in cur.fetchall()]
        pii_keywords = ["email", "user_name", "username", "ip_address", "phone", "first_name", "last_name", "password"]
        for kw in pii_keywords:
            assert kw not in col_names

# 20-22: Comportamiento ante datos inexistentes y corruptos
def test_20_22_nonexistent_and_corrupt_data(temp_memory_env):
    mgr = temp_memory_env["manager"]

    # Non-existent job
    res_ghost = mgr.analyze_job("ghost_job_9999")
    assert res_ghost["status"] == "NOT_FOUND"

    # Empty/None prompt
    genome_empty = mgr.extract_prompt_genome("")
    assert all(len(v) == 0 for v in genome_empty.values())

    genome_none = mgr.extract_prompt_genome(None)
    assert all(len(v) == 0 for v in genome_none.values())

# 23: Idempotencia de refresh_patterns
def test_23_refresh_patterns_idempotency(temp_memory_env):
    mgr = temp_memory_env["manager"]
    collector = temp_memory_env["collector"]

    storage.job_store.create_job({"job_id": "job_idemp_mem", "status": "COMPLETED", "prompt": "cyberpunk neon"})
    collector.ingest_performance_event({"job_id": "job_idemp_mem", "channel": "fb", "views": 1000, "likes": 50})

    res1 = mgr.refresh_patterns()
    res2 = mgr.refresh_patterns()

    assert res1["patterns_updated"] == res2["patterns_updated"]
    assert res1["global_baseline"] == res2["global_baseline"]
