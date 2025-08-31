"""
MongoDB Bağlantı Test Script
Kullanım: python test_mongodb_connection.py
"""
import asyncio
import sys
from datetime import datetime

# Path'i ayarla
sys.path.append('.')

from src.storage.storage_manager import StorageManager

async def test_mongodb():
    print("=" * 60)
    print("MongoDB BAĞLANTI TESTİ")
    print("=" * 60)
    
    try:
        # Storage Manager'ı başlat
        print("\n1. Storage Manager başlatılıyor...")
        manager = StorageManager()
        
        # MongoDB'ye bağlan
        print("2. MongoDB'ye bağlanılıyor...")
        connected = await manager.initialize()
        
        if connected:
            print("✅ MongoDB BAĞLANTI BAŞARILI!")
            
            # Test verisi oluştur
            print("\n3. Test verisi yazılıyor...")
            test_data = {
                "durum": "test",
                "işlem": "connection_test",
                "açıklama": f"Test zamanı: {datetime.now()}",
                "sonuç": {
                    "summary": {
                        "total_logs": 100,
                        "n_anomalies": 5,
                        "anomaly_rate": 5.0
                    },
                    "critical_anomalies": [
                        {"message": "Test anomali 1", "score": -0.8},
                        {"message": "Test anomali 2", "score": -0.7}
                    ]
                }
            }
            
            # MongoDB'ye kaydet
            result = await manager.save_anomaly_analysis(
                test_data, 
                source_type="test",
                host="test_host",
                time_range="test_range",
                auto_save=True
            )
            
            if result.get("analysis_id"):
                print(f"✅ YAZMA TESTİ BAŞARILI!")
                print(f"   Analysis ID: {result['analysis_id']}")
                print(f"   File Path: {result.get('file_path', 'N/A')}")
                
                # Veriyi geri oku
                print("\n4. Veri geri okunuyor...")
                history = await manager.get_anomaly_history(
                    filters={"analysis_id": result["analysis_id"]},
                    limit=1,
                    include_details=True
                )
                
                if history:
                    print(f"✅ OKUMA TESTİ BAŞARILI!")
                    print(f"   Kayıt bulundu: {history[0].get('analysis_id')}")
                    print(f"   Anomali sayısı: {history[0].get('anomaly_count', 'N/A')}")
                    
                    # Son 5 kaydı listele
                    print("\n5. Son 5 kayıt listeleniyor...")
                    recent = await manager.get_anomaly_history(limit=5)
                    print(f"   Toplam {len(recent)} kayıt bulundu:")
                    for i, rec in enumerate(recent, 1):
                        print(f"   {i}. {rec.get('analysis_id')} - {rec.get('created_at')}")
                else:
                    print("❌ OKUMA TESTİ BAŞARISIZ - Kayıt okunamadı")
            else:
                print("❌ YAZMA TESTİ BAŞARISIZ - Analysis ID alınamadı")
        else:
            print("❌ MongoDB BAĞLANTI BAŞARISIZ!")
            print("   Lütfen MongoDB bağlantı ayarlarını kontrol edin.")
            print("   MongoDB çalışıyor mu? Port açık mı?")
        
        # Bağlantıyı kapat
        await manager.shutdown()
        print("\n✅ Test tamamlandı")
        
    except Exception as e:
        print(f"\n❌ TEST HATASI: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_mongodb())