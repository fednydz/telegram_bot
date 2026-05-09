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

@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    await message.reply(
        "🎬 أهلاً بك في بوت معالجة الفيديو!\n\n"
        "أرسل فيديو مدته 5 دقائق أو أكثر\n"
        "وسأقوم بقصه وإضافة علامة مائية وتقسيمه"
    )

@dp.message_handler(content_types=['video'])
async def handle_video(message: types.Message):
    user_id = message.from_user.id
    if message.video.duration < 300:
        await message.reply("⏰ أرسل فيديو مدته 5 دقائق أو أكثر")
        return
    user_data[user_id] = {'file_id': message.video.file_id}
    await message.reply("📐 اختر النسبة:", reply_markup=ratio_keyboard)

@dp.message_handler(lambda m: m.text in ['16:9', '9:16'])
async def handle_ratio(message: types.Message):
    user_id = message.from_user.id
    if user_id not in user_data:
        await message.reply("أرسل الفيديو أولاً")
        return
    
    msg = await message.reply("⚙️ جاري المعالجة...")
    try:
        file = await bot.get_file(user_data[user_id]['file_id'])
        await bot.download_file(file.file_path, f"input_{user_id}.mp4")
        
        clip = VideoFileClip(f"input_{user_id}.mp4")
        target = (1920, 1080) if message.text == "16:9" else (1080, 1920)
        clip = clip.resize(target)
        
        watermark = TextClip("@YourBot", fontsize=40, color='white').set_opacity(0.6).set_position(('right','bottom')).set_duration(clip.duration)
        final = CompositeVideoClip([clip, watermark])
        
        output = f"output_{user_id}.mp4"
        final.write_videofile(output, codec='libx264', audio_codec='aac')
        
        with open(output, 'rb') as video:
            await message.reply_video(video, caption="✅ فيديو معالج")
        
        os.remove(f"input_{user_id}.mp4")
        os.remove(output)
        await msg.edit_text("✨ تم!")
    except Exception as e:
        await msg.edit_text(f"❌ خطأ: {str(e)[:100]}")
    finally:
        if user_id in user_data:
            del user_data[user_id]

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
