# test_with_timeout.py
import requests
import json

url = "http://localhost:8000/api/chat-query-anomalies"

# Basit bir test
data = {
    "api_key": "lcw-test-2024",
    "query": "ACCESS component kaç anomali var?",
    "analysis_id": "analysis_9b5bca3322e7"
}

print("Sending request...")
try:
    response = requests.post(url, json=data, timeout=30)  # 30 saniye timeout
    print(f"Status Code: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        print(json.dumps(result, indent=2))
    else:
        print(f"Error Response: {response.text}")
except requests.exceptions.Timeout:
    print("Request timed out after 30 seconds")
except Exception as e:
    print(f"Error: {e}")