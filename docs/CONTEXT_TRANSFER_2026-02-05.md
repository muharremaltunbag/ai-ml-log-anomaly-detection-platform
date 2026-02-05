# 📚 MongoDB Log Anomaly Detection - Proje Bağlam Aktarım Dokümanı

**Tarih:** 5 Şubat 2026
**Proje:** LC Waikiki – MongoDB Log Anomaly Detection & DBA Assistant
**Oturum Türü:** LCWGPT Input-Pipeline Kontrolü ve Run-Level Metadata

---

## 1. 📌 Projenin Amacı ve Hedefleri

### Proje Neden Başlatıldı?
LC Waikiki'nin 45+ MongoDB sunucusu ve 21+ cluster'ı kapsayan geniş NoSQL altyapısında:
- Manuel log analizi sürdürülebilir değildi
- Anomali tespiti reaktif (sorun olduktan sonra) yapılıyordu
- DBA ekibinin iş yükü çok yüksekti

### Hangi Problemi Çözüyoruz?
1. **Proaktif anomali tespiti** - Sorunları oluşmadan önce tespit etmek
2. **Otomatik açıklama** - ML ile tespit edilen anomalilerin LCWGPT ile yorumlanması
3. **Sunucu bazlı izolasyon** - Her sunucunun kendi model ve analizine sahip olması
4. **Session sürekliliği** - Farklı oturumlarda modelin korunması

### Nihai Hedef
Tam otomatik, sunucu bazlı, AI destekli MongoDB log anomali tespit ve açıklama sistemi.

---

## 2. 🔒 Genel Kurallar ve Etkileşim Prensipleri

### Çalışma Kuralları
| Kural | Açıklama |
|-------|----------|
| **Varsayım YAPMA** | Dosya içeriği görmeden kod önerisi üretme |
| **Dosya/Satır Düzeyi** | Her değişiklik için dosya adı, satır, gerekçe belirt |
| **Kullanıcı Onayı** | Her adım sonunda "Devam edelim mi?" sor |
| **Minimal Değişiklik** | Sadece ilgili bloğu değiştir, tüm dosyayı yeniden yazma |
| **Geriye Uyumluluk** | Mevcut çalışan yapıyı bozma |

### LLM Mimarisi
- **Claude** → Teknik analiz, ML state kontrolü, prompt tasarımı
- **LCWGPT** → Anomali sonuçlarını natural language ile açıklama (LC Waikiki kurumsal LLM)
- **ChatGPT** → Prompt tasarımı ve versiyonlama

---

## 3. 🛠️ Yapılan Geliştirmeler ve Teknik Adımlar

### Bu Oturumda Tamamlanan Ana Hedefler

**Hedef:** LCWGPT Input-Pipeline Kontrolü
- LCWGPT'ye giden payload'ın SADECE ilgili sunucunun EN GÜNCEL anomaly sonuçlarını içermesini garanti etmek

### Önceki Oturumda Tamamlananlar (Referans)
- ML model lifecycle (server-specific create → incremental → save → reload) **5/5 test PASSED**
- MongoDBAnomalyDetector ve AnomalyDetectionTools düzeltmeleri
- Sunucu bazlı Singleton pattern implementasyonu

---

## 4. ✅ Bu Oturumda Yapılan Değişiklikler

### Öneri 1: Context Binding Güçlendirmesi

**Dosya:** src/anomaly/anomaly_tools.py
**Fonksiyon:** _generate_ai_explanation() (Satır ~1700)
**İşlevi:** LCWGPT'ye anomali verilerini gönderip AI açıklaması alan fonksiyon

**Değişiklik:**
Basit server_info = f"Sunucu: {server_name}\n" yerine güçlü context bloğu eklendi:

`python
run_context = f"""
═══════════════════════════════════════════════════════════════════════════════
📌 ANALİZ BAĞLAMI (BU OTURUM İÇİN GEÇERLİ - DİĞER SUNUCULAR İÇİN GEÇERLİ DEĞİL)
═══════════════════════════════════════════════════════════════════════════════
🆔  Run ID: {run_id or 'N/A'}
🖥️  Sunucu: {server_name or 'Belirtilmemiş'}
📅  Analiz Zamanı: {context_timestamp}
📊  Toplam Log Sayısı: {summary.get('total_logs', 0):,}
🔴  Tespit Edilen Anomali: {summary.get('n_anomalies', 0)}
...
⚠️  KRİTİK TALİMAT:
    • Bu analiz YALNIZCA "{server_name}" için geçerlidir.
    • Başka MongoDB sunucuları hakkında yorum veya öneri YAPMA.
═══════════════════════════════════════════════════════════════════════════════
"""
`

**Neden:** LCWGPT'nin sadece ilgili sunucuyu yorumlamasını, genel tavsiye vermemesini sağlamak.

---

