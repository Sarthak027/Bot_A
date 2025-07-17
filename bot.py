import os
import json
import base64
import time
import asyncio
import requests
from telegram import Update, PhotoSize, Video
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from config import BOT_TOKEN, ADMIN_ID, BOT_USERNAME, SHORTNER_API_KEY

# Ensure files directory exists
os.makedirs("files", exist_ok=True)

# Database files
TOKEN_DB = "tokens.json"
PREMIUM_DB = "premium.json"

# Load/Save Helpers
def load_json(file):
    try:
        if os.path.exists(file):
            with open(file, "r") as f:
                return json.load(f)
    except:
        return {}
    return {}

def save_json(file, data):
    with open(file, "w") as f:
        json.dump(data, f, indent=2)

TOKENS = load_json(TOKEN_DB)
PREMIUM_USERS = load_json(PREMIUM_DB)

# Token Utils
def generate_token():
    return "Z" + str(int(time.time()))

def encode_token(token):
    return base64.urlsafe_b64encode(f"get-{token}".encode()).decode()

def decode_token(encoded):
    try:
        decoded = base64.urlsafe_b64decode(encoded).decode()
        if decoded.startswith("get-"):
            return decoded[4:]
    except:
        return None
    return None

# Shortener
def short_url(long_url):
    try:
        res = requests.get("https://shortner.in/api", params={
            "api": SHORTNER_API_KEY,
            "url": long_url
        }).json()
        return res.get("shortenedUrl", long_url)
    except:
        return long_url

# START Command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    args = context.args

    if user_id in PREMIUM_USERS:
        await update.message.reply_text("✅ Premium access granted.")
        return

    if not args:
        await update.message.reply_text("❌ Invalid or missing token.")
        return

    token = decode_token(args[0])
    if not token or token not in TOKENS:
        await update.message.reply_text("❌ Invalid token.")
        return

    token_data = TOKENS[token]
    created = token_data["created"]

    if time.time() - created > 21600:  # 6 hours
        await update.message.reply_text("❌ Token expired.")
        return

    await update.message.reply_text("🔓 Verified! Sending your files...")

    for file_path in token_data["files"]:
        try:
            with open(file_path, "rb") as f:
                ext = os.path.splitext(file_path)[1]
                if ext in [".jpg", ".jpeg", ".png"]:
                    msg = await context.bot.send_photo(chat_id=update.effective_chat.id, photo=f)
                elif ext in [".mp4", ".mov", ".avi"]:
                    msg = await context.bot.send_video(chat_id=update.effective_chat.id, video=f)
                else:
                    continue

            # Schedule deletion after 15 minutes
            async def delete_later(chat_id, message_id):
                await asyncio.sleep(900)
                try:
                    await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
                except:
                    pass

            asyncio.create_task(delete_later(update.effective_chat.id, msg.message_id))
        except Exception as e:
            await update.message.reply_text(f"⚠️ Failed to send file: {file_path}")

# UPLOAD Handler (Admin Only)
async def upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    chat_data = context.chat_data
    token = chat_data.get("token")

    if not token:
        token = generate_token()
        chat_data["token"] = token
        TOKENS[token] = {"created": time.time(), "files": []}

    file_path = None
    file_name = None

    if update.message.photo:
        photo: PhotoSize = update.message.photo[-1]
        file = await photo.get_file()
        file_name = f"{photo.file_unique_id}.jpg"
    elif update.message.video:
        video: Video = update.message.video
        file = await video.get_file()
        file_name = f"{video.file_unique_id}.mp4"
    else:
        await update.message.reply_text("❌ Only photos and videos are accepted.")
        return

    file_path = f"files/{file_name}"
    await file.download_to_drive(file_path)

    TOKENS[token]["files"].append(file_path)
    save_json(TOKEN_DB, TOKENS)

    await update.message.reply_text(f"✅ File saved under token: `{token}`", parse_mode="Markdown")

# FINISH Handler - Generates Shortlink
async def finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    token = context.chat_data.get("token")
    if not token:
        await update.message.reply_text("❌ No token in progress.")
        return

    encoded = encode_token(token)
    link = f"https://t.me/{BOT_USERNAME}?start={encoded}"
    shortlink = short_url(link)

    await update.message.reply_text(f"🔗 Protected Link:\n{shortlink}")
    context.chat_data["token"] = None

# BUY Premium
async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💳 Send ₹99 to @Lordslayer5 and reply with your screenshot. You’ll be manually upgraded.")

# ADD Premium
async def add_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("Usage: /addpremium <user_id>")
        return
    user_id = context.args[0]
    PREMIUM_USERS[user_id] = True
    save_json(PREMIUM_DB, PREMIUM_USERS)
    await update.message.reply_text(f"✅ Added {user_id} as premium.")

# Main Bot Setup
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("upload", upload))
    app.add_handler(CommandHandler("finish", finish))
    app.add_handler(CommandHandler("buy", buy))
    app.add_handler(CommandHandler("addpremium", add_premium))

    # Accept only photo or video
    app.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO, upload))

    app.run_polling()

if __name__ == "__main__":
    main()
