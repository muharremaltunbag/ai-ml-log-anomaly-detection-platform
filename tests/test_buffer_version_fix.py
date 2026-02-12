"""
Test: Historical buffer version fix doğrulaması

Amaç:
1. model_version="1.0" ile kaydedilen buffer, load_model() ile yüklenebilmeli
2. model_version="2.1" ile kaydedilen buffer, load_model() ile yüklenebilmeli
3. historical_data=None olan pkl, güvenli empty buffer ile başlamalı
4. Buffer update sonrası buffer_version=2.0 olmalı
"""

import sys
import os
import tempfile
import shutil
import joblib
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from sklearn.ensemble import IsolationForest

# Pre-import: anomaly_detector modülünü doğrudan dosya yolundan yükle
# (__init__.py → anomaly_tools → langchain bağımlılığını bypass etmek için)
import importlib.util

_base_dir = os.path.join(os.path.dirname(__file__), '..', 'src', 'anomaly')

# Önce log_reader'ı yükle (anomaly_detector'un bağımlılığı)
_lr_spec = importlib.util.spec_from_file_location(
    'src.anomaly.log_reader', os.path.join(_base_dir, 'log_reader.py'))
_lr_mod = importlib.util.module_from_spec(_lr_spec)
sys.modules['src.anomaly.log_reader'] = _lr_mod
_lr_spec.loader.exec_module(_lr_mod)

# anomaly_detector'u doğrudan yükle
_ad_spec = importlib.util.spec_from_file_location(
    'src.anomaly.anomaly_detector', os.path.join(_base_dir, 'anomaly_detector.py'))
_ad_mod = importlib.util.module_from_spec(_ad_spec)
sys.modules['src.anomaly.anomaly_detector'] = _ad_mod
_ad_spec.loader.exec_module(_ad_mod)
MongoDBAnomalyDetector = _ad_mod.MongoDBAnomalyDetector

# mssql_anomaly_detector'u doğrudan yükle
_ms_spec = importlib.util.spec_from_file_location(
    'src.anomaly.mssql_anomaly_detector', os.path.join(_base_dir, 'mssql_anomaly_detector.py'))
_ms_mod = importlib.util.module_from_spec(_ms_spec)
sys.modules['src.anomaly.mssql_anomaly_detector'] = _ms_mod
_ms_spec.loader.exec_module(_ms_mod)
MSSQLAnomalyDetector = _ms_mod.MSSQLAnomalyDetector


def create_mock_model_pkl(path, model_version, historical_data):
    """Minimal pkl dosyası oluştur (gerçek model ile)"""
    X_dummy = pd.DataFrame({'f1': [1, 2, 3], 'f2': [4, 5, 6]})
    model = IsolationForest(n_estimators=10, random_state=42)
    model.fit(X_dummy)

    model_data = {
        'model': model,
        'feature_names': ['f1', 'f2'],
        'training_stats': {'n_samples': 3},
        'model_version': model_version,
        'historical_data': historical_data,
        'online_learning_config': {'enabled': True},
    }
    joblib.dump(model_data, path)


def test_v10_buffer_loads():
    """model_version=1.0 ile kaydedilmiş DOLU buffer yüklenebilmeli"""
    tmpdir = tempfile.mkdtemp()
    try:
        pkl_path = os.path.join(tmpdir, 'isolation_forest_test_v10.pkl')

        buffer_features = pd.DataFrame({'f1': [10, 20], 'f2': [30, 40]})
        historical = {
            'features': buffer_features,
            'predictions': np.array([1, -1]),
            'scores': np.array([-0.1, -0.5]),
            'metadata': {
                'total_samples': 2,
                'anomaly_samples': 1,
                'last_update': '2026-01-01T00:00:00',
                'buffer_version': 1.0
            }
        }
        create_mock_model_pkl(pkl_path, model_version='1.0', historical_data=historical)

        # MongoDBAnomalyDetector modül seviyesinde import edildi
        detector = MongoDBAnomalyDetector.__new__(MongoDBAnomalyDetector)
        detector.__init__()

        result = detector.load_model(path=pkl_path)

        assert result is True, "load_model should return True"
        assert detector.historical_data['features'] is not None, "Buffer features should NOT be None"
        assert len(detector.historical_data['features']) == 2, f"Expected 2 samples, got {len(detector.historical_data['features'])}"
        assert detector.historical_data['metadata']['total_samples'] == 2
        print("✅ TEST 1 PASSED: v1.0 buffer loaded successfully")
    finally:
        shutil.rmtree(tmpdir)


