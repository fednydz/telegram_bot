# استخدام صغة Python رسمية خفيفة
FROM python:3.9-slim

# 【 الخطوة السحرية 】 تثبيت ffmpeg داخل الحاوية
# هذا الأمر هو الذي كان مفقودًا ويقوم بإعداد المحرك.
RUN apt-get update && apt-get install -y ffmpeg && apt-get clean

# تعيين مجلد العمل داخل الحاوية
WORKDIR /app

# نسخ ملف المتطلبات وتثبيت مكتبات بايثون (مثل aiogram, moviepy)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# نسخ باقي ملفات المشروع
COPY . .

# الأمر الذي يُشغّل البوت
CMD ["python", "bot.py"]
