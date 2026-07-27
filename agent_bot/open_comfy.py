"""
open_comfy.py — Abre ComfyUI Cloud y se desconecta
====================================================
Hace el login automatico y luego DESCONECTA el script Python
del navegador. El browser queda completamente independiente
y NUNCA se cierra solo aunque el script termine.

Luego abre una segunda ventana del Inspector de Chrome para
que cada accion que hagas quede registrada en la consola.

USO: python open_comfy.py
"""

import asyncio
import os
import sys
import json
import subprocess
import time
from pathlib import Path
from playwright.async_api import async_playwright

sys.stdout.reconfigure(encoding='utf-8')

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PROFILE_DIR = r"C:\AgentSessions\ComfySession"
AUTH_FILE   = Path(r"C:\AgentScreenshots\recordings\auth_state.json")
AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)


async def do_login(email, password):
    """Hace login y guarda las cookies en auth_state.json."""
    async with async_playwright() as p:
        # Limpiar perfil anterior
        try:
            import shutil
            if os.path.exists(PROFILE_DIR):
                shutil.rmtree(PROFILE_DIR, ignore_errors=True)
        except: pass
        os.makedirs(PROFILE_DIR, exist_ok=True)

        print("  Abriendo navegador para login...")
        context = await p.chromium.launch_persistent_context(
            user_data_dir=PROFILE_DIR,
            headless=False,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--start-maximized',
                '--no-first-run',
                '--no-default-browser-check',
            ],
            ignore_default_args=['--enable-automation'],
        )

        page = await context.new_page()
        await page.set_viewport_size({"width": 1600, "height": 900})

        await page.goto("https://cloud.comfy.org/")
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=12000)
        except: pass
        await asyncio.sleep(2)

        if "login" not in page.url and "sign-in" not in page.url:
            print("  Ya habia sesion activa.")
            await context.storage_state(path=str(AUTH_FILE))
            await context.close()
            return True

        # Boton Google
        print(f"  Iniciando sesion con Google para {email}...")
        await page.wait_for_selector(
            "button:has-text('Log in with Google'), button:has-text('Sign in with Google')",
            timeout=12000
        )
        btn = page.locator(
            "button:has-text('Log in with Google'), button:has-text('Sign in with Google')"
        ).first

        async with context.expect_page() as pi:
            await btn.click()
        popup = await pi.value
        await popup.wait_for_load_state("domcontentloaded")
        await asyncio.sleep(3)

        # "Elige una cuenta"?
        try:
            chooser = await popup.locator('text="Elige una cuenta"').is_visible(timeout=4000)
        except: chooser = False
        if chooser:
            await popup.evaluate("""() => {
                for (let el of document.querySelectorAll('*')) {
                    const t = el.childNodes.length===1&&el.firstChild?.nodeType===3
                        ? el.textContent.trim() : '';
                    if (t==='Usar otra cuenta'||t==='Use another account'){el.click();return;}
                }
            }""")
            await asyncio.sleep(3)

        # Email
        await popup.wait_for_selector('input[type="email"]', state="visible", timeout=10000)
        await asyncio.sleep(1)
        await popup.locator('input[type="email"]').first.fill(email)
        await asyncio.sleep(1)
        try:
            nb = popup.locator('button:has-text("Siguiente"), button:has-text("Next")').first
            if await nb.is_visible(timeout=2000): await nb.click()
            else: await popup.keyboard.press("Enter")
        except: await popup.keyboard.press("Enter")
        await asyncio.sleep(4)
        print(f"  Email OK.")

        # Password
        await popup.wait_for_selector('input[type="password"]', state="visible", timeout=10000)
        await asyncio.sleep(1)
        await popup.locator('input[type="password"]').first.fill(password)
        await asyncio.sleep(1)
        try:
            nb = popup.locator('button:has-text("Siguiente"), button:has-text("Next")').first
            if await nb.is_visible(timeout=2000): await nb.click()
            else: await popup.keyboard.press("Enter")
        except: await popup.keyboard.press("Enter")
        await asyncio.sleep(5)
        print("  Password OK.")

        # Pantallas intermedias
        for _ in range(5):
            if popup.is_closed(): break
            try:
                c = popup.locator(
                    'div[role="button"]:has-text("Continuar"), div[role="button"]:has-text("Continue"), '
                    'button:has-text("Continuar"), button:has-text("Continue"), '
                    'button:has-text("Acepto"), button:has-text("I agree"), '
                    'div[role="button"]:has-text("Ahora no"), button:has-text("Ahora no")'
                ).first
                if await c.is_visible(timeout=3000):
                    txt = await c.inner_text()
                    print(f"  Aceptando: '{txt.strip()}'")
                    await c.click(); await asyncio.sleep(4)
                else: break
            except: break

        try:
            if not popup.is_closed():
                await popup.wait_for_event("close", timeout=25000)
        except: pass
        await asyncio.sleep(7)

        try:
            await page.wait_for_load_state("domcontentloaded", timeout=10000)
        except: pass
        await asyncio.sleep(4)

        if "login" in page.url:
            print("  [ERROR] Login fallido.")
            await context.close()
            return False

        print(f"  Workspace cargado: {page.url}")

        # Guardar cookies/estado
        await context.storage_state(path=str(AUTH_FILE))
        print(f"  Sesion guardada en: {AUTH_FILE}")

        # NO cerrar el contexto todavia — dejamos que el GC lo maneje
        # El perfil persistente queda en PROFILE_DIR con la sesion activa
        await context.close()
        return True


