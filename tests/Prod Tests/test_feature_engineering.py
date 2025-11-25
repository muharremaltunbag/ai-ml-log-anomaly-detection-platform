"""
Feature Engineering Pipeline Test
"""
import sys
import os
from pathlib import Path
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Path setup
current_dir = Path(__file__).parent
project_root = current_dir.parent.parent
sys.path.insert(0, str(project_root))

from src.anomaly.feature_engineer import MongoDBFeatureEngineer

def test_feature_engineering():
    """Feature engineering pipeline testi"""
    print("\n" + "="*70)
    print(" FEATURE ENGINEERING TEST ")
    print("="*70)
    
    # Test için çeşitli anomali türlerini içeren sample logs
    sample_logs = pd.DataFrame([
        # 1. Auth failure
        {
            "t": {"$date": "2025-11-13T23:22:13.583+00:00"},
            "s": "I",
            "c": "ACCESS",
            "msg": "Checking authorization failed",
            "attr": {
                "error": {
                    "code": 13,
                    "errmsg": "not authorized on admin"
                }
            },
            "host": "ECOMFIXMONGODB01"
        },
        # 2. Slow query
        {
            "t": {"$date": "2025-11-13T23:22:14.100+00:00"},
            "s": "I",
            "c": "COMMAND",
            "msg": 'Slow query: find customers.orders planSummary: COLLSCAN durationMillis: 2500',
            "attr": {
                "durationMillis": 2500,
                "docsExamined": 50000,
                "keysExamined": 0
            },
            "host": "ECOMFIXMONGODB01"
        },
        # 3. Error severity
        {
            "t": {"$date": "2025-11-13T23:22:15.200+00:00"},
            "s": "E",
            "c": "NETWORK",
            "msg": "Connection refused",
            "attr": {},
            "host": "ECOMFIXMONGODB01"
        },
        # 4. Out of Memory
        {
            "t": {"$date": "2025-11-13T23:22:16.300+00:00"},
            "s": "F",
            "c": "STORAGE",
            "msg": "Out of memory: tcmalloc allocation failed",
            "attr": {
                "error": {
                    "code": 137,
                    "errmsg": "OutOfMemory"
                }
            },
            "host": "ECOMFIXMONGODB01"
        },
        # 5. Index build
        {
            "t": {"$date": "2025-11-13T23:22:17.400+00:00"},
            "s": "I",
            "c": "INDEX",
            "msg": "Index build: starting",
            "attr": {},
            "host": "ECOMFIXMONGODB01"
        },
        # 6. Drop operation
        {
            "t": {"$date": "2025-11-13T23:22:18.500+00:00"},
            "s": "I",
            "c": "COMMAND",
            "msg": "CMD: dropIndexes",
            "attr": {},
            "host": "ECOMFIXMONGODB01"
        }
    ])
    
    # Feature engineer instance
    print("\n1️⃣ Initializing Feature Engineer...")
    engineer = MongoDBFeatureEngineer()
    
    # Feature extraction
    print("\n2️⃣ Extracting features...")
    features_df, enriched_df = engineer.create_features(sample_logs)
    
    print(f"\n✅ Original logs: {len(sample_logs)}")
    print(f"✅ After feature engineering: {len(features_df)}")
    print(f"✅ Feature count: {len(features_df.columns)}")
    
    # Kritik feature'ları kontrol et
    print(f"\n3️⃣ Critical Features Check:")
    print("-" * 40)
    
    critical_features = {
        'is_auth_failure': 'Auth Failures',
        'is_slow_query': 'Slow Queries',
        'is_error': 'Errors',
        'is_out_of_memory': 'OOM',
        'is_index_build': 'Index Builds',
        'is_drop_operation': 'Drop Operations',
        'is_collscan': 'COLLSCAN',
        'query_duration_ms': 'Query Duration',
        'docs_examined_count': 'Docs Examined',
        'extreme_burst_flag': 'Extreme Bursts'
    }
    
    for feat, name in critical_features.items():
        if feat in features_df.columns:
            if feat in ['query_duration_ms', 'docs_examined_count']:
                # Continuous features
                values = features_df[feat]
                print(f"   {name}: max={values.max()}, mean={values.mean():.1f}")
            else:
                # Binary features
                count = features_df[feat].sum()
                pct = features_df[feat].mean() * 100
                print(f"   {name}: {count}/{len(features_df)} ({pct:.0f}%)")
        else:
            print(f"   ⚠️ {name}: Feature missing!")
    
    # Feature statistics
    print(f"\n4️⃣ Feature Statistics:")
    print("-" * 40)
    stats = engineer.get_feature_statistics(features_df)
    
    print(f"   Binary features: {len(stats['binary_features'])}")
    print(f"   Continuous features: {len(stats['continuous_features'])}")
    
    # Anomali tespit edilmesi gereken loglar
    print(f"\n5️⃣ Expected Anomalies Detection:")
    print("-" * 40)
    
    expected_anomalies = [
        (0, "Auth failure"),
        (1, "Slow query + COLLSCAN"),
        (2, "Error severity"),
        (3, "Out of Memory"),
        (4, "Index build"),
        (5, "Drop operation")
    ]
    
    for idx, desc in expected_anomalies:
        flags = []
        if enriched_df.loc[idx, 'is_auth_failure'] == 1:
            flags.append("AUTH")
        if enriched_df.loc[idx, 'is_slow_query'] == 1:
            flags.append("SLOW")
        if enriched_df.loc[idx, 'is_error'] == 1:
            flags.append("ERROR")
        if enriched_df.loc[idx, 'is_out_of_memory'] == 1:
            flags.append("OOM")
        if enriched_df.loc[idx, 'is_index_build'] == 1:
            flags.append("INDEX")
        if enriched_df.loc[idx, 'is_drop_operation'] == 1:
            flags.append("DROP")
        
        status = "✅" if flags else "❌"
        print(f"   Log #{idx} ({desc}): {status} {' | '.join(flags)}")
    
    # Memory usage
    print(f"\n6️⃣ Memory Usage:")
    print("-" * 40)
    memory_mb = enriched_df.memory_usage(deep=True).sum() / 1024 / 1024
    print(f"   Total memory: {memory_mb:.2f} MB")
    print(f"   Per log: {memory_mb/len(enriched_df)*1000:.2f} KB")
    
    # Filter test
    print(f"\n7️⃣ Filter Test:")
    print("-" * 40)
    df_filtered, X_filtered = engineer.apply_filters(enriched_df, features_df)
    print(f"   Before filter: {len(enriched_df)} logs")
    print(f"   After filter: {len(df_filtered)} logs")
    print(f"   Filtered out: {len(enriched_df) - len(df_filtered)} logs")
    
    return features_df, enriched_df

