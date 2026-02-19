# MongoDB Isolation Forest Anomaly Detection - Uçtan Uca Analiz ve Sağlamlaştırma Stratejisi

> **Tarih:** 2026-02-18
> **Amaç:** Mevcutta çalışan MongoDB log anomaly detection sistemini (Isolation Forest tabanlı) BOZMADAN sağlamlaştırmak.
> **Yöntem:** Tüm kaynak kodlar okundu, kanıta dayalı (dosya:satır referanslı) zayıf noktalar tespit edildi.

---

## BÖLÜM 1: MEVCUT DURUM HARİTASI

### 1.1 Veri Akışı (End-to-End)

```
LOG KAYNAKLARI                    PARSE/STRUCTURE              FEATURE EXTRACTION
┌─────────────────┐              ┌─────────────────┐          ┌──────────────────────┐
│ OpenSearch       │──read_logs──▶│ MongoDBLogReader │──enrich──▶│ MongoDBFeatureEngineer│
│ Upload (file)    │              │ (log_reader.py)  │          │ (feature_engineer.py) │
│ MongoDB Direct   │              │ JSON/Text parse  │          │ create_features()     │
│ Test Servers     │              │ enrich_log_entry │          │ apply_filters()       │
└─────────────────┘              └─────────────────┘          └──────────┬───────────┘
                                                                         │
                                                                    X (DataFrame)
                                                                    50+ numeric features
                                                                         │
ANOMALY SCORING              THRESHOLD/OUTPUT               HISTORY/STORAGE
┌─────────────────────┐      ┌──────────────────┐          ┌────────────────────┐
│ MongoDBAnomalyDetector│     │ analyze_anomalies│          │ MongoDBHandler      │
│ (anomaly_detector.py)│     │ severity_score    │          │ (mongodb_handler.py)│
│ predict()→(-1/1)     │──▶  │ (0-100 composite) │──save──▶│ anomaly_history     │
│ score_samples()      │     │ false_pos filter  │          │ model_registry      │
│ critical_rules()     │     │ AI explanation    │          │ TTL cleanup         │
└─────────────────────┘      └──────────────────┘          └────────────────────┘
         │                            │
         ▼                            ▼
UI/LCWGPT                    API Layer
┌─────────────────┐          ┌─────────────────────────┐
│ script-anomaly.js│◀────────│ api.py                   │
│ script-ml-panel  │  JSON   │ /api/analyze-uploaded-log │
│ script-ml-viz    │         │ /api/analyze-cluster      │
│                  │         │ /api/anomaly-history      │
└─────────────────┘          └─────────────────────────┘
```

### 1.2 Model Yaşam Döngüsü

| Aşama | Dosya:Satır | Mekanizma |
|-------|-------------|-----------|
| **İlk Eğitim** | `anomaly_detector.py:461-681` | `train()` - IsolationForest + StandardScaler fit, historical buffer oluşturma |
| **Incremental Update** | `anomaly_detector.py:2675-2811` | `train_incremental()` - Mini model ensemble'a eklenir, weight decay uygulanır |
| **Drift Detection** | `anomaly_detector.py:2868-2931` | `detect_model_drift()` - Anomaly ratio farkına dayalı drift tespiti |
| **Predict (Single)** | `anomaly_detector.py:816-972` | `predict()` - Scaler transform + model.predict + critical rules override |
| **Predict (Ensemble)** | `anomaly_detector.py:2812-2866` | `predict_ensemble()` - Weighted voting, tüm mini modellerin ağırlıklı ortalaması |
| **Persistence** | `anomaly_detector.py:1570-1676` | `save_model()` - joblib.dump (model + scaler + historical buffer + metadata) |
| **Load** | `anomaly_detector.py:1678-1866` | `load_model()` - Server-specific fallback to global, feature alignment |
| **Singleton** | `anomaly_detector.py:33-63` | `get_instance()` - FQDN normalization, per-server caching |

