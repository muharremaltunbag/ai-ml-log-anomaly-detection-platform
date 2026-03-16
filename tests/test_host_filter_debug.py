from src.anomaly.log_reader import OpenSearchProxyReader
import json

def test_host_filter():
    """Host filter debug testi"""
    print("HOST FILTER DEBUG")
    print("=" * 50)
    
    reader = OpenSearchProxyReader()
    reader.connect()
    
    # Test 1: Host filter olmadan
    print("\n1. Host filter YOK:")
    df1 = reader.read_logs(limit=100, last_hours=1)
    print(f"   Log sayısı: {len(df1)}")
    if len(df1) > 0:
        print(f"   İlk log host: {df1.iloc[0].get('host', 'N/A')}")
    
    # Test 2: Host filter ile (scroll olmadan)
    print("\n2. Host filter VAR (limit=100):")
    df2 = reader.read_logs(
        limit=100, 
        last_hours=1,
        host_filter="mongo-prod-03.internal.local"
    )
    print(f"   Log sayısı: {len(df2)}")
    
    # Test 3: Basit query test
    print("\n3. Direct query test:")
    query = {
        "size": 10,
        "query": {
            "bool": {
                "must": [
                    {"range": {"@timestamp": {"gte": "now-1h"}}},
                    {"term": {"host.name": "mongo-prod-03.internal.local"}}
                ]
            }
        }
    }
    
    result = reader._make_request("db-mongodb-*/_search", "GET", query)
    if result and 'hits' in result:
        print(f"   Total hits: {result['hits']['total']['value']}")
        print(f"   Returned: {len(result['hits']['hits'])}")
        
        # Host'ları kontrol et
        if result['hits']['hits']:
            hosts = set()
            for hit in result['hits']['hits']:
                host = hit['_source'].get('host', {}).get('name', 'N/A')
                hosts.add(host)
            print(f"   Unique hosts in results: {hosts}")

test_host_filter()