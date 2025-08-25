import asyncio
import json
from datetime import datetime

async def test_api_response():
    """API response yapısını test et"""
    
    # API'den gelen gerçek response simülasyonu
    api_response = {
        "durum": "tamamlandı",
        "işlem": "anomaly_analysis", 
        "açıklama": "Test",
        "sonuç": {  # Dikkat: "sonuç" key'i
            "summary": {
                "total_logs": 5000,
                "n_anomalies": 25,
                "anomaly_rate": 0.5
            },
            "critical_anomalies": [
                {"log": "Real anomaly 1", "score": 0.95},
                {"log": "Real anomaly 2", "score": 0.85},
                {"log": "Real anomaly 3", "score": 0.75}
            ],
            "logs_analyzed": 5000,
            "filtered_logs": 4800
        }
    }
    
    print("API Response yapısı:")
    print(f"- Keys: {list(api_response.keys())}")
    print(f"- sonuç keys: {list(api_response['sonuç'].keys())}")
    print(f"- critical_anomalies count: {len(api_response['sonuç']['critical_anomalies'])}")
    
    # Storage Manager'ı test et
    from src.storage.storage_manager import StorageManager
    
    storage = StorageManager()
    await storage.initialize()
    
    # Normalize fonksiyonunu test et
    normalized = storage._normalize_analysis_result(
        api_response,
        {"source_type": "opensearch", "host": "test", "time_range": "test"}
    )
    
    print("\nNormalized sonuç:")
    print(f"- Keys: {list(normalized.keys())}")
    print(f"- sonuç keys: {list(normalized.get('sonuç', {}).keys())}")
    
    # Kaydet
    save_result = await storage.save_anomaly_analysis(
        api_response,
        source_type="opensearch",
        host="api_test_host",
        time_range="last_hour"
    )
    
    print(f"\nKayıt sonucu: {save_result.get('analysis_id')}")
    
    # Geri oku
    if save_result.get('analysis_id'):
        history = await storage.get_anomaly_history(
            filters={"analysis_id": save_result['analysis_id']},
            limit=1
        )
        
        if history:
            print(f"\nMongoDB'den okunan:")
            print(f"- anomaly_count: {history[0].get('anomaly_count')}")
            print(f"- critical_count: {history[0].get('critical_count')}")
            print(f"- logs_analyzed: {history[0].get('logs_analyzed')}")
    
    await storage.shutdown()

asyncio.run(test_api_response())