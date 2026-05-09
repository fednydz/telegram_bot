import os
import asyncio
import tempfile
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("❌ يرجى تعيين متغير البيئة BOT_TOKEN في Railway")

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

async def run_ffmpeg(cmd: list) -> None:
    """تشغيل FFmpeg بشكل غير متزامن"""
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"فشل FFmpeg: {stderr.decode('utf-8', errors='ignore')}")

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    status_msg = await update.message.reply_text("⏳ جاري تحميل الفيديو...")

    video = update.message.video
    tg_file = await context.bot.get_file(video.file_id)

    with tempfile.TemporaryDirectory() as tmpdir:
        input_path = os.path.join(tmpdir, "input.mp4")
        output_pattern = os.path.join(tmpdir, "part_%03d.mp4")
        logo_path = "logo.png"  # ✅ مسار الشعار

        await tg_file.download_to_drive(input_path)
        await status_msg.edit_text("⚙️ جاري تقسيم الفيديو وإضافة العلامة المائية...")

        # 🎬 أمر التقسيم مع إضافة watermark
        # overlay=10:10 = وضع الشعار في الزاوية العلوية اليسرى مع مسافة 10px
        # يمكنك تغيير الموقع: overlay=W-w-10:10 (علوي يمين) أو overlay=10:H-h-10 (سفلي يسار)
        cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-i", logo_path,
            "-filter_complex", "[0:v][1:v]overlay=10:10:shortest=1",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "23",
            "-c:a", "aac",
            "-f", "segment",
            "-segment_time", "30",
            "-reset_timestamps", "1",
            output_pattern
        ]

        await run_ffmpeg(cmd)

        parts = sorted([f for f in os.listdir(tmpdir) if f.endswith(".mp4")])
        if not parts:
            await status_msg.edit_text("❌ فشل تقسيم الفيديو.")
            return

        await status_msg.edit_text(f"✅ تم إنشاء {len(parts)} مقطع مع العلامة المائية. جاري الإرسال...")

        for part in parts:
            part_path = os.path.join(tmpdir, part)
            file_size = os.path.getsize(part_path)

            if file_size > 50 * 1024 * 1024:
                await update.message.reply_document(
                    document=open(part_path, "rb"),
                    caption=f"📹 {part}"
                )
            else:
                await update.message.reply_video(video=open(part_path, "rb"))

        await status_msg.edit_text("🎉 تم إرسال جميع المقاطع بنجاح!")

def main() -> None:
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.VIDEO, handle_video))
    app.add_error_handler(lambda update, context: logging.error(f"Error: {context.error}"))
    print("🤖 البوت يعمل الآن مع العلامة المائية...")
    app.run_polling()

if __name__ == "__main__":
    main()
