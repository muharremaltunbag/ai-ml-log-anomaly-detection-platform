# tests/test_opensearch_connection_deep.py

import sys
import os
from pathlib import Path

# Project root'u bul ve sys.path'e ekle
current_file = Path(__file__).resolve()
project_root = current_file.parent.parent.parent  # tests/Prod Tests -> tests -> project_root
sys.path.insert(0, str(project_root))

print(f"[DEBUG] Current file: {current_file}")
print(f"[DEBUG] Project root: {project_root}")
print(f"[DEBUG] Python path: {sys.path[0]}")

# Şimdi import'ları yap
try:
    from src.anomaly.log_reader import OpenSearchProxyReader
    print("[DEBUG] Import successful!")
except ImportError as e:
    print(f"[ERROR] Import failed: {e}")
    print(f"[DEBUG] Looking for src in: {project_root / 'src'}")
    print(f"[DEBUG] Directory exists: {(project_root / 'src').exists()}")
    if (project_root / 'src').exists():
        print(f"[DEBUG] src contents: {list((project_root / 'src').iterdir())}")
    sys.exit(1)

from dotenv import load_dotenv
import pandas as pd
import json
import time
from datetime import datetime, timedelta
import logging

# Logging setup
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_opensearch_connection():
    """OpenSearch bağlantı testi"""
    print("\n" + "="*60)
    print("OpenSearch Bağlantı Testi")
    print("="*60)
    
    # .env yükle
    load_dotenv()
    
    # Reader oluştur
    reader = OpenSearchProxyReader()
    
    # Test 1: Login
    print("\n[TEST 1] Login Test...")
    login_success = reader._login()
    print(f"✅ Login: {'SUCCESS' if login_success else 'FAILED'}")
    
    if not login_success:
        print("❌ Login başarısız! Credentials kontrol edilmeli.")
        return False
    
    # Test 2: Tenant Selection
    print("\n[TEST 2] Tenant Selection Test...")
    tenant_success = reader._select_tenant()
    print(f"✅ Tenant (LCW): {'SELECTED' if tenant_success else 'FAILED'}")
    
    # Test 3: Full Connection
    print("\n[TEST 3] Full Connection Test...")
    connect_success = reader.connect()
    print(f"✅ Connection: {'ESTABLISHED' if connect_success else 'FAILED'}")
    
    return connect_success

def test_log_reading():
    """Log okuma ve parse testi"""
    print("\n" + "="*60)
    print("Log Okuma ve Parse Testi")
    print("="*60)
    
    reader = OpenSearchProxyReader()
    
    if not reader.connect():
        print("❌ Bağlantı kurulamadı!")
        return False
    
    # Test 4: İlk 10 logu oku
    print("\n[TEST 4] Reading first 10 logs...")
    df = reader.read_logs(limit=10, last_hours=1)
    
    if df.empty:
        print("❌ Log okunamadı!")
        return False
    
    print(f"✅ {len(df)} log okundu")
    
    # Log içeriğini analiz et
    print("\n[ANALYSIS] Log Structure:")
    print(f"  - Columns: {df.columns.tolist()}")
    
    # İlk logun detayları
    if not df.empty:
        first_log = df.iloc[0].to_dict()
        print("\n[SAMPLE] First log entry:")
        
        # Önemli alanları göster
        if 'host' in first_log:
            print(f"  - Host: {first_log['host']}")
        if 't' in first_log and '$date' in first_log['t']:
            print(f"  - Timestamp: {first_log['t']['$date']}")
        if 's' in first_log:
            print(f"  - Severity: {first_log['s']}")
        if 'c' in first_log:
            print(f"  - Component: {first_log['c']}")
        if 'msg' in first_log:
            msg = first_log['msg'][:100] + "..." if len(str(first_log['msg'])) > 100 else first_log['msg']
            print(f"  - Message: {msg}")
        if 'full_message' in first_log:
            full_msg = first_log['full_message'][:100] + "..." if len(str(first_log['full_message'])) > 100 else first_log['full_message']
            print(f"  - Extracted Message: {full_msg}")
    
    return True

def test_host_listing():
    """MongoDB host listesi testi"""
    print("\n" + "="*60)
    print("MongoDB Host Listesi Testi")
    print("="*60)
    
    reader = OpenSearchProxyReader()
    
    if not reader.connect():
        print("❌ Bağlantı kurulamadı!")
        return False
    
    # Test 5: Mevcut host'ları listele
    print("\n[TEST 5] Getting available MongoDB hosts...")
    hosts = reader.get_available_hosts(last_hours=24)
    
    if not hosts:
        print("❌ Host listesi alınamadı!")
        return False
    
    print(f"✅ {len(hosts)} MongoDB host bulundu:")
    
    # İlk 5 host'u göster
    for i, host in enumerate(hosts[:5], 1):
        print(f"  {i}. {host}")
    
    if len(hosts) > 5:
        print(f"  ... ve {len(hosts)-5} host daha")
    
    return True

