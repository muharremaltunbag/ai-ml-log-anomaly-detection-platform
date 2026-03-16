#!/usr/bin/env python3
"""
OpenSearch MongoDB Sunucu Analiz Script'i
Tüm MongoDB sunucularını tespit eder ve log dağılımını analiz eder
"""

import os
import sys
import json
import pandas as pd
from datetime import datetime, timedelta
import requests
from dotenv import load_dotenv
import urllib3

# SSL uyarılarını sustur
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# .env dosyasını yükle
load_dotenv()

# Script'i proje root'undan çalıştırıyoruz
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.anomaly.log_reader import OpenSearchProxyReader

def analyze_mongodb_hosts():
    """OpenSearch'teki tüm MongoDB sunucularını analiz et"""
    
    print("=== OpenSearch MongoDB Sunucu Analizi ===\n")
    
    # OpenSearch bağlantısı
    reader = OpenSearchProxyReader()
    
    # Bağlantı kontrolü
    print("1. OpenSearch'e bağlanılıyor...")
    if not reader.connect():
        print("❌ OpenSearch'e bağlanılamadı!")
        return
    
    print("✅ OpenSearch bağlantısı başarılı\n")
    
    # Tüm host'ları bulmak için aggregation query
    print("2. Tüm MongoDB sunucuları aranıyor...")
    
    # Son 7 gün için aggregation query
    aggregation_query = {
        "size": 0,
        "query": {
            "bool": {
                "must": [
                    {
                        "range": {
                            "@timestamp": {
                                "gte": "now-7d"
                            }
                        }
                    }
                ]
            }
        },
        "aggs": {
            "hosts": {
                "terms": {
                    "field": "host.name",
                    "size": 1000,  # Maksimum 1000 farklı host
                    "order": {
                        "_count": "desc"
                    }
                }
            }
        }
    }
    
    # Aggregation çalıştır
    search_path = f"{reader.index_pattern}/_search"
    result = reader._make_request(search_path, "GET", aggregation_query)
    
    if not result:
        print("❌ Aggregation sorgusu başarısız!")
        return
    
    # Host listesini al
    hosts = []
    if 'aggregations' in result and 'hosts' in result['aggregations']:
        for bucket in result['aggregations']['hosts']['buckets']:
            hosts.append({
                'host': bucket['key'],
                'log_count': bucket['doc_count']
            })
    
    print(f"\n✅ Toplam {len(hosts)} farklı MongoDB sunucusu bulundu\n")
    
    # Host listesini göster
    print("3. MongoDB Sunucu Listesi:")
    print("-" * 80)
    print(f"{'Host Adı':<50} {'Log Sayısı':>20}")
    print("-" * 80)
    
    # MongoDB sunucularını filtrele ve göster
    mongodb_hosts = []
    for host in hosts:
        # MongoDB sunucusu mu kontrol et
        hostname = host['host'].lower()
        # FQDN'den sadece hostname kısmını al
        hostname_base = hostname.split('.')[0] if '.' in hostname else hostname
        
        if any(keyword in hostname_base for keyword in ['mongodb', 'mongo', 'mng', 'mdb']):
            mongodb_hosts.append(host)
            print(f"{host['host']:<50} {host['log_count']:>20,}")
    
    print("-" * 80)
    print(f"Toplam MongoDB Sunucusu: {len(mongodb_hosts)}")
    
    # Her MongoDB sunucusu için detaylı analiz
    print("\n3.1. MongoDB Sunucuları Detaylı Analiz:")
    print("-" * 80)
    
    for i, host in enumerate(mongodb_hosts[:10]):  # İlk 10 sunucuyu analiz et
        print(f"\n📊 {i+1}. {host['host']} Analizi:")
        print(f"   Toplam Log Sayısı: {host['log_count']:,}")
        
        # Son 1 saatteki log sayısını al
        recent_query = {
            "size": 0,
            "query": {
                "bool": {
                    "must": [
                        {
                            "term": {
                                "host.name": host['host']
                            }
                        },
                        {
                            "range": {
                                "@timestamp": {
                                    "gte": "now-1h"
                                }
                            }
                        }
                    ]
                }
            }
        }
        
        recent_result = reader._make_request(search_path, "GET", recent_query)
        
        if recent_result and 'hits' in recent_result:
            recent_count = recent_result['hits']['total']['value']
            print(f"   Son 1 saatteki log sayısı: {recent_count:,}")
            
            # Log path analizi
            path_query = {
                "size": 0,
                "query": {
                    "bool": {
                        "must": [
                            {
                                "term": {
                                    "host.name": host['host']
                                }
                            },
                            {
                                "range": {
                                    "@timestamp": {
                                        "gte": "now-24h"
                                    }
                                }
                            }
                        ]
                    }
                },
                "aggs": {
                    "log_paths": {
                        "terms": {
                            "field": "log.file.path.keyword",
                            "size": 5
                        }
                    }
                }
            }
            
            path_result = reader._make_request(search_path, "GET", path_query)
            
            if path_result and 'aggregations' in path_result:
                print("   Log dosya yolları:")
                for bucket in path_result['aggregations']['log_paths']['buckets']:
                    print(f"     - {bucket['key']}: {bucket['doc_count']:,} log")
    
    if len(mongodb_hosts) > 10:
        print(f"\n   ... ve {len(mongodb_hosts) - 10} sunucu daha")
    
    # mongo-prod-01 özel kontrolü
    print("\n4. mongo-prod-01 Sunucusu Kontrolü:")
    print("-" * 80)
    
    target_host = "mongo-prod-01"
    found = False
    
    for host in hosts:
        if target_host in host['host'].lower():
            print(f"✅ BULUNDU: {host['host']} - Log sayısı: {host['log_count']:,}")
            found = True
            
            # Bu sunucudan örnek loglar al
            print("\n   Örnek loglar alınıyor...")
            sample_query = {
                "size": 5,
                "query": {
                    "bool": {
                        "must": [
                            {
                                "term": {
                                    "host.name": host['host']
                                }
                            },
                            {
                                "range": {
                                    "@timestamp": {
                                        "gte": "now-1h"
                                    }
                                }
                            }
                        ]
                    }
                },
                "sort": [{"@timestamp": {"order": "desc"}}]
            }
            
            sample_result = reader._make_request(search_path, "GET", sample_query)
            
            if sample_result and 'hits' in sample_result:
                print(f"   Son 1 saatte {sample_result['hits']['total']['value']} log bulundu")
                
                # Log örneklerini göster
                for i, hit in enumerate(sample_result['hits']['hits'][:3]):
                    source = hit['_source']
                    print(f"\n   Örnek Log {i+1}:")
                    print(f"   - Timestamp: {source.get('@timestamp')}")
                    print(f"   - Log path: {source.get('log', {}).get('file', {}).get('path', 'N/A')}")
                    if 'message' in source:
                        msg = source['message'][0] if isinstance(source['message'], list) else source['message']
                        print(f"   - Message sample: {msg[:100]}...")
    
    if not found:
        print(f"❌ '{target_host}' sunucusu bulunamadı!")
        print("\nOlası sebepler:")
        print("- Host adı farklı yazılmış olabilir (örn: FQDN ile)")
        print("- Son 7 günde log göndermemiş olabilir")
        print("- Filebeat/Logstash konfigürasyonu eksik olabilir")
    
    # Eksik olabilecek sunucuları listele
    print("\n5. Bilinen MongoDB Sunucuları ve Durumları:")
    print("-" * 80)
    
    known_servers = [
        "mongo-prod-02", "mongo-prod-01", "mongo-prod-03",
        "dbserver-001", "testmongodb01", "testmongodb02", "testmongodb03",
        "notif-mongo-01", "notif-mongo-02", "notif-mongo-03", "notif-mongo-04",
        "analytics-mongo-01"
    ]
    
    for server in known_servers:
        found = False
        for host in hosts:
            if server.lower() in host['host'].lower():
                print(f"✅ {server:<30} - AKTIF (Log sayısı: {host['log_count']:,})")
                found = True
                break
        if not found:
            print(f"❌ {server:<30} - BULUNAMADI")
    
    # Zaman bazlı analiz
    print("\n6. Zaman Bazlı Log Dağılımı (Son 24 saat):")
    print("-" * 80)
    
    time_query = {
        "size": 0,
        "query": {
            "range": {
                "@timestamp": {
                    "gte": "now-24h"
                }
            }
        },
        "aggs": {
            "logs_over_time": {
                "date_histogram": {
                    "field": "@timestamp",
                    "fixed_interval": "1h",
                    "min_doc_count": 0
                }
            }
        }
    }
    
    time_result = reader._make_request(search_path, "GET", time_query)
    
    if time_result and 'aggregations' in time_result:
        print("Saatlik log dağılımı:")
        for bucket in time_result['aggregations']['logs_over_time']['buckets'][-10:]:
            time_str = bucket['key_as_string']
            count = bucket['doc_count']
            print(f"  {time_str}: {count:,} log")
    
    return mongodb_hosts

