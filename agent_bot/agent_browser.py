import asyncio, json, base64, time, os
from typing import Dict, Any, List
import httpx
from playwright.async_api import async_playwright

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "qwen2.5:1.5b" 

SYSTEM_PROMPT = """
Eres el Agente de Navegación de la Agencia Valeria. Tu misión es lograr objetivos específicos en la web.
Recibirás:
1) Objetivo de alto nivel.
2) Snapshot del DOM (roles y texto).
3) Historial de acciones recientes.

Debes responder ÚNICAMENTE en formato JSON:
{
 "action": "click|type|wait|done|error",
 "target": "texto exacto del botón o campo",
 "value": "texto a escribir (solo si action es type)",
 "reason": "breve explicación de por qué haces esto"
}

Reglas de Oro:
- Prioriza botones por su texto visible (ej: "Siguiente", "Log in with Google").
- Si ves el campo de contraseña, usa "type" inmediatamente.
- Si el objetivo (ej: estar logueado) ya es visible, usa "done".
- Si hay un error persistente, usa "error".
"""

class CognitiveBrowserAgent:
    def __init__(self, page, session_id="dev"):
        self.page = page
        self.session_id = session_id
        self.history = []

    def _log(self, msg):
        ts = time.strftime('%H:%M:%S')
        print(f"[{ts}] [BRAIN-{self.session_id}] {msg}")
        with open(f"C:\\AgentScreenshots\\sessions\\brain_log_{self.session_id}.txt", "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")

    async def get_perception(self) -> str:
        # Extraer elementos interactivos visibles
        script = """
        () => {
          return Array.from(document.querySelectorAll('button, input, [role="button"], a, [role="link"]'))
            .filter(el => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0 && window.getComputedStyle(el).visibility !== 'hidden';
            })
            .map(el => ({
                role: el.getAttribute('role') || el.tagName.toLowerCase(),
                text: (el.innerText || el.value || el.getAttribute('aria-label') || el.placeholder || '').trim().slice(0, 50),
                type: el.getAttribute('type') || ''
            })).slice(0, 50);
        }
        """
        data = await self.page.evaluate(script)
        return json.dumps(data, ensure_ascii=False)

    async def ask_llm(self, goal: str, dom: str) -> Dict[str, Any]:
        payload = {
            "model": MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"OBJETIVO: {goal}\n\nESTADO ACTUAL DEL DOM:\n{dom}\n\nHISTORIAL: {self.history[-3:]}"}
            ],
            "format": "json",
            "stream": False
        }
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(OLLAMA_URL, json=payload)
                if r.status_code != 200: return {"action": "wait", "reason": "Ollama offline"}
                content = r.json().get("message", {}).get("content", "{}")
                return json.loads(content)
        except Exception as e:
            self._log(f"Error consultando cerebro: {e}")
            return {"action": "wait", "reason": "error_llm"}

    async def execute(self, goal: str, max_steps=15):
        self._log(f"🚀 Iniciando misión cognitiva: {goal}")
        
        for step in range(max_steps):
            await asyncio.sleep(2) # Estabilizar
            dom = await self.get_perception()
            
            # Captura de radiografía para depuración
            shot_path = f"C:\\AgentScreenshots\\sessions\\brain_{self.session_id}_step_{step}.png"
            await self.page.screenshot(path=shot_path)
            
            decision = await self.ask_llm(goal, dom)
            action = decision.get("action", "wait")
            target = decision.get("target", "")
            value = decision.get("value", "")
            reason = decision.get("reason", "")

            self._log(f"Paso {step+1}: {action} en '{target}' -> {reason}")
            self.history.append(decision)

            if action == "done":
                self._log("✅ Objetivo alcanzado según el cerebro.")
                return True
            
            if action == "error":
                self._log("❌ El cerebro reporta un bloqueo insuperable.")
                return False

            try:
                # 1. Intentar como selector CSS directo si parece uno
                if "[" in target or "#" in target or "." in target:
                    loc = self.page.locator(target).first
                    if await loc.is_visible(timeout=2000):
                        if action == "click": await loc.click()
                        elif action == "type":
                            await loc.click()
                            await loc.fill("")
                            await loc.type(value, delay=100)
                            await self.page.keyboard.press("Enter")
                        return True

                # 2. Búsqueda por texto (solo elementos visibles)
                if action == "click":
                    loc = self.page.get_by_text(target, exact=False).filter(has_not=self.page.locator("[aria-hidden='true']")).first
                    if await loc.is_visible(timeout=2000):
                        await loc.click()
                    else:
                        # Fallback por rol
                        await self.page.locator(f"button:has-text('{target}'), [role='button']:has-text('{target}'), a:has-text('{target}')").filter(has_not=self.page.locator("[aria-hidden='true']")).first.click()
                
                elif action == "type":
                    # Buscar inputs específicos de password/email si el target lo sugiere o es genérico
                    if "password" in target.lower() or "contraseña" in target.lower():
                        loc = self.page.locator("input[type='password'], input[name*='pass']").filter(has_not=self.page.locator("[aria-hidden='true']")).first
                    elif "email" in target.lower() or "correo" in target.lower():
                        loc = self.page.locator("input[type='email'], input[name*='email'], input[type='text']").filter(has_not=self.page.locator("[aria-hidden='true']")).first
                    else:
                        loc = self.page.locator(f"input[placeholder*='{target}'], input[aria-label*='{target}']").filter(has_not=self.page.locator("[aria-hidden='true']")).first
                    
                    await loc.click()
                    await loc.fill("")
                    await loc.type(value, delay=100)
                    await self.page.keyboard.press("Enter")
                
                elif action == "wait":
                    await asyncio.sleep(3)
            
            except Exception as e:
                self._log(f"⚠️ Error ejecutando acción: {e}")
                continue

        return False
