import asyncio
from src.storage.storage_manager import StorageManager

async def test_fix():
    """Düzeltme doğrulama testi"""
    
    # Gerçek API response yapısı
    real_api_response = {
        "durum": "tamamlandı",
        "işlem": "anomaly_analysis",
        "açıklama": "Fix test",
        "sonuç": {  # "sonuç" key'i kullanılıyor
            "summary": {
                "total_logs": 9999,
                "n_anomalies": 77,
                "anomaly_rate": 0.77
            },
            "critical_anomalies": [
                {"log": "Critical 1", "score": 0.99},
                {"log": "Critical 2", "score": 0.98},
                {"log": "Critical 3", "score": 0.97},
                {"log": "Critical 4", "score": 0.96},
                {"log": "Critical 5", "score": 0.95}
            ],
            "logs_analyzed": 9999,
            "filtered_logs": 9500
        }
    }
    
    print("🔧 FIX TEST BAŞLADI")
    print("-" * 50)
    print(f"Test verisi hazır:")
    print(f"- Total logs: {real_api_response['sonuç']['summary']['total_logs']}")
    print(f"- Anomalies: {real_api_response['sonuç']['summary']['n_anomalies']}")
    print(f"- Critical count: {len(real_api_response['sonuç']['critical_anomalies'])}")
    
    storage = StorageManager()
    await storage.initialize()
    
    # Kaydet
    save_result = await storage.save_anomaly_analysis(
        real_api_response,
        source_type="opensearch",
        host="fix_test_host",
        time_range="last_hour"
    )
    
    print(f"\n✅ Kayıt ID: {save_result.get('analysis_id')}")
    
    # MongoDB'den oku
    if save_result.get('analysis_id'):
        history = await storage.get_anomaly_history(
            filters={"analysis_id": save_result['analysis_id']},
            limit=1
        )
        
        if history:
            record = history[0]
            print("\n📊 MongoDB'DEN OKUNAN:")
            print(f"✓ anomaly_count: {record.get('anomaly_count')} (beklenen: 77)")
            print(f"✓ critical_count: {record.get('critical_count')} (beklenen: 5)")
            print(f"✓ logs_analyzed: {record.get('logs_analyzed')} (beklenen: 9999)")
            print(f"✓ filtered_logs: {record.get('filtered_logs')} (beklenen: 9500)")
            
            # Başarı kontrolü
            if record.get('anomaly_count') == 77 and record.get('critical_count') == 5:
                print("\n🎉 BAŞARILI - DÜZELTME ÇALIŞIYOR!")
            else:
                print("\n❌ HALA SORUN VAR!")
    
    await storage.shutdown()

asyncio.run(test_fix())