import asyncio
import re
import json
import os
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler
)
from config import TOKEN, ACCOUNTS_FILE
from automation import automation_manager

# TOKEN DIRECTO SEGUN SOLICITUD
TOKEN = "8698043786:AAG9AIsccgFOtAd8bgX8wfrrkcN2U6dTId0"

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── ESTADOS ────────────────────────────────────────────────────────────────────
STATE_IDLE            = "idle"
STATE_AWAIT_EMAIL     = "await_email"
STATE_AWAIT_PASSWORD  = "await_password"
STATE_LOGGING_IN      = "logging_in"
STATE_AWAIT_TASK      = "await_task"
STATE_PRODUCING       = "producing"

def validar_email(email: str) -> bool:
    return bool(re.match(r'^[\w\.\+\-]+@[\w\.\-]+\.\w{2,}$', email))

# ── COMANDOS ───────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reinicia todo y pide el email."""
    context.user_data.clear()
    if os.path.exists(ACCOUNTS_FILE):
        try: os.remove(ACCOUNTS_FILE)
        except: pass
    context.user_data["state"] = STATE_AWAIT_EMAIL
    await update.message.reply_text(
        "👋 ¡Hola! Configuremos tu cuenta de ComfyUI Cloud.\n\n"
        "📧 Dame tu correo de Gmail:"
    )

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = context.user_data.get("state", STATE_IDLE)
    email = context.user_data.get("email", "—")
    creds = "✅ Guardadas" if os.path.exists(ACCOUNTS_FILE) else "❌ No configuradas"
    labels = {
        STATE_IDLE:           "💤 En espera",
        STATE_AWAIT_EMAIL:    "📧 Esperando email",
        STATE_AWAIT_PASSWORD: "🔑 Esperando contraseña",
        STATE_LOGGING_IN:     "🤖 Login en progreso...",
    }
    await update.message.reply_text(
        f"📊 *Estado actual*\n\n"
        f"Estado: {labels.get(state, state)}\n"
        f"Email: `{email}`\n"
        f"Credenciales: {creds}",
        parse_mode="Markdown",
    )

async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await automation_manager.close()
    context.user_data["state"] = STATE_IDLE
    await update.message.reply_text("🛑 Navegador cerrado.")

# ── MANEJADOR DE MENSAJES ──────────────────────────────────────────────────────

async def manejar_mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = context.user_data.get("state", STATE_IDLE)
    text  = update.message.text.strip() if update.message.text else ""

    if state == STATE_AWAIT_EMAIL:
        if not validar_email(text):
            await update.message.reply_text("❌ Email inválido. Ingresa uno correcto:")
            return
        context.user_data["email"] = text
        context.user_data["state"] = STATE_AWAIT_PASSWORD
        await update.message.reply_text(f"✅ Email *{text}* OK.\n\n🔑 Dame tu contraseña:", parse_mode="Markdown")
        return

    if state == STATE_AWAIT_PASSWORD:
        email = context.user_data["email"]
        password = text
        with open(ACCOUNTS_FILE, "w") as f:
            json.dump({"email": email, "password": password}, f)

        context.user_data["state"] = STATE_LOGGING_IN
        await update.message.reply_text("✅ Contraseña OK.\n\n🚀 Iniciando login automático... Te reporto cada paso 👇")

        async def run_automation():
            async def status_report(msg: str):
                try: await update.message.reply_text(f"🤖 {msg}")
                except: pass

            try:
                ok = await automation_manager.run_full_login(email, password, status_report)
                if ok:
                    context.user_data["state"] = STATE_IDLE
                    reply_markup = InlineKeyboardMarkup([
                        [InlineKeyboardButton("🎬 Grok (Img2Vid)", callback_data="task:grok")],
                        [InlineKeyboardButton("🎞️ Kling (Vid2Vid)", callback_data="task:kling")],
                        [InlineKeyboardButton("🍌 NanoBanana", callback_data="task:nanobanana")]
                    ])
                    await update.message.reply_text("🎉 ¡Login completado! Ya estás dentro.\n¿Qué deseas producir?", reply_markup=reply_markup)
                else:
                    context.user_data["state"] = STATE_IDLE
                    await update.message.reply_text("❌ Falló el login automático. Usa /start para reintentar.")
            except Exception as e:
                context.user_data["state"] = STATE_IDLE
                await update.message.reply_text(f"💥 Error: {e}")

        asyncio.create_task(run_automation())
        return

    if state == STATE_LOGGING_IN:
        await update.message.reply_text("⏳ Espera... el login está en curso.")
        return

async def manejar_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data.startswith("task:"):
        task = query.data.split(":")[1]
        context.user_data["task"] = task
        await query.edit_message_text(f"🚀 Has seleccionado: {task.upper()}\nEnvía el prompt o imagen necesaria para comenzar.")

# ── ARRANQUE ───────────────────────────────────────────────────────────────────

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("stop",   cmd_stop))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manejar_mensaje))
    app.add_handler(CallbackQueryHandler(manejar_callback))
    logger.info("Bot iniciado.")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
