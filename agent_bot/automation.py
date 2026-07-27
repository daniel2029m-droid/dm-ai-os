"""
automation.py — AGENTE DE NAVEGACIÓN INTELIGENTE (VERSIÓN BLINDADA v3)
====================================================================
Este agente emula el comportamiento de un asistente humano:
- Detecta y cierra ventanas emergentes (Google, ComfyUI).
- Navega de forma adaptativa si los selectores cambian.
- Verifica créditos en tiempo real.
- Gestión de descargas robusta.
"""

import asyncio
import os
import json
import shutil
import time
import re
from pathlib import Path
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
from agent_browser import CognitiveBrowserAgent
from config import CHROME_PATH

# ============================================================
# === CONFIGURACIÓN Y RUTAS
# ============================================================
os.makedirs("C:\\AgentScreenshots", exist_ok=True)
os.makedirs("C:\\AgentScreenshots\\sessions", exist_ok=True)
LOG_FILE   = "C:\\AgentScreenshots\\automation_log.txt"
AUTH_STATE = Path(r"C:\AgentScreenshots\recordings\auth_state.json")

FINAL_DOWNLOAD_DIR  = Path(r"C:\Users\moral\Downloads\videos de @valeria")
DEFAULT_DOWNLOAD_DIR = Path(os.path.expanduser("~")) / "Downloads"
os.makedirs(FINAL_DOWNLOAD_DIR, exist_ok=True)

