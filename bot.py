import os
import asyncio
import tempfile
import subprocess
import logging
import re
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes, CommandHandler
from dotenv import load_dotenv

load_dotenv()

# ========== إعداد السجلات ==========
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ========== المتغيرات ==========
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
MAX_DURATION = 60  # أقصى مدة للجزء بالثواني
MAX_VIDEO_SIZE = 50 * 1024 * 1024  # 50 ميجابايت
MAX_YOUTUBE_DURATION = 600  # 10 دقائق كحد أقصى لليوتيوب

# ========== التحقق من رابط يوتيوب ==========
def is_youtube_url(url):
    """التحقق إذا كان الرابط من يوتيوب"""
    youtube_regex = (
        r'(https?://)?(www\.)?'
        '(youtube|youtu|youtube-nocookie)\.(com|be)/'
        '(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})'
    )
    return re.match(youtube_regex, url)

# ========== دوال الفيديو ==========
def get_video_duration(input_path):
    """الحصول على مدة الفيديو بالثواني"""
    try:
        result = subprocess.run(
            [
                'ffprobe', '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                input_path
            ],
            capture_output=True, text=True, timeout=10
        )
        return float(result.stdout.strip())
    except Exception as e:
        logger.error(f"Duration error: {e}")
        return None

def split_video(input_path, output_dir, max_duration=60):
    """تقسيم الفيديو إلى أجزاء باستخدام ffmpeg"""
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
            subprocess.run(
                [
                    'ffmpeg', '-y',
                    '-i', input_path,
                    '-ss', str(start_time),
                    '-t', str(part_duration),
                    '-c', 'copy',
                    '-avoid_negative_ts', 'make_zero',
                    '-movflags', '+faststart',
                    output_path
                ],
                capture_output=True, timeout=60
            )
            
            if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
                parts.append(output_path)
        except Exception as e:
            logger.error(f"Split error at {start_time}s: {e}")
        
        start_time += part_duration
    
    return parts, duration

def download_youtube_video(url, output_path):
    """تحميل فيديو من يوتيوب باستخدام yt-dlp"""
    try:
        cmd = [
            'yt-dlp',
            '-f', 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            '--merge-output-format', 'mp4',
            '-o', output_path,
            '--no-playlist',
            '--restrict-filenames',
            url
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600  # 10 دقائق كحد أقصى
        )
        
        if result.returncode == 0:
            # البحث عن الملف المحمل
            base_path = output_path.replace('.%(ext)s', '')
            for file in os.listdir(os.path.dirname(output_path)):
                if file.startswith(os.path.basename(base_path)) and file.endswith('.mp4'):
                    return os.path.join(os.path.dirname(output_path), file)
            return None
        else:
            logger.error(f"yt-dlp error: {result.stderr}")
            return None
            
    except subprocess.TimeoutExpired:
        logger.error("YouTube download timeout")
        return None
    except Exception as e:
        logger.error(f"YouTube download error: {e}")
        return None

