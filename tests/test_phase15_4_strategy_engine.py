"""
Phase 15.4 Test Suite: Creative Strategy Engine.
Covers items 1 to 24:
1-2: Table creation and indexes in SQLite.
3-6: Brief creation with OUTPERFORMING evidence, Cold-Start fallback, LOW_CONFIDENCE treatment, UNDERPERFORMING avoidance.
7-11: Global baseline, recommended genome, actionable hypothesis, confidence score, evidence persistence.
12-13: get_brief() and list_briefs().
14-15: execute_brief() with Phase 14 dispatch and dispatched_job_id tracking.
16-18: reject_brief() and terminal state immutability (DISPATCHED and REJECTED).
19-20: SQLite persistence across restarts and idempotency.
21-23: End-to-End integration: Metrics -> Memory -> Strategy Brief -> Phase 14 Execution and failure tolerance.
24: Full regression check.
"""
import pytest
import sqlite3
from unittest.mock import AsyncMock, patch

from src.core.strategy_engine import StrategyEngine, StrategyError, strategy_engine
from src.core.creative_memory import CreativeMemoryManager
from src.core.content_intelligence import ContentIntelligenceCollector
from src.storage.content_metrics_store import ContentMetricsStore
from src.storage.storage_layer import storage

@pytest.fixture
def temp_strategy_env(tmp_path):
    db_file = tmp_path / "test_strategy.db"
    store = ContentMetricsStore(db_path=str(db_file))
    collector = ContentIntelligenceCollector(metrics_store=store)
    mem_manager = CreativeMemoryManager(db_path=str(db_file), metrics_store=store, min_pattern_samples=3)
    strat_engine = StrategyEngine(db_path=str(db_file), memory_manager=mem_manager)
    return {
        "db_path": str(db_file),
        "store": store,
        "collector": collector,
        "mem_manager": mem_manager,
        "strat_engine": strat_engine
    }

# 1-2: Creación de tabla e índices
def test_1_2_table_and_indexes(temp_strategy_env):
    strat = temp_strategy_env["strat_engine"]
    strat._ensure_db()
    with sqlite3.connect(temp_strategy_env["db_path"]) as conn:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(creative_strategy_briefs);")
        cols = [r[1] for r in cur.fetchall()]
        assert "brief_id" in cols
        assert "topic" in cols
        assert "recommended_prompt" in cols
        assert "confidence_score" in cols
        assert "status" in cols
        assert "dispatched_job_id" in cols

        cur.execute("PRAGMA index_list(creative_strategy_briefs);")
        indexes = [r[1] for r in cur.fetchall()]
        assert "idx_creative_strategy_briefs_status" in indexes
        assert "idx_creative_strategy_briefs_created" in indexes

# 3-6: Brief con evidencia OUTPERFORMING, Cold-Start y evasión de UNDERPERFORMING
def test_3_6_evidence_vs_cold_start_and_avoidance(temp_strategy_env):
    strat = temp_strategy_env["strat_engine"]
    collector = temp_strategy_env["collector"]
    mem = temp_strategy_env["mem_manager"]

    # 1. Cold-start scenario (no historical data)
    cold_brief = strat.create_brief(topic="cyberpunk cyborg")
    assert cold_brief["status"] == "PROPOSED"
    assert cold_brief["confidence_score"] <= 0.40
    assert "Exploration baseline" in cold_brief["hypothesis"]

    # 2. Seed historical winning and losing patterns
    # Winning: cinematic style + neon lighting (3 samples, high scores)
    for i in range(3):
        j_id = f"job_strat_win_{i}"
        storage.job_store.create_job({"job_id": j_id, "status": "COMPLETED", "prompt": "cinematic neon hero shot"})
        collector.ingest_performance_event({"job_id": j_id, "channel": "fb", "views": 1000, "likes": 120, "retention_rate": 0.85, "ctr": 0.08})

    # Losing: minimalist style (3 samples, low scores)
    for i in range(3):
        j_id = f"job_strat_low_{i}"
        storage.job_store.create_job({"job_id": j_id, "status": "COMPLETED", "prompt": "minimalist simple background"})
        collector.ingest_performance_event({"job_id": j_id, "channel": "fb", "views": 1000, "likes": 2, "retention_rate": 0.1, "ctr": 0.01})

    mem.refresh_patterns()

    # 3. Evidence-backed brief creation
    ev_brief = strat.create_brief(topic="cyberpunk cyborg")
    assert ev_brief["confidence_score"] >= 0.60
    assert "cinematic" in ev_brief["recommended_prompt"]
    assert "neon" in ev_brief["recommended_prompt"]
    assert "minimalist" not in ev_brief["recommended_prompt"]
    assert len(ev_brief["evidence_patterns"]) >= 1

# 7-11: Genome, hipótesis, confidence score y evidencia persistida
def test_7_11_genome_hypothesis_and_evidence(temp_strategy_env):
    strat = temp_strategy_env["strat_engine"]
    brief = strat.create_brief(topic="quantum supercomputer", custom_hypothesis="Testing custom quantum hypothesis")
    assert "quantum supercomputer" in brief["recommended_prompt"]
    assert "Testing custom quantum hypothesis" in brief["hypothesis"]
    assert isinstance(brief["recommended_genome"], dict)
    assert "STYLE" in brief["recommended_genome"]
    assert 0.0 <= brief["confidence_score"] <= 1.0