def test_v21_buffer_loads():
    """model_version=2.1 ile kaydedilmiş buffer yüklenebilmeli (regresyon testi)"""
    tmpdir = tempfile.mkdtemp()
    try:
        pkl_path = os.path.join(tmpdir, 'isolation_forest_test_v21.pkl')

        buffer_features = pd.DataFrame({'f1': [100, 200, 300], 'f2': [400, 500, 600]})
        historical = {
            'features': buffer_features,
            'predictions': np.array([1, 1, -1]),
            'scores': np.array([-0.1, -0.2, -0.6]),
            'metadata': {
                'total_samples': 3,
                'anomaly_samples': 1,
                'last_update': '2026-02-01T00:00:00',
                'buffer_version': 2.0
            }
        }
        create_mock_model_pkl(pkl_path, model_version='2.1', historical_data=historical)

        # MongoDBAnomalyDetector modül seviyesinde import edildi
        detector = MongoDBAnomalyDetector.__new__(MongoDBAnomalyDetector)
        detector.__init__()

        result = detector.load_model(path=pkl_path)

        assert result is True, "load_model should return True"
        assert detector.historical_data['features'] is not None, "Buffer features should NOT be None"
        assert len(detector.historical_data['features']) == 3
        print("✅ TEST 2 PASSED: v2.1 buffer loaded successfully (regression)")
    finally:
        shutil.rmtree(tmpdir)


def test_none_buffer_safe_fallback():
    """historical_data=None → güvenli empty buffer"""
    tmpdir = tempfile.mkdtemp()
    try:
        pkl_path = os.path.join(tmpdir, 'isolation_forest_test_none.pkl')

        create_mock_model_pkl(pkl_path, model_version='1.0', historical_data=None)

        # MongoDBAnomalyDetector modül seviyesinde import edildi
        detector = MongoDBAnomalyDetector.__new__(MongoDBAnomalyDetector)
        detector.__init__()

        result = detector.load_model(path=pkl_path)

        assert result is True, "load_model should still return True"
        assert detector.historical_data['features'] is None, "Buffer features should be None for empty buffer"
        assert detector.historical_data['metadata']['total_samples'] == 0
        print("✅ TEST 3 PASSED: None buffer → safe empty fallback")
    finally:
        shutil.rmtree(tmpdir)


def test_buffer_version_updated_after_train():
    """train() sonrası buffer_version 2.0 olmalı"""
    from src.anomaly.anomaly_detector import MongoDBAnomalyDetector
    detector = MongoDBAnomalyDetector.__new__(MongoDBAnomalyDetector)
    detector.__init__()

    X = pd.DataFrame({
        'f1': np.random.randn(50),
        'f2': np.random.randn(50)
    })

    # İlk training
    detector.train(X, save_model=False)

    assert detector.historical_data['metadata']['buffer_version'] == 2.0, \
        f"Expected buffer_version=2.0, got {detector.historical_data['metadata']['buffer_version']}"
    assert detector.historical_data['features'] is not None
    assert len(detector.historical_data['features']) == 50
    print("✅ TEST 4 PASSED: buffer_version=2.0 after train()")


def test_mssql_detector_inherits_fix():
    """MSSQLAnomalyDetector da aynı fix'i inherit ediyor olmalı"""
    tmpdir = tempfile.mkdtemp()
    try:
        pkl_path = os.path.join(tmpdir, 'mssql_isolation_forest_test.pkl')

        buffer_features = pd.DataFrame({'f1': [1], 'f2': [2]})
        historical = {
            'features': buffer_features,
            'predictions': np.array([1]),
            'scores': np.array([-0.1]),
            'metadata': {
                'total_samples': 1,
                'anomaly_samples': 0,
                'last_update': '2026-01-15T00:00:00',
                'buffer_version': 1.0
            }
        }
        create_mock_model_pkl(pkl_path, model_version='1.0', historical_data=historical)

        # MSSQLAnomalyDetector modül seviyesinde import edildi
        detector = MSSQLAnomalyDetector.__new__(MSSQLAnomalyDetector)
        detector.__init__()

        result = detector.load_model(path=pkl_path)

        assert result is True
        assert detector.historical_data['features'] is not None, "MSSQL detector should also load v1.0 buffer"
        assert len(detector.historical_data['features']) == 1
        print("✅ TEST 5 PASSED: MSSQLAnomalyDetector inherits buffer fix")
    finally:
        shutil.rmtree(tmpdir)


if __name__ == '__main__':
    print("=" * 60)
    print("Buffer Version Fix — Test Suite")
    print("=" * 60)

    tests = [
        test_v10_buffer_loads,
        test_v21_buffer_loads,
        test_none_buffer_safe_fallback,
        test_buffer_version_updated_after_train,
        test_mssql_detector_inherits_fix,
    ]

    passed = 0
    failed = 0
    for test_fn in tests:
        try:
            test_fn()
            passed += 1
        except Exception as e:
            print(f"❌ {test_fn.__name__} FAILED: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)

    sys.exit(0 if failed == 0 else 1)
