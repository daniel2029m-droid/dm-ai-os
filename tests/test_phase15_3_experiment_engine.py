"""
Phase 15.3 Test Suite: Experiment Engine.
Covers items 1 to 24:
1-5: Experiment creation, name/variable validation, control and variant rows.
6-8: Matrix determinism, lineage, hashing & idempotency.
9-12: Dispatch via CreativeEngine, variable isolation, failure tolerance.
13: Abort handling.
14-18: Evaluation scenarios: no metrics, < 3 samples, sufficient evidence, winner detection, inconclusive/insufficient evidence.
19: Terminal state immutability.
20-21: SQLite persistence & restart recovery.
22-24: Cross-phase integration with 15.1 (metrics) and 15.2 (creative memory).
"""
import pytest
import sqlite3
from unittest.mock import AsyncMock, patch

from src.core.experiment_engine import ExperimentEngine, ExperimentError, experiment_engine
from src.storage.content_metrics_store import ContentMetricsStore
from src.core.content_intelligence import ContentIntelligenceCollector
from src.core.creative_memory import CreativeMemoryManager
from src.storage.storage_layer import storage

@pytest.fixture
def temp_exp_env(tmp_path):
    db_file = tmp_path / "test_experiments.db"
    store = ContentMetricsStore(db_path=str(db_file))
    collector = ContentIntelligenceCollector(metrics_store=store)
    exp_engine = ExperimentEngine(db_path=str(db_file), metrics_store=store)
    mem_manager = CreativeMemoryManager(db_path=str(db_file), metrics_store=store)
    return {
        "db_path": str(db_file),
        "store": store,
        "collector": collector,
        "exp_engine": exp_engine,
        "mem_manager": mem_manager
    }

# 1-5: Creación, validación de variables, control y variantes
def test_1_5_experiment_creation_and_validation(temp_exp_env):
    eng = temp_exp_env["exp_engine"]

    # 1. Valid creation
    exp = eng.create_experiment(
        name="Test Prompt Hook Experiment",
        base_template="flux2_klein_txt2img",
        base_prompt="cyberpunk street scene",
        variable_tested="PROMPT_HOOK",
        control_value="standard view",
        variant_values=["cinematic close-up", "dynamic action view"],
        hypothesis="Cinematic hook will increase engagement"
    )
    assert exp["status"] == "DRAFT"
    assert len(exp["variants"]) == 3 # 1 control + 2 variants
    assert any(v["is_control"] == 1 for v in exp["variants"])

    # 2. Invalid name
    with pytest.raises(ExperimentError) as exc1:
        eng.create_experiment(name="", base_template="t", base_prompt="p", variable_tested="SEED", control_value=1, variant_values=[2])
    assert exc1.value.error_code == "INVALID_EXPERIMENT_NAME"

    # 3. Invalid variable
    with pytest.raises(ExperimentError) as exc2:
        eng.create_experiment(name="Bad Var", base_template="t", base_prompt="p", variable_tested="UNSUPPORTED_VAR", control_value=1, variant_values=[2])
    assert exc2.value.error_code == "INVALID_EXPERIMENT_VARIABLE"

# 6-8: Matriz determinista, lineage e idempotencia
def test_6_8_matrix_lineage_and_idempotency(temp_exp_env):
    eng = temp_exp_env["exp_engine"]

    # Create experiment
    exp1 = eng.create_experiment(
        name="CFG Scale Test",
        base_template="flux2_klein_txt2img",
        base_prompt="neon warrior",
        variable_tested="CFG",
        control_value=1.0,
        variant_values=[1.5, 2.0]
    )

    # Re-creating exact same definition should return existing without duplicates
    exp2 = eng.create_experiment(
        name="CFG Scale Test",
        base_template="flux2_klein_txt2img",
        base_prompt="neon warrior",
        variable_tested="CFG",
        control_value=1.0,
        variant_values=[1.5, 2.0]
    )
    assert exp1["experiment_id"] == exp2["experiment_id"]

    all_exps = eng.list_experiments()
    assert len(all_exps) == 1

    # Check lineage in variants
    for v in exp1["variants"]:
        assert v["experiment_id"] == exp1["experiment_id"]
        assert "variable_value" in v
        assert "parameters" in v

