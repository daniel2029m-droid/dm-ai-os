# RunPod Video AI Models Evaluation Report — DM AI OS

## Overview
This document evaluates Video AI models available for self-hosting on RunPod GPU infrastructure (RTX 4090 / RTX 5090 / L40S) for DM AI OS media generation tasks.

---

## Model Evaluation Matrix

| Model | Type | Approx VRAM | Capabilities | Max Resolution | Speed | Quality | Est. Cost / Min GPU | Workflow | Integration Status |
|---|---|---|---|---|---|---|---|---|---|
| **Wan 2.2 I2V** | Image-to-Video | 16 - 24 GB | I2V, T2V | 720p / 1080p | Fast (20-30s/clip) | High | ~$0.005 | ComfyUI / API | **Primary Recommended** |
| **Wan 2.2 TI2V-5B** | Text/Image-to-Video (5B) | 24 - 32 GB | T2V, I2V | 720p / 1080p | Moderate (45s/clip) | Very High | ~$0.008 | ComfyUI / API | **Recommended (High Quality)** |
| **Wan 2.2 + VACE** | Motion Transfer | 24 - 40 GB | Ref Image + Ref Video | 720p | Moderate (60s/clip) | High (Pose Transfer) | ~$0.010 | ComfyUI VACE Node | **Motion Transfer Recommended** |
| **LTX-Video 2.x** | Real-time Video | 12 - 16 GB | T2V, I2V | 512p / 720p | Ultra Fast (5-10s) | Good | ~$0.002 | ComfyUI / Diffusers | Secondary / Lightweight |
| **HunyuanVideo** | Video Foundation Model | 32 - 80 GB | T2V, I2V | 720p / 1080p | Slow (90s-120s) | Ultra High | ~$0.025 | ComfyUI / Native | Heavyweight / Premium |

---

## Detailed Model Breakdown

### 1. Wan 2.2 I2V & TI2V-5B (Primary Recommendation)
- **Use Case**: Animate static FLUX.2 generated portrait images into dynamic social media reels and clips.
- **VRAM Requirements**: Fits comfortably on single RTX 4090 (24GB VRAM) or RTX 5090 (32GB VRAM).
- **Quality / Speed Trade-off**: Excellent photorealism and temporal stability for facial features and clothing textures.
- **Workflow**: `workflows/runpod/wan22_i2v.json`

### 2. Wan 2.2 + VACE Motion Transfer
- **Use Case**: Take a reference character photo (e.g. Valeria influencer image) AND a reference motion video (e.g. dance or gesture video), and generate a new video of Valeria performing the exact same motion.
- **Capabilities**: Preserves character appearance while adopting motion trajectory from reference video.
- **Workflow**: `workflows/runpod/wan22_motion_transfer.json`

### 3. LTX-Video 2.x
- **Use Case**: Quick previews, draft animations, or fast real-time content generation when latency is critical.
- **VRAM Requirements**: Low VRAM usage (<16GB). Runs on budget GPUs.

### 4. HunyuanVideo (Tencent)
- **Use Case**: Ultra high fidelity cinematic commercial video rendering.
- **Notes**: High VRAM consumption (requires A100 or L40S/RTX 5090). Best used as premium fallback for high-end campaigns.

---

## Cost Control & Deployment Guidelines
1. **Auto-Start / Auto-Stop**: GPUs are automatically spun up on request and stopped when idle (`RUNPOD_IDLE_TIMEOUT_SECONDS=120`).
2. **Persistence**: Models are pre-stored on RunPod Network Volumes (`RUNPOD_NETWORK_VOLUME_ID`) so pod startup time is under 15-20 seconds.
