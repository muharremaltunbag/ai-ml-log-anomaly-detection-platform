# tests/debug_slow_query.py

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

# Veri çek
reader = OpenSearchProxyReader()
reader.connect()
df = reader.read_logs(limit=5000, last_hours=24)

# Slow query'leri bul
print("\n🔍 SLOW QUERY ANALYSIS:")

# Manuel pattern arama
slow_pattern = df['msg'].str.contains(r"Slow query|durationMillis:[1-9]\d{3}", case=False, na=False, regex=True)
print(f"Manual pattern found: {slow_pattern.sum()} slow queries")

# Feature engineering
fe = MongoDBFeatureEngineer()
X, enriched_df = fe.create_features(df)

# Feature'da kaç tane var?
print(f"is_slow_query feature: {enriched_df['is_slow_query'].sum()}")

# Filter sonrası
X_filtered, enriched_filtered = fe.apply_filters(enriched_df, X)
print(f"After filter: {enriched_filtered['is_slow_query'].sum()}")

# Component ve host durumu
print(f"\n📊 DATA FIELDS:")
print(f"Has 'c' field: {'c' in enriched_filtered.columns}")
print(f"Has 'host' field: {'host' in enriched_filtered.columns}")

if 'c' in enriched_filtered.columns:
    print(f"Non-null components: {enriched_filtered['c'].notna().sum()}")
    print(f"Sample components: {enriched_filtered['c'].value_counts().head(3).to_dict()}")

if 'host' in enriched_filtered.columns:
    print(f"Non-null hosts: {enriched_filtered['host'].notna().sum()}")
    print(f"Sample hosts: {enriched_filtered['host'].value_counts().head(3).to_dict()}")

# Duration ve docs count kontrolü
print(f"\n📈 METRICS:")
print(f"query_duration_ms > 0: {(enriched_filtered['query_duration_ms'] > 0).sum()}")
print(f"docs_examined_count > 0: {(enriched_filtered['docs_examined_count'] > 0).sum()}")

# Contamination rate problemi?
print(f"\n⚠️ CONTAMINATION ANALYSIS:")
print(f"Total logs: {len(enriched_filtered)}")
print(f"2% contamination = {int(len(enriched_filtered) * 0.02)} anomalies")
print(f"Slow queries: {enriched_filtered['is_slow_query'].sum()}")
print("Problem: Eğer slow query sayısı > contamination limit ise hepsi yakalanmaz!")