from src.anomaly.anomaly_tools import AnomalyDetectionTools
import json

def test_api_direct():
    """API'yi direkt test et"""
    print("API DIRECT TEST")
    print("=" * 50)
    
    tools = AnomalyDetectionTools()
    
    # OpenSearch'ten veri çek
    args = {
        "source_type": "opensearch",
        "time_range": "last_hour",
        "host_filter": None
    }
    
    print(f"\nTest args: {args}")
    
    try:
        result_str = tools.analyze_mongodb_logs(args)
        result = json.loads(result_str)
        
        print(f"\nDurum: {result.get('durum')}")
        print(f"İşlem: {result.get('işlem')}")
        
        if result.get('durum') == 'hata':
            print(f"HATA: {result.get('açıklama')}")
        elif 'sonuç' in result:
            sonuc = result['sonuç']
            print(f"\nLogs analyzed: {sonuc.get('logs_analyzed', 0)}")
            print(f"Filtered logs: {sonuc.get('filtered_logs', 0)}")
            
            if 'summary' in sonuc:
                print(f"Total logs: {sonuc['summary'].get('total_logs', 0)}")
                print(f"Anomalies: {sonuc['summary'].get('n_anomalies', 0)}")
                print(f"Anomaly rate: {sonuc['summary'].get('anomaly_rate', 0):.2f}%")
            
            if 'critical_anomalies' in sonuc:
                print(f"Critical anomalies: {len(sonuc['critical_anomalies'])}")
                
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_api_direct()