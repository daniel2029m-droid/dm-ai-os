import os
import subprocess
import json
import shutil

def optimize_system():
    print("--- Iniciando Optimización de Recursos para Valeria Montesano Digital ---")
    
    # 1. Sugerencia de limpieza de temporales (Informativo)
    print("[!] Nota: Tienes 30GB de archivos temporales en C:. Se recomienda usar 'Limpieza de disco' en Windows.")

    # 2. Configuración de Ollama en Disco D
    ollama_custom_path = "D:\\OllamaModels"
    if os.path.exists("D:\\"):
        if not os.path.exists(ollama_custom_path):
            os.makedirs(ollama_custom_path)
            print(f"[+] Creada carpeta de modelos en {ollama_custom_path}")
        
        print("[*] Para que Ollama use el Disco D, debes cerrar Ollama y ejecutarlo con la variable OLLAMA_MODELS=" + ollama_custom_path)
    else:
        print("[!] No se detectó el Disco D para mover modelos.")

    # 3. Optimización del Bot (Timeouts y Hilos)
    # Actualizaremos config.py con parámetros de rendimiento
    config_path = "config.py"
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            lines = f.readlines()
        
        new_lines = []
        for line in lines:
            if "OLLAMA_API_URL" in line:
                new_lines.append(line)
                new_lines.append("\n# Parámetros de Optimización\n")
                new_lines.append("OLLAMA_KEEP_ALIVE = '5m'\n")
                new_lines.append("OLLAMA_NUM_THREAD = 4  # Deja núcleos libres para el sistema\n")
            else:
                new_lines.append(line)
        
        with open(config_path, 'w') as f:
            f.writelines(new_lines)
        print("[+] config.py actualizado con parámetros de rendimiento.")

if __name__ == "__main__":
    optimize_system()
