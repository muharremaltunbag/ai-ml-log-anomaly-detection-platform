# test_ml_training.py - GERÇEK EĞİTİM TESTİ
import sys
import os
from pathlib import Path
import time

# Root dizini ekle
root_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(root_dir))

from src.anomaly.log_reader import OpenSearchProxyReader
from src.anomaly.feature_engineer import MongoDBFeatureEngineer
from src.anomaly.anomaly_detector import MongoDBAnomalyDetector

print("=" * 50)
print("ML MODEL TRAINING TEST - Sıfırdan Eğitim")
print("=" * 50)

try:
    # 1. Veri hazırlama
    print("\n[1] Training verisi hazırlanıyor...")
    reader = OpenSearchProxyReader()
    reader.connect()
    df = reader.read_logs(limit=10000, last_hours=24)  # Daha fazla veri
    print(f"✅ {len(df)} log çekildi")

    # 2. Feature engineering
    print("\n[2] Feature extraction...")
    engineer = MongoDBFeatureEngineer()
    start_time = time.time()
    X, enriched_df = engineer.create_features(df)
    feature_time = time.time() - start_time
    print(f"✅ {X.shape} feature matrix oluşturuldu ({feature_time:.2f} saniye)")

    # 3. Yeni model instance (ESKİ MODEL YÜKLEME!)
    print("\n[3] YENİ Model Instance Oluşturuluyor...")
    detector = MongoDBAnomalyDetector()
    
    # Eski modeli temizle
    if Path("models/isolation_forest.pkl").exists():
        print("⚠️ Eski model bulundu, yedekleniyor...")
        import shutil
        backup_path = f"models/isolation_forest_backup_{time.strftime('%Y%m%d_%H%M%S')}.pkl"
        shutil.copy("models/isolation_forest.pkl", backup_path)
        print(f"✅ Yedeklendi: {backup_path}")
    
    # 4. GERÇEK MODEL EĞİTİMİ
    print("\n[4] MODEL EĞİTİMİ BAŞLIYOR...")
    print(f"   - Training samples: {X.shape[0]}")
    print(f"   - Features: {X.shape[1]}")
    print(f"   - Contamination: {detector.model_config['parameters']['contamination']}")
    
    # Eğitim zamanını ölç
    start_train = time.time()
    training_stats = detector.train(X, save_model=True)
    train_time = time.time() - start_train
    
    print(f"\n✅ Model eğitimi tamamlandı!")
    print(f"   - Eğitim süresi: {train_time:.2f} saniye")
    print(f"   - Model tipi: {training_stats['model_type']}")
    print(f"   - Sample/saniye: {X.shape[0]/train_time:.0f}")
    
    # 5. Model doğrulama
    print("\n[5] Model Doğrulama...")
    predictions, scores = detector.predict(X, df=enriched_df)
    
    anomaly_count = (predictions == -1).sum()
    anomaly_rate = anomaly_count / len(predictions) * 100
    
    print(f"✅ Anomali tespiti:")
    print(f"   - Toplam: {len(predictions)}")
    print(f"   - Anomali: {anomaly_count}")
    print(f"   - Oran: %{anomaly_rate:.2f}")
    print(f"   - Hedef: %{detector.model_config['parameters']['contamination']*100:.1f}")
    
    # 6. Model boyutu kontrolü
    model_path = Path("models/isolation_forest.pkl")
    if model_path.exists():
        model_size_mb = model_path.stat().st_size / (1024 * 1024)
        print(f"\n✅ Model kaydedildi:")
        print(f"   - Dosya: {model_path}")
        print(f"   - Boyut: {model_size_mb:.2f} MB")
    
    # 7. Feature importance (opsiyonel, uzun sürebilir)
    print("\n[6] Feature Importance Hesaplanıyor (bu biraz sürebilir)...")
    start_importance = time.time()
    importance = detector.calculate_feature_importance(X, sample_size=min(1000, len(X)))
    importance_time = time.time() - start_importance
    
    print(f"✅ Feature importance hesaplandı ({importance_time:.2f} saniye)")
    print("\nEn önemli 5 feature:")
    for i, (feat, score) in enumerate(list(importance.items())[:5], 1):
        print(f"   {i}. {feat}: {score:.4f}")
    
    # ÖZET
    print("\n" + "="*50)
    print("TEST ÖZETI")
    print("="*50)
    print(f"Toplam süre: {time.time() - start_time:.2f} saniye")
    print(f"- Veri okuma: ~5 saniye")
    print(f"- Feature engineering: {feature_time:.2f} saniye")
    print(f"- Model eğitimi: {train_time:.2f} saniye")
    print(f"- Feature importance: {importance_time:.2f} saniye")
    
    # Performans beklentileri
    print("\n📊 PERFORMANS DEĞERLENDİRMESİ:")
    if train_time < 1:
        print("⚠️ Model ÇOK HIZLI eğitildi - muhtemelen cached/loaded")
    elif train_time < 5:
        print("✅ Normal eğitim süresi (1-5 saniye arası)")
    elif train_time < 30:
        print("✅ Büyük veri seti için normal süre")
    else:
        print("⚠️ Eğitim uzun sürdü, optimizasyon gerekebilir")
        
except Exception as e:
    print(f"\n❌ TEST HATASI: {e}")
    import traceback
    traceback.print_exc()