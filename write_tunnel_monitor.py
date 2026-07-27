import os

monitor_py_content = """#!/usr/bin/env python3
\"\"\"
backend/tunnel_monitor.py
=========================
Monitor y Auto-reinicio de Túneles LocalTunnel.
- Lanza los túneles del Frontend (1420) y Backend (8000) de forma asíncrona.
- Escucha la salida de consola en hilos separados para capturar las URLs.
- Guarda las URLs activas en la base de datos de configuraciones SQLite.
- Monitorea si algún proceso de túnel se cae y lo reinicia automáticamente de inmediato.
\"\"\"

import subprocess
import re
import time
import sys
import threading
from pathlib import Path

# Añadir raíz al path
sys.path.insert(0, str(Path(__file__).parent.parent))
import backend.database as db

def leer_consola_tunel(proc, port: int, url_key: str):
    \"\"\"Hilo que lee la salida estándar del túnel y captura la URL asignada.\"\"\"
    print(f"[MONITOR-TÚNEL {port}] Leyendo consola...")
    for line in iter(proc.stdout.readline, ""):
        if not line:
            break
        line_str = line.strip()
        print(f"[TÚNEL-{port}] {line_str}")
        
        # Expresión regular para buscar 'your url is: https://...'
        match = re.search(r"your url is:\s*(https://[a-zA-Z0-9\-\.]+)", line_str)
        if match:
            url = match.group(1)
            db.guardar_config(url_key, url, "red")
            print(f"🚀 [TÚNEL-{port}] URL guardada en DB: {url_key} = {url}")
            
    proc.stdout.close()

def main():
    tunnels = [
        {"port": 1420, "url_key": "REMOTE_FRONTEND_URL", "proc": None},
        {"port": 8000, "url_key": "REMOTE_TUNNEL_URL", "proc": None}
    ]
    
    print("📡 Iniciando Monitor de Túneles Autónomos. Manteniendo conexiones vivas...")
    while True:
        for t in tunnels:
            # Si el proceso no ha sido lanzado o terminó
            if t["proc"] is None or t["proc"].poll() is not None:
                if t["proc"] is not None:
                    print(f"⚠️ [TÚNEL-{t['port']}] Conexión caída. Reiniciando de inmediato...")
                
                cmd = ["npx", "localtunnel", "--port", str(t["port"]), "--local-host", "127.0.0.1"]
                try:
                    proc = subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        shell=True
                    )
                    t["proc"] = proc
                    
                    # Iniciar hilo secundario no bloqueante para leer salida
                    hilo = threading.Thread(
                        target=leer_consola_tunel,
                        args=(proc, t["port"], t["url_key"]),
                        daemon=True
                    )
                    hilo.start()
                except Exception as err:
                    print(f"❌ Error al iniciar túnel para puerto {t['port']}: {err}")
                    
        time.sleep(6)

if __name__ == "__main__":
    main()
"""

backend_dir = r"C:\Users\moral\youtube_automatizado\backend"
with open(os.path.join(backend_dir, "tunnel_monitor.py"), "w", encoding="utf-8") as f:
    f.write(monitor_py_content)
print("SUCCESS: backend/tunnel_monitor.py written successfully!")
