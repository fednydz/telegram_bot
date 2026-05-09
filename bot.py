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

API_TOKEN = os.getenv('BOT_TOKEN')
if not API_TOKEN:
    print("❌ خطأ: لم يتم العثور على BOT_TOKEN")
    exit(1)

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())
logging.basicConfig(level=logging.INFO)

user_data = {}

ratio_keyboard = ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
ratio_keyboard.add(KeyboardButton("16:9"), KeyboardButton("9:16"))

def crop_to_ratio(clip, target_ratio):
    """قص الفيديو إلى النسبة المطلوبة"""
    current_ratio = clip.w / clip.h
    if current_ratio > target_ratio:
        new_width = int(target_ratio * clip.h)
        x_center = clip.w / 2
        return clip.crop(x_center=new_width/2, width=new_width)
    else:
        new_height = int(clip.w / target_ratio)
        y_center = clip.h / 2
        return clip.crop(y_center=new_height/2, height=new_height)

def split_video_into_parts(clip, output_dir, duration_per_part=60):
    """تقسيم الفيديو إلى أجزاء"""
    total_duration = clip.duration
    if total_duration <= duration_per_part:
        # إذا كان الفيديو أقصر من مدة التقسيم، لا تقسيمه
        segment_path = os.path.join(output_dir, f"part_1.mp4")
        clip.write_videofile(segment_path, codec='libx264', audio_codec='aac', verbose=False, logger=None)
        return [segment_path]
    
    num_parts = math.ceil(total_duration / duration_per_part)
    parts_paths = []
    
    for i in range(num_parts):
        start_time = i * duration_per_part
        end_time = min((i + 1) * duration_per_part, total_duration)
        
        segment = clip.subclip(start_time, end_time)
        segment_path = os.path.join(output_dir, f"part_{i+1}.mp4")
        segment.write_videofile(segment_path, codec='libx264', audio_codec='aac', verbose=False, logger=None)
        parts_paths.append(segment_path)
    
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
        "✨ لا توجد شروط على مدة الفيديو!"
    )

@dp.message_handler(content_types=['video'])
async def handle_video(message: types.Message):
    user_id = message.from_user.id
    video = message.video
    
    # لا يوجد شرط على المدة - أي فيديو مقبول
    duration_min = video.duration // 60
    duration_sec = video.duration % 60
    
    user_data[user_id] = {
        'file_id': video.file_id,
        'duration': video.duration
    }
    
    await message.reply(
        f"✅ تم استلام الفيديو (مدته: {duration_min} دقيقة و {duration_sec} ثانية)\n\n"
        "📐 الآن اختر النسبة التي تريدها:",
        reply_markup=ratio_keyboard
    )

@dp.message_handler(lambda message: message.text in ['16:9', '9:16'])
async def handle_ratio(message: types.Message):
    user_id = message.from_user.id
    ratio = message.text
    
    if user_id not in user_data or 'file_id' not in user_data[user_id]:
        await message.reply("❌ حدث خطأ. أرسل الفيديو مرة أخرى باستخدام /start")
        return
    
    processing_msg = await message.reply("⚙️ جاري معالجة الفيديو... قد يستغرق هذا بضع لحظات.")
    
    try:
        # تحميل الفيديو
        file = await bot.get_file(user_data[user_id]['file_id'])
        input_path = f"input_{user_id}.mp4"
        await bot.download_file(file.file_path, input_path)
        
        output_dir = f"output_{user_id}"
        os.makedirs(output_dir, exist_ok=True)
        
        # معالجة الفيديو
        clip = VideoFileClip(input_path)
        
        # قص النسبة
        target_ratio = 16/9 if ratio == "16:9" else 9/16
        cropped_clip = crop_to_ratio(clip, target_ratio)
        
        # تغيير الحجم
        if ratio == "16:9":
            cropped_clip = cropped_clip.resize(height=720)
        else:
            cropped_clip = cropped_clip.resize(width=720)
        
        # إضافة علامة مائية
        watermark_text = "🔹 @mounirdjouida_bot 🔹"
        watermark = (TextClip(watermark_text, fontsize=30, color='white', font='Arial')
                     .set_opacity(0.5)
                     .set_position(('right', 'bottom'))
                     .set_duration(cropped_clip.duration))
        
        final_clip = CompositeVideoClip([cropped_clip, watermark])
        
        # تقسيم الفيديو
        await processing_msg.edit_text("✂️ جاري تقسيم الفيديو إلى مقاطع...")
        parts_paths = split_video_into_parts(final_clip, output_dir, duration_per_part=60)
        
        # إرسال المقاطع
        await processing_msg.edit_text(f"📤 جاري إرسال {len(parts_paths)} مقطع...")
        
        for i, part_path in enumerate(parts_paths):
            with open(part_path, 'rb') as video_file:
                await message.reply_video(
                    types.InputFile(video_file),
                    caption=f"🎬 الجزء {i+1} من {len(parts_paths)}"
                )
            os.remove(part_path)
        
        # تنظيف
        clip.close()
        cropped_clip.close()
        final_clip.close()
        os.remove(input_path)
        os.rmdir(output_dir)
        
        await processing_msg.edit_text("✨ تم الانتهاء من إرسال جميع المقاطع!")
        
    except Exception as e:
        await processing_msg.edit_text(f"❌ حدث خطأ: {str(e)[:200]}")
        logging.error(f"Error: {e}")
    finally:
        if user_id in user_data:
            del user_data[user_id]

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
