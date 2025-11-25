# test_ML_Pipeline_v2.py - Tamamen düzeltilmiş versiyon
"""
ML Pipeline End-to-End Test v2
Doğru method isimleri ile
"""
import sys
import os
from pathlib import Path
import pandas as pd
import numpy as np
from datetime import datetime
import json

# Path setup
current_dir = Path(__file__).parent
project_root = current_dir.parent.parent
sys.path.insert(0, str(project_root))

def test_feature_engineering():
    """Feature Engineering Pipeline Testi"""
    print("\n" + "="*60)
    print("FEATURE ENGINEERING TEST")
    print("="*60)
    
    try:
        from src.anomaly.log_reader import OpenSearchProxyReader
        from src.anomaly.feature_engineer import MongoDBFeatureEngineer
        
        # 1. Log okuma
        print("→ OpenSearch'e bağlanılıyor...")
        reader = OpenSearchProxyReader()
        if not reader.connect():
            print("❌ OpenSearch bağlantısı başarısız!")
            return None, None
        
        # Production host'lardan log oku
        test_hosts = [
            "ecaztrdbmng007.lcwecomtr.com",  # ecommerce
            "ecaztrdbmng010.lcwecomtr.com",  # ecommercelog
            "lcwmongodb01n1.lcwaikiki.local" # lcw production
        ]
        
        all_logs = []
        for host in test_hosts:
            print(f"\n→ {host} logları okunuyor...")
            df = reader.read_logs(limit=500, last_hours=24, host_filter=host)
            if not df.empty:
                print(f"   ✅ {len(df)} log okundu")
                all_logs.append(df)
            else:
                print(f"   ⚠️ Log bulunamadı, daha geniş aralık deneniyor...")
                df = reader.read_logs(limit=500, last_hours=72, host_filter=host)
                if not df.empty:
                    print(f"   ✅ {len(df)} log okundu (72 saat)")
                    all_logs.append(df)
        
        if not all_logs:
            print("❌ Hiç log okunamadı!")
            return None, None
        
        combined_df = pd.concat(all_logs, ignore_index=True)
        print(f"\n✅ Toplam {len(combined_df)} log birleştirildi")
        
        # 2. Feature Engineering
        print("\n" + "-"*40)
        print("→ Feature Engineering başlatılıyor...")
        
        engineer = MongoDBFeatureEngineer()
        X, enriched_df = engineer.create_features(combined_df)
        
        print(f"✅ Feature extraction tamamlandı!")
        print(f"   • Input shape: {combined_df.shape}")
        print(f"   • Feature matrix: {X.shape}")
        print(f"   • Feature count: {X.shape[1]}")
        
        # Feature istatistikleri
        stats = engineer.get_feature_statistics(X)
        
        print("\n📊 Kritik Feature İstatistikleri:")
        critical_features = [
            'is_slow_query', 'is_collscan', 'is_auth_failure', 
            'is_drop_operation', 'is_out_of_memory', 'is_fatal'
        ]
        
        for feat in critical_features:
            if feat in stats['binary_features']:
                count = stats['binary_features'][feat]['count']
                pct = stats['binary_features'][feat]['percentage']
                if count > 0:
                    print(f"   🔴 {feat}: {count} ({pct:.2f}%)")
                else:
                    print(f"   🟢 {feat}: 0")
        
        # Filtreleme
        X_filtered, enriched_filtered = engineer.apply_filters(enriched_df, X)
        reduction = (1 - len(X_filtered)/len(X)) * 100
        print(f"\n✅ Filtreleme: %{reduction:.1f} normal log filtrelendi")
        print(f"   Kalan anomali adayı: {len(X_filtered)} log")
        
        # DEBUG: Feature matrix tiplerini kontrol et
        print(f"\n📊 Feature Matrix Kontrolü:")
        print(f"   Shape: {X_filtered.shape}")
        print(f"   Dtypes: {X_filtered.dtypes.value_counts().to_dict()}")
        non_numeric = X_filtered.select_dtypes(exclude=['int64', 'float64']).columns.tolist()
        if non_numeric:
            print(f"   ⚠️ Non-numeric kolonlar: {non_numeric}")
            # Non-numeric kolonları temizle
            X_filtered = X_filtered.select_dtypes(include=['int64', 'float64'])
            print(f"   ✅ Temizlendi, yeni shape: {X_filtered.shape}")
        
        return X_filtered, enriched_filtered
        
    except Exception as e:
        print(f"❌ Feature engineering hatası: {e}")
        import traceback
        traceback.print_exc()
        return None, None

