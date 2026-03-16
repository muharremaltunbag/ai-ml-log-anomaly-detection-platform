import time
from datetime import datetime
from src.anomaly.log_reader import OpenSearchProxyReader

def test_consistency():
    """Log tutarlılık testi"""
    
    host = "mongo-prod-03.internal.local"
    results = []
    
    print(f"Test Host: {host}")
    print("-" * 50)
    
    for i in range(3):
        print(f"\nDeneme {i+1} - {datetime.now().strftime('%H:%M:%S')}")
        
        reader = OpenSearchProxyReader(
            host_filter=host,
            time_range="last_day"
        )
        
        # Login ve tenant seçimi
        reader._login()
        reader._select_tenant()
        
        # Log oku
        logs = reader.get_logs(limit=10000)  # Max 10000
        count = len(logs)
        results.append(count)
        
        print(f"  Log sayısı: {count}")
        
        if count < 100:
            print(f"  ⚠️ UYARI: Çok az log! Bir sorun var!")
            # İlk birkaç logu göster
            if logs:
                print(f"  İlk log: {logs[0].get('timestamp', 'N/A')}")
                print(f"  Son log: {logs[-1].get('timestamp', 'N/A')}")
        
        time.sleep(2)
    
    print("\n" + "=" * 50)
    print(f"SONUÇLAR: {results}")
    print(f"Ortalama: {sum(results)/len(results):.0f}")

test_consistency()