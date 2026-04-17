import os
import logging
import asyncio
import yt_dlp
import json
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import urllib.parse

# ================= НАСТРОЙКИ =================
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
APP_URL = os.environ.get("RENDER_EXTERNAL_URL")
PORT = int(os.environ.get("PORT", 10000))

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Глобальная переменная для приложения
app = None

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

# ================= HTTP СЕРВЕР С ПОДДЕРЖКОЙ PTB =================
class WebhookHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/telegram':
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'OK')
        else:
            self.send_response(404)
            self.end_headers()
    
    def do_POST(self):
        if self.path == '/telegram':
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'OK')
            
            # Передаём обновление в PTB асинхронно
            if app:
                try:
                    update_data = json.loads(body.decode('utf-8'))
                    asyncio.run_coroutine_threadsafe(
                        app.process_update(Update.de_json(update_data, app.bot)),
                        loop
                    )
                except Exception as e:
                    logger.error(f"Error processing update: {e}")
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        logger.info(f"{self.address_string()} - {format % args}")

def start_http_server():
    global loop
    server = HTTPServer(('0.0.0.0', PORT), WebhookHandler)
    logger.info(f"HTTP server running on port {PORT}")
    server.serve_forever()

# ================= ЗАПУСК =================
async def main():
    global app, loop
    loop = asyncio.get_running_loop()
    
    if not os.path.exists("downloads"):
        os.makedirs("downloads")
    
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    await app.initialize()
    await app.start()
    
    webhook_url = f"{APP_URL}/telegram"
    logger.info(f"Setting webhook: {webhook_url}")
    await app.bot.set_webhook(url=webhook_url)
    
    # Запускаем HTTP сервер в отдельном потоке
    threading.Thread(target=start_http_server, daemon=True).start()
    
    logger.info("Bot is ready!")
    await asyncio.Event().wait()

if __name__ == '__main__':
    asyncio.run(main())
