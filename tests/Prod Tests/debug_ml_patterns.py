# tests/debug_ml_patterns.py

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
import numpy as np

def debug_pattern_detection():
    """Pattern detection problemini debug et"""
    
    print("\n" + "="*60)
    print("ML PATTERN DETECTION DEBUG")
    print("="*60)
    
    # 1. Veri çek
    reader = OpenSearchProxyReader()
    reader.connect()
    df = reader.read_logs(limit=5000, last_hours=24)
    
    # 2. AUTH_FAIL loglarını bul
    auth_fail_mask = df['msg'].str.contains(
        r"Authentication failed|Unauthorized|Checking authorization failed", 
        case=False, na=False
    )
    auth_fail_logs = df[auth_fail_mask]
    print(f"\n📍 Found {len(auth_fail_logs)} AUTH_FAIL logs")
    
    if len(auth_fail_logs) > 0:
        print("Sample AUTH_FAIL messages:")
        for msg in auth_fail_logs['msg'].head(3):
            print(f"  - {msg[:100]}")
    
    # 3. SLOW_QUERY loglarını bul
    slow_query_mask = df['msg'].str.contains(
        r"Slow query|durationMillis:[1-9]\d{3}", 
        case=False, na=False, regex=True
    )
    slow_query_logs = df[slow_query_mask]
    print(f"\n📍 Found {len(slow_query_logs)} SLOW_QUERY logs")
    
    if len(slow_query_logs) > 0:
        print("Sample SLOW_QUERY messages:")
        for msg in slow_query_logs['msg'].head(3):
            print(f"  - {msg[:100]}")
    
    # 4. Feature engineering
    fe = MongoDBFeatureEngineer()
    X, enriched_df = fe.create_features(df)
    
    # 5. AUTH_FAIL feature kontrolü
    print("\n🔍 AUTH_FAIL Feature Check:")
    print(f"  is_auth_failure sum: {enriched_df['is_auth_failure'].sum()}")
    print(f"  Manual pattern count: {auth_fail_mask.sum()}")
    
    # Neden fark var?
    if auth_fail_mask.sum() != enriched_df['is_auth_failure'].sum():
        print("  ⚠️ MISMATCH! Checking why...")
        
        # Auth fail olan ama feature'da yakalanmayan loglar
        missed_auth = auth_fail_mask & (enriched_df['is_auth_failure'] == 0)
        if missed_auth.any():
            print(f"  ❌ {missed_auth.sum()} AUTH_FAIL logs missed by feature")
            print("  Sample missed messages:")
            for msg in df[missed_auth]['msg'].head(2):
                print(f"    - {msg[:100]}")
    
    # 6. SLOW_QUERY feature kontrolü  
    print("\n🔍 SLOW_QUERY Feature Check:")
    print(f"  is_slow_query sum: {enriched_df['is_slow_query'].sum()}")
    print(f"  Manual pattern count: {slow_query_mask.sum()}")
    
    if slow_query_mask.sum() != enriched_df['is_slow_query'].sum():
        print("  ⚠️ MISMATCH! Checking why...")
        
        missed_slow = slow_query_mask & (enriched_df['is_slow_query'] == 0)
        if missed_slow.any():
            print(f"  ❌ {missed_slow.sum()} SLOW_QUERY logs missed by feature")
            print("  Sample missed messages:")
            for msg in df[missed_slow]['msg'].head(2):
                print(f"    - {msg[:100]}")
    
    # 7. Filter etkisi
    X_filtered, enriched_filtered = fe.apply_filters(enriched_df, X)
    print(f"\n📊 Filter Impact:")
    print(f"  Before filter: {len(enriched_df)} logs")
    print(f"  After filter: {len(enriched_filtered)} logs")
    print(f"  Filtered out: {len(enriched_df) - len(enriched_filtered)} logs")
    
    # Filtrelenen AUTH_FAIL sayısı
    filtered_auth = enriched_df['is_auth_failure'].sum() - enriched_filtered['is_auth_failure'].sum()
    print(f"  AUTH_FAIL filtered out: {filtered_auth}")
    
    filtered_slow = enriched_df['is_slow_query'].sum() - enriched_filtered['is_slow_query'].sum()
    print(f"  SLOW_QUERY filtered out: {filtered_slow}")
    
    # 8. ML Model test
    print("\n🤖 ML Detection Test:")
    
    # Sadece enabled features
    enabled_features = fe.enabled_features
    X_clean = X_filtered[enabled_features].fillna(0).astype(float)
    
    detector = MongoDBAnomalyDetector()
    detector.train(X_clean, save_model=False, incremental=False)
    predictions, scores = detector.predict(X_clean, enriched_filtered)
    
    # Anomali olarak işaretlenen AUTH_FAIL sayısı
    anomaly_mask = predictions == -1
    auth_anomalies = (enriched_filtered['is_auth_failure'] == 1) & anomaly_mask
    slow_anomalies = (enriched_filtered['is_slow_query'] == 1) & anomaly_mask
    
    print(f"  Total anomalies: {anomaly_mask.sum()}")
    print(f"  AUTH_FAIL marked as anomaly: {auth_anomalies.sum()}/{enriched_filtered['is_auth_failure'].sum()}")
    print(f"  SLOW_QUERY marked as anomaly: {slow_anomalies.sum()}/{enriched_filtered['is_slow_query'].sum()}")
    
    # 9. Score analizi
    if enriched_filtered['is_auth_failure'].sum() > 0:
        auth_scores = scores[enriched_filtered['is_auth_failure'] == 1]
        print(f"\n📈 AUTH_FAIL Anomaly Scores:")
        print(f"  Min: {auth_scores.min():.3f}, Max: {auth_scores.max():.3f}, Mean: {auth_scores.mean():.3f}")
        print(f"  Threshold (2% contamination): {np.percentile(scores, 2):.3f}")
    
    if enriched_filtered['is_slow_query'].sum() > 0:
        slow_scores = scores[enriched_filtered['is_slow_query'] == 1]
        print(f"\n📈 SLOW_QUERY Anomaly Scores:")
        print(f"  Min: {slow_scores.min():.3f}, Max: {slow_scores.max():.3f}, Mean: {slow_scores.mean():.3f}")
    
    print("\n" + "="*60)
    print("DIAGNOSIS COMPLETE")
    print("="*60)

if __name__ == "__main__":
    debug_pattern_detection()