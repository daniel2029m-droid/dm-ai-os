# LibreChat — Connection Setup Guide
## DM AI Operating System v1.2.0

---

## librechat.yaml Configuration

Add the DM AI OS as a custom endpoint in your `librechat.yaml`:

```yaml
version: 1.1.5

endpoints:
  custom:
    - name: "DM AI Operating System"
      apiKey: "dm-secret-key-v1"
      baseURL: "http://localhost:8000/v1"
      models:
        default:
          - "dm-autonomous-brain"
          - "dm-reasoner"
          - "dm-fast"
          - "dm-memory"
          - "dm-browser"
          - "dm-research"
          - "dm-media"
          - "dm-facebook"
        fetch: true
      titleConvo: true
      titleModel: "dm-fast"
      summarize: false
      summaryModel: "dm-fast"
      forcePrompt: false
      modelDisplayLabel: "DM AI OS"
      iconURL: ""
```

---

## Environment Variables (`.env`)

```env
# DM AI OS endpoint
DM_AI_API_KEY=dm-secret-key-v1
DM_AI_BASE_URL=http://localhost:8000/v1
```

---

## Restart LibreChat

```bash
docker compose down && docker compose up -d
```

---

## Verify

The DM AI OS endpoint will appear in LibreChat's model selector under "DM AI Operating System".

Streaming, tool calling, and memory context are all supported.