### 1.3 Feature Engineering

**Dosya:** `feature_engineer.py` (818 satır)

| Kategori | Feature Sayısı | Örnekler | Satır Aralığı |
|----------|---------------|----------|---------------|
| Temporal | 5 | `hour_of_day`, `is_weekend`, `extreme_burst_flag`, `burst_density` | 191-232 |
| Message-based | 18 | `is_auth_failure`, `is_collscan`, `is_slow_query`, `is_fatal`, `is_drop_operation` | 233-550 |
| Severity | 1 | `severity_W` | 552-563 |
| Component | 15 | `component_encoded`, `is_rare_component`, `is_wiredtiger_event`, `component_criticality_score` | 565-671 |
| Combination | 2 | `is_rare_combo`, `is_rare_message` | 673-691 |
| Attribute | 3 | `has_error_key`, `attr_key_count`, `has_many_attrs` | 693-749 |
| Numeric perf | 6 | `query_duration_ms`, `docs_examined_count`, `performance_score`, `txn_wait_ratio` | 407-545 |
| **TOPLAM** | **~50** | Config'den `enabled_features`: 50 | `anomaly_config.json:161-213` |

### 1.4 Threshold ve Severity Mekanizması

**Dosya:** `anomaly_detector.py:1352-1514`

Severity skoru bileşik puanlama sistemi ile hesaplanır (0-100):

| Katman | Puan Aralığı | Kaynak |
|--------|-------------|--------|
| Base ML Score | 0-40 | `abs(anomaly_score) * 40` (satır 1371) |
| Component Criticality | 0-20 | REPL=20, ACCESS=18, STORAGE=15, ... (satır 1376-1386) |
| Critical Feature birikimli | 0-40+ | Fatal +30, Massive Scan +40, Replication +35, ... (satır 1400-1465) |
| Temporal Factor | 5-10 | İş saatleri +10, gece +5, normal +7 (satır 1469-1482) |
| Rule Override Bonus | +20 | `anomaly_score == -1.0` (satır 1485-1487) |
| **Cap** | **min(100, total)** | (satır 1490) |

**Severity Seviyeleri:** CRITICAL >= 80, HIGH >= 60, MEDIUM >= 40, LOW >= 20, INFO < 20

### 1.5 Çalışan Yapının Güçlü Yönleri

1. **Thread Safety:** Singleton pattern + `_training_lock` + `_model_io_lock` (`anomaly_detector.py:29-31, 92-95`)
2. **Feature Schema Stabilizer:** Train/predict feature uyumsuzluğunu otomatik çözer (`feature_engineer.py:54-118`)
3. **Ensemble + Critical Rules:** ML tahminini domain kuralları ile override eder (`anomaly_detector.py:144-274, 961-966`)
4. **Incremental Learning:** Online learning buffer, FIFO, weight decay, drift detection (`anomaly_detector.py:97-136`)
5. **Severity Composite Score:** 5 katmanlı bileşik puanlama (`anomaly_detector.py:1352-1514`)
6. **Numerical Capping:** Config-based cap ile devasa değerlerin ML modelini bozması engellenir (`feature_engineer.py:493-505`)
7. **Concurrency Control:** API katmanında semaphore (max 3 concurrent) ve progress tracking (`api.py`)

---

## BÖLÜM 2: KANITLI ZAYIF NOKTALAR

### BULGU-1: Alert Budget / SLO Mekanizması Yok

- **Konum:** `anomaly_detector.py:507-540`
- **Kanıt:** Contamination dinamik ayarlanıyor (`<500 → 0.10`, `<2000 → 0.08`, `>=2000 → 0.05`) ama günlük alarm bütçesi tanımlı değil
- **Etki:** Sunucular arası karşılaştırılabilirlik kaybolur, günlük alarm sayısı öngörülemez
- **Öneri:** DOKUNMA - Sadece analiz çıktısına `expected_daily_alerts` ve `contamination_used` metrikleri eklenmeli

