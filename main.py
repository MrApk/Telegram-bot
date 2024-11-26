import logging
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.error import RetryAfter
import os
import time
import uuid

RAPIDAPI_HOST = "terabox-downloader-direct-download-link-generator.p.rapidapi.com"
RAPIDAPI_KEY = os.environ.get('rkey')

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


video_cache = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /start command."""
    await update.message.reply_text(
        "Welcome! Send me a TeraBox link, and I'll fetch the video for you to play or download!"
    )

async def fetch_video_link(terabox_url: str) -> tuple[str, int]:
    """Fetch the direct download link and file size for a TeraBox URL."""
    url = f"https://{RAPIDAPI_HOST}/fetch"
    headers = {
        "X-RapidAPI-Host": RAPIDAPI_HOST,
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "Content-Type": "application/json"
    }
    payload = {"url": terabox_url}
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        logger.info(f"API response: {response.status_code}, {response.text}")
        
        if response.status_code == 200:
            data = response.json()
            dlink = data[0].get("dlink", None)  # Extract the direct download link
            size = int(data[0].get("size", 0))  # Extract the file size (in bytes)
            if dlink:
                return dlink, size
            else:
                return None, 0
        else:
            logger.error(f"API Error: {response.status_code}, {response.text}")
            return None, 0
    except Exception as e:
        logger.error(f"Error fetching video link: {e}")
        return None, 0

async def download_video(dlink: str, total_size: int, progress_message, chat_id, bot) -> str:
    """Download video and update progress."""
    if dlink in video_cache:
        logger.info("Using cached video")
        return video_cache[dlink]

    video_path = f"{uuid.uuid4()}.mp4"

    try:
        response = requests.get(dlink, stream=True)
        response.raise_for_status()

        downloaded_size = 0
        chunk_size = 65536  # 64 KB
        last_update_time = time.time()

        with open(video_path, "wb") as video_file:
            for chunk in response.iter_content(chunk_size=chunk_size):
                video_file.write(chunk)
                downloaded_size += len(chunk)

                # Update progress every 10 seconds
                if time.time() - last_update_time > 10:
                    progress = (downloaded_size / total_size) * 100
                    try:
                        await bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=progress_message.message_id,
                            text=f"Downloading... {progress:.2f}%",
                        )
                    except RetryAfter as e:
                        logger.warning(f"Flood control exceeded: Retry in {e.retry_after} seconds")
                        time.sleep(e.retry_after)
                    except Exception as e:
                        logger.warning(f"Error updating progress: {e}")
                    last_update_time = time.time()

        video_cache[dlink] = video_path
        return video_path
    except Exception as e:
        logger.error(f"Error downloading video: {e}")
        if os.path.exists(video_path):
            os.remove(video_path)
        raise

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle user messages."""
    user_message = update.message.text.strip()

    if user_message.startswith("http"):
        progress_message = await update.message.reply_text("Fetching video link...")

        try:
            dlink, total_size = await fetch_video_link(user_message)
            if dlink:
                video_path = await download_video(
                    dlink, total_size, progress_message, update.message.chat_id, context.bot
                )

                # Send video
                with open(video_path, "rb") as video_file:
                    await update.message.reply_video(video=video_file, caption="Here is your video!")
                os.remove(video_path)  # Clean up after sending
            else:
                await update.message.reply_text("Failed to fetch the video link.")
        except Exception as e:
            logger.error(f"Error handling download: {e}")
            await update.message.reply_text("An error occurred while downloading the video.")
    else:
        await update.message.reply_text("Please send a valid TeraBox link.")

def main():
# Replace these with your credentials
    TELEGRAM_BOT_TOKEN = os.environ.get('botkey')
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", lambda update, context: update.message.reply_text("Send a TeraBox link.")))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot is running...")
    application.run_polling()

if __name__ == "__main__":
    main()