### Öneri 2: API System Prompt Sunucu İzolasyonu

**Dosya:** web_ui/api.py
**Fonksiyon:** chat_query_anomalies() (Satır ~1745)
**İşlevi:** Chat üzerinden anomali sorgulama endpoint'i - LCWGPT ile etkileşim

**Değişiklik:**
System prompt'a sunucu izolasyon kuralları eklendi:

`python
system_prompt = """...
═══════════════════════════════════════════════════════════════════════════════
🚨 KRİTİK KURAL - SUNUCU İZOLASYONU (HER ZAMAN UYGULA)
═══════════════════════════════════════════════════════════════════════════════
1. Sana verilen anomali verileri SADECE belirli bir MongoDB sunucusuna aittir.
2. Yanıtlarında YALNIZCA bu sunucuya özgü analiz ve öneriler yap.
3. Başka MongoDB sunucuları veya genel cluster tavsiyeleri VERME.
4. Her yanıtının BAŞINDA hangi sunucuyu analiz ettiğini açıkça belirt.
...
"""
`

**Neden:** LCWGPT'nin farklı sunucu analizlerini karıştırmaması, her yanıtta sunucu adını belirtmesi.

---

### Öneri 3.1: Run ID Üretim Fonksiyonu

**Dosya:** src/anomaly/anomaly_tools.py
**Konum:** _load_config() metodundan sonra (Satır ~95-110)
**İşlevi:** Her analiz oturumu için benzersiz ID üretimi

**Eklenen Kod:**
`python
def _generate_run_id(self, server_name: str = None) -> str:
    """
    Her analiz oturumu için benzersiz bir Run ID üretir.
    Format: run_{server}_{timestamp}_{random}
    Örnek: run_ecaztrdbmng015_20250116_153042_a7b3c9
    """
    import uuid
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    random_suffix = uuid.uuid4().hex[:6]
    
    if server_name:
        clean_server = server_name.lower().replace('.', '_').replace('-', '_')[:20]
        run_id = f"run_{clean_server}_{timestamp}_{random_suffix}"
    else:
        run_id = f"run_global_{timestamp}_{random_suffix}"
    
    logger.info(f"📍 Generated Run ID: {run_id}")
    return run_id
`

**Neden:** Her analiz run'ının takip edilebilmesi, log'larda ve storage'da gruplama yapılabilmesi.

---

### Öneri 3.2: analyze_mongodb_logs() İçinde Run ID Üretimi

**Dosya:** src/anomaly/anomaly_tools.py
**Fonksiyon:** nalyze_mongodb_logs() (Satır ~335)
**İşlevi:** Ana anomali analiz fonksiyonu - tüm source type'ları (opensearch, upload, file) yönetir

**Değişiklikler:**

1. **Fonksiyon başına run_id üretimi eklendi:**
`python
# Host filter'dan sunucu adını erken çıkar (run_id için)
early_server_name = None
host_filter_early = args_dict.get("host_filter")
if host_filter_early:
    if isinstance(host_filter_early, list) and host_filter_early:
        early_server_name = host_filter_early[0].split('.')[0]
    elif isinstance(host_filter_early, str):
        early_server_name = host_filter_early.split('.')[0]

# Run ID üret
current_run_id = self._generate_run_id(server_name=early_server_name)
logger.info(f"═══ ANALYSIS RUN STARTED ═══")
logger.info(f"📍 Run ID: {current_run_id}")
`

2. **Tüm result objelerine run_id eklendi:**
   - OpenSearch result (Satır ~920): "run_id": current_run_id
   - Upload result (Satır ~600): "run_id": current_run_id
   - File result (Satır ~1130): "run_id": current_run_id
   - enhanced_analysis dict (Satır ~1100): enhanced_analysis["run_id"] = current_run_id

**Neden:** Her analiz sonucunun hangi run'a ait olduğunun takip edilmesi.

---

### Öneri 3.3: _generate_ai_explanation() Fonksiyonuna run_id Parametresi

**Dosya:** src/anomaly/anomaly_tools.py
**Fonksiyon:** _generate_ai_explanation() (Satır ~1580)

**Değişiklikler:**

1. **Fonksiyon imzası güncellendi:**
`python
# ÖNCESİ:
def _generate_ai_explanation(self, anomaly_data: Dict[str, Any], server_name: str = None) -> Dict[str, Any]:

# SONRASI:
def _generate_ai_explanation(self, anomaly_data: Dict[str, Any], server_name: str = None, run_id: str = None) -> Dict[str, Any]:
`

2. **Context bloğuna run_id eklendi:**
`python
run_context = f"""
...
🆔  Run ID: {run_id or 'N/A'}
🖥️  Sunucu: {server_name or 'Belirtilmemiş'}
...
"""
`

