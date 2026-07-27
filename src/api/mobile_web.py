"""
DM AI OS — iPhone Mobile Remote Client (PWA) v1.4.1
=====================================================
Provides a touch-optimized, high-aesthetic presentation layer for iPhone.
Consumes existing API Gateway endpoints (/v1/chat/completions, /agent/run, etc.)
with 100% OpenAI-compliant payloads, dual Bearer/X-API-Key auth, and full multimodal support.
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
            width: 7px;
            height: 7px;
            background-color: #34d399;
            border-radius: 50%;
            box-shadow: 0 0 8px #34d399;
            animation: pulse 2s infinite;
        }}

        @keyframes pulse {{
            0% {{ transform: scale(0.95); opacity: 0.8; }}
            50% {{ transform: scale(1.2); opacity: 1; }}
            100% {{ transform: scale(0.95); opacity: 0.8; }}
        }}

        /* Navigation Bar (Bottom Tabs) */
        .nav-tabs {{
            background: rgba(15, 23, 42, 0.95);
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            border-top: 1px solid var(--bg-card-border);
            display: flex;
            justify-content: space-around;
            padding: 8px 0;
            padding-bottom: var(--safe-bottom);
            z-index: 100;
        }}

        .tab-btn {{
            background: none;
            border: none;
            color: var(--text-muted);
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 4px;
            font-size: 0.7rem;
            font-weight: 500;
            cursor: pointer;
            width: 25%;
            transition: all 0.2s ease;
        }}

        .tab-btn.active {{
            color: var(--accent-cyan);
        }}

        .tab-icon {{
            font-size: 1.25rem;
        }}

        /* Content Area */
        .main-container {{
            flex: 1;
            overflow: hidden;
            position: relative;
        }}

        .tab-content {{
            display: none;
            height: 100%;
            overflow-y: auto;
            padding: 16px;
            -webkit-overflow-scrolling: touch;
        }}

        .tab-content.active {{
            display: flex;
            flex-direction: column;
        }}

        /* Chat Tab */
        #chat-tab {{
            padding: 0;
        }}

        .chat-messages {{
            flex: 1;
            overflow-y: auto;
            padding: 16px;
            display: flex;
            flex-direction: column;
            gap: 14px;
        }}

        .msg-bubble {{
            max-width: 88%;
            padding: 12px 16px;
            border-radius: 18px;
            font-size: 0.92rem;
            line-height: 1.45;
            word-break: break-word;
            position: relative;
            animation: fadeIn 0.3s ease;
        }}

        @keyframes fadeIn {{
            from {{ opacity: 0; transform: translateY(8px); }}
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

        .msg-meta {{
            font-size: 0.68rem;
            color: rgba(255, 255, 255, 0.5);
            margin-top: 6px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}

        .tts-btn {{
            background: none;
            border: none;
            color: var(--accent-cyan);
            font-size: 0.8rem;
            cursor: pointer;
            padding: 2px 6px;
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

        .icon-btn.recording {{
            background: #f43f5e;
            color: white;
            animation: pulse 1s infinite;
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
    </style>
</head>
<body>

    <!-- Header Bar -->
    <header class="app-header">
        <div class="brand-title">
            <span>⚡</span> DM AI OS
        </div>
        <div class="status-badge" id="headerStatus">
            <div class="pulse-dot"></div>
            <span id="statusText">ONLINE</span>
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
                <div class="preview-box" id="previewBox">
                    <span id="previewText"></span>
                    <span style="cursor:pointer" onclick="clearAttachment()">✖</span>
                </div>

                <div class="quick-pills">
                    <span class="quick-pill" onclick="triggerDictation()">🎙️ Dictar</span>
                    <span class="quick-pill" onclick="openCamera()">📷 Cámara</span>
                    <span class="quick-pill" onclick="openFile()">📄 Documento</span>
                    <span class="quick-pill" onclick="quickTask('research')">🔍 Investigar</span>
                    <span class="quick-pill" onclick="quickTask('browser')">🌐 Navegar</span>
                </div>

                <div class="input-controls">
                    <input type="file" id="fileInput" accept="image/*,application/pdf,.txt,.md" style="display:none" onchange="handleFileSelected(event)">
                    <input type="file" id="cameraInput" accept="image/*" capture="environment" style="display:none" onchange="handleFileSelected(event)">

                    <button class="icon-btn" onclick="openFile()" title="Adjuntar Archivo">📎</button>
                    <button class="icon-btn" id="voiceBtn" onclick="toggleVoiceRecording()" title="Dictar por voz">🎙️</button>
                    
                    <textarea class="chat-textarea" id="chatInput" placeholder="Mensaje o comando a DM AI OS..." rows="1" onkeydown="handleKeyDown(event)"></textarea>
                    
                    <button class="icon-btn send-btn" id="sendBtn" onclick="sendMessage()" title="Enviar">➔</button>
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
                        <div class="agent-name">Media</div>
                        <div class="agent-desc">Generación visual</div>
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

        <!-- Tab 3: Memoria del Sistema -->
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

        <!-- Tab 4: Estado del Sistema & DevTools Console -->
        <section id="status-tab" class="tab-content">
            <div class="card">
                <div class="card-title"><span>📊</span> Telemetría DM AI OS</div>
                <div class="metric-row">
                    <span class="metric-label">Sistema Gateway:</span>
                    <span class="metric-val" style="color:var(--accent-green)">ONLINE</span>
                </div>
                <div class="metric-row">
                    <span class="metric-label">Versión Plataforma:</span>
                    <span class="metric-val">v1.4.0-production</span>
                </div>
                <div class="metric-row">
                    <span class="metric-label">Modelo Activo:</span>
                    <span class="metric-val">dm-autonomous-brain</span>
                </div>
                <div class="metric-row">
                    <span class="metric-label">API Key Requerida:</span>
                    <span class="metric-val">dm-secret-key-v1</span>
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
        <button class="tab-btn active" onclick="switchTab('chat-tab', this)">
            <span class="tab-icon">💬</span>
            <span>Chat</span>
        </button>
        <button class="tab-btn" onclick="switchTab('agents-tab', this)">
            <span class="tab-icon">⚡</span>
            <span>Agentes</span>
        </button>
        <button class="tab-btn" onclick="switchTab('memory-tab', this)">
            <span class="tab-icon">🧠</span>
            <span>Memoria</span>
        </button>
        <button class="tab-btn" onclick="switchTab('status-tab', this)">
            <span class="tab-icon">📊</span>
            <span>Estado</span>
        </button>
    </nav>

    <script>
        const API_KEY = "dm-secret-key-v1";
        let activeAgent = "browser";
        let attachedFile = null;
        let speechRecognition = null;
        let isRecording = false;

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

        // Switch Tabs
        function switchTab(tabId, btn) {{
            document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.getElementById(tabId).classList.add('active');
            btn.classList.add('active');
        }}

        // Read file as Base64 Data URL or Text
        function readFileAsync(file) {{
            return new Promise((resolve, reject) => {{
                const reader = new FileReader();
                if (file.type.startsWith('image/')) {{
                    reader.readAsDataURL(file);
                }} else {{
                    reader.readAsText(file);
                }}
                reader.onload = () => resolve(reader.result);
                reader.onerror = error => reject(error);
            }});
        }}

        // Send Chat Message via OpenAI Compatibility Endpoint
        async function sendMessage() {{
            const input = document.getElementById('chatInput');
            const prompt = input.value.trim();
            if (!prompt && !attachedFile) return;

            const chatMessages = document.getElementById('chatMessages');

            let userContentText = prompt;
            let currentFile = attachedFile;

            if (currentFile) {{
                userContentText += ` \\n[Adjunto: ${{currentFile.name}}]`;
            }}

            // Render User Bubble
            const userBubble = document.createElement('div');
            userBubble.className = 'msg-bubble msg-user';
            userBubble.innerText = userContentText;
            chatMessages.appendChild(userBubble);

            input.value = '';
            clearAttachment();
            chatMessages.scrollTop = chatMessages.scrollHeight;

            // Render Temporary Assistant Bubble
            const aiBubble = document.createElement('div');
            aiBubble.className = 'msg-bubble msg-assistant';
            aiBubble.innerHTML = '<em>Procesando en cerebro PC...</em>';
            chatMessages.appendChild(aiBubble);
            chatMessages.scrollTop = chatMessages.scrollHeight;

            try {{
                let messagePayloadContent = prompt || 'Analizar archivo adjunto';

                if (currentFile) {{
                    const fileData = await readFileAsync(currentFile);
                    if (currentFile.type.startsWith('image/')) {{
                        messagePayloadContent = [
                            {{ type: "text", text: prompt || "Analizar esta imagen" }},
                            {{ type: "image_url", image_url: {{ url: fileData }} }}
                        ];
                    }} else {{
                        messagePayloadContent = prompt + `\\n\\n[Documento Adjunto (${{currentFile.name}})]:\\n` + fileData;
                    }}
                }}

                const requestBody = {{
                    model: 'dm-autonomous-brain',
                    messages: [
                        {{ role: 'user', content: messagePayloadContent }}
                    ]
                }};

                logDebug('HTTP_POST_REQ', {{ url: '/v1/chat/completions', body: requestBody }});

                const res = await fetch('/v1/chat/completions', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json',
                        'Authorization': 'Bearer ' + API_KEY,
                        'X-API-Key': API_KEY
                    }},
                    body: JSON.stringify(requestBody)
                }});

                logDebug('HTTP_POST_RES_STATUS', res.status);

                if (!res.ok) {{
                    const errText = await res.text();
                    logDebug('HTTP_POST_ERROR_BODY', errText);
                    throw new Error(`HTTP ${{res.status}}: ${{errText}}`);
                }}

                const data = await res.json();
                logDebug('HTTP_POST_RES_JSON', data);

                const reply = data.choices && data.choices[0] && data.choices[0].message && data.choices[0].message.content
                    ? data.choices[0].message.content 
                    : 'Soy DM AI OS, cerebro procesado con éxito.';

                aiBubble.innerHTML = `<strong>DM AI OS</strong><br>${{reply.replace(/\\n/g, '<br>')}}`;
                speakText(reply);
            }} catch (err) {{
                logDebug('JS_EXCEPTION', err.message);
                aiBubble.innerHTML = `<span style="color:#f43f5e">Error al comunicar con PC: ${{err.message}}</span>`;
            }}
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }}

        function handleKeyDown(e) {{
            if (e.key === 'Enter' && !e.shiftKey) {{
                e.preventDefault();
                sendMessage();
            }}
        }}

        // Voice Dictation (Web Speech API)
        function toggleVoiceRecording() {{
            const btn = document.getElementById('voiceBtn');
            const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

            if (!SpeechRecognition) {{
                alert('El reconocimiento de voz no está soportado en este navegador.');
                return;
            }}

            if (!speechRecognition) {{
                speechRecognition = new SpeechRecognition();
                speechRecognition.lang = 'es-ES';
                speechRecognition.continuous = false;

                speechRecognition.onresult = (event) => {{
                    const transcript = event.results[0][0].transcript;
                    document.getElementById('chatInput').value += ' ' + transcript;
                }};

                speechRecognition.onend = () => {{
                    isRecording = false;
                    btn.classList.remove('recording');
                }};
            }}

            if (isRecording) {{
                speechRecognition.stop();
                isRecording = false;
                btn.classList.remove('recording');
            }} else {{
                speechRecognition.start();
                isRecording = true;
                btn.classList.add('recording');
            }}
        }}

        function triggerDictation() {{
            toggleVoiceRecording();
        }}

        // Text-to-Speech Output
        function speakText(text) {{
            if ('speechSynthesis' in window) {{
                window.speechSynthesis.cancel();
                const cleanText = text.replace(/🔊 Escuchar|dm-autonomous-brain|DM AI OS/g, '');
                const utterance = new SpeechSynthesisUtterance(cleanText);
                utterance.lang = 'es-ES';
                window.speechSynthesis.speak(utterance);
            }}
        }}

        // File & Camera Capture
        function openFile() {{
            document.getElementById('fileInput').click();
        }}

        function openCamera() {{
            document.getElementById('cameraInput').click();
        }}

        function handleFileSelected(e) {{
            const file = e.target.files[0];
            if (file) {{
                attachedFile = file;
                document.getElementById('previewText').innerText = `📎 ${{file.name}} (${{(file.size/1024).toFixed(1)}} KB)`;
                document.getElementById('previewBox').style.display = 'flex';
                logDebug('FILE_ATTACHED', {{ name: file.name, size: file.size, type: file.type }});
            }}
        }}

        function clearAttachment() {{
            attachedFile = null;
            document.getElementById('fileInput').value = '';
            document.getElementById('cameraInput').value = '';
            document.getElementById('previewBox').style.display = 'none';
        }}

        // Agent Execution Tab
        function selectAgent(name, desc) {{
            activeAgent = name;
            document.getElementById('agentTaskInput').placeholder = `Tarea para agente ${{name.toUpperCase()}} (${{desc}})...`;
        }}

        async function runSelectedAgent() {{
            const task = document.getElementById('agentTaskInput').value.trim();
            if (!task) return;
            const resDiv = document.getElementById('agentResult');
            resDiv.innerHTML = '<pre>Ejecutando agente en PC...</pre>';

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
                logDebug('AGENT_RUN_RES', data);
            }} catch (err) {{
                resDiv.innerHTML = `<pre style="color:#f43f5e">Error: ${{err.message}}</pre>`;
                logDebug('AGENT_RUN_ERROR', err.message);
            }}
        }}

        async function runWorkflow() {{
            const goal = document.getElementById('workflowGoalInput').value.trim();
            if (!goal) return;
            const resDiv = document.getElementById('workflowResult');
            resDiv.innerHTML = '<pre>Ejecutando DAG paralelo en PC...</pre>';

            try {{
                const res = await fetch('/workflow/run', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json',
                        'Authorization': 'Bearer ' + API_KEY,
                        'X-API-Key': API_KEY
                    }},
                    body: JSON.stringify({{ goal: goal }})
                }});
                const data = await res.json();
                resDiv.innerHTML = `<pre>${{JSON.stringify(data, null, 2)}}</pre>`;
                logDebug('WORKFLOW_RUN_RES', data);
            }} catch (err) {{
                resDiv.innerHTML = `<pre style="color:#f43f5e">Error: ${{err.message}}</pre>`;
                logDebug('WORKFLOW_RUN_ERROR', err.message);
            }}
        }}

        function quickTask(type) {{
            switchTab('agents-tab', document.querySelectorAll('.tab-btn')[1]);
            selectAgent(type, 'Tarea Rápida');
        }}

        // Memory Management Tab
        async function searchMemory() {{
            const q = document.getElementById('memQuery').value.trim();
            const resDiv = document.getElementById('memSearchResults');
            resDiv.innerHTML = '<pre>Buscando recuerdos...</pre>';

            try {{
                const res = await fetch('/memory/search', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json',
                        'Authorization': 'Bearer ' + API_KEY,
                        'X-API-Key': API_KEY
                    }},
                    body: JSON.stringify({{ query: q, category: 'general' }})
                }});
                const data = await res.json();
                resDiv.innerHTML = `<pre>${{JSON.stringify(data, null, 2)}}</pre>`;
                logDebug('MEMORY_SEARCH_RES', data);
            }} catch (err) {{
                resDiv.innerHTML = `<pre style="color:#f43f5e">Error: ${{err.message}}</pre>`;
                logDebug('MEMORY_SEARCH_ERROR', err.message);
            }}
        }}

        async function storeMemory() {{
            const content = document.getElementById('memContent').value.trim();
            if (!content) return;

            try {{
                const res = await fetch('/memory/store', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json',
                        'Authorization': 'Bearer ' + API_KEY,
                        'X-API-Key': API_KEY
                    }},
                    body: JSON.stringify({{ content: content, category: 'user_note', importance: 0.8 }})
                }});
                alert('Recuerdo guardado exitosamente.');
                document.getElementById('memContent').value = '';
                logDebug('MEMORY_STORE_OK', content);
            }} catch (err) {{
                alert('Error al guardar recuerdo: ' + err.message);
                logDebug('MEMORY_STORE_ERROR', err.message);
            }}
        }}

        async function loadMemoryProfile() {{
            const resDiv = document.getElementById('memProfileResult');
            resDiv.innerHTML = '<pre>Cargando perfil...</pre>';

            try {{
                const res = await fetch('/memory/profile?user_id=daniel', {{
                    headers: {{
                        'Authorization': 'Bearer ' + API_KEY,
                        'X-API-Key': API_KEY
                    }}
                }});
                const data = await res.json();
                resDiv.innerHTML = `<pre>${{JSON.stringify(data, null, 2)}}</pre>`;
                logDebug('MEMORY_PROFILE_RES', data);
            }} catch (err) {{
                resDiv.innerHTML = `<pre style="color:#f43f5e">Error: ${{err.message}}</pre>`;
                logDebug('MEMORY_PROFILE_ERROR', err.message);
            }}
        }}

        // Telemetry & Status Tab
        async function fetchSystemTelemetry() {{
            const div = document.getElementById('telemetryDetails');
            div.innerHTML = '<pre>Consultando backend PC...</pre>';

            try {{
                const res = await fetch('/system/status', {{
                    headers: {{
                        'Authorization': 'Bearer ' + API_KEY,
                        'X-API-Key': API_KEY
                    }}
                }});
                const data = await res.json();
                div.innerHTML = `<pre>${{JSON.stringify(data, null, 2)}}</pre>`;
                logDebug('TELEMETRY_RES', data);
            }} catch (err) {{
                div.innerHTML = `<pre style="color:#f43f5e">Error: ${{err.message}}</pre>`;
                logDebug('TELEMETRY_ERROR', err.message);
            }}
        }}

        function copyUrl() {{
            const url = document.getElementById('apiUrl').innerText;
            navigator.clipboard.writeText(url).then(() => {{
                alert('Base URL copiada al portapapeles: ' + url);
            }});
        }}

        // Register Service Worker for PWA
        if ('serviceWorker' in navigator) {{
            navigator.serviceWorker.register('/sw.js').catch(() => {{}});
        }}
    </script>
</body>
</html>
"""
