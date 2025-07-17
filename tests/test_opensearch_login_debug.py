# tests\test_opensearch_login_debug.py
import os
from dotenv import load_dotenv
import requests
import json
import urllib3

# SSL uyarılarını sustur
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# .env yükle
load_dotenv()

# Credentials
username = os.getenv('OPENSEARCH_USER')
password = os.getenv('OPENSEARCH_PASS')

print("🔍 OpenSearch Login Debug")
print("-" * 50)
print(f"Username: {username}")
print(f"Password: {'*' * len(password) if password else 'NOT SET!'}")
print(f"Password length: {len(password) if password else 0}")
print("-" * 50)

# Login URL
login_url = "https://opslog.lcwaikiki.com/auth/login"

# Headers (browser'dan alınan)
headers = {
    "Content-Type": "application/json",
    "osd-version": "2.6.0",
    "Referer": "https://opslog.lcwaikiki.com/app/login?",
    "Origin": "https://opslog.lcwaikiki.com"
}

# Login data
login_data = {
    "username": username,
    "password": password
}

print(f"\n🔐 Attempting login to: {login_url}")
print(f"Headers: {json.dumps(headers, indent=2)}")
print(f"Body: username={username}, password=***")

try:
    # Login request
    response = requests.post(
        login_url,
        json=login_data,
        headers=headers,
        verify=False,
        timeout=30
    )
    
    print(f"\n📊 Response Status: {response.status_code}")
    print(f"Response Headers:")
    for key, value in response.headers.items():
        if key.lower() in ['set-cookie', 'content-type', 'osd-name']:
            print(f"  {key}: {value[:100]}...")
    
    if response.status_code == 200:
        print("\n✅ Login successful!")
        cookies = response.cookies.get_dict()
        if 'security_authentication' in cookies:
            print(f"🍪 Got security cookie: {cookies['security_authentication'][:50]}...")
        else:
            print("⚠️  No security cookie in response")
    else:
        print(f"\n❌ Login failed!")
        print(f"Response body: {response.text[:200]}")
        
except Exception as e:
    print(f"\n❌ Request error: {e}")