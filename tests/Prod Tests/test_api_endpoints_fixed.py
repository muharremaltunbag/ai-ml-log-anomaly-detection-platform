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
API_KEY = os.getenv("API_KEY", "lcw-test-2024")  # .env'den veya default

print("=" * 50)
print("API ENDPOINT TESTS (FIXED)")
print("=" * 50)
print(f"API_KEY: {API_KEY[:10]}...")

def test_endpoint(method, endpoint, data=None, params=None, description=""):
    """Helper function for testing endpoints"""
    url = f"{BASE_URL}{endpoint}"
    print(f"\n[TEST] {description}")
    print(f"   {method} {url}")
    
    try:
        if method == "GET":
            response = requests.get(url, params=params)
        elif method == "POST":
            response = requests.post(url, json=data, params=params)
        else:
            response = requests.request(method, url, json=data)
        
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            print("   ✅ SUCCESS")
            # Content type'a göre parse et
            content_type = response.headers.get('content-type', '')
            if 'application/json' in content_type:
                return True, response.json()
            elif 'text/html' in content_type:
                # HTML response için başarılı kabul et
                return True, {"html": "HTML content received"}
            else:
                return True, response.text
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

# Root endpoint - HTML bekliyoruz, JSON değil
results['root'] = test_endpoint(
    "GET", "/",
    description="Root endpoint (HTML expected)"
)

results['status'] = test_endpoint(
    "GET", "/api/status",
    description="API Status"
)

# 2. ML MODEL ENDPOINTS
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

# 4. ANOMALY ANALYSIS
print("\n" + "="*50)
print("4. ANOMALY ANALYSIS ENDPOINTS")
print("="*50)

# Host listesini al
success, hosts_data = results['hosts']
if success and hosts_data and hosts_data.get('hosts'):
    test_host = hosts_data['hosts'][0]
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

# 6. DBA SPECIFIC ENDPOINTS - DÜZELTİLMİŞ
print("\n" + "="*50)
print("6. DBA ANALYSIS ENDPOINTS (FIXED)")
print("="*50)

if success and hosts_data and hosts_data.get('hosts'):
    # DBA endpoint - Query params OLARAK gönder (POST body değil)
    dba_params = {
        "host": test_host,
        "start_time": (datetime.now() - timedelta(hours=2)).isoformat() + "Z",
        "end_time": datetime.now().isoformat() + "Z",
        "api_key": API_KEY,
        "auto_explain": False
    }
    
    # POST yerine query parameters ile
    results['dba_analyze'] = test_endpoint(
        "POST", f"/api/dba/analyze-specific-time"
               f"?host={dba_params['host']}"
               f"&start_time={dba_params['start_time']}"
               f"&end_time={dba_params['end_time']}"
               f"&api_key={dba_params['api_key']}"
               f"&auto_explain={dba_params['auto_explain']}",
        description="DBA Specific Time Analysis (FIXED)"
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

# Sunucu adı ile birlikte query gönder
if success and hosts_data and hosts_data.get('hosts'):
    query_data = {
        "query": f"{hosts_data['hosts'][0]} sunucusu için MongoDB loglarında anomali analizi yap",
        "api_key": API_KEY
    }
else:
    query_data = {
        "query": "MongoDB loglarında anomali analizi yap",
        "api_key": API_KEY
    }

results['query'] = test_endpoint(
    "POST", "/api/query",
    data=query_data,
    description="Process Query (with server name)"
)

# 8. COLLECTIONS
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

# Detaylı sonuçlar
print("\nDetaylı Sonuçlar:")
for test_name, (success, data) in results.items():
    status = "✅" if success else "❌"
    print(f"  {status} {test_name}")
    if not success and data:
        print(f"      Hata: {str(data)[:100]}")

# Kritik endpoint kontrolü
critical_endpoints = ['status', 'ml_model_info', 'hosts', 'anomaly_history']
critical_passed = all(results.get(ep, (False,))[0] for ep in critical_endpoints)

if critical_passed:
    print("\n✅ TÜM KRİTİK ENDPOINT'LER ÇALIŞIYOR!")
else:
    print("\n⚠️ BAZI KRİTİK ENDPOINT'LER BAŞARISIZ!")
    failed_critical = [ep for ep in critical_endpoints if not results.get(ep, (False,))[0]]
    print(f"   Başarısız kritik endpoint'ler: {failed_critical}")

# Tüm testler başarılı mı?
if passed_tests == total_tests:
    print("\n" + "="*50)
    print("🎉 TÜM TESTLER BAŞARILI!")
    print("="*50)
    print("Sistem tamamen fonksiyonel durumda!")