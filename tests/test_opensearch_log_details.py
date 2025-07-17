import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.anomaly.log_reader import OpenSearchProxyReader
import logging

# Logging ayarla
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

print("🔍 OpenSearch MongoDB Log Detaylı Analizi")
print("=" * 60)

# Reader'ı başlat ve bağlan
reader = OpenSearchProxyReader()
if reader.connect():
    print("✅ Bağlantı başarılı!")
    
    # Son 1 saatteki 5 log oku
    df = reader.read_logs(limit=5, last_hours=1)
    
    print(f"\n📊 Toplam {len(df)} log okundu")
    print("\n=== DETAYLI LOG ANALİZİ ===")
    
    for i in range(min(5, len(df))):
        print(f"\n{'='*60}")
        print(f"📌 LOG {i+1}")
        print(f"{'='*60}")
        
        log = df.iloc[i]
        
        print(f"🖥️  Host: {log.get('host', 'N/A')}")
        print(f"📅 Timestamp: {log.get('t', {}).get('$date', 'N/A')}")
        print(f"🏷️  Component: {log.get('c', 'N/A')}")
        print(f"⚠️  Severity: {log.get('s', 'N/A')}")
        print(f"🔗 Context: {log.get('ctx', 'N/A')}")
        print(f"💬 Message: {log.get('msg', 'N/A')[:200]}...")
        
        # Attributes varsa göster
        if 'attr' in log and log['attr'] and isinstance(log['attr'], dict):
            print(f"📎 Attributes:")
            for key, value in log['attr'].items():
                print(f"   - {key}: {value}")
        
        # ID varsa göster
        if 'id' in log:
            print(f"🆔 ID: {log.get('id', 'N/A')}")
    
    # Component dağılımı
    print(f"\n\n📊 COMPONENT DAĞILIMI:")
    if 'c' in df.columns:
        component_counts = df['c'].value_counts()
        for comp, count in component_counts.items():
            print(f"   {comp}: {count}")
    
    # Host dağılımı
    print(f"\n📊 HOST DAĞILIMI:")
    if 'host' in df.columns:
        host_counts = df['host'].value_counts()
        for host, count in host_counts.items():
            print(f"   {host}: {count}")
            
else:
    print("❌ Bağlantı başarısız!")