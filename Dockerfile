FROM python:3.11-slim

# تثبيت ffmpeg و yt-dlp
RUN apt-get update && \
    apt-get install -y ffmpeg curl && \
    rm -rf /var/lib/apt/lists/*

# تثبيت yt-dlp
RUN curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -o /usr/local/bin/yt-dlp && \
    chmod a+rx /usr/local/bin/yt-dlp

# إنشاء مجلد العمل
WORKDIR /app

# نسخ الملفات
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py .
COPY .env .

# تشغيل البوت
CMD ["python", "bot.py"]