def launch_chrome_with_profile():
    """
    Abre Chrome directamente (no via Playwright) con el perfil
    que ya tiene la sesion activa. Este Chrome es 100% independiente
    de Python — nunca se cierra por Python.
    """
    if not os.path.exists(CHROME_PATH):
        # Buscar Chrome en otras ubicaciones
        paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        ]
        chrome = None
        for p in paths:
            if os.path.exists(p):
                chrome = p
                break
        if not chrome:
            print("  [ERROR] Chrome no encontrado. Abre chrome manualmente e ingresa a:")
            print("  https://cloud.comfy.org/")
            return False
    else:
        chrome = CHROME_PATH

    cmd = [
        chrome,
        f"--user-data-dir={PROFILE_DIR}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-blink-features=AutomationControlled",
        "--start-maximized",
        "https://cloud.comfy.org/",
    ]

    print(f"  Abriendo Chrome con sesion activa...")
    # Popen = no bloquea, el proceso de Chrome vive por su cuenta
    subprocess.Popen(cmd)
    return True


def main():
    print("=" * 65)
    print("  ABRIR COMFYUI CLOUD — Sesion Independiente")
    print("=" * 65)
    print()

    # Leer credenciales
    try:
        from cryptography.fernet import Fernet
        with open('secret.key', 'rb') as f: key = f.read()
        cipher = Fernet(key)
        with open('accounts.json', 'rb') as f:
            accounts = json.loads(cipher.decrypt(f.read()))
        if not accounts:
            print("[ERROR] No hay cuentas guardadas.")
            return
        email    = accounts[-1]['email']
        password = accounts[-1]['password']
        print(f"  Cuenta: {email}")
        print()
    except Exception as e:
        print(f"[ERROR] Credenciales: {e}"); return

    # Paso 1: Login con Playwright (ventana temporal)
    print("PASO 1: Login automatico")
    print("-" * 40)
    ok = asyncio.run(do_login(email, password))
    if not ok:
        print("[ERROR] Login fallido.")
        return

    print()
    print("PASO 2: Abriendo Chrome independiente")
    print("-" * 40)

    # Esperar un momento para que el perfil quede limpio
    time.sleep(2)

    ok = launch_chrome_with_profile()
    if not ok:
        return

    print()
    print("=" * 65)
    print("  Chrome abierto con tu sesion activa.")
    print()
    print("  El navegador es COMPLETAMENTE INDEPENDIENTE de Python.")
    print("  Podras cerrar esta ventana de terminal y el Chrome")
    print("  seguira abierto.")
    print()
    print("  REALIZA TU FLUJO MANUAL EN COMFYUI:")
    print("  1. Clic en 'Plantillas' (barra lateral izquierda)")
    print("  2. Busca el template (grok, nanobana, kling...)")
    print("  3. Carga la plantilla en el lienzo")
    print("  4. Sube imagen de referencia")
    print("  5. Escribe el prompt")
    print("  6. Clic en 'Ejecutar'")
    print()
    print("  Cuando termines, avisa y extraeremos el flujo del")
    print("  historial del navegador para generar el codigo.")
    print("=" * 65)


if __name__ == "__main__":
    main()
