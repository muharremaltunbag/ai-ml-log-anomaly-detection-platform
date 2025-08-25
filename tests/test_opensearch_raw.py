from datetime import datetime, timedelta
import json

def test_raw_query():
    """OpenSearch'e doğrudan sorgu"""
    
    from src.anomaly.log_reader import OpenSearchProxyReader
    
    reader = OpenSearchProxyReader()
    
    # Son 24 saat
    end_time = datetime.now()
    start_time = end_time - timedelta(hours=24)
    
    query = {
        "query": {
            "bool": {
                "must": [
                    {
                        "range": {
                            "timestamp": {
                                "gte": start_time.isoformat(),
                                "lte": end_time.isoformat()
                            }
                        }
                    }
                ]
            }
        },
        "track_total_hits": True,
        "size": 0  # Sadece count al
    }
    
    response = reader._make_request(
        "db-mongodb-*/_search",
        method="GET",
        json_data=query
    )
    
    if response:
        data = response.json()
        total = data['hits']['total']['value']
        print(f"OpenSearch'teki toplam log (son 24 saat): {total}")
        
        # Host bazlı aggregation
        query['aggs'] = {
            "hosts": {
                "terms": {
                    "field": "host.keyword",
                    "size": 50
                }
            }
        }
        
        response = reader._make_request(
            "db-mongodb-*/_search", 
            method="GET",
            json_data=query
        )
        
        if response:
            data = response.json()
            print("\nHost bazlı dağılım:")
            for bucket in data['aggregations']['hosts']['buckets']:
                print(f"  {bucket['key']}: {bucket['doc_count']}")

test_raw_query()