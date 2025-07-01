# MongoDB LangChain Assistant - Kapsamlı Proje Dokümantasyonu ve Dynamic SSH Entegrasyonu

## 🎯 Proje Tanımı ve Hedefler

### Ana Amaç
MongoDB LangChain Assistant, LC Waikiki için geliştirilmiş, LLM (GPT-4o) tabanlı bir araç üzerinden doğal dil ile MongoDB'ye güvenli erişim sağlayan, Linux sunucu monitoring, gelişmiş query performance analizi ve dynamic SSH ile MongoDB log anomali tespiti yetenekleriyle genişletilmiş kapsamlı bir chatbot sistemi geliştirmek. Bu sistem, GPT-4o tabanlı doğal dil ile MongoDB veritabanı yönetimi sağlayan, Linux sunucu monitoring, query performance analizi ve production-ready anomaly detection yeteneklerine sahip kurumsal bir chatbot sistemidir.

Production Anomaly Detection Hedefi: MongoDB loglarının LC Waikiki'nin OpenSearch platformu üzerinden toplanması ve bu loglara yönelik bir anomaly detection (Isolation Forest) modelinin production ortamda dynamic SSH bağlantılarıyla uygulanmasını sağlamak.

### Özel Hedefler
- MongoDB Yönetimi: Doğal dil ile sorgu gönderimi, Türkçe sorguları MongoDB komutlarına dönüştürme ve CRUD işlemleri
- Schema Yönetimi: Schema görüntüleme, analiz işlevleri ve kapsamlı veritabanı yapı analizi
- Veri Yönetimi: CRUD işlemleri (Create, Read, Update, Delete)
- Index Yönetimi: İndeks oluşturma, silme, görüntüleme ve performans optimizasyonu
- Güvenlik: Gizli şirket veritabanı üzerinde en güvenli entegrasyon, NoSQL injection koruması, rate limiting ve güvenli veritabanı erişimi
- Kurumsal UI: LC Waikiki test ortamı için kurumsal kullanıcı arayüzü entegrasyonu, renk paleti ve tasarım standartları
- Platform Entegrasyonu: Windsurf platformuna entegre edilebilir yapı
- Proje Erişimi: Proje dosyalarına tam erişimli, kullanıcı dostu chatbot
- Linux Monitoring: Linux sunucu monitoring yeteneği, SSH üzerinden CPU, Memory, Disk, Network metrikleri
- Modüler Genişletme: Mevcut MongoDB Assistant yapısını bozmadan genişletme
- Esnek Konfigürasyon: Hardcoded değerleri kaldırarak esnek config yapısı oluşturma
- Çoklu Ortam Desteği: Test ve production ortamlarında çalışabilir monitoring modülü
- Tool Entegrasyonu: LangChain agent'a monitoring tool'ları ekleme
- Performance Analizi: Query performance analizi, optimizasyon önerileri, execution plan değerlendirmesi ve performans skoru hesaplama
- Sorgu Optimizasyonu: MongoDB execution plan analizi ve performans skoru hesaplama sistemi
- Modüler Yapı: Her bileşen bağımsız, test edilebilir, genişletilebilir
- Anomaly Detection: MongoDB log anomali tespiti özelliğini entegre etme
- Mevcut Yapıyı Koruma: MongoDB LangChain Assistant'ın çalışan sistemine zarar vermeden genişletme
- Modüler Entegrasyon: Anomaly detection'ı ayrı bir modül (src/anomaly) olarak ekleme
- Çoklu Veri Kaynağı: Hem dosya sisteminden hem de gelecekte OpenSearch'ten log okuma
- Format Esnekliği: JSON (test) ve legacy text (production) log formatlarını destekleme
- Tool Sayısı Genişletme: 10 → 13 tool'a çıkarma
- Dynamic SSH Integration (Yeni): Dinamik SSH bağlantı yapısı (kullanıcı bazlı kimlik doğrulama)
- OpenSearch Hazır Mimari (Yeni): Gelecekte geçiş yapılabilecek architecture
- Production MongoDB Cluster Entegrasyonu (Yeni): Gerçek production sunucularıyla çalışma