def test_cluster_mapping():
    """Cluster mapping testi"""
    print("\n" + "="*60)
    print("Cluster Mapping Testi")
    print("="*60)
    
    from src.anomaly.log_reader import get_available_clusters_with_hosts
    
    # Test 6: Cluster gruplandırması
    print("\n[TEST 6] Getting cluster mappings...")
    cluster_info = get_available_clusters_with_hosts(last_hours=24)
    
    print(f"\n✅ Summary:")
    print(f"  - Total Hosts: {cluster_info['summary']['total_hosts']}")
    print(f"  - Clusters: {cluster_info['summary']['cluster_count']}")
    print(f"  - Standalone: {cluster_info['summary']['standalone_count']}")
    print(f"  - Unmapped: {cluster_info['summary']['unmapped_count']}")
    
    # Cluster detayları
    if cluster_info['clusters']:
        print("\n[CLUSTERS]")
        for cluster_id, cluster_data in list(cluster_info['clusters'].items())[:3]:
            print(f"  • {cluster_data['display_name']} ({cluster_data['environment']})")
            print(f"    - Nodes: {cluster_data['node_count']}")
            print(f"    - Hosts: {', '.join(cluster_data['hosts'][:2])}")
    
    return True

def test_performance():
    """Performans testi - büyük veri setleri"""
    print("\n" + "="*60)
    print("Performans Testi")
    print("="*60)
    
    reader = OpenSearchProxyReader()
    
    if not reader.connect():
        print("❌ Bağlantı kurulamadı!")
        return False
    
    # Test 7: 1000 log okuma süresi
    print("\n[TEST 7] Performance test - reading 1000 logs...")
    start_time = time.time()
    df = reader.read_logs(limit=1000, last_hours=1)
    elapsed = time.time() - start_time
    
    if not df.empty:
        print(f"✅ {len(df)} log {elapsed:.2f} saniyede okundu")
        print(f"  - Throughput: {len(df)/elapsed:.0f} logs/second")
        print(f"  - Memory usage: ~{df.memory_usage(deep=True).sum() / 1024 / 1024:.2f} MB")
    else:
        print("❌ Log okunamadı!")
        return False
    
    return True

def test_specific_timerange():
    """Belirli tarih aralığı testi"""
    print("\n" + "="*60)
    print("Spesifik Tarih Aralığı Testi")
    print("="*60)
    
    reader = OpenSearchProxyReader()
    
    if not reader.connect():
        print("❌ Bağlantı kurulamadı!")
        return False
    
    # Test 8: Son 15 dakikalık loglar
    print("\n[TEST 8] Reading logs from last 15 minutes...")
    
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(minutes=15)
    
    df = reader.read_logs(
        limit=100,
        start_time=start_time.isoformat() + 'Z',
        end_time=end_time.isoformat() + 'Z'
    )
    
    if not df.empty:
        print(f"✅ {len(df)} log bulundu (son 15 dakika)")
        
        # Severity dağılımı
        if 's' in df.columns:
            severity_dist = df['s'].value_counts()
            print("\n[SEVERITY DISTRIBUTION]")
            for sev, count in severity_dist.items():
                print(f"  - {sev}: {count}")
    else:
        print("⚠️ Son 15 dakikada log bulunamadı")
    
    return True

def main():
    """Ana test fonksiyonu"""
    print("\n" + "="*60)
    print("OpenSearch Deep Test Suite")
    print("="*60)
    
    tests = [
        ("Connection", test_opensearch_connection),
        ("Log Reading", test_log_reading),
        ("Host Listing", test_host_listing),
        ("Cluster Mapping", test_cluster_mapping),
        ("Performance", test_performance),
        ("Time Range", test_specific_timerange)
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            print(f"\n🔄 Running: {test_name}")
            result = test_func()
            results.append((test_name, result))
            print(f"{'✅' if result else '❌'} {test_name}: {'PASSED' if result else 'FAILED'}")
        except Exception as e:
            print(f"❌ {test_name}: EXCEPTION - {str(e)}")
            results.append((test_name, False))
            logger.exception(f"Test failed: {test_name}")
    
    # Final report
    print("\n" + "="*60)
    print("TEST REPORT")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)