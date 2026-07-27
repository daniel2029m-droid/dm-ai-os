"""
Phase 13.1 — Playwright E2E Verification (Against LIVE server at port 8000)
===========================================================================
Uses already-running server. Sends message via JS evaluate. Captures network audit + screenshots.
Fixed: encoding issues, proper wait, correct audit file written even on partial success.

NOTE: This is a standalone script, NOT a pytest test. Run directly:
  .venv/Scripts/python.exe tests/test_pwa_playwright_e2e.py
"""

import sys
import time
import json
from pathlib import Path

# Force UTF-8 output to prevent cp1252 encoding errors on Windows
if hasattr(sys.stdout, 'buffer'):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from playwright.sync_api import sync_playwright

BASE_URL = "http://127.0.0.1:8000"

def run_e2e_verification():
    deployment_dir = Path("deployment")
    deployment_dir.mkdir(exist_ok=True)

    print("[E2E] Starting Playwright verification against live server...")

    network_logs = []
    console_logs = []
    chat_req_captured = False
    chat_res_captured = False
    chat_status = None
    chat_content = ""

    with sync_playwright() as p:
        iphone_13 = p.devices['iPhone 13']
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(**iphone_13)
        page = context.new_page()

        # Capture ALL console messages
        def on_console(msg):
            console_logs.append({"type": msg.type, "text": msg.text})
        page.on("console", on_console)

        # Capture ALL requests
        def on_request(request):
            if "/v1/chat/completions" in request.url:
                nonlocal chat_req_captured
                chat_req_captured = True
                try:
                    body = request.post_data
                    network_logs.append({
                        "event": "REQUEST",
                        "url": request.url,
                        "method": request.method,
                        "headers": dict(request.headers),
                        "body": body
                    })
                    print("[E2E] -> POST /v1/chat/completions REQUEST captured")
                except Exception as e:
                    print(f"[E2E] Request capture error: {e}")

        # Capture ALL responses
        def on_response(response):
            if "/v1/chat/completions" in response.url:
                nonlocal chat_res_captured, chat_status
                chat_res_captured = True
                chat_status = response.status
                try:
                    network_logs.append({
                        "event": "RESPONSE",
                        "url": response.url,
                        "status": response.status,
                        "ok": response.ok,
                    })
                    print(f"[E2E] <- POST /v1/chat/completions RESPONSE: HTTP {response.status}")
                except Exception as e:
                    print(f"[E2E] Response capture error: {e}")

        page.on("request", on_request)
        page.on("response", on_response)

        # Step 1: Load PWA
        print(f"[E2E] Loading {BASE_URL}/connect ...")
        page.goto(f"{BASE_URL}/connect", wait_until="networkidle")
        time.sleep(2)

        # Screenshot 1: PWA loaded
        page.screenshot(path=str(deployment_dir / "evidence_pwa_loaded.png"))
        print("[E2E] Screenshot 1: PWA Loaded saved")

        # Step 2: Fill chatInput and call sendMessage() via JS
        print("[E2E] Filling chat input via JavaScript...")
        page.evaluate("""() => {
            const input = document.getElementById('chatInput');
            if (input) {
                input.value = 'Hola DM AI OS, prueba de integracion movil real desde iPhone';
                input.dispatchEvent(new Event('input', { bubbles: true }));
            }
        }""")
        time.sleep(0.5)

        print("[E2E] Calling sendMessage() via JavaScript...")
        page.evaluate("() => { if (typeof sendMessage === 'function') sendMessage(); }")

        # Step 3: Wait for network response (up to 60s) BEFORE checking DOM
        print("[E2E] Waiting for POST /v1/chat/completions response (up to 60s)...")
        try:
            with page.expect_response(
                lambda r: "/v1/chat/completions" in r.url,
                timeout=60000
            ) as response_info:
                pass
            resp = response_info.value
            chat_status = resp.status
            chat_res_captured = True
            print(f"[E2E] Response received! HTTP {chat_status}")
        except Exception as e:
            print(f"[E2E] Network response wait error: {e}")

        # Wait a bit more for DOM to render the response
        time.sleep(3)

        # Screenshot 2: Chat with response
        page.screenshot(path=str(deployment_dir / "evidence_mobile_chat_success.png"))
        print("[E2E] Screenshot 2: Chat result saved")

        # Get chat messages DOM content (ASCII-safe)
        chat_content = page.evaluate("""() => {
            const el = document.getElementById('chatMessages');
            if (!el) return 'NOT_FOUND';
            return el.innerText.replace(/[^\x00-\x7F]/g, '?');
        }""")
        print(f"[E2E] Chat DOM content (ASCII):\n{chat_content[:400]}")

        # Step 4: Status tab
        try:
            page.evaluate("""() => {
                const tabs = document.querySelectorAll('.tab-btn');
                tabs.forEach(t => { if (t.innerText.includes('Estado') || t.innerText.includes('Status')) t.click(); });
            }""")
            time.sleep(2)
        except Exception as e:
            print(f"[E2E] Status tab error: {e}")

        page.screenshot(path=str(deployment_dir / "evidence_mobile_status_dashboard.png"))
        print("[E2E] Screenshot 3: Status dashboard saved")

        browser.close()

    # Determine final result
    result = "PASS" if (chat_res_captured and chat_status == 200) else "FAIL"

    # Save complete audit
    audit = {
        "summary": {
            "chat_request_captured": chat_req_captured,
            "chat_response_captured": chat_res_captured,
            "chat_http_status": chat_status,
            "result": result,
        },
        "network_logs": network_logs,
        "console_logs": console_logs[:50]  # limit to 50 entries
    }

    audit_path = deployment_dir / "mobile_network_audit.json"
    with open(audit_path, "w", encoding="utf-8") as f:
        json.dump(audit, f, indent=2, ensure_ascii=False)

    print()
    print("===================================================")
    print(f"  RESULT: {result}")
    print(f"  POST /v1/chat/completions HTTP Status: {chat_status}")
    print(f"  Request captured: {chat_req_captured}")
    print(f"  Response captured: {chat_res_captured}")
    print(f"  Audit: {audit_path.absolute()}")
    print("===================================================")

    return audit

if __name__ == "__main__":
    run_e2e_verification()
