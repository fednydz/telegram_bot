"""
🎬 telegram_bot - بوت تقسيم الفيديو
يقوم بتقسيم الفيديوهات المرسلة إلى أجزاء مدة كل جزء 30 ثانية.
يدعم Webhook لـ Railway و Polling للتجربة المحلية.
"""

import os
import math
import asyncio
import logging
from pathlib import Path
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from moviepy.editor import VideoFileClip

# --- إعدادات التسجيل ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# --- ثوابت الإعداد ---
CHUNK_DURATION = 30  # مدة كل جزء بالثواني
TEMP_DIR = Path("temp_videos")
TEMP_DIR.mkdir(exist_ok=True)

# --- رسالة الترحيب وطريقة العمل ---
WELCOME_MSG = (
    "👋 أهلاً بك في بوت تقسيم الفيديو!\n\n"
    "📌 *طريقة العمل:*\n"
    "1️⃣ أرسل أي فيديو للبوت.\n"
    "2️⃣ سيقوم بتقسيمه تلقائياً إلى أجزاء مدة كل جزء 30 ثانية.\n"
    "3️⃣ سيتم إرسال الأجزاء لك كفيديوهات، أو كملفات إذا تجاوز الحجم 50 ميجا.\n\n"
    "⚙️ ملاحظات: المعالجة قد تستغرق بضع دقائق حسب طول الفيديو.\n"
    "📩 لأي استفسار أو دعم، تواصل مع المطور."
)

# --- دوال الردود ---
async def send_welcome(update: Update):
    """إرسال رسالة الترحيب للمستخدم"""
    await update.message.reply_text(WELCOME_MSG, parse_mode="Markdown")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /start"""
    await send_welcome(update)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الرد على أي رسالة نصية برسالة الترحيب"""
    await send_welcome(update)

# --- دالة معالجة وتقسيم الفيديو ---
async def process_video(user_id: int, chat_id: int, msg_id: int, input_path: str, bot):
    """تقسيم الفيديو إلى أجزاء وإرسالها"""
    try:
        # تشغيل المعالجة الثقيلة في Thread منفصل لعدم حظر البوت
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
        
        # تحديث رسالة الحالة
        await bot.edit_message_text(chat_id, msg_id, f"✅ تم التقسيم إلى {parts} أجزاء. جاري الإرسال...")

        # إرسال الأجزاء واحداً تلو الآخر
        for i, path in enumerate(chunk_paths, 1):
            caption = f"🎬 الجزء {i} من {parts}"
            try:
                # محاولة الإرسال كفيديو (حد تلغرام 50 ميجا)
                with open(path, "rb") as f:
                    await bot.send_video(chat_id, video=f, caption=caption)
            except Exception:
                # إذا فشل، إرسال كملف (يدعم حتى 2 جيجا)
                with open(path, "rb") as f:
                    await bot.send_document(chat_id, document=f, caption=f"{caption} (ملف)")
            # حذف الملف المؤقت بعد الإرسال
            path.unlink(missing_ok=True)

        await bot.edit_message_text(chat_id, msg_id, "🎉 تم إرسال جميع الأجزاء بنجاح!")

    except Exception as e:
        logger.error(f"Error processing video: {e}")
        try:
            await bot.edit_message_text(chat_id, msg_id, f"❌ خطأ: {str(e)[:100]}")
        except Exception:
            pass
    finally:
        # تنظيف الملف الأصلي
        Path(input_path).unlink(missing_ok=True)

# --- معالج استقبال الفيديو ---
async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """استقبال الفيديو وبدء المعالجة"""
    msg = await update.message.reply_text("⏳ جاري التحميل والمعالجة... يرجى الانتظار.")
    
    video = update.message.video
    file = await video.get_file()
    input_path = TEMP_DIR / f"{update.effective_user.id}_{video.file_unique_id}.mp4"
    
    await file.download_to_drive(str(input_path))
    
    # بدء المعالجة في الخلفية دون حظر البوت
    asyncio.create_task(process_video(
        update.effective_user.id,
        update.effective_chat.id,
        msg.message_id,
        str(input_path),
        context.bot
    ))

# --- الدالة الرئيسية ---
def main():
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise ValueError("⚠️ متغير BOT_TOKEN غير موجود في البيئة!")

    # بناء التطبيق
    app = Application.builder().token(token).build()
    
    # تسجيل المعالجات
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VIDEO, handle_video))

    logger.info("🤖 بوت التقسيم يعمل الآن...")
    
    # --- تحديد وضع التشغيل: Webhook لـ Railway أو Polling للمحلي ---
    railway_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN")
    
    if railway_domain:
        # 🌐 وضع Webhook لـ Railway
        webhook_url = f"https://{railway_domain}/{token}"
        port = int(os.getenv("PORT", 8080))
        
        logger.info(f"🔗 تم تفعيل Webhook: {webhook_url}")
        logger.info(f"🚀 الاستماع على المنفذ: {port}")
        
        app.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path=token,
            webhook_url=webhook_url,
            allowed_updates=Update.ALL_TYPES
        )
    else:
        # 🔄 وضع Polling للتجربة المحلية
        logger.info("🔄 يعمل بنظام Polling (للتجربة المحلية)")
        app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
