import os
import asyncio
import tempfile
import subprocess
import logging
import re
import shutil
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes, CommandHandler
from telegram.error import BadRequest

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
MAX_DURATION = 60
MAX_VIDEO_SIZE = 200 * 1024 * 1024
MAX_YOUTUBE_DURATION = 10800

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
            subprocess.run(['ffmpeg', '-y', '-i', input_path, '-ss', str(start_time), '-t', str(part_duration), '-c', 'copy', '-avoid_negative_ts', 'make_zero', '-movflags', '+faststart', output_path], capture_output=True, timeout=120)
            if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
                parts.append(output_path)
                logger.info(f"✅ Part {part_num} created")
        except Exception as e:
            logger.error(f"Split error: {e}")
        
        start_time += part_duration
    
    return parts, duration

async def safe_edit_message(message, new_text):
    try:
        await message.edit_text(new_text)
        await asyncio.sleep(0.3)
    except BadRequest as e:
        if "message is not modified" in str(e).lower():
            pass
        else:
            raise
    except Exception as e:
        logger.error(f"Edit error: {e}")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 أهلاً! أرسل فيديو أو رابط يوتيوب وسأقسمه لأجزاء 60 ثانية"
    )

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    video = message.video or (message.document if message.document and message.document.mime_type.startswith('video/') else None)
    
    if not video:
        return
    
    file_size = video.file_size or 0
    if file_size > MAX_VIDEO_SIZE:
        await message.reply_text(f"❌ الفيديو كبير جداً! الحد: {MAX_VIDEO_SIZE // (1024*1024)}MB")
        return
    
    status_msg = await message.reply_text('⏳ جاري التحميل...')
    temp_dir = None
    
    try:
        temp_dir = tempfile.mkdtemp()
        input_path = os.path.join(temp_dir, 'input.mp4')
        
        file = await video.get_file()
        await file.download_to_drive(input_path)
        
        if not os.path.exists(input_path):
            await safe_edit_message(status_msg, '❌ فشل التحميل')
            return
        
        await safe_edit_message(status_msg, '✂️ جاري التقسيم...')
        parts, total_duration = split_video(input_path, temp_dir, MAX_DURATION)
        
        if not parts:
            await safe_edit_message(status_msg, '❌ فشل التقسيم')
            return
        
        await safe_edit_message(status_msg, f'📤 جاري إرسال {len(parts)} جزء...')
        
        for i, part_path in enumerate(parts, 1):
            if not os.path.exists(part_path):
                continue
            try:
                with open(part_path, 'rb') as f:
                    await message.reply_video(video=f, caption=f'الجزء {i}/{len(parts)}', supports_streaming=True)
            except:
                with open(part_path, 'rb') as f:
                    await message.reply_document(document=f, caption=f'الجزء {i}/{len(parts)}')
            await asyncio.sleep(0.5)
        
        await safe_edit_message(status_msg, f'✅ تم! {len(parts)} جزء')
        
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        await safe_edit_message(status_msg, f'❌ خطأ: {str(e)[:50]}')
    finally:
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

async def handle_youtube(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text
    if not is_youtube_url(url):
        return
    
    status_msg = await update.message.reply_text('🎥 جاري التحميل من يوتيوب...')
    temp_dir = None
    
    try:
        temp_dir = tempfile.mkdtemp()
        
        # ✅ تحديث yt-dlp
        subprocess.run(['yt-dlp', '-U', '--quiet'], capture_output=True, timeout=30)
        
        # ✅ خيارات تحميل محسّنة
        cmd = [
            'yt-dlp',
            '-f', 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            '--merge-output-format', 'mp4',
            '-o', os.path.join(temp_dir, 'video.%(ext)s'),
            '--no-playlist',
            '--restrict-filenames',
            '--no-warnings',
            '--socket-timeout', '30',
            '--retries', '3',
            '--extractor-args', 'youtube:player_client=web',
            url
        ]
        
        logger.info(f"🎥 Downloading: {url}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        
        if result.returncode != 0:
            logger.error(f"yt-dlp error: {result.stderr}")
            await safe_edit_message(status_msg, f'❌ فشل التحميل\nالخطأ: {result.stderr[:100]}')
            return
        
        # البحث عن الملف
        video_file = None
        for file in os.listdir(temp_dir):
            if file.endswith('.mp4'):
                video_file = os.path.join(temp_dir, file)
                logger.info(f"✅ Found: {file}")
                break
        
        if not video_file:
            await safe_edit_message(status_msg, '❌ لم أجد الفيديو')
            return
        
        duration = get_video_duration(video_file)
        if duration and duration > MAX_YOUTUBE_DURATION:
            await safe_edit_message(status_msg, f'❌ طويل جداً: {int(duration//60)} دقيقة (الحد: {MAX_YOUTUBE_DURATION//60})')
            return
        
        await safe_edit_message(status_msg, '✂️ جاري التقسيم...')
        parts, total_duration = split_video(video_file, temp_dir, MAX_DURATION)
        
        if not parts:
            await safe_edit_message(status_msg, '❌ فشل التقسيم')
            return
        
        await safe_edit_message(status_msg, f'📤 جاري إرسال {len(parts)} جزء...')
        
        for i, part_path in enumerate(parts, 1):
            if not os.path.exists(part_path):
                continue
            try:
                with open(part_path, 'rb') as f:
                    await update.message.reply_video(video=f, caption=f'الجزء {i}/{len(parts)}', supports_streaming=True)
            except:
                with open(part_path, 'rb') as f:
                    await update.message.reply_document(document=f, caption=f'الجزء {i}/{len(parts)}')
            await asyncio.sleep(0.5)
        
        await safe_edit_message(status_msg, f'✅ تم! {len(parts)} جزء')
    
    except subprocess.TimeoutExpired:
        logger.error("Timeout")
        await safe_edit_message(status_msg, '⏱️ انتهى الوقت')
    except Exception as e:
        logger.error(f"YouTube error: {e}", exc_info=True)
        await safe_edit_message(status_msg, f'❌ خطأ: {str(e)[:100]}')
    finally:
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

def main():
    if not BOT_TOKEN:
        logger.error("No token!")
        return
    
    logger.info("🚀 Starting bot...")
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.VIDEO | filters.Document.MimeType('video/*'), handle_video))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_youtube))
    logger.info("✅ Bot running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
