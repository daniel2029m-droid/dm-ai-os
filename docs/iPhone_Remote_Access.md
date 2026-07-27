# DM AI OS — iPhone Remote Access Guide

Esta guía explica cómo conectar tu iPhone u otros dispositivos remotos de forma segura a DM AI OS cuando estás fuera de la red local, usando la compatibilidad con OpenAI.

## 1. Exponer la API al Exterior

Dado que el API Gateway corre en `localhost:8000`, debes exponerlo de forma segura. Utilizaremos **Cloudflare Quick Tunnels** que proveen HTTPS automático sin configuraciones en tu router.

**En el equipo anfitrión de DM AI OS:**
1. Inicia el sistema normalmente:
   ```powershell
   python src/api/server.py
   ```
2. En otra terminal, levanta el túnel ejecutando el script proporcionado:
   ```powershell
   .\scripts\start_tunnel.ps1
   ```
3. El script te proporcionará una URL pública segura (e.g., `https://something.trycloudflare.com`). **Copia esta URL.**

> **Nota:** La URL del túnel rápido cambia cada vez que ejecutas el script. Si deseas una URL fija, considera registrarte en [Cloudflare Zero Trust](https://one.dash.cloudflare.com/) y crear un túnel persistente, o instalar [Tailscale](https://tailscale.com/) y usar la IP asignada por Tailscale en el dispositivo (ej. `http://100.x.y.z:8000`).

## 2. Comprobar Conectividad (Sin Autenticación)

El endpoint de salud es público y no requiere API Key. Sirve para validar que el túnel funciona.
- Desde el navegador de tu iPhone entra a: `https://<TU_URL_TÚNEL>/health`
- Deberías ver: `{"status":"ONLINE","version":"v1.4.0-production"}`

## 3. Configuración en la App Cliente (iOS)

Puedes utilizar cualquier cliente compatible con OpenAI en tu iPhone. Se recomienda **Chatbox** (disponible en la App Store) u **Open WebUI** (si lo tienes alojado).

**Instrucciones para Chatbox (o similar):**
1. Descarga y abre la app Chatbox.
2. Ve a los **Settings (Ajustes)** y selecciona el proveedor de IA: **Custom OpenAI** (u OpenAI API).
3. Configura los siguientes campos:
   - **API Host / Base URL:** La URL del túnel terminada en `/v1` (Ejemplo: `https://something.trycloudflare.com/v1`).
   - **API Key:** Ingresa la clave maestra configurada (por defecto: `dm-secret-key-v1` o tu `DM_API_KEY`).
   - **Model:** `llama3.2` (o cualquier modelo detectado localmente por DM AI OS).
4. Guarda la configuración.
5. Inicia una conversación; tus mensajes serán ruteados al `BrainPipeline` local a través de internet de manera segura.

## Seguridad

- **No compartas tu URL de Cloudflare si no tienes autenticación habilitada.**
- Verifica que en `config/openai_security.json` el valor `"require_auth"` sea `true` y `"auth_mode"` sea `"both"`. 
- Esto garantiza que todas las peticiones requieran el encabezado `Authorization: Bearer <API_KEY>` o `X-API-Key: <API_KEY>`.
