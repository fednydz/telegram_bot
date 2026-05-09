import os
import asyncio
import tempfile
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

# 🔐 استخدام متغير البيئة بدلاً من الكتابة المباشرة
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
    # رسالة حالة قابلة للتعديل
    status_msg = await update.message.reply_text("⏳ جاري تحميل الفيديو...")

    video = update.message.video
    tg_file = await context.bot.get_file(video.file_id)

    # 📁 مجلد مؤقت فريد لكل طلب (يُحذف تلقائياً بعد الانتهاء)
    with tempfile.TemporaryDirectory() as tmpdir:
        input_path = os.path.join(tmpdir, "input.mp4")
        output_pattern = os.path.join(tmpdir, "part_%03d.mp4")

        await tg_file.download_to_drive(input_path)
        await status_msg.edit_text("⚙️ جاري تقسيم الفيديو...")

        # 🎬 أمر التقسيم (أكثر استقراراً)
        # ملاحظة: -c copy سريع لكن قد يسبب مشاكل مزامنة إذا لم يبدأ عند keyframe
        # للحصول على دقة أعلى، استبدل -c copy بـ: -c:v libx264 -c:a aac
        cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-c", "copy",
            "-f", "segment",
            "-segment_time", "30",
            "-reset_timestamps", "1",
            output_pattern
        ]

        await run_ffmpeg(cmd)

        # 📂 جلب الملفات الناتجة
        parts = sorted([f for f in os.listdir(tmpdir) if f.endswith(".mp4")])
        if not parts:
            await status_msg.edit_text("❌ فشل تقسيم الفيديو. تأكد من صيغة الفيديو أو جربه مرة أخرى.")
            return

        await status_msg.edit_text(f"✅ تم إنشاء {len(parts)} مقطع. جاري الإرسال...")

        # 📤 إرسال المقاطع
        for part in parts:
            part_path = os.path.join(tmpdir, part)
            file_size = os.path.getsize(part_path)

            # ⚠️ تلغرام يقبل الفيديو حتى 50MB فقط. إذا تجاوزها نرسله كملف (يدعم حتى 2GB)
            if file_size > 50 * 1024 * 1024:
                await update.message.reply_document(
                    document=open(part_path, "rb"),
                    caption=f" {part} (حجم كبير: {file_size/1024/1024:.1f} MB)"
                )
            else:
                await update.message.reply_video(video=open(part_path, "rb"))

        await status_msg.edit_text("🎉 تم إرسال جميع المقاطع بنجاح!")

# 🤖 إعداد التطبيق
def main() -> None:
    app = ApplicationBuilder().token(TOKEN).build()
    
    # إضافة معالج الفيديوهات
    app.add_handler(MessageHandler(filters.VIDEO, handle_video))
    
    # معالج الأخطاء العامة
    app.add_error_handler(lambda update, context: logging.error(f"Error: {context.error}"))
    
    print("🤖 البوت يعمل الآن...")
    app.run_polling()

if __name__ == "__main__":
    main()