def test_anomaly_detection(X, enriched_df):
    """Anomaly Detection Pipeline Testi"""
    print("\n" + "="*60)
    print("ANOMALY DETECTION TEST")
    print("="*60)
    
    try:
        from src.anomaly.anomaly_detector import MongoDBAnomalyDetector
        
        # Anomaly detector oluştur
        detector = MongoDBAnomalyDetector()
        
        print("→ Anomaly detection başlatılıyor...")
        print(f"   Input: {X.shape[0]} log, {X.shape[1]} feature")
        
        # ÖNEMLİ: Önce modeli eğit
        print("\n→ Model training başlatılıyor...")
        training_stats = detector.train(X, save_model=False)
        print(f"✅ Model eğitimi tamamlandı!")
        print(f"   • {training_stats['n_samples']} sample")
        print(f"   • {training_stats['n_features']} feature")
        print(f"   • {training_stats['training_time_seconds']:.2f} saniye")
        
        # Şimdi predict yap
        print("\n→ Anomaly prediction başlatılıyor...")
        predictions, anomaly_scores = detector.predict(X, enriched_df)
        
        # Analiz yap
        print("→ Anomaly analizi yapılıyor...")
        analysis = detector.analyze_anomalies(enriched_df, X, predictions, anomaly_scores)
        
        # Sonuçları göster
        print(f"\n🔍 ANOMALY DETECTION SONUÇLARI:")
        print(f"   • Toplam log: {analysis['summary']['total_logs']}")
        print(f"   • Tespit edilen anomali: {analysis['summary']['n_anomalies']}")
        print(f"   • Anomali oranı: %{analysis['summary']['anomaly_rate']:.2f}")
        
        # Score dağılımı
        print(f"\n📊 Anomaly Score Dağılımı:")
        print(f"   • Min: {analysis['summary']['score_range']['min']:.3f}")
        print(f"   • Max: {analysis['summary']['score_range']['max']:.3f}")
        print(f"   • Mean: {analysis['summary']['score_range']['mean']:.3f}")
        
        # Severity dağılımı
        if 'severity_distribution' in analysis:
            print(f"\n📊 Severity Dağılımı:")
            for level, count in analysis['severity_distribution'].items():
                if count > 0:
                    print(f"   {level}: {count}")
        
        # Critical anomaliler
        if 'critical_anomalies' in analysis and analysis['critical_anomalies']:
            print(f"\n🔴 Top 5 Kritik Anomali:")
            for i, anomaly in enumerate(analysis['critical_anomalies'][:5], 1):
                msg = anomaly['message'][:100] + "..." if len(anomaly['message']) > 100 else anomaly['message']
                score = anomaly.get('severity_score', anomaly.get('anomaly_score', 0))
                level = anomaly.get('severity_level', 'UNKNOWN')
                print(f"   {i}. [{level}] Score:{score:.2f} - {msg}")
        
        # Performance alerts
        if 'performance_alerts' in analysis:
            print(f"\n⚠️ Performance Alerts:")
            for alert_type, alert_data in analysis['performance_alerts'].items():
                if isinstance(alert_data, dict) and 'count' in alert_data:
                    print(f"   • {alert_type}: {alert_data['count']} incidents")
        
        return analysis
        
    except Exception as e:
        print(f"❌ Anomaly detection hatası: {e}")
        import traceback
        traceback.print_exc()
        return None

