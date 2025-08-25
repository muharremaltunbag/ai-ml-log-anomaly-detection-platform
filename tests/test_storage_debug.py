import asyncio
import json
from src.storage.storage_manager import StorageManager
import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

async def test_storage_debug():
    """Storage Manager debug testi"""
    
    # Test verisi (gerçek anomaly response gibi)
    test_result = {
        "durum": "tamamlandı",
        "işlem": "anomaly_analysis",
        "açıklama": "Test analizi",
        "data": {  # Dikkat: "data" key'i kullanıyoruz
            "summary": {
                "total_logs": 1000,
                "n_anomalies": 10,
                "anomaly_rate": 1.0
            },
            "critical_anomalies": [
                {"log": "Test anomaly 1", "score": 0.9},
                {"log": "Test anomaly 2", "score": 0.8}
            ],
            "logs_analyzed": 1000,
            "filtered_logs": 950
        }
    }
    
    print("Test verisi hazırlandı:")
    print(f"- summary: {test_result['data']['summary']}")
    print(f"- critical_anomalies count: {len(test_result['data']['critical_anomalies'])}")
    
    # Storage Manager'ı başlat
    storage = StorageManager()
    await storage.initialize()
    
    # Kaydet
    print("\nKaydetme işlemi başlıyor...")
    save_result = await storage.save_anomaly_analysis(
        test_result,
        source_type="test",
        host="test_host",
        time_range="test_range"
    )
    
    print(f"\nKayıt sonucu:")
    print(f"- Analysis ID: {save_result.get('analysis_id')}")
    
    # MongoDB'den geri oku
    if save_result.get('analysis_id'):
        history = await storage.get_anomaly_history(
            filters={"analysis_id": save_result['analysis_id']},
            limit=1
        )
        
        if history:
            print(f"\nMongoDB'den okunan:")
            print(f"- anomaly_count: {history[0].get('anomaly_count')}")
            print(f"- critical_count: {history[0].get('critical_count')}")
            print(f"- summary: {history[0].get('summary')}")
    
    await storage.shutdown()

# Çalıştır
asyncio.run(test_storage_debug())