import os
import glob
import shutil
from pymongo import MongoClient
import logging

# Log ayarları
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("SystemCleanup")

def clean_file_system():
    """Disk üzerindeki tüm model ve cache dosyalarını temizler"""
    logger.info("--- 🗑️  DOSYA SİSTEMİ TEMİZLİĞİ BAŞLIYOR ---")
    
    # Silinecek desenler ve klasörler
    targets = [
        "models/*.pkl",
        "models_backup_*/*.pkl",
        "storage/models/*.pkl",
        "storage/backups/*.pkl",
        "storage/exports/anomaly/*.json" # Eski analiz çıktılarını da temizleyelim
    ]

    deleted_count = 0
    for pattern in targets:
        # Recursive globbing için ** kullanımı gerekebilir ama şimdilik düz path
        files = glob.glob(pattern, recursive=True)
        for f in files:
            try:
                os.remove(f)
                logger.info(f"Silindi: {f}")
                deleted_count += 1
            except Exception as e:
                logger.error(f"Silinemedi: {f} - {e}")
    
    logger.info(f"✅ Dosya temizliği tamamlandı. Toplam {deleted_count} dosya silindi.")

def clean_database():
    """MongoDB üzerindeki analiz geçmişini temizler"""
    logger.info("--- 🗄️  VERİTABANI TEMİZLİĞİ BAŞLIYOR ---")
    
    try:
        # Local MongoDB bağlantısı (Config'den okumak yerine standart port)
        client = MongoClient("mongodb://localhost:27017/")
        db_name = "anomaly_detection"
        
        if db_name in client.list_database_names():
            db = client[db_name]
            
            # anomaly_results koleksiyonunu temizle
            result = db.anomaly_results.delete_many({})
            logger.info(f"🗑️  'anomaly_results' koleksiyonundan {result.deleted_count} kayıt silindi.")
            
            # İsteğe bağlı: model_registry temizliği
            result_registry = db.model_registry.delete_many({})
            logger.info(f"🗑️  'model_registry' koleksiyonundan {result_registry.deleted_count} kayıt silindi.")
            
        else:
            logger.warning(f"Veritabanı '{db_name}' bulunamadı, zaten temiz olabilir.")
            
    except Exception as e:
        logger.error(f"Veritabanı temizliği sırasında hata: {e}")

if __name__ == "__main__":
    print("⚠️  UYARI: Bu işlem tüm ML modellerini ve geçmiş analizleri silecektir.")
    confirm = input("Devam etmek istiyor musunuz? (e/h): ")
    
    if confirm.lower() == 'e':
        clean_file_system()
        clean_database()
        print("\n✨ SİSTEM SIFIRLANDI VE TESTE HAZIR ✨")
    else:
        print("İşlem iptal edildi.")