# MongoDB Log Anomaly Detection — Proje Bağlam Aktarımı
> **Tarih:** 2026-02-26
> **Branch:** `claude/enhance-opensearch-logging-HtRk7`
> **Toplam Commit:** 53 | **Son Commit:** `c76b6f8`

---

## 1. PROJENİN AMACI VE HEDEFLERİ

### Neden Başlatıldı?
LCWaikiki'nin veritabanı ekibi (DBA Team), MongoDB / MSSQL / Elasticsearch sunucularından gelen log verilerini **manuel olarak** izliyor. Yüzlerce sunucu, binlerce satır log, yüksek MTTR (mean time to resolve). Gerçek sorunlar gürültüde kayboluyordu.

### Hangi Problemi Çözüyoruz?
1. **Anomali Tespiti:** ML (Isolation Forest) ile loglardan otomatik anomali tespiti
2. **Doğal Dil Etkileşimi:** DBA'ların "son 1 saatte neler oldu?" gibi sorularla sisteme ulaşması (LLM + LangChain)
3. **Çok Kaynaklı (Multi-Source) Destek:** MongoDB, MSSQL, Elasticsearch — tümü OpenSearch üzerinden
4. **Prediction Layer:** Trend analizi, rate alerting, forecasting ile anomali tahmini
5. **LCWaikiki Entegrasyonu:** Kurumsal LCW GPT (LLM) üzerinden AI açıklamalar

### Nihai Hedef
- Production-grade, self-service DBA monitoring aracı
- 3 veri kaynağı (MongoDB / MSSQL / Elasticsearch) için tam parite
- Prediction/forecasting UI entegrasyonu (sonraki aşama)
- Otomatik retrain, drift detection, feedback loop

---

## 2. GENEL KURALLAR VE ETKİLEŞİM PRENSİPLERİ

| Kural | Açıklama |
|-------|----------|
| **Varsayım yapma** | Repo'daki güncel kodu yeniden okumadan karar verme |
| **Mevcut yapıyı bozma** | Production'da çalışan pipeline'ı kırma |
| **Modüler ilerle** | İzole, test edilebilir değişiklikler yap |
| **Her müdahaleyi gerekçelendir** | Dosya, satır aralığı, sorun, neden, öncesi/sonrası mantığı yaz |
| **Token sınırını gözet** | Gereksiz tekrar analiz yapma, bu belge zaten bağlamı taşıyor |
| **Source parity** | MongoDB'de yapılan her fix'in MSSQL ve ES eşdeğerini kontrol et |
| **Backward compatibility** | save/load, API response formatları, config şemaları değişmesin |

---

## 3. PROJE MİMARİSİ — TEKNİK YAPI

### Genel Mimari (3 Katman)

```
Kullanıcı → Web UI (FastAPI) → Agent Layer (LangChain) → ML/Storage/Connectors
                                                              ↓
                                           OpenSearch ← MongoDB / MSSQL / ES logları
```

### Dizin Yapısı

