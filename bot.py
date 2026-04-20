import os
import logging
import asyncio
import yt_dlp
import json
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

# ================= НАСТРОЙКИ =================
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
APP_URL = os.environ.get("RENDER_EXTERNAL_URL")
PORT = int(os.environ.get("PORT", 10000))

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

app = None
loop = None

# ================= ФУНКЦИЯ СКАЧИВАНИЯ =================
def sync_download_video(url):
    """Скачивает видео с YouTube, TikTok, Instagram и Snapchat"""
    if not os.path.exists("downloads"):
        os.makedirs("downloads")
    
    # Определяем тип сайта
    is_youtube = 'youtube.com' in url or 'youtu.be' in url
    is_tiktok = 'tiktok.com' in url
    is_instagram = 'instagram.com' in url
    is_snapchat = 'snapchat.com' in url
    
    # Настройки в зависимости от сайта
    if is_youtube:
        ydl_opts = {
            'outtmpl': 'downloads/%(title)s_%(id)s.%(ext)s',
            'format': 'best[height<=720][ext=mp4]/best[height<=720]/best',
            'quiet': True,
            'no_warnings': True,
        }
    elif is_tiktok:
        ydl_opts = {
            'outtmpl': 'downloads/%(title)s_%(id)s.%(ext)s',
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'quiet': True,
            'no_warnings': True,
        }
    elif is_instagram:
        ydl_opts = {
            'outtmpl': 'downloads/%(title)s_%(id)s.%(ext)s',
            'format': 'best[ext=mp4]/best',
            'quiet': True,
            'no_warnings': True,
        }
    elif is_snapchat:
        ydl_opts = {
            'outtmpl': 'downloads/%(title)s_%(id)s.%(ext)s',
            'format': 'best',
            'quiet': True,
            'no_warnings': True,
        }
    else:
        ydl_opts = {
            'outtmpl': 'downloads/%(title)s_%(id)s.%(ext)s',
            'format': 'best',
            'quiet': True,
            'no_warnings': True,
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
        "👋 *Привет! Я бот для скачивания видео!*\n\n"
        "📱 *Поддерживаемые платформы:*\n"
        "• YouTube\n"
        "• TikTok (без водяного знака)\n"
        "• Instagram Reels\n"
        "• Snapchat\n\n"
        "🔗 *Отправь мне ссылку*, и я пришлю видео!\n\n"
        "📝 *Примеры:*\n"
        "• `https://youtube.com/watch?v=...`\n"
        "• `https://www.tiktok.com/@user/video/...`\n"
        "• `https://www.instagram.com/reel/...`\n"
        "• `https://www.snapchat.com/...`",
        parse_mode='Markdown'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🆘 *Помощь*\n\n"
        "1️⃣ Отправь ссылку на видео\n"
        "2️⃣ Подожди 5-15 секунд\n"
        "3️⃣ Получи видео!\n\n"
        "⚠️ *Ограничения:*\n"
        "• Максимальный размер: 50 МБ\n"
        "• YouTube: до 720p\n"
        "• Instagram может требовать авторизацию\n\n"
        "❓ *Не работает?* Попробуй другую ссылку.",
        parse_mode='Markdown'
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    chat_id = update.message.chat_id
    
    supported = ['tiktok.com', 'instagram.com', 'youtube.com', 'youtu.be', 'snapchat.com']
    if not any(s in url for s in supported):
        await update.message.reply_text(
            "❌ *Ссылка не поддерживается!*\n\n"
            "Поддерживаются: YouTube, TikTok, Instagram, Snapchat.",
            parse_mode='Markdown'
        )
        return
    
    if 'tiktok.com' in url:
        site = 'TikTok'
    elif 'instagram.com' in url:
        site = 'Instagram'
    elif 'snapchat.com' in url:
        site = 'Snapchat'
    else:
        site = 'YouTube'
    
    status_msg = await update.message.reply_text(f"⏳ Скачиваю с {site}...")
    
    try:
        video_path = await asyncio.to_thread(sync_download_video, url)
        
        if video_path and os.path.exists(video_path):
            file_size = os.path.getsize(video_path) / (1024 * 1024)
            
            if file_size > 50:
                await status_msg.edit_text(f"❌ Файл {file_size:.1f} МБ > 50 МБ")
                os.remove(video_path)
                return
            
            await status_msg.edit_text("📤 Отправляю...")
            
            with open(video_path, 'rb') as f:
                await context.bot.send_video(
                    chat_id=chat_id,
                    video=f,
                    caption=f"✅ Готово! {site}",
                    supports_streaming=True
                )
            
            await status_msg.delete()
            os.remove(video_path)
        else:
            await status_msg.edit_text("❌ Не удалось скачать. Возможно, видео удалено.")
            
    except Exception as e:
        err = str(e)
        logger.error(f"Error: {err}")
        
        if "login" in err.lower() or "cookie" in err.lower():
            msg = f"❌ {site} требует авторизацию. Попробуй другую ссылку."
        elif "not found" in err.lower():
            msg = "❌ Видео не найдено."
        else:
            msg = f"❌ Ошибка. Попробуй позже."
        
        await status_msg.edit_text(msg)

# ================= HTTP СЕРВЕР =================
class WebhookHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200 if self.path == '/telegram' else 404)
        self.end_headers()
        if self.path == '/telegram':
            self.wfile.write(b'OK')
    
    def do_POST(self):
        if self.path == '/telegram':
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'OK')
            
            if app:
                try:
                    update_data = json.loads(body.decode('utf-8'))
                    asyncio.run_coroutine_threadsafe(
                        app.process_update(Update.de_json(update_data, app.bot)),
                        loop
                    )
                except Exception as e:
                    logger.error(f"Update error: {e}")
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        logger.info(f"{self.address_string()} - {format % args}")

def start_http_server():
    server = HTTPServer(('0.0.0.0', PORT), WebhookHandler)
    logger.info(f"HTTP server on port {PORT}")
    server.serve_forever()

# ================= ЗАПУСК =================
async def main():
    global app, loop
    loop = asyncio.get_running_loop()
    
    if not os.path.exists("downloads"):
        os.makedirs("downloads")
    
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    await app.initialize()
    await app.start()
    
    webhook_url = f"{APP_URL}/telegram"
    await app.bot.set_webhook(url=webhook_url)
    
    threading.Thread(target=start_http_server, daemon=True).start()
    
    logger.info("Bot ready!")
    await asyncio.Event().wait()

if __name__ == '__main__':
    asyncio.run(main())
