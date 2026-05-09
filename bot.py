import os
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.utils import executor
from moviepy.video.io.VideoFileClip import VideoFileClip
from moviepy.video.VideoClip import TextClip
from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip
from dotenv import load_dotenv
import math

load_dotenv()

# ========== توجيه مسار ffmpeg يدوياً (لضمان العمل على Railway) ==========
FFMPEG_PATH = "/usr/bin/ffmpeg"  # المسار الافتراضي داخل حاويات Linux/Railway
if os.path.exists(FFMPEG_PATH):
    from moviepy.config import change_settings
    change_settings({"FFMPEG_BINARY": FFMPEG_PATH})
    print(f"✅ تم توجيه moviepy لاستخدام ffmpeg من: {FFMPEG_PATH}")
else:
    print(f"⚠️ لم يتم العثور على ffmpeg في المسار {FFMPEG_PATH}!")
    # محاولة البحث عن ffmpeg في مسارات أخرى شائعة
    possible_paths = ["/usr/local/bin/ffmpeg", "/usr/bin/ffmpeg"]
    for path in possible_paths:
        if os.path.exists(path):
            from moviepy.config import change_settings
            change_settings({"FFMPEG_BINARY": path})
            print(f"✅ تم توجيه moviepy لاستخدام ffmpeg من: {path}")
            break
# ======================================================================

API_TOKEN = os.getenv('BOT_TOKEN')
if not API_TOKEN:
    print("❌ خطأ: لم يتم العثور على BOT_TOKEN في متغيرات البيئة")
    exit(1)

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())
logging.basicConfig(level=logging.INFO)

# تخزين بيانات المستخدمين مؤقتاً
user_data = {}

# أزرار اختيار النسبة
ratio_keyboard = ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
ratio_keyboard.add(KeyboardButton("16:9"), KeyboardButton("9:16"))

def crop_to_ratio(clip, target_ratio):
    """قص الفيديو إلى النسبة المطلوبة (16:9 أو 9:16)"""
    current_ratio = clip.w / clip.h
    if current_ratio > target_ratio:
        # الفيديو أعرض مما ينبغي - نقص العرض
        new_width = int(target_ratio * clip.h)
        x_center = clip.w / 2
        return clip.crop(x_center=new_width/2, width=new_width)
    else:
        # الفيديو أطول مما ينبغي - نقص الارتفاع
        new_height = int(clip.w / target_ratio)
        y_center = clip.h / 2
        return clip.crop(y_center=new_height/2, height=new_height)

def split_video_into_parts(clip, output_dir, duration_per_part=60):
    """
    تقسيم الفيديو إلى أجزاء
    كل جزء مدته duration_per_part ثانية (افتراضياً 60 ثانية)
    """
    total_duration = clip.duration
    
    # إذا كان الفيديو أقصر من مدة التقسيم، لا نحتاج لتقسيمه
    if total_duration <= duration_per_part:
        output_path = os.path.join(output_dir, "part_1.mp4")
        clip.write_videofile(output_path, codec='libx264', audio_codec='aac', 
                             verbose=False, logger=None, preset='fast')
        return [output_path]
    
    # حساب عدد الأجزاء المطلوبة
    num_parts = math.ceil(total_duration / duration_per_part)
    parts_paths = []
    
    for i in range(num_parts):
        start_time = i * duration_per_part
        end_time = min((i + 1) * duration_per_part, total_duration)
        
        # قص المقطع
        segment = clip.subclip(start_time, end_time)
        segment_path = os.path.join(output_dir, f"part_{i+1}.mp4")
        
        # حفظ المقطع مع تحسين الإعدادات للسرعة وجودة مقبولة
        segment.write_videofile(segment_path, codec='libx264', audio_codec='aac', 
                                verbose=False, logger=None, preset='fast')
        parts_paths.append(segment_path)
        segment.close()
    
    return parts_paths

@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    await message.reply(
        "🎬 أهلاً بك في بوت معالجة الفيديو!\n\n"
        "📤 أرسل أي فيديو (أي مدة كانت)\n"
        "وسأقوم بـ:\n"
        "1️⃣ قص الفيديو إلى النسبة التي تختارها (16:9 أو 9:16)\n"
        "2️⃣ إضافة علامة مائية\n"
        "3️⃣ تقسيم الفيديو إلى مقاطع (كل 60 ثانية)\n"
        "4️⃣ إرسال جميع المقاطع إليك\n\n"
        "✨ لا توجد شروط على مدة الفيديو!\n"
        "⚡ ملاحظة: الفيديوهات الطويلة قد تستغرق وقتاً أطول في المعالجة."
    )

@dp.message_handler(content_types=['video'])
async def handle_video(message: types.Message):
    user_id = message.from_user.id
    video = message.video
    
    # حساب مدة الفيديو بالدقائق والثواني
    duration_min = video.duration // 60
    duration_sec = video.duration % 60
    
    # تخزين معلومات الفيديو
    user_data[user_id] = {
        'file_id': video.file_id,
        'duration': video.duration
    }
    
    # إعلام المستخدم باستلام الفيديو
    duration_text = f"{duration_min} دقيقة و {duration_sec} ثانية"
    await message.reply(
        f"✅ تم استلام الفيديو\n"
        f"📏 المدة: {duration_text}\n"
        f"📐 الآن اختر النسبة التي تريدها:",
        reply_markup=ratio_keyboard
    )

