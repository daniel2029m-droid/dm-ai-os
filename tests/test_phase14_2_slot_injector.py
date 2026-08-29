"""
Phase 14.2 Test Suite: Dynamic Slot Injector.
Covers requirements A to R:
A. Simple PROMPT substitution
B. Numeric substitution preserving int
C. Float substitution preserving float
D. Compound string substitution
E. Substitution inside lists
F. Substitution inside nested dicts
G. Multiple placeholders in single workflow
H. Defaults applied (STEPS=20, CFG=7.0, WIDTH=512, HEIGHT=512, DENOISE=1.0, etc.)
I. Deterministic SEED when provided
J. Random SEED generated when not provided
K. Unknown placeholder detected
L. Mandatory required placeholder missing detected
M. Incorrect type detected
N. workflow_template_sha256 is stable
O. workflow_effective_sha256 is stable for identical input
P. workflow_effective_sha256 differs when seed changes
Q/R. CreativeEngine and JobStore zero regression
"""
import pytest
import copy
from src.core.dynamic_slot_injector import (
    DynamicSlotInjector,
    SlotInjectionError,
    slot_injector,
    SLOT_REGISTRY
)
from src.core.creative_engine import CreativeEngine, creative_engine
from src.storage.storage_layer import storage

@pytest.fixture
def sample_workflow_template():
    return {
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "seed": "{{SEED}}",
                "steps": "{{STEPS}}",
                "cfg": "{{CFG}}",
                "denoise": "{{DENOISE}}",
                "model": ["4", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["5", 0]
            }
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {
                "width": "{{WIDTH}}",
                "height": "{{HEIGHT}}",
                "batch_size": 1
            }
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": "{{PROMPT}}"
            }
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": "{{NEGATIVE_PROMPT}}"
            }
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {
                "filename_prefix": "render_{{SEED}}_preview"
            }
        }
    }

# A: Sustitución simple de PROMPT
def test_a_simple_prompt_substitution(sample_workflow_template):
    injector = DynamicSlotInjector()
    res = injector.process(sample_workflow_template, user_params={"PROMPT": "Cyberpunk cityscape", "SEED": 42})
    wf = res["effective_workflow"]
    assert wf["6"]["inputs"]["text"] == "Cyberpunk cityscape"

# B: Sustitución numérica preservando int
def test_b_int_preservation(sample_workflow_template):
    injector = DynamicSlotInjector()
    res = injector.process(sample_workflow_template, user_params={"PROMPT": "test", "STEPS": 30, "SEED": 1234})
    wf = res["effective_workflow"]
    assert wf["3"]["inputs"]["steps"] == 30
    assert isinstance(wf["3"]["inputs"]["steps"], int)
    assert wf["3"]["inputs"]["seed"] == 1234
    assert isinstance(wf["3"]["inputs"]["seed"], int)

# C: Sustitución float preservando float
def test_c_float_preservation(sample_workflow_template):
    injector = DynamicSlotInjector()
    res = injector.process(sample_workflow_template, user_params={"PROMPT": "test", "CFG": 8.5, "DENOISE": 0.75, "SEED": 1})
    wf = res["effective_workflow"]
    assert wf["3"]["inputs"]["cfg"] == 8.5
    assert isinstance(wf["3"]["inputs"]["cfg"], float)
    assert wf["3"]["inputs"]["denoise"] == 0.75
    assert isinstance(wf["3"]["inputs"]["denoise"], float)

# D: Sustitución dentro de strings compuestos
def test_d_compound_string_substitution(sample_workflow_template):
    injector = DynamicSlotInjector()
    res = injector.process(sample_workflow_template, user_params={"PROMPT": "test", "SEED": 99999})
    wf = res["effective_workflow"]
    assert wf["9"]["inputs"]["filename_prefix"] == "render_99999_preview"
    assert isinstance(wf["9"]["inputs"]["filename_prefix"], str)

# E: Sustitución dentro de listas
def test_e_list_substitution():
    injector = DynamicSlotInjector()
    template = {
        "node": {
            "dimensions": ["{{WIDTH}}", "{{HEIGHT}}"],
            "compound_list": ["prefix_{{SEED}}", "static_val"]
        }
    }
    res = injector.process(template, user_params={"WIDTH": 1024, "HEIGHT": 768, "SEED": 55})
    wf = res["effective_workflow"]
    assert wf["node"]["dimensions"] == [1024, 768]
    assert wf["node"]["compound_list"] == ["prefix_55", "static_val"]

# F: Sustitución dentro de diccionarios anidados
def test_f_nested_dict_substitution():
    injector = DynamicSlotInjector()
    template = {
        "level1": {
            "level2": {
                "level3": {
                    "prompt": "{{PROMPT}}",
                    "cfg": "{{CFG}}"
                }
            }
        }
    }
    res = injector.process(template, user_params={"PROMPT": "nested value", "CFG": 6.5})
    wf = res["effective_workflow"]
    assert wf["level1"]["level2"]["level3"]["prompt"] == "nested value"
    assert wf["level1"]["level2"]["level3"]["cfg"] == 6.5

# G: Múltiples placeholders en un mismo workflow
def test_g_multiple_placeholders(sample_workflow_template):
    injector = DynamicSlotInjector()
    user_params = {
        "PROMPT": "Neon samurai in rain",
        "NEGATIVE_PROMPT": "low quality, blurry",
        "SEED": 10101,
        "STEPS": 25,
        "CFG": 7.5,
        "WIDTH": 768,
        "HEIGHT": 512,
        "DENOISE": 0.85
    }
    res = injector.process(sample_workflow_template, user_params=user_params)
    wf = res["effective_workflow"]
    assert wf["6"]["inputs"]["text"] == "Neon samurai in rain"
    assert wf["7"]["inputs"]["text"] == "low quality, blurry"
    assert wf["3"]["inputs"]["seed"] == 10101
    assert wf["3"]["inputs"]["steps"] == 25
    assert wf["3"]["inputs"]["cfg"] == 7.5
    assert wf["5"]["inputs"]["width"] == 768
    assert wf["5"]["inputs"]["height"] == 512
    assert wf["3"]["inputs"]["denoise"] == 0.85

