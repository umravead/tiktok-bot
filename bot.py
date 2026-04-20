import os
import logging
import asyncio
import yt_dlp
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
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

# Хранилище для временных данных пользователей
user_data = {}

# ================= ФУНКЦИЯ СКАЧИВАНИЯ =================
def sync_download_video(url, download_type='video'):
    """Скачивает видео или аудио с TikTok, Instagram и Snapchat"""
    if not os.path.exists("downloads"):
        os.makedirs("downloads")
    
    is_tiktok = 'tiktok.com' in url
    is_instagram = 'instagram.com' in url
    is_snapchat = 'snapchat.com' in url
    
    # Используем только ID видео как имя файла (коротко и уникально)
    ydl_opts = {
        'outtmpl': 'downloads/%(id)s.%(ext)s',
        'quiet': True,
        'no_warnings': True,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
    }
    
    if download_type == 'audio':
        ydl_opts.update({
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        })
    else:
        if is_tiktok:
            ydl_opts.update({
                'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            })
        elif is_instagram:
            ydl_opts.update({
                'format': 'best[ext=mp4]/best',
            })
        elif is_snapchat:
            ydl_opts.update({
                'format': 'best',
            })
        else:
            ydl_opts.update({
                'format': 'best',
            })
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            logger.info(f"Downloading {download_type}: {url}")
            info = ydl.extract_info(url, download=True)
            
            if download_type == 'audio':
                filename = ydl.prepare_filename(info)
                filename = filename.rsplit('.', 1)[0] + '.mp3'
            else:
                filename = ydl.prepare_filename(info)
            
            if not os.path.exists(filename):
                video_id = info.get('id')
                for f in os.listdir('downloads'):
                    if video_id in f and f.endswith(('.mp4', '.mkv', '.webm', '.mp3')):
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
        "👋 *Привет! Я бот для скачивания видео и аудио!*\n\n"
        "📱 *Поддерживаемые платформы:*\n"
        "• TikTok (без водяного знака)\n"
        "• Instagram Reels\n"
        "• Snapchat\n\n"
        "🔗 *Просто отправь мне ссылку*, и я предложу выбрать:\n"
        "• 🎬 Скачать видео\n"
        "• 🎵 Скачать аудио (MP3)\n\n"
        "🆘 */help* — помощь и ограничения",
        parse_mode='Markdown'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🆘 *Помощь по использованию*\n\n"
        "1️⃣ Отправь ссылку на видео\n"
        "2️⃣ Выбери: видео или аудио\n"
        "3️⃣ Подожди 5-15 секунд\n"
        "4️⃣ Получи файл!\n\n"
        "⚠️ *Ограничения:*\n"
        "• Максимальный размер: 50 МБ\n"
        "• Аудио: MP3 192 kbps\n\n"
        "❓ *Не работает?* Попробуй другую ссылку.",
        parse_mode='Markdown'
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    chat_id = update.message.chat_id
    
    supported = ['tiktok.com', 'instagram.com', 'snapchat.com']
    if not any(s in url for s in supported):
        await update.message.reply_text(
            "❌ *Ссылка не поддерживается!*\n\n"
            "Поддерживаются: TikTok, Instagram, Snapchat.",
            parse_mode='Markdown'
        )
        return
    
    if 'tiktok.com' in url:
        site = 'TikTok'
    elif 'instagram.com' in url:
        site = 'Instagram'
    else:
        site = 'Snapchat'
    
    user_data[chat_id] = {'url': url, 'site': site}
    
    keyboard = [
        [
            InlineKeyboardButton("🎬 Скачать видео", callback_data='video'),
            InlineKeyboardButton("🎵 Скачать аудио", callback_data='audio'),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"🔗 *Ссылка получена!* ({site})\n\n"
        "Что будем скачивать?",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    chat_id = query.message.chat_id
    
    if chat_id not in user_data:
        await query.edit_message_text("❌ Сессия истекла. Отправь ссылку снова.")
        return
    
    data = user_data[chat_id]
    url = data['url']
    site = data['site']
    download_type = query.data
    
    type_text = "видео" if download_type == 'video' else "аудио"
    await query.edit_message_text(f"⏳ Скачиваю {type_text} с {site}...")
    
    try:
        file_path = await asyncio.to_thread(sync_download_video, url, download_type)
        
        if file_path and os.path.exists(file_path):
            file_size = os.path.getsize(file_path) / (1024 * 1024)
            
            if file_size > 50:
                await query.edit_message_text(f"❌ Файл {file_size:.1f} МБ > 50 МБ")
                os.remove(file_path)
                del user_data[chat_id]
                return
            
            await query.edit_message_text(f"📤 Отправляю {type_text}...")
            
            if download_type == 'video':
                with open(file_path, 'rb') as f:
                    await context.bot.send_video(
                        chat_id=chat_id,
                        video=f,
                        caption=f"✅ Готово! Видео с {site}",
                        supports_streaming=True
                    )
            else:
                with open(file_path, 'rb') as f:
                    await context.bot.send_audio(
                        chat_id=chat_id,
                        audio=f,
                        caption=f"✅ Готово! Аудио с {site}",
                        title=f"{site}_audio"
                    )
            
            await query.delete_message()
            os.remove(file_path)
            
        else:
            await query.edit_message_text("❌ Не удалось скачать. Возможно, видео удалено.")
            
    except Exception as e:
        err = str(e)
        logger.error(f"Error: {err}")
        
        if "login" in err.lower() or "cookie" in err.lower():
            msg = f"❌ {site} требует авторизацию. Попробуй другую ссылку."
        elif "not found" in err.lower():
            msg = "❌ Видео не найдено."
        elif "ffmpeg" in err.lower():
            msg = "❌ Ошибка конвертации аудио. Попробуй позже."
        else:
            msg = f"❌ Ошибка. Попробуй позже."
        
        await query.edit_message_text(msg)
    
    if chat_id in user_data:
        del user_data[chat_id]

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
    app.add_handler(CallbackQueryHandler(button_callback))
    
    await app.initialize()
    await app.start()
    
    webhook_url = f"{APP_URL}/telegram"
    await app.bot.set_webhook(url=webhook_url)
    
    threading.Thread(target=start_http_server, daemon=True).start()
    
    logger.info("Bot ready!")
    await asyncio.Event().wait()

if __name__ == '__main__':
    asyncio.run(main())
