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
MAX_YOUTUBE_DURATION = 10800  # ✅ 3 ساعات (10,800 ثانية)

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
    
    logger.info(f"✂️ Splitting {duration}s video into {max_duration}s parts...")
    
    while start_time < duration:
        part_num += 1
        output_path = os.path.join(output_dir, f'part_{part_num:03d}.mp4')
        remaining = duration - start_time
        part_duration = min(max_duration, remaining)
        
        try:
            subprocess.run(['ffmpeg', '-y', '-i', input_path, '-ss', str(start_time), '-t', str(part_duration), '-c', 'copy', '-avoid_negative_ts', 'make_zero', '-movflags', '+faststart', output_path], capture_output=True, timeout=120)
            if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
                parts.append(output_path)
                logger.info(f"✅ Created part {part_num}/{int(duration//max_duration)+1}")
        except Exception as e:
            logger.error(f"Split error at {start_time}s: {e}")
        
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
        "👋 أهلاً! أنا بوت تقسيم الفيديوهات.\n\n"
        "📹 أرسل فيديو (حتى 200MB) أو رابط يوتيوب\n"
        "⏱️ سأقسمه إلى أجزاء 60 ثانية\n"
        "🎥 أدعم فيديوهات حتى 3 ساعات!"
    )

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    video = message.video or (message.document if message.document and message.document.mime_type.startswith('video/') else None)
    
    if not video:
        return
    
    file_size = video.file_size or 0
    
    if file_size > MAX_VIDEO_SIZE:
        await message.reply_text(f"❌ الفيديو كبير جداً!\nالحد الأقصى: {MAX_VIDEO_SIZE // (1024*1024)} ميجابايت")
        return
    
    status_msg = await message.reply_text('⏳ جاري التحميل...')
    temp_dir = None
    
    try:
        temp_dir = tempfile.mkdtemp()
        input_path = os.path.join(temp_dir, 'input.mp4')
        
        await safe_edit_message(status_msg, '⏳ جاري التحميل...')
        file = await video.get_file()
        await file.download_to_drive(input_path)
        
        if not os.path.exists(input_path) or os.path.getsize(input_path) < 1000:
            await safe_edit_message(status_msg, '❌ فشل التحميل')
            return
        
        duration = get_video_duration(input_path)
        if duration:
            await safe_edit_message(status_msg, f'✂️ جاري التقسيم...\n⏱️ المدة: {int(duration//60)} دقيقة\n📊 الأجزاء المتوقعة: {int(duration//60)+1}')
        
        parts, total_duration = split_video(input_path, temp_dir, MAX_DURATION)
        
        if not parts:
            await safe_edit_message(status_msg, '❌ فشل التقسيم')
            return
        
        total_parts = len(parts)
        await safe_edit_message(status_msg, f'📤 جاري إرسال {total_parts} جزء...')
        
        for i, part_path in enumerate(parts, 1):
            if not os.path.exists(part_path):
                continue
            
            file_size = os.path.getsize(part_path)
            
            try:
                if file_size > 20 * 1024 * 1024:
                    with open(part_path, 'rb') as f:
                        await message.reply_document(
                            document=f,
                            caption=f'📹 الجزء {i}/{total_parts}',
                            filename=f'part_{i}.mp4'
                        )
                else:
                    with open(part_path, 'rb') as f:
                        await message.reply_video(
                            video=f,
                            caption=f'🎬 الجزء {i}/{total_parts}',
                            supports_streaming=True
                        )
            except Exception as e:
                logger.error(f"Failed to send part {i}: {e}")
            
            await asyncio.sleep(0.5)
        
        await safe_edit_message(status_msg, f'✅ تم!\n📊 الأجزاء: {total_parts}\n⏱️ المدة: {int(total_duration//60)} دقيقة\n🗑️ تم الحذف')
        
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        await safe_edit_message(status_msg, f'❌ خطأ: {str(e)[:100]}')
    
    finally:
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                logger.error(f"Cleanup error: {e}")