```
MongoDB-LLM-assistant/
├── config/                     # 5 JSON config (anomaly, cluster, es, mssql, monitoring)
├── src/
│   ├── agents/                 # LLM agent: query translator, validator, schema analyzer
│   ├── anomaly/                # ML pipeline: detector, feature engineer, log reader (×3 kaynak)
│   │   ├── anomaly_detector.py       # 3188 satır — Core ML (Isolation Forest)
│   │   ├── anomaly_tools.py          # 5161 satır — Orchestrator + LangChain tools
│   │   ├── feature_engineer.py       #  823 satır — MongoDB feature engineering (40+ feature)
│   │   ├── mssql_anomaly_detector.py #  711 satır — MSSQL detector (extends base)
│   │   ├── mssql_feature_engineer.py #  807 satır — MSSQL features
│   │   ├── mssql_log_reader.py       # 1150 satır — MSSQL WMI log reader
│   │   ├── elasticsearch_anomaly_detector.py # 697 — ES detector (extends base)
│   │   ├── elasticsearch_feature_engineer.py # 774 — ES features
│   │   ├── elasticsearch_log_reader.py       # 1044 — ES OpenSearch reader
│   │   ├── log_reader.py             # 1814 satır — MongoDB log reader (JSON/text/OpenSearch)
│   │   ├── forecaster.py             # 1143 satır — Tiered forecaster (EWMA, regression, WMA)
│   │   ├── rate_alert.py             #  676 satır — Rate-based alerting
│   │   ├── trend_analyzer.py         #  623 satır — Trend detection
│   │   ├── scheduler.py              #  226 satır — Auto scheduling
│   │   └── retrain_all_models.py     #  744 satır — Batch retrain
│   ├── connectors/             # MongoDB, LCWGPT, OpenAI bağlantı adapterleri
│   ├── monitoring/             # SSH üzerinden Linux monitoring
│   ├── performance/            # Query performance (slow queries, explain)
│   └── storage/                # Storage manager, MongoDB handler, fallback
│       ├── storage_manager.py  # 1234 satır — Hybrid storage orchestrator
│       ├── mongodb_handler.py  # 1026 satır — Async MongoDB client
│       └── fallback_storage.py #  188 satır — File-only fallback
├── web_ui/
│   ├── api.py                  # 5755 satır — FastAPI REST API
│   └── static/                 # SPA: index.html + 11 JS modülü + CSS
├── tests/                      # 50+ test dosyası
├── main.py                     # CLI entry point
├── docker-compose.yml          # Container orchestration
└── requirements.txt            # fastapi, langchain, scikit-learn, pymongo, motor, pandas, paramiko
```

---

## 4. MODÜL ANALİZLERİ — DETAYLI

### 4.1 `anomaly_detector.py` — Core ML Engine (3188 satır)

**Class:** `MongoDBAnomalyDetector`

| Özellik | Detay |
|---------|-------|
| **Model** | scikit-learn `IsolationForest` (contamination=0.15, n_estimators=200) |
| **Singleton** | `get_instance(server_name)` — per-server model cache |
| **Thread Safety** | `_instance_lock` (per-subclass), `_training_lock`, `_model_io_lock` |
| **Scaler** | `StandardScaler` + `model_scalers` deque (per-batch snapshot) |
| **Ensemble** | `train_incremental()` — mini batch Isolation Forest ensemble |
| **Feature Alignment** | predict() içinde otomatik feature reorder/add/drop |
| **Critical Rules** | `_apply_critical_rules()` — ML'i override eden rule engine (OOM, FATAL, shutdown vb.) |
| **Evaluation** | `evaluate_model()` — precision/recall/F1 (pseudo-labels via `create_validation_dataset()`) |
| **Drift Detection** | `detect_model_drift()` — Wasserstein distance + KS test |
| **Persistence** | `save_model()` / `load_model()` — joblib + metadata dict |

**Inheritance:**
```
MongoDBAnomalyDetector
├── MSSQLAnomalyDetector (mssql_anomaly_detector.py)
│   └── Override: _instance_lock, _instances, severity_mapping, feature_names
└── ElasticsearchAnomalyDetector (elasticsearch_anomaly_detector.py)
    └── Override: _instance_lock, _instances, severity_mapping, config_path
```

**Key Methods:**
- `train(X, incremental=True)` → full/incremental training
- `train_incremental(X, batch_id)` → ensemble mini-batch
- `predict(X, df)` → predictions + anomaly_scores
- `predict_ensemble(X)` → weighted voting across ensemble
- `analyze_anomalies(X, df, predictions, scores)` → severity, category, rule hits
- `calculate_feature_importance(X)` → permutation-based importance
- `detect_dead_features(scores)` → near-zero variance features
- `generate_comprehensive_report()` → full evaluation + recommendations

