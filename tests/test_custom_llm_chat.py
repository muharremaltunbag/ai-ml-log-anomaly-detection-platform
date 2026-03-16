# test_custom_llm_chat.py
import requests
import json
import time

url = "http://localhost:8000/api/chat-query-anomalies"
api_key = "test-api-key"
analysis_id = "analysis_9b5bca3322e7"  # MongoDB'den aldığımız ID

# Test sorguları
test_queries = [
    "ACCESS component'indeki authentication failed hatalarını analiz et",
    "En kritik 10 anomaliyi listele ve öneriler sun",
    "COMMAND bileşenindeki slow query problemlerini özetle",
    "Hangi component'te en çok anomali var?",
    "Bu anomaliler için ne önerirsin?"
]

for i, query in enumerate(test_queries, 1):
    print(f"\n{'='*70}")
    print(f"TEST {i}: {query}")
    print('='*70)
    
    start_time = time.time()
    
    try:
        response = requests.post(url, json={
            "api_key": api_key,
            "query": query,
            "analysis_id": analysis_id
        }, timeout=60)  # 60 saniye timeout
        
        elapsed = time.time() - start_time
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Status: {result.get('status')}")
            print(f"📊 Toplam Anomali: {result.get('total_anomalies')}")
            print(f"⏱️ Yanıt Süresi: {elapsed:.2f} saniye")
            print(f"📦 Chunk Info: {result.get('chunk_info', 'N/A')}")
            print(f"\n🤖 AI Response:")
            print("-" * 50)
            print(result.get('ai_response', 'Yanıt yok'))
            print("-" * 50)
        else:
            print(f"❌ Hata: {response.status_code}")
            print(response.text)
            
    except requests.exceptions.Timeout:
        print("⏰ Timeout: 60 saniye içinde yanıt alınamadı")
    except Exception as e:
        print(f"❌ Hata: {e}")
    
    # Her testten sonra 2 saniye bekle
    time.sleep(2)