import os
import logging
import subprocess
import math
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.utils import executor
from dotenv import load_dotenv

load_dotenv()

# ========== إعدادات ffmpeg ==========
FFMPEG_PATH = "/usr/bin/ffmpeg"  # مسار ffmpeg في Railway/Linux

# التحقق من وجود ffmpeg
def check_ffmpeg():
    try:
        result = subprocess.run([FFMPEG_PATH, "-version"], capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ FFmpeg تم العثور عليه بنجاح")
            return True
        else:
            print("❌ FFmpeg غير موجود!")
            return False
    except:
        print("❌ FFmpeg غير موجود!")
        return False

# ========== إعدادات البوت ==========
API_TOKEN = os.getenv('BOT_TOKEN')
if not API_TOKEN:
    print("❌ خطأ: لم يتم العثور على BOT_TOKEN")
    exit(1)

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())
logging.basicConfig(level=logging.INFO)

# تخزين بيانات المستخدمين
user_data = {}

# أزرار اختيار النسبة
ratio_keyboard = ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
ratio_keyboard.add(KeyboardButton("16:9"), KeyboardButton("9:16"))

# ========== دوال معالجة الفيديو باستخدام FFmpeg ==========

def get_video_duration(input_path):
    """الحصول على مدة الفيديو بالثواني باستخدام ffprobe"""
    try:
        cmd = [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", input_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return float(result.stdout.strip())
    except:
        return 0

def crop_video_ffmpeg(input_path, output_path, ratio):
    """
    قص الفيديو إلى النسبة المطلوبة (16:9 أو 9:16) باستخدام FFmpeg
    """
    # الحصول على أبعاد الفيديو الأصلية
    probe_cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height", "-of", "csv=p=0",
        input_path
    ]
    result = subprocess.run(probe_cmd, capture_output=True, text=True)
    width, height = map(int, result.stdout.strip().split(','))
    
    current_ratio = width / height
    target_ratio = 16/9 if ratio == "16:9" else 9/16
    
    if current_ratio > target_ratio:
        # قص العرض (crop from sides)
        new_width = int(height * target_ratio)
        crop_width = (width - new_width) // 2
        crop_filter = f"crop={new_width}:{height}:{crop_width}:0"
    else:
        # قص الارتفاع (crop from top and bottom)
        new_height = int(width / target_ratio)
        crop_height = (height - new_height) // 2
        crop_filter = f"crop={width}:{new_height}:0:{crop_height}"
    
    # تطبيق القص وتغيير الحجم إلى 720p
    cmd = [
        FFMPEG_PATH, "-i", input_path,
        "-vf", f"{crop_filter},scale=720:-2" if ratio == "16:9" else f"{crop_filter},scale=-2:720",
        "-c:a", "copy",  # نسخ الصوت دون تغيير
        "-y",  # استبدال الملف إذا وجد
        output_path
    ]
    
    subprocess.run(cmd, capture_output=True, text=True, check=True)
    return output_path

def add_watermark_ffmpeg(input_path, output_path, watermark_text):
    """إضافة علامة مائية نصية باستخدام FFmpeg"""
    cmd = [
        FFMPEG_PATH, "-i", input_path,
        "-vf", f"drawtext=text='{watermark_text}':fontcolor=white:fontsize=30:box=1:boxcolor=black@0.5:boxborderw=5:x=w-text_w-10:y=h-text_h-10",
        "-c:a", "copy",
        "-y",
        output_path
    ]
    subprocess.run(cmd, capture_output=True, text=True, check=True)
    return output_path

def split_video_ffmpeg(input_path, output_dir, part_duration=60):
    """
    تقسيم الفيديو إلى أجزاء كل جزء مدته part_duration ثانية
    باستخدام FFmpeg (دون إعادة ترميز - سريع جداً)
    """
    total_duration = get_video_duration(input_path)
    
    if total_duration <= part_duration:
        # فيديو قصير - انسخه كما هو
        output_path = os.path.join(output_dir, "part_1.mp4")
        subprocess.run([FFMPEG_PATH, "-i", input_path, "-c", "copy", "-y", output_path], check=True)
        return [output_path]
    
    num_parts = math.ceil(total_duration / part_duration)
    parts_paths = []
    
    for i in range(num_parts):
        start_time = i * part_duration
        output_path = os.path.join(output_dir, f"part_{i+1}.mp4")
        
        # استخدم -c copy للنسخ المباشر (سريع جداً)
        cmd = [
            FFMPEG_PATH, "-i", input_path,
            "-ss", str(start_time),
            "-t", str(part_duration),
            "-c", "copy",
            "-y",
            output_path
        ]
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        parts_paths.append(output_path)
    
    return parts_paths

def process_video_complete(input_path, output_dir, ratio, watermark_text):
    """
    معالجة الفيديو بالكامل: قص + علامة مائية + تقسيم
    """
    # 1. قص الفيديو إلى النسبة المطلوبة
    cropped_path = os.path.join(output_dir, "cropped.mp4")
    crop_video_ffmpeg(input_path, cropped_path, ratio)
    
    # 2. إضافة العلامة المائية
    watermarked_path = os.path.join(output_dir, "watermarked.mp4")
    add_watermark_ffmpeg(cropped_path, watermarked_path, watermark_text)
    
    # 3. تقسيم الفيديو إلى أجزاء
    parts_paths = split_video_ffmpeg(watermarked_path, output_dir, part_duration=60)
    
    # تنظيف الملفات المؤقتة
    if os.path.exists(cropped_path):
        os.remove(cropped_path)
    if os.path.exists(watermarked_path):
        os.remove(watermarked_path)
    
    return parts_paths