### 4.2 `anomaly_tools.py` — Pipeline Orchestrator (5161 satır)

**Class:** `AnomalyDetectionTools`

Bu dosya 3 veri kaynağı için end-to-end pipeline'ı yönetiyor:

**MongoDB Pipeline:** `analyze_mongodb_logs()`
```
MongoDBLogReader → MongoDBFeatureEngineer → MongoDBAnomalyDetector
→ analyze_anomalies() → LCWGPT AI açıklama → StorageManager kayıt
→ Prediction Layer (trend + rate + forecast)
```

**MSSQL Pipeline:** `analyze_mssql_logs()`
```
MSSQLOpenSearchReader → MSSQLFeatureEngineer → MSSQLAnomalyDetector
→ analyze_anomalies() → LCWGPT AI açıklama → StorageManager kayıt
→ Prediction Layer
```

**Elasticsearch Pipeline:** `analyze_elasticsearch_logs()`
```
ElasticsearchOpenSearchReader → ElasticsearchFeatureEngineer → ElasticsearchAnomalyDetector
→ analyze_anomalies() → LCWGPT AI açıklama → StorageManager kayıt
→ Prediction Layer
```

**LangChain Tools (factory):** `create_anomaly_tools()` → 5 StructuredTool döner:
1. `analyze_mongodb_logs` — MongoDB analiz
2. `analyze_mssql_logs` — MSSQL analiz
3. `analyze_elasticsearch_logs` — ES analiz
4. `get_anomaly_summary` — Geçmiş analiz özeti
5. `train_anomaly_model` — Model eğitimi

**LLM Entegrasyonu:**
- `LLM_PROVIDER` env var → `lcwgpt` veya `openai`
- `LCWGPTConnector` → kurumsal API
- Prompt: Top-10 anomali → AI açıklama (Türkçe)
- Anomaly digest: token-efficient özet (chat sistemi için)

### 4.3 `forecaster.py` — Prediction Engine (1143 satır)

**Class:** `AnomalyForecaster`

**Tiered Model System:**
| Tier | Veri Gereksinimi | Yöntem |
|------|-----------------|--------|
| **Tier 0** | < 3 nokta | "Yeterli veri yok" |
| **Tier 1** | 3-9 nokta | Yön tahmini (artan/azalan) |
| **Tier 2** | 10-19 nokta | Weighted Moving Average |
| **Tier 3** | 20-49 nokta | Linear Regression + R² |
| **Tier 4** | 50+ nokta | EWMA decomposition + seasonality |

**5 Metric Extractor (Cross-Source):**
- `_extract_anomaly_rate()` — anomali oranı (%)
- `_extract_critical_ratio()` — CRITICAL+HIGH yüzdesi
- `_extract_error_rate()` — component-level anomali
- `_extract_slow_query_count()` — MongoDB slow queries
- `_extract_collscan_count()` — MongoDB collection scans

**Alerting:** `ForecastAlert` dataclass → severity (INFO/WARNING/CRITICAL), confidence, bounds, explainability

### 4.4 `api.py` — FastAPI Backend (5755 satır)

**Ana Endpoint'ler:**

| Endpoint | Method | İşlev |
|----------|--------|-------|
| `/api/analyze-cluster` | POST | MongoDB cluster analizi |
| `/api/analyze-mssql-logs` | POST | MSSQL analiz |
| `/api/analyze-elasticsearch-logs` | POST | ES analiz |
| `/api/chat` | POST | LCWGPT chat (anomali hakkında soru-cevap) |
| `/api/get-anomaly-chunk` | POST | 20'lik chunk ile LCWGPT'ye anomali gönder |
| `/api/prediction/alerts` | GET | Prediction alert'leri |
| `/api/prediction/summary` | GET | Alert istatistikleri |
| `/api/prediction/config` | GET | Prediction config durumu |
| `/api/anomaly/feedback` | POST | Kullanıcı feedback (TP/FP) |
| `/api/anomaly-history` | GET | Sayfalı analiz geçmişi |
| `/api/export-analysis/{id}` | POST | Analiz export |
| `/api/progress` | GET | Real-time ilerleme (streaming) |

