# MongoDB-LLM-assistant\src\storage\config.py
"""
Storage Configuration Module
MongoDB ve dosya sistemi ayarları
"""
import os
from pathlib import Path
from typing import Optional
from datetime import timedelta

# Base paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
STORAGE_ROOT = PROJECT_ROOT / "storage"

# MongoDB Optional Control
MONGODB_ENABLED = os.getenv('MONGODB_ENABLED', 'true').lower() == 'true'

# MongoDB Config (Optional)
if MONGODB_ENABLED:
    MONGODB_CONFIG = {
        "connection_string": os.getenv('MONGODB_URI', 'mongodb://localhost:27017/'),
        "database": os.getenv('MONGODB_STORAGE_DB', 'anomaly_detection'),
        "collections": {
            "anomaly_history": "anomaly_history",
            "model_registry": "model_registry",
            "user_feedback": "user_feedback",
            "analysis_cache": "analysis_cache"
        },
        "options": {
            "serverSelectionTimeoutMS": 5000,
            "connectTimeoutMS": 10000,
            "maxPoolSize": 10,
            "minPoolSize": 1
        }
    }
else:
    MONGODB_CONFIG = None

# File Storage Configuration
FILE_STORAGE_CONFIG = {
    "base_path": STORAGE_ROOT,
    "subdirs": {
        "models": STORAGE_ROOT / "models",
        "exports": STORAGE_ROOT / "exports",
        "temp": STORAGE_ROOT / "temp",
        "backups": STORAGE_ROOT / "backups"
    },
    "max_file_size_mb": 100,
    "allowed_extensions": [".pkl", ".joblib", ".json", ".csv", ".log"]
}

# Retention Policies
RETENTION_POLICY = {
    "anomaly_history_days": 90,
    "model_versions_count": 10,
    "cache_ttl_hours": 24,
    "temp_files_hours": 6
}

# Storage Limits
STORAGE_LIMITS = {
    "max_anomaly_records": 1_000_000,
    "max_model_size_mb": 500,
    "max_cache_size_gb": 10,
    "batch_size": 1000
}

# Auto-save Configuration
AUTO_SAVE_CONFIG = {
    "enabled": True,
    "anomaly_threshold": 100,  # Auto-save after N anomalies
    "time_interval_minutes": 60,  # Auto-save every N minutes
    "compress": True,
    "format": "json"  # json, pickle, parquet
}

# Create directories if not exist
def initialize_storage_dirs():
    """Storage dizinlerini oluştur"""
    for path in FILE_STORAGE_CONFIG["subdirs"].values():
        path.mkdir(parents=True, exist_ok=True)
    print(f"✅ Storage directories initialized at: {STORAGE_ROOT}")

# Validate configuration
def validate_config():
    """Konfigürasyonu doğrula"""
    errors = []
    
    # MongoDB connection check
    if not MONGODB_CONFIG["connection_string"]:
        errors.append("MongoDB connection string is missing")
    
    # Directory permissions check
    if not os.access(STORAGE_ROOT, os.W_OK):
        errors.append(f"No write permission for {STORAGE_ROOT}")
    
    return errors

# Get config as dict
def get_config_dict():
    """Tüm konfigürasyonu dict olarak döndür"""
    return {
        "mongodb": MONGODB_CONFIG,
        "file_storage": FILE_STORAGE_CONFIG,
        "retention": RETENTION_POLICY,
        "limits": STORAGE_LIMITS,
        "auto_save": AUTO_SAVE_CONFIG
    }