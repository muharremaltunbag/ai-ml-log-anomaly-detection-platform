#!/usr/bin/env python3
"""
Server Validation Debug Endpoint Test Script
Bu script yeni eklenen debug endpoint'ini test eder.
"""

import requests
import json
import sys
import os

# Base URL ve API key
BASE_URL = "http://localhost:8000"
API_KEY = "test-api-key"

def test_debug_endpoint():
    """Debug endpoint'ini test et"""
    print("🔧 Server Validation Debug Endpoint Test")
    print("=" * 50)
    
    try:
        # Debug endpoint'ini çağır
        url = f"{BASE_URL}/api/debug/server-validation"
        params = {"api_key": API_KEY}
        
        print(f"📡 Calling: {url}")
        print(f"🔑 API Key: {API_KEY}")
        print()
        
        response = requests.get(url, params=params, timeout=30)
        
        print(f"📊 Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            
            print("✅ SUCCESS! Debug endpoint çalışıyor.")
            print()
            
            # Test sonuçlarını göster
            print("🖥️ AVAILABLE HOSTS:")
            hosts = data.get("available_hosts", [])
            total_hosts = data.get("total_hosts", 0)
            print(f"   Total: {total_hosts}")
            for i, host in enumerate(hosts[:5], 1):
                print(f"   {i}. {host}")
            if len(hosts) > 5:
                print(f"   ... ve {len(hosts) - 5} host daha")
            print()
            
            # Validation testlerini göster
            print("🧪 VALIDATION TESTS:")
            tests = data.get("validation_tests", [])
            for i, test in enumerate(tests, 1):
                print(f"   {i}. {test['test']}")
                print(f"      Query: {test['query']}")
                print(f"      Expected: {test['expected']}")
                print(f"      Endpoint: {test['endpoint']}")
                if 'server_detected' in test:
                    print(f"      Server Detected: {test['server_detected']}")
                print()
            
            # FQDN correction test
            print("🔧 FQDN CORRECTION TEST:")
            fqdn = data.get("fqdn_correction", {})
            print(f"   Input: {fqdn.get('input', 'N/A')}")
            print(f"   Output: {fqdn.get('output', 'N/A')}")
            print(f"   Corrected: {fqdn.get('corrected', False)}")
            print()
            
            # Storage bilgisi
            if "last_analysis_server" in data:
                print("💾 LAST ANALYSIS INFO:")
                analysis = data["last_analysis_server"]
                print(f"   Analysis ID: {analysis.get('analysis_id', 'N/A')}")
                print(f"   Host: {analysis.get('host', 'N/A')}")
                print(f"   Timestamp: {analysis.get('timestamp', 'N/A')}")
                print()
            
            # Sistem durumu
            print("🚦 SYSTEM STATUS:")
            status = data.get("system_status", {})
            for key, value in status.items():
                print(f"   {key}: {value}")
            
            print()
            print("🎉 Test tamamlandı! Tüm bileşenler çalışıyor görünüyor.")
            
        elif response.status_code == 401:
            print("❌ HATA: API key geçersiz")
            print("   Lütfen API key'i kontrol edin")
            
        elif response.status_code == 500:
            print("❌ HATA: Server error")
            try:
                error_data = response.json()
                print(f"   Error: {error_data.get('detail', 'Unknown error')}")
            except:
                print(f"   Raw response: {response.text}")
                
        else:
            print(f"❌ Beklenmeyen status code: {response.status_code}")
            print(f"   Response: {response.text}")
            
    except requests.exceptions.ConnectionError:
        print("❌ BAĞLANTI HATASI!")
        print("   Backend server çalışıyor mu?")
        print("   Lütfen şu komutu çalıştırın:")
        print("   cd MongoDB-LLM-assistant && python main.py")
        
    except requests.exceptions.Timeout:
        print("❌ TIMEOUT HATASI!")
        print("   Server çok yavaş yanıt veriyor")
        
    except Exception as e:
        print(f"❌ BEKLENMEYEN HATA: {e}")

def test_invalid_api_key():
    """Geçersiz API key ile test"""
    print("\n🔒 Invalid API Key Test")
    print("-" * 30)
    
    try:
        url = f"{BASE_URL}/api/debug/server-validation"
        params = {"api_key": "invalid-key"}
        
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 401:
            print("✅ API key validation çalışıyor (401 döndü)")
        else:
            print(f"⚠️ Beklenmeyen response: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Test hatası: {e}")

if __name__ == "__main__":
    print("🚀 MongoDB LLM Assistant - Server Validation Test")
    print("=" * 60)
    
    # Ana test
    test_debug_endpoint()
    
    # API key validation test
    test_invalid_api_key()
    
    print("\n" + "=" * 60)
    print("Test tamamlandı!")