**Singleton Management:**
- `get_storage_manager()` → async lock ile lazy init
- `get_llm_connector()` → LCWGPTConnector/OpenAI singleton
- `get_anomaly_detector()` → per-server detector

### 4.5 `storage_manager.py` + `mongodb_handler.py` — Persistence (2260 satır)

**StorageManager Pattern:**
```
API/Tools → StorageManager → MongoDB (metadata) + Filesystem (detail JSON, models)
```

**Key Capabilities:**
- Async/await — FastAPI uyumlu
- LRU cache — son analizler bellekte
- Auto-cleanup — disk %80'i aşarsa eski verileri sil
- Model versioning — backup + restore
- Hybrid search — MongoDB filtre + filesystem detail

**mongodb_handler.py:**
- `save_analysis()`, `get_analysis_history()`, `get_analysis_by_id()`
- `save_prediction_alert()`, `get_prediction_alerts()`, `get_prediction_summary()`
- `save_feedback()`, `get_feedback()`
- `save_model_metadata()`, `get_model_metadata()`

### 4.6 Feature Engineering (3 kaynak)

**MongoDB (`feature_engineer.py` — 823 satır):**
40+ feature: severity_score, component encoding, message_length, hour_of_day, operation_type, duration_ms, connection features, replication features, query pattern features, transaction indicators, seasonal decomposition

**MSSQL (`mssql_feature_engineer.py` — 807 satır):**
Error code encoding, severity level, login features (failed_login_ratio, time_since_last_login), IP/username frequency baseline, connection error patterns, permission error patterns

**Elasticsearch (`elasticsearch_feature_engineer.py` — 774 satır):**
Log level encoding, GC metrics, index operation features, cluster health features, node statistics, search latency features

### 4.7 Log Readers (3 kaynak)

Tümü OpenSearch'ten okuma yapıyor:
- **MongoDB:** `db-mongodb-*` index pattern
- **MSSQL:** `db-mssql-*` index pattern
- **Elasticsearch:** `db-elasticsearch-*` index pattern

OpenSearch bağlantısı: `opslog.lcwaikiki.com:443` (HTTPS, SSL verify=false)
Alternate hosts: `10.29.21.30:443`, `hqopnsrcmstr01-03.lcwaikiki.local:9200`

---

## 5. YAPILAN GELİŞTİRMELER — KRONOLOJİK

### Faz 1: MSSQL Pipeline Güçlendirme (Commit 49eb675 → f50f5fa)
- False positive azaltma: Known benign signature allowlist
- Drift detection: Wasserstein distance + KS test
- SLO: Alert budget + contamination tracking
- MSSQL: Rule engine fix, failed_login_ratio fix, time_since_last_login feature
- MSSQL: IP/username frekans baseline, regex daraltma, severity scoring fix
- MSSQL: Template method pattern ile mesaj çıkarma

### Faz 2: ML Panel & Feedback Sistemi (4cb0f18 → c472915)
- Sistem sıfırlama scripti (system_reset.py)
- UI: Sistem reset butonu + modal
- ML panel: Hardcoded metrikler → gerçek model verisine geçiş
- Kullanıcı feedback sistemi: True Positive / False Alarm buttons
- UI: Feedback butonları iyileştirme

### Faz 3: Elasticsearch Pipeline (1062487 → 3aa7c1d)
- Elasticsearch log anomaly detection pipeline sıfırdan oluşturuldu
- ES pipeline bug fix'leri (event_timestamp, CRITICAL severity scoring)
- OpenSearch `db-elasticsearch-*` hardening
- ES detector finalize

