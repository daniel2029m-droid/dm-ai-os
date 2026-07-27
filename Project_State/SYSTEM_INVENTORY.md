# SYSTEM INVENTORY
**Last Updated:** 2026-07-23T12:39:00-03:00 | **Source:** Audit/

---

## Hardware
| Component | Detail |
|---|---|
| **OS** | Windows 11 Pro (Build 26100, 64-bit) |
| **CPU** | AMD Ryzen 5 4600G — 6 cores / 12 threads @ 3701 MHz |
| **RAM** | 15.37 GB total / 4.97 GB free at audit time |
| **GPU** | AMD Radeon(TM) Graphics — 512 MB VRAM (integrated iGPU) |
| **Disk C:** | 237.63 GB total / 13.04 GB free ⚠️ LOW |
| **Motherboard** | ASRock B450M-HDV R4.0 |
| **BIOS** | AMI P10.10 |

> ⚠️ **CRITICAL**: Only 13 GB free on C:. Project must be mindful of disk usage.  
> ⚠️ **NO dedicated GPU** — AMD iGPU only (512 MB VRAM). RunPod required for all GPU workloads.

---

## Languages & Runtimes
| Tool | Version | Path | Status |
|---|---|---|---|
| Python | 3.13.5 | `C:\Python313\python.exe` | ✅ Installed |
| Python 3.10 | 3.10.x | `%LOCALAPPDATA%\Programs\Python\Python310` | ✅ Installed (secondary) |
| pip | 25.3 | bundled with Python 3.13 | ✅ Installed |
| Node.js | 22.17.0 | `C:\Program Files\nodejs\node.exe` | ✅ Installed |
| npm | ERROR (Win32 issue) | — | ⚠️ Broken — npm.cmd not resolving |
| .NET | detected in PATH | `C:\Program Files\dotnet\` | ✅ Installed |

---

## Dev Tools
| Tool | Version | Status |
|---|---|---|
| Git | 2.52.0 | ✅ Installed — user: Mr-Q8 / moradalimpieza@gmail.com |
| VS Code | Installed | ✅ Installed — `%LOCALAPPDATA%\Programs\Microsoft VS Code` |
| PowerShell | 5.1.26100.6899 | ✅ Installed |
| Chocolatey | Installed | ✅ in PATH |
| Docker | — | ❌ NOT FOUND |
| WSL | — | ❌ NOT INSTALLED (no distros) |

---

## AI / LLM Tools
| Tool | Version | Status |
|---|---|---|
| Ollama | 0.32.1 | ✅ Installed — `%LOCALAPPDATA%\Programs\Ollama` |
| LM Studio | Installed | ✅ (`%USERPROFILE%\.lmstudio\bin` in PATH) |
| Pinokio | Installed | ✅ (data on D:\pinokio_data) |
| llama.cpp | — | ❌ NOT FOUND |
| ComfyUI | — | ❌ NOT FOUND locally |
| Open WebUI | — | ❌ NOT FOUND locally |
| n8n | — | ❌ NOT INSTALLED |

---

## Ollama Models (Local)
| Model | Size | ID |
|---|---|---|
| qwen2.5:1.5b | 986 MB | 65ec06548149 |
| qwen2.5:0.5b | 397 MB | a8b0c5157701 |

---

## Browsers
| Browser | Status |
|---|---|
| Microsoft Edge | ✅ Installed |
| Google Chrome | ✅ Installed |
| Firefox | ✅ Installed |
| Brave | ❌ Not installed |
| Opera | ❌ Not installed |

---

## VS Code Extensions
| Extension |
|---|
| ms-dotnettools.csdevkit |
| ms-dotnettools.csharp |
| ms-dotnettools.vscode-dotnet-runtime |
| qwenlm.qwen-code-vscode-ide-companion |
| rangav.vscode-thunder-client |
| rooveterinaryinc.roo-cline |

---

## Storage Paths (AI/Data)
| Variable | Path |
|---|---|
| HF_HOME | `D:\hf_cache` |
| HF_MODULES_CACHE | `D:\hf_cache\modules` |
| TRANSFORMERS_CACHE | `D:\hf_cache\transformers` |
| LMSTUDIO_HOME | `D:\lmstudio\data` |
| PINOKIO_HOME | `D:\pinokio\data` |
| PINOKIO_MODELS | `D:\pinokio_data\models` |
| PINOKIO_CACHE | `D:\pinokio_data\cache` |
| GRADLE_USER_HOME | `D:\gradle` |

> ✅ D: drive detected via env vars — likely a second drive with more space (used for models/data)

---

## API Keys Status
| Key | Status |
|---|---|
| OPENAI_API_KEY | ❌ NOT SET |
| ANTHROPIC_API_KEY | ❌ NOT SET |
| RUNPOD_API_KEY | ❌ NOT SET |
| HUGGINGFACE_TOKEN | ❌ NOT SET |
| GOOGLE_API_KEY | ❌ NOT SET |
| GROQ_API_KEY | ❌ NOT SET |
| OLLAMA_HOST | ✅ SET (0.0.0.0) |

---

## Existing AI Projects (detected)
| Path |
|---|
| `C:\Users\moral\.agents` |
| `C:\Users\moral\.ollama` |
| `C:\Users\moral\Agente_Resultados` |
| `C:\Users\moral\.bito\codeReviewAgent` |
| `C:\Users\moral\.gemini\antigravity\scratch\agent_bot` |
| `C:\Users\moral\.gemini\antigravity\scratch\multi_agent_system` |

---

## Network
- OLLAMA_HOST = `0.0.0.0` (exposed to all interfaces)
- OLLAMA_ORIGINS = `*`
- No Docker networking detected
