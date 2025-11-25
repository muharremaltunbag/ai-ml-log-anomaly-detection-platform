"""
LCWGPT Integration Test Script
MongoDB Log Anomaly Detection System için LCWGPT entegrasyonu testi
"""
import os
import sys
from datetime import datetime
import json

# Path ayarları
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from src.connectors.lcwgpt_connector import LCWGPTConnector
from langchain.schema import HumanMessage, SystemMessage

def test_lcwgpt_connection():
    """LCWGPT bağlantı testi"""
    print("\n" + "="*60)
    print("LCWGPT CONNECTION TEST")
    print("="*60)
    
    try:
        print("→ LCWGPT'ye bağlanılıyor...")
        connector = LCWGPTConnector()
        
        if connector.connect():
            print("✅ LCWGPT bağlantısı başarılı!")
            
            # Basit test mesajı
            print("\n→ Test mesajı gönderiliyor...")
            test_messages = [
                SystemMessage(content="Sen bir MongoDB anomali analiz uzmanısın. Kısa ve net yanıtlar ver."),
                HumanMessage(content="Merhaba, MongoDB slow query anomalisi ne anlama gelir?")
            ]
            
            response = connector.invoke(test_messages)
            if response and response.content:
                print("✅ Test yanıtı alındı:")
                print(f"   📝 Yanıt: {response.content[:200]}...")
            else:
                print("❌ Test yanıtı alınamadı")
            
            return connector
        else:
            print("❌ LCWGPT bağlantısı kurulamadı")
            return None
            
    except Exception as e:
        print(f"❌ LCWGPT bağlantı hatası: {e}")
        print("⚠️ LCWGPT credentials .env dosyasında tanımlı olmalı:")
        print("   LCWGPT_API_KEY=...")
        print("   LCWGPT_ENDPOINT=...")
        print("   LCWGPT_INSTITUTION_ID=...")
        return None

def test_anomaly_explanation(connector):
    """Anomali açıklama testi"""
    print("\n" + "="*60)
    print("ANOMALY EXPLANATION TEST")
    print("="*60)
    
    # Test anomali verisi
    test_anomaly = {
        "component": "QUERY",
        "severity": "W",
        "score": -0.95,
        "message": "Slow query: COLLSCAN { find: \"products\", filter: { category: \"electronics\" } } 5234ms",
        "timestamp": datetime.now().isoformat()
    }
    
    print(f"→ Test anomalisi:")
    print(f"   Component: {test_anomaly['component']}")
    print(f"   Severity: {test_anomaly['severity']}")
    print(f"   Score: {test_anomaly['score']}")
    print(f"   Message: {test_anomaly['message'][:80]}...")
    
    # LCWGPT'ye anomali analizi yaptır
    print("\n→ LCWGPT'den anomali açıklaması isteniyor...")
    
    messages = [
        SystemMessage(content="""Sen bir MongoDB anomali uzmanısın. Kısa, net ve aksiyona yönelik analiz yap.

FORMAT:
1. NE TESPİT EDİLDİ: Kısa açıklama
2. NEDEN ÖNEMLİ: Risk ve etki
3. ÖNERİLEN AKSİYON: Yapılacaklar

Türkçe yanıt ver."""),
        HumanMessage(content=f"""
MongoDB Anomalisi:
- Component: {test_anomaly['component']}
- Severity: {test_anomaly['severity']}
- Anomaly Score: {test_anomaly['score']} (çok yüksek)
- Log Message: {test_anomaly['message']}

Bu anomaliyi analiz et.""")
    ]
    
    try:
        response = connector.invoke(messages)
        if response and response.content:
            print("✅ Anomali açıklaması alındı:\n")
            print("─" * 50)
            print(response.content)
            print("─" * 50)
            return True
        else:
            print("❌ Anomali açıklaması alınamadı")
            return False
    except Exception as e:
        print(f"❌ Anomali açıklama hatası: {e}")
        return False

def test_batch_anomaly_analysis(connector):
    """Toplu anomali analizi testi"""
    print("\n" + "="*60)
    print("BATCH ANOMALY ANALYSIS TEST")
    print("="*60)
    
    # Birden fazla anomali
    anomalies = [
        {
            "component": "QUERY",
            "severity": "W",
            "score": -0.92,
            "message": "Slow query: COLLSCAN 3500ms"
        },
        {
            "component": "REPL",
            "severity": "E",
            "score": -0.88,
            "message": "Replication lag detected: secondary 10 seconds behind"
        },
        {
            "component": "STORAGE",
            "severity": "F",
            "score": -0.95,
            "message": "Out of disk space on /data/db"
        }
    ]
    
    print(f"→ {len(anomalies)} anomali analiz ediliyor...")
    
    # Özet analiz iste
    anomaly_summary = "\n".join([
        f"- [{a['component']}] Skor: {a['score']}, {a['message'][:50]}..."
        for a in anomalies
    ])
    
    messages = [
        SystemMessage(content="MongoDB anomali uzmanısın. Kritik sorunları tespit et ve önceliklendir."),
        HumanMessage(content=f"""
Tespit edilen anomaliler:
{anomaly_summary}

En kritik 2 sorunu belirle ve çözüm öner. Kısa ve net ol.""")
    ]
    
    try:
        response = connector.invoke(messages)
        if response and response.content:
            print("✅ Toplu analiz tamamlandı:\n")
            print("─" * 50)
            print(response.content)
            print("─" * 50)
            return True
        else:
            print("❌ Toplu analiz başarısız")
            return False
    except Exception as e:
        print(f"❌ Toplu analiz hatası: {e}")
        return False

def main():
    """Ana test fonksiyonu"""
    print("="*60)
    print("LCWGPT Integration Test")
    print(f"Test Tarihi: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    
    # 1. Bağlantı testi
    connector = test_lcwgpt_connection()
    
    if connector and connector.is_connected():
        # 2. Anomali açıklama testi
        test_anomaly_explanation(connector)
        
        # 3. Toplu analiz testi
        test_batch_anomaly_analysis(connector)
        
        # Bağlantıyı kapat
        connector.disconnect()
        print("\n✅ Tüm testler tamamlandı!")
    else:
        print("\n❌ LCWGPT bağlantısı olmadan testler yapılamaz")
        print("   Lütfen .env dosyasında LCWGPT ayarlarını kontrol edin")

if __name__ == "__main__":
    main()