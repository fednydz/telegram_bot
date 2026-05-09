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

    try:

        await update.message.reply_text(
            "جاري تحميل الفيديو..."
        )

        # الحصول على الفيديو
        video = update.message.video

        # تحميل الفيديو
        tg_file = await context.bot.get_file(
            video.file_id
        )

        input_file = "input.mp4"

        await tg_file.download_to_drive(
            input_file
        )

        await update.message.reply_text(
            "جاري تقسيم الفيديو..."
        )

        # أمر تقسيم الفيديو
        subprocess.run([
            "ffmpeg",
            "-i",
            input_file,
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

        # قراءة الملفات الناتجة
        files = sorted(
            os.listdir("parts")
        )

        if not files:

            await update.message.reply_text(
                "فشل تقسيم الفيديو."
            )

            return

        await update.message.reply_text(
            f"تم إنشاء {len(files)} مقطع."
        )

        # إرسال المقاطع
        for filename in files:

            file_path = os.path.join(
                "parts",
                filename
            )

            with open(file_path, "rb") as f:

                await update.message.reply_video(
                    video=f
                )

        await update.message.reply_text(
            "تم الانتهاء."
        )

        # حذف الملفات المؤقتة
        if os.path.exists(input_file):
            os.remove(input_file)

        for filename in files:

            path = os.path.join(
                "parts",
                filename
            )

            if os.path.exists(path):
                os.remove(path)

    except Exception as e:

        await update.message.reply_text(
            f"حدث خطأ:\n{str(e)}"
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
