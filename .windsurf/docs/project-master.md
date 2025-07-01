# MongoDB LangChain Assistant - Teknik Dokümantasyon

## 📁 Kapsamlı Proje Yapısı ve Modüler Mimari

```
mongodb-langchain-assistant/ (MongoDB-LLM-assistant/ - Production)
├── venv/                       # Virtual environment
├── config/                     # Konfigürasyon
│   ├── monitoring_servers.json # SSH sunucu konfigürasyonları
│   └── anomaly_config.json    # Anomaly detection konfigürasyonu (güncellendi)
├── src/                        # Ana kaynak kodu
│   ├── connectors/            # Bağlantı modülleri (Connector Katmanı/Bağlantı katmanı)
│   │   ├── __init__.py
│   │   ├── base_connector.py  # Abstract base class
│   │   ├── mongodb_connector.py # MongoDB bağlantısı, Connection pooling, bağlantı yönetimi
│   │   └── openai_connector.py  # LLM entegrasyonu, LLM bağlantısı
│   ├── agents/                # LangChain agent modülleri (Agent Katmanı/LangChain agent katmanı)
│   │   ├── __init__.py
│   │   ├── mongodb_agent.py   # Ana orchestration (SSH config desteği eklendi)
│   │   ├── query_validator.py # Güvenlik kontrolü
│   │   ├── query_translator.py # Doğal dil → MongoDB çevirici, Doğal dil → MongoDB
│   │   ├── schema_analyzer.py  # Veritabanı yapı analizi
│   │   └── tools.py           # LangChain araçları (güncellendi), LangChain tool tanımları (2 satır eklendi)
│   ├── monitoring/            # Linux Monitoring (Monitoring Katmanı/Linux monitoring katmanı)
│   │   ├── __init__.py
│   │   ├── linux_monitor.py   # SSH bağlantı ve metrik toplama, bağlantı yönetimi, SSH bağlantı ve metrik toplama
│   │   └── monitoring_tools.py # LangChain tool tanımları, 5 LangChain tool, 5 monitoring tool
│   ├── performance/           # Query Performance Analyzer (Performance Katmanı/Query performance katmanı)
│   │   ├── __init__.py
│   │   ├── query_analyzer.py  # Execution plan analizi
│   │   └── performance_tools.py # LangChain performance tools, 2 LangChain tool, 2 performance tool
│   ├── anomaly/               # Anomaly Detection Katmanı (güncellendi)
│   │   ├── __init__.py
│   │   ├── log_reader.py      # Log okuma modülü (JSON/Text desteği) + DynamicSSHLogReader (YENİ)
│   │   ├── feature_engineer.py # Feature extraction (15 aktif feature)
│   │   ├── anomaly_detector.py # Isolation Forest modeli
│   │   └── anomaly_tools.py   # LangChain anomaly tools (3 adet) (SSH config desteği eklendi)
│   ├── utils/                 # Yardımcı fonksiyonlar
│   └── schemas/               # Veri yapıları
├── models/                    # Model dosyaları (anomaly models)
├── output/                    # Anomali çıktıları (CSV, JSON)
├── web_ui/                    # Web arayüzü (SSH form entegrasyonu eklendi)
│   ├── api.py                # FastAPI backend (SSH config desteği eklendi)
│   ├── config.py             # Web kullanıcı arayüzü ayarları, Web konfigürasyonu
│   └── static/               # Ön yüz dosyaları (Frontend dosyaları) (SSH UI eklendi)
│       ├── index.html        # LC Waikiki kurumsal tasarım (SSH form eklendi)
│       ├── style.css         # Kurumsal renkler + UI enhancement (SSH stilleri eklendi)
│       └── script.js         # API iletişimi + görselleştirme (SSH kontrolü eklendi)
├── tests/                     # Test dosyaları
├── logs/                      # Günlük dosyaları (Sistem logları)
├── main.py                   # CLI giriş noktası ve ana giriş noktası
├── .env                       # Gizli yapılandırma (güncellendi)
├── .gitignore                # Git ignore listesi
└── requirements.txt          # Python bağımlılıkları (paramiko eklendi - güncellendi)
```

