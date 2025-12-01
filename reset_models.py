import os
import glob
import logging

# Logging ayarları
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def reset_all_models():
    """
    models/ klasöründeki tüm .pkl dosyalarını siler.
    Bu işlem, Scaler güncellemesi sonrası modellerin sıfırdan temiz veriye göre
    eğitilmesini sağlamak için gereklidir.
    """
    models_dir = "models"
    
    if not os.path.exists(models_dir):
        logger.warning(f"'{models_dir}' klasörü bulunamadı, silinecek model yok.")
        return

    # Tüm .pkl dosyalarını bul
    model_files = glob.glob(os.path.join(models_dir, "*.pkl"))
    
    if not model_files:
        logger.info("Silinecek model dosyası bulunamadı. Sistem zaten temiz.")
        return

    logger.info(f"Toplam {len(model_files)} adet eski model dosyası bulundu. Siliniyor...")
    
    deleted_count = 0
    for file_path in model_files:
        try:
            os.remove(file_path)
            logger.info(f"Silindi: {file_path}")
            deleted_count += 1
        except Exception as e:
            logger.error(f"Silinemedi: {file_path}. Hata: {e}")

    logger.info(f"TEMİZLİK TAMAMLANDI: {deleted_count} model silindi.")
    logger.info("Bir sonraki analizde modeller otomatik olarak 'Feature Scaling' ile yeniden eğitilecek.")

if __name__ == "__main__":
    reset_all_models()