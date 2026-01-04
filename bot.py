import os
import json
import requests
from pathlib import Path
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters
)

# =========================
# ENVIRONMENT VARIABLES
# =========================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
COMPANY_NAME = os.environ.get("COMPANY_NAME", "SVL1-ltd")
USERNAME = os.environ.get("USERNAME", "VEND")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))

CLEAR_TAMPER_URL = "https://server-newa.stronpower.com/api/ClearTamperDirectly"
SEND_TOKEN_URL = "https://server-newa.stronpower.com/api/VendingMeterSendToken"

WHITELIST_FILE = Path("whitelist.json")

# Conversation states
PASSWORD, METER_ID, CONFIRM = range(3)

# =========================
# WHITELIST HELPERS
# =========================
def load_whitelist():
    if not WHITELIST_FILE.exists():
        WHITELIST_FILE.write_text(json.dumps({"users": []}))
    return json.loads(WHITELIST_FILE.read_text())

def save_whitelist(data):
    WHITELIST_FILE.write_text(json.dumps(data, indent=2))

def is_allowed(user_id: int):
    data = load_whitelist()
    return user_id == ADMIN_ID or user_id in data["users"]

def add_user(user_id: int):
    data = load_whitelist()
    if user_id not in data["users"]:
        data["users"].append(user_id)
        save_whitelist(data)

def remove_user(user_id: int):
    data = load_whitelist()
    if user_id in data["users"]:
        data["users"].remove(user_id)
        save_whitelist(data)

# =========================
# COMMANDS
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        await update.message.reply_text("❌ You are not authorised to use this bot.")
        return ConversationHandler.END

    await update.message.reply_text("Enter password:")
    return PASSWORD

async def getid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Your Telegram ID is:\n{update.effective_user.id}"
    )

async def invite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Admin only.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /invite <telegram_id>")
        return

    user_id = int(context.args[0])
    add_user(user_id)
    await update.message.reply_text(f"✅ User {user_id} invited.")

async def revoke(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Admin only.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /revoke <telegram_id>")
        return

    user_id = int(context.args[0])
    remove_user(user_id)
    await update.message.reply_text(f"🚫 User {user_id} removed.")

# =========================
# CONVERSATION STEPS
# =========================
async def get_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["password"] = update.message.text.strip()
    await update.message.reply_text("Enter meter number:")
    return METER_ID

async def get_meter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    password = context.user_data["password"]
    meter_id = update.message.text.strip()

    payload = {
        "CompanyName": COMPANY_NAME,
        "UserName": USERNAME,
        "PassWord": password,
        "METER_ID": meter_id
    }

    try:
        r = requests.post(CLEAR_TAMPER_URL, json=payload, timeout=15)
        r.raise_for_status()
        token = str(r.json()).strip()

        if not token.isdigit() or len(token) != 20:
            await update.message.reply_text("❌ Invalid token received.")
            return ConversationHandler.END

        context.user_data["meter_id"] = meter_id
        context.user_data["token"] = token

        await update.message.reply_text(
            f"Token generated:\n\n{token}\n\n"
            "Reply YES to send token or NO to cancel."
        )
        return CONFIRM

    except Exception as e:
        await update.message.reply_text(f"Error: {e}")
        return ConversationHandler.END

async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.lower() != "yes":
        await update.message.reply_text("Cancelled.")
        return ConversationHandler.END

    payload = {
        "CompanyName": COMPANY_NAME,
        "UserName": USERNAME,
        "PassWord": context.user_data["password"],
        "MeterID": context.user_data["meter_id"],
        "Token": context.user_data["token"]
    }

    try:
        r = requests.post(SEND_TOKEN_URL, json=payload, timeout=15)
        r.raise_for_status()
        await update.message.reply_text("✅ Token sent successfully.")
    except Exception as e:
        await update.message.reply_text(f"❌ Failed: {e}")

    return ConversationHandler.END

# =========================
# MAIN
# =========================
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_password)],
            METER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_meter)],
            CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm)],
        },
        fallbacks=[]
    )

    app.add_handler(CommandHandler("getid", getid))
    app.add_handler(CommandHandler("invite", invite))
    app.add_handler(CommandHandler("revoke", revoke))
    app.add_handler(conv)

    app.run_polling()

if __name__ == "__main__":
    main()