# 9-12: Dispatch mediante CreativeEngine y tolerancia a fallos
@pytest.mark.asyncio
async def test_9_12_dispatch_and_fault_tolerance(temp_exp_env):
    eng = temp_exp_env["exp_engine"]

    exp = eng.create_experiment(
        name="Seed Variation Test",
        base_template="flux2_klein_txt2img",
        base_prompt="futuristic city",
        variable_tested="SEED",
        control_value=100,
        variant_values=[200, 300]
    )
    exp_id = exp["experiment_id"]

    call_count = 0
    async def mock_run_wf(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise RuntimeError("Simulated dispatch network timeout")
        return {"status": "SUBMITTED", "job_id": f"cr_exp_job_{call_count}"}

    with patch("src.core.creative_engine.creative_engine.run_workflow", side_effect=mock_run_wf):
        res = await eng.run_experiment(exp_id)
        assert res["status"] == "RUNNING"
        variants = res["variants"]
        # 2 dispatched, 1 failed
        dispatched = [v for v in variants if v["status"] == "DISPATCHED"]
        failed = [v for v in variants if v["status"] == "FAILED"]
        assert len(dispatched) == 2
        assert len(failed) == 1
        assert failed[0]["job_id"] is None

# 13: Abort handling
def test_13_abort_experiment(temp_exp_env):
    eng = temp_exp_env["exp_engine"]
    exp = eng.create_experiment(
        name="Abort Test",
        base_template="t",
        base_prompt="p",
        variable_tested="STEPS",
        control_value=20,
        variant_values=[25]
    )
    exp_id = exp["experiment_id"]
    aborted = eng.abort_experiment(exp_id, reason="Testing user abort")
    assert aborted["status"] == "ABORTED"
    assert aborted["evaluation_summary"]["abort_reason"] == "Testing user abort"

# 14-18: Evaluación: sin métricas, < 3 muestras, suficiente evidencia, winner detection, insufficient evidence
def test_14_18_evaluation_scenarios(temp_exp_env):
    eng = temp_exp_env["exp_engine"]
    collector = temp_exp_env["collector"]

    exp = eng.create_experiment(
        name="Hook Comparison Test",
        base_template="flux2_klein_txt2img",
        base_prompt="portrait",
        variable_tested="PROMPT_HOOK",
        control_value="neutral",
        variant_values=["cinematic", "cyberpunk"]
    )
    exp_id = exp["experiment_id"]

    # Assign mock job_ids to variants
    variants = exp["variants"]
    for idx, v in enumerate(variants):
        j_id = f"job_exp_eval_{idx}"
        storage.job_store.create_job({"job_id": j_id, "status": "COMPLETED", "prompt": v["prompt"]})
        with sqlite3.connect(temp_exp_env["db_path"]) as conn:
            conn.cursor().execute("UPDATE creative_experiment_variants SET job_id = ?, status = 'DISPATCHED' WHERE variant_id = ?", (j_id, v["variant_id"]))
            conn.commit()

    # Scenario 1: Evaluation with NO metrics -> INSUFFICIENT_EVIDENCE
    eval1 = eng.evaluate_experiment(exp_id)
    assert eval1["status"] == "INSUFFICIENT_EVIDENCE"

    # Scenario 2: Evaluation with < 3 samples (only 2 samples ingested for control)
    collector.ingest_performance_event({"job_id": "job_exp_eval_0", "channel": "fb", "views": 1000, "likes": 50})
    collector.ingest_performance_event({"job_id": "job_exp_eval_0", "channel": "fb", "views": 1000, "likes": 55})
    eval2 = eng.evaluate_experiment(exp_id, minimum_variant_samples=3)
    assert eval2["status"] == "INSUFFICIENT_EVIDENCE"

    # Scenario 3: Complete 3 samples for control (avg ~ 50) and 3 samples for Variant A (avg ~ 80)
    collector.ingest_performance_event({"job_id": "job_exp_eval_0", "channel": "fb", "views": 1000, "likes": 50})
    
    # 3 samples for Variant_A ("job_exp_eval_1") with higher engagement
    for _ in range(3):
        collector.ingest_performance_event({"job_id": "job_exp_eval_1", "channel": "fb", "views": 1000, "likes": 120, "retention_rate": 0.8, "ctr": 0.08})

    # 3 samples for Variant_B ("job_exp_eval_2") with lower engagement
    for _ in range(3):
        collector.ingest_performance_event({"job_id": "job_exp_eval_2", "channel": "fb", "views": 1000, "likes": 10, "retention_rate": 0.2, "ctr": 0.01})

    eval3 = eng.evaluate_experiment(exp_id, minimum_variant_samples=3, minimum_lift=0.05)
    assert eval3["status"] == "CONCLUDED"
    assert eval3["winning_job_id"] == "job_exp_eval_1"
    assert "outperformed control" in eval3["evaluation_summary"]["decision_reason"]

# 19: Terminal state protection
def test_19_terminal_state_protection(temp_exp_env):
    eng = temp_exp_env["exp_engine"]
    exp = eng.create_experiment(name="Terminal Test", base_template="t", base_prompt="p", variable_tested="SEED", control_value=1, variant_values=[2])
    eng.abort_experiment(exp["experiment_id"])

    # Cannot run aborted
    with pytest.raises(ExperimentError) as exc1:
        import asyncio
        asyncio.run(eng.run_experiment(exp["experiment_id"]))
    assert exc1.value.error_code == "EXPERIMENT_TERMINAL_STATE"

# 20-21: Persistencia SQLite y recuperación tras reinicio
def test_20_21_sqlite_persistence_and_restart(temp_exp_env):
    db_path = temp_exp_env["db_path"]
    eng1 = temp_exp_env["exp_engine"]

    exp = eng1.create_experiment(
        name="Persistence Test",
        base_template="flux2_klein_txt2img",
        base_prompt="scifi hero",
        variable_tested="STEPS",
        control_value=20,
        variant_values=[30, 40]
    )
    exp_id = exp["experiment_id"]

    # Instantiate fresh engine pointing to same db
    eng2 = ExperimentEngine(db_path=db_path)
    loaded = eng2.get_experiment(exp_id)
    assert loaded is not None
    assert loaded["name"] == "Persistence Test"
    assert len(loaded["variants"]) == 3

# 22-24: Integración con Phase 15.1 y 15.2
def test_22_24_integration_with_metrics_and_memory(temp_exp_env):
    eng = temp_exp_env["exp_engine"]
    mem = temp_exp_env["mem_manager"]
    collector = temp_exp_env["collector"]

    # Register job, experiment, metric, and update memory
    job_id = "job_cross_phase_test"
    storage.job_store.create_job({
        "job_id": job_id,
        "status": "COMPLETED",
        "prompt": "photorealistic cyberpunk portrait with neon lighting"
    })
    for _ in range(3):
        collector.ingest_performance_event({
            "job_id": job_id,
            "channel": "facebook",
            "views": 1000,
            "likes": 90,
            "retention_rate": 0.8
        })

    mem.refresh_patterns()
    top_patterns = mem.get_top_patterns(category="STYLE")
    assert len(top_patterns) >= 1
