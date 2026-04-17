import os
import logging
import asyncio
import yt_dlp
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ================= НАСТРОЙКИ =================
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
APP_URL = os.environ.get("RENDER_EXTERNAL_URL")
PORT = int(os.environ.get("PORT", 10000))

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ================= ФУНКЦИЯ СКАЧИВАНИЯ =================
def sync_download_video(url):
    if not os.path.exists("downloads"):
        os.makedirs("downloads")
    
    ydl_opts = {
        'outtmpl': 'downloads/%(title)s_%(id)s.%(ext)s',
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'quiet': True,
        'no_warnings': True,
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        
        if not os.path.exists(filename):
            video_id = info.get('id')
            for f in os.listdir('downloads'):
                if video_id in f and f.endswith(('.mp4', '.mkv', '.webm')):
                    filename = os.path.join('downloads', f)
                    break
        
        return filename

# ================= ОБРАБОТЧИКИ =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Отправь ссылку на TikTok — скачаю без водяного знака!\n\n"
        "Пример: https://www.tiktok.com/@username/video/1234567890"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    chat_id = update.message.chat_id
    
    if 'tiktok.com' not in url:
        await update.message.reply_text("❌ Это не ссылка на TikTok!")
        return
    
    status_msg = await update.message.reply_text("⏳ Скачиваю видео...")
    
    try:
        video_path = await asyncio.to_thread(sync_download_video, url)
        
        if video_path and os.path.exists(video_path):
            await status_msg.edit_text("📤 Отправляю...")
            
            with open(video_path, 'rb') as f:
                await context.bot.send_video(
                    chat_id=chat_id,
                    video=f,
                    caption="✅ Готово! Без водяного знака.",
                    supports_streaming=True
                )
            
            await status_msg.delete()
            os.remove(video_path)
        else:
            await status_msg.edit_text("❌ Не удалось скачать видео.")
            
    except Exception as e:
        logger.error(f"Error: {e}")
        await status_msg.edit_text("❌ Ошибка. Попробуйте позже.")

# ================= ЗАПУСК =================
def main():
    if not os.path.exists("downloads"):
        os.makedirs("downloads")
    
    if not TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set!")
        return
    
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    webhook_url = f"{APP_URL}/telegram"
    logger.info(f"Setting webhook: {webhook_url}")
    
    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path="telegram",
        webhook_url=webhook_url
    )

if __name__ == '__main__':
    main()