async def handle_youtube(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text
    if not is_youtube_url(url):
        return
    
    status_msg = await update.message.reply_text('🎥 جاري التحميل من يوتيوب...')
    temp_dir = None
    
    try:
        temp_dir = tempfile.mkdtemp()
        video_path = os.path.join(temp_dir, 'video')
        
        await safe_edit_message(status_msg, '🎥 جاري التحميل من يوتيوب...\n⏳ قد يستغرق عدة دقائق للفيديوهات الطويلة')
        
        # تحديث yt-dlp
        try:
            subprocess.run(['yt-dlp', '-U'], capture_output=True, timeout=30)
        except:
            pass
        
        # ✅ زيادة المهلة لـ 3 ساعات (10,800 ثانية)
        cmd = [
            'yt-dlp',
            '-f', 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/bestvideo+bestaudio/best',
            '--merge-output-format', 'mp4',
            '-o', f'{video_path}.%(ext)s',
            '--no-playlist',
            '--restrict-filenames',
            '--no-warnings',
            '--socket-timeout', '60',
            '--retries', '5',
            '--fragment-retries', '5',
            '--extractor-retries', '3',
            '--no-check-certificate',
            url
        ]
        
        logger.info(f"🎥 Downloading from: {url}")
        # ✅ زيادة المهلة إلى 1800 ثانية (30 دقيقة) للتحميل
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        
        if result.returncode != 0:
            logger.error(f"yt-dlp error: {result.stderr}")
            await safe_edit_message(status_msg, '❌ فشل التحميل من يوتيوب')
            return
        
        # البحث عن الملف
        downloaded_file = None
        for file in os.listdir(temp_dir):
            if file.endswith(('.mp4', '.mkv', '.webm')):
                downloaded_file = os.path.join(temp_dir, file)
                logger.info(f"✅ Found: {file}")
                break
        
        if not downloaded_file:
            await safe_edit_message(status_msg, '❌ لم يتم العثور على الفيديو')
            return
        
        duration = get_video_duration(downloaded_file)
        logger.info(f"⏱️ Duration: {duration}s ({int(duration//60)} min)")
        
        # ✅ التحقق من مدة 3 ساعات
        if duration and duration > MAX_YOUTUBE_DURATION:
            await safe_edit_message(status_msg, f'❌ الفيديو طويل جداً: {int(duration//3600)} ساعة {int((duration%3600)//60)} دقيقة\nالحد الأقصى: 3 ساعات')
            return
        
        estimated_parts = int(duration // 60) + 1
        await safe_edit_message(status_msg, f'✂️ جاري التقسيم...\n⏱️ المدة: {int(duration//60)} دقيقة\n📊 عدد الأجزاء: {estimated_parts}')
        
        parts, total_duration = split_video(downloaded_file, temp_dir, MAX_DURATION)
        
        if not parts:
            await safe_edit_message(status_msg, '❌ فشل التقسيم')
            return
        
        total_parts = len(parts)
        await safe_edit_message(status_msg, f'📤 جاري إرسال {total_parts} جزء...')
        
        for i, part_path in enumerate(parts, 1):
            if not os.path.exists(part_path):
                continue
            
            file_size = os.path.getsize(part_path)
            
            try:
                if file_size > 20 * 1024 * 1024:
                    with open(part_path, 'rb') as f:
                        await update.message.reply_document(
                            document=f,
                            caption=f'📹 الجزء {i}/{total_parts}',
                            filename=f'youtube_part_{i}.mp4'
                        )
                else:
                    with open(part_path, 'rb') as f:
                        await update.message.reply_video(
                            video=f,
                            caption=f'🎬 الجزء {i}/{total_parts}',
                            supports_streaming=True
                        )
                logger.info(f"📤 Sent {i}/{total_parts}")
            except Exception as e:
                logger.error(f"Send error: {e}")
            
            await asyncio.sleep(0.5)
        
        await safe_edit_message(status_msg, f'✅ تم بنجاح!\n📊 الأجزاء: {total_parts}\n⏱️ المدة: {int(total_duration//60)} دقيقة')
    
    except subprocess.TimeoutExpired:
        logger.error("Download timeout")
        await safe_edit_message(status_msg, '⏱️ انتهى وقت التحميل')
    except Exception as e:
        logger.error(f"YouTube error: {e}", exc_info=True)
        await safe_edit_message(status_msg, f'❌ خطأ: {str(e)[:100]}')
    
    finally:
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                logger.error(f"Cleanup error: {e}")

def main():
    if not BOT_TOKEN:
        logger.error("No token!")
        return
    
    logger.info("🚀 Starting Telegram bot (supports up to 3 hours)...")
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.VIDEO | filters.Document.MimeType('video/*'), handle_video))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_youtube))
    
    logger.info("✅ Bot is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
