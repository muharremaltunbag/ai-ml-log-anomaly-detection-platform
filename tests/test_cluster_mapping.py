# tests/test_cluster_mapping.py
from src.anomaly.log_reader import get_available_clusters_with_hosts
import json

clusters = get_available_clusters_with_hosts(last_hours=24)
print(json.dumps(clusters, indent=2))