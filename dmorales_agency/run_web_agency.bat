@echo off
title SERVIDOR WEB AGENCIA IA
echo [+] Iniciando Servidor Web Local...
echo [+] Tu sitio estara disponible en:
echo     LOCAL: http://localhost:8080
echo     RED LOCAL: http://192.168.1.100:8080
echo.
echo [!] Presiona Ctrl+C para detener el servidor.
python -m http.server 8080
pause
