import os

upgrade_script_content = """import os
import sys

# ─── 1. REESCRIBIR BACKEND MAIN.PY ──────────────────────────────────────

main_py_content = \"\"\"#!/usr/bin/env python3
import os
import json
import asyncio
import sys
import subprocess
import requests
from pathlib import Path
from typing import List, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent))

import backend.database as db
from pipeline.imagenes_stock import procesar_imagenes_video
from pipeline.componer_video import componer_video

app = FastAPI(
    title="Antigravity Automation Suite API",
    description="Backend de control para la generación y publicación de contenido",
    version="1.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    db.inicializar_db()

OUTPUT_PATH = Path(__file__).parent.parent / "output"
OUTPUT_PATH.mkdir(parents=True, exist_ok=True)
app.mount("/output", StaticFiles(directory=str(OUTPUT_PATH)), name="output")

# Gestor de WebSocket
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        try:
            logs = db.obtener_conexion().execute(
                "SELECT agente, mensaje, nivel, fecha FROM agentes_logs ORDER BY id DESC LIMIT 50"
            ).fetchall()
            for log in reversed(logs):
                await websocket.send_json({
                    "agente": log["agente"],
                    "mensaje": log["mensaje"],
                    "nivel": log["nivel"],
                    "fecha": log["fecha"]
                })
        except Exception as e:
            print(f"Error cargando logs iniciales: {e}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def enviar_mensaje(self, log_dict: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(log_dict)
            except:
                pass

manager = ConnectionManager()

@app.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

async def emitir_log(agente: str, mensaje: str, nivel: str = "INFO"):
    db.registrar_log_agente(agente, mensaje, nivel)
    import datetime
    log_dict = {
        "agente": agente,
        "mensaje": mensaje,
        "nivel": nivel,
        "fecha": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    await manager.enviar_mensaje(log_dict)

class ConfigItem(BaseModel):
    clave: str
    valor: str
    categoria: str = "general"

class CanalItem(BaseModel):
    id_canal: str
    nombre: str
    plataforma: str
    nicho: str = "general"

class VideoRequest(BaseModel):
    nicho: str = "psicologia y personalidad"
    tema_especifico: str = None

# Modelos del Chat
class ChatMessage(BaseModel):
    role: str # "user" | "assistant" | "system"
    content: str
    images: Optional[List[str]] = None # Base64 images list

class ChatRequest(BaseModel):
    model: str
    messages: List[ChatMessage]

# Endpoints
@app.get("/api/config")
def get_config():
    conn = db.obtener_conexion()
    rows = conn.execute("SELECT clave, valor, categoria FROM configuracion").fetchall()
    conn.close()
    return {row["clave"]: {"valor": row["valor"], "categoria": row["categoria"]} for row in rows}

@app.post("/api/config")
async def save_config(item: ConfigItem):
    db.guardar_config(item.clave, item.valor, item.categoria)
    await emitir_log("System", f"Configuración guardada: {item.clave}")
    return {"status": "ok"}

@app.get("/api/channels")
def get_channels():
    conn = db.obtener_conexion()
    rows = conn.execute("SELECT id_canal, nombre, plataforma, nicho, estado FROM canales").fetchall()
    conn.close()
    return [dict(row) for row in rows]

@app.post("/api/channels")
async def add_channel(item: CanalItem):
    conn = db.obtener_conexion()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO canales (id_canal, nombre, plataforma, nicho) VALUES (?, ?, ?, ?)",
        (item.id_canal, item.nombre, item.plataforma, item.nicho)
    )
    conn.commit()
    conn.close()
    await emitir_log("System", f"Nuevo canal registrado: {item.nombre} ({item.plataforma})")
    return {"status": "ok"}

@app.post("/api/channels/{platform}/login")
def trigger_login(platform: str, background_tasks: BackgroundTasks):
    if platform not in ["youtube", "pinterest", "tiktok"]:
        raise HTTPException(status_code=400, detail="Plataforma no válida")
        
    cmd = [
        sys.executable,
        str(Path(__file__).parent / "agents" / "browser_bot.py"),
        "--login", platform
    ]
    background_tasks.add_task(subprocess.run, cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return {"status": "iniciando_login"}

# Endpoint para listar modelos locales de Ollama
@app.get("/api/ollama/models")
def get_ollama_models():
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=3)
        if r.status_code == 200:
            return [m["name"] for m in r.json().get("models", [])]
    except:
        pass
    return []

# Endpoint de Chat 100% Local con Ollama
@app.post("/api/chat")
async def chat_ollama(req: ChatRequest):
    ollama_url = "http://localhost:11434/api/chat"
    
    # Formatear mensajes
    formatted_messages = []
    for msg in req.messages:
        msg_dict = {"role": msg.role, "content": msg.content}
        if msg.images:
            # Ollama requiere el base64 sin el prefijo data:image/...;base64,
            clean_images = []
            for img in msg.images:
                if "," in img:
                    clean_images.append(img.split(",")[1])
                else:
                    clean_images.append(img)
            msg_dict["images"] = clean_images
        formatted_messages.append(msg_dict)
        
    payload = {
        "model": req.model,
        "messages": formatted_messages,
        "stream": False
    }
    
    try:
        r = requests.post(ollama_url, json=payload, timeout=90)
        r.raise_for_status()
        data = r.json()
        return {"message": data.get("message", {}).get("content", "")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ollama error: {str(e)}")

@app.get("/api/queue")
def get_queue():
    conn = db.obtener_conexion()
    rows = conn.execute("SELECT id_video, titulo, tema, nicho, estado, video_path, fecha_creacion FROM videos_cola ORDER BY fecha_creacion DESC").fetchall()
    conn.close()
    return [dict(row) for row in rows]

async def tarea_generacion_pipeline(id_video: str, nicho: str, tema_especifico: str):
    try:
        await emitir_log("Agente Guionista", f"Iniciando generación de guión para nicho '{nicho}'...")
        if not tema_especifico:
            from pipeline.generar_guion import cargar_temas_pendientes, generar_banco_temas
            pendientes = cargar_temas_pendientes()
            if not pendientes:
                await emitir_log("Agente Guionista", "Generando nuevo banco de temas en CSV...")
                generar_banco_temas(n=15)
                pendientes = cargar_temas_pendientes()
            
            if pendientes:
                tema_especifico = pendientes[0]["tema"]
            else:
                tema_especifico = "La psicología de las personas altamente sensibles"
                
        from pipeline.generar_guion import generar_guion
        guion = generar_guion(tema_especifico, id_video)
        if not guion:
            raise Exception("No se pudo generar el guión")
            
        titulo = guion.get("titulo", "Sin Título")
        db.agregar_video_cola(id_video, titulo, tema_especifico, nicho, guion)
        await emitir_log("Agente Guionista", f"Guión generado: '{titulo}'")
        
        await emitir_log("Agente Narrador", "Generando voces de narración...")
        db.actualizar_estado_video(id_video, "voz_generando")
        from pipeline.generar_voz import procesar_guion_completo as gen_voz
        audio_result = gen_voz(id_video)
        if not audio_result:
            raise Exception("Error en generación de voz")
        db.actualizar_estado_video(id_video, "voz_generada")
        await emitir_log("Agente Narrador", "Voz generada y sincronizada correctamente.")
        
        await emitir_log("Agente Diseñador", "Generando recursos visuales...")
        db.actualizar_estado_video(id_video, "imagenes_descargando")
        procesar_imagenes_video(id_video)
        db.actualizar_estado_video(id_video, "imagenes_listas")
        await emitir_log("Agente Diseñador", "Ilustraciones descargadas con éxito.")
        
        await emitir_log("Agente Editor", "Compilando y renderizando video final...")
        db.actualizar_estado_video(id_video, "renderizando")
        
        video_final_path = componer_video(id_video)
        if video_final_path and os.path.exists(video_final_path):
            db.actualizar_estado_video(id_video, "completado", video_path=video_final_path)
            await emitir_log("Agente Editor", f"¡Video final compilado exitosamente! Guardado en: {video_final_path}", "SUCCESS")
        else:
            raise Exception("Error en la composición final del video")
            
    except Exception as e:
        db.actualizar_estado_video(id_video, "fallido", error_msg=str(e))
        await emitir_log("System", f"Fallo en la producción de {id_video}: {str(e)}", "ERROR")

@app.post("/api/queue/generate")
def trigger_generation(req: VideoRequest, background_tasks: BackgroundTasks):
    import datetime
    id_video = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    background_tasks.add_task(tarea_generacion_pipeline, id_video, req.nicho, req.tema_especifico)
    return {"status": "en_cola", "id_video": id_video}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
\"\"\"

with open("C:/Users/moral/youtube_automatizado/backend/main.py", "w", encoding="utf-8") as f:
    f.write(main_py_content)
print("SUCCESS: backend/main.py updated!")

# ─── 2. REESCRIBIR FRONTEND APP.TSX ─────────────────────────────────────

app_tsx_content = \"\"\"import "./App.css";
import React, { useState, useEffect, useRef } from "react";
import { 
  Play, Cpu, Settings, Terminal, Video, RefreshCw, Plus, MessageSquare,
  CheckCircle, AlertCircle, Loader, Link, Database, Smartphone, Image, Send, Paperclip
} from "lucide-react";

interface VideoItem {
  id_video: string;
  titulo: string;
  tema: string;
  nicho: string;
  estado: string;
  video_path: string;
  fecha_creacion: string;
}

interface ChannelItem {
  id_canal: string;
  nombre: string;
  plataforma: string;
  nicho: string;
  estado: string;
}

interface LogItem {
  agente: string;
  mensaje: string;
  nivel: string;
  fecha: string;
}

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  images?: string[]; // base64 strings
}

export default function App() {
  const [activeTab, setActiveTab] = useState<"dashboard" | "queue" | "chat" | "agents" | "settings">("dashboard");
  const [backendUrl, setBackendUrl] = useState(() => {
    return localStorage.getItem("backend_url") || "http://localhost:8000";
  });
  
  const [isConnecting, setIsConnecting] = useState(false);
  const [wsConnected, setWsConnected] = useState(false);
  const [tunnelUrl, setTunnelUrl] = useState("");
  
  // Form States
  const [nicho, setNicho] = useState("psicologia y personalidad");
  const [tema, setTema] = useState("");
  
  // Data States
  const [videoQueue, setVideoQueue] = useState<VideoItem[]>([]);
  const [channels, setChannels] = useState<ChannelItem[]>([]);
  const [logs, setLogs] = useState<LogItem[]>([]);
  const [selectedVideo, setSelectedVideo] = useState<VideoItem | null>(null);
  
  // Chat States
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([
    { role: "assistant", content: "¡Hola! Soy tu asistente de Mentes Curiosas. Puedo ayudarte a redactar guiones, analizar canales o procesar imágenes. ¿Qué deseas hacer hoy?" }
  ]);
  const [chatInput, setChatInput] = useState("");
  const [chatModel, setChatModel] = useState("qwen2.5-coder:latest");
  const [ollamaModels, setOllamaModels] = useState<string[]>([]);
  const [chatLoading, setChatLoading] = useState(false);
  const [attachedImage, setAttachedImage] = useState<string | null>(null);
  
  // Config States
  const [configs, setConfigs] = useState<Record<string, { valor: string, categoria: string }>>({});
  
  // Add Channel Form
  const [newChanName, setNewChanName] = useState("");
  const [newChanPlat, setNewChanPlat] = useState("youtube");
  const [newChanNicho, setNewChanNicho] = useState("");
  
  const wsRef = useRef<WebSocket | null>(null);
  const logsEndRef = useRef<HTMLDivElement | null>(null);
  const chatEndRef = useRef<HTMLDivElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  // Headers especiales para BYPASSEAR la advertencia de localtunnel en la API
  const getFetchHeaders = () => {
    return {
      "Content-Type": "application/json",
      "bypass-tunnel-reminder": "true"
    };
  };

  const saveBackendUrl = (url: string) => {
    const cleanUrl = url.replace(/\\\\/$/, "");
    setBackendUrl(cleanUrl);
    localStorage.setItem("backend_url", cleanUrl);
  };

  const fetchData = async () => {
    if (!backendUrl) return;
    try {
      const qRes = await fetch(`${backendUrl}/api/queue`, { headers: getFetchHeaders() });
      if (qRes.ok) setVideoQueue(await qRes.json());
      
      const cRes = await fetch(`${backendUrl}/api/channels`, { headers: getFetchHeaders() });
      if (cRes.ok) setChannels(await cRes.json());
      
      const cfgRes = await fetch(`${backendUrl}/api/config`, { headers: getFetchHeaders() });
      if (cfgRes.ok) {
        const data = await cfgRes.json();
        setConfigs(data);
        if (data.REMOTE_TUNNEL_URL) {
          setTunnelUrl(data.REMOTE_TUNNEL_URL.valor);
        }
      }
      
      // Obtener modelos de Ollama
      const modelsRes = await fetch(`${backendUrl}/api/ollama/models`, { headers: getFetchHeaders() });
      if (modelsRes.ok) {
        const mList = await modelsRes.json();
        setOllamaModels(mList);
        if (mList.length > 0 && !mList.includes(chatModel)) {
          setChatModel(mList[0]);
        }
      }
      setIsConnecting(false);
    } catch (e) {
      console.error("Error conectando con backend:", e);
      setIsConnecting(true);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 8000);

    const wsProto = backendUrl.startsWith("https") ? "wss" : "ws";
    const wsUrl = `${backendUrl.replace(/^https?:/, wsProto)}/api/ws`;
    
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      setWsConnected(true);
      setIsConnecting(false);
    };
    
    ws.onmessage = (event) => {
      const log = JSON.parse(event.data);
      setLogs((prev) => {
        const exists = prev.some(l => l.fecha === log.fecha && l.mensaje === log.mensaje);
        if (exists) return prev;
        return [...prev, log].slice(-150);
      });
    };
    
    ws.onclose = () => {
      setWsConnected(false);
    };

    return () => {
      ws.close();
      clearInterval(interval);
    };
  }, [backendUrl]);

  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatMessages]);

  const handleTriggerGeneration = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await fetch(`${backendUrl}/api/queue/generate`, {
        method: "POST",
        headers: getFetchHeaders(),
        body: JSON.stringify({ nicho, tema_especifico: tema || null })
      });
      if (res.ok) {
        setTema("");
        fetchData();
        setActiveTab("queue");
      }
    } catch (err) {
      alert("Error iniciando generación de video");
    }
  };

  const handleAddChannel = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newChanName) return;
    try {
      const res = await fetch(`${backendUrl}/api/channels`, {
        method: "POST",
        headers: getFetchHeaders(),
        body: JSON.stringify({
          id_canal: newChanName.toLowerCase().replace(/\\\\s+/g, "_"),
          nombre: newChanName,
          plataforma: newChanPlat,
          nicho: newChanNicho || "general"
        })
      });
      if (res.ok) {
        setNewChanName("");
        setNewChanNicho("");
        fetchData();
      }
    } catch (err) {
      alert("Error agregando canal");
    }
  };

  const handleTriggerLogin = async (platform: string) => {
    try {
      const res = await fetch(`${backendUrl}/api/channels/${platform}/login`, {
        method: "POST",
        headers: getFetchHeaders()
      });
      if (res.ok) {
        alert(`🖥️ Navegador iniciado en tu PC. Inicia sesión en ${platform.toUpperCase()} y luego CIERRA la ventana del navegador cuando termines.`);
      } else {
        alert("Error al iniciar el navegador");
      }
    } catch (err) {
      alert("Error al conectar con el servidor backend");
    }
  };

  // Chat Submission
  const handleSendChatMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!chatInput.trim() && !attachedImage) return;

    const userMsg: ChatMessage = {
      role: "user",
      content: chatInput,
      images: attachedImage ? [attachedImage] : undefined
    };

    setChatMessages((prev) => [...prev, userMsg]);
    setChatInput("");
    setAttachedImage(null);
    setChatLoading(true);

    try {
      const chatHistory = [...chatMessages, userMsg].map(m => ({
        role: m.role,
        content: m.content,
        images: m.images
      }));

      const res = await fetch(`${backendUrl}/api/chat`, {
        method: "POST",
        headers: getFetchHeaders(),
        body: JSON.stringify({
          model: chatModel,
          messages: chatHistory
        })
      });

      if (res.ok) {
        const data = await res.json();
        setChatMessages((prev) => [...prev, { role: "assistant", content: data.message }]);
      } else {
        const errData = await res.json();
        setChatMessages((prev) => [...prev, { role: "assistant", content: `❌ Error: ${errData.detail || "Error en Ollama"}` }]);
      }
    } catch (err) {
      setChatMessages((prev) => [...prev, { role: "assistant", content: "❌ Error de conexión con el backend." }]);
    } finally {
      setChatLoading(false);
    }
  };

  // Image attachment
  const handleImageAttach = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onloadend = () => {
      setAttachedImage(reader.result as string);
    };
    reader.readAsDataURL(file);
  };

  const handleSaveConfig = async (clave: string, valor: string, categoria: string = "general") => {
    try {
      const res = await fetch(`${backendUrl}/api/config`, {
        method: "POST",
        headers: getFetchHeaders(),
        body: JSON.stringify({ clave, valor, category: categoria })
      });
      if (res.ok) {
        fetchData();
      }
    } catch (err) {
      alert("Error guardando ajuste");
    }
  };

  return (
    <div className="app-container">
      <aside className="sidebar">
        <div className="brand">
          <Cpu className="brand-icon" />
          <h2>Antigravity Suite</h2>
        </div>
        
        <nav className="nav-menu">
          <button className={`nav-item ${activeTab === "dashboard" ? "active" : ""}`} onClick={() => setActiveTab("dashboard")}>
            <Database className="icon" />
            <span>Dashboard</span>
          </button>
          
          <button className={`nav-item ${activeTab === "queue" ? "active" : ""}`} onClick={() => setActiveTab("queue")}>
            <Video className="icon" />
            <span>Cola & Librería</span>
          </button>

          <button className={`nav-item ${activeTab === "chat" ? "active" : ""}`} onClick={() => setActiveTab("chat")}>
            <MessageSquare className="icon" />
            <span>Chat IA (Ollama)</span>
          </button>
          
          <button className={`nav-item ${activeTab === "agents" ? "active" : ""}`} onClick={() => setActiveTab("agents")}>
            <Terminal className="icon" />
            <span>Consola de Agentes</span>
          </button>
          
          <button className={`nav-item ${activeTab === "settings" ? "active" : ""}`} onClick={() => setActiveTab("settings")}>
            <Settings className="icon" />
            <span>Ajustes</span>
          </button>
        </nav>
        
        <div className="status-box">
          <div className="status-row">
            <span className="label">Conexión Local:</span>
            <span className={`badge ${isConnecting ? "error" : "success"}`}>
              {isConnecting ? "Sin Servidor" : "En línea"}
            </span>
          </div>
          <div className="status-row">
            <span className="label">Agentes WS:</span>
            <span className={`badge ${wsConnected ? "success" : "warning"}`}>
              {wsConnected ? "Conectado" : "Esperando"}
            </span>
          </div>
        </div>
      </aside>

      <main className="main-content">
        <header className="top-navbar">
          <div className="nav-title">
            <h1>
              {activeTab === "dashboard" && "Dashboard de Automatización"}
              {activeTab === "queue" && "Librería y Cola de Videos"}
              {activeTab === "chat" && "Asistente Chat Local (Ollama)"}
              {activeTab === "agents" && "Consola de Agentes Autónomos"}
              {activeTab === "settings" && "Configuración General"}
            </h1>
          </div>
          
          <div className="nav-actions">
            {tunnelUrl && (
              <a href={tunnelUrl} target="_blank" rel="noreferrer" className="tunnel-link" title="Túnel para acceder desde el celular">
                <Smartphone className="icon" />
                <span>Acceso Remoto Celular</span>
              </a>
            )}
            <button className="refresh-btn" onClick={fetchData}>
              <RefreshCw className="icon" />
            </button>
          </div>
        </header>

        <div className="page-body">
          {/* TAB 1: DASHBOARD */}
          {activeTab === "dashboard" && (
            <div className="dashboard-page animate-fade">
              <div className="cards-grid">
                <div className="card glass">
                  <div className="card-header">
                    <h3>Canales Registrados</h3>
                    <Plus className="header-icon" />
                  </div>
                  <div className="card-value">{channels.length}</div>
                  <div className="card-sub">YouTube, TikTok, Facebook</div>
                </div>

                <div className="card glass">
                  <div className="card-header">
                    <h3>Cola de Producción</h3>
                    <Video className="header-icon" />
                  </div>
                  <div className="card-value">{videoQueue.filter(v => v.estado !== "completado" && v.estado !== "fallido").length}</div>
                  <div className="card-sub">Videos en procesamiento</div>
                </div>

                <div className="card glass">
                  <div className="card-header">
                    <h3>Videos Creados</h3>
                    <CheckCircle className="header-icon" />
                  </div>
                  <div className="card-value">{videoQueue.filter(v => v.estado === "completado").length}</div>
                  <div className="card-sub">Guardados en /output/videos/</div>
                </div>
              </div>

              <div className="dash-row">
                <div className="dash-box glass col-6">
                  <h3 className="box-title">Crear Nuevo Short con IA</h3>
                  <form onSubmit={handleTriggerGeneration} className="gen-form">
                    <div className="form-group">
                      <label>Nicho del Canal</label>
                      <select value={nicho} onChange={(e) => setNicho(e.target.value)}>
                        <option value="psicologia y personalidad">Psicología y Personalidad (Ilustrado)</option>
                        <option value="finanzas personales">Finanzas Personales (Dopamínico)</option>
                        <option value="productividad">Productividad y Foco (Dopamínico)</option>
                      </select>
                    </div>

                    <div className="form-group">
                      <label>Tema Específico (Opcional)</label>
                      <input 
                        type="text" 
                        value={tema} 
                        onChange={(e) => setTema(e.target.value)} 
                        placeholder="Ej: Por qué procrastinamos cuando estamos tristes"
                      />
                    </div>

                    <button type="submit" className="primary-btn">
                      <Play className="btn-icon" />
                      <span>Iniciar Pipeline de Producción</span>
                    </button>
                  </form>
                </div>

                <div className="dash-box glass col-6">
                  <h3 className="box-title">Registrar Nueva Cuenta / Canal</h3>
                  <form onSubmit={handleAddChannel} className="inline-form">
                    <input 
                      type="text" 
                      placeholder="Nombre del Canal" 
                      value={newChanName} 
                      onChange={(e) => setNewChanName(e.target.value)} 
                      required
                    />
                    <select value={newChanPlat} onChange={(e) => setNewChanPlat(e.target.value)}>
                      <option value="youtube">YouTube</option>
                      <option value="tiktok">TikTok</option>
                      <option value="instagram">Instagram</option>
                      <option value="pinterest">Pinterest</option>
                      <option value="facebook">Facebook</option>
                    </select>
                    <button type="submit" className="add-btn">
                      <Plus />
                    </button>
                  </form>

                  <div className="channels-list">
                    {channels.map((chan) => (
                      <div key={chan.id_canal} className="channel-row">
                        <div className="channel-info">
                          <span className="channel-name">{chan.nombre}</span>
                          <span className="channel-platform">{chan.plataforma.toUpperCase()}</span>
                        </div>
                        <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
                          <button 
                            className="inline-btn"
                            onClick={() => handleTriggerLogin(chan.plataforma)}
                            title="Iniciar sesión en la PC"
                          >
                            Conectar
                          </button>
                          <span className="badge success">{chan.estado}</span>
                        </div>
                      </div>
                    ))}
                    {channels.length === 0 && (
                      <div className="empty-state">No hay canales registrados aún.</div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* TAB 2: QUEUE & LIBRARY */}
          {activeTab === "queue" && (
            <div className="queue-page animate-fade">
              <div className="media-split">
                <div className="queue-list-box glass">
                  <h3 className="box-title">Historial de Generaciones</h3>
                  <div className="queue-items">
                    {videoQueue.map((video) => (
                      <div 
                        key={video.id_video} 
                        className={`queue-item ${selectedVideo?.id_video === video.id_video ? "selected" : ""}`}
                        onClick={() => {
                          if (video.estado === "completado") setSelectedVideo(video);
                        }}
                      >
                        <div className="item-main">
                          <span className="item-title">{video.titulo}</span>
                          <span className="item-meta">{video.nicho} | {video.id_video}</span>
                        </div>
                        <div className="item-status">
                          <span className={`badge ${
                            video.estado === "completado" ? "success" : 
                            video.estado === "fallido" ? "error" : "processing"
                          }`}>
                            {video.estado}
                          </span>
                        </div>
                      </div>
                    ))}
                    {videoQueue.length === 0 && (
                      <div className="empty-state">No hay videos encolados.</div>
                    )}
                  </div>
                </div>

                <div className="media-player-box glass">
                  <h3 className="box-title">Reproductor e Inspección</h3>
                  {selectedVideo ? (
                    <div className="player-content">
                      <video 
                        key={selectedVideo.id_video}
                        controls 
                        className="video-player"
                        src={`${backendUrl}/output/videos/${selectedVideo.id_video}.mp4`}
                      />
                      <div className="video-details">
                        <h4>{selectedVideo.titulo}</h4>
                        <p><strong>Tema:</strong> {selectedVideo.tema}</p>
                        <p><strong>Nicho:</strong> {selectedVideo.nicho}</p>
                      </div>
                    </div>
                  ) : (
                    <div className="empty-player">
                      <Video className="big-icon" />
                      <p>Selecciona un video completado de la lista.</p>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* TAB 3: CHAT IA (OLLAMA) */}
          {activeTab === "chat" && (
            <div className="chat-page animate-fade">
              <div className="chat-container-box glass">
                <div className="chat-header-bar">
                  <div className="model-selector-group">
                    <label>Modelo Local:</label>
                    <select value={chatModel} onChange={(e) => setChatModel(e.target.value)}>
                      {ollamaModels.map((m) => (
                        <option key={m} value={m}>{m}</option>
                      ))}
                      {ollamaModels.length === 0 && (
                        <option value="qwen2.5-coder:latest">qwen2.5-coder (Ollama offline)</option>
                      )}
                    </select>
                  </div>
                  <span className="secure-badge">100% Local e Ilimitado</span>
                </div>

                <div className="chat-messages-area">
                  {chatMessages.map((msg, idx) => (
                    <div key={idx} className={`chat-message-row ${msg.role}`}>
                      <div className="message-avatar">
                        {msg.role === "user" ? "Tú" : "IA"}
                      </div>
                      <div className="message-bubble">
                        <p style={{ whiteSpace: "pre-line" }}>{msg.content}</p>
                        {msg.images && msg.images.map((img, i) => (
                          <img key={i} src={img} alt="attached" className="message-attached-image" />
                        ))}
                      </div>
                    </div>
                  ))}
                  {chatLoading && (
                    <div className="chat-message-row assistant">
                      <div className="message-avatar">IA</div>
                      <div className="message-bubble loading">
                        <Loader className="spinner" />
                        <span>Generando respuesta en Ollama...</span>
                      </div>
                    </div>
                  )}
                  <div ref={chatEndRef} />
                </div>

                {attachedImage && (
                  <div className="attached-preview-box">
                    <div className="preview-container">
                      <img src={attachedImage} alt="preview" />
                      <button className="remove-preview-btn" onClick={() => setAttachedImage(null)}>×</button>
                    </div>
                  </div>
                )}

                <form onSubmit={handleSendChatMessage} className="chat-input-bar">
                  <button 
                    type="button" 
                    className="attachment-btn" 
                    onClick={() => fileInputRef.current?.click()}
                    title="Subir archivo o imagen (Qwen2-VL/Vision)"
                  >
                    <Paperclip />
                  </button>
                  <input 
                    type="file" 
                    ref={fileInputRef} 
                    style={{ display: "none" }} 
                    accept="image/*"
                    onChange={handleImageAttach}
                  />
                  <input 
                    type="text" 
                    placeholder="Escribe tu mensaje o consulta al modelo local..."
                    value={chatInput}
                    onChange={(e) => setChatInput(e.target.value)}
                    disabled={chatLoading}
                  />
                  <button type="submit" className="send-btn" disabled={chatLoading}>
                    <Send />
                  </button>
                </form>
              </div>
            </div>
          )}

          {/* TAB 4: AGENTS TERMINAL */}
          {activeTab === "agents" && (
            <div className="agents-page animate-fade">
              <div className="terminal-box glass">
                <div className="terminal-header">
                  <div className="terminal-dots">
                    <span className="dot red"></span>
                    <span className="dot yellow"></span>
                    <span className="dot green"></span>
                  </div>
                  <span className="terminal-title">Consola de Agentes Autónomos (WS Live Feed)</span>
                </div>
                
                <div className="terminal-body">
                  {logs.map((log, idx) => (
                    <div key={idx} className={`log-row ${log.nivel.toLowerCase()}`}>
                      <span className="log-time">[{log.fecha.split(" ")[1] || log.fecha}]</span>
                      <span className="log-agent">&lt;{log.agente}&gt;</span>
                      <span className="log-message">{log.mensaje}</span>
                    </div>
                  ))}
                  {logs.length === 0 && (
                    <div className="log-row info">
                      <span className="log-message">Esperando eventos de los agentes...</span>
                    </div>
                  )}
                  <div ref={logsEndRef} />
                </div>
              </div>
            </div>
          )}

          {/* TAB 5: CONFIGURATION SETTINGS */}
          {activeTab === "settings" && (
            <div className="settings-page animate-fade glass">
              <h3 className="box-title">Parámetros del Pipeline y LLMs</h3>
              <div className="settings-form">
                
                <div className="settings-section">
                  <h4>Conexión con el Servidor</h4>
                  <div className="form-group">
                    <label>URL del Servidor de Backend (FastAPI)</label>
                    <div className="input-with-btn">
                      <input 
                        type="text" 
                        value={backendUrl} 
                        onChange={(e) => saveBackendUrl(e.target.value)} 
                        placeholder="Ej: http://localhost:8000"
                      />
                    </div>
                    <small>Ingresa tu URL pública de LocalTunnel/Ngrok si estás accediendo desde tu celular.</small>
                  </div>
                </div>

                <div className="settings-section">
                  <h4>Llaves de API (Guardado en base de datos local cifrada)</h4>
                  
                  <div className="form-group col-6">
                    <label>Groq API Key</label>
                    <input 
                      type="password" 
                      defaultValue={configs.GROQ_API_KEY?.valor || ""} 
                      onBlur={(e) => handleSaveConfig("GROQ_API_KEY", e.target.value, "api_keys")}
                      placeholder="gsk_..."
                    />
                  </div>

                  <div className="form-group col-6">
                    <label>RunPod API Key</label>
                    <input 
                      type="password" 
                      defaultValue={configs.RUNPOD_API_KEY?.valor || ""} 
                      onBlur={(e) => handleSaveConfig("RUNPOD_API_KEY", e.target.value, "api_keys")}
                      placeholder="Ingresa tu clave de RunPod"
                    />
                  </div>

                  <div className="form-group col-6">
                    <label>Pexels API Key</label>
                    <input 
                      type="password" 
                      defaultValue={configs.PEXELS_API_KEY?.valor || ""} 
                      onBlur={(e) => handleSaveConfig("PEXELS_API_KEY", e.target.value, "api_keys")}
                      placeholder="Ingresa tu clave de Pexels"
                    />
                  </div>

                  <div className="form-group col-6">
                    <label>URL ComfyUI (Opcional)</label>
                    <input 
                      type="text" 
                      defaultValue={configs.COMFYUI_URL?.valor || ""} 
                      onBlur={(e) => handleSaveConfig("COMFYUI_URL", e.target.value, "urls")}
                      placeholder="http://127.0.0.1:8188"
                    />
                  </div>
                </div>

                <div className="settings-section">
                  <h4>Motores de Generación de Contenido</h4>
                  
                  <div className="form-group col-6">
                    <label>Motor de Composición de Video</label>
                    <select 
                      defaultValue={configs.RENDER_MOTOR?.valor || "remotion"}
                      onChange={(e) => handleSaveConfig("RENDER_MOTOR", e.target.value, "video_settings")}
                    >
                      <option value="remotion">Remotion (React - Subtítulos Premium)</option>
                      <option value="ffmpeg">FFmpeg (Rápido local en CPU)</option>
                    </select>
                  </div>

                  <div className="form-group col-6">
                    <label>Origen de Ilustraciones por Defecto</label>
                    <select 
                      defaultValue={configs.IMAGEN_FUENTE?.valor || "pollinations"}
                      onChange={(e) => handleSaveConfig("IMAGEN_FUENTE", e.target.value, "video_settings")}
                    >
                      <option value="pollinations">Pollinations AI (Flux - Gratuito)</option>
                      <option value="runpod_comfy">RunPod + ComfyUI (Wan 2.1 - Video)</option>
                      <option value="pexels">Pexels (Fotos de stock)</option>
                    </select>
                  </div>
                </div>

              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
\"\"\"

with open("C:/Users/moral/youtube_automatizado/frontend/src/App.tsx", "w", encoding="utf-8") as f:
    f.write(app_tsx_content)
print("SUCCESS: frontend/src/App.tsx updated!")

# ─── 3. AGREGAR ESTILOS DEL CHAT A APP.CSS ─────────────────────────────

chat_css_content = \"\"\"
/* ─── CHAT IA PAGE ───────────────────────────────────────────────────── */
.chat-page {
  height: calc(100vh - 170px);
}
.chat-container-box {
  display: flex;
  flex-direction: column;
  height: 100%;
  border-radius: 16px;
  overflow: hidden;
  border: 1px solid var(--glass-border);
  background: rgba(18, 14, 37, 0.4);
}
.chat-header-bar {
  height: 50px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--glass-border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
}
.model-selector-group {
  display: flex;
  align-items: center;
  gap: 12px;
}
.model-selector-group label {
  font-size: 13px;
  color: var(--text-secondary);
  font-weight: 500;
}
.model-selector-group select {
  padding: 6px 12px;
  background-color: rgba(0, 0, 0, 0.3);
  border: 1px solid var(--glass-border);
  border-radius: 6px;
  color: var(--text-primary);
  font-family: inherit;
  font-size: 13px;
  outline: none;
}
.secure-badge {
  font-size: 11px;
  font-weight: 700;
  color: var(--accent-cyan);
  background: rgba(0, 240, 255, 0.1);
  padding: 4px 10px;
  border-radius: 20px;
  border: 1px solid rgba(0, 240, 255, 0.2);
  text-transform: uppercase;
}
.chat-messages-area {
  flex-grow: 1;
  padding: 24px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.chat-messages-area::-webkit-scrollbar {
  width: 8px;
}
.chat-messages-area::-webkit-scrollbar-thumb {
  background: var(--glass-border);
  border-radius: 4px;
}
.chat-message-row {
  display: flex;
  gap: 16px;
  max-width: 85%;
}
.chat-message-row.user {
  align-self: flex-end;
  flex-direction: row-reverse;
}
.chat-message-row.assistant {
  align-self: flex-start;
}
.message-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: var(--glass-border);
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 12px;
  border: 1px solid var(--glass-border);
}
.chat-message-row.user .message-avatar {
  background: linear-gradient(135deg, var(--accent-cyan), var(--accent-purple));
  color: #fff;
  border: none;
}
.message-bubble {
  padding: 12px 18px;
  border-radius: 16px;
  font-size: 15px;
  line-height: 1.5;
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
}
.chat-message-row.user .message-bubble {
  background: rgba(130, 0, 255, 0.12);
  border-color: rgba(130, 0, 255, 0.3);
  border-top-right-radius: 4px;
}
.chat-message-row.assistant .message-bubble {
  border-top-left-radius: 4px;
}
.message-attached-image {
  max-width: 250px;
  border-radius: 8px;
  margin-top: 10px;
  border: 1px solid var(--glass-border);
}
.message-bubble.loading {
  display: flex;
  align-items: center;
  gap: 12px;
  color: var(--text-secondary);
}
.spinner {
  width: 18px;
  height: 18px;
  animation: spin 1s linear infinite;
  color: var(--accent-cyan);
}
@keyframes spin {
  100% { transform: rotate(360deg); }
}
.attached-preview-box {
  padding: 10px 24px;
  border-top: 1px solid var(--glass-border);
  background: rgba(0, 0, 0, 0.2);
}
.preview-container {
  position: relative;
  display: inline-block;
}
.preview-container img {
  width: 80px;
  height: 80px;
  object-fit: cover;
  border-radius: 8px;
  border: 1px solid var(--accent-cyan);
}
.remove-preview-btn {
  position: absolute;
  top: -8px;
  right: -8px;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background-color: var(--error);
  color: #fff;
  border: none;
  font-size: 14px;
  font-weight: bold;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}
.chat-input-bar {
  height: 60px;
  border-top: 1px solid var(--glass-border);
  background: var(--bg-secondary);
  display: flex;
  align-items: center;
  padding: 0 16px;
  gap: 12px;
}
.chat-input-bar input[type='text'] {
  flex-grow: 1;
  height: 40px;
  background-color: rgba(0, 0, 0, 0.3);
  border: 1px solid var(--glass-border);
  border-radius: 8px;
  padding: 0 16px;
  color: var(--text-primary);
  font-family: inherit;
  outline: none;
}
.chat-input-bar input[type='text']:focus {
  border-color: var(--accent-cyan);
}
.attachment-btn, .send-btn {
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  color: var(--text-primary);
  width: 40px;
  height: 40px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.3s ease;
}
.attachment-btn:hover {
  border-color: var(--accent-cyan);
  color: var(--accent-cyan);
}
.send-btn {
  background: var(--accent-cyan);
  color: #000;
  border: none;
}
.send-btn:hover {
  transform: scale(1.05);
  box-shadow: 0 0 12px rgba(0, 240, 255, 0.4);
}
.send-btn:disabled, .attachment-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  transform: none;
}
\"\"\"

with open("C:/Users/moral/youtube_automatizado/frontend/src/App.css", "a", encoding="utf-8") as f:
    f.write(chat_css_content)
print("SUCCESS: frontend/src/App.css updated!")
"""

with open(r"C:\Users\moral\.gemini\antigravity-ide\scratch\write_upgrade.py", "w", encoding="utf-8") as f:
    f.write(upgrade_script_content)
print("SUCCESS: write_upgrade.py created in scratch!")
