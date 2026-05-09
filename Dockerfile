import os
import asyncio
import tempfile
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("❌ يرجى تعيين متغير البيئة BOT_TOKEN في Railway")

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

async def run_ffmpeg(cmd: list) -> None:
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"فشل FFmpeg: {stderr.decode('utf-8', errors='ignore')}")

async def set_ratio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("16:9 (أفقي)", callback_data="ratio_16:9"),
         InlineKeyboardButton("9:16 (عمودي)", callback_data="ratio_9:16")]
    ]
    await update.message.reply_text("📐 اختر نسبة العرض المطلوبة للفيديو:", reply_markup=InlineKeyboardMarkup(keyboard))

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    ratio = query.data.split("_")[1]
    context.user_data["aspect_ratio"] = ratio
    await query.edit_message_text(f"✅ تم تعيين النسبة إلى {ratio}")

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    status_msg = await update.message.reply_text("⏳ جاري تحميل الفيديو...")
    video = update.message.video
    tg_file = await context.bot.get_file(video.file_id)

    with tempfile.TemporaryDirectory() as tmpdir:
        input_path = os.path.join(tmpdir, "input.mp4")
        output_pattern = os.path.join(tmpdir, "part_%03d.mp4")
        logo_path = "logo.png"

        await tg_file.download_to_drive(input_path)
        await status_msg.edit_text("⚙️ جاري التقسيم وإضافة العلامة المائية...")

        # 1️⃣ تحديد فلتر الفيديو بناءً على النسبة
        aspect = context.user_data.get("aspect_ratio", "original")
        if aspect == "16:9":
            # تحويل لأفقي مع حشو أسود
            video_filter = "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2"
        elif aspect == "9:16":
            # تحويل لعمودي مع حشو جانبي
            video_filter = "scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2"
        else:
            video_filter = None

        # 2️⃣ فلتر الشعار (تصغير الحجم + الموقع)
        # scale=120:-1 -> عرض 120 بكسل، الارتفاع تلقائي للحفاظ على النسبة
        # main_w-overlay_w-20 -> الموقع من اليمين (عرض الفيديو - عرض الشعار - هامش 20)
        # 20 -> الموقع من الأعلى (هامش 20)
        logo_filter = "[1:v]scale=120:-1[logo];"
        position = "main_w-overlay_w-20:20" 

        # 3️⃣ دمج الأوامر
        if video_filter:
            # إذا تم تغيير النسبة: نعدل الفيديو [v0] ثم نضع الشعار عليه
            filter_complex = f"[0:v]{video_filter}[v0];{logo_filter}[v0][logo]overlay={position}:shortest=1"
        else:
            # إذا النسبة أصلية: نضع الشعار مباشرة على الفيديو الأصلي
            filter_complex = f"{logo_filter}[0:v][logo]overlay={position}:shortest=1"

        cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-i", logo_path,
            "-filter_complex", filter_complex,
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
            "-c:a", "aac",
            "-f", "segment", "-segment_time", "30",
            "-reset_timestamps", "1",
            output_pattern,
        ]

        await run_ffmpeg(cmd)

        parts = sorted([f for f in os.listdir(tmpdir) if f.endswith(".mp4")])
        if not parts:
            await status_msg.edit_text("❌ فشل تقسيم الفيديو.")
            return

        await status_msg.edit_text(f"✅ تم إنشاء {len(parts)} مقطع. جاري الإرسال...")

        for part in parts:
            part_path = os.path.join(tmpdir, part)
            file_size = os.path.getsize(part_path)
            if file_size > 50 * 1024 * 1024:
                await update.message.reply_document(document=open(part_path, "rb"), caption=f"📹 {part}")
            else:
                await update.message.reply_video(video=open(part_path, "rb"))

        await status_msg.edit_text("🎉 تم إرسال جميع المقاطع بنجاح!")

def main() -> None:
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("ratio", set_ratio))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.VIDEO, handle_video))
    app.add_error_handler(lambda update, context: logging.error(f"Error: {context.error}"))
    print("🤖 البوت يعمل الآن (علامة مائية صغيرة + جهة اليمين)...")
    app.run_polling()

if __name__ == "__main__":
    main()