## 🔧 Detaylı Modül Analizi ve İşlevsel Özellikleri

### 1. Bağlantı Modülleri (Connectors) - Connector Katmanı

#### BaseConnector (base_connector.py)
- Abstract base class (Soyut temel sınıf)
- Ortak bağlantı arayüzü: connect(), disconnect(), validate_connection()
- Günlükleme altyapısı

#### MongoDBConnector - Teknik Detaylar
```
# MongoDB Bağlantısı - Teknik Özellikler:
- MongoClient ile bağlantı yönetimi
- Connection pooling (Bağlantı havuzu) ile güvenli bağlantı
MongoClient(uri, serverSelectionTimeoutMS=5000)
# Ping ile bağlantı doğrulama
client.admin.command('ping')
- Zaman aşımı: 5 saniye
- Otomatik yeniden bağlanma desteği
```

#### OpenAIConnector
```
# Konfigürasyon:
- ChatOpenAI LangChain entegrasyonu
- Model: gpt-4o
- Temperature: 0
- Maksimum token: 2000
- Zaman aşımı: 30 saniye
- Maksimum yeniden deneme: 2
```

### 2. Agent Modülleri - Agent Katmanı

#### QueryValidator (Sorgu Doğrulayıcı) - Gelişmiş Güvenlik Sistemi

Detaylı Güvenlik Özellikleri:
```python
class QueryValidator:
    # İzin verilen MongoDB operatörleri (genişletilmiş liste)
    allowed_operators = {
        '$eq', '$ne', '$gt', '$gte', '$lt', '$lte',
        '$in', '$nin', '$exists', '$type', '$regex',
        '$and', '$or', '$not', '$match', '$group',
        '$sort', '$limit', '$skip', '$project'
    }
    
    # Tehlikeli operatörler (engellenen)
    dangerous_operators = {
        '$where',      # JavaScript execution
        '$function',   # Custom functions
        '$accumulator' # Custom aggregation
    }
    
    # Güvenlik parametreleri:
    # - Derinlik limiti: 8 seviye, Maksimum 8 seviye
    # - Hassas koleksiyonlar: users, permissions, audit_logs
    # - JavaScript tespiti
    # - Aggregation pipeline doğrulaması
    # - Rate limiting altyapısı
```

#### SchemaAnalyzer (Şema Çözümleyici)

İki Analiz Modu:
1. analyze_collection_schema(): Temel analiz
2. analyze_collection_schema_advanced(): Hibrit analiz 
   - İlk 50 doküman (hızlı başlangıç)
   - $sample ile rastgele örnekleme
   - Skip metoduyla dağıtılmış örnekleme

Çıktılar:
- Alan tip analizi
- Doluluk oranları hesaplama
- Index bilgileri
- Öneriler (null alanlar, karışık tipler)

#### QueryTranslator (Sorgu Çevirici) - Gelişmiş NLP Motoru

Doğal Dil İşleme Stratejileri:
- LLM tabanlı çeviri
- Yazım hatası toleransı: Fuzzy matching sistemi
- Eş anlamlı tanıma: Synonym detection
- Bağlamsal çıkarım: Intent recognition
- Alan adı tahmini: Field name prediction
- Kurumsal odaklı sistem istemi

Çıktı Formatı:
```json
{
  "collection": "tahmin edilen koleksiyon",
  "operation": "find/aggregate/update",
  "query": {MongoDB sorgu objesi},
  "options": {limit, sort, projection},
  "explanation": "Türkçe açıklama",
  "assumptions": ["yapılan tahminler"]
}
```

Ek Metodlar:
- optimize_query(): Sorgu optimizasyonu
- explain_query(): Kullanıcı dostu açıklama

#### Tools (tools.py) - Güncellenmiş

MongoDB LangChain Araç Tanımları:
1. execute_query (mongodb_query): MongoDB sorgu çalıştırma (find, aggregate, count)
2. view_schema: Şema görüntüleme ve analiz
3. manage_indexes: Index yönetimi

Özellikler:
- Pydantic giriş doğrulaması
- JSON kodlayıcı (ObjectId, datetime desteği)
- Hata yönetimi