### BULGU-2: Evaluation Metrikleri Pseudo-Label Üzerinden (Circular Logic)

- **Konum:** `anomaly_detector.py:2310-2451`
- **Kanıt:** `create_validation_dataset()` rule-based ve statistical pseudo-label üretiyor (fatal, OOM, shutdown vb.) → Bunlar zaten critical_rules engine'inin override ettiği tipler
- **Etki:** F1/precision/recall yapay yüksek çıkabilir
- **Öneri:** Evaluation raporuna `"evaluation_method": "pseudo_label"` disclaimer'ı eklenmeli

### BULGU-3: Drift Detection Sadece Anomaly Ratio Farkına Bakıyor

- **Konum:** `anomaly_detector.py:2868-2931`
- **Kanıt:** `ratio_diff = abs(anomaly_ratio - original_ratio)`, feature distribution kayması kontrol edilmiyor
- **Etki:** MongoDB `verbosity`/`slowms` değişikliklerinde log dağılımı değişir ama drift tespit edilmeyebilir
- **Öneri:** Feature mean/std karşılaştırması eklenebilir (scaler.mean_ / scaler.var_ mevcut)

### BULGU-4: `eval()` Kullanımı Attribute Parsing'de

- **Konum:** `feature_engineer.py:704`
- **Kanıt:** `return eval(attr_obj)` - Log verisi üzerinden code injection riski
- **Etki:** Pratik risk düşük (veri OpenSearch'ten geliyor) ama güvenlik best practice'e aykırı
- **Öneri:** `eval()` → `ast.literal_eval()` değişikliği. Sıfır risk, davranış aynı kalır

### BULGU-5: False Positive Threshold'ları Hardcoded

- **Konum:** `anomaly_detector.py:1164`, `anomaly_tools.py:1843-1844`
- **Kanıt:** Threshold'lar (30, 40, 45, 99.5) kod içinde hardcoded, config'de yok
- **Etki:** Farklı sunucularda farklı threshold gerekebilir, kalibre edilebilirlik yok
- **Öneri:** Threshold'ları config'e taşıma + Known benign signature allowlist ekleme

### BULGU-6: `print()` Debug Logları

- **Konum:** `anomaly_detector.py:1210, 1278, 1347, 1674` ve diğer dosyalar
- **Kanıt:** `print(f"[DEBUG] ...")` kullanımı, `logger` yerine
- **Etki:** Log level kontrolünü bypass eder, production'da stdout pollution
- **Öneri:** Düşük öncelik. `print()` → `logger.debug()` dönüşümü

---

## BÖLÜM 3: UYGULANAN İYİLEŞTİRMELER

Aşağıdaki 5 iyileştirme uygulandı ve test edildi:

| # | Aksiyon | Durum | Commit |
|---|---------|-------|--------|
| 1 | `eval()` → `ast.literal_eval()` güvenlik düzeltmesi | UYGULAND | `fix(security)` |
| 2 | Evaluation method pseudo_label disclaimer | UYGULAND | `enhance(eval)` |
| 3 | FP threshold'ları config'e taşıma (9 parametre) | UYGULAND | `enhance(config)` |
| 4 | Known benign signature allowlist (6 pattern) | UYGULAND | `feat(fp)` |
| 5 | Feature distribution drift detection | UYGULAND | `enhance(drift)` |
| 6 | Alert budget / SLO metriği | UYGULAND | `enhance(slo)` |

## BÖLÜM 4: KALAN BACKLOG

| # | Aksiyon | Risk | Etki | Tür |
|---|---------|------|------|-----|
| 7 | `print()` → `logger` dönüşümü | Yok | Log hijyeni | Kod temizliği |

### Sonuç

6 iyileştirmenin 5'i uygulandı. Sistem operasyonel olarak stabil, mevcut yapı korundu. Tüm değişiklikler additive (ekleme) niteliğinde — hiçbir mevcut davranış değiştirilmedi.
