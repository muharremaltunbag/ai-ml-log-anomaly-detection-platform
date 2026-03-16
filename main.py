# main.py - MongoDB Anomaly Detection Platform Entry Point

"""MongoDB LangChain Assistant - Ana Giriş Noktası"""

import os
import sys
import logging
from datetime import datetime
from typing import Dict, Any  # Bu satırı ekleyin
from dotenv import load_dotenv

# Proje root'u Python path'e ekle
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.agents.mongodb_agent import MongoDBAgent

# Ortam değişkenlerini yükle
load_dotenv()

# Logging yapılandırması
def setup_logging():
    """Logging sistemini yapılandır"""
    log_level = os.getenv("LOG_LEVEL", "INFO")
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # Log dizinini oluştur
    os.makedirs("logs", exist_ok=True)
    
    # Log dosyası adı
    log_file = f"logs/mongodb_assistant_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    
    # Root logger yapılandırması
    logging.basicConfig(
        level=getattr(logging, log_level),
        format=log_format,
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # Gürültülü kütüphaneleri sustur
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("pymongo").setLevel(logging.WARNING)
    
    return logging.getLogger(__name__)

# Ana uygulama sınıfı
class MongoDBAssistantCLI:
    """Komut satırı arayüzü"""
    
    def __init__(self):
        self.logger = setup_logging()
        self.agent = None
        self.running = False
        
    def print_banner(self):
        """Hoşgeldin mesajı"""
        print("\n" + "="*60)
        print("🤖 MongoDB Doğal Dil Asistanı")
        print("="*60)
        print("📝 Doğal dilde MongoDB sorguları yazabilirsiniz")
        print("💡 Örnek: 'users koleksiyonundaki aktif kullanıcıları göster'")
        print("❓ Yardım için 'help' yazın")
        print("🚪 Çıkmak için 'exit' veya 'quit' yazın")
        print("="*60 + "\n")
    
    def print_help(self):
        """Yardım mesajı"""
        print("\n📚 KULLANILABILIR KOMUTLAR:")
        print("-" * 40)
        print("help          - Bu yardım mesajını göster")
        print("status        - Sistem durumunu göster")
        print("collections   - Mevcut koleksiyonları listele")
        print("schema <name> - Koleksiyon şemasını göster")
        print("history       - Konuşma geçmişini göster")
        print("clear         - Konuşma geçmişini temizle")
        print("exit/quit     - Uygulamadan çık")
        print("-" * 40)
        print("\n💡 SORGU ÖRNEKLERİ:")
        print("- 30 yaşından büyük kullanıcıları bul")
        print("- products koleksiyonunun yapısını göster")
        print("- orders'da toplam sipariş sayısı")
        print("- customers'da city alanına index ekle")
        print("-" * 40 + "\n")
    def initialize_agent(self) -> bool:
        """Agent'ı başlat"""
        try:
            print("🔄 Sistem başlatılıyor...")
            
            # Agent oluştur
            self.agent = MongoDBAgent()
            
            # Başlat
            if not self.agent.initialize():
                print("❌ Sistem başlatılamadı!")
                print("📋 Lütfen .env dosyasındaki ayarları kontrol edin.")
                return False
            
            print("✅ Sistem başarıyla başlatıldı!")
            
            # Mevcut koleksiyonları göster
            collections = self.agent.get_available_collections()
            if collections:
                print(f"📊 Mevcut koleksiyonlar ({len(collections)}): {', '.join(collections[:5])}")
                if len(collections) > 5:
                    print(f"   ... ve {len(collections) - 5} koleksiyon daha")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Başlatma hatası: {e}")
            print(f"❌ Beklenmeyen hata: {e}")
            return False
    
    def handle_command(self, command: str) -> bool:
        """Özel komutları işle"""
        cmd = command.lower().strip()
        
        # Çıkış komutları
        if cmd in ['exit', 'quit', 'q']:
            return False
        
        # Yardım
        elif cmd == 'help':
            self.print_help()
        
        # Durum
        elif cmd == 'status':
            status = self.agent.get_status()
            print("\n📊 SİSTEM DURUMU:")
            print("-" * 30)
            print(f"MongoDB Bağlantısı: {'✅ Aktif' if status['mongodb_connected'] else '❌ Kapalı'}")
            print(f"OpenAI Bağlantısı: {'✅ Aktif' if status['openai_connected'] else '❌ Kapalı'}")
            print(f"Agent Durumu: {'✅ Hazır' if status['agent_ready'] else '❌ Hazır değil'}")
            print(f"Konuşma Geçmişi: {status['conversation_length']} mesaj")
            print(f"Mevcut Araçlar: {', '.join(status['available_tools'])}")
            print("-" * 30 + "\n")
        
        # Koleksiyonlar
        elif cmd == 'collections':
            collections = self.agent.get_available_collections()
            if collections:
                print(f"\n📁 MEV CUT KOLEKSİYONLAR ({len(collections)}):")
                print("-" * 30)
                for i, coll in enumerate(collections, 1):
                    print(f"{i:3}. {coll}")
                print("-" * 30 + "\n")
            else:
                print("❌ Koleksiyon listesi alınamadı")
        
        # Schema görüntüleme
        elif cmd.startswith('schema '):
            collection_name = cmd[7:].strip()
            if collection_name:
                print(f"\n🔍 {collection_name} koleksiyonu analiz ediliyor...")
                schema = self.agent.analyze_collection(collection_name, detailed=False)
                self._print_schema(schema)
            else:
                print("❌ Koleksiyon adı belirtin: schema <koleksiyon_adı>")
        
        # Geçmiş
        elif cmd == 'history':
            history = self.agent.get_conversation_history()
            if history:
                print("\n💬 KONUŞMA GEÇMİŞİ:")
                print("-" * 50)
                for i, msg in enumerate(history, 1):
                    print(f"{i}. [{msg['type']}] {msg['content'][:100]}...")
                print("-" * 50 + "\n")
            else:
                print("📭 Konuşma geçmişi boş")
        
        # Temizle
        elif cmd == 'clear':
            self.agent.clear_conversation_history()
            print("🧹 Konuşma geçmişi temizlendi")
        
        # Bilinmeyen komut - normal sorgu olarak işle
        else:
            return None
        
        return True
    
    def _print_schema(self, schema: Dict):
        """Schema bilgisini güzel format et"""
        if "error" in schema:
            print(f"❌ Hata: {schema['error']}")
            return
        
        print(f"\n📋 KOLEKSIYON: {schema.get('collection', 'Bilinmiyor')}")
        print(f"📊 Doküman Sayısı: {schema.get('document_count', 0):,}")
        print("-" * 50)
        
        fields = schema.get('fields', {})
        if fields:
            print("📝 ALANLAR:")
            for field, info in list(fields.items())[:20]:  # İlk 20 alan
                print(f"  • {field}")
                print(f"    - Tip: {info.get('primary_type', 'unknown')}")
                print(f"    - Doluluk: %{info.get('fill_rate', 0)}")
                if info.get('examples'):
                    print(f"    - Örnek: {info['examples'][0]}")
        
        indexes = schema.get('indexes', [])
        if indexes:
            print("\n🔑 INDEX'LER:")
            for idx in indexes:
                print(f"  • {idx.get('name', 'unnamed')} - {idx.get('keys', {})}")
        
        print("-" * 50 + "\n")
    def process_query(self, query: str):
        """Kullanıcı sorgusunu işle ve sonucu göster"""
        try:
            print("\n🔄 Sorgu işleniyor...")
            
            # Agent'a gönder
            result = self.agent.process_query(query)
            
            # Sonucu formatla ve göster
            self._display_result(result)
            
        except KeyboardInterrupt:
            print("\n⚠️ İşlem iptal edildi")
        except Exception as e:
            self.logger.error(f"Sorgu işleme hatası: {e}")
            print(f"\n❌ Hata: {e}")
    
    def _display_result(self, result: Dict):
        """Sonucu kullanıcı dostu göster"""
        print("\n" + "="*50)
        
        # Durum göstergesi
        durum = result.get("durum", "bilinmiyor")
        if durum == "başarılı":
            print("✅ İŞLEM BAŞARILI")
        elif durum == "uyarı":
            print("⚠️ UYARI")
        elif durum == "hata":
            print("❌ HATA")
        else:
            print("ℹ️ SONUÇ")
        
        # İşlem ve açıklama
        if "işlem" in result:
            print(f"📌 İşlem: {result['işlem']}")
        
        if "koleksiyon" in result:
            print(f"📁 Koleksiyon: {result['koleksiyon']}")
        
        print("-"*50)
        
        if "açıklama" in result:
            print(f"📝 {result['açıklama']}")
        
        # Tahminler
        if "tahminler" in result and result["tahminler"]:
            print("\n💡 Yapılan Tahminler:")
            for tahmin in result["tahminler"]:
                print(f"  • {tahmin}")
        
        # Sonuç detayları
        if "sonuç" in result and result["sonuç"]:
            print("\n📊 Sonuç Detayları:")
            sonuc = result["sonuç"]
            
            # JSON ise güzel yazdır
            if isinstance(sonuc, dict):
                import json
                print(json.dumps(sonuc, indent=2, ensure_ascii=False))
            else:
                print(sonuc)
        
        # Öneriler
        if "öneriler" in result and result["öneriler"]:
            print("\n💡 Öneriler:")
            for oneri in result["öneriler"]:
                print(f"  • {oneri}")
        
        print("="*50 + "\n")
    
    def run(self):
        """Ana uygulama döngüsü"""
        try:
            # Banner göster
            self.print_banner()
            
            # Agent'ı başlat
            if not self.initialize_agent():
                return
            
            self.running = True
            
            # Ana döngü
            while self.running:
                try:
                    # Kullanıcı girdisi al
                    user_input = input("\n🤖 > ").strip()
                    
                    if not user_input:
                        continue
                    
                    # Özel komut kontrolü
                    command_result = self.handle_command(user_input)
                    
                    if command_result is False:
                        # Çıkış komutu
                        self.running = False
                    elif command_result is True:
                        # Komut işlendi
                        continue
                    else:
                        # Normal sorgu olarak işle
                        self.process_query(user_input)
                    
                except KeyboardInterrupt:
                    print("\n\n⚠️ Çıkmak için 'exit' yazın")
                    continue
                except Exception as e:
                    self.logger.error(f"Döngü hatası: {e}")
                    print(f"\n❌ Beklenmeyen hata: {e}")
                    print("💡 Devam etmek için Enter'a basın...")
                    input()
            
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Temizlik işlemleri"""
        print("\n🔄 Sistem kapatılıyor...")
        
        if self.agent:
            self.agent.shutdown()
        
        print("👋 Güle güle!\n")


# Ana giriş noktası
def main():
    """Ana fonksiyon"""
    try:
        # CLI uygulamasını başlat
        app = MongoDBAssistantCLI()
        app.run()
        
    except Exception as e:
        logging.error(f"Uygulama hatası: {e}")
        print(f"\n❌ Kritik hata: {e}")
        print("📋 Detaylar için log dosyasını kontrol edin.")
        sys.exit(1)


if __name__ == "__main__":
    main()