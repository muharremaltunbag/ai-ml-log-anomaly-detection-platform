# tests/test_after_fix.py

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

# Test
reader = OpenSearchProxyReader()
reader.connect()
df = reader.read_logs(limit=1000, last_hours=2)

fe = MongoDBFeatureEngineer()
X, enriched_df = fe.create_features(df)
X_filtered, enriched_filtered = fe.apply_filters(enriched_df, X)

print(f"✅ Total logs: {len(enriched_filtered)}")
print(f"✅ Has component: {'c' in enriched_filtered.columns}")
print(f"✅ Has host: {'host' in enriched_filtered.columns}")
print(f"✅ Slow queries: {enriched_filtered['is_slow_query'].sum()}")

# Model ile test
detector = MongoDBAnomalyDetector()
# Config'i override et
detector.model_config['parameters']['contamination'] = 0.05  # %5

print(f"✅ Enabled features: {fe.enabled_features}")
enabled_features = fe.enabled_features
X_clean = X_filtered[enabled_features].fillna(0).astype(float)

detector.train(X_clean, save_model=False, incremental=False)
predictions, scores = detector.predict(X_clean, enriched_filtered)

anomaly_count = (predictions == -1).sum()
slow_in_anomalies = ((predictions == -1) & (enriched_filtered['is_slow_query'] == 1)).sum()

print(f"\n📊 Results:")
print(f"  Anomalies: {anomaly_count}")
print(f"  Slow queries caught: {slow_in_anomalies}/{enriched_filtered['is_slow_query'].sum()}")
print(f"  Catch rate: {slow_in_anomalies/enriched_filtered['is_slow_query'].sum()*100:.1f}%")