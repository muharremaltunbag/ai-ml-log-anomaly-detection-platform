#tests\test_opensearch_all_hosts.py
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.anomaly.log_reader import OpenSearchProxyReader
import logging
import pandas as pd

logging.basicConfig(level=logging.INFO)

print("🔍 OpenSearch MongoDB Sunucu Kapsamı Analizi")
print("=" * 60)

reader = OpenSearchProxyReader()
if reader.connect():
    print("✅ Bağlantı başarılı!\n")
    
    # 1. Son 24 saatte kaç farklı host var?
    print("📊 SON 24 SAATTEKİ TÜM MONGODB HOSTLARı:")
    df_24h = reader.read_logs(limit=1000, last_hours=24)
    
    if not df_24h.empty and 'host' in df_24h.columns:
        host_counts = df_24h['host'].value_counts()
        print(f"\nToplam {len(host_counts)} farklı host bulundu:")
        for host, count in host_counts.items():
            print(f"  - {host}: {count} log")
    
    # 2. mongo-prod-01 özel araması
    print(f"\n\n🔎 mongo-prod-01 ÖZEL ARAMASI:")
    
    # Custom query ile ara
    host_query = {
        "size": 100,
        "query": {
            "bool": {
                "must": [
                    {"range": {"@timestamp": {"gte": "now-24h"}}},
                    {"match": {"host.name": "mongo-prod-01"}}
                ]
            }
        }
    }
    
    result = reader._make_request("db-mongodb-*/_search", "GET", host_query)
    
    if result and 'hits' in result:
        total = result['hits']['total']['value'] if isinstance(result['hits']['total'], dict) else result['hits']['total']
        print(f"mongo-prod-01 için bulunan log sayısı: {total}")
        
        if total > 0:
            print("\n📝 Örnek mongo-prod-01 logu:")
            hit = result['hits']['hits'][0]
            print(f"  Index: {hit['_index']}")
            print(f"  Timestamp: {hit['_source'].get('@timestamp')}")
            print(f"  Host: {hit['_source'].get('host', {}).get('name')}")
    else:
        print("mongo-prod-01 için log bulunamadı!")
    
    # 3. Tüm host.name değerlerini aggregation ile bul
    print(f"\n\n📊 HOST.NAME AGGREGATION ANALİZİ:")
    
    agg_query = {
        "size": 0,
        "query": {
            "range": {"@timestamp": {"gte": "now-7d"}}
        },
        "aggs": {
            "hosts": {
                "terms": {
                    "field": "host.name.keyword",
                    "size": 50
                }
            }
        }
    }
    
    agg_result = reader._make_request("db-mongodb-*/_search", "GET", agg_query)
    
    if agg_result and 'aggregations' in agg_result:
        buckets = agg_result['aggregations']['hosts']['buckets']
        print(f"\nSon 7 günde {len(buckets)} farklı host bulundu:")
        
        # MongoDB sunucularını filtrele
        mongo_hosts = [b for b in buckets if 'mongo' in b['key'].lower()]
        print(f"\nMongoDB olarak tanımlanan hostlar ({len(mongo_hosts)} adet):")
        for bucket in mongo_hosts:
            print(f"  - {bucket['key']}: {bucket['doc_count']} log")
    
    # 4. Index pattern kontrolü
    print(f"\n\n📁 INDEX PATTERN ANALİZİ:")
    
    # Son 7 günün index'lerini kontrol et
    indices_result = reader._make_request("_cat/indices/db-mongodb-*?v&s=index:desc", "GET")
    if indices_result:
        print("Mevcut MongoDB index'leri:")
        print(indices_result[:500])  # İlk 500 karakter

else:
    print("❌ Bağlantı başarısız!")