def test_model_persistence():
    """Model Save/Load Testi"""
    print("\n" + "="*60)
    print("MODEL PERSISTENCE TEST")
    print("="*60)
    
    try:
        from src.anomaly.anomaly_detector import MongoDBAnomalyDetector
        import tempfile
        
        detector = MongoDBAnomalyDetector()
        
        # Dummy data ile model eğit
        print("→ Test modeli oluşturuluyor...")
        X_dummy = pd.DataFrame(np.random.randn(100, 36), 
                               columns=[f'feature_{i}' for i in range(36)])
        
        print("→ Model eğitiliyor...")
        detector.train(X_dummy, save_model=False)
        
        # Model kaydet
        with tempfile.NamedTemporaryFile(suffix='.pkl', delete=False) as tmp:
            print(f"→ Model kaydediliyor: {tmp.name}")
            saved_path = detector.save_model(tmp.name)
            
            # Model yükle
            print("→ Model yükleniyor...")
            detector2 = MongoDBAnomalyDetector()
            success = detector2.load_model(tmp.name)
            
            if success:
                # Test prediction
                test_pred1, _ = detector.predict(X_dummy[:5])
                test_pred2, _ = detector2.predict(X_dummy[:5])
                
                if np.array_equal(test_pred1, test_pred2):
                    print("✅ Model save/load başarılı!")
                    print(f"   • Model dosya boyutu: {Path(tmp.name).stat().st_size / 1024:.2f} KB")
                    return True
                else:
                    print("❌ Model save/load başarısız - tahminler uyuşmuyor")
                    return False
            else:
                print("❌ Model yüklenemedi")
                return False
                
    except Exception as e:
        print(f"❌ Model persistence hatası: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Ana test fonksiyonu"""
    print("\n" + "="*60)
    print("MongoDB ML Pipeline - End-to-End Test v2")
    print("Test Tarihi:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("="*60)
    
    # Test 1: Feature Engineering
    X, enriched_df = test_feature_engineering()
    if X is None:
        print("\n❌ Feature engineering başarısız!")
        return False
    
    # Test 2: Anomaly Detection
    analysis = test_anomaly_detection(X, enriched_df)
    if analysis is None:
        print("\n❌ Anomaly detection başarısız!")
        return False
    
    # Test 3: Model Persistence
    model_test = test_model_persistence()
    
    # Sonuç
    print("\n" + "="*60)
    print("ML PIPELINE TEST SONUCU")
    print("="*60)
    
    success_count = 0
    if X is not None and not X.empty:
        print("✅ Feature Engineering: PASS")
        success_count += 1
    else:
        print("❌ Feature Engineering: FAIL")
    
    if analysis is not None:
        print("✅ Anomaly Detection: PASS")
        success_count += 1
    else:
        print("❌ Anomaly Detection: FAIL")
    
    if model_test:
        print("✅ Model Persistence: PASS")
        success_count += 1
    else:
        print("❌ Model Persistence: FAIL")
    
    print(f"\n📊 Toplam: {success_count}/3 test başarılı")
    
    # Özet istatistikler
    if analysis:
        print(f"\n📈 ÖZET İSTATİSTİKLER:")
        print(f"   • İşlenen log sayısı: {analysis['summary']['total_logs']}")
        print(f"   • Tespit edilen anomali: {analysis['summary']['n_anomalies']}")
        print(f"   • Anomali oranı: %{analysis['summary']['anomaly_rate']:.2f}")
        if 'ensemble_stats' in analysis.get('summary', {}):
            print(f"   • Rule overrides: {analysis['summary']['ensemble_stats']['total_rule_overrides']}")
    
    if success_count == 3:
        print("\n🎉 TÜM TESTLER BAŞARILI - ML PIPELINE PRODUCTION READY!")
        return True
    else:
        print("\n⚠️ Bazı testler başarısız, kontrol gerekiyor")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)