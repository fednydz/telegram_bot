FROM python:3.10-slim

# تثبيت FFmpeg وتنظيف الـ cache لتقليل حجم الصورة
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# نسخ requirements أولاً للاستفادة من Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# نسخ باقي الملفات
COPY . .

CMD ["python", "bot.py"]