3. **Tüm çağrı noktalarına run_id parametresi eklendi:**
   - OpenSearch çağrısı (Satır ~880): un_id=current_run_id
   - Upload çağrısı (Satır ~570): un_id=current_run_id
   - File çağrısı (Satır ~1090): un_id=current_run_id

**Neden:** LCWGPT'nin hangi run'ı yorumladığını bilmesi, log takibi.

---

## 5. 📂 Analiz Edilen Modüller ve İşlevleri

### src/anomaly/anomaly_tools.py
**İşlev:** Anomali tespit tool'larının ana dosyası
- AnomalyDetectionTools class'ı
- nalyze_mongodb_logs() - Ana analiz fonksiyonu (opensearch, upload, file destekler)
- _generate_ai_explanation() - LCWGPT çağrısı yapan fonksiyon
- _ensure_detector_ready() - Sunucu bazlı detector instance yönetimi
- _filter_false_positives() - False positive filtreleme
- _perform_enhanced_analysis() - ML analizi ve feature engineering

### src/connectors/lcwgpt_connector.py
**İşlev:** LCWGPT API bağlantı yöneticisi
- LCWGPTChat - LangChain uyumlu chat model wrapper
- LCWGPTConnector - Bağlantı ve invoke yönetimi
- Payload formatı: {"message": "...", "context": "...", "model": "Sonnet", "institution_id": "..."}
- **Bu dosya değiştirilmedi** - Sadece transport katmanı, ne gönderileceğini belirLEMİYOR

### web_ui/api.py
**İşlev:** FastAPI backend - UI ile iletişim
- /api/chat-query-anomalies - Chat üzerinden LCWGPT sorgulama
- /api/analyze-uploaded-log - Log analizi endpoint'i
- /api/dba/analyze-specific-time - DBA spesifik zaman analizi
- Progress tracking, storage entegrasyonu, sunucu validasyonu

---

## 6. 🔧 Kullanılan Teknolojiler

| Teknoloji | Kullanım Alanı |
|-----------|----------------|
| **Python/FastAPI** | Backend API |
| **LangChain** | LLM entegrasyonu |
| **LCWGPT (Sonnet)** | AI açıklama üretimi |
| **IsolationForest** | ML anomali tespiti |
| **OpenSearch** | Log toplama ve sorgulama |
| **MongoDB** | Storage ve metadata |
| **Pandas/NumPy** | Feature engineering |

---

## 7. 📊 Güncel Durum

### Tamamlanan Modüller
| Modül | Durum |
|-------|-------|
| ML Model Lifecycle | ✅ 5/5 test PASSED |
| Sunucu Bazlı Singleton | ✅ Çalışıyor |
| LCWGPT Context Binding | ✅ Uygulandı |
| System Prompt İzolasyonu | ✅ Uygulandı |
| Run-Level Metadata | ✅ Uygulandı |

### Test Edilmesi Gerekenler
1. OpenSearch analizi yapıp log'larda "Run ID" görünümü
2. LCWGPT yanıtında sunucu adının başta belirtilmesi
3. Farklı sunucular için farklı run_id üretimi
4. Storage'a run_id ile kayıt

---

## 8. 🚀 Kaldığımız Yer ve Sonraki Adımlar

### Şu Anki Aşama
LCWGPT Input-Pipeline Kontrolü **TAMAMLANDI**. Tüm değişiklikler uygulandı:
- Context Binding ✅
- System Prompt İzolasyonu ✅
- Run-Level Metadata ✅

### Sonraki Potansiyel Adımlar
1. **Entegrasyon Testi** - Tüm değişikliklerin birlikte çalıştığını doğrulama
2. **UX Akışı Tasarımı** - Sunucu seçimi → Anomaly run → LCWGPT çağrısı → UI gösterimi
3. **Storage Entegrasyonu** - run_id ile anomali sonuçlarının MongoDB'ye kaydı
4. **Chat History** - Aynı run içindeki sohbet geçmişinin korunması

---

## 9. 📁 Proje Dosya Yapısı (Referans)

`
MongoDB-LLM-assistant/
├── config/
│   ├── anomaly_config.json
│   └── cluster_mapping.json
├── models/
│   ├── isolation_forest.pkl
│   └── isolation_forest_{server_name}.pkl
├── src/
│   ├── anomaly/
│   │   ├── anomaly_detector.py      # ML model yönetimi
│   │   ├── anomaly_tools.py         # ⭐ Ana değişiklik dosyası
│   │   ├── feature_engineer.py
│   │   └── log_reader.py
│   ├── connectors/
│   │   ├── lcwgpt_connector.py      # LCWGPT API bağlantısı
│   │   └── mongodb_connector.py
│   └── storage/
│       └── storage_manager.py
├── web_ui/
│   ├── api.py                        # ⭐ İkinci değişiklik dosyası
│   └── static/
└── tests/
`


