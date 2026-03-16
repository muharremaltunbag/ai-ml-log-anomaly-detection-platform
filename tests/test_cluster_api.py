# tests/test_cluster_api.py
import requests

API_KEY = "test-api-key"
BASE_URL = "http://localhost:8000"

# 1. Cluster listesini al
response = requests.get(f"{BASE_URL}/api/mongodb/clusters?api_key={API_KEY}")
print("Clusters:", response.json())

# 2. Belirli cluster'ın host'larını al
response = requests.get(f"{BASE_URL}/api/mongodb/cluster/mongo-cluster-01/hosts?api_key={API_KEY}")
print("Cluster hosts:", response.json())

# 3. Cluster analizi yap
response = requests.post(f"{BASE_URL}/api/analyze-cluster", json={
    "cluster_id": "testmongo",
    "api_key": API_KEY,
    "time_range": "last_24h"
})
print("Analysis result:", response.json())