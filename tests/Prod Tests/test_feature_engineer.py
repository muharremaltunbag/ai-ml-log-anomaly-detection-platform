# tests/test_feature_engineer.py

import sys
from pathlib import Path

# Path düzeltmesi
current_file = Path(__file__).resolve()
project_root = current_file.parent.parent.parent
sys.path.insert(0, str(project_root))

print(f"[DEBUG] Project root: {project_root}")

from src.anomaly.log_reader import OpenSearchProxyReader
from src.anomaly.feature_engineer import MongoDBFeatureEngineer
import pandas as pd

print("\n" + "="*60)
print("FEATURE ENGINEER COMPREHENSIVE TEST")
print("="*60)

# 1. Veri çek
reader = OpenSearchProxyReader()
reader.connect()
df_original = reader.read_logs(limit=100, last_hours=1)

print("\n📊 ORIGINAL DATA:")
print(f"  Shape: {df_original.shape}")
print(f"  Columns: {df_original.columns.tolist()}")

# Önemli field'ları kontrol et
important_fields = ['t', 's', 'c', 'id', 'ctx', 'msg', 'attr', 'raw_log', 'host']
for field in important_fields:
    if field in df_original.columns:
        null_count = df_original[field].isna().sum()
        print(f"  {field}: {len(df_original) - null_count}/{len(df_original)} non-null")

# 2. Feature Engineering
fe = MongoDBFeatureEngineer()
X, enriched_df = fe.create_features(df_original)

print("\n🔧 AFTER CREATE_FEATURES:")
print(f"  X shape: {X.shape}")
print(f"  enriched_df shape: {enriched_df.shape}")
print(f"  New features added: {len(X.columns) - len(df_original.columns)}")

# Original field'lar hala var mı?
lost_fields = []
for field in important_fields:
    if field in df_original.columns and field not in enriched_df.columns:
        lost_fields.append(field)
        print(f"  ❌ LOST: {field}")

if not lost_fields:
    print(f"  ✅ All original fields preserved")

# Feature değerleri kontrolü
print("\n📈 FEATURE VALUES CHECK:")
feature_checks = [
    ('is_slow_query', enriched_df['is_slow_query'].sum()),
    ('is_auth_failure', enriched_df['is_auth_failure'].sum()),
    ('query_duration_ms', (enriched_df['query_duration_ms'] > 0).sum()),
    ('docs_examined_count', (enriched_df['docs_examined_count'] > 0).sum()),
    ('performance_score', (enriched_df['performance_score'] > 0).sum())
]

for feature, count in feature_checks:
    print(f"  {feature}: {count} positive values")

# 3. Apply Filters
X_filtered, enriched_filtered = fe.apply_filters(enriched_df, X)

print("\n🔀 AFTER APPLY_FILTERS:")
print(f"  X_filtered shape: {X_filtered.shape}")
print(f"  enriched_filtered shape: {enriched_filtered.shape}")
print(f"  Logs filtered out: {len(enriched_df) - len(enriched_filtered)}")

# Field'lar filter'dan sonra kayboldu mu?
lost_after_filter = []
for field in important_fields:
    if field in enriched_df.columns and field not in enriched_filtered.columns:
        lost_after_filter.append(field)
        print(f"  ❌ LOST AFTER FILTER: {field}")

if not lost_after_filter:
    print(f"  ✅ All fields preserved after filter")
else:
    print(f"\n  🔧 ATTEMPTING TO RESTORE LOST FIELDS...")
    # Manuel restore dene
    for field in lost_after_filter:
        if field in df_original.columns:
            try:
                # Filter mask'i yeniden oluştur
                filter_mask = enriched_df.index.isin(enriched_filtered.index)
                enriched_filtered[field] = enriched_df.loc[filter_mask, field].values
                print(f"    ✅ Restored: {field}")
            except:
                print(f"    ❌ Failed to restore: {field}")

# 4. Sample data görüntüle
print("\n📝 SAMPLE ENRICHED DATA:")
sample = enriched_filtered.head(3)
for idx, row in sample.iterrows():
    print(f"\nLog {idx}:")
    print(f"  Component: {row.get('c', 'N/A')}")
    print(f"  Host: {row.get('host', 'N/A')}")
    print(f"  Message: {str(row.get('msg', 'N/A'))[:50]}...")
    print(f"  is_slow_query: {row.get('is_slow_query', 0)}")
    print(f"  query_duration_ms: {row.get('query_duration_ms', 0)}")

print("\n" + "="*60)
print("TEST COMPLETE")
print("="*60)