@dp.message_handler(lambda message: message.text in ['16:9', '9:16'])
async def handle_ratio(message: types.Message):
    user_id = message.from_user.id
    ratio = message.text
    
    # التحقق من وجود بيانات المستخدم
    if user_id not in user_data or 'file_id' not in user_data[user_id]:
        await message.reply("❌ حدث خطأ. أرسل الفيديو مرة أخرى باستخدام /start")
        return
    
    # رسالة المعالجة (سيتم تحديثها لاحقاً)
    processing_msg = await message.reply("⚙️ جاري معالجة الفيديو... قد يستغرق هذا بضع لحظات ⏳")
    
    input_path = None
    output_dir = None
    
    try:
        # 1. تحميل الفيديو من تلغرام
        await processing_msg.edit_text("📥 جاري تحميل الفيديو...")
        file = await bot.get_file(user_data[user_id]['file_id'])
        input_path = f"input_{user_id}.mp4"
        await bot.download_file(file.file_path, input_path)
        
        # 2. إنشاء مجلد للمخرجات
        output_dir = f"output_{user_id}"
        os.makedirs(output_dir, exist_ok=True)
        
        # 3. تحميل الفيديو باستخدام moviepy
        await processing_msg.edit_text("🎬 جاري تحليل الفيديو...")
        clip = VideoFileClip(input_path)
        
        # 4. قص الفيديو إلى النسبة المطلوبة
        await processing_msg.edit_text("✂️ جاري قص الفيديو إلى النسبة المطلوبة...")
        target_ratio = 16/9 if ratio == "16:9" else 9/16
        cropped_clip = crop_to_ratio(clip, target_ratio)
        
        # 5. تغيير الحجم (لتقليل حجم الملف وتسريع المعالجة)
        if ratio == "16:9":
            cropped_clip = cropped_clip.resize(height=720)
        else:
            cropped_clip = cropped_clip.resize(width=720)
        
        # 6. إضافة علامة مائية
        await processing_msg.edit_text("💧 جاري إضافة العلامة المائية...")
        watermark_text = "🔹 @mounirdjouida_bot 🔹"
        watermark = (TextClip(watermark_text, fontsize=30, color='white', font='Arial')
                     .set_opacity(0.5)
                     .set_position(('right', 'bottom'))
                     .set_duration(cropped_clip.duration))
        
        final_clip = CompositeVideoClip([cropped_clip, watermark])
        
        # 7. تقسيم الفيديو إلى أجزاء
        await processing_msg.edit_text("✂️ جاري تقسيم الفيديو إلى مقاطع (كل 60 ثانية)...")
        parts_paths = split_video_into_parts(final_clip, output_dir, duration_per_part=60)
        
        # 8. إرسال الأجزاء إلى المستخدم
        await processing_msg.edit_text(f"📤 جاري إرسال {len(parts_paths)} مقطع...")
        
        for i, part_path in enumerate(parts_paths):
            with open(part_path, 'rb') as video_file:
                await message.reply_video(
                    types.InputFile(video_file, filename=f"part_{i+1}.mp4"),
                    caption=f"🎬 الجزء {i+1} من {len(parts_paths)}"
                )
            os.remove(part_path)  # حذف المقطع بعد الإرسال لتوفير المساحة
        
        # 9. تنظيف الملفات المؤقتة
        clip.close()
        cropped_clip.close()
        final_clip.close()
        
        await processing_msg.delete()  # حذف رسالة "جاري المعالجة"
        await message.reply("✨ تم الانتهاء من إرسال جميع المقاطع! شكراً لاستخدام البوت.")
        
    except Exception as e:
        error_message = str(e)
        logging.error(f"خطأ في معالجة الفيديو للمستخدم {user_id}: {error_message}")
        await processing_msg.edit_text(f"❌ حدث خطأ أثناء المعالجة:\n`{error_message[:150]}`", parse_mode='Markdown')
    
    finally:
        # تنظيف الملفات المؤقتة
        if input_path and os.path.exists(input_path):
            try:
                os.remove(input_path)
            except:
                pass
        
        if output_dir and os.path.exists(output_dir):
            try:
                os.rmdir(output_dir)
            except:
                pass  # قد يكون المجلد غير فارغ، لكن هذا طبيعي
        
        # تنظيف بيانات المستخدم
        if user_id in user_data:
            del user_data[user_id]

# أمر مساعدة إضافي
@dp.message_handler(commands=['help'])
async def help_command(message: types.Message):
    await message.reply(
        "📖 **مساعدة البوت**\n\n"
        "1️⃣ أرسل أي فيديو (أي مدة كانت)\n"
        "2️⃣ اختر النسبة المطلوبة (16:9 أو 9:16)\n"
        "3️⃣ انتظر حتى تتم المعالجة\n"
        "4️⃣ ستحصل على الفيديو مقسماً إلى مقاطع كل منها 60 ثانية\n\n"
        "**ملاحظات:**\n"
        "• العلامة المائية تضاف تلقائياً\n"
        "• الفيديوهات الطويلة قد تستغرق وقتاً أطول\n"
        "• الحد الأقصى لحجم الفيديو هو 50 ميجابايت (حدود Telegram)"
    )

if __name__ == '__main__':
    print("🚀 بدء تشغيل البوت...")
    executor.start_polling(dp, skip_updates=True)
