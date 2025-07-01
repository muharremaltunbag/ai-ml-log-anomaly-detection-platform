---
trigger: manual
---

# MongoDB LangChain Assistant - Windsurf Rules


Çalışma Prensipleri ve Kurallar
Etkileşim Kuralları ve Çalışma Prensipleri

Adım Adım İlerleme: Tek seferde her şeyi anlatmama - adım adım ilerleme, kullanıcı yönlendirmeli
Kısa ve Öz Mesajlar: Her mesaj kısa, öz, net ve anlaşılır
Proaktif Olmama: Kullanıcı sormadan analiz yapmama veya işlem başlatmama
Onay Mekanizması: Her adımda ne yapılacağını önerip kullanıcı onayı alma, her kritik adımda kullanıcı onayı
Teknik Basitlik: Teknik karmaşıklığı minimumda tutma, karmaşıklığı minimumda tutma
Yavaş ve Kontrollü İlerleme: Her adımda kullanıcıdan onay alma 
Varsayımda Bulunmama: Log yolu, format, sunucu bilgileri gibi detayları sormak 
Test Ortamını Koruma: Vagrant ortamını ve mevcut test yapısını bozmamak 
Adım Adım Bilgi Toplama: İhtiyaç duyulan bilgileri sırayla istemek 
Her Adımda Özetleme: Ne yaptık, ne yapacağız açıkça belirtmek 

Geliştirme Prensipleri ve İlkeleri (Teknik Prensipler)

Modüler Yaklaşım: Her bileşen bağımsız ve test edilebilir, her component bağımsız
Güvenlik Öncelikli: NoSQL injection koruması, rate limiting, her katmanda güvenlik, her katmanda güvenlik kontrolü
Kod Kalitesi: Kod okunabilirliği ve basitlik öncelikli
Mevcut Yapıyı Koruma: Backend'e zarar vermeden kullanıcı arayüzü ekleme, backend'e zarar vermeden özellik ekleme
Soyutlama Kontrolü: Gereksiz soyutlama yapmama
Dokümantasyon: Yorum satırlarıyla açık dokümantasyon, inline yorum ve README
Geriye Uyumluluk: Mevcut yapı bozulmadı, mevcut yapı korunur, mevcut 10 tool'un çalışmasını bozmamak
Esneklik: Config tabanlı, ortam bağımsız
Config Tabanlı Esneklik: Hardcoded değerler yerine config dosyaları, config dosyası kullanımı
Test Edilebilirlik: Unit test ready
OpenSearch Ready: Şu an dosya bazlı çalışırken, OpenSearch entegrasyonuna hazır mimari


## 📁 Kod Yapısı Kuralları

### Modüler Mimari
- Her yeni özellik ayrı modül (src/feature_name/) olarak ekle
- Mevcut 13 tool yapısını bozma
- Base classes'ı (BaseConnector gibi) her zaman extend et
- __init__.py dosyalarını her modülde bulundur

### Tool Development
- Yeni LangChain tool'ları StructuredTool pattern'i ile oluştur
- Tool response formatı standart JSON yapısını takip etmeli:
```json
{
  "durum": "başarılı|uyarı|hata",
  "işlem": "işlem_adı",
  "açıklama": "Türkçe açıklama",
  "sonuç": {},
  "öneriler": []
}
```
- tools.py'de get_all_tools() fonksiyonunu güncelle

### Import Standartları
- Relative imports kullan (from ..module import)
- External dependencies requirements.txt'e ekle
- Version pinning yap (paramiko==3.5.0)

## 🔧 Config Yönetimi Kuralları

### Environment Variables
- Hassas bilgileri .env dosyasında sakla
- .gitignore'da .env dosyasını kontrol et
- Production ve test ortamları için ayrı config'ler

### JSON Config Files
- monitoring_servers.json ve anomaly_config.json'ı güncel tut
- Config validation'ı runtime'da yap
- Environment bazlı config loading

## 🧪 Test Kuralları

### SSH Test
- Production SSH test'i sadece geçerli credentials ile
- Test ortamında Vagrant VM'leri kullan (2200, 2201, 2222)
- SSH connection timeout'ları test et

### MongoDB Test
- Test veritabanı: localhost:27017/chatbot_test
- Production'da: SSH tunnel üzerinden erişim
- Schema validation her test öncesi

### Tool Test
- Her tool ayrı ayrı test edilmeli
- Integration test'ler 13 tool'u birlikte test etmeli
- Error handling senaryolarını kapsa

## 📝 Dokümantasyon Kuralları

### Kod Dokümantasyonu
- Inline comment'ler Türkçe
- Fonksiyon docstring'leri İngilizce
- Complex logic için explanatory comment'ler

### File Updates
- Yeni özellik eklerken .windsurf/context.md güncelle
- Büyük değişiklikler için docs/project-master.md güncelle
- Sprint durumu için docs/current-sprint.md güncelle

## 🎯 LangChain Kuralları

### Agent Behavior
- System prompt Türkçe olmalı
- Temperature: 0 (deterministik yanıtlar)
- Max tokens: 2000
- Tool kullanımında önce schema kontrol et

### Tool Integration
- MongoDB (3) + Monitoring (5) + Performance (2) + Anomaly (3) = 13 tool
- Yeni tool eklerken mevcut yapıyı boz
- Tool kategorilerini koru (MongoDB, Monitoring, Performance, Anomaly)

## 🚫 Yasak İşlemler

### Never Do
- Hardcoded credentials kullanma
- Production'da test data ile çalışma
- SSH key'leri kod içinde saklama
- QueryValidator'ı bypass etme
- .env dosyasını commit etme
- OpenAI API key'ini log'lama

### Production Never
- Console.log ile sensitive data yazdırma
- Development config'i production'da kullanma
- SSH AutoAddPolicy'yi production'da bırakma
- Memory leak riski olan connection'ları açık bırakma

## 🔄 Maintenance Kuralları

### Regular Updates
- Model retrain (anomaly detection) haftalık
- SSH key rotation aylık
- Config file review aylık
- Dependency update'leri quarterly

### Performance Monitoring
- Query performance threshold'ları takip et
- SSH connection pool'ları monitor et
- Memory usage'ı track et
- API response time'larını measure et

## 📊 LC Waikiki Standartları

### UI Standards
- Renk paleti: #0047BA (Primary), #0033A0 (Secondary), #5C5B5B (Tertiary)
- Responsive design zorunlu
- Accessibility standartlarına uygun
- Corporate branding guidelines'ı takip et

### Error Handling
- User-friendly Türkçe hata mesajları
- Technical error'ları log'la ama user'a gösterme
- Graceful degradation sağla
- Fallback mechanism'ları implement et