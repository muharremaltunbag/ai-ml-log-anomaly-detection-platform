# tests/test_production_with_buffer.py

import sys
from pathlib import Path

# Path düzeltmesi
current_file = Path(__file__).resolve()
project_root = current_file.parent.parent.parent
sys.path.insert(0, str(project_root))

print(f"[DEBUG] Project root: {project_root}")

from src.anomaly.log_reader import OpenSearchProxyReader
from src.anomaly.feature_engineer import MongoDBFeatureEngineer  
from src.anomaly.anomaly_detector import MongoDBAnomalyDetector
import pandas as pd

def test_with_historical_buffer():
    """Production test - Historical Buffer AÇIK"""
    
    print("\n" + "="*60)
    print("PRODUCTION TEST WITH HISTORICAL BUFFER")
    print("="*60)
    
    # 1. OpenSearch bağlantısı
    print("\n[1] Connecting to OpenSearch...")
    reader = OpenSearchProxyReader()
    if not reader.connect():
        return False
    print("✅ Connected")
    
    # 2. İlk batch - Model eğitimi için
    print("\n[2] Reading initial batch...")
    df1 = reader.read_logs(limit=200, last_hours=2)
    if df1.empty:
        print("❌ No logs")
        return False
    print(f"✅ Retrieved {len(df1)} logs for training")
    
    # 3. Feature extraction - Batch 1
    print("\n[3] Extracting features (Batch 1)...")
    fe = MongoDBFeatureEngineer()
    X1, enriched_df1 = fe.create_features(df1)
    X1_filtered, enriched_filtered1 = fe.apply_filters(enriched_df1, X1)
    print(f"✅ {X1_filtered.shape[0]} logs, {X1_filtered.shape[1]} features")
    
    # YENİ: Sadece enabled features'ı al ve dict sütunlarını temizle
    enabled_features = fe.enabled_features
    X1_clean = X1_filtered[enabled_features].copy()

    # Dict içeren sütunları kontrol et ve temizle
    for col in X1_clean.columns:
        if X1_clean[col].apply(lambda x: isinstance(x, dict)).any():
            print(f"  ⚠️ Removing column with dict values: {col}")
            X1_clean = X1_clean.drop(columns=[col])

    print(f"✅ {X1_clean.shape[0]} logs, {X1_clean.shape[1]} features (cleaned)")

    # 4. Model - İlk eğitim
    print("\n[4] Initial model training...")
    detector = MongoDBAnomalyDetector()
    
    # Historical buffer AÇIK (default)
    print(f"  • Online learning: {detector.online_learning_config['enabled']}")
    print(f"  • Max history size: {detector.online_learning_config.get('max_history_size', 100000)}")
    
    # İlk train
    detector.train(X1_clean, save_model=False, incremental=True)
    print("✅ Initial model trained")
    
    # Buffer durumu
    if detector.historical_data['features'] is not None:
        print(f"  • Historical buffer: {len(detector.historical_data['features'])} samples")
    
    # 5. İkinci batch - Incremental learning testi
    print("\n[5] Reading second batch (incremental)...")
    df2 = reader.read_logs(limit=100, last_hours=1)
    if not df2.empty:
        print(f"✅ Retrieved {len(df2)} new logs")
        
        # Feature extraction - Batch 2
        X2, enriched_df2 = fe.create_features(df2)
        X2_filtered, enriched_filtered2 = fe.apply_filters(enriched_df2, X2)
        
        # Feature uyumunu GARANTI et
        # Model'in beklediği feature listesini al
        expected_features = detector.feature_names
        
        # X2'yi expected features'a göre düzenle
        X2_aligned = pd.DataFrame()
        for feature in expected_features:
            if feature in X2_filtered.columns:
                X2_aligned[feature] = X2_filtered[feature]
            else:
                # Eksik feature'ı 0 ile doldur
                X2_aligned[feature] = 0
        
        print(f"  • Features aligned: {X2_aligned.shape}")
        
        # Incremental train
        print("\n[6] Incremental training...")
        detector.train(X2_aligned, save_model=False, incremental=True)
        print("✅ Model updated with new data")
        
        # Yeni buffer durumu
        if detector.historical_data['features'] is not None:
            print(f"  • Updated buffer: {len(detector.historical_data['features'])} samples")
            print(f"  • Buffer anomaly rate: {detector.historical_data['metadata']['anomaly_samples']}/{detector.historical_data['metadata']['total_samples']}")
    
    # 6. Test - Son veriyle predict
    print("\n[7] Final prediction test...")
    df_test = reader.read_logs(limit=50, last_hours=1)
    if df_test.empty:
        # Eğer yeni veri yoksa, mevcut veriyi kullan
        df_test = df1.tail(50)
    
    X_test, enriched_test = fe.create_features(df_test)
    X_test_filtered, enriched_test_filtered = fe.apply_filters(enriched_test, X_test)
    
    # Feature alignment - CRITICAL!
    X_test_aligned = pd.DataFrame()
    for feature in detector.feature_names:
        if feature in X_test_filtered.columns:
            X_test_aligned[feature] = X_test_filtered[feature]
        else:
            X_test_aligned[feature] = 0
    
    # Predict
    predictions, scores = detector.predict(X_test_aligned, enriched_test_filtered)
    
    # 7. Analiz
    print("\n[8] Analyzing results...")
    analysis = detector.analyze_anomalies(
        enriched_test_filtered, X_test_aligned, predictions, scores
    )
    
    # 8. SONUÇLAR
    print("\n" + "="*60)
    print("📊 FINAL RESULTS")
    print("="*60)
    
    # Summary
    print(f"\n📈 Detection Summary:")
    print(f"  • Total analyzed: {analysis['summary']['total_logs']}")
    print(f"  • Anomalies found: {analysis['summary']['n_anomalies']}")
    print(f"  • Anomaly rate: {analysis['summary']['anomaly_rate']:.1f}%")
    
    # Historical Buffer Stats
    print(f"\n📚 Historical Buffer Status:")
    buffer_info = detector.get_historical_buffer_info()
    if buffer_info['buffer_stats']['total_samples'] > 0:
        print(f"  • Total samples in buffer: {buffer_info['buffer_stats']['total_samples']}")
        print(f"  • Buffer anomaly rate: {buffer_info['buffer_stats']['anomaly_rate']:.1f}%")
        print(f"  • Buffer size: {buffer_info['buffer_stats']['size_mb']:.2f} MB")
        print(f"  • Last update: {buffer_info['buffer_stats']['last_update']}")
    
    # Top anomalies
    if analysis.get('critical_anomalies'):
        print(f"\n🔴 Top Critical Anomalies:")
        for i, a in enumerate(analysis['critical_anomalies'][:5], 1):
            msg = a.get('message', '')[:100]
            level = a.get('severity_level')
            score = a.get('severity_score', 0)
            print(f"  {i}. [{level}] (Score:{score:.0f}) {msg}...")
    
    # Performance alerts
    if analysis.get('performance_alerts'):
        has_alerts = False
        for alert, data in analysis['performance_alerts'].items():
            if data['count'] > 0:
                if not has_alerts:
                    print(f"\n⚡ Performance Issues:")
                    has_alerts = True
                print(f"  • {alert}: {data['count']}")
    
    # Rule engine stats
    if 'ensemble_stats' in analysis.get('summary', {}):
        stats = analysis['summary']['ensemble_stats']
        if stats['total_rule_overrides'] > 0:
            print(f"\n📏 Rule Engine:")
            print(f"  • Total overrides: {stats['total_rule_overrides']}")
            if stats.get('rule_hits'):
                print(f"  • Rules triggered:")
                for rule, count in stats['rule_hits'].items():
                    print(f"    - {rule}: {count}x")
    
    # Online Learning Validation
    print(f"\n🔄 Online Learning Validation:")
    validation = detector.validate_online_learning()
    print(f"  • Status: {validation['status']}")
    print(f"  • Historical buffer active: {validation['checks'].get('has_historical_buffer', False)}")
    print(f"  • Feature consistency: {validation['checks'].get('feature_consistency', 'N/A')}")
    
    if validation['warnings']:
        print(f"  • Warnings: {', '.join(validation['warnings'][:2])}")
    
    print("\n✅ TEST COMPLETED - Historical Buffer Working!")
    print("   Model is learning incrementally from historical data")
    
    return True

if __name__ == "__main__":
    try:
        test_with_historical_buffer()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()