import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
import os
from dotenv import load_dotenv

# .env dosyasını yükle
load_dotenv()

async def test_connection():
    # .env'den URI'yi al
    uri = os.getenv('MONGODB_URI')
    print(f"📡 Bağlantı URI: {uri}")
    
    try:
        print("🔄 MongoDB'ye bağlanılıyor...")
        client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
        
        # Bağlantıyı test et
        await client.admin.command('ping')
        print("✅ MongoDB bağlantısı BAŞARILI!")
        
        # Database listele
        db_list = await client.list_database_names()
        print(f"📚 Mevcut veritabanları: {db_list}")
        
        # Test verisi ekle
        db = client.anomaly_detection
        test_collection = db.test_connection
        
        test_doc = {
            "test": True,
            "timestamp": datetime.now(),
            "message": "MongoDB bağlantı testi başarılı!"
        }
        
        result = await test_collection.insert_one(test_doc)
        print(f"✅ Test verisi eklendi! ID: {result.inserted_id}")
        
        # Veriyi oku
        doc = await test_collection.find_one({"test": True})
        print(f"📖 Okunan veri: {doc['message']}")
        
        # Test verisini sil
        await test_collection.delete_one({"_id": result.inserted_id})
        print("🗑️ Test verisi temizlendi")
        
        print("\n🎉 TÜM TESTLER BAŞARILI! MongoDB hazır!")
        
    except Exception as e:
        print(f"❌ HATA: {e}")
    finally:
        client.close()

if __name__ == "__main__":
    asyncio.run(test_connection())