### Faz 4: UI Entegrasyonu & Source Parity (d1f9349 → 8250549)
- ES UI entegrasyonu (MongoDB/MSSQL ile aynı seviye)
- Storage layer bug fix (tüm kaynaklar)
- LCWGPT invoke path düzeltmesi
- AI prompt zenginleştirme (3 kaynak)
- Anomaly digest + conversation memory (token-efficient chat)
- NoneType crash önleme (tüm codebase)
- Data source card redesign, MSSQL ERRORLOG entegrasyonu
- Feature name validation — state mutation önleme
- LCWGPT response validation

### Faz 5: Prediction Layer (d198d81 → 5c24d3b)
- Prediction layer eklendi (trend, rate, forecast)
- Forecaster modülü: Tiered model (EWMA, regression, WMA)
- Concurrency fix (multi-tenant)
- MSSQL + ES pipeline'larına prediction entegrasyonu
- Cross-source prediction desteği güçlendirme
- Comprehensive prediction improvements (P1-P6):
  - P1: Forecaster `_extract_anomaly_rate` cross-source field map
  - P2: Config `prediction.forecasting.confidence_level` desteği
  - P3: Trend analyzer `_safe_get_stats` defensive accessor
  - P4: Rate alert `severity_distribution` fallback
  - P5: Storage manager `save_prediction_alert` auto-init
  - P6: API endpoints tüm prediction config alanlarını döndürüyor

### Faz 6: Production Readiness (979776b → c76b6f8)
- **F1:** Scaler corruption fix → per-batch `batch_scaler` + `model_scalers` deque
- **F2:** MSSQL `apply_filters()` skip fix
- **F3:** self.model = None sentinel → `_ensemble_mode` flag
- **F4:** Per-subclass `_instance_lock` (MSSQL, ES ayrı lock)
- **F5:** OpenSearch redundant load_model → doğrulandı (sorun yok)
- **F6:** `evaluate_model()` scaler.transform eklendi
- Dead code cleanup: `_calculate_sample_weights`, `export_results` silindi
- 22 bare `print()` → `logger.info()` / `logger.debug()` dönüşümü
- `create_validation_dataset()` return type annotation fix (2→3 element)

---

## 6. ÇÖZÜLEN VE ERTELENEN SORUNLAR

### Çözülen Buglar (Tamamı Kapandı)

| # | Bug | Çözüm | Commit |
|---|-----|-------|--------|
| BUG-1 | `partial_fit()` StandardScaler bozuyor | Per-batch scaler + `model_scalers` deque | F1 (979776b) |
| BUG-2 | MSSQL path `apply_filters()` atlıyor | `mssql_feature_engineer.apply_filters()` çağrısı eklendi | F2 (979776b) |
| BUG-3 | `self.model = None` sentinel race | `_ensemble_mode` flag ile çözüldü | F3 (979776b) |
| BUG-4 | `_instance_lock` shared across subclasses | Per-subclass lock tanımı | F4 (979776b) |
| BUG-5 | OpenSearch redundant `load_model()` | Doğrulandı — sorun yok | F5 (979776b) |
| BUG-6 | MongoDB feature_score uncapped | `min(feature_score, 40)` | F6 (979776b) |
| ISS-6 | `evaluate_model()` scaler kullanmıyor | `scaler.transform` eklendi | F6 (979776b) |

### Bilinçli DEFER (Risk Düşük)

| # | Konu | Neden DEFER |
|---|------|-------------|
| ISS-1 | Incremental learning full refit | IsolationForest `partial_fit` desteklemez; `train_incremental()` ensemble zaten çözüm |
| ISS-2 | `predict()` training lock scope geniş | Lock daraltma race condition riski taşır; mevcut throughput yeterli |
| ISS-3 | `_apply_critical_rules` O(n×r) | 11 rule × 500 anomaly = 5500 iteration, negligible |

### Dead Code Kararları

