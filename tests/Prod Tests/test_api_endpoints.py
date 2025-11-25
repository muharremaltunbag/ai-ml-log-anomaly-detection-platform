import sys
import os
from pathlib import Path
import requests
import json
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv

# .env dosyasını yükle
load_dotenv()

# Root dizini ekle
root_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(root_dir))

# API Configuration
BASE_URL = "http://localhost:8000"
API_KEY = os.getenv("API_KEY")  # .env'den al

if not API_KEY:
    print("⚠️ WARNING: API_KEY not found in .env file!")
    print("Please add API_KEY=your_key to .env file")
    sys.exit(1)

print("=" * 50)
print("API ENDPOINT TESTS")
print("=" * 50)

def test_endpoint(method, endpoint, data=None, params=None, description=""):
    """Helper function for testing endpoints"""
    url = f"{BASE_URL}{endpoint}"
    print(f"\n[TEST] {description}")
    print(f"   {method} {url}")
    
    try:
        if method == "GET":
            response = requests.get(url, params=params)
        elif method == "POST":
            response = requests.post(url, json=data)
        else:
            response = requests.request(method, url, json=data)
        
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            print("   ✅ SUCCESS")
            return True, response.json()
        else:
            print(f"   ❌ FAILED: {response.text[:200]}")
            return False, None
            
    except Exception as e:
        print(f"   ❌ ERROR: {e}")
        return False, None

# Test sonuçları
results = {}

# 1. HEALTH & STATUS
print("\n" + "="*50)
print("1. HEALTH & STATUS ENDPOINTS")
print("="*50)

results['root'] = test_endpoint(
    "GET", "/",
    description="Root endpoint (HTML)"
)

results['status'] = test_endpoint(
    "GET", "/api/status",
    description="API Status"
)

# 2. MODEL ENDPOINTS
print("\n" + "="*50)
print("2. ML MODEL ENDPOINTS")
print("="*50)

results['ml_model_info'] = test_endpoint(
    "GET", "/api/ml/model-info",
    params={"api_key": API_KEY},
    description="ML Model Information"
)

results['ml_metrics'] = test_endpoint(
    "GET", "/api/ml/metrics", 
    params={"api_key": API_KEY},
    description="ML Model Metrics"
)

# 3. MONGODB HOSTS
print("\n" + "="*50)
print("3. MONGODB HOST ENDPOINTS")
print("="*50)

results['hosts'] = test_endpoint(
    "GET", "/api/mongodb/hosts",
    params={"api_key": API_KEY},
    description="Available MongoDB Hosts"
)

results['clusters'] = test_endpoint(
    "GET", "/api/mongodb/clusters",
    params={"api_key": API_KEY},
    description="MongoDB Clusters"
)

# 4. ANOMALY ANALYSIS (OpenSearch Test)
print("\n" + "="*50)
print("4. ANOMALY ANALYSIS ENDPOINTS")
print("="*50)

# Önce host listesini al
success, hosts_data = results['hosts']
if success and hosts_data and hosts_data.get('hosts'):
    test_host = hosts_data['hosts'][0]  # İlk host'u test için kullan
    print(f"   Using test host: {test_host}")
    
    analysis_data = {
        "file_path": "",
        "api_key": API_KEY,
        "time_range": "last_hour",
        "source_type": "opensearch",
        "host_filter": test_host
    }
    
    results['analyze_opensearch'] = test_endpoint(
        "POST", "/api/analyze-uploaded-log",
        data=analysis_data,
        description="OpenSearch Anomaly Analysis"
    )

# 5. STORAGE & HISTORY
print("\n" + "="*50)
print("5. STORAGE & HISTORY ENDPOINTS")
print("="*50)

results['anomaly_history'] = test_endpoint(
    "GET", "/api/anomaly-history",
    params={"api_key": API_KEY, "limit": 5},
    description="Anomaly History"
)

