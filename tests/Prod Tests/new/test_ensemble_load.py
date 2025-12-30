# test_ensemble_load.py
import sys
import os

project_path = os.path.dirname(os.path.abspath(__file__))
# Eğer tests klasöründeyse, bir üst dizine çık
if 'tests' in project_path:
    project_path = os.path.dirname(os.path.dirname(os.path.dirname(project_path)))
sys.path.insert(0, project_path)

from src.anomaly.anomaly_detector import MongoDBAnomalyDetector

print("=== ENSEMBLE LOAD TEST ===\n")

# Test 1: Yeni instance oluştur ve model yükle
print("1. Creating new detector instance...")
detector = MongoDBAnomalyDetector()

print("2. Loading model for ecaztrdbmng015...")
success = detector.load_model(server_name="ecaztrdbmng015")

print(f"\n--- Load Result ---")
print(f"Load successful: {success}")
print(f"is_trained: {detector.is_trained}")
print(f"model is None: {detector.model is None}")

print(f"\n--- Ensemble Status ---")
print(f"incremental_models count: {len(detector.incremental_models)}")
print(f"model_weights: {detector.model_weights}")
print(f"model_metadata count: {len(detector.model_metadata)}")
print(f"incremental_config enabled: {detector.incremental_config.get('enabled', False)}")

# Test 2: Ensemble info
print(f"\n--- Ensemble Info ---")
ensemble_info = detector.get_ensemble_info()
print(f"Status: {ensemble_info.get('status')}")
print(f"Model count: {ensemble_info.get('model_count')}")

if ensemble_info.get('model_count', 0) > 0:
    print("\n✅ ENSEMBLE SUCCESSFULLY LOADED!")
else:
    print("\n❌ ENSEMBLE NOT LOADED - Check load_model() implementation")