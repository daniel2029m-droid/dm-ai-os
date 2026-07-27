# Grok Build Troubleshooting Guide
## DM AI Operating System v1.3.0-production

---

## 1. Connection Refused (`http://localhost:8000/v1`)

### Cause
The API Gateway server is not running.

### Solution
Launch the platform startup script:
```powershell
.\start_platform.ps1
```
Verify the server health manually:
```bash
curl http://localhost:8000/health
```
Expected output: `{"status":"ONLINE","version":"v1.2.0-production"}`

---

## 2. Models Not Appearing in Grok Build CLI

### Cause
`~/.grok/config.toml` was not merged or Grok Build CLI has not refreshed config.

### Solution
1. Run automatic configuration merge:
   ```bash
   python -m src.grok_validation
   ```
2. Check `~/.grok/config.toml` contains `[model.dm-autonomous-brain]`.
3. Restart Grok Build CLI.

---

## 3. Ollama Disconnected Warning

### Cause
Ollama daemon is not active on `http://localhost:11434`.

### Solution
Start Ollama in a separate terminal:
```bash
ollama serve
```

---

## 4. 401 Unauthorized Error

### Cause
Security mode in `config/openai_security.json` is set to `bearer` or `api_key` but Grok Build is not sending headers.

### Solution
Option A: Set `auth_mode: "none"` in `config/openai_security.json`.
Option B: Add `api_key = "dm-secret-key-v1"` to `~/.grok/config.toml`.
