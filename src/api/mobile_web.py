"""
DM AI OS — iPhone Mobile Remote Client (PWA) v1.5.0
=====================================================
Provides a touch-optimized, high-aesthetic presentation layer for iPhone.
Features:
- AI Router Selector (Auto, Claude, Gemini, Grok, GPT OSS, Qwen Local, DeepSeek Local, Higgsfield AI)
- Settings > AI Providers Panel (Status, Account, Latency, Test, Change Account, Logout)
- Hardware Manager & Local Model Manager (Ollama, Whisper, XTTS, Piper)
- Provider Call History Log
"""

def get_mobile_html(api_url: str, tunnel_url: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
    <title>DM AI OS — Remote Terminal</title>
    
    <!-- PWA & iOS Meta Tags -->
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="apple-mobile-web-app-title" content="DM AI OS">
    <meta name="theme-color" content="#0f172a">
    <link rel="manifest" href="/manifest.json">
    <link rel="apple-touch-icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><rect width='100' height='100' rx='20' fill='%230f172a'/><text x='50' y='65' font-size='50' text-anchor='middle' fill='%2338bdf8'>DM</text></svg>">

    <!-- Modern Typography -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Fira+Code:wght@400;500&display=swap" rel="stylesheet">

    <style>
        :root {{
            --bg-dark: #070b14;
            --bg-card: rgba(15, 23, 42, 0.75);
            --bg-card-border: rgba(56, 189, 248, 0.15);
            --accent-cyan: #38bdf8;
            --accent-purple: #8b5cf6;
            --accent-green: #34d399;
            --accent-red: #f43f5e;
            --accent-yellow: #fbbf24;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --safe-bottom: env(safe-area-inset-bottom, 20px);
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            -webkit-tap-highlight-color: transparent;
            touch-action: manipulation;
        }}

        body {{
            background-color: var(--bg-dark);
            color: var(--text-main);
            height: 100vh;
            display: flex;
            flex-direction: column;
            overflow: hidden;
            background-image: 
                radial-gradient(circle at 15% 15%, rgba(56, 189, 248, 0.08) 0%, transparent 40%),
                radial-gradient(circle at 85% 85%, rgba(139, 92, 246, 0.08) 0%, transparent 40%);
        }}

        /* Header Bar */
        .app-header {{
            background: rgba(15, 23, 42, 0.85);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            padding: 12px 16px;
            padding-top: max(12px, env(safe-area-inset-top));
            border-bottom: 1px solid var(--bg-card-border);
            display: flex;
            align-items: center;
            justify-content: space-between;
            z-index: 100;
        }}

        .brand-title {{
            font-size: 1.1rem;
            font-weight: 700;
            background: linear-gradient(135deg, #38bdf8, #8b5cf6);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        .status-badge {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: rgba(6, 95, 70, 0.4);
            border: 1px solid rgba(52, 211, 153, 0.3);
            color: #34d399;
            padding: 4px 10px;
            border-radius: 999px;
            font-size: 0.75rem;
            font-weight: 600;
        }}

        .pulse-dot {{
            width: 8px;
            height: 8px;
            background: #34d399;
            border-radius: 50%;
            animation: pulse 1.5s infinite;
        }}

        @keyframes pulse {{
            0% {{ transform: scale(0.95); box-shadow: 0 0 0 0 rgba(52, 211, 153, 0.7); }}
            70% {{ transform: scale(1); box-shadow: 0 0 0 6px rgba(52, 211, 153, 0); }}
            100% {{ transform: scale(0.95); box-shadow: 0 0 0 0 rgba(52, 211, 153, 0); }}
        }}

        /* Main Container */
        .main-container {{
            flex: 1;
            position: relative;
            overflow: hidden;
        }}

        .tab-content {{
            position: absolute;
            top: 0; left: 0; right: 0; bottom: 0;
            overflow-y: auto;
            padding: 16px;
            display: none;
            -webkit-overflow-scrolling: touch;
        }}

        .tab-content.active {{
            display: block;
        }}

        /* Chat Tab */
        #chat-tab {{
            padding: 0;
            display: none;
            flex-direction: column;
            height: 100%;
        }}

        #chat-tab.active {{
            display: flex;
        }}

        .chat-messages {{
            flex: 1;
            overflow-y: auto;
            padding: 16px;
            display: flex;
            flex-direction: column;
            gap: 12px;
        }}

        .msg-bubble {{
            max-width: 85%;
            padding: 12px 16px;
            border-radius: 18px;
            font-size: 0.92rem;
            line-height: 1.45;
            word-wrap: break-word;
            animation: fadeIn 0.2s ease-out;
        }}

        @keyframes fadeIn {{
            from {{ opacity: 0; transform: translateY(6px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}

        .msg-user {{
            align-self: flex-end;
            background: linear-gradient(135deg, #0284c7, #6d28d9);
            color: #fff;
            border-bottom-right-radius: 4px;
            box-shadow: 0 4px 12px rgba(2, 132, 199, 0.25);
        }}

        .msg-assistant {{
            align-self: flex-start;
            background: rgba(30, 41, 59, 0.85);
            border: 1px solid rgba(255, 255, 255, 0.08);
            color: var(--text-main);
            border-bottom-left-radius: 4px;
        }}

        /* Input Bar */
        .chat-input-area {{
            background: rgba(15, 23, 42, 0.9);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            border-top: 1px solid var(--bg-card-border);
            padding: 10px 14px;
            display: flex;
            flex-direction: column;
            gap: 8px;
        }}

        .router-bar {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 8px;
            padding-bottom: 2px;
        }}

        .router-select {{
            background: rgba(7, 11, 20, 0.8);
            border: 1px solid var(--bg-card-border);
            color: var(--accent-cyan);
            border-radius: 8px;
            padding: 4px 10px;
            font-size: 0.78rem;
            font-weight: 600;
            outline: none;
            cursor: pointer;
        }}

        .quick-pills {{
            display: flex;
            gap: 8px;
            overflow-x: auto;
            padding-bottom: 4px;
            scrollbar-width: none;
        }}

        .quick-pill {{
            background: rgba(56, 189, 248, 0.1);
            border: 1px solid rgba(56, 189, 248, 0.25);
            color: var(--accent-cyan);
            padding: 5px 12px;
            border-radius: 999px;
            font-size: 0.75rem;
            white-space: nowrap;
            cursor: pointer;
        }}

        .input-controls {{
            display: flex;
            align-items: flex-end;
            gap: 8px;
        }}

        .chat-textarea {{
            flex: 1;
            background: rgba(7, 11, 20, 0.7);
            border: 1px solid var(--bg-card-border);
            border-radius: 20px;
            color: var(--text-main);
            padding: 10px 14px;
            font-size: 0.95rem;
            resize: none;
            max-height: 100px;
            min-height: 42px;
            outline: none;
        }}

        .chat-textarea:focus {{
            border-color: var(--accent-cyan);
        }}

        .icon-btn {{
            background: rgba(30, 41, 59, 0.8);
            border: 1px solid var(--bg-card-border);
            color: var(--accent-cyan);
            width: 42px;
            height: 42px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.1rem;
            cursor: pointer;
            transition: all 0.2s;
            flex-shrink: 0;
        }}

        .send-btn {{
            background: linear-gradient(135deg, #38bdf8, #8b5cf6);
            color: #0f172a;
            border: none;
            font-weight: 700;
        }}

        .preview-box {{
            display: none;
            align-items: center;
            gap: 8px;
            background: rgba(30, 41, 59, 0.6);
            padding: 6px 12px;
            border-radius: 10px;
            font-size: 0.8rem;
            color: var(--accent-cyan);
        }}

        /* Cards & Components */
        .card {{
            background: var(--bg-card);
            border: 1px solid var(--bg-card-border);
            border-radius: 16px;
            padding: 18px;
            margin-bottom: 14px;
            backdrop-filter: blur(12px);
        }}

        .card-title {{
            font-size: 1rem;
            font-weight: 600;
            color: var(--accent-cyan);
            margin-bottom: 10px;
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        .grid-2 {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
        }}

        .agent-card {{
            background: rgba(30, 41, 59, 0.6);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 12px;
            padding: 14px;
            text-align: center;
            cursor: pointer;
            transition: all 0.2s;
        }}

        .agent-card:active {{
            transform: scale(0.97);
            border-color: var(--accent-cyan);
        }}

        .agent-icon {{
            font-size: 1.8rem;
            margin-bottom: 6px;
        }}

        .agent-name {{
            font-size: 0.85rem;
            font-weight: 600;
            color: var(--text-main);
        }}

        .agent-desc {{
            font-size: 0.7rem;
            color: var(--text-muted);
            margin-top: 4px;
        }}

        .metric-row {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 8px 0;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            font-size: 0.85rem;
        }}

        .metric-label {{
            color: var(--text-muted);
        }}

        .metric-val {{
            font-family: 'Fira Code', monospace;
            color: var(--text-main);
            font-weight: 500;
        }}

        .action-input {{
            width: 100%;
            background: rgba(7, 11, 20, 0.8);
            border: 1px solid var(--bg-card-border);
            border-radius: 10px;
            padding: 10px;
            color: var(--text-main);
            margin-bottom: 10px;
            font-size: 0.9rem;
        }}

        .primary-btn {{
            width: 100%;
            background: linear-gradient(135deg, #38bdf8, #8b5cf6);
            color: #0f172a;
            border: none;
            padding: 12px;
            border-radius: 10px;
            font-weight: 700;
            font-size: 0.95rem;
            cursor: pointer;
        }}

        .btn-small {{
            padding: 6px 12px;
            font-size: 0.78rem;
            border-radius: 6px;
            border: none;
            font-weight: 600;
            cursor: pointer;
        }}

        .btn-cyan {{ background: rgba(56,189,248,0.2); color: #38bdf8; border: 1px solid #38bdf8; }}
        .btn-purple {{ background: rgba(139,92,246,0.2); color: #c084fc; border: 1px solid #c084fc; }}
        .btn-red {{ background: rgba(244,63,94,0.2); color: #f43f5e; border: 1px solid #f43f5e; }}

        .provider-item {{
            background: rgba(7, 11, 20, 0.6);
            border: 1px solid var(--bg-card-border);
            border-radius: 12px;
            padding: 12px;
            margin-bottom: 10px;
        }}

        .provider-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 8px;
        }}

        .provider-actions {{
            display: flex;
            gap: 6px;
            margin-top: 10px;
            flex-wrap: wrap;
        }}

        /* Bottom Navigation */
        .nav-tabs {{
            background: rgba(15, 23, 42, 0.95);
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            border-top: 1px solid var(--bg-card-border);
            display: flex;
            justify-content: space-around;
            padding: 8px 0;
            padding-bottom: max(8px, env(safe-area-inset-bottom));
        }}

        .tab-btn {{
            background: none;
            border: none;
            color: var(--text-muted);
            display: flex;
            flex-direction: column;
            align-items: center;
            font-size: 0.7rem;
            gap: 3px;
            cursor: pointer;
            flex: 1;
        }}

        .tab-btn.active {{
            color: var(--accent-cyan);
        }}

        .tab-icon {{
            font-size: 1.2rem;
        }}

        pre {{
            background: rgba(7, 11, 20, 0.9);
            padding: 10px;
            border-radius: 8px;
            font-family: 'Fira Code', monospace;
            font-size: 0.78rem;
            overflow-x: auto;
            color: #38bdf8;
            margin-top: 6px;
            white-space: pre-wrap;
            word-break: break-all;
        }}

        /* Lightbox Fullscreen Modal */
        .lightbox-modal {{
            position: fixed;
            top: 0;
            left: 0;
            width: 100vw;
            height: 100vh;
            background: rgba(0, 0, 0, 0.92);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            z-index: 99999;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 16px;
        }}

        .lightbox-close {{
            position: absolute;
            top: max(16px, env(safe-area-inset-top));
            right: 16px;
            background: rgba(255, 255, 255, 0.15);
            border: 1px solid rgba(255, 255, 255, 0.2);
            color: #fff;
            font-size: 1.4rem;
            width: 44px;
            height: 44px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            z-index: 100000;
        }}

        .lightbox-content {{
            max-width: 100%;
            max-height: 80vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 16px;
        }}

        .lightbox-content img {{
            max-width: 100%;
            max-height: 70vh;
            border-radius: 12px;
            box-shadow: 0 12px 36px rgba(0, 0, 0, 0.8);
            object-fit: contain;
        }}

        .lightbox-btn {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
            background: linear-gradient(135deg, #38bdf8, #8b5cf6);
            color: #fff;
            padding: 12px 24px;
            border-radius: 100px;
            font-size: 0.95rem;
            font-weight: 600;
            text-decoration: none;
            box-shadow: 0 4px 16px rgba(56, 189, 248, 0.4);
        }}
    </style>
</head>
<body ontouchstart="">

    <!-- Header Bar -->
    <header class="app-header">
        <div class="brand-title">
            <span>⚡</span> DM AI OS
        </div>
        <div style="display:flex; align-items:center; gap:8px;">
            <div id="workerComputeBadge" style="font-size:0.68rem; padding:3px 8px; border-radius:12px; background:rgba(16,185,129,0.15); color:#34d399; border:1px solid rgba(16,185,129,0.3); font-weight:600; display:flex; align-items:center; gap:4px;">
                <span style="display:inline-block; width:6px; height:6px; border-radius:50%; background:#10b981;"></span>
                <span id="workerBadgeText">Colab T4...</span>
            </div>
            <div class="status-badge" id="headerStatus">
                <div class="pulse-dot"></div>
                <span id="statusText">ONLINE</span>
            </div>
        </div>
    </header>

    <!-- Main Tab Container -->
    <main class="main-container">

        <!-- Tab 1: Chat Terminal -->
        <section id="chat-tab" class="tab-content active">
            <div class="chat-messages" id="chatMessages">
                <div class="msg-bubble msg-assistant">
                    <strong>DM AI OS Remote Terminal Ready</strong><br>
                    Cerebro autónomo conectado desde la PC. ¿Qué deseas ejecutar?
                </div>
            </div>

            <div class="chat-input-area">
                <!-- AI Router selector bar -->
                <div class="router-bar" style="display:flex; flex-direction:column; gap:6px;">
                    <div style="display:flex; align-items:center; justify-content:space-between; gap:8px;">
                        <span style="font-size:0.75rem; color:var(--text-muted); flex-shrink:0;">Proveedor:</span>
                        <select class="router-select" id="aiProviderSelect" onchange="onProviderChanged()" style="flex:1;">
                            <option value="auto" selected>✨ Auto (Recomendado)</option>
                            <option value="antigravity">🧠 Antigravity (Local Agent Bridge)</option>
                            <option value="comfyui">🎨 ComfyUI (Google Colab T4 16GB)</option>
                            <option value="openrouter">🌐 OpenRouter (Modelos Gratis)</option>
                            <option value="nvidia">⚡ NVIDIA NIM API</option>
                            <option value="ollama">💻 Ollama (Local)</option>
                            <option value="claude">🟣 Claude (Anthropic)</option>
                            <option value="gemini">🔵 Gemini (Google)</option>
                            <option value="grok">⚡ Grok (xAI)</option>
                            <option value="openai">🟢 GPT OSS (OpenAI)</option>
                            <option value="qwen">💻 Qwen Local</option>
                            <option value="deepseek">🐳 DeepSeek Local</option>
                            <option value="higgsfield">🎬 Higgsfield AI</option>
                        </select>

                    </div>
                    <div style="display:flex; align-items:center; justify-content:space-between; gap:8px;">
                        <span style="font-size:0.75rem; color:var(--text-muted); flex-shrink:0;">Modelo:</span>
                        <select class="router-select" id="aiModelSelect" style="flex:1;">
                            <option value="face_swap" selected>🎭 Face Swap / Transferencia de Rostro [INSTANTÁNEO] [GRATIS]</option>
                            <option value="flux1_schnell">⚡ FLUX.1 Schnell (Ultra-Fotorealista HD) [TOP] [GRATIS]</option>
                            <option value="flux1_kontext">🎨 FLUX.1 Kontext (Edición In-Context y Consistencia) [GRATIS]</option>
                            <option value="qwen25_vl">👁️ Qwen2.5-VL Multimodal (Análisis Visual) [MULTIMODAL] [GRATIS]</option>
                            <option value="sdxl_base">📸 SDXL Juggernaut v9 (Selfie iPhone) [TOP] [GRATIS]</option>
                            <option value="wan22_i2v">🎬 Wan 2.1 Video (Animación Cinemática I2V) [GRATIS]</option>
                            <option value="ltx_video">🎥 LTX-Video 0.9.5 (Generación de Video Rápido) [GRATIS]</option>
                            <option value="f5_tts">🎙️ F5-TTS (Clonación de Voz de Valeria) [GRATIS]</option>
                            <option value="auto">✨ Auto (Mejor Disponible)</option>
                        </select>

                    </div>
                </div>

                <div class="preview-box" id="previewBox" style="display:none; flex-wrap:wrap; gap:8px; align-items:center; background:rgba(30,41,59,0.9); border:1px solid rgba(56,189,248,0.3); border-radius:10px; padding:8px 12px; margin-bottom:8px;">
                    <div id="attachmentsContainer" style="display:flex; gap:8px; flex-wrap:wrap; align-items:center; flex:1;"></div>
                    <div style="display:flex; gap:6px; align-items:center;">
                        <button type="button" onclick="openFile()" style="font-size:0.75rem; padding:4px 10px; border-radius:6px; background:rgba(56,189,248,0.2); color:#38bdf8; border:1px solid #38bdf8; cursor:pointer;">+ Agregar otra</button>
                        <button type="button" onclick="clearAttachments()" style="background:none; border:none; color:#94a3b8; font-size:1.1rem; cursor:pointer; padding:4px;">✖</button>
                    </div>
                </div>

                <div class="quick-pills">
                    <span class="quick-pill" onclick="triggerDictation()">🎙️ Dictar</span>
                    <span class="quick-pill" onclick="openCamera()">📷 Cámara</span>
                    <span class="quick-pill" onclick="openFile()">📎 Subir imagen (@Image 1)</span>
                    <span class="quick-pill" onclick="openFile()">📎 Subir segunda (@Image 2)</span>
                    <span class="quick-pill" onclick="quickTask('research')">🔍 Investigar</span>
                    <span class="quick-pill" onclick="quickTask('media')">🎨 Higgsfield</span>
                </div>

                <div class="input-controls">
                    <input type="file" id="fileInput" accept="image/*" multiple style="opacity:0; position:absolute; width:1px; height:1px; pointer-events:none;" onchange="handleFileSelected(event, 'image')">
                    <input type="file" id="fileInputAnimate" accept="image/*" style="opacity:0; position:absolute; width:1px; height:1px; pointer-events:none;" onchange="handleFileSelected(event, 'video')">
                    <input type="file" id="cameraInput" accept="image/*" capture="environment" style="opacity:0; position:absolute; width:1px; height:1px; pointer-events:none;" onchange="handleFileSelected(event, 'image')">

                    <button type="button" class="icon-btn" onclick="openFile()" title="Subir imagen de referencia (@Image 1, @Image 2)">📎</button>
                    <button type="button" class="icon-btn" id="voiceBtn" onclick="toggleVoiceRecording()" title="Dictar por voz">🎙️</button>
                    
                    <textarea class="chat-textarea" id="chatInput" placeholder="Mensaje o comando a DM AI OS..." rows="1" onkeydown="handleKeyDown(event)"></textarea>

                    
                    <button type="button" class="icon-btn send-btn" id="sendBtn" onclick="sendMessage()" title="Enviar">➔</button>
                </div>
            </div>
        </section>

        <!-- Tab 2: Agentes & Workflows -->
        <section id="agents-tab" class="tab-content">
            <div class="card">
                <div class="card-title"><span>⚡</span> Agentes Autónomos</div>
                <div class="grid-2">
                    <div class="agent-card" onclick="selectAgent('browser', 'Navegación Web Autónoma')">
                        <div class="agent-icon">🌐</div>
                        <div class="agent-name">Browser</div>
                        <div class="agent-desc">Navegación e inspección DOM</div>
                    </div>
                    <div class="agent-card" onclick="selectAgent('computer', 'Comandos de Sistema')">
                        <div class="agent-icon">🖥️</div>
                        <div class="agent-name">Computer</div>
                        <div class="agent-desc">Diagnóstico y OS local</div>
                    </div>
                    <div class="agent-card" onclick="selectAgent('research', 'Investigación Profunda')">
                        <div class="agent-icon">🔍</div>
                        <div class="agent-name">Research</div>
                        <div class="agent-desc">Síntesis y análisis</div>
                    </div>
                    <div class="agent-card" onclick="selectAgent('facebook', 'Creación de Contenido')">
                        <div class="agent-icon">📱</div>
                        <div class="agent-name">Facebook</div>
                        <div class="agent-desc">Generador de Posts</div>
                    </div>
                    <div class="agent-card" onclick="selectAgent('university', 'Análisis Académico')">
                        <div class="agent-icon">🎓</div>
                        <div class="agent-name">University</div>
                        <div class="agent-desc">Investigación teórica</div>
                    </div>
                    <div class="agent-card" onclick="selectAgent('media', 'Procesamiento Multimedia')">
                        <div class="agent-icon">🎨</div>
                        <div class="agent-name">Media (Higgsfield)</div>
                        <div class="agent-desc">Generación visual MCP</div>
                    </div>
                </div>
            </div>

            <div class="card">
                <div class="card-title"><span>🚀</span> Ejecutar Agente Individual</div>
                <input type="text" class="action-input" id="agentTaskInput" placeholder="Escribe la tarea para el agente seleccionado...">
                <button class="primary-btn" onclick="runSelectedAgent()">Ejecutar Agente</button>
                <div id="agentResult"></div>
            </div>

            <div class="card">
                <div class="card-title"><span>🔄</span> Workflow DAG Paralelo</div>
                <input type="text" class="action-input" id="workflowGoalInput" placeholder="Meta global para el workflow...">
                <button class="primary-btn" onclick="runWorkflow()">Ejecutar Workflow Completo</button>
                <div id="workflowResult"></div>
            </div>
        </section>

        <!-- Tab 3: Settings > AI Providers & Local Models -->
        <section id="providers-tab" class="tab-content">
            <div class="card">
                <div class="card-title">
                    <span>🤖</span> Settings → AI Providers
                    <button class="btn-small btn-cyan" style="margin-left:auto;" onclick="loadProviders(true)">⚡ Refrescar</button>
                </div>
                <div id="providersList">
                    <div style="color:var(--text-muted); font-size:0.85rem;">Cargando proveedores...</div>
                </div>
            </div>

            <div class="card">
                <div class="card-title"><span>🖥️</span> Hardware Manager</div>
                <button class="primary-btn" onclick="loadHardwareReport()">Diagnosticar Hardware PC</button>
                <div id="hardwareReport"></div>
            </div>

            <div class="card">
                <div class="card-title"><span>💻</span> Local Model Manager</div>
                <div class="metric-row"><span class="metric-label">Ollama LLMs:</span><span class="metric-val" id="ollamaStatus">Detectando...</span></div>
                <div class="metric-row"><span class="metric-label">Whisper STT:</span><span class="metric-val" id="whisperStatus">Disponible</span></div>
                <div class="metric-row"><span class="metric-label">XTTS Voice:</span><span class="metric-val" id="xttsStatus">Disponible</span></div>
                <div class="metric-row"><span class="metric-label">Piper TTS:</span><span class="metric-val" id="piperStatus">Disponible</span></div>
            </div>

            <div class="card">
                <div class="card-title"><span>📜</span> Historial de Proveedores</div>
                <button class="primary-btn" onclick="loadProviderHistory()">Ver Historial de Llamadas</button>
                <div id="providerHistoryLog"></div>
            </div>
        </section>

        <!-- Tab 4: Memoria del Sistema -->
        <section id="memory-tab" class="tab-content">
            <div class="card">
                <div class="card-title"><span>🔍</span> Buscar en Memoria IA</div>
                <input type="text" class="action-input" id="memQuery" placeholder="Consulta semántica (ej. preferencias, usuario)...">
                <button class="primary-btn" onclick="searchMemory()">Buscar Recuerdos</button>
                <div id="memSearchResults"></div>
            </div>

            <div class="card">
                <div class="card-title"><span>💾</span> Guardar Nuevo Recuerdo</div>
                <input type="text" class="action-input" id="memContent" placeholder="Contenido del recuerdo...">
                <button class="primary-btn" onclick="storeMemory()">Guardar en Memoria</button>
            </div>

            <div class="card">
                <div class="card-title"><span>👤</span> Perfil y Contexto del Usuario</div>
                <button class="primary-btn" onclick="loadMemoryProfile()">Cargar Perfil Actual</button>
                <div id="memProfileResult"></div>
            </div>
        </section>

        <!-- Tab 5: Estado del Sistema & DevTools Console -->
        <section id="status-tab" class="tab-content">
            <div class="card">
                <div class="card-title"><span>📊</span> Telemetría DM AI OS</div>
                <div class="metric-row">
                    <span class="metric-label">Sistema Gateway:</span>
                    <span class="metric-val" style="color:var(--accent-green)">ONLINE</span>
                </div>
                <div class="metric-row">
                    <span class="metric-label">Versión Plataforma:</span>
                    <span class="metric-val">v1.5.0-production</span>
                </div>
                <div class="metric-row">
                    <span class="metric-label">AI Router Activo:</span>
                    <span class="metric-val">AUTO Router</span>
                </div>
            </div>

            <div class="card">
                <div class="card-title"><span>🌐</span> Túnel y Endpoints</div>
                <div class="field">
                    <span class="metric-label">URL Base OpenAI:</span>
                    <div class="value" id="apiUrl" style="background:rgba(7,11,20,0.8); padding:8px; border-radius:6px; font-family:monospace; margin-top:4px; font-size:0.8rem; word-break:break-all;">{api_url}</div>
                </div>
                <button class="primary-btn" style="margin-top:10px;" onclick="copyUrl()">Copiar Base URL</button>
            </div>

            <div class="card">
                <div class="card-title"><span>🧠</span> Estado Ollama & MCP Server</div>
                <button class="primary-btn" onclick="fetchSystemTelemetry()">Actualizar Telemetría Real</button>
                <div id="telemetryDetails" style="margin-top:10px;"></div>
            </div>

            <div class="card">
                <div class="card-title"><span>🛠️</span> DevTools Console Log</div>
                <button class="primary-btn" style="background:rgba(244,63,94,0.2); color:#f43f5e; border:1px solid #f43f5e;" onclick="clearDebugConsole()">Limpiar Log</button>
                <div id="debugConsoleLog" style="margin-top:10px;"></div>
            </div>
        </section>

    </main>

    <!-- Bottom Navigation Bar -->
    <nav class="nav-tabs">
        <button type="button" class="tab-btn active" onclick="switchTab('chat-tab', this)">
            <span class="tab-icon">💬</span>
            <span>Chat</span>
        </button>
        <button type="button" class="tab-btn" onclick="switchTab('agents-tab', this)">
            <span class="tab-icon">⚡</span>
            <span>Agentes</span>
        </button>
        <button type="button" class="tab-btn" onclick="switchTab('providers-tab', this); loadProviders();">
            <span class="tab-icon">🤖</span>
            <span>Proveedores</span>
        </button>
        <button type="button" class="tab-btn" onclick="switchTab('memory-tab', this)">
            <span class="tab-icon">🧠</span>
            <span>Memoria</span>
        </button>
        <button type="button" class="tab-btn" onclick="switchTab('status-tab', this)">
            <span class="tab-icon">📊</span>
            <span>Estado</span>
        </button>
    </nav>

    <script>
        const API_KEY = "dm-secret-key-v1";
        let activeAgent = "browser";
        let attachedFile = null;

        // Custom Console Debug Logger
        function logDebug(type, obj) {{
            const logMsg = `[${{new Date().toLocaleTimeString()}}] [${{type}}] ${{typeof obj === 'string' ? obj : JSON.stringify(obj, null, 2)}}`;
            console.log(logMsg);
            const consoleDiv = document.getElementById('debugConsoleLog');
            if (consoleDiv) {{
                const pre = document.createElement('pre');
                pre.style.color = type.includes('ERROR') || type.includes('400') || type.includes('500') ? '#f43f5e' : '#38bdf8';
                pre.innerText = logMsg;
                consoleDiv.insertBefore(pre, consoleDiv.firstChild);
            }}
        }}

        function clearDebugConsole() {{
            const consoleDiv = document.getElementById('debugConsoleLog');
            if (consoleDiv) consoleDiv.innerHTML = '';
        }}

        let _allModelsData = [];

        let _colabActivationUrl = "https://colab.research.google.com/github/daniel2029m-droid/dm-ai-os/blob/main/deployment/colab_comfyui_t4.ipynb";

        function activateColabWorker() {{
            window.open(_colabActivationUrl, '_blank');
        }}

        async function updateWorkerStatus() {{
            try {{
                const res = await fetch('/api/v1/workers/status');
                if (res.ok) {{
                    const data = await res.json();
                    if (data.activation_url) {{
                        _colabActivationUrl = data.activation_url;
                    }}
                    const badge = document.getElementById('workerComputeBadge');
                    const text = document.getElementById('workerBadgeText');
                    if (badge && text) {{
                        if (data.status === 'ready' || data.state === 'ready') {{
                            badge.style.background = 'rgba(16,185,129,0.15)';
                            badge.style.borderColor = 'rgba(16,185,129,0.4)';
                            badge.style.color = '#34d399';
                            badge.style.cursor = 'default';
                            badge.onclick = null;
                            text.textContent = `🟢 Colab (${{data.gpu_name || 'Tesla T4'}})`;
                        }} else if (data.status === 'reconnecting' || data.state === 'connecting') {{
                            badge.style.background = 'rgba(245,158,11,0.15)';
                            badge.style.borderColor = 'rgba(245,158,11,0.4)';
                            badge.style.color = '#fbbf24';
                            badge.style.cursor = 'default';
                            badge.onclick = null;
                            text.textContent = `🟡 Colab Reconectando...`;
                        }} else {{
                            badge.style.background = 'rgba(245,158,11,0.2)';
                            badge.style.borderColor = 'rgba(245,158,11,0.5)';
                            badge.style.color = '#fbbf24';
                            badge.style.cursor = 'pointer';
                            badge.onclick = activateColabWorker;
                            text.innerHTML = `🟡 Colab Offline <strong style="text-decoration:underline;margin-left:2px;">[⚡ Iniciar]</strong>`;
                        }}
                    }}
                }}
            }} catch (e) {{}}
        }}

        async function loadDynamicModels() {{
            try {{
                const res = await fetch('/api/providers/models', {{
                    headers: {{ 'Authorization': 'Bearer ' + API_KEY, 'X-API-Key': API_KEY }}
                }});
                if (res.ok) {{
                    _allModelsData = await res.json();
                    onProviderChanged();
                }}
            }} catch (err) {{
                console.warn('Error al cargar modelos dinámicos:', err);
            }}
            updateWorkerStatus();
            setInterval(updateWorkerStatus, 15000);
        }}

        function onProviderChanged() {{
            const provSelect = document.getElementById('aiProviderSelect');
            const modelSelect = document.getElementById('aiModelSelect');
            if (!provSelect || !modelSelect) return;

            const pid = provSelect.value;
            modelSelect.innerHTML = '';

            const providerObj = _allModelsData.find(p => p.provider_id === pid);
            if (providerObj && providerObj.models && providerObj.models.length > 0) {{
                providerObj.models.forEach(m => {{
                    const opt = document.createElement('option');
                    opt.value = m.id;
                    let tag = m.free ? ' [GRATIS]' : '';
                    if (m.multimodal) tag += ' [MULTIMODAL]';
                    if (m.local) tag += ' [LOCAL]';
                    opt.textContent = `${{m.name || m.id}}${{tag}}`;
                    modelSelect.appendChild(opt);
                }});
            }} else {{
                const opt = document.createElement('option');
                opt.value = 'auto';
                opt.textContent = 'Auto / Standard';
                modelSelect.appendChild(opt);
            }}
        }}

        // Switch Tabs
        function switchTab(tabId, btn) {{
            document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.getElementById(tabId).classList.add('active');
            if (btn) btn.classList.add('active');
        }}

        // Send Chat Message via OpenAI Compatibility Endpoint + AI Router
        async function sendMessage() {{
            const input = document.getElementById('chatInput');
            const prompt = input.value.trim();
            if (!prompt && attachedFiles.length === 0) return;

            const chatMessages = document.getElementById('chatMessages');
            const providerSelect = document.getElementById('aiProviderSelect');
            const modelSelect = document.getElementById('aiModelSelect');

            const selectedProvider = providerSelect ? providerSelect.value : 'auto';
            const selectedModel = modelSelect ? modelSelect.value : 'auto';

            let userContentText = prompt;
            const currentFiles = [...attachedFiles];
            let currentMediaMode = mediaMode;  // 'image' or 'video'
            clearAttachments();
            mediaMode = 'image';

            if (currentFiles.length > 0) {{
                const names = currentFiles.map((f, i) => `@Image ${{i+1}}: ${{f.name}}`).join(', ');
                userContentText += ` [Adjuntos: ${{names}}]`;
            }}

            const userMsgDiv = document.createElement('div');
            userMsgDiv.className = 'msg-bubble msg-user';
            userMsgDiv.innerText = userContentText;
            chatMessages.appendChild(userMsgDiv);

            input.value = '';
            chatMessages.scrollTop = chatMessages.scrollHeight;

            const assistantMsgDiv = document.createElement('div');
            assistantMsgDiv.className = 'msg-bubble msg-assistant';
            const modelLabel = selectedModel && selectedModel !== 'auto' ? ` / ${{selectedModel}}` : '';
            assistantMsgDiv.innerHTML = `<em>Pensando con router [${{selectedProvider.toUpperCase()}}${{modelLabel}}]...</em>`;
            chatMessages.appendChild(assistantMsgDiv);
            chatMessages.scrollTop = chatMessages.scrollHeight;

            let uploadedUrls = [];
            if (currentFiles.length > 0) {{
                assistantMsgDiv.innerHTML = `<em>Subiendo ${{currentFiles.length}} imagen(es) de referencia...</em>`;
                for (let i = 0; i < currentFiles.length; i++) {{
                    const f = currentFiles[i];
                    try {{
                        const formData = new FormData();
                        formData.append('file', f);
                        const upRes = await fetch('/api/providers/upload-media', {{
                            method: 'POST',
                            headers: {{ 'Authorization': 'Bearer ' + API_KEY, 'X-API-Key': API_KEY }},
                            body: formData
                        }});
                        const upData = await upRes.json();
                        if (upData.url) {{
                            uploadedUrls.push(upData.url);
                        }}
                    }} catch (upErr) {{
                        logDebug('UPLOAD_ERR', upErr.message);
                    }}
                }}
            }}

            assistantMsgDiv.innerHTML = `<em>Generando respuesta con router [${{selectedProvider.toUpperCase()}}${{modelLabel}}]...</em>`;

            try {{
                const payload = {{
                    messages: [{{ role: 'user', content: userContentText }}],
                    provider: (uploadedUrls.length > 0 && currentMediaMode === 'video') ? 'higgsfield' : selectedProvider,
                    model: (selectedModel && selectedModel !== 'auto') ? selectedModel : null,
                    image_urls: uploadedUrls,
                    reference_images: uploadedUrls,
                    image_url: uploadedUrls[0] || null,
                    image_url_2: uploadedUrls[1] || null,
                    reference_image_url: uploadedUrls[0] || null,
                }};


                const res = await fetch('/api/providers/route/chat', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json',
                        'Authorization': 'Bearer ' + API_KEY,
                        'X-API-Key': API_KEY
                    }},
                    body: JSON.stringify(payload)
                }});

                let data = {{}};
                const resText = await res.text();
                try {{
                    data = JSON.parse(resText);
                }} catch (jsonErr) {{
                    if (!res.ok) {{
                        throw new Error(`Servidor ocupado (${{res.status}}). La GPU sigue procesando en segundo plano.`);
                    }}
                    throw new Error('Respuesta no válida del servidor');
                }}



                // Extract image or video URL anywhere inside data object
                function extractMediaFromData(obj) {{
                    if (!obj) return {{}};
                    if (obj.image_url) return {{ type: 'image', url: obj.image_url }};
                    if (obj.video_url) return {{ type: 'video', url: obj.video_url }};
                    if (obj.result && typeof obj.result === 'object') {{
                        if (obj.result.image_url) return {{ type: 'image', url: obj.result.image_url }};
                        if (obj.result.video_url) return {{ type: 'video', url: obj.result.video_url }};
                        if (obj.result.results && obj.result.results.rawUrl) return {{ type: 'image', url: obj.result.results.rawUrl }};
                    }}
                    if (obj.raw_result && typeof obj.raw_result === 'object') {{
                        if (obj.raw_result.results && obj.raw_result.results.rawUrl) return {{ type: 'image', url: obj.raw_result.results.rawUrl }};
                    }}
                    return {{}};
                }}

                if (data.pending || (data.status === 'SUBMITTED' && data.job_id)) {{
                    const jobId = data.job_id;
                    const gpuLabel = data.gpu || 'Tesla T4';
                    const modelLabel = data.model || 'Z-Image Turbo';
                    let elapsed = 0;
                    assistantMsgDiv.innerHTML = `<em>🎨 Renderizando con ${{modelLabel}} en ${{gpuLabel}}... (<span id="renderTimer_${{jobId}}">0s</span>)</em>`;
                    
                    const pollInterval = setInterval(async () => {{
                        elapsed += 2;
                        const timerSpan = document.getElementById(`renderTimer_${{jobId}}`);
                        if (timerSpan) timerSpan.innerText = `${{elapsed}}s`;
                        
                        try {{
                            const statRes = await fetch(`/api/v1/creative/assets/${{jobId}}/status`, {{
                                headers: {{ 'Authorization': 'Bearer ' + API_KEY, 'X-API-Key': API_KEY }}
                            }});
                            if (statRes.ok) {{
                                const statData = await statRes.json();
                                if (statData.status === 'COMPLETED' && statData.view_url) {{
                                    clearInterval(pollInterval);
                                    const viewUrl = statData.view_url;
                                    const dlUrl = statData.download_url || viewUrl;
                                    const fn = viewUrl.split('/').pop().split('?')[0] || 'valeria_photo.png';
                                    assistantMsgDiv.innerHTML = `
                                        <div style="font-weight:700; color:#38bdf8; margin-bottom:8px; font-size:0.9rem;">🖼️ Imagen generada por ComfyUI (${{gpuLabel}}):</div>
                                        <div style="position:relative; display:inline-block; margin:6px 0; width:100%;">
                                            <img src="${{viewUrl}}" alt="Valeria" onclick="openMediaLightbox('${{viewUrl}}', '${{dlUrl}}', '${{fn}}')" style="max-width:100%; max-height:480px; border-radius:12px; box-shadow:0 8px 28px rgba(0,0,0,0.7); display:block; object-fit:contain; cursor:pointer; background:#0f172a;" title="Toca para ver en pantalla completa" />
                                            <div style="margin-top:10px; display:flex; gap:8px;">
                                                <a href="${{dlUrl}}" download="${{fn}}" target="_blank" style="background:#0284c7; color:#fff; border-radius:6px; padding:6px 14px; font-size:0.8rem; font-weight:600; text-decoration:none;">📥 Descargar Imagen HD</a>
                                                <a href="${{viewUrl}}" target="_blank" style="background:rgba(255,255,255,0.1); color:#e2e8f0; border-radius:6px; padding:6px 14px; font-size:0.8rem; font-weight:600; text-decoration:none; border:1px solid rgba(255,255,255,0.2);">🌐 Ver Pantalla Completa</a>
                                            </div>
                                        </div>
                                    `;
                                    chatMessages.scrollTop = chatMessages.scrollHeight;
                                }}

                            }}
                        }} catch (pollErr) {{
                            console.warn('Polling error:', pollErr);
                        }}
                    }}, 2000);
                    return;
                }}

                const extracted = extractMediaFromData(data);
                let answerText = "";


                if (!res.ok) {{
                    const detail = data.detail || data.error || data.message || (typeof data === 'string' ? data : JSON.stringify(data));
                    answerText = `⚠️ **Error de API (${{res.status}}):** ${{typeof detail === 'object' ? JSON.stringify(detail) : detail}}`;
                }} else if (data.choices && data.choices[0] && data.choices[0].message && typeof data.choices[0].message.content === 'string') {{
                    answerText = data.choices[0].message.content;
                }} else if (data.message && typeof data.message === 'object' && typeof data.message.content === 'string') {{
                    answerText = data.message.content;
                }} else if (typeof data.message === 'string') {{
                    answerText = data.message;
                }} else if (data.response && typeof data.response === 'object' && typeof data.response.content === 'string') {{
                    answerText = data.response.content;
                }} else if (typeof data.response === 'string') {{
                    answerText = data.response;
                }} else if (typeof data.content === 'string') {{
                    answerText = data.content;
                }} else if (typeof data.output === 'string') {{
                    answerText = data.output;
                }} else if (typeof data.text === 'string') {{
                    answerText = data.text;
                }} else if (data.result && typeof data.result === 'object') {{
                    if (typeof data.result.content === 'string') answerText = data.result.content;
                    else if (data.result.message && typeof data.result.message.content === 'string') answerText = data.result.message.content;
                    else if (typeof data.result.message === 'string') answerText = data.result.message;
                    else if (typeof data.result.response === 'string') answerText = data.result.response;
                    else if (typeof data.result.output === 'string') answerText = data.result.output;
                    else if (typeof data.result.text === 'string') answerText = data.result.text;
                    else answerText = JSON.stringify(data.result);
                }} else if (typeof data.result === 'string') {{
                    answerText = data.result;
                }} else if (extracted.url) {{
                    if (extracted.type === 'video') {{
                        answerText = `🎬 **Video generado por ${{data.provider || 'Higgsfield AI'}}:**\n\n![Video](${{extracted.url}})\n\n[📥 Descargar Video](${{extracted.url}})`;
                    }} else {{
                        answerText = `🖼️ **Imagen generada por ${{data.provider || 'Higgsfield AI'}}:**\n\n![Imagen](${{extracted.url}})\n\n[📥 Descargar Imagen](${{extracted.url}})`;
                    }}
                }} else if (typeof data.detail === 'string') {{
                    answerText = `⚠️ **Error de API:** ${{data.detail}}`;
                }} else if (typeof data.error === 'string') {{
                    answerText = `⚠️ **Error:** ${{data.error}}`;
                }} else {{
                    answerText = `⚠️ **Respuesta no reconocida:**\n\`\`\`json\n${{JSON.stringify(data, null, 2)}}\n\`\`\``;
                }}

                // Render media with signed URL support and Lightbox
                function renderMedia(text) {{
                    // Images: ![alt](url) → clickable image card with Lightbox & download
                    text = text.replace(/!\[(.*?)\]\((https?:\/\/[^\)]+|\/[^\)]+)\)/g, function(m, alt, url) {{
                        const filename = url.split('/').pop().split('?')[0] || 'generated_asset.png';
                        const downloadUrl = url.includes('/view?') ? url.replace('/view?', '/download?') : url;
                        return `<div style="position:relative;display:inline-block;margin:10px 0;width:100%;">`+
                               `<img src="${{url}}" alt="${{alt}}" onclick="openMediaLightbox('${{url}}', '${{downloadUrl}}', '${{filename}}')" `+
                               `style="max-width:100%;max-height:420px;border-radius:0.75rem;box-shadow:0 8px 24px rgba(0,0,0,0.5);display:block;object-fit:contain;cursor:pointer;" title="Toca para ver en pantalla completa" />`+
                               `<a href="${{downloadUrl}}" download="${{filename}}" target="_blank" title="Descargar" `+
                               `style="position:absolute;bottom:10px;right:10px;background:rgba(0,0,0,0.75);color:#fff;border-radius:0.5rem;padding:6px 14px;font-size:0.78rem;font-weight:600;text-decoration:none;backdrop-filter:blur(6px);border:1px solid rgba(255,255,255,0.15);">`+
                               `📥 Descargar</a></div>`;
                    }});
                    // Remaining links
                    text = text.replace(/\[([^\]]+)\]\((https?:\/\/[^\)]+|\/[^\)]+)\)/g, '<a href="$2" target="_blank" style="color:var(--accent-cyan);font-weight:600;text-decoration:underline;">$1</a>');
                    // Bold
                    text = text.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
                    // Newlines
                    text = text.replace(/\\n/g, '<br>');
                    return text;
                }}

                let formattedHtml = "";
                const rawStr = JSON.stringify(data);

                if (rawStr.includes("Out of credits")) {{
                    formattedHtml = `<div style="background:rgba(239,68,68,0.15);border:1px solid rgba(239,68,68,0.4);border-radius:10px;padding:14px;margin:8px 0;">` +
                        `<div style="font-weight:700;color:#f87171;font-size:0.92rem;margin-bottom:6px;">⚠️ Sin créditos en la cuenta actual de Higgsfield</div>` +
                        `<div style="font-size:0.8rem;color:#cbd5e1;margin-bottom:12px;">La cuenta de Gmail actual en Higgsfield se ha quedado sin créditos (queda 1 crédito). Cambia de cuenta para obtener créditos gratis de prueba.</div>` +
                        `<button type="button" onclick="startHiggsfieldSwitch()" style="background:linear-gradient(135deg,#10b981,#059669);color:#fff;border:none;padding:10px 16px;border-radius:8px;font-weight:600;font-size:0.85rem;cursor:pointer;width:100%;">🔄 Cambiar Cuenta (Obtener Créditos Gratis)</button>` +
                        `</div>`;
                }} else {{
                    formattedHtml = renderMedia(answerText);
                }}

                assistantMsgDiv.innerHTML = formattedHtml +
                    `<div class="metric-row" style="margin-top:8px; font-size:0.7rem; color:var(--accent-cyan); border:none;">` +
                    `<span>Proveedor: ${{data._provider_used || selectedProvider}}</span>` +
                    `<span>${{data._routing_ms || 0}} ms</span>` +
                    `</div>`;
                chatMessages.scrollTop = chatMessages.scrollHeight;
                logDebug('CHAT_OK', data);
            }} catch (err) {{
                assistantMsgDiv.innerHTML = `<span style="color:#f43f5e">Error al comunicar con DM AI OS: ${{err.message}}</span>`;
                logDebug('CHAT_ERROR', err.message);
            }}
        }}

        function handleKeyDown(e) {{
            if (e.key === 'Enter' && !e.shiftKey) {{
                e.preventDefault();
                sendMessage();
            }}
        }}

        let mediaMode = 'image';  // 'image' = reference for img-to-img, 'video' = animate

        function openFile() {{
            document.getElementById('fileInput').click();
        }}

        function openFileAnimate() {{
            document.getElementById('fileInputAnimate').click();
        }}

        function openCamera() {{
            document.getElementById('cameraInput').click();
        }}

        function setMediaMode(mode) {{
            mediaMode = mode;
            const imgBtn = document.getElementById('modeImgBtn');
            const vidBtn = document.getElementById('modeVidBtn');
            if (mode === 'video') {{
                imgBtn.style.background = 'rgba(139,92,246,0.1)';
                imgBtn.style.color = '#94a3b8';
                imgBtn.style.borderColor = 'rgba(139,92,246,0.3)';
                vidBtn.style.background = 'rgba(139,92,246,0.3)';
                vidBtn.style.color = '#c084fc';
                vidBtn.style.borderColor = '#c084fc';
            }} else {{
                imgBtn.style.background = 'rgba(56,189,248,0.3)';
                imgBtn.style.color = '#38bdf8';
                imgBtn.style.borderColor = '#38bdf8';
                vidBtn.style.background = 'rgba(139,92,246,0.1)';
                vidBtn.style.color = '#94a3b8';
                vidBtn.style.borderColor = 'rgba(139,92,246,0.3)';
            }}
        }}

        let attachedFiles = [];

        function renderAttachmentsPreview() {{
            const container = document.getElementById('attachmentsContainer');
            const previewBox = document.getElementById('previewBox');
            if (!container || !previewBox) return;
            if (attachedFiles.length === 0) {{
                previewBox.style.display = 'none';
                container.innerHTML = '';
                return;
            }}
            previewBox.style.display = 'flex';
            container.innerHTML = '';
            attachedFiles.forEach((file, idx) => {{
                const item = document.createElement('div');
                item.style.cssText = 'display:flex; align-items:center; gap:6px; background:rgba(15,23,42,0.9); border:1px solid rgba(56,189,248,0.4); border-radius:6px; padding:3px 8px;';
                
                const label = document.createElement('span');
                label.style.cssText = 'font-size:0.75rem; color:#38bdf8; font-weight:700;';
                label.textContent = `@Image ${{idx + 1}}`;
                
                const name = document.createElement('span');
                name.style.cssText = 'font-size:0.75rem; color:#e2e8f0; max-width:130px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;';
                name.textContent = file.name;
                
                const removeBtn = document.createElement('button');
                removeBtn.type = 'button';
                removeBtn.style.cssText = 'background:none; border:none; color:#f43f5e; font-size:0.85rem; cursor:pointer; padding:0 2px;';
                removeBtn.textContent = '✖';
                removeBtn.onclick = () => {{
                    attachedFiles.splice(idx, 1);
                    renderAttachmentsPreview();
                }};
                
                item.appendChild(label);
                item.appendChild(name);
                item.appendChild(removeBtn);
                container.appendChild(item);
            }});
        }}

        function handleFileSelected(event, mode) {{
            const files = event.target.files;
            if (!files || files.length === 0) return;
            Array.from(files).forEach(f => {{
                attachedFiles.push(f);
            }});
            if (mode) mediaMode = mode;
            renderAttachmentsPreview();
            event.target.value = '';
            
            const chatInput = document.getElementById('chatInput');
            if (!chatInput.value && attachedFiles.length >= 2) {{
                chatInput.value = 'Change the person of the @Image 1 to the person of the @Image 2, SAME OUTFIT as @Image 1, same pose.';
            }}
        }}

        function clearAttachments() {{
            attachedFiles = [];
            renderAttachmentsPreview();
        }}

        async function approveAntigravityAction(sessionId, actionId, btn) {{
            if (btn) btn.disabled = true;
            try {{
                const res = await fetch('/api/v1/antigravity/approve', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + API_KEY, 'X-API-Key': API_KEY }},
                    body: JSON.stringify({{ session_id: sessionId, action_id: actionId, decision: 'APPROVE' }})
                }});
                const data = await res.json();
                alert(data.message || 'Acción aprobada y ejecutada.');
                if (btn && btn.parentElement) btn.parentElement.innerHTML = '<span style="color:#22c55e; font-weight:700;">✅ ACCIÓN APROBADA Y EJECUTADA</span>';
            }} catch (err) {{
                alert('Error al aprobar: ' + err.message);
                if (btn) btn.disabled = false;
            }}
        }}

        async function rejectAntigravityAction(sessionId, actionId, btn) {{
            if (btn) btn.disabled = true;
            try {{
                const res = await fetch('/api/v1/antigravity/reject', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + API_KEY, 'X-API-Key': API_KEY }},
                    body: JSON.stringify({{ session_id: sessionId, action_id: actionId, decision: 'REJECT' }})
                }});
                const data = await res.json();
                alert(data.message || 'Acción rechazada.');
                if (btn && btn.parentElement) btn.parentElement.innerHTML = '<span style="color:#ef4444; font-weight:700;">❌ ACCIÓN RECHAZADA</span>';
            }} catch (err) {{
                alert('Error al rechazar: ' + err.message);
                if (btn) btn.disabled = false;
            }}
        }}




        function selectAgent(name, desc) {{
            activeAgent = name;
            const input = document.getElementById('agentTaskInput');
            if (input) input.placeholder = `Tarea para ${{name.toUpperCase()}} (${{desc}})...`;
        }}

        async function runSelectedAgent() {{
            const input = document.getElementById('agentTaskInput');
            const task = input.value.trim();
            if (!task) return;
            const resDiv = document.getElementById('agentResult');
            resDiv.innerHTML = '<pre>Ejecutando agente...</pre>';

            try {{
                const res = await fetch('/agent/run', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json',
                        'Authorization': 'Bearer ' + API_KEY,
                        'X-API-Key': API_KEY
                    }},
                    body: JSON.stringify({{ agent: activeAgent, task: task, params: {{}} }})
                }});
                const data = await res.json();
                resDiv.innerHTML = `<pre>${{JSON.stringify(data, null, 2)}}</pre>`;
            }} catch (err) {{
                resDiv.innerHTML = `<pre style="color:#f43f5e">Error: ${{err.message}}</pre>`;
            }}
        }}

        // AI Providers Panel Management
        async function loadProviders(forceCheck = false) {{
            const container = document.getElementById('providersList');
            if (!container) return;
            container.innerHTML = '<div style="color:var(--text-muted); font-size:0.85rem;">Cargando estado de proveedores...</div>';

            try {{
                const endpoint = forceCheck ? '/api/providers/health' : '/api/providers';
                const res = await fetch(endpoint, {{
                    headers: {{ 'Authorization': 'Bearer ' + API_KEY, 'X-API-Key': API_KEY }}
                }});
                const providers = await res.json();

                let html = '';
                providers.forEach(p => {{
                    const isAvailable = p.status === 'available' || (!p.status && p.account !== 'Not configured');
                    const badgeColor = isAvailable ? 'var(--accent-green)' : 'var(--accent-yellow)';
                    const statusText = p.status ? p.status.toUpperCase() : 'CONFIGURADO';

                    html += `
                    <div class="provider-item">
                        <div class="provider-header">
                            <strong style="color:var(--text-main); font-size:0.9rem;">${{p.name || p.id}}</strong>
                            <span class="btn-small" style="background:rgba(255,255,255,0.05); color:${{badgeColor}}">${{statusText}}</span>
                        </div>
                        <div class="metric-row"><span class="metric-label">Cuenta:</span><span class="metric-val">${{p.account || p.provider_id || 'N/A'}}</span></div>
                        <div class="metric-row"><span class="metric-label">Latencia:</span><span class="metric-val">${{p.latency_ms !== undefined ? p.latency_ms + ' ms' : 'N/A'}}</span></div>
                        <div class="provider-actions">
                            <button class="btn-small btn-cyan" onclick="healthCheckProvider('${{p.id || p.provider_id}}')">⚡ Probar Conexión</button>
                            ${{(p.id || p.provider_id) === 'higgsfield' ? `<button class="btn-small btn-purple" onclick="switchHiggsfieldAccount()">🔄 Cambiar Cuenta</button>` : `<button class="btn-small btn-purple" onclick="loginProvider('${{p.id || p.provider_id}}')">🔄 Cambiar Cuenta</button>`}}
                            <button class="btn-small btn-red" onclick="logoutProvider('${{p.id || p.provider_id}}')">🚪 Cerrar Sesión</button>
                        </div>
                    </div>`;
                }});
                container.innerHTML = html;
            }} catch (err) {{
                container.innerHTML = `<div style="color:var(--accent-red)">Error al cargar proveedores: ${{err.message}}</div>`;
            }}
        }}

        async function healthCheckProvider(id) {{
            try {{
                const res = await fetch(`/api/providers/${{id}}/health`, {{
                    headers: {{ 'Authorization': 'Bearer ' + API_KEY, 'X-API-Key': API_KEY }}
                }});
                const data = await res.json();
                alert(`Resultado para ${{id.toUpperCase()}}:\nStatus: ${{data.status}}\nLatencia: ${{data.latency_ms}} ms\nCuenta: ${{data.account}}`);
                loadProviders();
            }} catch (err) {{
                alert('Error al probar conexión: ' + err.message);
            }}
        }}

        async function loginProvider(id) {{
            try {{
                const res = await fetch(`/api/providers/${{id}}/login`, {{
                    method: 'POST',
                    headers: {{ 'Authorization': 'Bearer ' + API_KEY, 'X-API-Key': API_KEY }}
                }});
                const data = await res.json();
                alert(`Autenticación para ${{id.toUpperCase()}}:\n${{data.message}}`);
                loadProviders();
            }} catch (err) {{
                alert('Error al iniciar sesión: ' + err.message);
            }}
        }}

        // ── Higgsfield: Cambiar Cuenta / Pegar Token con Redirección al Chat ──────
        function switchHiggsfieldAccount() {{
            let modal = document.getElementById('higgsfieldLoginModal');
            if (!modal) {{
                modal = document.createElement('div');
                modal.id = 'higgsfieldLoginModal';
                modal.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;z-index:9999;background:rgba(0,0,0,0.85);backdrop-filter:blur(8px);display:flex;align-items:center;justify-content:center;';
                modal.innerHTML = `
                    <div style="background:linear-gradient(135deg,#1a1a2e,#16213e);border:1px solid rgba(99,102,241,0.3);border-radius:1.5rem;padding:2rem;max-width:500px;width:92%;text-align:center;box-shadow:0 25px 60px rgba(0,0,0,0.6);">
                        <div style="font-size:2.8rem;margin-bottom:0.75rem;">🔐</div>
                        <h2 style="color:#e2e8f0;margin:0 0 0.4rem;font-size:1.35rem;">Conectar Cuenta Higgsfield</h2>
                        <p style="color:#94a3b8;font-size:0.85rem;margin:0 0 1.5rem;">Cada cuenta de Gmail incluye <strong style="color:#818cf8;">3 días gratis</strong> para generar imágenes y video.</p>

                        <!-- OPCIÓN A: OAUTH LOGIN (URL from backend CLI) -->
                        <div id="hfInstructions" style="background:rgba(99,102,241,0.1);border:1px solid rgba(99,102,241,0.2);border-radius:0.75rem;padding:1rem;text-align:left;margin-bottom:1.25rem;">
                            <p style="color:#818cf8;font-weight:600;margin:0 0 0.4rem;font-size:0.85rem;">🌐 Opción A — Login con Google (Automático):</p>
                            <ol style="color:#94a3b8;font-size:0.8rem;margin:0 0 0.75rem;padding-left:1.2rem;line-height:1.7;">
                                <li>Haz clic en el botón verde ⬇️</li>
                                <li>Elige tu cuenta de Gmail (3 días gratis)</li>
                                <li>Esta pantalla se actualizará sola al terminar</li>
                            </ol>
                            <div style="text-align:center;">
                                <a id="hfLoginBtn" href="https://cloud.higgsfield.ai" target="_blank" style="display:inline-block;padding:0.65rem 1.4rem;background:linear-gradient(135deg,#10b981,#059669);color:#fff;font-weight:600;font-size:0.85rem;border-radius:0.5rem;text-decoration:none;box-shadow:0 4px 12px rgba(16,185,129,0.3);">🔗 Cargando URL de login...</a>
                            </div>
                        </div>

                        <!-- OPCIÓN B: PEGAR TOKEN / API KEY -->
                        <div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);border-radius:0.75rem;padding:1rem;text-align:left;margin-bottom:1.25rem;">
                            <p style="color:#a78bfa;font-weight:600;margin:0 0 0.5rem;font-size:0.85rem;">🔑 Opción B — Pegar Token / API Key de Higgsfield:</p>
                            <input type="text" id="hfManualToken" placeholder="Pega el Bearer Token o API Key aquí..." style="width:100%;box-sizing:border-box;padding:0.6rem 0.8rem;background:rgba(0,0,0,0.4);border:1px solid rgba(167,139,250,0.3);border-radius:0.5rem;color:#e2e8f0;font-size:0.82rem;margin-bottom:0.75rem;outline:none;">
                            <div style="text-align:right;">
                                <button onclick="saveManualHiggsfieldToken()" style="padding:0.5rem 1.2rem;background:linear-gradient(135deg,#8b5cf6,#6366f1);color:#fff;font-weight:600;font-size:0.82rem;border:none;border-radius:0.4rem;cursor:pointer;">💾 Guardar Token</button>
                            </div>
                        </div>

                        <div id="hfStatusText" style="color:#94a3b8;font-size:0.83rem;margin-bottom:0.75rem;">💡 Usa la Opción A para obtener tu API Key, luego pégala en Opción B.</div>

                        <div id="hfSuccessBanner" style="display:none;background:rgba(16,185,129,0.15);border:1px solid rgba(16,185,129,0.3);border-radius:0.75rem;padding:1rem;margin-bottom:1.25rem;">
                            <div style="font-size:1.8rem;">✅</div>
                            <div id="hfSuccessMsg" style="color:#10b981;font-weight:600;margin-top:0.3rem;">¡Cuenta Conectada! Redirigiendo al Chat...</div>
                        </div>

                        <div id="hfErrorBanner" style="display:none;background:rgba(239,68,68,0.15);border:1px solid rgba(239,68,68,0.3);border-radius:0.75rem;padding:1rem;margin-bottom:1.25rem;">
                            <div id="hfErrorMsg" style="color:#ef4444;font-size:0.85rem;"></div>
                        </div>

                        <div style="display:flex;gap:0.75rem;justify-content:center;flex-wrap:wrap;">
                            <button id="hfCancelBtn" onclick="closeHiggsfieldModal(true)" style="padding:0.65rem 1.6rem;background:linear-gradient(135deg,#3b82f6,#2563eb);color:#fff;font-weight:600;border:none;border-radius:0.5rem;cursor:pointer;font-size:0.85rem;box-shadow:0 4px 12px rgba(59,130,246,0.3);">💬 Ir al Chat Principal</button>
                            <button onclick="closeHiggsfieldModal(false)" style="padding:0.65rem 1.2rem;background:rgba(255,255,255,0.07);color:#94a3b8;font-weight:500;border:1px solid rgba(255,255,255,0.1);border-radius:0.5rem;cursor:pointer;font-size:0.85rem;">✖ Cerrar</button>
                        </div>
                    </div>
                `;
                document.body.appendChild(modal);
            }}
            modal.style.display = 'flex';
            document.getElementById('hfSuccessBanner').style.display = 'none';
            document.getElementById('hfErrorBanner').style.display = 'none';
            document.getElementById('hfStatusText').textContent = 'Esperando autenticación...';
            startHiggsfieldSwitch();
        }}

        let _hfPollInterval = null;

        async function startHiggsfieldSwitch() {{
            document.getElementById('hfSuccessBanner').style.display = 'none';
            document.getElementById('hfErrorBanner').style.display = 'none';
            document.getElementById('hfStatusText').textContent = 'Iniciando login con Higgsfield...';
            const loginBtn = document.getElementById('hfLoginBtn');
            if (loginBtn) loginBtn.textContent = '⏳ Obteniendo URL de login...';
            try {{
                const res = await fetch('/api/providers/higgsfield/switch-account', {{
                    method: 'POST',
                    headers: {{ 'Authorization': 'Bearer ' + API_KEY, 'X-API-Key': API_KEY }}
                }});
                const data = await res.json();
                // Update login button with real OAuth URL from backend
                if (data.login_url && loginBtn) {{
                    loginBtn.href = data.login_url;
                    loginBtn.textContent = '🔐 Abrir Login de Higgsfield con Google';
                }}
                document.getElementById('hfStatusText').textContent = data.message || 'Haz clic en el botón verde para iniciar sesión.';
                if (_hfPollInterval) clearInterval(_hfPollInterval);
                _hfPollInterval = setInterval(pollHiggsfieldLogin, 2500);
            }} catch (err) {{
                document.getElementById('hfStatusText').textContent = 'Error al conectar. Usa Opción B para pegar el token manualmente.';
            }}
        }}

        async function saveManualHiggsfieldToken() {{
            const token = document.getElementById('hfManualToken').value.trim();
            if (!token) {{
                alert('Por favor ingresa un token válido.');
                return;
            }}
            try {{
                const res = await fetch('/api/providers/higgsfield/set-token', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + API_KEY, 'X-API-Key': API_KEY }},
                    body: JSON.stringify({{ token: token }})
                }});
                const data = await res.json();
                if (res.ok) {{
                    document.getElementById('hfSuccessMsg').textContent = '¡Token Guardado! Redirigiendo al Chat...';
                    document.getElementById('hfSuccessBanner').style.display = 'block';
                    document.getElementById('hfErrorBanner').style.display = 'none';
                    setTimeout(() => closeHiggsfieldModal(true), 1200);
                }} else {{
                    alert('Error al guardar token: ' + (data.detail || 'Token no válido'));
                }}
            }} catch (err) {{
                alert('Error de conexión: ' + err.message);
            }}
        }}

        async function pollHiggsfieldLogin() {{
            try {{
                const res = await fetch('/api/providers/higgsfield/login-status', {{
                    headers: {{ 'Authorization': 'Bearer ' + API_KEY, 'X-API-Key': API_KEY }}
                }});
                const data = await res.json();
                // Always update login button URL if backend has a new one
                if (data.oauth_url) {{
                    const loginBtn = document.getElementById('hfLoginBtn');
                    if (loginBtn && loginBtn.href !== data.oauth_url) {{
                        loginBtn.href = data.oauth_url;
                        loginBtn.textContent = '🔐 Abrir Login de Higgsfield con Google';
                    }}
                }}
                if (data.status === 'success') {{
                    clearInterval(_hfPollInterval);
                    document.getElementById('hfSuccessMsg').textContent = `¡Cuenta conectada! (${{data.account || 'Gmail'}}). Redirigiendo al Chat...`;
                    document.getElementById('hfSuccessBanner').style.display = 'block';
                    document.getElementById('hfStatusText').textContent = '';
                    setTimeout(() => closeHiggsfieldModal(true), 1200);
                }} else if (data.status === 'waiting') {{
                    const sec = Math.round(data.elapsed_seconds || 0);
                    document.getElementById('hfStatusText').textContent = `Esperando que completes el login en el navegador... (${{sec}}s)`;
                }} else if (data.status === 'timeout') {{
                    clearInterval(_hfPollInterval);
                    document.getElementById('hfStatusText').textContent = '⏰ Tiempo agotado. Haz clic en el botón verde para intentar de nuevo.';
                }}
            }} catch (err) {{
                // keep polling silently
            }}
        }}

        let _hfOpenedLogin = false;

        function closeHiggsfieldModal(goToChat = false) {{
            clearInterval(_hfPollInterval);
            _hfOpenedLogin = false;
            const modal = document.getElementById('higgsfieldLoginModal');
            if (modal) modal.style.display = 'none';
            loadProviders();
            if (goToChat) {{
                // Activate chat tab and its button
                const chatTabBtn = document.querySelectorAll('.tab-btn')[0];
                switchTab('chat-tab', chatTabBtn || null);
                // Force scroll chat into view
                const chatSection = document.getElementById('chat-tab');
                if (chatSection) chatSection.scrollIntoView({{behavior:'smooth'}});
            }}
        }}

        async function logoutProvider(id) {{
            if (!confirm(`¿Cerrar sesión de ${{id.toUpperCase()}}?`)) return;
            try {{
                const res = await fetch(`/api/providers/${{id}}/logout`, {{
                    method: 'POST',
                    headers: {{ 'Authorization': 'Bearer ' + API_KEY, 'X-API-Key': API_KEY }}
                }});
                const data = await res.json();
                // Show inline toast instead of blocking alert
                const toast = document.createElement('div');
                toast.style.cssText = 'position:fixed;bottom:80px;left:50%;transform:translateX(-50%);background:#1e293b;border:1px solid #334155;color:#94a3b8;padding:0.7rem 1.4rem;border-radius:0.75rem;font-size:0.85rem;z-index:9000;box-shadow:0 8px 24px rgba(0,0,0,0.4);';
                toast.textContent = `${{id.toUpperCase()}}: ${{data.message || 'Sesión cerrada'}}`;
                document.body.appendChild(toast);
                setTimeout(() => toast.remove(), 3000);
                loadProviders();
            }} catch (err) {{
                console.error('Error al cerrar sesión:', err);
            }}
        }}

        async function loadHardwareReport() {{
            const div = document.getElementById('hardwareReport');
            div.innerHTML = '<pre>Diagnosticando hardware local...</pre>';
            try {{
                const res = await fetch('/api/providers/hardware', {{
                    headers: {{ 'Authorization': 'Bearer ' + API_KEY, 'X-API-Key': API_KEY }}
                }});
                const data = await res.json();
                div.innerHTML = `<pre>${{JSON.stringify(data, null, 2)}}</pre>`;
            }} catch (err) {{
                div.innerHTML = `<pre style="color:#f43f5e">Error: ${{err.message}}</pre>`;
            }}
        }}

        async function loadProviderHistory() {{
            const div = document.getElementById('providerHistoryLog');
            div.innerHTML = '<pre>Cargando historial de llamadas...</pre>';
            try {{
                const res = await fetch('/api/providers/history', {{
                    headers: {{ 'Authorization': 'Bearer ' + API_KEY, 'X-API-Key': API_KEY }}
                }});
                const data = await res.json();
                div.innerHTML = `<pre>${{JSON.stringify(data, null, 2)}}</pre>`;
            }} catch (err) {{
                div.innerHTML = `<pre style="color:#f43f5e">Error: ${{err.message}}</pre>`;
            }}
        }}

        function quickTask(type) {{
            switchTab('agents-tab', document.querySelectorAll('.tab-btn')[1]);
            selectAgent(type, 'Tarea Rápida');
        }}

        async function searchMemory() {{
            const q = document.getElementById('memQuery').value.trim();
            const resDiv = document.getElementById('memSearchResults');
            resDiv.innerHTML = '<pre>Buscando recuerdos...</pre>';
            try {{
                const res = await fetch('/memory/search', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + API_KEY, 'X-API-Key': API_KEY }},
                    body: JSON.stringify({{ query: q, category: 'general' }})
                }});
                const data = await res.json();
                resDiv.innerHTML = `<pre>${{JSON.stringify(data, null, 2)}}</pre>`;
            }} catch (err) {{
                resDiv.innerHTML = `<pre style="color:#f43f5e">Error: ${{err.message}}</pre>`;
            }}
        }}

        async function storeMemory() {{
            const content = document.getElementById('memContent').value.trim();
            if (!content) return;
            try {{
                await fetch('/memory/store', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + API_KEY, 'X-API-Key': API_KEY }},
                    body: JSON.stringify({{ content: content, category: 'user_note', importance: 0.8 }})
                }});
                alert('Recuerdo guardado exitosamente.');
                document.getElementById('memContent').value = '';
            }} catch (err) {{
                alert('Error: ' + err.message);
            }}
        }}

        async function loadMemoryProfile() {{
            const resDiv = document.getElementById('memProfileResult');
            resDiv.innerHTML = '<pre>Cargando perfil...</pre>';
            try {{
                const res = await fetch('/memory/profile?user_id=daniel', {{
                    headers: {{ 'Authorization': 'Bearer ' + API_KEY, 'X-API-Key': API_KEY }}
                }});
                const data = await res.json();
                resDiv.innerHTML = `<pre>${{JSON.stringify(data, null, 2)}}</pre>`;
            }} catch (err) {{
                resDiv.innerHTML = `<pre style="color:#f43f5e">Error: ${{err.message}}</pre>`;
            }}
        }}

        async function fetchSystemTelemetry() {{
            const div = document.getElementById('telemetryDetails');
            div.innerHTML = '<pre>Consultando backend PC...</pre>';
            try {{
                const res = await fetch('/system/status', {{
                    headers: {{ 'Authorization': 'Bearer ' + API_KEY, 'X-API-Key': API_KEY }}
                }});
                const data = await res.json();
                div.innerHTML = `<pre>${{JSON.stringify(data, null, 2)}}</pre>`;
            }} catch (err) {{
                div.innerHTML = `<pre style="color:#f43f5e">Error: ${{err.message}}</pre>`;
            }}
        }}

        function copyUrl() {{
            const url = document.getElementById('apiUrl').innerText;
            navigator.clipboard.writeText(url).then(() => {{
                alert('Base URL copiada al portapapeles: ' + url);
            }});
        }}

        // Lightbox Media Modal Handlers
        function openMediaLightbox(viewUrl, downloadUrl, filename) {{
            const modal = document.getElementById('mediaLightbox');
            const img = document.getElementById('lightboxImg');
            const dlBtn = document.getElementById('lightboxDownloadBtn');
            if (!modal || !img) return;

            img.src = viewUrl;
            if (dlBtn) {{
                dlBtn.href = downloadUrl || viewUrl;
                dlBtn.download = filename || 'generated_asset.png';
            }}
            modal.style.display = 'flex';
        }}

        function closeMediaLightbox(e) {{
            if (e && e.target && e.target.id === 'lightboxImg') return;
            const modal = document.getElementById('mediaLightbox');
            const img = document.getElementById('lightboxImg');
            if (modal) modal.style.display = 'none';
            if (img) img.src = '';
        }}

        // Initial load of dynamic models on startup
        document.addEventListener('DOMContentLoaded', () => {{
            loadDynamicModels();
        }});
        loadDynamicModels();

        // Register Service Worker for PWA
        if ('serviceWorker' in navigator) {{
            navigator.serviceWorker.register('/sw.js').catch(() => {{}});
        }}
    </script>

    <!-- Fullscreen Media Lightbox Modal -->
    <div id="mediaLightbox" class="lightbox-modal" style="display:none;" onclick="closeMediaLightbox(event)">
        <button class="lightbox-close" onclick="closeMediaLightbox(event)">✕</button>
        <div class="lightbox-content" onclick="event.stopPropagation()">
            <img id="lightboxImg" src="" alt="Fullscreen asset preview" />
            <div class="lightbox-actions">
                <a id="lightboxDownloadBtn" href="" download="asset.png" target="_blank" class="lightbox-btn">📥 Guardar en el dispositivo</a>
            </div>
        </div>
    </div>
</body>
</html>
"""
