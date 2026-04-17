import os
import logging
import asyncio
import yt_dlp
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ================= НАСТРОЙКИ =================
# Для Render: токен будет в переменных окружения
# Для локального запуска: создайте переменную TELEGRAM_BOT_TOKEN или впишите токен прямо сюда
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "ВАШ_ТОКЕН_ЕСЛИ_ЛОКАЛЬНО")

# Render автоматически подставляет URL приложения
APP_URL = os.environ.get("RENDER_EXTERNAL_URL")
PORT = int(os.environ.get("PORT", 8000))

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ================= ФУНКЦИЯ СКАЧИВАНИЯ =================
def sync_download_video(url):
    """Скачивает видео с TikTok без водяного знака"""
    if not os.path.exists("downloads"):
        os.makedirs("downloads")
    
    ydl_opts = {
        'outtmpl': 'downloads/%(title)s_%(id)s.%(ext)s',
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            logger.info(f"Downloading: {url}")
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
            if not os.path.exists(filename):
                video_id = info.get('id')
                for f in os.listdir('downloads'):
                    if video_id in f and f.endswith(('.mp4', '.mkv', '.webm')):
                        filename = os.path.join('downloads', f)
                        break
            
            logger.info(f"Downloaded: {filename}")
            return filename
            
    except Exception as e:
        logger.error(f"Download error: {e}")
        raise e

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
        await status_msg.edit_text(f"❌ Ошибка. Попробуйте позже.")

# ================= ЗАПУСК =================
def main():
    if not os.path.exists("downloads"):
        os.makedirs("downloads")
    
    if TOKEN == "ВАШ_ТОКЕН_ЕСЛИ_ЛОКАЛЬНО":
        print("❌ Впишите токен в код или создайте переменную TELEGRAM_BOT_TOKEN")
        return
    
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Если есть APP_URL — значит мы на Render, используем webhook
    if APP_URL:
        webhook_url = f"{APP_URL}/telegram"
        logger.info(f"Running on Render. Webhook: {webhook_url}")
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path="telegram",
            webhook_url=webhook_url
        )
    else:
        # Локальный запуск — используем polling
        logger.info("Running locally. Using polling.")
        app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()