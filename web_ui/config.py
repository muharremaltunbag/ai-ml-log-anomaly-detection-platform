# web_ui\config.py

"""Web UI Konfigürasyon Dosyası"""
import os
from dotenv import load_dotenv

load_dotenv()

# Web UI Ayarları
WEB_HOST = os.getenv("WEB_HOST", "127.0.0.1")
WEB_PORT = int(os.getenv("WEB_PORT", "8000"))

# Güvenlik
API_KEY = os.getenv("WEB_API_KEY", "")  # Set via WEB_API_KEY env var
MAX_QUERY_LENGTH = 10000
RATE_LIMIT_REQUESTS = 30
RATE_LIMIT_MINUTES = 1

# CORS ayarları
_extra_origins = os.getenv("CORS_ORIGINS", "")
ALLOWED_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
] + [o.strip() for o in _extra_origins.split(",") if o.strip()]