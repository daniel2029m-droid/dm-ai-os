"""
debug_comfy.py -- Script de diagnostico de navegacion ComfyUI Cloud
Ejecutar: python debug_comfy.py

Abre Chrome VISIBLE, hace login, y luego:
- Imprime el HTML del sidebar/nav
- Captura screenshots de cada paso
- Te muestra los selectores reales disponibles
"""
import asyncio
import os
import sys
import json
from playwright.async_api import async_playwright

# Forzar UTF-8 en stdout para evitar error de encoding en Windows
sys.stdout.reconfigure(encoding='utf-8')

# ─── CONFIGURAR CREDENCIALES AQUÍ ─────────────────────────────────────────────
EMAIL    = "TU_EMAIL_AQUI@gmail.com"
PASSWORD = "TU_CONTRASEÑA_AQUI"
# ──────────────────────────────────────────────────────────────────────────────

SCREENSHOT_DIR = r"C:\AgentScreenshots"
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

def shot(name):
    return os.path.join(SCREENSHOT_DIR, f"debug_{name}.png")

async def main():
    print("=" * 60)
    print("  DEBUG COMFYUI CLOUD — Navegación paso a paso")
    print("=" * 60)

    # Leer credenciales desde accounts.json si no se configuraron arriba
    if EMAIL == "TU_EMAIL_AQUI@gmail.com":
        try:
            from cryptography.fernet import Fernet
            with open('secret.key', 'rb') as f:
                key = f.read()
            cipher = Fernet(key)
            with open('accounts.json', 'rb') as f:
                accounts = json.loads(cipher.decrypt(f.read()))
            if accounts:
                email    = accounts[-1]['email']
                password = accounts[-1]['password']
                print(f"[OK] Credenciales leídas de accounts.json: {email}")
            else:
                print("[ERROR] accounts.json está vacío. Configura EMAIL y PASSWORD en este script.")
                return
        except Exception as e:
            print(f"[ERROR] No se pudo leer accounts.json: {e}")
            print("        Configura EMAIL y PASSWORD manualmente en debug_comfy.py líneas 15-16.")
            return
    else:
        email    = EMAIL
        password = PASSWORD

    async with async_playwright() as p:
        # Perfil temporal limpio
        user_data_dir = r"C:\AgentSessions\DebugProfile"
        try:
            import shutil
            if os.path.exists(user_data_dir):
                shutil.rmtree(user_data_dir, ignore_errors=True)
        except: pass
        os.makedirs(user_data_dir, exist_ok=True)

        context = await p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=False,  # VISIBLE para debug
            no_viewport=True,
            args=['--disable-blink-features=AutomationControlled', '--start-maximized'],
            ignore_default_args=['--enable-automation']
        )

        page = await context.new_page()
        await page.set_viewport_size({"width": 1600, "height": 900})

        # ── PASO 1: Ir a ComfyUI Cloud ──────────────────────────────────────
        print("\n[PASO 1] Navegando a https://cloud.comfy.org ...")
        await page.goto("https://cloud.comfy.org/")
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(2)
        print(f"         URL actual: {page.url}")
        await page.screenshot(path=shot("01_inicial"))
        print(f"         Screenshot guardado: {shot('01_inicial')}")

        # ── PASO 2: Login Google ────────────────────────────────────────────
        if "login" in page.url or "sign-in" in page.url or "signin" in page.url:
            print("\n[PASO 2] Pantalla de login detectada. Haciendo clic en Google...")
            try:
                # Esperar botón de Google
                await page.wait_for_selector("button:has-text('Log in with Google'), button:has-text('Sign in with Google')", timeout=10000)
                google_btn = page.locator("button:has-text('Log in with Google'), button:has-text('Sign in with Google')").first
                print(f"         Botón Google encontrado: '{await google_btn.inner_text()}'")

                async with context.expect_page() as popup_info:
                    await google_btn.click()

                popup = await popup_info.value
                await popup.wait_for_load_state("domcontentloaded")
                await asyncio.sleep(3)
                print(f"         Popup URL: {popup.url}")
                await popup.screenshot(path=shot("02_google_popup"))
                print(f"         Screenshot: {shot('02_google_popup')}")

                # ¿Selector de cuentas?
                try:
                    chooser = await popup.locator('text="Elige una cuenta"').is_visible(timeout=4000)
                except: chooser = False

                if chooser:
                    print("         [INFO] Pantalla 'Elige una cuenta'. Haciendo clic en 'Usar otra cuenta'...")
                    await popup.evaluate('''() => {
                        const all = document.querySelectorAll("*");
                        for (let el of all) {
                            const t = (el.childNodes.length === 1 && el.firstChild?.nodeType === 3)
                                ? el.textContent.trim() : "";
                            if (t === "Usar otra cuenta" || t === "Use another account") {
                                el.click(); return;
                            }
                        }
                    }''')
                    await asyncio.sleep(3)

                # Email
                print("         Ingresando email...")
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
                await popup.screenshot(path=shot("03_google_password"))

                # Password
                print("         Ingresando contraseña...")
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

                # Pantallas intermedias
                for attempt in range(5):
                    if popup.is_closed(): break
                    try:
                        consent = popup.locator(
                            'div[role="button"]:has-text("Continuar"), div[role="button"]:has-text("Continue"), '
                            'button:has-text("Continuar"), button:has-text("Continue"), '
                            'button:has-text("Acepto"), button:has-text("I agree"), '
                            'div[role="button"]:has-text("Ahora no"), button:has-text("Ahora no"), button:has-text("Not now")'
                        ).first
                        if await consent.is_visible(timeout=3000):
                            txt = await consent.inner_text()
                            print(f"         Aceptando pantalla intermedia: '{txt.strip()}'")
                            await consent.click()
                            await asyncio.sleep(4)
                        else: break
                    except: break

                # Esperar cierre del popup
                print("         Esperando cierre del popup de Google...")
                try:
                    if not popup.is_closed():
                        await popup.wait_for_event("close", timeout=20000)
                except: pass
                await asyncio.sleep(8)
                print(f"         URL tras login: {page.url}")

            except Exception as e:
                print(f"         [ERROR en login]: {e}")
                await page.screenshot(path=shot("02_login_error"))
                await context.close()
                return

        # ── PASO 3: POST-LOGIN — Inspeccionar la interfaz ────────────────────
        print(f"\n[PASO 3] Post-login. URL: {page.url}")
        await page.screenshot(path=shot("04_post_login"))
        print(f"         Screenshot: {shot('04_post_login')}")

        # Extraer estructura de la página
        print("\n[PASO 3.1] Extrayendo estructura de navegación...")
        nav_info = await page.evaluate('''() => {
            const results = [];

            // Buscar todos los elementos de navegación posibles
            const navSelectors = ['nav', 'aside', '[class*="sidebar"]', '[class*="nav"]', '[class*="menu"]', '[role="navigation"]'];
            for (const sel of navSelectors) {
                const els = document.querySelectorAll(sel);
                els.forEach(el => {
                    results.push({
                        selector: sel,
                        tag: el.tagName,
                        classes: el.className.substring(0, 200),
                        id: el.id,
                        text: el.innerText?.substring(0, 300),
                        children: el.children.length
                    });
                });
            }

            // Buscar botones con texto relevante
            const buttons = document.querySelectorAll("button, a[role='button'], [class*='btn']");
            const btnList = [];
            buttons.forEach(b => {
                const txt = b.innerText?.trim();
                if (txt && txt.length < 50) {
                    btnList.push({
                        tag: b.tagName,
                        text: txt,
                        classes: b.className?.substring(0, 100),
                        ariaLabel: b.getAttribute("aria-label"),
                        href: b.getAttribute("href")
                    });
                }
            });

            // Buscar inputs
            const inputs = [];
            document.querySelectorAll("input").forEach(inp => {
                inputs.push({
                    type: inp.type,
                    placeholder: inp.placeholder,
                    classes: inp.className?.substring(0, 100)
                });
            });

            return { navElements: results, buttons: btnList.slice(0, 30), inputs };
        }''')

        print("\n  NAV ELEMENTS:")
        for n in nav_info.get('navElements', []):
            print(f"    [{n['tag']}] sel={n['selector']} | id={n['id']} | children={n['children']}")
            print(f"         classes: {n['classes'][:80]}")
            print(f"         text:    {n['text'][:100] if n['text'] else 'N/A'}")

        print("\n  BUTTONS FOUND:")
        for b in nav_info.get('buttons', []):
            print(f"    [{b['tag']}] '{b['text']}' | aria-label={b['ariaLabel']} | href={b['href']}")
            print(f"           classes: {b['classes'][:80]}")

        print("\n  INPUTS FOUND:")
        for i in nav_info.get('inputs', []):
            print(f"    [input type={i['type']}] placeholder='{i['placeholder']}'")

        # ── PASO 4: Buscar el ícono/botón de Templates ───────────────────────
        print("\n[PASO 4] Buscando panel de Templates en la barra lateral...")

        # Intentar hacer clic en diferentes opciones del sidebar
        sidebar_attempts = [
            "text=Templates",
            "text=Plantillas",
            "text=Community",
            "[aria-label*='template' i]",
            "[aria-label*='Templates' i]",
            "[title*='template' i]",
            "nav li:nth-child(5)",
            "nav li:nth-child(6)",
            "aside li:nth-child(5)",
            "aside li:nth-child(6)",
        ]

        for sel in sidebar_attempts:
            try:
                el = page.locator(sel).first
                visible = await el.is_visible(timeout=1500)
                if visible:
                    txt = await el.inner_text()
                    print(f"    [VISIBLE] '{sel}' → texto: '{txt[:50]}'")
                else:
                    print(f"    [hidden]  '{sel}'")
            except:
                print(f"    [not found] '{sel}'")

        await page.screenshot(path=shot("05_sidebar_inspection"))
        print(f"\n  Screenshot sidebar: {shot('05_sidebar_inspection')}")

        # ── PASO 5: Imprimir HTML completo del sidebar ───────────────────────
        sidebar_html = await page.evaluate('''() => {
            // Buscar la barra lateral
            const candidates = [
                document.querySelector("nav"),
                document.querySelector("aside"),
                document.querySelector('[class*="sidebar"]'),
                document.querySelector('[class*="left-panel"]'),
                document.querySelector('[class*="leftbar"]'),
            ];
            for (const el of candidates) {
                if (el) return el.outerHTML.substring(0, 3000);
            }
            return "No se encontró sidebar";
        }''')
        print("\n[PASO 5] HTML del sidebar (primeros 3000 chars):")
        print("-" * 50)
        print(sidebar_html[:3000])
        print("-" * 50)

        # Guardar HTML completo en archivo
        html_path = os.path.join(SCREENSHOT_DIR, "debug_sidebar.html")
        with open(html_path, "w", encoding="utf-8") as f:
            full_html = await page.content()
            f.write(full_html)
        print(f"\n  HTML completo guardado en: {html_path}")

        # Esperar input del usuario antes de cerrar
        print("\n" + "=" * 60)
        print("  INSPECCIÓN COMPLETADA")
        print(f"  Screenshots en: {SCREENSHOT_DIR}")
        print("  El navegador permanecerá abierto 30 segundos para inspección manual...")
        print("=" * 60)
        await asyncio.sleep(30)
        await context.close()

if __name__ == "__main__":
    asyncio.run(main())
