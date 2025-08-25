from src.anomaly.log_reader import OpenSearchProxyReader
from datetime import datetime

def test_actual_reader():
    """Gerçek kullanım testi"""
    
    print("GERÇEK LOG READER TESTİ")
    print("=" * 50)
    
    # Reader'ı doğru şekilde oluştur
    reader = OpenSearchProxyReader()
    
    # Bağlan
    if not reader.connect():
        print("❌ OpenSearch bağlantısı başarısız!")
        return
    
    print("✅ OpenSearch bağlantısı başarılı")
    
    # Test 1: Limit ile
    print("\n1. TEST: Limit=100")
    df1 = reader.read_logs(limit=100, last_hours=1)
    print(f"   Dönen log sayısı: {len(df1)}")
    
    # Test 2: Host filter ile
    print("\n2. TEST: Host filter + limit=100")
    df2 = reader.read_logs(
        limit=100, 
        last_hours=1, 
        host_filter="lcwmongodb01n3.lcwaikiki.local"
    )
    print(f"   Dönen log sayısı: {len(df2)}")
    
    # Test 3: Limit olmadan (scroll)
    print("\n3. TEST: Limit yok (scroll mode)")
    df3 = reader.read_logs(
        limit=None,  # Scroll kullanacak
        last_hours=1,
        host_filter="lcwmongodb01n3.lcwaikiki.local"
    )
    print(f"   Dönen log sayısı: {len(df3)}")
    
    # Host listesi
    print("\n4. TEST: Mevcut hostlar")
    hosts = reader.get_available_hosts(last_hours=24)
    for host in hosts[:5]:
        print(f"   - {host}")

test_actual_reader()