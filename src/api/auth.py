import os
import json
from pathlib import Path
from fastapi import HTTPException, Security, Depends
from fastapi.security.api_key import APIKeyHeader

API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

def load_security_config():
    cfg_path = Path(__file__).resolve().parent.parent.parent / "config" / "security.json"
    if cfg_path.exists():
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"require_auth": False, "default_api_key": "dm-secret-key-v1"}

async def verify_api_key(api_key: str = Depends(api_key_header)):
    cfg = load_security_config()
    if not cfg.get("require_auth", False):
        return True
    
    expected_key = os.getenv("DM_API_KEY", cfg.get("default_api_key", "dm-secret-key-v1"))
    if api_key == expected_key:
        return api_key
    raise HTTPException(status_code=403, detail="Invalid or missing API Key")
