# test_model_keys.py
import joblib
import sys
import os

# Test dosyasinin bulundugu dizin
test_dir = os.path.dirname(os.path.abspath(__file__))

# Proje root dizini (3 ust klasor: new -> Prod Tests -> tests -> project root)
project_root = os.path.abspath(os.path.join(test_dir, '..', '..', '..'))
sys.path.insert(0, project_root)

# Model dosyasi path'i - Proje root'undaki models klasoru
model_path = os.path.join(project_root, 'models', 'isolation_forest_dbserver-015.pkl')

# Alternatif: Linux sunucusundaysa
# model_path = '/opt/mongodb-assistant/models/isolation_forest_DBSERVER002.pkl'

print(f"Model path: {model_path}")
print(f"File exists: {os.path.exists(model_path)}")

if os.path.exists(model_path):
    try:
        data = joblib.load(model_path)
        print("\n=== MODEL FILE CONTENT ===")
        print(f"Keys: {list(data.keys())}")
        print(f"\n--- Ensemble Check ---")
        print(f"is_ensemble_mode: {data.get('is_ensemble_mode', 'KEY NOT FOUND')}")
        print(f"incremental_models: {len(data.get('incremental_models', []))} items")
        print(f"model_weights: {data.get('model_weights', 'KEY NOT FOUND')}")
        print(f"model_metadata: {len(data.get('model_metadata', []))} items")
        print(f"incremental_config: {data.get('incremental_config', 'KEY NOT FOUND')}")
        
        print(f"\n--- Other Fields ---")
        print(f"model_version: {data.get('model_version', 'KEY NOT FOUND')}")
        print(f"server_name: {data.get('server_name', 'KEY NOT FOUND')}")
        print(f"is_scaler_fitted: {data.get('is_scaler_fitted', 'KEY NOT FOUND')}")
        
        # Historical data check
        hist = data.get('historical_data')
        if hist and hist.get('features') is not None:
            print(f"historical_data samples: {len(hist['features'])}")
        else:
            print(f"historical_data: Empty or not found")
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
else:
    # List existing model files
    models_dir = os.path.join(project_root, 'models')
    if os.path.exists(models_dir):
        files = [f for f in os.listdir(models_dir) if f.endswith('.pkl')]
        if files:
            print(f"\nExisting model files ({models_dir}):")
            for f in files:
                full_path = os.path.join(models_dir, f)
                size_mb = os.path.getsize(full_path) / 1024 / 1024
                print(f"  - {f} ({size_mb:.2f} MB)")
        else:
            print(f"\nModels folder exists but is empty: {models_dir}")
    else:
        print(f"Models folder not found: {models_dir}")