# MODELS
**Last Updated:** 2026-07-23T12:39:00-03:00 | **Source:** Audit/ollama.json + Audit/models.json

---

## Ollama Models (Local)
| Model | Size | ID | VRAM Est. | Status |
|---|---|---|---|---|
| qwen2.5:1.5b | 986 MB | 65ec06548149 | ~1.2 GB | ✅ Ready |
| qwen2.5:0.5b | 397 MB | a8b0c5157701 | ~512 MB | ✅ Ready |

**Ollama ModelsDir:** `C:\Users\moral\.ollama\models`

---

## GGUF Files
> Scan result: NONE found in standard locations.

---

## LM Studio
> Installed. Data at `D:\lmstudio\data`. Models not audited (LM Studio manages its own registry).
> To audit: open LM Studio → check loaded models manually.

---

## Pinokio
> Models dir: `D:\pinokio_data\models`. Contents not audited.

---

## GPU Constraint
> ⚠️ NO dedicated GPU. AMD iGPU = 512 MB VRAM only.
> All GPU workloads (image gen, video gen, large model inference) → RunPod.
> Local inference limited to: qwen2.5:1.5b and smaller (Ollama).

---

## Recommended Model Strategy
| Use Case | Backend | Model |
|---|---|---|
| Agent reasoning (local) | Ollama | qwen2.5:1.5b |
| Ultra-light tasks | Ollama | qwen2.5:0.5b |
| Image generation | RunPod / ComfyUI | SDXL / Flux (TBD) |
| Video generation | RunPod | CogVideoX / Wan (TBD) |
| Large reasoning | RunPod (budget: $10) | Qwen3 / Llama (TBD) |
