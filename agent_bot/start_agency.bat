@echo off
title Agencia Valeria Montesano Digital - FULL PRO
color 0A
cls
chcp 65001 > nul

echo.
echo  ============================================================
echo   AGENCIA VALERIA MONTESANO DIGITAL - SISTEMA DE AGENTES IA
echo  ============================================================
echo.

:: 1. Configurar Disco C para modelos (ya no existe el disco D)
set OLLAMA_MODELS=C:\Users\moral\.ollama\models
set OLLAMA_HOST=127.0.0.1:11434
echo  [+] Modelos Ollama configurados en Disco C.

:: 2. Crear carpetas necesarias en C:
if not exist "C:\AgentSessions" mkdir "C:\AgentSessions"
if not exist "C:\AgentScreenshots" mkdir "C:\AgentScreenshots"
echo  [+] Carpetas de trabajo verificadas en C:.

:: 3. Verificar e Iniciar Ollama
tasklist | find /i "ollama.exe" > nul
if errorlevel 1 (
    echo  [!] Ollama no esta activo. Iniciando...
    start "" "ollama" serve
    echo  [+] Esperando 15 segundos para que Ollama levante...
    timeout /t 15 /nobreak > nul
)
echo  [+] Verificando modelo cerebral (qwen2.5:1.5b)...
ollama pull qwen2.5:1.5b
echo  [+] Cerebro listo.

:: 4. Verificar que Python existe
python --version > nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python no encontrado. Instala Python y agrega al PATH.
    pause
    exit
)
echo  [+] Python detectado OK.

:: 5. Ir al directorio del bot
cd /d "C:\Users\moral\.gemini\antigravity\scratch\agent_bot"

echo.
echo  ============================================================
echo   Iniciando Bot... (se reinicia solo si falla)
echo   Para APAGAR envia /kill en Telegram o cierra esta ventana.
echo  ============================================================
echo.

:: 6. Loop de auto-reinicio
:loop
echo [%date% %time%] Iniciando bot... >> bot_log.txt
python bot.py >> bot_log.txt 2>&1
echo [%date% %time%] Bot detenido. Reiniciando en 5 segundos... >> bot_log.txt
echo  [!] Bot caido. Reiniciando en 5 segundos...
timeout /t 5 /nobreak > nul
goto loop
