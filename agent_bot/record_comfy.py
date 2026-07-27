"""
record_comfy.py — Grabador de Sesion ComfyUI Cloud
===================================================
ESTRATEGIA:
  1. Python hace el login automatico y guarda las cookies de sesion
  2. Lanza 'playwright codegen' (herramienta nativa) con la sesion guardada
  3. El codegen abre su propio navegador INDEPENDIENTE del script Python
     → el browser NUNCA se cierra solo aunque el script termine
  4. Tu navegas libremente, codegen graba cada accion en tiempo real
  5. Al cerrar el navegador, el codigo Python generado se guarda

USO: python record_comfy.py [grok|nanobana|kling]
"""

import asyncio
import os
import sys
import json
import subprocess
from pathlib import Path
from playwright.async_api import async_playwright

sys.stdout.reconfigure(encoding='utf-8')

SCENARIO   = sys.argv[1] if len(sys.argv) > 1 else "grok"
BASE_DIR   = Path(r"C:\AgentScreenshots\recordings")
BASE_DIR.mkdir(parents=True, exist_ok=True)
AUTH_FILE  = BASE_DIR / "auth_state.json"
CODE_FILE  = BASE_DIR / f"comfy_{SCENARIO}_code.py"


async def do_login_and_save(email, password):
    """Hace login en ComfyUI y guarda el estado de sesion."""
    print("  [1/3] Iniciando login automatico...")

    async with async_playwright() as p:
        # Perfil temporal limpio
        ud = r"C:\AgentSessions\LoginTemp"
        try:
            import shutil
            if os.path.exists(ud): shutil.rmtree(ud, ignore_errors=True)
        except: pass
        os.makedirs(ud, exist_ok=True)

        context = await p.chromium.launch_persistent_context(
            user_data_dir=ud,
            headless=False,
            args=['--disable-blink-features=AutomationControlled'],
            ignore_default_args=['--enable-automation'],
        )
        page = await context.new_page()
        await page.set_viewport_size({"width": 1280, "height": 800})

        await page.goto("https://cloud.comfy.org/")
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=15000)
        except: pass
        await asyncio.sleep(2)

        if "login" in page.url or "sign-in" in page.url:
            # Click en boton de Google
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
                        const t = el.childNodes.length === 1 && el.firstChild?.nodeType === 3
                            ? el.textContent.trim() : '';
                        if (t === 'Usar otra cuenta' || t === 'Use another account') {
                            el.click(); return;
                        }
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
            print(f"     Email ingresado: {email}")

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
            print("     Contrasena ingresada.")

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
                        await c.click(); await asyncio.sleep(4)
                    else: break
                except: break

            try:
                if not popup.is_closed():
                    await popup.wait_for_event("close", timeout=25000)
            except: pass
            await asyncio.sleep(7)

        # Verificar que estamos en el workspace
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=15000)
        except: pass
        await asyncio.sleep(4)

        current_url = page.url
        if "login" in current_url or "sign-in" in current_url:
            print("  [ERROR] Login fallido. El navegador sigue en la pantalla de login.")
            await context.close()
            return False

        print(f"     Workspace cargado: {current_url}")

        # Guardar estado de sesion (cookies + localStorage)
        await context.storage_state(path=str(AUTH_FILE))
        print(f"  [OK] Sesion guardada en: {AUTH_FILE}")

        await context.close()
        return True


