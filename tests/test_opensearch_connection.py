# test_opensearch_api.py
import requests
from requests.auth import HTTPBasicAuth
import os
from dotenv import load_dotenv
import urllib3
import json

# SSL uyarılarını sustur
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

load_dotenv()

username = os.getenv('OPENSEARCH_USER')
password = os.getenv('OPENSEARCH_PASS')

print(f"🔍 Searching for OpenSearch API endpoint...")
print(f"Username: {username}")
print("-" * 50)

# Base URL
base_url = "https://opslog.lcwaikiki.com"

# Session with auth
session = requests.Session()
session.auth = HTTPBasicAuth(username, password)
session.verify = False
session.headers.update({'Content-Type': 'application/json'})

# Possible API paths
api_paths = [
    "",  # root
    "/opensearch",
    "/elasticsearch", 
    "/es",
    "/api",
    "/_search",
    "/app/opensearch",
    "/app/api"
]

print("\n🔄 Testing API paths...")
for path in api_paths:
    url = f"{base_url}{path}"
    try:
        # Cluster health endpoint
        health_url = f"{url}/_cluster/health"
        resp = session.get(health_url, timeout=5)
        
        if resp.status_code == 200:
            print(f"\n✅ FOUND WORKING API at: {url}")
            print(f"   Cluster Health: {resp.json()}")
            
            # Test search
            search_url = f"{url}/db-mongodb-*/_search"
            search_body = {
                "size": 1,
                "query": {"match_all": {}}
            }
            search_resp = session.post(search_url, json=search_body)
            
            if search_resp.status_code == 200:
                result = search_resp.json()
                print(f"   Total MongoDB logs: {result['hits']['total']['value']:,}")
                print(f"\n📝 UPDATE YOUR .env FILE:")
                print(f"   OPENSEARCH_URL={url}")
                
                # Save working config
                with open("tests/working_opensearch_config.txt", "w") as f:
                    f.write(f"OPENSEARCH_URL={url}\n")
                    f.write(f"OPENSEARCH_USER={username}\n")
                    f.write("OPENSEARCH_PASS=<your_password>\n")
                print(f"\n   Config saved to: tests/working_opensearch_config.txt")
                
            break
            
        elif resp.status_code == 302:
            print(f"   {path} → 302 Redirect")
        elif resp.status_code == 404:
            print(f"   {path} → 404 Not Found")
        else:
            print(f"   {path} → {resp.status_code}")
            
    except requests.exceptions.Timeout:
        print(f"   {path} → Timeout")
    except Exception as e:
        if "ConnectionError" not in str(e):
            print(f"   {path} → Error: {str(e)[:50]}")

# Direct API test with cookies
print("\n\n🍪 Testing with authentication cookie...")
try:
    # First get the cookie
    login_resp = session.get(base_url, allow_redirects=True)
    
    # Try API with cookie
    if session.cookies:
        print(f"   Got cookies: {list(session.cookies.keys())}")
        
        # Test direct API access
        api_resp = session.get(f"{base_url}/_cluster/health")
        print(f"   API Response: {api_resp.status_code}")
        
except Exception as e:
    print(f"   Cookie test error: {e}")