def generate_opensearch_queries():
    """OpenSearch Dev Console için kullanılabilecek sorgu örnekleri"""
    
    print("\n\n=== OpenSearch Dev Console Sorgu Örnekleri ===\n")
    
    queries = {
        "Tüm MongoDB Sunucularını Listele": """
GET db-mongodb-*/_search
{
  "size": 0,
  "aggs": {
    "mongodb_hosts": {
      "terms": {
        "field": "host.name",
        "size": 1000
      }
    }
  }
}
""",
        
        "mongo-prod-01 Sunucusunu Ara": """
GET db-mongodb-*/_search
{
  "query": {
    "bool": {
      "should": [
        {"term": {"host.name": "mongo-prod-01"}},
        {"term": {"host.name": "mongo-prod-01.internal.local"}},
        {"wildcard": {"host.name": "*mongo-prod-01*"}}
      ]
    }
  }
}
""",
        
        "Son 1 Saatteki Tüm MongoDB Logları": """
GET db-mongodb-*/_search
{
  "query": {
    "range": {
      "@timestamp": {
        "gte": "now-1h"
      }
    }
  },
  "aggs": {
    "hosts": {
      "terms": {
        "field": "host.name"
      }
    }
  }
}
""",
        
        "Filebeat Agent Durumu": """
GET db-mongodb-*/_search
{
  "size": 0,
  "aggs": {
    "agents": {
      "terms": {
        "field": "agent.hostname.keyword"
      }
    }
  }
}
""",
        
        "Log Path Analizi": """
GET db-mongodb-*/_search
{
  "size": 0,
  "aggs": {
    "log_paths": {
      "terms": {
        "field": "log.file.path.keyword"
      }
    }
  }
}
"""
    }
    
    for title, query in queries.items():
        print(f"{title}:")
        print(query)
        print("-" * 80)
    
    print("\nBu sorguları https://localhost:9200 Dev Tools'da kullanabilirsiniz.")

if __name__ == "__main__":
    # Host analizi yap
    analyze_mongodb_hosts()
    
    # Sorgu örnekleri göster
    generate_opensearch_queries()