def launch_codegen(scenario, auth_file, code_file):
    """
    Lanza playwright codegen con la sesion guardada.
    El navegador es completamente independiente — no se cierra solo.
    """
    print()
    print("  [2/3] Lanzando Playwright Codegen...")
    print()
    print("  ┌─────────────────────────────────────────────────────────┐")
    print("  │  SE ABRIRA UN NAVEGADOR CON TU SESION ACTIVA            │")
    print("  │                                                          │")
    print(f"  │  Escenario a grabar: {scenario.upper():<34}│")
    print("  │                                                          │")
    print("  │  Pasos a realizar:                                       │")
    print("  │  1. Clic en icono 'Plantillas' (barra lateral)           │")
    print(f"  │  2. Buscar '{scenario}' en el buscador                       │" if len(scenario) < 10 else f"  │  2. Buscar '{scenario}' en el buscador              │")
    print("  │  3. Cargar la plantilla en el lienzo                     │")
    print("  │  4. Subir imagen de referencia                           │")
    print("  │  5. Escribir el prompt                                   │")
    print("  │  6. Clic en 'Ejecutar' / 'Queue Prompt'                  │")
    print("  │                                                          │")
    print("  │  Cuando termines: cierra el navegador (X roja)           │")
    print("  │  El codigo se guardara automaticamente.                  │")
    print("  └─────────────────────────────────────────────────────────┘")
    print()

    # Comando: playwright codegen con sesion guardada
    cmd = [
        sys.executable, "-m", "playwright", "codegen",
        "--load-storage", str(auth_file),   # cargar sesion guardada
        "--target", "python-async",          # generar codigo Python async
        "--output", str(code_file),          # guardar codigo aqui
        "--viewport-size", "1600,900",
        "https://cloud.comfy.org/",          # URL de inicio
    ]

    print(f"  Comando: {' '.join(cmd[2:])}")
    print()

    # Ejecutar codegen — esto BLOQUEA hasta que el usuario cierre el navegador
    result = subprocess.run(cmd)

    return result.returncode == 0


def post_process_code(code_file, scenario):
    """
    Lee el codigo generado por codegen y lo adapta
    para integrarlo directamente en automation.py
    """
    if not code_file.exists():
        print(f"  [AVISO] No se genero el archivo de codigo: {code_file}")
        return

    raw = code_file.read_text(encoding='utf-8')
    print()
    print("  [3/3] Procesando codigo generado...")
    print()
    print("  ─── CODIGO GENERADO (listo para automation.py) ────────────")
    print()
    print(raw[:3000])
    if len(raw) > 3000:
        print(f"  ... ({len(raw)-3000} caracteres mas en el archivo)")
    print()
    print("  ────────────────────────────────────────────────────────────")
    print()
    print(f"  Archivo completo en: {code_file}")
    print()
    print("  SIGUIENTE PASO:")
    print("  Revisa el codigo arriba y dile a Antigravity:")
    print(f"  'Integra el codigo de {code_file.name} en automation.py'")


def main():
    print("=" * 65)
    print(f"  GRABADOR COMFYUI CLOUD — Escenario: {SCENARIO.upper()}")
    print("=" * 65)
    print()

    # Leer credenciales cifradas
    try:
        from cryptography.fernet import Fernet
        with open('secret.key', 'rb') as f: key = f.read()
        cipher = Fernet(key)
        with open('accounts.json', 'rb') as f:
            accounts = json.loads(cipher.decrypt(f.read()))
        if not accounts:
            print("[ERROR] No hay cuentas. Envia las credenciales al bot primero.")
            return
        email    = accounts[-1]['email']
        password = accounts[-1]['password']
        print(f"  Cuenta: {email}")
        print()
    except Exception as e:
        print(f"[ERROR] No se pudieron leer credenciales: {e}")
        return

    # Paso 1: Login y guardar sesion
    ok = asyncio.run(do_login_and_save(email, password))
    if not ok:
        print("[ERROR] No se pudo completar el login. Revisa las credenciales.")
        return

    # Paso 2: Lanzar codegen con sesion guardada
    print()
    input("  Presiona ENTER para abrir el navegador de grabacion...")
    print()

    success = launch_codegen(SCENARIO, AUTH_FILE, CODE_FILE)

    # Paso 3: Mostrar y procesar el codigo generado
    if success or CODE_FILE.exists():
        post_process_code(CODE_FILE, SCENARIO)
    else:
        print()
        print("  [AVISO] El codegen termino sin generar codigo.")
        print("          Esto pasa si cierras el navegador antes de hacer alguna accion.")
        print(f"          Si grabaste algo, el archivo estara en: {CODE_FILE}")


if __name__ == "__main__":
    main()
