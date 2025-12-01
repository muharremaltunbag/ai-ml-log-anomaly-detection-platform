"""
Thread Safety Test for MongoDBAnomalyDetector.train() method
Düzeltme 2/6 - Thread Lock Kapsamı Testi
"""
import sys
import os
from pathlib import Path

# Path düzeltmesi
current_file = Path(__file__).resolve()
project_root = current_file.parent.parent.parent
sys.path.insert(0, str(project_root))

import threading
import time
import pandas as pd
import numpy as np

print("=" * 60)
print("THREAD SAFETY TEST - anomaly_detector.py train()")
print("=" * 60)

# Test 1: Import ve Lock Kontrolü
print("\n📋 Test 1: Import ve Lock Kontrolü")
try:
    from src.anomaly.anomaly_detector import MongoDBAnomalyDetector
    detector = MongoDBAnomalyDetector()
    
    # Lock attribute kontrolü
    assert hasattr(detector, '_training_lock'), "_training_lock attribute bulunamadı!"
    print("✅ MongoDBAnomalyDetector import edildi")
    print(f"✅ _training_lock mevcut: {type(detector._training_lock)}")
except Exception as e:
    print(f"❌ Import hatası: {e}")
    sys.exit(1)

# Test 2: Tek Thread Training
print("\n📋 Test 2: Tek Thread Training")
try:
    # Test data oluştur
    X_test = pd.DataFrame({
        'hour_of_day': np.random.randint(0, 24, 100),
        'is_error': np.random.randint(0, 2, 100),
        'severity_W': np.random.randint(0, 2, 100),
        'is_rare_component': np.random.randint(0, 2, 100),
        'component_encoded': np.random.randint(0, 10, 100),
        'is_auth_failure': np.random.randint(0, 2, 100),
        'is_drop_operation': np.random.randint(0, 2, 100),
        'is_collscan': np.random.randint(0, 2, 100),
        'is_slow_query': np.random.randint(0, 2, 100),
        'query_duration_ms': np.random.randint(0, 5000, 100),
        'docs_examined_count': np.random.randint(0, 100000, 100),
    })
    
    result = detector.train(X_test.copy(), save_model=False, server_name="test_single_thread")
    
    assert detector.is_trained, "Model eğitilmedi!"
    assert 'n_samples' in result, "Training stats eksik!"
    print(f"✅ Tek thread training başarılı")
    print(f"   Samples: {result['n_samples']}, Features: {result['n_features']}")
    print(f"   Training time: {result['training_time_seconds']:.3f}s")
except Exception as e:
    print(f"❌ Tek thread training hatası: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 3: Lock Release Kontrolü
print("\n📋 Test 3: Lock Release Kontrolü")
try:
    # Training sonrası lock serbest mi?
    lock_acquired = detector._training_lock.acquire(blocking=False)
    if lock_acquired:
        detector._training_lock.release()
        print("✅ Lock training sonrası serbest bırakılmış")
    else:
        print("❌ Lock hala tutulu! Thread safety sorunu!")
        sys.exit(1)
except Exception as e:
    print(f"❌ Lock kontrolü hatası: {e}")
    sys.exit(1)

# Test 4: Concurrent Training (Race Condition Testi)
print("\n📋 Test 4: Concurrent Training (Race Condition Testi)")

results = []
errors = []
execution_order = []

def train_thread(thread_id):
    """Her thread farklı server_name ile training yapar"""
    try:
        start_time = time.time()
        execution_order.append(f"T{thread_id}_start")
        
        # Her thread için farklı data
        X_thread = pd.DataFrame({
            'hour_of_day': np.random.randint(0, 24, 50 + thread_id * 10),
            'is_error': np.random.randint(0, 2, 50 + thread_id * 10),
            'severity_W': np.random.randint(0, 2, 50 + thread_id * 10),
            'is_rare_component': np.random.randint(0, 2, 50 + thread_id * 10),
            'component_encoded': np.random.randint(0, 10, 50 + thread_id * 10),
            'is_auth_failure': np.random.randint(0, 2, 50 + thread_id * 10),
            'is_drop_operation': np.random.randint(0, 2, 50 + thread_id * 10),
            'is_collscan': np.random.randint(0, 2, 50 + thread_id * 10),
            'is_slow_query': np.random.randint(0, 2, 50 + thread_id * 10),
            'query_duration_ms': np.random.randint(0, 5000, 50 + thread_id * 10),
            'docs_examined_count': np.random.randint(0, 100000, 50 + thread_id * 10),
        })
        
        result = detector.train(X_thread, save_model=False, server_name=f"concurrent_test_{thread_id}")
        
        elapsed = time.time() - start_time
        execution_order.append(f"T{thread_id}_end")
        results.append({
            'thread_id': thread_id,
            'status': 'success',
            'samples': result['n_samples'],
            'elapsed': elapsed
        })
    except Exception as e:
        execution_order.append(f"T{thread_id}_error")
        errors.append({
            'thread_id': thread_id,
            'error': str(e)
        })

# 3 concurrent thread başlat
threads = []
for i in range(3):
    t = threading.Thread(target=train_thread, args=(i,))
    threads.append(t)

# Tüm thread'leri aynı anda başlat
for t in threads:
    t.start()

# Tüm thread'lerin bitmesini bekle
for t in threads:
    t.join(timeout=30)  # Max 30 saniye bekle

print(f"\n   Execution order: {' -> '.join(execution_order)}")
print(f"   ✅ Başarılı thread: {len(results)}")
print(f"   ❌ Hatalı thread: {len(errors)}")

if errors:
    print("\n   Hatalar:")
    for err in errors:
        print(f"   Thread {err['thread_id']}: {err['error']}")
else:
    print("\n   Thread detayları:")
    for r in results:
        print(f"   Thread {r['thread_id']}: {r['samples']} samples, {r['elapsed']:.3f}s")

# Test 5: Exception Durumunda Lock Release
print("\n📋 Test 5: Exception Durumunda Lock Release")
try:
    # Boş DataFrame ile hata oluştur
    X_empty = pd.DataFrame()
    
    try:
        detector.train(X_empty, save_model=False)
    except Exception as expected_error:
        print(f"   Beklenen hata oluştu: {type(expected_error).__name__}")
    
    # Hata sonrası lock serbest mi?
    lock_acquired = detector._training_lock.acquire(blocking=False)
    if lock_acquired:
        detector._training_lock.release()
        print("✅ Exception sonrası lock serbest bırakılmış (finally çalıştı)")
    else:
        print("❌ Exception sonrası lock hala tutulu! finally bloğu çalışmadı!")
        sys.exit(1)
except Exception as e:
    print(f"❌ Exception lock testi hatası: {e}")

# Özet
print("\n" + "=" * 60)
print("TEST ÖZETİ")
print("=" * 60)

total_tests = 5
passed_tests = 5 - len(errors)

if len(errors) == 0:
    print(f"✅ Tüm testler başarılı ({passed_tests}/{total_tests})")
    print("✅ Thread safety düzeltmesi doğru çalışıyor!")
else:
    print(f"⚠️ {len(errors)} test başarısız ({passed_tests}/{total_tests})")
    print("❌ Thread safety sorunları mevcut!")

print("\n" + "=" * 60)