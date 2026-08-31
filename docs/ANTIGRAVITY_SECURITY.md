# 🛡️ DM AI OS v1.5.2 — Antigravity Security & Permissions Engine

## 1. Niveles de Permisos

| Nivel | Mutación Permitida | Comportamiento |
| :--- | :---: | :--- |
| **`READ_ONLY`** | ❌ NO | Bloquea estrictamente cualquier intento de escritura, eliminación o ejecución de comandos. Responde con `BLOCKED`. |
| **`APPROVAL_REQUIRED`** | ⚠️ BAJO CONTROL | Intercepta la acción, genera un `action_id` único y envía una tarjeta interactiva a la PWA móvil con botones `[APROBAR]` y `[RECHAZAR]`. |
| **`AUTONOMOUS`** | ✅ SÍ (AUTORIZADO) | Ejecuta herramientas dentro de la política de seguridad permitida sin confirmación manual previa. |

## 2. Auditoría y Protección de Secretos

* Ninguna clave de API, secreto de OAuth, token JWT ni cookie se guarda en la base de datos de auditoría (`data/antigravity_sessions.db`).
* Las entradas de auditoría registran hashes de entrada, marcas de tiempo, duraciones en milisegundos y verificaciones físicas en disco.