def _log(msg, session_id=None):
    ts = time.strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{ts}] {msg}"
    # Log general
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    # Log de sesión específica si existe
    if session_id:
        session_log = f"C:\\AgentScreenshots\\sessions\\log_{session_id}.txt"
        with open(session_log, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    print(line)

# ============================================================
# === SELECTORES DINÁMICOS (FALLBACK SYSTEM)
# ============================================================
SELECTORS = {
    "login_google_btn": [
        "button:has-text('Log in with Google')",
        "div[role='button']:has-text('Log in with Google')",
        "div:has-text('Log in with Google')",
        "button:has-text('Sign in with Google')",
        "[data-provider='google']",
    ],
    "account_picker": [
        "div[role='link']:has-text('{email}')",
        "div:has-text('{email}')",
        "[data-email='{email}']",
        "button:has-text('Añadir otra cuenta')",
        "button:has-text('Use another account')",
    ],
    "sidebar_items": ".p-menuitem-link, .sidebar-item, [role='menuitem']",
    "templates_btn": [
        "div[role='button']:has-text('Plantillas')",
        "span:has-text('Plantillas')",
        ".pi-folder-open",
        "button:has(i.pi-folder-open)",
    ],
    "search_input": [
        "input[placeholder*='Buscar']",
        "input[placeholder*='Search']",
        ".p-inputtext",
    ],
    "user_avatar": [
        ".p-avatar",
        "[class*='user-avatar']",
        "button:has(img)",
        "img[src*='googleusercontent']",
    ],
    "run_btn": [
        "button:has-text('Ejecutar')",
        "button:has-text('Run')",
        "[data-testid='queue-button']",
    ],
}

# ============================================================
# === AGENTE AUTÓNOMO
# ============================================================
class AutomationManager:
    def __init__(self):
        self.browser = None
        self.playwright = None
        self.context = None
        self.current_page = None
        self.session_id = None

    async def start(self, headless=False):
        self.playwright = await async_playwright().start()
        chrome_exe = CHROME_PATH if os.path.exists(CHROME_PATH) else None
        launch_args = {
            "executable_path": chrome_exe,
            "headless": headless,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--start-maximized",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-search-engine-choice-screen"
            ]
        }
        # Siempre iniciamos limpio para asegurar que el agente maneje el login según las credenciales actuales
        _log("[AGENT] Iniciando perfil limpio (Agente Activo)...")
        self.browser = await self.playwright.chromium.launch(**launch_args)
        self.context = await self.browser.new_context()

    def log(self, msg):
        _log(msg, self.session_id)

    async def _trace(self, page, step_name):
        """Radiografía técnica del estado actual de la página."""
        try:
            url = page.url
            title = await page.title()
            # Detectar elementos interesantes visibles
            buttons = await page.eval_on_selector_all("button, div[role='button'], a", "elements => elements.filter(e => e.offsetParent !== null).map(e => e.innerText.trim()).filter(t => t.length > 0)")
            inputs = await page.eval_on_selector_all("input", "elements => elements.filter(e => e.offsetParent !== null).map(e => e.placeholder || e.name || e.type)")
            
            trace_msg = f"\n[RADIOGRAFÍA: {step_name}]\n  URL: {url}\n  TÍTULO: {title}\n  BOTONES VISIBLES: {buttons[:15]}\n  INPUTS VISIBLES: {inputs}\n"
            self.log(trace_msg)
            
            # Screenshot de trazabilidad
            shot_path = f"C:\\AgentScreenshots\\sessions\\{self.session_id}_{step_name}.png"
            await page.screenshot(path=shot_path)
            self.log(f"  [📷] Captura guardada: {shot_path}")
        except Exception as e:
            self.log(f"  [⚠️] Error en radiografía: {e}")

    async def _handle_popups(self, page):
        """Maneja pantallas de bloqueo, llaves de acceso y otros avisos de Google."""
        try:
            # 1. Pantalla de Llaves de Acceso (Passkeys)
            if "speedbump/passkeyenrollment" in page.url:
                self.log("  [SPEEDBUMP] Detectada pantalla de Llaves de Acceso. Saltando...")
                btn = page.locator("button:has-text('Ahora no'), [role='button']:has-text('Ahora no')").first
                if await btn.is_visible(timeout=2000):
                    await btn.click()
                    await asyncio.sleep(2)
            
            # 2. Otros avisos comunes
            popups = ["Entendido", "Aceptar", "Confirmar", "Continuar"]
            for text in popups:
                btn = page.locator(f"button:has-text('{text}')").first
                if await btn.is_visible(timeout=500):
                    await btn.click()
        except:
            pass

    # ----------------------------------------------------------
    # FLUJO COMPLETO DE LOGIN (CON REPORTE EN TIEMPO REAL)
    # ----------------------------------------------------------
    async def run_full_login(self, email, password, status_callback):
        self.session_id = f"login_{int(time.time())}"
        try:
            await status_callback("Abriendo navegador seguro...")
            if not self.browser:
                await self.start(headless=False)

            page = self.current_page or await self.context.new_page()
            self.current_page = page
            
            await status_callback("Accediendo a Google Identidad...")
            ok = await self._login_google(page, email, password)
            
            if ok:
                await status_callback("✅ ¡Dentro! Sesión de ComfyUI verificada.")
                return True
            else:
                await status_callback("❌ El login falló o requiere intervención manual.")
                return False
        except Exception as e:
            await status_callback(f"⚠️ Error durante el proceso: {str(e)}")
            return False

    # ----------------------------------------------------------
    # MOTOR DE LOGIN ROBUSTO (PROPORCIONADO POR USUARIO)
    # ----------------------------------------------------------
    async def _human_delay(self, min_s=0.5, max_s=1.2):
        import random
        await asyncio.sleep(random.uniform(min_s, max_s))

    async def _wait_for_password_screen(self, page):
        for _ in range(10):
            if await page.get_by_text("Introduce tu contraseña").is_visible():
                return True
            await asyncio.sleep(1)
        return False

    async def _get_visible_password_input(self, page):
        await page.wait_for_selector('input[type="password"]', timeout=10000)
        inputs = page.locator('input[type="password"]')
        count = await inputs.count()
        for i in range(count):
            el = inputs.nth(i)
            if await el.is_visible():
                return el
        return None

    async def _type_password_human_like(self, input_el, password):
        await input_el.click()
        for char in password:
            await input_el.type(char, delay=80)
        value = await input_el.input_value()
        if value == "":
            raise Exception("No se escribió la contraseña")

    async def _click_next_button(self, page):
        for _ in range(5):
            btn = page.get_by_role("button", name="Siguiente")
            if await btn.is_visible():
                await btn.click()
                return True
            await asyncio.sleep(1)
        return False

    async def _detect_possible_blocks(self, page):
        if await page.get_by_text("Verifica que eres tú").is_visible():
            self.log("[ BLOQUEO ] Google activó verificación humana")
            return True
        if await page.get_by_text("Inténtalo de nuevo").is_visible():
            self.log("[ BLOQUEO ] Error de login genérico")
            return True
        return False

    # ----------------------------------------------------------
    # BÚSQUEDA INTELIGENTE
    # ----------------------------------------------------------
    async def _find(self, page, key, timeout=10000):
        """Búsqueda con registro de intentos detallado."""
        for sel in SELECTORS.get(key, []):
            try:
                el = page.locator(sel).first
                if await el.is_visible(timeout=1000):
                    self.log(f"  [DETECCIÓN ✓] {key} encontrado vía: {sel}")
                    return el
            except:
                continue
        # Fallback por texto si nada funciona
        try:
            return page.locator(f"text='{key}'").first
        except:
            return None

    async def _login_google(self, page, email, password):
        self.log("🔐 Iniciando login con Inteligencia Adaptativa...")
        brain = CognitiveBrowserAgent(page, session_id=self.session_id)
        await page.goto("https://accounts.google.com/")

        # Misión: Navegar hasta el éxito saltando obstáculos
        goal = f"Iniciar sesión con {email} y {password}. Si aparece 'Llaves de acceso', elige 'Ahora no'. Si ya estás en myaccount, responde 'done'."
        
        # Usamos el cerebro para el loop principal, apoyado por los handlers de speedbumps
        for i in range(15):
            await self._handle_popups(page)
            if "myaccount.google.com" in page.url:
                self.log("✅ Login Google Confirmado")
                break
            
            # Si el cerebro detecta el objetivo, lo ejecuta
            await brain.execute(goal, max_steps=1)
            await asyncio.sleep(2)

        # Traspaso a ComfyUI
        self.log("⚙️ Pasando a ComfyUI...")
        await page.goto("https://cloud.comfy.org/cloud/login", timeout=60000)
        await asyncio.sleep(4)
        
        login_btn = await self._find(page, "login_google_btn")
        if login_btn:
            await login_btn.click()
            await asyncio.sleep(10)
        
        return await page.locator(".p-avatar, [class*='user-avatar']").is_visible(timeout=15000)

    # ----------------------------------------------------------
    # PASO 2: VERIFICAR CRÉDITOS
    # ----------------------------------------------------------
    async def _verify_credits(self, page):
        self.log("[AGENTE PORTAL] Verificando créditos...")
        goal = "Hacer clic en el logo/avatar de usuario en la esquina superior derecha para ver el balance. Si ya ves los créditos, responde 'done'."
        await brain.execute(goal, max_steps=5)
        
        try:
            # Intento de lectura tradicional de balance como respaldo
            balance_text = await page.locator(".p-balance, [class*='balance']").first.inner_text()
            self.log(f"  [BALANCE] Detectado: {balance_text}")
            return "-" not in balance_text
        except:
            self.log("  [AVISO] No se pudo leer balance exacto, asumiendo OK por ahora.")
            return True

    # ----------------------------------------------------------
    # PASO 3: NAVEGAR A TEMPLATES
    # ----------------------------------------------------------
    async def _navigate_to_templates(self, page, template_name="grok"):
        brain = CognitiveBrowserAgent(page, session_id=self.session_id)
        self.log(f"[AGENTE PRODUCCIÓN] Buscando template: {template_name}")
        
        goal = f"Navegar al apartado de Plantillas o Templates y buscar '{template_name}'. Una vez abierto el workflow, responde 'done'."
        return await brain.execute(goal)

    # ----------------------------------------------------------
    # PASO 2: VERIFICAR CRÉDITOS (TOP RIGHT LOGO)
    # ----------------------------------------------------------
    async def _verify_credits(self, page):
        _log("[AGENT] Verificando créditos...")
        avatar = await self._find(page, "user_avatar")
        if avatar:
            await avatar.click()
            await asyncio.sleep(2)
            
            # Buscar texto de créditos en el menú desplegable
            menu = page.locator(".p-menu, .user-menu, .p-popover").first
            text = await menu.inner_text()
            _log(f"[AGENT] Info Usuario: {text}")
            
            # Buscar números
            match = re.search(r'(-?\d+)', text)
            if match:
                credits = int(match.group(1))
                if credits <= 0:
                    _log(f"[AGENT] ❌ Créditos insuficientes ({credits}).")
                    return False
                _log(f"[AGENT] ✅ Créditos positivos: {credits}")
                return True
        
        _log("[AGENT] ⚠️ No se pudo verificar créditos. Continuando...")
        return True

    # ----------------------------------------------------------
    # PASO 3: NAVEGAR A PLANTILLAS (6ta OPCIÓN)
    # ----------------------------------------------------------
    async def _navigate_to_templates(self, page, template_type):
        _log("[AGENT] Abriendo Plantillas (6ta opción lateral)...")
        # Intentar click en la 6ta opción del sidebar directamente
        try:
            sidebar_items = page.locator(SELECTORS["sidebar_items"])
            if await sidebar_items.count() >= 6:
                await sidebar_items.nth(5).click() # 0-indexed, so 5 is the 6th
                await asyncio.sleep(3)
            else:
                # Fallback al botón por texto
                btn = await self._find(page, "templates_btn")
                await btn.click()
                await asyncio.sleep(3)
        except:
            await page.goto("https://cloud.comfy.org/workflows")
            await asyncio.sleep(5)

        # Buscar por texto en el panel
        search_term = "grok" if "grok" in template_type.lower() else template_type
        search_box = await self._find(page, "search_input")
        await search_box.fill(search_term)
        await page.keyboard.press("Enter")
        await asyncio.sleep(3)

        # Seleccionar tarjeta
        target = "Imagen a Video" if "grok" in template_type.lower() else template_type
        card = page.locator(f"div[role='button']:has-text('{target}'), .p-card:has-text('{target}')").first
        await card.click()
        await asyncio.sleep(5)
        return True

    # ----------------------------------------------------------
    # PASO 4: EJECUCIÓN Y DESCARGA
    # ----------------------------------------------------------
    async def _run_and_download(self, page, file_path, batch_count):
        # Subir imagen
        if file_path:
            await page.locator("input[type='file']").first.set_input_files(file_path)
            await asyncio.sleep(2)

        # Run
        run_btn = await self._find(page, "run_btn")
        for _ in range(batch_count):
            await run_btn.click()
            await asyncio.sleep(1)

        _log("[AGENT] Esperando generación (90s)...")
        await asyncio.sleep(90)

        # Descargar
        await page.locator("button:has(i.pi-image), .pi-image").first.click()
        await asyncio.sleep(2)
        
        # Click derecho en primer asset
        asset = page.locator(".media-asset-item, .asset-card").first
        await asset.click(button="right")
        await page.locator("text='Descargar', text='Download'").first.click()
        
        # Monitorear carpeta
        return await self._move_file()

    async def _move_file(self, timeout=60):
        _log("[FS] Monitoreando descargas...")
        start = time.time()
        while time.time() - start < timeout:
            for f in os.listdir(DEFAULT_DOWNLOAD_DIR):
                if not (f.endswith(".tmp") or f.endswith(".crdownload")):
                    src = DEFAULT_DOWNLOAD_DIR / f
                    dst = FINAL_DOWNLOAD_DIR / f"{Path(f).stem}.mp4"
                    shutil.move(str(src), str(dst))
                    return str(dst)
            await asyncio.sleep(2)
        return None

    # ----------------------------------------------------------
    # ENTRY POINT
    # ----------------------------------------------------------
    async def run_comfy_task(self, email, password, prompt, file_path=None, batch_count=1, template_type="grok", kling_sample_path=None):
        self.session_id = f"{template_type}_{int(time.time())}"
        self.log(f"\n{'#'*60}\n# INICIANDO SESIÓN RADIOGRAFÍA: {self.session_id}\n{'#'*60}")
        await self.start(headless=False)
        page = await self.context.new_page()
        
        try:
            # 1. Login
            if not await self._login_google(page, email, password):
                return {"status": "error", "message": "Fallo en Login Google"}

            # 2. Créditos
            await self._trace(page, "Verificar_Creditos")
            if not await self._verify_credits(page):
                return {"status": "error", "message": "Créditos insuficientes"}

            # 3. Navegar
            await self._trace(page, "Antes_Navegar_Templates")
            await self._navigate_to_templates(page, template_type)
            await self._trace(page, "En_Workflow")

            # 4. Ejecutar y Descargar
            path = await self._run_and_download(page, file_path, batch_count)
            await self._trace(page, "Fin_Proceso")
            
            return {"status": "success", "message": "Proceso completado", "file_path": path}
        except Exception as e:
            self.log(f"[CRÍTICO] Error en flujo: {e}")
            await self._trace(page, "ERROR_FINAL")
            return {"status": "error", "message": str(e)}
        finally:
            await self.browser.close()
            await self.playwright.stop()

automation_manager = AutomationManager()
