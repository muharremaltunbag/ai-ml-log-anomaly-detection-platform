from src.anomaly.log_reader import OpenSearchProxyReader
from datetime import datetime, timedelta, timezone

def diagnose_time_format():
    """OpenSearch zaman formatı uyumsuzluğunu tespit et"""
    print("TIME FORMAT DIAGNOSIS")
    print("=" * 50)
    
    reader = OpenSearchProxyReader()
    if not reader.connect():
        print("❌ OpenSearch bağlantısı başarısız!")
        return
    
    print("✅ OpenSearch bağlantısı başarılı\n")
    
    # Test 1: now-Xh formatı
    print("Test 1: 'now-1h' format")
    query1 = {
        "size": 0,
        "query": {
            "bool": {
                "must": [
                    {"range": {"@timestamp": {"gte": "now-1h"}}}
                ]
            }
        }
    }
    
    # Test 2: ISO format (UTC)
    print("Test 2: ISO format (UTC)")
    one_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1))
    iso_format = one_hour_ago.isoformat().replace('+00:00', 'Z')
    query2 = {
        "size": 0,
        "query": {
            "bool": {
                "must": [
                    {"range": {"@timestamp": {"gte": iso_format}}}
                ]
            }
        }
    }
    
    # Test 3: ISO format (Local timezone)
    print("Test 3: ISO format (Local)")
    one_hour_ago_local = datetime.now() - timedelta(hours=1)
    iso_local = one_hour_ago_local.isoformat() + "Z"
    query3 = {
        "size": 0,
        "query": {
            "bool": {
                "must": [
                    {"range": {"@timestamp": {"gte": iso_local}}}
                ]
            }
        }
    }
    
    # Sorguları çalıştır
    result1 = reader._make_request("db-mongodb-*/_search", "GET", query1)
    result2 = reader._make_request("db-mongodb-*/_search", "GET", query2)
    result3 = reader._make_request("db-mongodb-*/_search", "GET", query3)
    
    print("\n📊 SONUÇLAR:")
    print("-" * 40)
    
    if result1 and 'hits' in result1:
        hits1 = result1['hits']['total']['value']
        print(f"✅ now-1h format: {hits1:,} hits")
    else:
        print("❌ now-1h format: FAILED")
    
    if result2 and 'hits' in result2:
        hits2 = result2['hits']['total']['value']
        print(f"{'✅' if hits2 > 0 else '❌'} ISO UTC ({iso_format}): {hits2:,} hits")
    else:
        print("❌ ISO UTC format: FAILED")
    
    if result3 and 'hits' in result3:
        hits3 = result3['hits']['total']['value']
        print(f"{'✅' if hits3 > 0 else '❌'} ISO Local ({iso_local}): {hits3:,} hits")
    else:
        print("❌ ISO Local format: FAILED")
    
    print("\n📌 ÖZET:")
    if hits1 > 0 and hits2 == 0:
        print("→ OpenSearch 'now-Xh' formatını bekliyor!")
        print("→ ISO format çalışmıyor, scroll API'yi düzeltmemiz gerekiyor.")
    elif hits1 > 0 and hits2 > 0:
        print("→ Her iki format da çalışıyor.")
        print("→ Scroll API'de başka bir sorun olabilir.")
    else:
        print("→ Beklenmeyen durum, detaylı inceleme gerekiyor.")

if __name__ == "__main__":
    diagnose_time_format()