def test_real_opensearch_data():
    """Gerçek OpenSearch verisini test et"""
    print("\n" + "="*70)
    print(" REAL DATA FEATURE ENGINEERING TEST ")
    print("="*70)
    
    from src.anomaly.log_reader import OpenSearchProxyReader
    
    # OpenSearch'ten veri oku
    print("\n1️⃣ Reading from OpenSearch...")
    reader = OpenSearchProxyReader()
    
    if not reader.connect():
        print("❌ OpenSearch bağlantısı kurulamadı")
        return None, None
    
    # Son 2 saatlik veri (daha fazla çeşitlilik için)
    df = reader.read_logs(
        limit=500,
        last_hours=2,
        host_filter="ECOMFIXMONGODB01"
    )
    
    if df.empty:
        print("❌ Veri okunamadı")
        return None, None
    
    print(f"✅ {len(df)} log okundu")
    
    # Feature engineering
    print("\n2️⃣ Feature Engineering on Real Data...")
    engineer = MongoDBFeatureEngineer()
    features_df, enriched_df = engineer.create_features(df)
    
    # Pattern distribution
    print("\n3️⃣ Pattern Distribution in Real Data:")
    print("-" * 40)
    
    patterns = {
        'is_auth_failure': 'Auth Failures',
        'is_slow_query': 'Slow Queries',
        'is_error': 'Errors',
        'is_collscan': 'COLLSCAN',
        'is_out_of_memory': 'OOM',
        'is_drop_operation': 'Drop Ops',
        'is_index_build': 'Index Builds'
    }
    
    for feat, name in patterns.items():
        if feat in enriched_df.columns:
            count = enriched_df[feat].sum()
            pct = enriched_df[feat].mean() * 100
            if count > 0:
                print(f"   ✅ {name}: {count} ({pct:.1f}%)")
            else:
                print(f"   ℹ️ {name}: 0")
    
    # Performance metrics
    print("\n4️⃣ Performance Metrics:")
    print("-" * 40)
    
    if 'query_duration_ms' in enriched_df.columns:
        slow_queries = enriched_df[enriched_df['query_duration_ms'] > 100]
        if len(slow_queries) > 0:
            print(f"   Slow queries (>100ms): {len(slow_queries)}")
            print(f"   Max duration: {enriched_df['query_duration_ms'].max():.0f}ms")
            print(f"   Avg duration: {slow_queries['query_duration_ms'].mean():.0f}ms")
    
    if 'docs_examined_count' in enriched_df.columns:
        high_scan = enriched_df[enriched_df['docs_examined_count'] > 10000]
        if len(high_scan) > 0:
            print(f"   High doc scans (>10K): {len(high_scan)}")
            print(f"   Max docs examined: {enriched_df['docs_examined_count'].max():.0f}")
    
    return features_df, enriched_df

if __name__ == "__main__":
    # Test 1: Synthetic data
    print("="*70)
    print(" TEST 1: SYNTHETIC DATA ")
    print("="*70)
    features_df, enriched_df = test_feature_engineering()
    
    # Test 2: Real OpenSearch data
    print("\n\n")
    print("="*70)
    print(" TEST 2: REAL OPENSEARCH DATA ")
    print("="*70)
    real_features, real_enriched = test_real_opensearch_data()
    
    # Final summary
    print("\n" + "="*70)
    print(" TEST SUMMARY ")
    print("="*70)
    
    if features_df is not None:
        print("✅ Synthetic data test: PASSED")
    else:
        print("❌ Synthetic data test: FAILED")
    
    if real_features is not None:
        print("✅ Real data test: PASSED")
    else:
        print("❌ Real data test: FAILED")