import os
import logging
import asyncio
import yt_dlp
import json
import requests
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
user_data = {}

# ================= РАЗВОРАЧИВАНИЕ КОРОТКИХ ССЫЛОК =================
def expand_url(short_url):
    """Разворачивает короткую ссылку в полную"""
    try:
        response = requests.head(short_url, allow_redirects=True, timeout=10)
        final_url = response.url
        logger.info(f"Expanded: {short_url} -> {final_url}")
        return final_url
    except Exception as e:
        logger.error(f"Error expanding URL: {e}")
        return short_url  # Возвращаем как есть, если не получилось

# ================= ФУНКЦИЯ СКАЧИВАНИЯ ФОТО ИЗ TIKTOK =================
def download_tiktok_photos(url):
    if not os.path.exists("downloads"):
        os.makedirs("downloads")
    
    clean_url = url.split('?')[0]
    logger.info(f"Downloading photos from: {clean_url}")
    
    api_url = "https://www.tikwm.com/api/"
    params = {"url": clean_url}
    
    try:
        response = requests.get(api_url, params=params, timeout=30)
        data = response.json()
        
        if data.get("code") != 0:
            raise Exception(f"API Error: {data.get('msg', 'Unknown error')}")
        
        images = data.get("data", {}).get("images", [])
        if not images:
            raise Exception("No images found")
        
        downloaded_files = []
        for i, img_url in enumerate(images):
            img_response = requests.get(img_url, timeout=30)
            filename = os.path.join("downloads", f"tiktok_photo_{i+1}.jpg")
            with open(filename, "wb") as f:
                f.write(img_response.content)
            downloaded_files.append(filename)
            logger.info(f"Downloaded photo: {filename}")
        
        return downloaded_files
        
    except Exception as e:
        logger.error(f"Photo download error: {e}")
        raise e

# ================= ФУНКЦИЯ СКАЧИВАНИЯ ВИДЕО/АУДИО =================
def sync_download_video(url, download_type='video'):
    if not os.path.exists("downloads"):
        os.makedirs("downloads")
    
    clean_url = url.split('?')[0]
    
    is_tiktok = 'tiktok.com' in clean_url
    is_instagram = 'instagram.com' in clean_url
    is_snapchat = 'snapchat.com' in clean_url
    
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
            ydl_opts.update({'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'})
        elif is_instagram:
            ydl_opts.update({'format': 'best[ext=mp4]/best'})
        elif is_snapchat:
            ydl_opts.update({'format': 'best'})
        else:
            ydl_opts.update({'format': 'best'})
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            logger.info(f"Downloading {download_type}: {clean_url}")
            info = ydl.extract_info(clean_url, download=True)
            
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
            
            return filename
            
    except Exception as e:
        logger.error(f"Download error: {e}")
        raise e

# ================= ОБРАБОТЧИКИ =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Привет! Я бот для скачивания видео, аудио и фото!*\n\n"
        "📱 *TikTok (видео, аудио, фото) | Instagram Reels | Snapchat*\n\n"
        "🔗 Отправь ссылку — я всё сделаю!",
        parse_mode='Markdown'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🆘 Отправь ссылку. Для фото — сразу скачаю. Для видео — выбери формат.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    chat_id = update.message.chat_id
    
    # Разворачиваем короткие ссылки
    if 'vt.tiktok.com' in url or 'vm.tiktok.com' in url:
        logger.info(f"Expanding short URL: {url}")
        url = await asyncio.to_thread(expand_url, url)
        logger.info(f"Expanded to: {url}")
    
    clean_url = url.split('?')[0]
    
    supported = ['tiktok.com', 'instagram.com', 'snapchat.com']
    if not any(s in clean_url for s in supported):
        await update.message.reply_text("❌ Поддерживаются: TikTok, Instagram, Snapchat.")
        return
    
    # ФОТО
    if '/photo/' in clean_url:
        logger.info(f"Photo detected: {url}")
        status_msg = await update.message.reply_text("⏳ Скачиваю фото из TikTok...")
        
        try:
            photo_files = await asyncio.to_thread(download_tiktok_photos, url)
            
            if photo_files:
                total_size = sum(os.path.getsize(f) for f in photo_files) / (1024 * 1024)
                if total_size > 50:
                    await status_msg.edit_text(f"❌ Слишком большой размер: {total_size:.1f} МБ")
                    for f in photo_files:
                        os.remove(f)
                    return
                
                await status_msg.edit_text("📤 Отправляю...")
                
                if len(photo_files) == 1:
                    with open(photo_files[0], 'rb') as f:
                        await context.bot.send_photo(chat_id=chat_id, photo=f, caption="✅ Готово!")
                else:
                    media_group = []
                    for path in photo_files:
                        with open(path, 'rb') as f:
                            media_group.append(telegram.InputMediaPhoto(f.read()))
                    await context.bot.send_media_group(chat_id=chat_id, media=media_group)
                
                await status_msg.delete()
                for f in photo_files:
                    os.remove(f)
            else:
                await status_msg.edit_text("❌ Не удалось скачать фото.")
        except Exception as e:
            logger.error(f"Photo error: {e}")
            await status_msg.edit_text("❌ Ошибка при скачивании фото.")
        return
    
    # ВИДЕО/АУДИО
    if 'tiktok.com' in clean_url:
        site = 'TikTok'
    elif 'instagram.com' in clean_url:
        site = 'Instagram'
    else:
        site = 'Snapchat'
    
    user_data[chat_id] = {'url': url, 'site': site}
    
    keyboard = [
        [InlineKeyboardButton("🎬 Видео", callback_data='video'),
         InlineKeyboardButton("🎵 Аудио", callback_data='audio')]
    ]
    
    await update.message.reply_text(
        f"🔗 {site}\nЧто скачиваем?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    
    if chat_id not in user_data:
        await query.edit_message_text("❌ Сессия истекла.")
        return
    
    data = user_data[chat_id]
    url = data['url']
    site = data['site']
    dtype = query.data
    
    type_text = "видео" if dtype == 'video' else "аудио"
    await query.edit_message_text(f"⏳ Скачиваю {type_text} с {site}...")
    
    try:
        file_path = await asyncio.to_thread(sync_download_video, url, dtype)
        
        if file_path and os.path.exists(file_path):
            size_mb = os.path.getsize(file_path) / (1024 * 1024)
            if size_mb > 50:
                await query.edit_message_text(f"❌ {size_mb:.1f} МБ > 50 МБ")
                os.remove(file_path)
                del user_data[chat_id]
                return
            
            await query.edit_message_text("📤 Отправляю...")
            
            with open(file_path, 'rb') as f:
                if dtype == 'video':
                    await context.bot.send_video(chat_id=chat_id, video=f, caption=f"✅ {site}", supports_streaming=True)
                else:
                    await context.bot.send_audio(chat_id=chat_id, audio=f, caption=f"✅ {site}", title=f"{site}_audio")
            
            await query.delete_message()
            os.remove(file_path)
        else:
            await query.edit_message_text("❌ Не удалось скачать.")
    except Exception as e:
        err = str(e)
        logger.error(f"Error: {err}")
        if "login" in err.lower():
            msg = f"❌ Требуется авторизация."
        elif "not found" in err.lower():
            msg = "❌ Не найдено."
        else:
            msg = "❌ Ошибка."
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
                        app.process_update(Update.de_json(update_data, app.bot)), loop
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
