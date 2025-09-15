import joblib
import os

model_path = "models/isolation_forest_lcwmongodb01n2.pkl"
file_size_mb = os.path.getsize(model_path) / (1024 * 1024)
print(f"Model dosya boyutu: {file_size_mb:.2f} MB")

model_data = joblib.load(model_path)
print(f"Model data keys: {list(model_data.keys())}")

if 'historical_data' in model_data:
    hist_data = model_data['historical_data']
    if hist_data and hist_data.get('features') is not None:
        print(f"Historical buffer samples: {len(hist_data['features'])}")
    else:
        print("Historical buffer BOŞ veya None!")