# ========== معالجة الأوامر ==========
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """رسالة الترحيب"""
    await update.message.reply_text(
        "👋 أهلاً بك في بوت تقسيم الفيديوهات!\n\n"
        "📹 **ماذا أفعل؟**\n"
        "1️⃣ أرسل فيديو مباشرة وسأقسمه إلى أجزاء (60 ثانية)\n"
        "2️⃣ أرسل رابط يوتيوب وسأحمله وأقسمه لك\n\n"
        "⚙️ **المميزات:**\n"
        "• تقسيم سريع ودقيق\n"
        "• الحفاظ على جودة الفيديو\n"
        "• دعم فيديوهات حتى 50 ميجابايت\n"
        "• تحميل من يوتيوب (حتى 10 دقائق)\n\n"
        "📝 **اكتب /help للمزيد من المعلومات**"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """رسالة المساعدة"""
    await update.message.reply_text(
        "📖 **كيفية الاستخدام:**\n\n"
        "**📹 للفيديوهات المباشرة:**\n"
        "1️⃣ أرسل الفيديو مباشرة\n"
        "2️⃣ انتظر حتى يتم التقسيم\n"
        "3️⃣ ستستلم الأجزاء واحداً تلو الآخر\n\n"
        "**🎥 لليوتيوب:**\n"
        "1️⃣ أرسل رابط فيديو يوتيوب\n"
        "2️⃣ سأقوم بتحميله وتقسيمه\n"
        "3️⃣ ستستلم الأجزاء مقسمة\n\n"
        "⚠️ **ملاحظات:**\n"
        "• الحد الأقصى للفيديو المباشر: 50 ميجابايت\n"
        "• الحد الأقصى لليوتيوب: 10 دقائق\n"
        "• مدة كل جزء: 60 ثانية كحد أقصى\n"
        "• قد تستغرق العملية بضع دقائق للفيديوهات الطويلة"
    )

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض حالة البوت"""
    await update.message.reply_text(
        "🤖 **حالة البوت:**\n"
        "✅ البوت يعمل بشكل طبيعي\n"
        f"⏱️ مدة كل جزء: {MAX_DURATION} ثانية\n"
        f"📦 الحد الأقصى (فيديو): {MAX_VIDEO_SIZE // (1024*1024)} ميجابايت\n"
        f"🎥 الحد الأقصى (يوتيوب): {MAX_YOUTUBE_DURATION // 60} دقائق\n\n"
        "أرسل فيديو أو رابط يوتيوب للبدء!"
    )

# ========== معالجة الفيديو المباشر ==========
async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """استقبال الفيديو وتقسيمه"""
    message = update.message
    
    # الحصول على الفيديو
    video = message.video
    if not video:
        if message.document and message.document.mime_type.startswith('video/'):
            video = message.document
        else:
            return
    
    # التحقق من الحجم
    if video.file_size and video.file_size > MAX_VIDEO_SIZE:
        await message.reply_text(
            f"❌ الفيديو كبير جداً!\n"
            f"الحد الأقصى: {MAX_VIDEO_SIZE // (1024*1024)} ميجابايت\n"
            f"حجم الفيديو: {video.file_size // (1024*1024)} ميجابايت"
        )
        return
    
    status_msg = await message.reply_text('⏳ جاري تحميل الفيديو...')
    
    try:
        file = await video.get_file()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = os.path.join(temp_dir, 'input.mp4')
            
            await status_msg.edit_text('⏳ جاري تحميل الفيديو...')
            await file.download_to_drive(input_path)
            
            if not os.path.exists(input_path) or os.path.getsize(input_path) < 1000:
                await status_msg.edit_text('❌ فشل في تحميل الفيديو')
                return
            
            await status_msg.edit_text('✂️ جاري تقسيم الفيديو...')
            parts, total_duration = split_video(input_path, temp_dir, MAX_DURATION)
            
            if not parts:
                await status_msg.edit_text('❌ فشل في تقسيم الفيديو')
                return
            
            total_parts = len(parts)
            await status_msg.edit_text(
                f'📤 جاري إرسال {total_parts} جزء...\n'
                f'⏱️ المدة الكلية: {int(total_duration)} ثانية'
            )
            
            for i, part_path in enumerate(parts, 1):
                file_size = os.path.getsize(part_path)
                
                if file_size > MAX_VIDEO_SIZE:
                    with open(part_path, 'rb') as f:
                        await message.reply_document(
                            document=f,
                            caption=f'📹 الجزء {i} من {total_parts}',
                            filename=f'part_{i}.mp4'
                        )
                else:
                    with open(part_path, 'rb') as f:
                        await message.reply_video(
                            video=f,
                            caption=f'🎬 الجزء {i} من {total_parts}',
                            supports_streaming=True
                        )
                
                await asyncio.sleep(0.5)
            
            await status_msg.edit_text(
                f'✅ تم بنجاح!\n'
                f'📊 عدد الأجزاء: {total_parts}\n'
                f'⏱️ المدة الكلية: {int(total_duration)} ثانية'
            )
    
    except Exception as e:
        logger.error(f"Video processing error: {e}", exc_info=True)
        await status_msg.edit_text(f'❌ حدث خطأ: {str(e)}')

# ========== معالجة روابط يوتيوب ==========
async def handle_youtube_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تحميل فيديو من يوتيوب وتقسيمه"""
    message = update.message
    url = message.text
    
    status_msg = await message.reply_text('🎥 جاري التحميل من يوتيوب...')
    
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            video_path = os.path.join(temp_dir, 'youtube_video.%(ext)s')
            
            await status_msg.edit_text('🎥 جاري تحميل الفيديو من يوتيوب...\n⏳ قد يستغرق هذا بضع دقائق')
            
            # تحميل الفيديو
            downloaded_path = download_youtube_video(url, video_path)
            
            if not downloaded_path or not os.path.exists(downloaded_path):
                await status_msg.edit_text(
                    '❌ فشل في تحميل الفيديو من يوتيوب\n'
                    'تأكد من:\n'
                    '• صحة الرابط\n'
                    '• أن الفيديو ليس طويلاً جداً (أقصى مدة 10 دقائق)\n'
                    '• أن الفيديو متاح للتحميل'
                )
                return
            
            # التحقق من المدة
            duration = get_video_duration(downloaded_path)
            if duration and duration > MAX_YOUTUBE_DURATION:
                await status_msg.edit_text(
                    f'❌ الفيديو طويل جداً!\n'
                    f'المدة: {int(duration // 60)} دقيقة\n'
                    f'الحد الأقصى: {MAX_YOUTUBE_DURATION // 60} دقائق'
                )
                return
            
            # تقسيم الفيديو
            await status_msg.edit_text('✂️ جاري تقسيم الفيديو...')
            parts, total_duration = split_video(downloaded_path, temp_dir, MAX_DURATION)
            
            if not parts:
                await status_msg.edit_text('❌ فشل في تقسيم الفيديو')
                return
            
            # إرسال الأجزاء
            total_parts = len(parts)
            await status_msg.edit_text(
                f'📤 جاري إرسال {total_parts} جزء...\n'
                f'⏱️ المدة الكلية: {int(total_duration)} ثانية'
            )
            
            for i, part_path in enumerate(parts, 1):
                file_size = os.path.getsize(part_path)
                
                if file_size > MAX_VIDEO_SIZE:
                    with open(part_path, 'rb') as f:
                        await message.reply_document(
                            document=f,
                            caption=f' الجزء {i} من {total_parts}',
                            filename=f'youtube_part_{i}.mp4'
                        )
                else:
                    with open(part_path, 'rb') as f:
                        await message.reply_video(
                            video=f,
                            caption=f'🎬 الجزء {i} من {total_parts}',
                            supports_streaming=True
                        )
                
                await asyncio.sleep(0.5)
            
            await status_msg.edit_text(
                f'✅ تم بنجاح!\n'
                f'📊 عدد الأجزاء: {total_parts}\n'
                f'⏱️ المدة الكلية: {int(total_duration)} ثانية'
            )
    
    except Exception as e:
        logger.error(f"YouTube processing error: {e}", exc_info=True)
        await status_msg.edit_text(f'❌ حدث خطأ: {str(e)}')

# ========== معالجة الرسائل النصية ==========
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الرسائل النصية (رابط يوتيوب)"""
    text = update.message.text
    
    if text and is_youtube_url(text):
        await handle_youtube_url(update, context)

# ========== معالجة الأخطاء ==========
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Exception while handling an update: {context.error}")

# ========== التشغيل الرئيسي ==========
def main():
    if not BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set!")
        return
    
    logger.info("🚀 Starting Telegram video splitter bot with YouTube support...")
    
    # إنشاء التطبيق
    application = Application.builder().token(BOT_TOKEN).build()
    
    # إضافة المعالجات
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("status", status_command))
    
    # معالجة الفيديوهات المباشرة
    application.add_handler(
        MessageHandler(
            filters.VIDEO | (filters.Document.MimeType('video/*')),
            handle_video
        )
    )
    
    # معالجة روابط يوتيوب
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        )
    )
    
    # معالج الأخطاء
    application.add_error_handler(error_handler)
    
    # بدء البوت
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