| Fonksiyon | Karar | Neden |
|-----------|-------|-------|
| `_calculate_sample_weights()` | **DELETE** ✅ | IsolationForest sample_weight desteklemiyor |
| `export_results()` | **DELETE** ✅ | Storage layer zaten persistence sağlıyor |
| `create_validation_dataset()` | **KEEP** ✅ | `evaluate_model()` aktif çağırıyor |
| `optimize_feature_selection()` | **DEFER** | İleride diagnostic dashboard'a entegre edilebilir |
| `get_prediction_summary()` | **KEEP** ✅ | `/api/prediction/summary` aktif kullanıyor |
| Debug print'ler | **FIX** ✅ | 22 `print()` → `logger` dönüştürüldü |

---

## 7. KULLANILAN TEKNOLOJİLER

| Katman | Teknoloji |
|--------|-----------|
| **ML** | scikit-learn (IsolationForest, StandardScaler), numpy, pandas, joblib |
| **Web** | FastAPI, uvicorn, Jinja2 |
| **LLM** | LangChain 0.3.14, LCWGPTConnector (kurumsal), OpenAI (fallback) |
| **Database** | MongoDB (pymongo, motor async), OpenSearch (log kaynağı) |
| **Frontend** | Vanilla JS (11 modül), Chart.js (ML visualization), CSS |
| **Monitoring** | Paramiko (SSH), Linux system monitoring |
| **Container** | Docker, docker-compose |
| **VCS** | Git, branch: `claude/enhance-opensearch-logging-HtRk7` |

---

## 8. LCWAİKİKİ ENTEGRASYON YAPISI

### LCWGPT (Kurumsal LLM)
- **Connector:** `LCWGPTConnector` (`src/connectors/lcwgpt_connector.py`)
- **API:** Kurumsal endpoint (env var: `LCWGPT_API_URL`)
- **Kullanım:** Anomali açıklama, chat, öneri üretimi
- **Prompt Dili:** Türkçe DBA perspektifi
- **Fallback:** OpenAI (env var: `LLM_PROVIDER`)

### OpenSearch
- **Host:** `opslog.lcwaikiki.com:443`
- **Index Patterns:** `db-mongodb-*`, `db-mssql-*`, `db-elasticsearch-*`
- **Auth:** Credentials (config JSON)
- **Scroll API:** 5m timeout, 10000 batch size

### Cluster Mapping
- `config/cluster_mapping.json` — 19 cluster tanımlı
- Environment: prod, test, dev, regional
- FQDN → hostname normalization (e.g., `ecaztrdbmng015.lcwecomtr.com` → `ecaztrdbmng015`)

---

## 9. PROMPT MÜHENDİSLİĞİ VE LLM DAVRANIŞ KONTROLÜ

### Anomali Açıklama Prompt'u
- Top-10 anomali → LCWGPT'ye gönderiliyor
- Prompt: server name, source type, anomaly count, severity breakdown, top anomalies with details
- Dil: Türkçe, DBA perspektifi
- Token limiti: Digest sistemi ile aşım önleniyor

### Chat Sistemi
- Anomaly digest: Token-efficient özet (en önemli 5-10 anomali)
- Conversation memory: Son 5 mesaj bağlamda tutuluyor
- Context: Son analiz sonuçları + digest + kullanıcı sorusu

### Response Validation
- LCWGPT response format kontrolü (3 kaynak için)
- Fallback explanation: LLM boş/hatalı döndürürse statik açıklama

---

## 10. TEST EDİLMEYEN / EKSİK KONULAR

| Konu | Durum |
|------|-------|
| **Prediction UI** | Backend hazır, UI entegrasyonu yapılmadı |
| **Forecasting chart** | `forecaster.py` veri üretiyor ama frontend chart yok |
| **Rate alert dashboard** | API endpoint var, UI widget yok |
| **Multi-tenant load test** | Concurrent 10+ analiz yük testi yapılmadı |
| **ES/MSSQL prediction e2e** | Prediction layer entegre ama cross-source e2e test eksik |
| **optimize_feature_selection UI** | Fonksiyon yazıldı ama hiçbir yerden çağrılmıyor |
| **Model retrain scheduler** | Scheduler modülü var, cron entegrasyonu yapılmadı |