### Mevcut Durum (Production)
- OpenSearch Erişimi: Şu anda YOK (erişim bekleniyor)
- Geçici Çözüm: SSH üzerinden dinamik kullanıcı kimlik bilgileriyle log okuma
- Temel Sistem: MongoDB LangChain Assistant (13 tool'lu chatbot)

### MongoDB Production Cluster Bilgileri (Yeni)
| Hostname         | IP Address      | Role                |
|------------------|-----------------|---------------------|
| lcwmongodb01n1   | 10.29.20.163    | Primary/Secondary   |
| lcwmongodb01n2   | 10.29.20.172    | Primary/Secondary   |
| lcwmongodb01n3   | 10.29.20.171    | Primary/Secondary   |

### Production Erişim Yapısı (Yeni)
Local Machine → Jump Server → MongoDB Sunucuları
               ↓                ↓
    RAGNAROK (10.29.1.229)    LDAP/DBA Authentication
    LCWECOMMERCE (10.62.0.70)    ↓
                              Log Files: /mongodata/log/

## 📋 Çalışma Prensipleri ve Kurallar

### Etkileşim Kuralları ve Çalışma Prensipleri
1. Adım Adım İlerleme: Tek seferde her şeyi anlatmama - adım adım ilerleme, kullanıcı yönlendirmeli
2. Kısa ve Öz Mesajlar: Her mesaj kısa, öz, net ve anlaşılır
3. Proaktif Olmama: Kullanıcı sormadan analiz yapmama veya işlem başlatmama
4. Onay Mekanizması: Her adımda ne yapılacağını önerip kullanıcı onayı alma, her kritik adımda kullanıcı onayı
5. Teknik Basitlik: Teknik karmaşıklığı minimumda tutma, karmaşıklığı minimumda tutma
6. Yavaş ve Kontrollü İlerleme: Her adımda kullanıcıdan onay alma (Anomaly ve SSH için)
7. Varsayımda Bulunmama: Log yolu, format, sunucu bilgileri gibi detayları sormak (Anomaly ve SSH için)
8. Test Ortamını Koruma: Vagrant ortamını ve mevcut test yapısını bozmamak (Anomaly ve SSH için)
9. Adım Adım Bilgi Toplama: İhtiyaç duyulan bilgileri sırayla istemek (SSH için)
10. Her Adımda Özetleme: Ne yaptık, ne yapacağız açıkça belirtmek (SSH için)

### Geliştirme Prensipleri ve İlkeleri (Teknik Prensipler)
- Modüler Yaklaşım: Her bileşen bağımsız ve test edilebilir, her component bağımsız
- Güvenlik Öncelikli: NoSQL injection koruması, rate limiting, her katmanda güvenlik, her katmanda güvenlik kontrolü
- Kod Kalitesi: Kod okunabilirliği ve basitlik öncelikli
- Mevcut Yapıyı Koruma: Backend'e zarar vermeden kullanıcı arayüzü ekleme, backend'e zarar vermeden özellik ekleme
- Soyutlama Kontrolü: Gereksiz soyutlama yapmama
- Dokümantasyon: Yorum satırlarıyla açık dokümantasyon, inline yorum ve README
- Geriye Uyumluluk: Mevcut yapı bozulmadı, mevcut yapı korunur, mevcut 10 tool'un çalışmasını bozmamak
- Esneklik: Config tabanlı, ortam bağımsız
- Config Tabanlı Esneklik: Hardcoded değerler yerine config dosyaları, config dosyası kullanımı
- Test Edilebilirlik: Unit test ready
- OpenSearch Ready: Şu an dosya bazlı çalışırken, OpenSearch entegrasyonuna hazır mimari

## 🛠️ Teknoloji Yığını

### Dil ve Framework (Temel Teknolojiler)
- Python 3.x: Ana geliştirme dili
- LangChain 0.3.14: Agent düzenleme, iş akışı yönetimi ve orchestration framework
- Visual Studio Code: Geliştirme ortamı
- FastAPI + Uvicorn: Web API çerçevesi, ASGI sunucusu ve web API framework

### LLM ve Yapay Zeka
- OpenAI GPT-4o: Doğal dil işleme motoru ve LLM motoru
- LangChain OpenAI entegrasyonu: Sorunsuz yapay zeka entegrasyonu
- Temperature: 0: Deterministik yanıtlar

### Veritabanı
- MongoDB: NoSQL belge tabanlı veritabanı (kendi barındırılan, Linux sunucular)
- pymongo sürücü 4.10.1: MongoDB bağlantı sürücüsü ve Python driver
- İstanbul'daki şirket içi ağ: Yerel ağ altyapısında konumlandırılmış

### Web Arayüzü ve Frontend
- Vanilla JavaScript: Ön yüz mantığı, saf JS (framework bağımlılığı yok)
- HTML5 + CSS3: LC Waikiki kurumsal tasarımı ve modern web standartları
- JSON renklendirme: Dinamik veri görselleştirme
- CSS Grid Layout: Metrik kutular için gelişmiş görselleştirme
- JSON: API iletişimi

### LC Waikiki Renk Paleti (Kurumsal Tasarım/Kurumsal Renkler):
- Primary: #0047BA        # LC Waikiki Mavisi
- Secondary: #0033A0      # İnternet Mavisi
- Tertiary: #5C5B5B       # Kurumsal Gri

### SSH ve Monitoring
- Paramiko 3.5.0: SSH bağlantıları ve güvenli sunucu erişimi
- JSON Config: Ortam yönetimi ve esnek konfigürasyon
- Vagrant + VirtualBox: Test ortamı (3 node MongoDB cluster)

### Anomaly Detection
- Isolation Forest: scikit-learn unsupervised anomaly detection
- Feature Engineering: 17 feature extraction (15 aktif)
- ThreadPoolExecutor: Paralel log okuma
- joblib: Model persistence ve save/load
- OpenSearch Ready: Gelecekte OpenSearch entegrasyonu için hazır mimari

### Dynamic SSH Integration (Yeni)
- Paramiko SSH Client: Production SSH bağlantıları
- Jump Server Support: Multi-hop SSH bağlantıları
- LDAP/DBA Authentication: Production kimlik doğrulama sistemleri
- TCP Tunneling: direct-tcpip ile secure connection forwarding
- Dynamic Configuration: Runtime SSH config yönetimi

### Güvenlik ve Yapılandırma
- python-dotenv: Kimlik bilgileri yönetimi
- Virtual environment izolasyonu: Bağımlılık yönetimi
- .env dosyasında hassas bilgiler: Güvenli yapılandırma
- QueryValidator: NoSQL injection koruması

## 📊 LangChain Tools Kapsamlı Özeti (13 Adet - SSH Entegrasyonlu)

### MongoDB Tools (3 adet)
1. mongodb_query: Sorgu çalıştırma (find, aggregate, count)
2. view_schema: Şema görüntüleme ve analiz
3. manage_indexes: Index yönetimi (oluşturma, silme, listeleme)

### Monitoring Tools (5 adet)
4. check_server_status: Sunucu durumu kontrolü (uptime, OS bilgisi)
5. get_server_metrics: CPU, Memory, Disk, Network metrikleri
6. find_resource_intensive_processes: Yüksek kaynak kullanımı analizi
7. execute_monitoring_command: Güvenli komut çalıştırma (whitelist)
8. get_servers_by_tag: Tag bazlı sunucu listeleme ve filtreleme

### Performance Tools (2 adet)
9. analyze_query_performance: Sorgu execution plan analizi, performans skoru
10. get_slow_queries: Yavaş sorguları listeleme ve optimizasyon önerileri

### Anomaly Detection Tools (3 adet - SSH Entegrasyonlu)
11. analyze_mongodb_logs: Log anomali analizi (SSH config desteği ile production log okuma)
12. get_anomaly_summary: Son analiz özeti (kritik anomaliler, güvenlik uyarıları)
13. train_anomaly_model: Model eğitimi (production SSH veriler ile training)