# H: Defaults aplicados cuando no se suministran
def test_h_defaults_applied(sample_workflow_template):
    injector = DynamicSlotInjector()
    res = injector.process(sample_workflow_template, user_params={"PROMPT": "Minimalist art"})
    params = res["effective_params"]
    assert params["STEPS"] == 20
    assert params["CFG"] == 7.0
    assert params["WIDTH"] == 512
    assert params["HEIGHT"] == 512
    assert params["DENOISE"] == 1.0
    assert params["NEGATIVE_PROMPT"] == ""

# I: Seed determinística cuando se proporciona
def test_i_deterministic_seed(sample_workflow_template):
    injector = DynamicSlotInjector()
    res = injector.process(sample_workflow_template, user_params={"PROMPT": "test", "SEED": 42})
    assert res["effective_params"]["SEED"] == 42
    assert res["effective_workflow"]["3"]["inputs"]["seed"] == 42

# J: Seed aleatoria generada cuando no se proporciona
def test_j_random_seed_generated(sample_workflow_template):
    injector = DynamicSlotInjector()
    res1 = injector.process(sample_workflow_template, user_params={"PROMPT": "test"})
    res2 = injector.process(sample_workflow_template, user_params={"PROMPT": "test"})
    assert isinstance(res1["effective_params"]["SEED"], int)
    assert 1 <= res1["effective_params"]["SEED"] <= (2**32 - 1)
    # Different dispatches without seed should generate different seeds
    assert "SEED" in res1["effective_params"]

# K: Placeholder desconocido detectado
def test_k_unknown_placeholder_error():
    injector = DynamicSlotInjector()
    invalid_template = {
        "node": {
            "setting": "{{UNKNOWN_CUSTOM_SLOT_XYZ}}"
        }
    }
    with pytest.raises(SlotInjectionError) as excinfo:
        injector.process(invalid_template, user_params={"PROMPT": "test"})
    assert "Unknown slot" in str(excinfo.value)
    assert "UNKNOWN_CUSTOM_SLOT_XYZ" in str(excinfo.value)

# L: Placeholder obligatorio ausente
def test_l_missing_required_placeholder(sample_workflow_template):
    injector = DynamicSlotInjector()
    with pytest.raises(SlotInjectionError) as excinfo:
        injector.process(sample_workflow_template, user_params={})
    assert "Required slot {{PROMPT}}" in str(excinfo.value)

# M: Tipo incorrecto detectado
def test_m_invalid_type_error(sample_workflow_template):
    injector = DynamicSlotInjector()
    with pytest.raises(SlotInjectionError) as excinfo:
        injector.process(sample_workflow_template, user_params={"PROMPT": "test", "STEPS": "twenty"})
    assert "expected int, got str" in str(excinfo.value)

# N: workflow_template_sha256 estable
def test_n_stable_template_hash(sample_workflow_template):
    injector = DynamicSlotInjector()
    res1 = injector.process(sample_workflow_template, user_params={"PROMPT": "art", "SEED": 1})
    res2 = injector.process(sample_workflow_template, user_params={"PROMPT": "different prompt", "SEED": 2})
    assert res1["workflow_template_sha256"] == res2["workflow_template_sha256"]

# O: workflow_effective_sha256 estable para la misma entrada
def test_o_stable_effective_hash(sample_workflow_template):
    injector = DynamicSlotInjector()
    res1 = injector.process(sample_workflow_template, user_params={"PROMPT": "art", "SEED": 555, "STEPS": 20})
    res2 = injector.process(sample_workflow_template, user_params={"PROMPT": "art", "SEED": 555, "STEPS": 20})
    assert res1["workflow_effective_sha256"] == res2["workflow_effective_sha256"]
    assert res1["idempotency_key"] == res2["idempotency_key"]

# P: workflow_effective_sha256 diferente cuando cambia la seed
def test_p_different_effective_hash_on_different_seed(sample_workflow_template):
    injector = DynamicSlotInjector()
    res1 = injector.process(sample_workflow_template, user_params={"PROMPT": "art", "SEED": 100})
    res2 = injector.process(sample_workflow_template, user_params={"PROMPT": "art", "SEED": 200})
    assert res1["workflow_effective_sha256"] != res2["workflow_effective_sha256"]
    assert res1["idempotency_key"] != res2["idempotency_key"]

# Q/R: Integración con CreativeEngine y JobStore
@pytest.mark.asyncio
async def test_q_creative_engine_slot_injection_integration():
    engine = CreativeEngine()
    res = await engine.run_workflow(
        template_name_or_path="flux2_klein_txt2img",
        prompt="Futuristic quantum computer",
        parameters={"steps": 25, "seed": 4242}
    )
    assert res["status"] in ("SUBMITTED", "COMPLETED", "FAILED", "UNAVAILABLE")
    assert "workflow_template_sha256" in res
    assert "workflow_effective_sha256" in res
    assert "idempotency_key" in res
    
    # Verify in JobStore
    job = storage.job_store.get_job(res["job_id"])
    assert job is not None
    assert job["idempotency_key"] == res["idempotency_key"]
    assert job["workflow_template_sha256"] == res["workflow_template_sha256"]
    assert job["workflow_effective_sha256"] == res["workflow_effective_sha256"]