---

## 11. GÜNCEL DURUM VE SON AŞAMA

### Tamamlanan Modüller (Production-Ready)

| Modül | Durum |
|-------|-------|
| MongoDB anomaly pipeline | ✅ Production |
| MSSQL anomaly pipeline | ✅ Production |
| Elasticsearch anomaly pipeline | ✅ Production |
| Feature engineering (3 kaynak) | ✅ Production |
| ML model (train/predict/ensemble) | ✅ Production (F1-F6 fix'li) |
| Storage layer (hybrid) | ✅ Production |
| LCWGPT entegrasyonu | ✅ Production |
| Prediction layer (backend) | ✅ Production |
| Forecaster (tiered) | ✅ Production |
| User feedback sistemi | ✅ Production |
| Anomaly digest / chat | ✅ Production |

### Şu An Sistemin Durumu
- **Backend/ML:** Tüm kritik buglar çözüldü, dead code temizlendi, production-ready
- **API:** Tüm endpoint'ler fonksiyonel, prediction dahil
- **Frontend:** Anomaly analiz, ML panel, feedback çalışıyor
- **Eksik:** Prediction/forecasting UI widget'ları

---

## 12. KALDIĞIMIZ YER VE SONRAKİ ADIMLAR

### Mevcut Aşama
**Backend/ML production-readiness audit TAMAMLANDI.** Prediction/forecasting UI entegrasyon fazına geçiş hazır.

### Sıradaki Adımlar (Öncelik Sırasıyla)

1. **Prediction UI Entegrasyonu**
   - Trend alert widget'ı (artan/azalan anomaly rate)
   - Rate alert dashboard (anlık threshold ihlalleri)
   - Forecast chart (gelecek projeksiyonu, confidence bands)
   - API endpoint'leri zaten var: `/api/prediction/alerts`, `/api/prediction/summary`, `/api/prediction/config`

2. **Forecasting Visualization**
   - Chart.js time series chart
   - Tier bilgisi gösterimi
   - Alert severity renklendirme

3. **İsteğe Bağlı İyileştirmeler**
   - `optimize_feature_selection()` → admin/diagnostic endpoint'e bağlama
   - Model retrain scheduler → cron entegrasyonu
   - Multi-tenant load testing
   - ES/MSSQL prediction e2e test

### Branch Bilgisi
- **Branch:** `claude/enhance-opensearch-logging-HtRk7`
- **Son Commit:** `c76b6f8` — "fix: dead code cleanup, debug prints → logger, annotation fix"
- **Push Durumu:** Güncel, origin ile sync

---

## 13. CONFIG ŞEMASI ÖZETİ

### `config/anomaly_config.json` (Ana Config)
```json
{
  "model_version": "2.1",
  "server_management": { "model_strategy": "per_server" },
  "environments": {
    "test": {
      "data_sources": { "opensearch": { "index_pattern": "db-mongodb-*" } }
    }
  },
  "model": {
    "algorithm": "isolation_forest",
    "contamination": 0.15,
    "n_estimators": 200
  },
  "online_learning": { "enabled": true, "ensemble": { "max_models": 5 } },
  "prediction": {
    "enabled": true,
    "trend_detection": { "enabled": true },
    "rate_alerting": { "enabled": true },
    "forecasting": { "enabled": true, "confidence_level": 0.95 }
  },
  "false_positive_reduction": { "known_benign_signatures": [...] }
}
```

---

> **Bu belge, yeni bir Claude oturumunda ilk mesaj olarak gönderildiğinde, projenin tüm bağlamını sıfırdan yükleyecek şekilde hazırlanmıştır. Gereksiz tekrar analiz yerine bu belgeyi referans alarak devam edin.**
