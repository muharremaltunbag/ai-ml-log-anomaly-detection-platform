# nuclear_cleanup.py
import os
import glob
import shutil
from pymongo import MongoClient
import logging

# Log ayarları
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("NuclearCleanup")

def nuke_file_system():
    """Dosya sistemindeki tüm kalıntıları temizler"""
    logger.info("--- ☢️  DOSYA SİSTEMİ TEMİZLENİYOR ---")
    
    patterns = [
        "models/*.pkl",
        "models_backup_*",
        "storage/models/*.pkl",
        "storage/backups/*",
        "storage/exports/anomaly/*.json",
        "logs/*.log",
        "output/*.json",
        "temp_logs/*",
        "__pycache__"
    ]

    for pattern in patterns:
        items = glob.glob(pattern, recursive=True)
        for item in items:
            try:
                if os.path.isfile(item):
                    os.remove(item)
                elif os.path.isdir(item):
                    shutil.rmtree(item)
                logger.info(f"Silindi: {item}")
            except Exception as e:
                logger.warning(f"Silinemedi: {item} - {e}")

def nuke_databases():
    """İlgili veritabanlarını KOMPLE siler (DROP DATABASE)"""
    logger.info("--- ☢️  VERİTABANLARI SİLİNİYOR (DROP) ---")
    
    try:
        client = MongoClient("mongodb://localhost:27017/")
        
        # Projenin kullanabileceği olası veritabanı isimleri
        # Loglardan ve kodlardan tespit edilen isimler
        target_dbs = [
            "anomaly_detection", 
            "lcw_assistant", 
            "mongodb_agent", 
            "admin_panel",
            "logs_db"
        ]
        
        existing_dbs = client.list_database_names()
        
        for db_name in target_dbs:
            if db_name in existing_dbs:
                logger.info(f"💥 Veritabanı Bulundu ve Yok Ediliyor: '{db_name}'")
                client.drop_database(db_name)
                logger.info(f"✅ '{db_name}' başarıyla silindi.")
            else:
                logger.info(f"ℹ️ '{db_name}' bulunamadı, temiz.")
                
    except Exception as e:
        logger.error(f"Veritabanı silme hatası: {e}")

if __name__ == "__main__":
    print("\n⚠️  DİKKAT: BU İŞLEM GERİ ALINAMAZ!")
    print("Bu script MongoDB'deki ilgili veritabanlarını (anomaly_detection vb.) tamamen silecektir.")
    confirm = input("Her şeyi silmek istiyor musunuz? (evet/hayir): ")
    
    if confirm.lower() == 'evet':
        nuke_file_system()
        nuke_databases()
        print("\n✨ SİSTEM FABRİKA AYARLARINA DÖNDÜ ✨")
        print("👉 Lütfen tarayıcınızda CTRL+F5 yapın ve LocalStorage'ı temizleyin.")
    else:
        print("İptal edildi.")