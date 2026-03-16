# test_opensearch_anomaly.py
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.anomaly.anomaly_tools import AnomalyDetectionTools
import json

def test_opensearch_anomaly_analysis():
    print("="*60)
    print("OpenSearch Anomali Analizi Testi")
    print("="*60)
    
    # Tools instance oluştur
    tools = AnomalyDetectionTools(environment="test")
    
    # Test 1: 1 saatlik veri ile anomali analizi
    print("\n1. Test: 1 saatlik veri anomali analizi...")
    result = tools.analyze_mongodb_logs({
        "source_type": "opensearch",
        "time_range": "last_hour",
        "threshold": 0.03
    })
    
    # Sonucu parse et
    result_dict = json.loads(result)
    print(f"✓ Durum: {result_dict['durum']}")
    print(f"✓ İşlem: {result_dict['işlem']}")
    
    if result_dict['durum'] == 'başarılı':
        sonuc = result_dict['sonuç']
        print(f"\n📊 Analiz Sonuçları:")
        print(f"  - Kaynak: {sonuc['source']}")
        print(f"  - Analiz edilen log sayısı: {sonuc['logs_analyzed']:,}")
        print(f"  - Filtrelenen log sayısı: {sonuc['filtered_logs']:,}")
        
        summary = sonuc['summary']
        print(f"\n📈 Anomali Özeti:")
        print(f"  - Toplam log: {summary['total_logs']:,}")
        print(f"  - Anomali sayısı: {summary['n_anomalies']}")
        print(f"  - Anomali oranı: %{summary['anomaly_rate']:.2f}")
        print(f"  - Ortalama anomali skoru: {summary['score_range']['mean']:.4f}")
        
        # Kritik anomaliler
        if sonuc['critical_anomalies']:
            print(f"\n⚠️ İlk 3 Kritik Anomali:")
            for i, anomaly in enumerate(sonuc['critical_anomalies'][:3], 1):
                print(f"  {i}. Component: {anomaly.get('component', 'N/A')}")
                print(f"     Skor: {anomaly.get('score', 0):.4f}")
                print(f"     Mesaj: {anomaly.get('message', '')[:80]}...")
    
    # Test 2: 24 saatlik veri ile anomali analizi
    print("\n" + "="*60)
    print("2. Test: 24 saatlik veri anomali analizi...")
    result_24h = tools.analyze_mongodb_logs({
        "source_type": "opensearch",
        "time_range": "last_24h",
        "threshold": 0.03
    })
    
    result_dict_24h = json.loads(result_24h)
    if result_dict_24h['durum'] == 'başarılı':
        sonuc_24h = result_dict_24h['sonuç']
        print(f"\n📊 24 Saatlik Analiz:")
        print(f"  - Toplam log: {sonuc_24h['logs_analyzed']:,}")
        print(f"  - Anomali sayısı: {sonuc_24h['summary']['n_anomalies']}")
        print(f"  - Anomali oranı: %{sonuc_24h['summary']['anomaly_rate']:.2f}")
        
        # Component analizi
        if 'component_analysis' in sonuc_24h:
            print(f"\n🔧 Component Bazlı Anomali Dağılımı:")
            comp_analysis = sonuc_24h['component_analysis']
            sorted_comps = sorted(comp_analysis.items(), 
                                key=lambda x: x[1]['anomaly_count'], 
                                reverse=True)[:5]
            for comp, stats in sorted_comps:
                print(f"  - {comp}: {stats['anomaly_count']} anomali (%{stats['anomaly_rate']:.1f})")
    
    # Test 3: Belirli bir host için analiz
    print("\n" + "="*60)
    print("3. Test: Belirli host için anomali analizi...")
    result_host = tools.analyze_mongodb_logs({
        "source_type": "opensearch", 
        "time_range": "last_24h",
        "threshold": 0.03,
        "host_filter": "mongo-prod-01"
    })
    
    result_dict_host = json.loads(result_host)
    if result_dict_host['durum'] == 'başarılı':
        print(f"✓ mongo-prod-01 için analiz tamamlandı")
        sonuc_host = result_dict_host['sonuç']
        print(f"  - Log sayısı: {sonuc_host['logs_analyzed']:,}")
        print(f"  - Anomali sayısı: {sonuc_host['summary']['n_anomalies']}")
    
    print("\n✅ Tüm testler tamamlandı!")

if __name__ == "__main__":
    test_opensearch_anomaly_analysis()