# Open WebUI — Connection Setup Guide
## DM AI Operating System v1.2.0

---

## Method 1: Environment Variable (Docker)

```bash
docker run -d \
  -p 3000:8080 \
  -e OPENAI_API_BASE_URL=http://host.docker.internal:8000/v1 \
  -e OPENAI_API_KEY=dm-secret-key-v1 \
  --name open-webui \
  ghcr.io/open-webui/open-webui:main
```

For Linux (host networking):
```bash
docker run -d \
  -p 3000:8080 \
  --network host \
  -e OPENAI_API_BASE_URL=http://localhost:8000/v1 \
  -e OPENAI_API_KEY=dm-secret-key-v1 \
  --name open-webui \
  ghcr.io/open-webui/open-webui:main
```

---

## Method 2: Open WebUI Admin Settings

1. Open `http://localhost:3000`
2. Go to **Settings → Admin → Connections**
3. Under **OpenAI API**:
   - **Base URL**: `http://localhost:8000/v1`
   - **API Key**: `dm-secret-key-v1`
4. Click **Verify Connection**
5. Go to **Settings → Admin → Models**
6. Available models will list `dm-autonomous-brain`, `dm-reasoner`, etc.

---

## Streaming

Open WebUI uses SSE streaming by default. The DM platform is fully compatible.

---

## Models in Open WebUI

After connecting, Open WebUI will show all DM models and Ollama models in the model selector:

- `dm-autonomous-brain`
- `dm-reasoner`
- `dm-fast`
- `dm-memory`
- `dm-browser`
- `dm-research`
- `dm-media`
- `dm-facebook`

---

## Verify

```bash
curl http://localhost:8000/v1/models \
  -H "Authorization: Bearer dm-secret-key-v1"
```
