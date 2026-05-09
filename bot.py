import os
import subprocess
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    ContextTypes,
    filters
)

# ضع توكن البوت هنا
TOKEN = "8409383212:AAGn1kYV1T_SpjwR_JA2xtKEV_FFrRlBxfE"

# إنشاء مجلد للمقاطع
os.makedirs("parts", exist_ok=True)


async def handle_video(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(
        "جاري تحميل الفيديو..."
    )

    # الحصول على الفيديو
    video = update.message.video

    # تحميل الفيديو
    file = await context.bot.get_file(
        video.file_id
    )

    await file.download_to_drive(
        "input.mp4"
    )

    await update.message.reply_text(
        "جاري تقسيم الفيديو..."
    )

    # تقسيم الفيديو إلى أجزاء 30 ثانية
    subprocess.run([
        "ffmpeg",
        "-i",
        "input.mp4",
        "-c",
        "copy",
        "-map",
        "0",
        "-segment_time",
        "30",
        "-f",
        "segment",
        "parts/output%03d.mp4"
    ])

    # إرسال المقاطع
    files = sorted(
        os.listdir("parts")
    )

    for filename in files:

        path = os.path.join(
            "parts",
            filename
        )

        with open(path, "rb") as f:

            await update.message.reply_video(
                video=f
            )

    await update.message.reply_text(
        "تم الانتهاء."
    )


# إنشاء التطبيق
app = ApplicationBuilder().token(
    TOKEN
).build()

# استقبال الفيديوهات
app.add_handler(
    MessageHandler(
        filters.VIDEO,
        handle_video
    )
)

print("Bot Started...")

# تشغيل البوت
app.run_polling()
