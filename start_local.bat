@echo off
cls
echo ==========================================
echo   MONGODB ANOMALY DETECTION SYSTEM
echo ==========================================
echo.
echo MongoDB: AKTIF (anomaly_app kullanicisi)
echo Database: anomaly_detection
echo.
echo FastAPI baslatiliyor...
echo.

python -m uvicorn web_ui.api:app --reload --host 0.0.0.0 --port 8000

pause