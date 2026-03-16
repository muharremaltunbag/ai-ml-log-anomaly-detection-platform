import os
import sys
import asyncio
from datetime import datetime
from dotenv import load_dotenv

# Load environment
load_dotenv()

print("=" * 60)
print("STORAGE VE OPENSEARCH TEST")
print("=" * 60)

async def test_storage():
    """Test MongoDB storage"""
    from src.storage.storage_manager import StorageManager
    
    print("\n1. STORAGE MANAGER TESTİ")
    print("-" * 40)
    
    storage = StorageManager()
    connected = await storage.initialize()
    
    if connected:
        print("✅ MongoDB bağlantısı başarılı")
        
        # Test data
        test_result = {
            "durum": "test",
            "işlem": "test_analysis",
            "açıklama": "Test anomaly analysis",
            "sonuç": {
                "summary": {
                    "total_logs": 100,
                    "n_anomalies": 5,
                    "anomaly_rate": 5.0
                },
                "critical_anomalies": [
                    {"log": "Test anomaly 1", "score": 0.9},
                    {"log": "Test anomaly 2", "score": 0.8}
                ]
            }
        }
        
        # Save test
        save_result = await storage.save_anomaly_analysis(
            test_result,
            source_type="test",
            host="test_host",
            time_range="test_range"
        )
        
        if save_result.get('analysis_id'):
            print(f"✅ Test kaydı başarılı - ID: {save_result['analysis_id']}")
            
            # Read back
            history = await storage.get_anomaly_history(limit=1)
            if history:
                print(f"✅ Kayıt okundu - Anomaly count: {history[0].get('anomaly_count')}")
        else:
            print("❌ Test kaydı başarısız")
    else:
        print("❌ MongoDB bağlantısı başarısız")
    
    await storage.shutdown()

def test_opensearch():
    """Test OpenSearch connection"""
    print("\n2. OPENSEARCH TESTİ")
    print("-" * 40)
    
    try:
        from src.anomaly.log_reader import OpenSearchLogReader
        
        reader = OpenSearchLogReader(
            host_filter="mongo-prod-02.internal.local",
            time_range="last_hour"
        )
        
        logs = reader.get_logs(limit=5)
        print(f"✅ OpenSearch bağlantısı başarılı - {len(logs)} log bulundu")
        
        if logs:
            print(f"   İlk log timestamp: {logs[0].get('timestamp', 'N/A')}")
    except Exception as e:
        print(f"❌ OpenSearch hatası: {e}")

# Run tests
if __name__ == "__main__":
    # Test Storage
    asyncio.run(test_storage())
    
    # Test OpenSearch
    test_opensearch()
    
    print("\n" + "=" * 60)
    print("TEST TAMAMLANDI")
    print("=" * 60)