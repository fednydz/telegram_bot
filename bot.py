import os
import math
import asyncio
import logging
from pathlib import Path
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from moviepy.editor import VideoFileClip

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

CHUNK_DURATION = 30
TEMP_DIR = Path("temp_videos")
TEMP_DIR.mkdir(exist_ok=True)

async def process_video(user_id: int, chat_id: int, msg_id: int, input_path: str, bot):
    try:
        def run_split():
            clip = VideoFileClip(input_path)
            total = clip.duration
            parts = math.ceil(total / CHUNK_DURATION)
            paths = []
            
            for i in range(parts):
                start = i * CHUNK_DURATION
                end = min(start + CHUNK_DURATION, total)
                out = TEMP_DIR / f"{user_id}_part_{i+1}.mp4"
                clip.subclip(start, end).write_videofile(
                    str(out), codec="libx264", audio_codec="aac",
                    verbose=False, logger=None, threads=2
                )
                paths.append(out)
            clip.close()
            return parts, paths

        parts, chunk_paths = await asyncio.to_thread(run_split)
        await bot.edit_message_text(chat_id, msg_id, f"✅ تم التقسيم إلى {parts} أجزاء. جاري الإرسال...")

        for i, path in enumerate(chunk_paths, 1):
            caption = f"🎬 الجزء {i} من {parts}"
            try:
                with open(path, "rb") as f:
                    await bot.send_video(chat_id, video=f, caption=caption)
            except Exception:
                with open(path, "rb") as f:
                    await bot.send_document(chat_id, document=f, caption=f"{caption} (ملف)")
            path.unlink(missing_ok=True)

        await bot.edit_message_text(chat_id, msg_id, "🎉 تم إرسال جميع الأجزاء بنجاح!")

    except Exception as e:
        logger.error(f"Error: {e}")
        try:
            await bot.edit_message_text(chat_id, msg_id, f"❌ خطأ: {str(e)[:100]}")
        except Exception:
            pass
    finally:
        Path(input_path).unlink(missing_ok=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 أهلاً! أرسل أي فيديو وسأقوم بتقسيمه إلى أجزاء مدة كل منها 30 ثانية.")

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ جاري التحميل والمعالجة...")
    video = update.message.video
    file = await video.get_file()
    input_path = TEMP_DIR / f"{update.effective_user.id}_{video.file_unique_id}.mp4"
    await file.download_to_drive(str(input_path))
    
    asyncio.create_task(process_video(
        update.effective_user.id, update.effective_chat.id,
        msg.message_id, str(input_path), context.bot
    ))

def main():
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise ValueError("⚠️ متغير BOT_TOKEN غير موجود في البيئة!")

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.VIDEO, handle_video))

    logger.info("🤖 بوت التقسيم يعمل الآن...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