results['storage_stats'] = test_endpoint(
    "GET", "/api/storage-stats",
    params={"api_key": API_KEY, "days": 7},
    description="Storage Statistics"
)

# 6. DBA SPECIFIC ENDPOINTS
print("\n" + "="*50)
print("6. DBA ANALYSIS ENDPOINTS")
print("="*50)

if success and hosts_data and hosts_data.get('hosts'):
    # DBA specific time range analysis
    dba_params = {
        "host": test_host,
        "start_time": (datetime.now() - timedelta(hours=2)).isoformat() + "Z",
        "end_time": datetime.now().isoformat() + "Z",
        "api_key": API_KEY,
        "auto_explain": False  # LCWGPT kullanmadan test
    }
    
    results['dba_analyze'] = test_endpoint(
        "POST", f"/api/dba/analyze-specific-time",
        params=dba_params,
        description="DBA Specific Time Analysis"
    )

results['dba_history'] = test_endpoint(
    "GET", "/api/dba/analysis-history",
    params={"api_key": API_KEY, "limit": 5, "days_back": 30},
    description="DBA Analysis History"
)

# 7. QUERY ENDPOINTS
print("\n" + "="*50)
print("7. QUERY ENDPOINTS")
print("="*50)

query_data = {
    "query": "MongoDB loglarında anomali analizi yap",
    "api_key": API_KEY
}

results['query'] = test_endpoint(
    "POST", "/api/query",
    data=query_data,
    description="Process Query"
)

# 8. COLLECTIONS (MongoDB)
print("\n" + "="*50)
print("8. MONGODB COLLECTION ENDPOINTS")
print("="*50)

results['collections'] = test_endpoint(
    "GET", "/api/collections",
    params={"api_key": API_KEY},
    description="List MongoDB Collections"
)

# TEST SONUÇ RAPORU
print("\n" + "="*50)
print("TEST SONUÇ RAPORU")
print("="*50)

total_tests = len(results)
passed_tests = sum(1 for v in results.values() if v[0])
failed_tests = total_tests - passed_tests

print(f"\nToplam Test: {total_tests}")
print(f"✅ Başarılı: {passed_tests}")
print(f"❌ Başarısız: {failed_tests}")
print(f"Başarı Oranı: %{(passed_tests/total_tests)*100:.1f}")

print("\nDetaylı Sonuçlar:")
for test_name, (success, _) in results.items():
    status = "✅" if success else "❌"
    print(f"  {status} {test_name}")

# Kritik endpoint kontrolü
critical_endpoints = ['status', 'ml_model_info', 'hosts', 'anomaly_history']
critical_passed = all(results.get(ep, (False,))[0] for ep in critical_endpoints)

if critical_passed:
    print("\n✅ TÜM KRİTİK ENDPOINT'LER ÇALIŞIYOR!")
else:
    print("\n⚠️ BAZI KRİTİK ENDPOINT'LER BAŞARISIZ!")
    failed_critical = [ep for ep in critical_endpoints if not results.get(ep, (False,))[0]]
    print(f"   Başarısız kritik endpoint'ler: {failed_critical}")

# Performance test (opsiyonel)
if passed_tests > 5:
    print("\n" + "="*50)
    print("PERFORMANCE TEST")
    print("="*50)
    
    print("\n[PERFORMANCE] Status endpoint 10 kez çağrılıyor...")
    times = []
    for i in range(10):
        start = time.time()
        response = requests.get(f"{BASE_URL}/api/status")
        elapsed = time.time() - start
        times.append(elapsed)
        print(f"   Request {i+1}: {elapsed:.3f}s")
    
    avg_time = sum(times) / len(times)
    print(f"\n📊 Ortalama yanıt süresi: {avg_time:.3f} saniye")
    
    if avg_time < 0.1:
        print("✅ Performans MÜKEMMEL (<100ms)")
    elif avg_time < 0.5:
        print("✅ Performans İYİ (<500ms)")
    else:
        print("⚠️ Performans YAVAŞ (>500ms)")