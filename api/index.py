import sys
import os
import shutil
import traceback
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

# Handle Vercel read-only filesystem by copying DBs to /tmp
if os.getenv("VERCEL"):
    tmp_state = Path("/tmp/Project_State")
    tmp_state.mkdir(parents=True, exist_ok=True)
    (tmp_state / "Storage").mkdir(parents=True, exist_ok=True)

    src_state = ROOT_DIR / "Project_State"
    if src_state.exists():
        for db_file in src_state.glob("*.db"):
            try:
                shutil.copy2(db_file, tmp_state / db_file.name)
            except Exception:
                pass
        storage_src = src_state / "Storage"
        if storage_src.exists():
            for db_file in storage_src.glob("*.db"):
                try:
                    shutil.copy2(db_file, tmp_state / "Storage" / db_file.name)
                except Exception:
                    pass

from src.api.server import app as fastapi_app

# Safe ASGI wrapper to prevent Vercel FUNCTION_INVOCATION_FAILED crashes
async def app(scope, receive, send):
    if scope.get("type") == "http":
        try:
            await fastapi_app(scope, receive, send)
        except Exception as exc:
            err_text = traceback.format_exc()
            body = (
                f"<!DOCTYPE html><html><head><title>DM AI OS Error</title></head>"
                f"<body style='background:#0a0e17;color:#f8fafc;font-family:sans-serif;padding:30px;'>"
                f"<h2 style='color:#f87171;'>DM AI OS — Vercel Runtime Error</h2>"
                f"<pre style='background:#1e293b;color:#f1f5f9;padding:20px;border-radius:12px;overflow-x:auto;'>{err_text}</pre>"
                f"</body></html>"
            ).encode("utf-8")
            await send({
                "type": "http.response.start",
                "status": 200,
                "headers": [
                    (b"content-type", b"text/html; charset=utf-8"),
                    (b"content-length", str(len(body)).encode("utf-8")),
                ],
            })
            await send({
                "type": "http.response.body",
                "body": body,
            })
    else:
        await fastapi_app(scope, receive, send)
