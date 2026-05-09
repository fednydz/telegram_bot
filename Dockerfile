FROM python:3.10-slim

# تثبيت FFmpeg وتنظيف الـ cache لتقليل حجم الصورة
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# نسخ ملف المتطلبات أولاً للاستفادة من Docker cache
COPY requirements.txt .

# تثبيت المكتبات
RUN pip install --no-cache-dir -r requirements.txt

# نسخ باقي الملفات (بما في ذلك logo.png و bot.py)
COPY . .

# التأكد من وجود ملف الشعار
RUN if [ ! -f logo.png ]; then \
      echo "⚠️ Warning: logo.png not found!"; \
    fi

CMD ["python", "bot.py"]
