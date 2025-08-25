import os
import sys
sys.path.append('.')
from dotenv import load_dotenv
load_dotenv()

print("OpenSearch Test Başlıyor...")
print("-" * 50)

# Önce environment variables kontrol edelim
print(f"OPENSEARCH_URL: {os.getenv('OPENSEARCH_URL')}")
print(f"OPENSEARCH_USER: {os.getenv('OPENSEARCH_USER')}")
print(f"OPENSEARCH_PASS: {'***' if os.getenv('OPENSEARCH_PASS') else 'YOK'}")
print("-" * 50)

try:
    from src.anomaly.log_reader import OpenSearchLogReader
    
    # Test OpenSearch connection
    print("OpenSearchLogReader oluşturuluyor...")
    reader = OpenSearchLogReader(
        host_filter="lcwmongodb01n1.lcwaikiki.local",
        time_range="last_day"
    )
    
    print("Log çekme denemesi...")
    logs = reader.get_logs(limit=5)
    print(f"✅ Toplam log sayısı: {len(logs)}")
    
    if logs:
        print("\n📝 İlk log örneği:")
        import json
        print(json.dumps(logs[0], indent=2, default=str)[:500])
    else:
        print("❌ Hiç log bulunamadı!")
        
except Exception as e:
    print(f"❌ HATA: {e}")
    import traceback
    traceback.print_exc()