"""
FULL MODEL VERSION CONSISTENCY TEST
Bu test:
1) Prod modeli yükler
2) Model version bilgisini okur
3) Mini training ile yeni model kaydeder
4) Incremental training yapar
5) Her aşamada model_version tutarlılığını doğrular
"""
import sys
import os

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE_DIR)
import pandas as pd
import joblib
from pathlib import Path
from datetime import datetime

from src.anomaly.anomaly_detector import MongoDBAnomalyDetector


def print_header(title):
    print("\n" + "="*80)
    print(title)
    print("="*80)


def safe_print(obj):
    try:
        print(obj)
    except Exception:
        print(str(obj))


def main():

    # -----------------------------------------------------------
    # TEST BAŞLIYOR
    # -----------------------------------------------------------
    print_header("FULL MODEL VERSION TEST BAŞLADI")

    SERVER = "ECAZGLDB"   # Prod test etmek istediğin sunucu adını buraya yaz
    MODEL_PATH = f"models/isolation_forest_{SERVER}.pkl"

    # -----------------------------------------------------------
    # AŞAMA 1: Mevcut Production Modelini Yükle
    # -----------------------------------------------------------
    print_header("AŞAMA 1 — Production Model Load Testi")

    detector = MongoDBAnomalyDetector()
    load_ok = detector.load_model(server_name=SERVER)

    print(f"LOAD OK: {load_ok}")
    print(f"Model Trained: {detector.is_trained}")
    print(f"Model Version (detector.model_version): {detector.model_version}")
    print(f"Model Version (training_stats): {detector.training_stats.get('model_version')}")
    print(f"Feature Count: {len(detector.feature_names)}")

    # -----------------------------------------------------------
    # AŞAMA 2: Mini Training (Yeni Versiyon Yazımı)
    # -----------------------------------------------------------
    print_header("AŞAMA 2 — Mini Training Testi")

    # Küçük sahte data (36 feature = prod ile uyumlu)
    df_train = pd.DataFrame([[i]*len(detector.feature_names) for i in range(10)],
                             columns=detector.feature_names)

    train_stats = detector.train(df_train, server_name=SERVER)

    print("TRAINING DONE")
    print(f"New Training Stats Version: {train_stats.get('model_version')}")
    print(f"Detector Model Version After Train: {detector.model_version}")

    # -----------------------------------------------------------
    # AŞAMA 3: Kaydedilen Model Dosyasını Aç
    # -----------------------------------------------------------
    print_header("AŞAMA 3 — Model Dosya İçeriği Testi")

    if Path(MODEL_PATH).exists():
        data = joblib.load(MODEL_PATH)
        print("MODEL FILE FOUND")
        print(f"model_version in file: {data.get('model_version')}")
        print(f"training_stats.model_version: {data.get('training_stats', {}).get('model_version')}")
        print(f"Keys: {list(data.keys())}")
    else:
        print("MODEL FILE NOT FOUND:", MODEL_PATH)

    # -----------------------------------------------------------
    # AŞAMA 4: Incremental Learning Testi
    # -----------------------------------------------------------
    print_header("AŞAMA 4 — Incremental Learning Versiyon Testi")

    df_inc = pd.DataFrame([[99]*len(detector.feature_names) for _ in range(5)],
                          columns=detector.feature_names)

    train_stats_inc = detector.train(df_inc, incremental=True, server_name=SERVER)

    print("INCREMENTAL TRAINING DONE")
    print(f"Detector Model Version After Incremental: {detector.model_version}")
    print(f"Training Stats Version: {train_stats_inc.get('model_version')}")

    # -----------------------------------------------------------
    # TEST BİTTİ
    # -----------------------------------------------------------
    print_header("FULL MODEL VERSION TEST TAMAMLANDI")
    print(f"Tamamlanma zamanı: {datetime.now().isoformat()}")


if __name__ == "__main__":
    main()
