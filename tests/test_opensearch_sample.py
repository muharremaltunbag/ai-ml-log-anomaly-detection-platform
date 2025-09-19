import os
import json
import pandas as pd
from src.anomaly.log_reader import OpenSearchProxyReader

print("🔎 OpenSearch Basit Test Başlıyor...")
print("-" * 60)
print(f"OPENSEARCH_URL: {os.getenv('OPENSEARCH_URL')}")
print(f"OPENSEARCH_USER: {os.getenv('OPENSEARCH_USER')}")
print(f"OPENSEARCH_PASS: {'***' if os.getenv('OPENSEARCH_PASS') else 'YOK'}")
print("-" * 60)

try:
    reader = OpenSearchProxyReader()
    if not reader.connect():
        print("❌ OpenSearch bağlantısı kurulamadı!")
        exit(1)

    print("📥 Son 1 saatten 5 log çekiliyor...")
    logs_df = reader.read_logs(limit=5, last_hours=1)

    if logs_df.empty:
        print("❌ Hiç log bulunamadı!")
    else:
        print(f"✅ {len(logs_df)} log alındı\n")
        print("📝 Log özeti:")
        for _, row in logs_df.iterrows():
            ts = row['t']['$date'] if 't' in row else row.get('@timestamp', 'N/A')
            host = row.get('host', 'unknown')
            msg = row.get('msg') or row.get('message', '')[:80]
            print(f"[{ts}] {host} - {msg}")

except Exception as e:
    print(f"❌ HATA: {e}")
    import traceback
    traceback.print_exc()
