# Test script
from src.anomaly.anomaly_tools import AnomalyDetectionTools

tools = AnomalyDetectionTools(environment='production')

# Cluster analiz testi
result = tools.analyze_mongodb_logs({
    "source_type": "opensearch",
    "host_filter": [
        "lcwmongodb01n1.lcwaikiki.local",
        "lcwmongodb01n2.lcwaikiki.local",
        "lcwmongodb01n3.lcwaikiki.local"
    ],
    "start_time": "2025-09-15T16:09:00Z",
    "end_time": "2025-09-15T16:11:00Z"
})

print("Cluster analysis completed")
# JSON string'i parse et
import json
if isinstance(result, str):
    result_dict = json.loads(result)
else:
    result_dict = result

print(f"Is cluster: {result_dict.get('sonuç', {}).get('server_info', {}).get('is_cluster')}")
print(f"Cluster name: {result_dict.get('sonuç', {}).get('server_info', {}).get('cluster_name')}")
print(f"Hosts analyzed: {result_dict.get('sonuç', {}).get('server_info', {}).get('cluster_hosts')}")
print(f"Total anomalies: {result_dict.get('sonuç', {}).get('anomaly_count')}")
print(f"Hosts analyzed: {result_dict.get('sonuç', {}).get('server_info', {}).get('cluster_hosts')}")