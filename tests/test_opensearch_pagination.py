# test_opensearch_pagination.py
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.anomaly.log_reader import OpenSearchProxyReader

def test_opensearch_pagination():
    print("="*60)
    print("OpenSearch Pagination 30 Günlük Test Başlıyor...")
    print("="*60)
    
    # Test için reader oluştur
    reader = OpenSearchProxyReader()
    
    # 1. Bağlantı testi
    print("\n1. Bağlantı testi...")
    if reader.connect():
        print("✓ Bağlantı başarılı")
    else:
        print("✗ Bağlantı başarısız - .env dosyasını kontrol edin")
        return

    
    # # 2. 1 saatlik veri ile test
    # print("\n2. 1 saatlik veri testi...")
    # df = reader.read_logs(limit=None, last_hours=1)
    # print(f"✓ Çekilen log sayısı: {len(df)}")
    
    # # 3. 24 saatlik veri testi
    # print("\n3. 24 saatlik veri testi (20K+ bekleniyor)...")
    # df_24h = reader.read_logs(limit=None, last_hours=24)
    # print(f"✓ Çekilen log sayısı: {len(df_24h)}")
    # print(f"✓ 20K limiti aşıldı mı? {'EVET ✅' if len(df_24h) > 20000 else 'HAYIR ❌'}")
    
    # 4. Mevcut host'ları listele
    print("\n4. Mevcut MongoDB host'ları...")
    hosts = reader.get_available_hosts(last_hours=24)
    print(f"✓ Bulunan host sayısı: {len(hosts)}")
    if hosts:
        print(f"✓ İlk 3 host: {hosts[:3]}")
        
        # 5. İlk host için test
        print(f"\n5. Host filtreleme testi ({hosts[0]})...")
        df_host = reader.read_logs(limit=None, last_hours=24, host_filter=hosts[0])
        print(f"✓ {hosts[0]} için log sayısı: {len(df_host)}")

    # 6. 1 aylık (30 gün) veri testi
    print("\n6. 1 aylık veri testi (30 gün = 720 saat)...")
    print("⏳ Bu test biraz uzun sürebilir...")
    
    import time
    start_time = time.time()
    
    df_month = reader.read_logs(limit=None, last_hours=720)  # 30 gün
    
    elapsed_time = time.time() - start_time
    
    print(f"✓ Çekilen log sayısı: {len(df_month):,}")
    print(f"✓ İşlem süresi: {elapsed_time:.2f} saniye")
    print(f"✓ Saniyede işlenen log: {len(df_month)/elapsed_time:.0f}")
    
    # DataFrame boyut bilgisi
    if len(df_month) > 0:
        memory_usage = df_month.memory_usage(deep=True).sum() / 1024 / 1024
        print(f"✓ DataFrame bellek kullanımı: {memory_usage:.2f} MB")
        
        # Zaman aralığı kontrolü
        if 't' in df_month.columns:
            print(f"✓ İlk log zamanı: {df_month['t'].iloc[0]}")
            print(f"✓ Son log zamanı: {df_month['t'].iloc[-1]}")
    
    print("\n" + "="*60)
    print("Test tamamlandı!")
    print("="*60)

if __name__ == "__main__":
    test_opensearch_pagination()