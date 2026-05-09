import os
import asyncio
import subprocess
import tempfile
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler

TOKEN = os.getenv("BOT_TOKEN")
WAIT_VIDEO, WAIT_RATIO = range(2)
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎬 أرسل فيديو لتقسيمه إلى أجزاء مدة كل منها 40 ثانية.")
    return WAIT_VIDEO

async def receive_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    video = update.message.video
    if not video or video.file_size > 50 * 1024 * 1024:
        await update.message.reply_text("⚠️ أرسل فيديو صالح وأقل من 50 ميجابايت.")
        return WAIT_VIDEO

    tmp_dir = tempfile.TemporaryDirectory()
    input_path = os.path.join(tmp_dir.name, "input.mp4")
    
    try:
        video_file = await context.bot.get_file(video.file_id)
        await video_file.download_to_drive(input_path)
    except:
        await update.message.reply_text("❌ فشل تحميل الفيديو.")
        return WAIT_VIDEO

    context.user_data["tmp_dir"] = tmp_dir
    context.user_data["input_path"] = input_path

    keyboard = [
        [InlineKeyboardButton("📺 16:9", callback_data="16:9")],
        [InlineKeyboardButton("📱 9:16", callback_data="9:16")]
    ]
    await update.message.reply_text("✅ اختر نسبة العرض:", reply_markup=InlineKeyboardMarkup(keyboard))
    return WAIT_RATIO

async def select_ratio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ratio = query.data
    tmp_dir = context.user_data["tmp_dir"]
    input_path = context.user_data["input_path"]
    resized_path = os.path.join(tmp_dir.name, "resized.mp4")

    vf = "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2" if ratio == "16:9" else "scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2"

    try:
        subprocess.run(["ffmpeg", "-y", "-i", input_path, "-vf", vf, "-c:a", "copy", resized_path], check=True)
        output_pattern = os.path.join(tmp_dir.name, "part_%03d.mp4")
        subprocess.run([
            "ffmpeg", "-y", "-i", resized_path, "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k", "-map", "0", "-segment_time", "40",
            "-f", "segment", "-reset_timestamps", "1", output_pattern
        ], check=True)

        parts = sorted([f for f in os.listdir(tmp_dir.name) if f.startswith("part_")])
        for i, part in enumerate(parts, 1):
            with open(os.path.join(tmp_dir.name, part), "rb") as vid:
                await query.message.reply_video(vid, caption=f"🎞️ الجزء {i}")
            await asyncio.sleep(1.5)
        await query.message.reply_text("✅ تم الانتهاء!")
    except Exception as e:
        logger.error(e)
        await query.message.reply_text(f"❌ خطأ: {e}")
    finally:
        tmp_dir.cleanup()
        context.user_data.clear()
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🛑 تم الإلغاء.")
    return ConversationHandler.END

def main():
    app = Application.builder().token(TOKEN).build()
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={WAIT_VIDEO: [MessageHandler(filters.VIDEO, receive_video)], WAIT_RATIO: [MessageHandler(filters.ALL, select_ratio)]},
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    app.add_handler(conv)
    print("🤖 Bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()
