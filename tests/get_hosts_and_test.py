from src.anomaly.log_reader import OpenSearchProxyReader
from src.anomaly.anomaly_tools import AnomalyDetectionTools
import json

def test_with_host():
    print("HOST LIST AND TEST")
    print("=" * 50)
    
    # 1. Host listesini al
    reader = OpenSearchProxyReader()
    if not reader.connect():
        print("❌ OpenSearch bağlantısı başarısız!")
        return
    
    print("✅ OpenSearch bağlantısı başarılı\n")
    
    # Host'ları listele
    hosts = reader.get_available_hosts(last_hours=1)
    print(f"📋 Son 1 saatte log üreten {len(hosts)} host bulundu:\n")
    
    for i, host in enumerate(hosts[:10], 1):
        print(f"  {i}. {host}")
    
    if not hosts:
        print("❌ Hiç host bulunamadı!")
        return
    
    # İlk host'u seç
    selected_host = hosts[0]
    print(f"\n🎯 Test için seçilen host: {selected_host}")
    
    # 2. Anomaly detection test
    print("\n" + "="*50)
    print("ANOMALY DETECTION TEST")
    print("="*50)
    
    tools = AnomalyDetectionTools()
    
    result_str = tools.analyze_mongodb_logs({
        "source_type": "opensearch",
        "time_range": "last_hour",
        "host_filter": selected_host  # Host filter eklendi
    })
    
    result = json.loads(result_str)
    
    if result.get('durum') == 'başarılı':
        print(f"✅ BAŞARILI!")
        print(f"   Logs analyzed: {result['sonuç'].get('logs_analyzed', 0):,}")
        print(f"   Filtered logs: {result['sonuç'].get('filtered_logs', 0):,}")
        print(f"   Anomalies: {result['sonuç']['summary'].get('n_anomalies', 0):,}")
        print(f"   Critical anomalies: {len(result['sonuç'].get('critical_anomalies', []))}")
    else:
        print(f"❌ HATA: {result.get('açıklama')}")

if __name__ == "__main__":
    test_with_host()