# ========== أوامر البوت ==========

@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    await message.reply(
        "🎬 أهلاً بك في بوت معالجة الفيديو!\n\n"
        "📤 أرسل أي فيديو (أي مدة كانت)\n"
        "وسأقوم بـ:\n"
        "1️⃣ قص الفيديو إلى النسبة التي تختارها (16:9 أو 9:16)\n"
        "2️⃣ إضافة علامة مائية\n"
        "3️⃣ تقسيم الفيديو إلى مقاطع (كل 60 ثانية)\n\n"
        "⚡ البوت يعمل بـ FFmpeg مباشرة - معالجة سريعة جداً!\n\n"
        "📐 أرسل الفيديو الآن."
    )

@dp.message_handler(commands=['help'])
async def help_command(message: types.Message):
    await message.reply(
        "📖 **مساعدة البوت**\n\n"
        "1️⃣ أرسل أي فيديو\n"
        "2️⃣ اختر النسبة المطلوبة\n"
        "3️⃣ انتظر المعالجة (ستكون سريعة)\n"
        "4️⃣ ستحصل على الفيديو مقسماً إلى مقاطع\n\n"
        "✨ البوت يستخدم FFmpeg مباشرة للمعالجة السريعة."
    )

@dp.message_handler(content_types=['video'])
async def handle_video(message: types.Message):
    user_id = message.from_user.id
    video = message.video
    
    duration_min = video.duration // 60
    duration_sec = video.duration % 60
    
    user_data[user_id] = {
        'file_id': video.file_id,
        'duration': video.duration
    }
    
    await message.reply(
        f"✅ تم استلام الفيديو\n"
        f"📏 المدة: {duration_min} دقيقة و {duration_sec} ثانية\n\n"
        f"📐 اختر النسبة:",
        reply_markup=ratio_keyboard
    )

@dp.message_handler(lambda message: message.text in ['16:9', '9:16'])
async def handle_ratio(message: types.Message):
    user_id = message.from_user.id
    ratio = message.text
    
    if user_id not in user_data or 'file_id' not in user_data[user_id]:
        await message.reply("❌ حدث خطأ. أرسل الفيديو مرة أخرى.")
        return
    
    processing_msg = await message.reply("⚙️ جاري معالجة الفيديو باستخدام FFmpeg... ⏳")
    
    input_path = None
    output_dir = None
    
    try:
        # 1. تحميل الفيديو من تلغرام
        await processing_msg.edit_text("📥 جاري تحميل الفيديو...")
        file = await bot.get_file(user_data[user_id]['file_id'])
        input_path = f"input_{user_id}.mp4"
        await bot.download_file(file.file_path, input_path)
        
        # 2. التحقق من FFmpeg
        if not check_ffmpeg():
            await processing_msg.edit_text("❌ خطأ: FFmpeg غير مثبت على الخادم!")
            return
        
        # 3. إنشاء مجلد للمخرجات
        output_dir = f"output_{user_id}"
        os.makedirs(output_dir, exist_ok=True)
        
        # 4. معالجة الفيديو (قص + علامة مائية + تقسيم)
        await processing_msg.edit_text("🎬 جاري قص الفيديو وإضافة العلامة المائية...")
        watermark_text = "@mounirdjouida_bot"
        
        parts_paths = process_video_complete(input_path, output_dir, ratio, watermark_text)
        
        # 5. إرسال الأجزاء إلى المستخدم
        await processing_msg.edit_text(f"📤 جاري إرسال {len(parts_paths)} مقطع...")
        
        for i, part_path in enumerate(parts_paths):
            with open(part_path, 'rb') as video_file:
                await message.reply_video(
                    types.InputFile(video_file, filename=f"video_part_{i+1}.mp4"),
                    caption=f"🎬 الجزء {i+1} من {len(parts_paths)}"
                )
            os.remove(part_path)  # حذف المقطع بعد الإرسال
        
        # 6. تنظيف الملفات المؤقتة
        if input_path and os.path.exists(input_path):
            os.remove(input_path)
        if output_dir and os.path.exists(output_dir):
            os.rmdir(output_dir)
        
        await processing_msg.delete()
        await message.reply("✨ تم إرسال جميع المقاطع بنجاح! FFmpeg يعمل بسرعة 🚀")
        
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr if e.stderr else str(e)
        logging.error(f"FFmpeg خطأ: {error_msg}")
        await processing_msg.edit_text(f"❌ خطأ في FFmpeg: {error_msg[:150]}")
    except Exception as e:
        error_msg = str(e)
        logging.error(f"خطأ عام: {error_msg}")
        await processing_msg.edit_text(f"❌ حدث خطأ: {error_msg[:150]}")
    
    finally:
        # تنظيف إضافي
        if input_path and os.path.exists(input_path):
            try:
                os.remove(input_path)
            except:
                pass
        if output_dir and os.path.exists(output_dir):
            try:
                os.rmdir(output_dir)
            except:
                pass
        if user_id in user_data:
            del user_data[user_id]

# ========== تشغيل البوت ==========
if __name__ == '__main__':
    print("🚀 بدء تشغيل بوت FFmpeg...")
    check_ffmpeg()
    executor.start_polling(dp, skip_updates=True)
