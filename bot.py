import os
import asyncio
import tempfile
import subprocess
import logging
import re
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes, CommandHandler

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
MAX_DURATION = 60
MAX_VIDEO_SIZE = 50 * 1024 * 1024

def is_youtube_url(url):
    youtube_regex = r'(https?://)?(www\.)?(youtube|youtu|youtube-nocookie)\.(com|be)/(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})'
    return re.match(youtube_regex, url)

def get_video_duration(input_path):
    try:
        result = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', input_path], capture_output=True, text=True, timeout=10)
        return float(result.stdout.strip())
    except:
        return None

def split_video(input_path, output_dir, max_duration=60):
    duration = get_video_duration(input_path)
    if duration is None:
        return None, 0
    
    parts = []
    part_num = 0
    start_time = 0.0
    
    while start_time < duration:
        part_num += 1
        output_path = os.path.join(output_dir, f'part_{part_num:03d}.mp4')
        remaining = duration - start_time
        part_duration = min(max_duration, remaining)
        
        try:
            subprocess.run(['ffmpeg', '-y', '-i', input_path, '-ss', str(start_time), '-t', str(part_duration), '-c', 'copy', '-avoid_negative_ts', 'make_zero', '-movflags', '+faststart', output_path], capture_output=True, timeout=60)
            if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
                parts.append(output_path)
        except Exception as e:
            logger.error(f"Split error: {e}")
        
        start_time += part_duration
    
    return parts, duration

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 أهلاً! أرسل فيديو أو رابط يوتيوب وسأقسمه إلى أجزاء 60 ثانية.")

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    video = message.video or (message.document if message.document and message.document.mime_type.startswith('video/') else None)
    
    if not video:
        return
    
    status_msg = await message.reply_text('⏳ جاري المعالجة...')
    
    try:
        file = await video.get_file()
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = os.path.join(temp_dir, 'input.mp4')
            await file.download_to_drive(input_path)
            
            await status_msg.edit_text('✂️ جاري التقسيم...')
            parts, duration = split_video(input_path, temp_dir, MAX_DURATION)
            
            if parts:
                await status_msg.edit_text(f'📤 جاري إرسال {len(parts)} جزء...')
                for i, part in enumerate(parts, 1):
                    with open(part, 'rb') as f:
                        await message.reply_video(video=f, caption=f'الجزء {i}/{len(parts)}', supports_streaming=True)
                    await asyncio.sleep(0.5)
                await status_msg.edit_text('✅ تم!')
            else:
                await status_msg.edit_text('❌ فشل التقسيم')
    except Exception as e:
        logger.error(f"Error: {e}")
        await status_msg.edit_text(f'❌ خطأ: {str(e)}')

async def handle_youtube(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text
    if not is_youtube_url(url):
        return
    
    status_msg = await update.message.reply_text('🎥 جاري التحميل من يوتيوب...')
    
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            video_path = os.path.join(temp_dir, 'yt.mp4')
            subprocess.run(['yt-dlp', '-f', 'best[ext=mp4]/best', '-o', video_path, '--no-playlist', url], capture_output=True, timeout=300)
            
            if os.path.exists(video_path):
                await status_msg.edit_text('✂️ جاري التقسيم...')
                parts, duration = split_video(video_path, temp_dir, MAX_DURATION)
                
                if parts:
                    await status_msg.edit_text(f'📤 جاري إرسال {len(parts)} جزء...')
                    for i, part in enumerate(parts, 1):
                        with open(part, 'rb') as f:
                            await update.message.reply_video(video=f, caption=f'الجزء {i}/{len(parts)}', supports_streaming=True)
                        await asyncio.sleep(0.5)
                    await status_msg.edit_text('✅ تم!')
            else:
                await status_msg.edit_text('❌ فشل التحميل')
    except Exception as e:
        logger.error(f"YouTube error: {e}")
        await status_msg.edit_text(f'❌ خطأ: {str(e)}')

def main():
    if not BOT_TOKEN:
        logger.error("No token!")
        return
    
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.VIDEO | filters.Document.MimeType('video/*'), handle_video))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_youtube))
    app.run_polling()

if __name__ == '__main__':
    main()