Anomaly Entegrasyonu (Güncellenmiş):
```python
# Yapılan Değişiklikler (2 satır eklendi):
from ..anomaly.anomaly_tools import create_anomaly_tools

# get_all_tools() fonksiyonuna ekleme:
anomaly_tools = create_anomaly_tools()
tools.extend(anomaly_tools)
```

#### MongoDBAgent - Ana Orchestration Katmanı (SSH Desteği Eklendi)

Ana Orchestration Özelikleri:
- Agent executor yönetimi
- Konuşma belleği
- Araç entegrasyonu (artık 13 tool ile)
- Standart JSON yanıt formatı
- Hata yönetimi ve yeniden deneme mantığı

SSH Entegrasyonu (Yeni):
```python
def process_query_with_args(self, user_input: str, additional_args: Dict[str, Any]):
    # SSH config ile sorgu işleme
    # Anomaly detection için özel format
    # Dynamic SSH parameter handling
```

### 3. Monitoring Modülleri - Monitoring Katmanı

#### linux_monitor.py - Core Monitoring Modülü

Temel Özellikler:
- Config Tabanlı Yapı: Hardcoded değer yok
- Çoklu Ortam Desteği: test, production, staging
- SSH Bağlantı Yönetimi: Paramiko ile güvenli bağlantı

Metrik Toplama Yetenekleri:
- CPU kullanımı ve yük ortalamaları
- Bellek (RAM) kullanımı
- Disk kullanımı
- Network bilgileri
- Process (işlem) analizi
- MongoDB durum kontrolü

Güvenlik Özellikleri:
- SSH key authentication
- Timeout koruması
- Connection pooling
- Error handling

#### monitoring_tools.py - LangChain Tool Entegrasyonu

