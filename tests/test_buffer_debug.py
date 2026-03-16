import joblib
import os

# Production model'i kontrol et
print(f"\Production ortamında test:")
prod_model_path = "models/isolation_forest_mongo-prod-01.pkl"
print(f"Production model size: {os.path.getsize(prod_model_path) / (1024*1024):.2f} MB")

model_data = joblib.load(prod_model_path)
print(f"\nModel keys: {list(model_data.keys())}")
print(f"Model version: {model_data.get('model_version', 'N/A')}")
print(f"Server name: {model_data.get('server_name', 'N/A')}")

# Historical data kontrolü
hist_data = model_data.get('historical_data')
if hist_data is None:
    print("\n❌ historical_data is None!")
elif hist_data.get('features') is None:
    print("\n❌ historical_data exists but features is None!")
    print(f"Metadata: {hist_data.get('metadata', {})}")
else:
    print(f"\n✅ Buffer has {len(hist_data['features'])} samples")

# Training stats
stats = model_data.get('training_stats', {})
print(f"\nLast training:")
print(f"  Samples: {stats.get('n_samples', 'N/A')}")
print(f"  Timestamp: {stats.get('timestamp', 'N/A')}")