import os
import asyncio
import tempfile
import subprocess
import logging
import re
import shutil
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes, CommandHandler

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
MAX_DURATION = 60
MAX_VIDEO_SIZE = 200 * 1024 * 1024  # 200 ميجابايت
MAX_YOUTUBE_DURATION = 600  # 10 دقائق

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
                logger.info(f"✅ Created part {part_num}: {os.path.getsize(output_path)} bytes")
        except Exception as e:
            logger.error(f"Split error: {e}")
        
        start_time += part_duration
    
    return parts, duration

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 أهلاً! أنا بوت تقسيم الفيديوهات.\n\n"
        "📹 أرسل فيديو (حتى 200MB) أو رابط يوتيوب\n"
        "⏱️ سأقسمه إلى أجزاء 60 ثانية"
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
        logger.info(f"📁 Created temp directory: {temp_dir}")
        
        input_path = os.path.join(temp_dir, 'input.mp4')
        
        await status_msg.edit_text('⏳ جاري التحميل...')
        file = await video.get_file()
        await file.download_to_drive(input_path)
        
        if not os.path.exists(input_path) or os.path.getsize(input_path) < 1000:
            await status_msg.edit_text('❌ فشل التحميل')
            return
        
        logger.info(f" Downloaded: {input_path} ({os.path.getsize(input_path)} bytes)")
        
        await status_msg.edit_text('✂️ جاري التقسيم...')
        parts, total_duration = split_video(input_path, temp_dir, MAX_DURATION)
        
        if not parts:
            await status_msg.edit_text('❌ فشل التقسيم')
            return
        
        total_parts = len(parts)
        logger.info(f"✂️ Split into {total_parts} parts")
        await status_msg.edit_text(f'📤 جاري إرسال {total_parts} جزء...')
        
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
                logger.info(f"📤 Sent part {i}/{total_parts}")
            except Exception as e:
                logger.error(f"Failed to send part {i}: {e}")
            
            await asyncio.sleep(0.5)
        
        await status_msg.edit_text(f'✅ تم!\n📊 الأجزاء: {total_parts}\n⏱️ المدة: {int(total_duration)} ثانية\n🗑️ تم حذف الفيديو الأصلي')
        
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        await status_msg.edit_text(f'❌ خطأ: {str(e)}')
    
    finally:
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
                logger.info(f"🗑️ Cleaned up temp directory: {temp_dir}")
            except Exception as e:
                logger.error(f"Failed to cleanup {temp_dir}: {e}")

async def handle_youtube(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text
    if not is_youtube_url(url):
        return
    
    status_msg = await update.message.reply_text('🎥 جاري التحميل من يوتيوب...')
    temp_dir = None
    
    try:
        temp_dir = tempfile.mkdtemp()
        logger.info(f"📁 Created temp directory: {temp_dir}")
        
        video_path = os.path.join(temp_dir, 'yt.mp4')
        
        await status_msg.edit_text('🎥 جاري التحميل من يوتيوب...')
        subprocess.run(['yt-dlp', '-f', 'best[ext=mp4]/best', '-o', video_path, '--no-playlist', url], capture_output=True, timeout=300)
        
        if not os.path.exists(video_path):
            await status_msg.edit_text('❌ فشل التحميل')
            return
        
        duration = get_video_duration(video_path)
        if duration and duration > MAX_YOUTUBE_DURATION:
            await status_msg.edit_text(f' الفيديو طويل جداً: {int(duration//60)} دقيقة (الحد: 10 دقائق)')
            return
        
        await status_msg.edit_text('✂️ جاري التقسيم...')
        parts, total_duration = split_video(video_path, temp_dir, MAX_DURATION)
        
        if not parts:
            await status_msg.edit_text('❌ فشل التقسيم')
            return
        
        total_parts = len(parts)
        await status_msg.edit_text(f'📤 جاري إرسال {total_parts} جزء...')
        
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
                            caption=f' الجزء {i}/{total_parts}',
                            supports_streaming=True
                        )
                logger.info(f" Sent YouTube part {i}/{total_parts}")
            except Exception as e:
                logger.error(f"Failed to send part {i}: {e}")
            
            await asyncio.sleep(0.5)
        
        await status_msg.edit_text(f'✅ تم!\n الأجزاء: {total_parts}\n️ المدة: {int(total_duration)} ثانية\n🗑️ تم حذف الفيديو')
    
    except Exception as e:
        logger.error(f"YouTube error: {e}")
        await status_msg.edit_text(f'❌ خطأ: {str(e)}')
    
    finally:
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
                logger.info(f"🗑️ Cleaned up temp directory: {temp_dir}")
            except Exception as e:
                logger.error(f"Failed to cleanup {temp_dir}: {e}")

def main():
    if not BOT_TOKEN:
        logger.error("No token!")
        return
    
    logger.info("🚀 Starting Telegram video splitter bot...")
    
    # ✅ بناء التطبيق (متوافق مع v21)
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.VIDEO | filters.Document.MimeType('video/*'), handle_video))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_youtube))
    
    logger.info("✅ Bot is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