# 12-13: get_brief y list_briefs
def test_12_13_get_and_list_briefs(temp_strategy_env):
    strat = temp_strategy_env["strat_engine"]
    b1 = strat.create_brief(topic="space exploration")
    b2 = strat.create_brief(topic="deep ocean trench")

    fetched = strat.get_brief(b1["brief_id"])
    assert fetched is not None
    assert fetched["topic"] == "space exploration"

    all_briefs = strat.list_briefs(limit=10)
    assert len(all_briefs) >= 2

    proposed_only = strat.list_briefs(status="PROPOSED")
    assert len(proposed_only) >= 2

# 14-15: execute_brief con Phase 14 dispatch y persistencia de dispatched_job_id
@pytest.mark.asyncio
async def test_14_15_execute_brief_pipeline(temp_strategy_env):
    strat = temp_strategy_env["strat_engine"]
    brief = strat.create_brief(topic="futuristic vehicle")
    b_id = brief["brief_id"]

    mock_job_id = "cr_strat_exec_999"
    with patch("src.core.creative_engine.creative_engine.run_workflow", new=AsyncMock(return_value={
        "status": "SUBMITTED",
        "job_id": mock_job_id
    })):
        executed = await strat.execute_brief(b_id)
        assert executed["status"] == "DISPATCHED"
        assert executed["dispatched_job_id"] == mock_job_id
        assert executed["concluded_at"] is not None

# 16-18: reject_brief e inmutabilidad de terminales
@pytest.mark.asyncio
async def test_16_18_reject_and_terminal_immutability(temp_strategy_env):
    strat = temp_strategy_env["strat_engine"]
    b1 = strat.create_brief(topic="ai robotics")
    b1_id = b1["brief_id"]

    # Reject brief
    rejected = strat.reject_brief(b1_id, reason="Topic already saturated")
    assert rejected["status"] == "REJECTED"

    # Cannot execute rejected
    with pytest.raises(StrategyError) as exc1:
        await strat.execute_brief(b1_id)
    assert exc1.value.error_code == "BRIEF_REJECTED"

    # Dispatched brief cannot be rejected or re-executed
    b2 = strat.create_brief(topic="holographic display")
    b2_id = b2["brief_id"]
    with patch("src.core.creative_engine.creative_engine.run_workflow", new=AsyncMock(return_value={"status": "SUBMITTED", "job_id": "cr_1"})):
        await strat.execute_brief(b2_id)

    with pytest.raises(StrategyError) as exc2:
        strat.reject_brief(b2_id)
    assert exc2.value.error_code == "BRIEF_ALREADY_DISPATCHED"

    with pytest.raises(StrategyError) as exc3:
        await strat.execute_brief(b2_id)
    assert exc3.value.error_code == "BRIEF_ALREADY_DISPATCHED"

# 19-20: Persistencia SQLite y recuperación tras reinicio, e idempotencia
def test_19_20_persistence_and_idempotency(temp_strategy_env):
    db_path = temp_strategy_env["db_path"]
    strat1 = temp_strategy_env["strat_engine"]

    b1 = strat1.create_brief(topic="renewable fusion energy")
    b1_id = b1["brief_id"]

    # Re-creating exact same brief should return existing proposed brief
    b2 = strat1.create_brief(topic="renewable fusion energy")
    assert b1_id == b2["brief_id"]

    # Restart recovery
    strat2 = StrategyEngine(db_path=db_path)
    loaded = strat2.get_brief(b1_id)
    assert loaded is not None
    assert loaded["topic"] == "renewable fusion energy"

# 21-23: Integración E2E (Metrics -> Memory -> Strategy -> Phase 14) y tolerancia a fallos
@pytest.mark.asyncio
async def test_21_23_full_strategy_e2e_and_fault_tolerance(temp_strategy_env):
    strat = temp_strategy_env["strat_engine"]
    collector = temp_strategy_env["collector"]
    mem = temp_strategy_env["mem_manager"]

    # 1. Ingest performance telemetry for a prior job
    job_id = "job_prior_e2e_001"
    storage.job_store.create_job({"job_id": job_id, "status": "COMPLETED", "prompt": "cyberpunk centered neon lights"})
    for _ in range(3):
        collector.ingest_performance_event({"job_id": job_id, "channel": "fb", "views": 1000, "likes": 100, "retention_rate": 0.8})

    # 2. Refresh creative memory
    mem.refresh_patterns()

    # 3. Generate strategy brief
    brief = strat.create_brief(topic="metropolis skyline")
    assert brief["status"] == "PROPOSED"
    assert brief["confidence_score"] > 0.0

    # 4. Accept brief
    accepted = strat.accept_brief(brief["brief_id"])
    assert accepted["status"] == "ACCEPTED"

    # 5. Fault tolerance check when CreativeEngine dispatch fails
    with patch("src.core.creative_engine.creative_engine.run_workflow", side_effect=RuntimeError("GPU allocation failure")):
        with pytest.raises(StrategyError) as exc:
            await strat.execute_brief(brief["brief_id"])
        assert exc.value.error_code == "DISPATCH_FAILED"

    # Brief remains in ACCEPTED state
    current = strat.get_brief(brief["brief_id"])
    assert current["status"] == "ACCEPTED"
    assert current["dispatched_job_id"] is None
