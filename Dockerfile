# LC Waikiki MongoDB LangChain Assistant - Dockerfile
# Python 3.11 base image (pandas/numpy için gerekli C kütüphaneleri içerir)
FROM python:3.11

# Maintainer bilgisi
LABEL maintainer="LC Waikiki BT Analitik Veritabanları Müdürlüğü"
LABEL description="MongoDB Anomaly DetectionAssistant API"

# Sistem bağımlılıklarını yükle
# gcc: Python C extension'ları için
# python3-dev: Python header dosyaları
# build-essential: Derleme araçları
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Çalışma dizinini ayarla
WORKDIR /app

# Requirements dosyasını kopyala (cache optimization için önce sadece bu)
COPY requirements.txt .

# Python bağımlılıklarını yükle
# --no-cache-dir: pip cache'i devre dışı bırak (image boyutunu küçült)
RUN pip install --no-cache-dir -r requirements.txt

# Uygulama dosyalarını kopyala
# src/ klasörü
COPY src/ ./src/

# config/ klasörü  
COPY config/ ./config/

# web_ui/ klasörü
COPY web_ui/ ./web_ui/

# Ana dosyalar
COPY main.py .

# models/ klasörü (eğer varsa)
COPY models/ ./models/

# Log ve output klasörlerini oluştur
RUN mkdir -p logs output temp_logs

# Güvenlik: root olmayan kullanıcı oluştur
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

# Kullanıcıya geç
USER appuser

# Port expose (FastAPI default)
EXPOSE 8000

# Healthcheck ekle
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/api/status || exit 1

# Environment variables
# Docker içinde 0.0.0.0 dinlemesi için
ENV WEB_HOST=0.0.0.0
ENV WEB_PORT=8000
ENV PYTHONPATH=/app

# Başlatma komutu
# Web API'yi başlat (CLI yerine)
CMD ["uvicorn", "web_ui.api:app", "--host", "0.0.0.0", "--port", "8000"]