Monitoring Tool'ları (5 adet):
4. check_server_status: Sunucu durumu kontrolü (uptime, hostname, OS bilgisi, online/offline durumu)
5. get_server_metrics: CPU, Memory, Disk, Network metrikleri (tüm metrikler veya spesifik tip, MongoDB process kontrolü)
6. find_resource_intensive_processes: En çok CPU/Memory kullanan işlemler (spesifik process arama, Top 5 resource consumer, yüksek kaynak kullanımı)
7. execute_monitoring_command: Güvenli komut çalıştırma (whitelist bazlı güvenlik, sadece monitoring komutları)
8. get_servers_by_tag: Tag bazlı sunucu gruplama (mongodb, production, test tag'leri, dinamik filtreleme)

### 4. Performance Modülleri - Performance Katmanı

#### query_analyzer.py - QueryPerformanceAnalyzer Sınıfı

Ana Özellikler:
- MongoDB explain() Analizi: Sorgu execution plan'larını detaylı analiz ve stage-by-stage inceleme
- Performans Skoru Hesaplama: 0-100 arası değerlendirme sistemi
- Stage Analizi: COLLSCAN, IXSCAN, FETCH tespiti
- Index Kullanım Analizi: Hangi indexlerin kullanıldığı
- Optimizasyon Önerileri: Performans iyileştirme tavsiyeleri
- Verimlilik Hesaplaması: Taranan/dönen doküman oranı
- İyileştirme Tahmini: Index ekleme senaryoları

Performans Değerlendirme Kriterleri ve Metrikler:
```
# Skorlama sistemi:
performance_score = {
    "time": 30,        # Execution time (max 30 puan)
    "efficiency": 30,  # Query efficiency (max 30 puan)
    "index": 25,       # Index usage (max 25 puan)
    "result_size": 15  # Result set size (max 15 puan)
}

# Detaylı puanlama:
- IXSCAN kullanımı: +40 puan (index kullanılıyor)
- COLLSCAN kullanımı: -30 puan (full collection scan)
- FETCH stage varlığı: -10 puan (ekstra veri çekme)
- Düşük docsExamined/docsReturned oranı: +20 puan
- Execution time optimizasyonu: +10 puan
```

#### performance_tools.py - LangChain Performance Tools

Performance Tool'ları (2 adet):
9. analyze_query_performance: Sorgu execution plan analizi, performans skoru hesaplama, stage detay analizi, index kullanım raporlama, optimizasyon önerileri sunma
10. get_slow_queries: Yavaş çalışan sorguları listeleme, execution time threshold bazında filtreleme, performance bottleneck tespiti, sorgu pattern analizi, yavaş sorgu tespiti

Tool Response Formatı:
```json
{
  "durum": "başarılı|hata|uyarı",
  "işlem": "query_performance_analysis",
  "açıklama": "Sorgu performans analizi tamamlandı",
  "sonuç": {
    "performance_score": 85,
    "execution_stats": {
      "execution_time": 15,
      "docs_examined": 1000,
      "docs_returned": 50
    },
    "stages": ["IXSCAN", "FETCH"],
    "index_usage": "user_age_index kullanıldı",
    "recommendations": ["Projection kullanarak veri boyutunu azaltın"]
  }
}
```

### 5. Anomaly Detection Modülleri - Anomaly Detection Katmanı (SSH Entegrasyonlu)

#### log_reader.py - Çok Formatlı Log Okuma Modülü + Dynamic SSH

Temel Özellikler:
- OpenSearch Hazırlığı: İleride OpenSearchLogReader sınıfı eklenecek
- Çift Format Desteği: JSON ve legacy text log formatları
- Otomatik Format Tespiti: _detect_log_format() metodu ile akıllı format algılama
- Paralel Okuma: ThreadPoolExecutor ile büyük dosyalar için optimize edilmiş okuma
- Zaman Filtresi: Son N saatteki logları okuma yeteneği

DynamicSSHLogReader Sınıfı (Yeni):
```python
class DynamicSSHLogReader:
    def set_connection_params(self, jump_server, jump_username,
                             mongodb_server, auth_method, target_username=None)
    def connect(self, jump_password, target_password=None)
    def read_logs(self, limit=None, last_hours=None)
    def _get_latest_log_file()
```

SSH Bağlantı Akışı (Yeni):
1. Jump Server Bağlantısı: Paramiko SSH client ile RAGNAROK/LCWECOMMERCE
2. TCP Tunnel: Jump üzerinden target'a direct-tcpip bağlantısı
3. Target Bağlantısı: LDAP (aynı kullanıcı) veya DBA (farklı kullanıcı) authentication
4. Log Okuma: /mongodata/log/ dizininden en güncel log dosyası okuma

Kritik Metodlar:
- read_logs(limit, last_hours)              # Ana okuma metodu
- _read_json_logs()                         # JSON format parser
- _read_text_logs()                         # Legacy text format parser
- _parse_text_message_attributes()          # Text'ten attribute çıkarma
- _detect_log_format()                      # Otomatik format tespiti
- set_connection_params()                   # Dynamic SSH config (YENİ)
- connect()                                 # SSH bağlantı kurma (YENİ)
- _get_latest_log_file()                   # En güncel log tespiti (YENİ)

Log Okuma Süreci (Production):
1. En güncel log dosyası tespiti: sudo ls -t /mongodata/log/mongod.log* | grep -v '.gz$' | head -1
2. Log okuma: sudo head -n {limit} veya sudo cat
3. JSON parse ve DataFrame dönüşümü

Veri Akışı (Güncellenmiş):
Production MongoDB Logs → Dynamic SSH Reader → Feature Engineering → Filtreleme → Isolation Forest → Anomaly Analysis → LangChain Tool Response → MongoDB Agent → User

#### feature_engineer.py - Gelişmiş Feature Extraction Modülü

Feature Engineering Özellikleri:
- 15 Aktif Feature Extraction: Temporal, message, severity, component bazlı çok boyutlu analiz
- Config Tabanlı Yönetim: Hangi feature'ların aktif olacağı config dosyasından kontrol
- Filtreleme Stratejisi: Auth success ve reauthenticate mesajlarını akıllı filtreleme
- Feature İstatistikleri: Binary ve continuous feature analizi

15 Aktif Feature Kategorileri:
```
# Temporal Features (4):
- hour_of_day          # Saat bazlı pattern analizi
- is_weekend           # Hafta sonu anomali tespiti
- extreme_burst_flag   # Ani yoğunluk artışı
- burst_density        # Yoğunluk dağılımı

# Message Features (3):
- is_auth_failure      # Authentication failure tespiti
- is_drop_operation    # Kritik DROP operasyonları
- is_rare_message      # Nadir görülen mesaj tipleri

# Component Features (3):
- component_encoded    # Component encoding
- is_rare_component    # Nadir component'ler
- component_changed    # Component değişim analizi

# Severity Features (1):
- severity_W           # Warning level severity

# Attribute Features (4):
- has_error_key        # Error anahtar kelimesi varlığı
- attr_key_count       # Attribute sayısı
- has_many_attrs       # Çok sayıda attribute varlığı
- (ve diğer attr features)
```

Filtreleme Stratejisi:
```
# Otomatik filtreleme:
- Auth success mesajları (%14.2 log azaltma)
- Reauthenticate mesajları (noise reduction)
- Rare threshold: 100 (nadir event minimum sayısı)
```

#### anomaly_detector.py - Isolation Forest Anomaly Detection

Model Özellikleri:
```
# Isolation Forest Parametreleri:
- Algorithm: scikit-learn Isolation Forest
- Contamination: %3 (anomali oranı)
- n_estimators: 300 (ağaç sayısı)
- Model Persistence: joblib ile save/load
- Random State: 42 (tekrarlanabilir sonuçlar)
```

Analiz Yetenekleri:
- Component Bazlı Anomali Dağılımı: Hangi component'lerde anomali var
- Temporal Pattern Analizi: Zaman bazlı anomali kalıpları
- DROP Operasyonu Tespiti: Kritik güvenlik operasyonları
- Feature Importance Hesaplama: Hangi feature'lar önemli
- Detaylı Güvenlik Analizi: Security-focused anomaly detection

Export Yetenekleri:
- CSV Export: Tablo formatında anomali sonuçları
- JSON Export: Structured data format
- Model Persistence: Eğitilmiş model kaydetme/yükleme

#### anomaly_tools.py - LangChain Anomaly Tools (SSH Entegrasyonlu)

3 Anomaly LangChain Tool (SSH Desteği ile):
11. analyze_mongodb_logs: Log anomali analizi
   - Parametreler: last_hours (varsayılan: 24), limit (varsayılan: 10000)
   - SSH Desteği: Dynamic SSH config ile production log okuma
   - Özellikler: Otomatik model eğitimi (yoksa), anomali skorlama, güvenlik analizi
   - Çıktı: Anomali listesi, güvenlik uyarıları, öneriler
12. get_anomaly_summary: Son analiz özeti
   - İçerik: Kritik anomaliler, güvenlik uyarıları, istatistikler
   - Format: MongoDB Agent uyumlu JSON response
   - Dil: Türkçe açıklamalar ve öneriler
13. train_anomaly_model: Model eğitimi
   - Parametreler: last_hours (eğitim verisi), force (zorla eğitim)
   - SSH Desteği: Production veriler ile model training
   - Gereksinimler: Minimum 1000 log
   - Özellikler: Model validation, performance metrics

SSH Entegrasyonu (Yeni):
```
# SSH config parametresi desteği
# Dinamik bağlantı yönetimi
# Geriye uyumluluk korundu
# Production authentication support
```

Tool Response Formatı (Anomaly):
```json
{
  "durum": "başarılı|uyarı|hata",
  "işlem": "anomaly_analysis",
  "açıklama": "MongoDB log anomali analizi tamamlandı",
  "sonuç": {
    "total_anomalies": 15,
    "security_alerts": 3,
    "top_components": ["replication", "command"],
    "critical_operations": ["DROP collection"],
    "recommendations": ["Kritik operasyonları inceleyin"]
  },
  "öneriler": ["DROP operasyonları için security review"]
}
```

### 6. Web Kullanıcı Arayüzü Katmanı - SSH Form Entegrasyonlu

#### FastAPI Backend (api.py) - SSH Config Desteği

Mevcut Uç Noktalar:
- POST /api/query: Sorgu işleme
- GET /api/status: Sistem durumu
- GET /api/collections: Koleksiyon listesi
- GET /api/schema/{name}: Şema detayları

SSH API Entegrasyonu (Yeni):
```python
class SSHConfig(BaseModel):
    jump_server: str
    jump_username: str
    jump_password: str
    mongodb_server: str
    auth_method: str
    target_username: Optional[str]
    target_password: Optional[str]
```

# SSH config endpoint'leri
# SSH test ve validation API'leri

Güvenlik:
- API anahtar kimlik doğrulaması
- Rate limiting hazırlığı
- CORS middleware
- Giriş doğrulaması
- SSH password memory-only storage (Yeni)

#### Ön Yüz - SSH Form Entegrasyonlu UI

SSH Form HTML Eklentileri (Yeni):
```html
<section id="sshSection" class="ssh-section">
  <!-- Jump server, kullanıcı, şifre inputları -->
  <!-- MongoDB sunucu seçimi -->
  <!-- LDAP/DBA auth seçimi -->
  <!-- SSH test ve kaydetme butonları -->
</section>
```

CSS SSH Stilleri (Yeni):
- Form kontrolleri ve responsive tasarım
- SSH status göstergeleri
- LC Waikiki kurumsal renk entegrasyonu
- Modal dialog sistem

JavaScript SSH Kontrolü (Yeni):
```javascript
// SSH config yönetimi
let sshConfig = {
    jump_server: '', jump_username: '', jump_password: '',
    mongodb_server: '', auth_method: '', 
    target_username: '', target_password: ''
};

// Test ve kaydetme fonksiyonları
function handleTestSSH() { /* SSH bağlantı testi */ }
function handleSaveSSH() { /* Config kaydetme */ }
```

Yeni UI Özellikleri ve Görselleştirme:
- displayResult() Geliştirildi: Metrik parse ve görselleştirme sistemi
- CSS Grid Layout: Metrik kutular için gelişmiş düzen
- İkon ve Animasyonlar: Her metrik tipi için özel görünüm
- Kullanıcı Yönlendirmeleri: "Yeni işlem yapmak ister misiniz?" mesajları
- JSON sözdizimi vurgulama: Gelişmiş kod renklendirme
- Performance Score Gösterimi: Görsel performans skorları
- Circular Progress Skorlar: Dairesel ilerleme göstergeleri
- Execution Tree Görünümü: İşlem ağacı görselleştirmesi
- Before/After Karşılaştırmaları: Optimizasyon öncesi/sonrası
- Metrik Kartları ve Animasyonlar: İnteraktif kart sistemi
- WebSocket hazırlığı: Real-time communication infrastructure
- Duyarlı tasarım: Multi-device uyumluluk (Mobile uyumlu, responsive design)
- Modal yapısı: Gelişmiş user interaction
- Loading States: Yükleme durumu göstergeleri
- Smooth Animasyonlar: Akıcı geçiş efektleri
- SSH Form Integration: Production SSH ayarları (Yeni)

#### CLI Arayüzü (main.py)

MongoDBAssistantCLI:
- Komut satırı arayüzü
- Özel komutlar: help, status, collections, schema, history, clear
- Renkli ve emoji destekli çıktılar
- Hata yönetimi
- Graceful shutdown

## 🤖 Prompt Mühendisliği ve Sistem İstemi Yapısı

### System Prompt Yapısı ve Özellikleri

```python
system_prompt = """Sen bir MongoDB veritabanı asistanısın. Kullanıcıların doğal dil sorgularını MongoDB işlemlerine çevirip çalıştırıyorsun.

GÖREVLER:
1. Kullanıcının doğal dil sorgusunu anla
2. Uygun MongoDB işlemini belirle
3. Güvenli ve optimize edilmiş sorgular oluştur
4. Sonuçları anlaşılır şekilde sun

KURALLAR:
- Her zaman önce schema'yı kontrol et
- Güvenlik uyarılarına dikkat et
- Büyük sonuç setleri için limit kullan
- Hataları kullanıcı dostu açıkla

ARAÇLAR:
MongoDB (3): mongodb_query, view_schema, manage_indexes
Monitoring (5): check_server_status, get_server_metrics, find_resource_intensive_processes, execute_monitoring_command, get_servers_by_tag
Performance (2): analyze_query_performance, get_slow_queries
Anomaly (3): analyze_mongodb_logs, get_anomaly_summary, train_anomaly_model"""
```

### LLM Davranış Kontrolü
- Türkçe iletişim zorunluluğu: Tüm yanıtlar Türkçe
- Tool kullanım kuralları: Structured tool usage
- Güvenlik uyarıları: Security-first approach
- Örnek kullanımlar: Context-aware examples
- Temperature: 0: Deterministik yanıtlar
- Max tokens: 2000: Optimize token usage
- Structured output zorunluluğu: JSON format requirement
- JSON response format: Consistent output structure

### Query Translation Stratejileri
- Yazım hatası toleransı: Fuzzy matching algoritmaları
- Eş anlamlı tanıma: Synonym detection ve replacement
- Bağlamsal çıkarım: Intent recognition ve context awareness
- Alan adı tahmini: Field name prediction algoritmaları

## 🔒 Kapsamlı Güvenlik Önlemleri

### Bağlantı Güvenliği
- Kimlik bilgileri .env dosyasında
- .gitignore ile sürüm kontrolünden hariç
- Bağlantı dizesi şifreleme
- Zaman aşımı ve yeniden deneme limitleri

### Sorgu Güvenliği
- QueryValidator ile her sorgu kontrol edilir
- Tehlikeli operatörler engellenir
- Derinlik ve karmaşıklık limitleri
- Hassas koleksiyonlarda ekstra kontrol

### LLM Güvenliği
- Temperature: 0 (tutarlı yanıtlar)
- Yapılandırılmış çıktı zorunluluğu
- Token limitleri
- Hata durumlarında fallback

### SSH Güvenliği
- Private key authentication
- Hardcoded credential yok
- Config dosyasından okuma
- Connection timeout koruması

### Dynamic SSH Güvenliği (Yeni)
- Memory-Only Password Storage: Şifreler localStorage'da saklanmaz
- SSH Key Policy: AutoAddPolicy (production'da değiştirilmeli)
- Config Validation: SSH parameter doğrulaması
- Connection Cleanup: Hata durumunda bağlantı temizliği
- Jump Server Security: Multi-hop SSH güvenliği
- Authentication Methods: LDAP/DBA auth support

### Komut Güvenliği (Whitelist Bazlı)
```
# Whitelist bazlı komut çalıştırma
allowed_commands = [
    "uptime", "hostname", "df", "free",
    "ps", "top", "netstat", "ss", "ip",
    "cat /proc/cpuinfo", "systemctl status"]
# Private key authentication
# Timeout koruması
```

### Anomaly Detection Güvenliği
- Config Güvenliği: Hassas bilgiler .env'de
- Log Filtreleme: Auth success otomatik filtreleme (noise reduction)
- DROP Tespiti: Kritik operasyonlar işaretleme ve güvenlik uyarıları
- Rate Limiting: %3 anomali threshold (false positive kontrolü)

### API Güvenliği
- API key authentication
- Rate limiting
- Input validation
- CORS kontrolleri

### Config Güvenliği
- .env dosyası .gitignore'da
- Hassas bilgiler environment variable
- Production config'leri ayrı

## 📝 Konfigürasyon Yönetimi

### Güncellenmiş Environment Variables (.env)
```
# MongoDB Ayarları
MONGODB_URI=mongodb://localhost:27017/chatbot_test
OPENAI_API_KEY=sk-proj-...

# Linux Monitoring Ayarları
MONITORING_ENV=test
MONITORING_CONFIG_PATH=config/monitoring_servers.json
MONITORING_DEFAULT_TIMEOUT=10
MONITORING_SSH_KEY_BASE_PATH=
```

### monitoring_servers.json Yapısı
```json
{
  "environments": {
    "test": {
      "ssh_config": {
        "default_user": "vagrant",
        "key_base_path": "path/to/keys"
      },
      "servers": {
        "mongodb-node1": {
          "host": "127.0.0.1",
          "port": 2200,
          "key_file": "{key_base_path}/private_key",
          "tags": ["mongodb", "primary", "test"]
        }
      }
    },
    "production": {
      "servers": {}
    }
  },
  "monitoring_commands": {
    "cpu": {
      "usage": "top -bn1 | grep 'Cpu(s)' ..."
    }
  }
}
```

### anomaly_config.json Yapısı (SSH Entegrasyonlu - Güncellenmiş)
```json
{
  "environments": {
    "test": {
      "data_sources": {
        "file": {
           "enabled": true,
           "format": "json",
          "path": "/path/to/test/logs"
        },
        "opensearch": {
           "enabled": false,
           "host": "10.29.21.32",
          "index": "mongodb-logs-test"
        }
      },
      "model_params": {
        "contamination": 0.03,
        "n_estimators": 300,
        "min_training_samples": 1000
      },
      "features": {
        "temporal": ["hour_of_day", "is_weekend", "burst_density"],
        "message": ["is_auth_failure", "is_drop_operation"],
        "component": ["component_encoded", "is_rare_component"],
        "severity": ["severity_W"],
        "attributes": ["has_error_key", "attr_key_count"]
      }
    },
    "production": {
      "data_sources": {
        "file": {
           "enabled": true,
           "format": "text",
          "path": "/var/log/mongodb"
        },
        "ssh": {
          "enabled": true,
          "jump_servers": {
            "RAGNAROK": {"host": "10.29.1.229", "port": 22},
            "LCWECOMMERCE": {"host": "10.62.0.70", "port": 22}
          },
          "mongodb_servers": {
            "lcwmongodb01n1": {"host": "10.29.20.163"},
            "lcwmongodb01n2": {"host": "10.29.20.172"},
            "lcwmongodb01n3": {"host": "10.29.20.171"}
          },
          "auth_methods": ["LDAP", "DBA"],
          "log_path": "/mongodata/log/"
        },
        "opensearch": {
           "enabled": false,
           "host": "10.29.21.32",
          "index": "mongodb-logs-prod"
        }
      }
    }
  }
}
```

Özellikler:
- Test/Production Ortam Ayrımı: Farklı veri kaynakları ve formatlar
- File ve OpenSearch Veri Kaynakları: Esnek veri okuma seçenekleri
- SSH Configuration: Production jump server ve MongoDB cluster bilgileri (Yeni)
- Model Parametreleri Merkezi Yönetimi: Isolation Forest config
- Feature Configuration: Aktif feature'ların yönetimi

## 📐 Standart JSON Çıktı Formatı
```json
{
  "durum": "başarılı/uyarı/hata",
  "işlem": "yapılan işlemin adı",
  "koleksiyon": "hedef koleksiyon",
  "açıklama": "ne yapıldığının Türkçe açıklaması",
  "tahminler": ["yapılan tahminler"],
  "sonuç": {işlem sonucu},
  "öneriler": ["iyileştirme önerileri"]
}
```

## 🚀 Kurulum ve Çalıştırma

### Backend Kurulum
```bash
# Virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Güncellenmiş bağımlılıklar (scikit-learn, joblib, paramiko eklendi)
pip install -r requirements.txt

# .env dosyası (güncellenmiş)
MONGODB_URI=mongodb://localhost:27017/chatbot_test
OPENAI_API_KEY=sk-proj-...
MONITORING_ENV=test
MONITORING_CONFIG_PATH=config/monitoring_servers.json
```

### Başlatma Talimatları
```bash
# Virtual environment'ı aktive et
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# Uygulamayı başlat
python main.py
```

### Web Kullanıcı Arayüzü Çalıştırma
```bash
# FastAPI sunucusu
python -m uvicorn web_ui.api:app --reload

# Tarayıcı: http://localhost:8000
# API Anahtarı: lcw-test-2024
```

### SSH Ayarları Kullanımı (Yeni)
1. Web UI Başlatma: http://localhost:8000
2. SSH Ayarları: SSH AYARLARI butonuna tıklayın
3. Jump Server Seçimi: RAGNAROK veya LCWECOMMERCE
4. Credentials Girişi: Kullanıcı adı ve şifre
5. MongoDB Sunucu Seçimi: lcwmongodb01n1/n2/n3
6. Auth Method: LDAP veya DBA
7. Test ve Kaydetme: Bağlantı test edip config kaydedin
```