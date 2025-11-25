import sys
import os
from pathlib import Path

# Root dizini ekle
root_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(root_dir))

from src.anomaly.log_reader import OpenSearchProxyReader
from src.anomaly.feature_engineer import MongoDBFeatureEngineer
from src.anomaly.anomaly_detector import MongoDBAnomalyDetector  # ✅ DOĞRU CLASS ADI

print("=" * 50)
print("ML MODEL TEST - Anomaly Detection Pipeline")
print("=" * 50)

try:
    # 1. Veri hazırlama
    print("\n[1] Veri Hazırlama...")
    reader = OpenSearchProxyReader()
    connected = reader.connect()
    
    if not connected:
        print("❌ OpenSearch bağlantısı başarısız!")
        exit(1)
    
    df = reader.read_logs(limit=5000, last_hours=2)
    print(f"✅ {len(df)} log çekildi")

    # 2. Feature engineering
    print("\n[2] Feature Engineering...")
    engineer = MongoDBFeatureEngineer()
    X, enriched_df = engineer.create_features(df)
    print(f"✅ {X.shape} feature matrix oluşturuldu")

    # 3. Model initialization
    print("\n[3] Model Initialization...")
    detector = MongoDBAnomalyDetector()
    
    # Model yükleme veya eğitme
    model_exists = detector.load_model()
    if model_exists:
        print("✅ Mevcut model yüklendi")
        print(f"   - Feature sayısı: {len(detector.feature_names)}")
        print(f"   - Historical buffer: {detector.historical_data['metadata']['total_samples']} samples")
    else:
        print("⚠️ Model bulunamadı, yeni model eğitiliyor...")
        detector.train(X)
        print("✅ Model eğitildi ve kaydedildi")

    # 4. Anomaly prediction
    print("\n[4] Anomaly Detection...")
    predictions, anomaly_scores = detector.predict(X, df=enriched_df)
    anomalies = enriched_df[predictions == -1]

    print(f"\n[5] SONUÇLAR:")
    print(f"✅ Toplam log: {len(df)}")
    print(f"✅ Anomali sayısı: {len(anomalies)} ({len(anomalies)/len(df)*100:.1f}%)")
    
    # Contamination rate kontrolü
    expected_rate = detector.model_config['parameters'].get('contamination', 0.03) * 100
    actual_rate = len(anomalies)/len(df)*100
    print(f"✅ Beklenen anomali oranı: %{expected_rate:.1f}")
    print(f"✅ Gerçek anomali oranı: %{actual_rate:.1f}")

    # 6. Detaylı analiz
    print("\n[6] Anomaly Analysis...")
    analysis = detector.analyze_anomalies(enriched_df, X, predictions, anomaly_scores)
    
    # Summary stats
    if 'summary' in analysis:
        summary = analysis['summary']
        print(f"\n[7] Analiz Özeti:")
        print(f"   - Score Range: [{summary['score_range']['min']:.3f}, {summary['score_range']['max']:.3f}]")
        print(f"   - Mean Score: {summary['score_range']['mean']:.3f}")
    
    # Kritik anomaliler
    if 'critical_anomalies' in analysis:
        critical = analysis['critical_anomalies'][:5]
        if critical:
            print(f"\n[8] İlk 5 Kritik Anomali:")
            for i, anomaly in enumerate(critical, 1):
                print(f"\n   {i}. Anomali:")
                print(f"      Severity Score: {anomaly.get('severity_score', 0):.1f}")
                print(f"      Level: {anomaly.get('severity_level', 'N/A')}")
                print(f"      Component: {anomaly.get('component', 'N/A')}")
                msg = anomaly.get('message', 'N/A')
                if msg and len(msg) > 100:
                    msg = msg[:100] + "..."
                print(f"      Message: {msg}")
    
    # Performance alerts
    if 'performance_alerts' in analysis:
        alerts = analysis['performance_alerts']
        if alerts:
            print(f"\n[9] Performance Alerts:")
            for alert_type, alert_data in alerts.items():
                print(f"   - {alert_type}: {alert_data['count']} cases")
    
    # Security alerts
    if 'security_alerts' in analysis:
        sec_alerts = analysis['security_alerts']
        active_alerts = {k: v for k, v in sec_alerts.items() if v.get('count', 0) > 0}
        if active_alerts:
            print(f"\n[10] Security Alerts:")
            for alert_type, alert_data in active_alerts.items():
                print(f"   - {alert_type}: {alert_data['count']} cases")
    
    # Model bilgileri
    print(f"\n[11] Model Info:")
    model_info = detector.get_model_info()
    print(f"   Model Type: {model_info['model_type']}")
    print(f"   Parameters:")
    for param, value in model_info['parameters'].items():
        print(f"      - {param}: {value}")
    
    # Online learning durumu
    if detector.online_learning_config.get('enabled', False):
        print(f"\n[12] Online Learning:")
        print(f"   Status: ENABLED")
        print(f"   History Retention: {detector.online_learning_config.get('history_retention', 'none')}")
        if detector.historical_data['features'] is not None:
            buffer_size_mb = detector.historical_data['features'].memory_usage(deep=True).sum() / 1024 / 1024
            print(f"   Buffer Size: {buffer_size_mb:.2f} MB")
    
    print("\n✅ ML MODEL TESTİ BAŞARILI!")
    
    # Bonus: Model performans metrikleri
    if hasattr(detector, 'rule_stats'):
        print(f"\n[13] Rule Engine Stats:")
        print(f"   Total Rule Overrides: {detector.rule_stats['total_overrides']}")
        if detector.rule_stats['rule_hits']:
            print(f"   Rule Hits:")
            for rule, count in detector.rule_stats['rule_hits'].items():
                print(f"      - {rule}: {count} hits")
    
except Exception as e:
    print(f"\n❌ TEST HATASI: {e}")
    import traceback
    traceback.print_exc()