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
    """Скачивает видео с TikTok, Instagram, YouTube и других сайтов"""
    if not os.path.exists("downloads"):
        os.makedirs("downloads")
    
    # Определяем тип сайта
    is_instagram = 'instagram.com' in url
    is_tiktok = 'tiktok.com' in url
    
    # Базовые настройки
    ydl_opts = {
        'outtmpl': 'downloads/%(title)s_%(id)s.%(ext)s',
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'quiet': True,
        'no_warnings': True,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
    }
    
    # Для Instagram добавляем куки из браузера (если доступно)
    if is_instagram:
        try:
            # Пробуем импортировать куки из Chrome
            ydl_opts['cookiesfrombrowser'] = ('chrome',)
            logger.info("Using cookies from Chrome for Instagram")
        except:
            logger.warning("Could not load cookies from browser. Instagram may fail.")
    
    # Для TikTok тоже могут понадобиться куки при блокировке
    if is_tiktok:
        try:
            ydl_opts['cookiesfrombrowser'] = ('chrome',)
        except:
            pass
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            logger.info(f"Downloading from: {'Instagram' if is_instagram else 'TikTok' if is_tiktok else 'Other'}")
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
            # Ищем файл, если расширение отличается
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

# ================= ОБРАБОТЧИКИ КОМАНД =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    await update.message.reply_text(
        "👋 *Привет! Я бот для скачивания видео!*\n\n"
        "📱 *Поддерживаемые платформы:*\n"
        "• TikTok (без водяного знака)\n"
        "• Instagram Reels\n"
        "• YouTube (видео)\n"
        "• И многие другие!\n\n"
        "🔗 *Просто отправь мне ссылку*, и я пришлю тебе видео!\n\n"
        "📝 *Примеры ссылок:*\n"
        "• `https://www.tiktok.com/@user/video/123`\n"
        "• `https://www.instagram.com/reel/abc/`\n"
        "• `https://youtube.com/watch?v=xyz`",
        parse_mode='Markdown'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    await update.message.reply_text(
        "🆘 *Помощь по использованию бота*\n\n"
        "1️⃣ Отправь мне ссылку на видео\n"
        "2️⃣ Подожди 5-15 секунд\n"
        "3️⃣ Получи видео без водяных знаков!\n\n"
        "⚠️ *Важно:*\n"
        "• Instagram требует авторизации. Если не работает, попробуй позже.\n"
        "• Максимальный размер видео — 50 МБ (ограничение Telegram)\n"
        "• Бот может 'засыпать' после 15 минут бездействия. Первое сообщение может идти до 50 секунд.",
        parse_mode='Markdown'
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений (ссылок)"""
    url = update.message.text.strip()
    chat_id = update.message.chat_id
    user_name = update.message.from_user.first_name
    
    # Проверяем, что это ссылка на поддерживаемый сайт
    supported_sites = ['tiktok.com', 'instagram.com', 'youtube.com', 'youtu.be', 'vm.tiktok']
    if not any(site in url for site in supported_sites):
        await update.message.reply_text(
            "❌ *Ссылка не поддерживается!*\n\n"
            "Сейчас я умею скачивать с:\n"
            "• TikTok\n"
            "• Instagram Reels\n"
            "• YouTube\n\n"
            "Отправь ссылку на один из этих сайтов.",
            parse_mode='Markdown'
        )
        return
    
    # Определяем тип сайта для сообщения
    site_name = "Instagram" if "instagram" in url else "TikTok" if "tiktok" in url else "YouTube"
    
    status_msg = await update.message.reply_text(
        f"⏳ *Скачиваю видео с {site_name}...*\n"
        "Это может занять 5-15 секунд.",
        parse_mode='Markdown'
    )
    
    try:
        # Скачиваем видео
        video_path = await asyncio.to_thread(sync_download_video, url)
        
        if video_path and os.path.exists(video_path):
            # Проверяем размер файла (Telegram лимит 50 МБ)
            file_size = os.path.getsize(video_path) / (1024 * 1024)
            
            if file_size > 50:
                await status_msg.edit_text(
                    f"❌ *Видео слишком большое!*\n"
                    f"Размер: {file_size:.1f} МБ\n"
                    f"Лимит Telegram: 50 МБ\n\n"
                    f"Попробуй другое видео.",
                    parse_mode='Markdown'
                )
                os.remove(video_path)
                return
            
            await status_msg.edit_text("📤 *Отправляю видео...*", parse_mode='Markdown')
            
            # Отправляем видео
            with open(video_path, 'rb') as f:
                await context.bot.send_video(
                    chat_id=chat_id,
                    video=f,
                    caption=f"✅ *Готово! Видео с {site_name}*",
                    parse_mode='Markdown',
                    supports_streaming=True
                )
            
            await status_msg.delete()
            os.remove(video_path)
            logger.info(f"Video sent to {user_name} ({chat_id}) from {site_name}")
            
        else:
            await status_msg.edit_text(
                "❌ *Не удалось скачать видео.*\n\n"
                "Возможные причины:\n"
                "• Видео удалено или приватное\n"
                "• Ссылка недействительна\n"
                "• Требуется авторизация (особенно для Instagram)\n\n"
                "Попробуй другую ссылку.",
                parse_mode='Markdown'
            )
            
    except Exception as e:
        error_text = str(e)
        logger.error(f"Error for {user_name}: {error_text}")
        
        # Понятное сообщение для частых ошибок
        if "login" in error_text.lower() or "cookie" in error_text.lower():
            error_msg = (
                "❌ *Требуется авторизация!*\n\n"
                f"Для скачивания с {site_name} нужен вход в аккаунт.\n"
                "Попробуй другую ссылку или повтори позже."
            )
        elif "not found" in error_text.lower():
            error_msg = "❌ *Видео не найдено.*\nПроверь ссылку."
        else:
            error_msg = f"❌ *Ошибка при скачивании.*\n`{error_text[:100]}`"
        
        await status_msg.edit_text(error_msg, parse_mode='Markdown')

# ================= HTTP СЕРВЕР ДЛЯ RENDER =================
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
    server = HTTPServer(('0.0.0.0', PORT), WebhookHandler)
    logger.info(f"HTTP server running on port {PORT}")
    server.serve_forever()

# ================= ЗАПУСК БОТА =================
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
    logger.info(f"Setting webhook: {webhook_url}")
    await app.bot.set_webhook(url=webhook_url)
    
    threading.Thread(target=start_http_server, daemon=True).start()
    
    logger.info("Bot is ready!")
    await asyncio.Event().wait()

if __name__ == '__main__':
    asyncio.run(main())
