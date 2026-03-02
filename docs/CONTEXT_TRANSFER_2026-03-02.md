# MongoDB Log Anomaly Detection — Proje Bagam Aktarimi
> **Tarih:** 2026-03-02
> **Branch:** `claude/verify-prediction-system-JkhT9`
> **Toplam Commit:** 63 | **Son Commit:** `e02f5df`

---

## 1. PROJENIN AMACI VE HEDEFLERI

### Neden Baslatildi?
LCWaikiki'nin veritabani ekibi (DBA Team), MongoDB / MSSQL / Elasticsearch sunucularindan gelen log verilerini **manuel olarak** izliyor. Yuzlerce sunucu, binlerce satir log, yuksek MTTR (mean time to resolve). Gercek sorunlar gurultude kayboluyordu.

### Hangi Problemi Cozuyoruz?
1. **Anomali Tespiti:** ML (Isolation Forest) ile loglardan otomatik anomali tespiti
2. **Dogal Dil Etkilesimi:** DBA'larin "son 1 saatte neler oldu?" gibi sorularla sisteme ulasmasi (LLM + LangChain)
3. **Cok Kaynakli (Multi-Source) Destek:** MongoDB, MSSQL, Elasticsearch — tumu OpenSearch uzerinden
4. **Prediction Layer:** Trend analizi, rate alerting, forecasting ile anomali tahmini
5. **LCWaikiki Entegrasyonu:** Kurumsal LCW GPT (LLM) uzerinden AI aciklamalar

### Nihai Hedef
- Production-grade, self-service DBA monitoring araci
- 3 veri kaynagi (MongoDB / MSSQL / Elasticsearch) icin tam parite
- Prediction/forecasting UI entegrasyonu (TAMAMLANDI)
- ML Signal Integration (TAMAMLANDI)
- Otomatik retrain, drift detection, feedback loop

---

## 2. GENEL KURALLAR VE ETKILESIM PRENSIPLERI

| Kural | Aciklama |
|-------|----------|
| **Varsayim yapma** | Repo'daki guncel kodu yeniden okumadan karar verme |
| **Mevcut yapiyi bozma** | Production'da calisan pipeline'i kirma |
| **Moduler ilerle** | Izole, test edilebilir degisiklikler yap |
| **Her mudahaleyi gerekcelendir** | Dosya, satir araligi, sorun, neden, oncesi/sonrasi mantigi yaz |
| **Token sinirini gozet** | Gereksiz tekrar analiz yapma, bu belge zaten baglami tasiyor |
| **Source parity** | MongoDB'de yapilan her fix'in MSSQL ve ES esdegerini kontrol et |
| **Backward compatibility** | save/load, API response formatlari, config semalari degismesin |

---

## 3. PROJE MIMARISI — TEKNIK YAPI

### Genel Mimari (3 Katman)

```
Kullanici -> Web UI (FastAPI) -> Agent Layer (LangChain) -> ML/Storage/Connectors
                                                              |
                                           OpenSearch <- MongoDB / MSSQL / ES loglari
```

### Dizin Yapisi

```
MongoDB-LLM-assistant/
|-- config/                     # 5 JSON config (anomaly, cluster, es, mssql, monitoring)
|-- src/
|   |-- agents/                 # LLM agent: query translator, validator, schema analyzer
|   |-- anomaly/                # ML pipeline: detector, feature engineer, log reader (x3 kaynak)
|   |   |-- anomaly_detector.py       # 3188 satir -- Core ML (Isolation Forest)
|   |   |-- anomaly_tools.py          # 5275 satir -- Orchestrator + LangChain tools
|   |   |-- feature_engineer.py       #  823 satir -- MongoDB feature engineering (40+ feature)
|   |   |-- mssql_anomaly_detector.py #  711 satir -- MSSQL detector (extends base)
|   |   |-- mssql_feature_engineer.py #  807 satir -- MSSQL features
|   |   |-- mssql_log_reader.py       # 1150 satir -- MSSQL WMI log reader
|   |   |-- elasticsearch_anomaly_detector.py # 697 -- ES detector (extends base)
|   |   |-- elasticsearch_feature_engineer.py # 774 -- ES features
|   |   |-- elasticsearch_log_reader.py       # 1044 -- ES OpenSearch reader
|   |   |-- log_reader.py             # 1814 satir -- MongoDB log reader (JSON/text/OpenSearch)
|   |   |-- forecaster.py             # 1339 satir -- Tiered forecaster (EWMA, regression, WMA)
|   |   |-- rate_alert.py             #  741 satir -- Rate-based alerting + ML context overlay
|   |   |-- trend_analyzer.py         #  762 satir -- Trend detection + ML score trend
|   |   |-- scheduler.py              #  226 satir -- Auto scheduling
|   |   +-- retrain_all_models.py     #  744 satir -- Batch retrain
|   |-- connectors/             # MongoDB, LCWGPT, OpenAI baglanti adapterleri
|   |-- monitoring/             # SSH uzerinden Linux monitoring
|   |-- performance/            # Query performance (slow queries, explain)
|   +-- storage/                # Storage manager, MongoDB handler, fallback
|       |-- storage_manager.py  # 1240 satir -- Hybrid storage orchestrator
|       |-- mongodb_handler.py  # 1139 satir -- Async MongoDB client
|       +-- fallback_storage.py #  188 satir -- File-only fallback
|-- web_ui/
|   |-- api.py                  # 5792 satir -- FastAPI REST API (60+ endpoint)
|   +-- static/                 # SPA: index.html + 11 JS modulu + CSS
|       |-- script-core.js      # 1170 satir -- Global config, API endpoints
|       |-- script.js           # 3676 satir -- Main event handling
|       |-- script-anomaly.js   # 4330 satir -- Anomaly analysis UI
|       |-- script-prediction.js# 1020 satir -- Prediction Studio (full-screen modal)
|       |-- script-ml-panel.js  #  680 satir -- ML metrics sidebar
|       |-- script-ml-visualization.js # 1138 -- Chart.js visualizations
|       |-- script-ui.js        # 1345 satir -- UI component helpers
|       |-- script-history.js   # 2557 satir -- Analysis history
|       |-- script-log-filter.js# 1489 satir -- Log filtering
|       |-- script-performance.js # 463 satir -- Performance tools
|       |-- script-dba-explorer.js # 432 satir -- DBA tools
|       |-- style.css           # 17223 satir -- Tum styling (ML badge'lar dahil)
|       +-- index.html          # 1111 satir -- Main SPA template
|-- tests/                      # 63 test dosyasi
|-- main.py                     # CLI entry point
|-- docker-compose.yml          # Container orchestration
+-- requirements.txt            # fastapi, langchain, scikit-learn, pymongo, motor, pandas, paramiko
```

---

## 4. MODUL ANALIZLERI — DETAYLI

### 4.1 `anomaly_detector.py` — Core ML Engine (3188 satir)

**Class:** `MongoDBAnomalyDetector`

| Ozellik | Detay |
|---------|-------|
| **Model** | scikit-learn `IsolationForest` (contamination=0.03, n_estimators=300) |
| **Singleton** | `get_instance(server_name)` — per-server model cache |
| **Thread Safety** | `_instance_lock` (per-subclass), `_training_lock`, `_model_io_lock` |
| **Scaler** | `StandardScaler` + `model_scalers` deque (per-batch snapshot) |
| **Ensemble** | `train_incremental()` — mini batch Isolation Forest ensemble (max 10 model) |
| **Feature Alignment** | predict() icinde otomatik feature reorder/add/drop |
| **Critical Rules** | `_apply_critical_rules()` — ML'i override eden 14 kuralik rule engine |
| **Evaluation** | `evaluate_model()` — precision/recall/F1 (pseudo-labels) |
| **Drift Detection** | `detect_model_drift()` — Wasserstein distance + KS test |
| **Persistence** | `save_model()` / `load_model()` — joblib + metadata dict |

**Critical Rules Engine (14 kural):**
| Kural | Kosul | Severity |
|-------|-------|----------|
| system_failure | fatal, OOM, shutdown | 1.0 |
| massive_scan | docs_examined > 1M | 1.0 |
| performance_critical | COLLSCAN + docs > 100k | 0.85 |
| long_transaction | TXN > 3s | 0.90 |
| replication_risk | replication issue | 0.90 |
| memory_pressure | OOM, memory_limit | 0.88 |
| error_burst | error + extreme_burst | 0.90 |
| security_alert | DROP, assertion | 0.88 |

**Inheritance:**
```
MongoDBAnomalyDetector
|-- MSSQLAnomalyDetector (mssql_anomaly_detector.py)
|   +-- Override: _instance_lock, _instances, severity_mapping, feature_names
+-- ElasticsearchAnomalyDetector (elasticsearch_anomaly_detector.py)
    +-- Override: _instance_lock, _instances, severity_mapping, config_path
```

**Key Methods:**
- `train(X, incremental=True)` -> full/incremental training
- `train_incremental(X, batch_id)` -> ensemble mini-batch (deque, max 10)
- `predict(X, df)` -> predictions + anomaly_scores, sonra critical_rules override
- `predict_ensemble(X)` -> weighted voting across ensemble
- `analyze_anomalies(X, df, predictions, scores)` -> severity, category, component, rule hits
- `calculate_feature_importance(X)` -> permutation-based importance
- `detect_model_drift(X_new)` -> KL divergence, feature-level drift

### 4.2 `anomaly_tools.py` — Pipeline Orchestrator (5275 satir)

**Class:** `AnomalyDetectionTools`

Bu dosya 3 veri kaynagi icin end-to-end pipeline'i yonetiyor:

**MongoDB Pipeline:** `analyze_mongodb_logs()`
```
MongoDBLogReader -> MongoDBFeatureEngineer -> MongoDBAnomalyDetector
-> analyze_anomalies() -> LCWGPT AI aciklama -> StorageManager kayit
-> Prediction Layer (trend + rate + forecast) -> _build_prediction_insight()
```

**MSSQL Pipeline:** `analyze_mssql_logs()`
```
MSSQLOpenSearchReader -> MSSQLFeatureEngineer -> MSSQLAnomalyDetector
-> analyze_anomalies() -> LCWGPT AI aciklama -> Prediction Layer
```

**Elasticsearch Pipeline:** `analyze_elasticsearch_logs()`
```
ElasticsearchOpenSearchReader -> ElasticsearchFeatureEngineer -> ElasticsearchAnomalyDetector
-> analyze_anomalies() -> LCWGPT AI aciklama -> Prediction Layer
```

**LangChain Tools (factory):** `create_anomaly_tools()` -> 5 StructuredTool doner:
1. `analyze_mongodb_logs` — MongoDB analiz
2. `analyze_mssql_logs` — MSSQL analiz
3. `analyze_elasticsearch_logs` — ES analiz
4. `get_anomaly_summary` — Gecmis analiz ozeti
5. `train_anomaly_model` — Model egitimi

**Prediction Entegrasyonu (anomaly_tools.py icinde):**
- `_run_prediction_checks(analysis, df, server_name, source_type)` -> async cagiri
- `_build_prediction_insight(prediction_results)` -> UI icin JSON olusturur
- `_build_prediction_context_for_prompt(prediction_results)` -> LLM prompt'a ek context

**Insight Builder `_build_prediction_insight()` detay (satirlar ~4100-4280):**
```python
# Trend section: direction, baseline/current rate, ML score trend enrichment
# Rate section: alert count, types, ML corroboration count (X/Y ML destekli)
# Forecast section: rising metrics, forecast alerts, insufficient data guidance
# Risk level: CRITICAL > WARNING > INFO > OK (prediction_alerts iceriginden)
```

### 4.3 `forecaster.py` — Prediction Engine (1339 satir)

**Class:** `AnomalyForecaster`

**Tiered Model System:**
| Tier | Veri Gereksinimi | Yontem | Confidence |
|------|-----------------|--------|-----------|
| **Tier 0** | < 5 nokta | Yon gostergesi | 0.1 |
| **Tier 1** | 5-9 nokta | Weighted Moving Average | 0.2-0.35 |
| **Tier 2** | 10-19 nokta | Linear Regression + R^2 | 0.2-0.7 |
| **Tier 3** | 20+ nokta | EWMA decomposition + seasonality + CUSUM | 0.4-0.9 |

**Metric Extractors (Cross-Source):**
Ortak: anomaly_rate, anomaly_count, critical_ratio, critical_count, error_count, mean_anomaly_score
MongoDB: slow_query_count, collscan_count, auth_failure_count
MSSQL: high_severity_count, connection_error_count, auth_failure_count
ES: oom_count, circuit_breaker_count, shard_failure_count, gc_overhead_count, disk_watermark_count, master_election_count

**ML Risk Context Overlay (`_compute_ml_risk_context`):**
- current_mean_score, baseline_mean_score, score_worsening boolean
- anomaly_rate, critical_count, ml_risk_level (OK/INFO/WARNING/CRITICAL)
- Forecast alert severity boost: WARNING -> CRITICAL eger ML risk yuksekse

**Alert Evaluation (`_evaluate_alert`):**
- baseline = past average, forecast vs baseline yuzde karsilastirma
- warning_pct (tipik %50) ve critical_pct (tipik %100) esikleri
- Volatility dampening: CV > 0.6 ise CRITICAL -> WARNING dusurme
- ML boost: ml_risk_ctx.score_worsening + ml_risk in (WARNING, CRITICAL) -> severity yukseltme

### 4.4 `trend_analyzer.py` — Trend Detection (762 satir)

**Class:** `TrendAnalyzer`

**6 Kontrol Turu:**
1. `_check_anomaly_rate_trend()` — Anomali orani artisi (baseline vs current)
2. `_check_component_concentration()` — Tek component'te yogunlasma
3. `_check_severity_escalation()` — CRITICAL+HIGH orani artisi
4. `_check_temporal_shift()` — Peak saat kaymalari
5. `_check_source_specific_trends()` — Kaynak-spesifik metrikler (slow_query, collscan, failed_login vb.)
6. `_check_ml_score_trend()` — IsolationForest ortalama skor trendi (PATCH 1)

**ML Score Trend Detay (PATCH 1 — e129113):**
- Gecmis mean score'larin abs() degeri alinir (daha negatif = daha anomalous)
- Baseline: gecmis ortalama. Esik: %30 artis = WARNING, %60 = CRITICAL
- Monoton kotuleme: Son 4 analizde skorlar kesintisiz artiyorsa ek alert

**Summary icinde ML skor bilgisi:**
- `ml_score_trend` dict: `ml_score_direction` ("worsening"/"improving"/"stable"), `current_mean_score`, `baseline_mean_score`

### 4.5 `rate_alert.py` — Rate-Based Alerting (741 satir)

**Class:** `RateAlertEngine`

**3 Pencere:**
| Pencere | Sure | Ornek Esikler (MongoDB) |
|---------|------|------------------------|
| short | 15dk | auth_failure=50, error=100, slow_query=30 |
| medium | 1 saat | auth_failure=150, error=300, slow_query=80 |
| long | 6 saat | auth_failure=500, error=1000, slow_query=200 |

**Source-Specific Detectors:**
- MongoDB: auth_failure, error_burst, slow_query, collscan, drop_operation, oom
- MSSQL: failed_login, connection_error, permission_error, high_severity, ag_error, fdhost_crash
- ES: circuit_breaker, shard_failure, gc_overhead, disk_watermark, master_election

**ML Context Overlay (PATCH 2 — 08d28a2):**
- Per-window ML anomaly density: `window_start <= ml_ts <= ts_max` (e02f5df ile duzeltildi)
- Density > 5% -> `ml_corroborated = true`, badge "ML check"
- Density <= 5% -> `ml_corroborated = false`, badge "ML ?"
- `ml_context` dict: window_anomaly_count, window_anomaly_density_pct, global_anomaly_rate, global_mean_score, ml_corroborated

### 4.6 Feature Engineering (3 kaynak)

**MongoDB (`feature_engineer.py` — 823 satir):**
50+ feature: severity_score, component_encoded, is_rare_component, message_length, hour_of_day, operation_type, query_duration_ms, docs_examined_count, keys_examined_count, is_collscan, is_slow_query, is_auth_failure, is_drop_operation, is_fatal, is_replication_issue, is_out_of_memory, burst_density, performance_score, txn_time_active_micros, txn_wait_ratio, WiredTiger features, component_criticality_score

**MSSQL (`mssql_feature_engineer.py` — 807 satir):**
Error code encoding, severity level (1-25), login features (failed_login_ratio, time_since_last_login), IP/username frequency baseline, connection error patterns, permission error patterns

**Elasticsearch (`elasticsearch_feature_engineer.py` — 774 satir):**
Log level encoding, GC metrics, index operation features, cluster health features, node statistics, search latency features, is_oom_error, is_circuit_breaker, is_shard_failure

### 4.7 Log Readers (3 kaynak)

Tumu OpenSearch'ten okuma yapiyor:
- **MongoDB:** `db-mongodb-*` index pattern
- **MSSQL:** `db-mssql-*` index pattern
- **Elasticsearch:** `db-elasticsearch-*` index pattern

OpenSearch baglantisi: `opslog.lcwaikiki.com:443` (HTTPS, SSL verify=false)
Alternate hosts: `10.29.21.30:443`, `hqopnsrcmstr01-03.lcwaikiki.local:9200`

### 4.8 `storage_manager.py` + `mongodb_handler.py` — Persistence (2379 satir)

**StorageManager Pattern:**
```
API/Tools -> StorageManager -> MongoDB (metadata) + Filesystem (detail JSON, models)
```

**Key Capabilities:**
- Async/await — FastAPI uyumlu (Motor client)
- LRU cache — son analizler bellekte
- Auto-cleanup — disk %80'i asarsa eski verileri sil
- Model versioning — backup + restore
- Hybrid search — MongoDB filtre + filesystem detail

**mongodb_handler.py Collections:**
- `anomaly_analysis_history` — Ana analiz kayitlari
- `prediction_alerts` — Trend/rate/forecast alert'leri
- `anomaly_feedback` — True Positive / False Positive labellari
- `model_metadata` — ML model bilgileri

### 4.9 `api.py` — FastAPI Backend (5792 satir)

**Ana Endpoint'ler:**

| Endpoint | Method | Islev |
|----------|--------|-------|
| `/api/analyze-cluster` | POST | MongoDB cluster analizi |
| `/api/analyze-mssql-logs` | POST | MSSQL analiz |
| `/api/analyze-elasticsearch-logs` | POST | ES analiz |
| `/api/chat` | POST | LCWGPT chat (anomali hakkinda soru-cevap) |
| `/api/get-anomaly-chunk` | POST | 20'lik chunk ile LCWGPT'ye anomali gonder |
| `/api/prediction/alerts` | GET | Prediction alert'leri (server, source_type, days filtresi) |
| `/api/prediction/summary` | GET | Alert istatistikleri |
| `/api/prediction/timeseries` | GET | Time-series chart verisi |
| `/api/prediction/config` | GET | Prediction config durumu |
| `/api/scheduler/status\|start\|stop\|trigger` | GET/POST | Scheduler yonetimi |
| `/api/anomaly/feedback` | POST | Kullanici feedback (TP/FP) |
| `/api/anomaly-history` | GET | Sayfall analiz gecmisi |
| `/api/export-analysis/{id}` | POST | Analiz export |
| `/api/progress` | GET | Real-time ilerleme (streaming) |
| `/api/ml/metrics` | GET | ML model performance metrikleri |
| `/api/system-reset` | POST | Tam sistem sifirlama |

**Singleton Management:**
- `get_storage_manager()` -> async lock ile lazy init
- `get_llm_connector()` -> LCWGPTConnector/OpenAI singleton
- `get_anomaly_detector()` -> per-server detector

---

## 5. YAPILAN GELISTIRMELER — KRONOLOJIK

### Faz 1: MSSQL Pipeline Guclendirme (Commit 49eb675 -> f50f5fa)
- False positive azaltma: Known benign signature allowlist
- Drift detection: Wasserstein distance + KS test
- SLO: Alert budget + contamination tracking
- MSSQL: Rule engine fix, failed_login_ratio fix, time_since_last_login feature
- MSSQL: IP/username frekans baseline, regex daraltma, severity scoring fix

### Faz 2: ML Panel & Feedback Sistemi (4cb0f18 -> c472915)
- Sistem sifirlama scripti (system_reset.py)
- UI: Sistem reset butonu + modal
- ML panel: Hardcoded metrikler -> gercek model verisine gecis
- Kullanici feedback sistemi: True Positive / False Alarm buttons

### Faz 3: Elasticsearch Pipeline (1062487 -> 3aa7c1d)
- Elasticsearch log anomaly detection pipeline sifirdan olusturuldu
- ES pipeline bug fix'leri (event_timestamp, CRITICAL severity scoring)
- OpenSearch `db-elasticsearch-*` hardening
- ES detector finalize

### Faz 4: UI Entegrasyonu & Source Parity (d1f9349 -> 8250549)
- ES UI entegrasyonu (MongoDB/MSSQL ile ayni seviye)
- Storage layer bug fix (tum kaynaklar)
- LCWGPT invoke path duzeltmesi
- AI prompt zenginlestirme (3 kaynak)
- Anomaly digest + conversation memory (token-efficient chat)
- NoneType crash onleme (tum codebase)
- Feature name validation — state mutation onleme

### Faz 5: Prediction Layer (d198d81 -> 5c24d3b)
- Prediction layer eklendi (trend, rate, forecast)
- Forecaster modulu: Tiered model (EWMA, regression, WMA)
- Concurrency fix (multi-tenant)
- MSSQL + ES pipeline'larina prediction entegrasyonu
- Cross-source prediction destegi guclendirme
- Comprehensive prediction improvements (P1-P6):
  - P1: Forecaster `_extract_anomaly_rate` cross-source field map
  - P2: Config `prediction.forecasting.confidence_level` destegi
  - P3: Trend analyzer `_safe_get_stats` defensive accessor
  - P4: Rate alert `severity_distribution` fallback
  - P5: Storage manager `save_prediction_alert` auto-init
  - P6: API endpoints tum prediction config alanlarini donduruyor

### Faz 6: Production Readiness (979776b -> c76b6f8)
- **F1:** Scaler corruption fix -> per-batch `batch_scaler` + `model_scalers` deque
- **F2:** MSSQL `apply_filters()` skip fix
- **F3:** self.model = None sentinel -> `_ensemble_mode` flag
- **F4:** Per-subclass `_instance_lock` (MSSQL, ES ayri lock)
- **F5:** OpenSearch redundant load_model -> dogrulandi (sorun yok)
- **F6:** `evaluate_model()` scaler.transform eklendi
- Dead code cleanup: `_calculate_sample_weights`, `export_results` silindi
- 22 bare `print()` -> `logger.info()` / `logger.debug()` donusumu

### Faz 7: Prediction UI Entegrasyonu (d50ecf4 -> 2ad4bb3)
- **Asama 1 (7ffb79c):** Prediction insight panel — anomaly results icinde kisa ozet paneli
- **Asama 2 (42edf5a):** Collapsible detail section — trend/rate/forecast tablari
- **Asama 3 (cf9d3cd):** Standalone prediction dashboard — API entegrasyonu
- **b8cf155:** Scheduler management panel dashboard'a eklendi
- **b7dd1ba:** Full-screen modal overlay'e donusturuldu
- **76d55a4:** Modal buyutme, okunabilirlik artirma
- **20d73c3-c111a82:** P1-1 ~ P1-4: Sidebar + two-column layout, source toggle, target hosts checkboxes, inline insight link
- **82b0ac6:** Empty state messages (yetersiz veri durumlari icin)
- **62c1c8b:** Tier roadmap — insufficient data guidance ("X analiz daha -> Tier Y")
- **9c361ae:** Chart.js time-series chart (trend visualization)
- **b052b51:** Alert table data path fix
- **c8c362f:** Source type filtering (MongoDB/MSSQL/ES)
- **d817f0f:** ML-derived risk signal to prediction insight
- **70c429d-2ad4bb3:** Trigger button fix, prominent header button

### Faz 8: ML Signal Integration (e129113 -> e02f5df) — EN SON

Bu faz IsolationForest ML skorlarini 3 prediction katmanina entegre etti:

**PATCH 1 — Trend Analyzer ML Score Trend (e129113):**
- `trend_analyzer.py` satirlar 585-683: `_check_ml_score_trend()` eklendi
- Gecmis analizlerin mean anomaly score'unu izler
- abs(mean) degeri artan trend -> "ml_score_degradation" alert
- Son 4 analizde monoton artis -> "ml_score_monotonic_degradation" alert
- `_build_summary()` satirlar 719-742: `ml_score_trend` dict eklendi
  - Alanlar: `ml_score_direction`, `current_mean_score`, `baseline_mean_score`

**PATCH 2 — Rate Alert ML Context Overlay (08d28a2):**
- `rate_alert.py` satirlar 588-635: ML anomaly timestamp parsing ve per-window density hesabi
- Satirlar 662-706: Rate alert'lere `ml_context` dict eklendi
  - Alanlar: `window_anomaly_count`, `window_anomaly_density_pct`, `global_anomaly_rate`, `global_mean_score`, `ml_corroborated`
- `ml_corroborated = True` -> density > 5%, spike ML-destekli
- `ml_corroborated = False` -> density <= 5%, spike ML destegi zayif

**PATCH 3 — Forecaster ML Score Metric + Risk Context (4af8d8d):**
- `forecaster.py` satirlar 339-354: `_extract_mean_anomaly_score()` extractor eklendi
- `forecaster.py` satirlar 1194-1251: `_compute_ml_risk_context()` static method eklendi
  - Alanlar: `current_mean_score`, `baseline_mean_score`, `score_worsening`, `anomaly_rate`, `critical_count`, `ml_risk_level`
- Satirlar 937-946: `_evaluate_alert()` icinde ML severity boost
  - WARNING -> CRITICAL eger ml_risk_ctx.score_worsening + ml_risk in (WARNING, CRITICAL)
- Satirlar 1156-1158: Her forecast metric'ine `ml_risk_context` dict eklendi (mean_anomaly_score haric, kendi referans dongusu icin)

**PATCH 4 — UI ML Signal Rendering (79dae05):**
- `script-prediction.js` satirlar 374-399: `_buildDetailSnippet()` — ML corroboration badge'lari
  - `ppd-ml-badge ppd-ml-confirmed` -> "ML check" (yesil)
  - `ppd-ml-badge ppd-ml-weak` -> "ML ?" (sari)
- `script-anomaly.js` satirlar 4200-4223: Forecast tablosunda ML risk context satiri
  - `pd-ml-risk-row pd-ml-risk-critical/warning/info` class'lari
  - Robot emoji + ML Risk seviyesi + anomali orani + skor bilgisi
- `style.css` satirlar 16123-16172: ML badge ve risk row CSS class'lari

**PATCH 5 — Orchestrator Insight Builder Enrichment (3f59560):**
- `anomaly_tools.py` satirlar 4166-4176: Trend summary'ye ML score trend eklendi
  - "ML skor trendi: worsening (baseline: X -> guncel: Y)"
- Satirlar 4192-4206: Rate summary'ye ML corroboration sayimi eklendi
  - "X/Y uyari ML tarafindan destekleniyor"
- Satirlar 4214-4218: Rate alert'lerin `ml_context` dict'i `prediction_alerts`'e forward edildi

**PATCH 6 — Test + Key Name Fix (d41b936):**
- `tests/test_ml_signal_integration.py` (443 satir): 13 unit test
  - TestTrendAnalyzerMLScoreTrend (5 test)
  - TestRateAlertEngineMLContext (2 test)
  - TestForecasterMLMetric (2 test)
  - TestInsightBuilderMLEnrichment (4 test)
- Key name fix: `ml_score_trend.ml_score_direction` (backend) ile `_build_prediction_insight` (orchestrator) arasindaki uyum duzeltildi

**BUG FIX (e02f5df):**
- `rate_alert.py` satir 632: `ml_ts >= window_start` -> `window_start <= ml_ts <= ts_max`
- Sorun: ML anomaly density hesabinda window ust siniri (ts_max) kontrol edilmiyordu
- Etki: Pencere disindan timestamp'lar sayilabiliyordu, density sismesi

---

## 6. COZULEN VE ERTELENEN SORUNLAR

### Cozulen Buglar (Tamami Kapandi)

| # | Bug | Cozum | Commit |
|---|-----|-------|--------|
| BUG-1 | `partial_fit()` StandardScaler bozuyor | Per-batch scaler + `model_scalers` deque | 979776b |
| BUG-2 | MSSQL path `apply_filters()` atliyor | `mssql_feature_engineer.apply_filters()` cagrisi eklendi | 979776b |
| BUG-3 | `self.model = None` sentinel race | `_ensemble_mode` flag ile cozuldu | 979776b |
| BUG-4 | `_instance_lock` shared across subclasses | Per-subclass lock tanimi | 979776b |
| BUG-6 | MongoDB feature_score uncapped | `min(feature_score, 40)` | 979776b |
| ISS-6 | `evaluate_model()` scaler kullanmiyor | `scaler.transform` eklendi | 979776b |
| BUG-7 | Rate alert ML density ust sinir eksik | `window_start <= ml_ts <= ts_max` | e02f5df |
| BUG-8 | Insight builder key name mismatch | `ml_score_direction` key uyumu | d41b936 |

### Bilincli DEFER (Risk Dusuk)

| # | Konu | Neden DEFER |
|---|------|-------------|
| ISS-1 | Incremental learning full refit | IsolationForest `partial_fit` desteklemez; ensemble zaten cozum |
| ISS-2 | `predict()` training lock scope genis | Lock daraltma race condition riski tasir |
| ISS-3 | `_apply_critical_rules` O(nxr) | 14 rule x 500 anomaly = 7000 iteration, negligible |

---

## 7. KULLANILAN TEKNOLOJILER

| Katman | Teknoloji |
|--------|-----------|
| **ML** | scikit-learn (IsolationForest, StandardScaler), numpy, pandas, joblib |
| **Web** | FastAPI, uvicorn, Jinja2 |
| **LLM** | LangChain 0.3.14, LCWGPTConnector (kurumsal), OpenAI gpt-4o (fallback) |
| **Database** | MongoDB (pymongo, motor async), OpenSearch (log kaynagi) |
| **Frontend** | Vanilla JS (11 modul), Chart.js (ML visualization), CSS |
| **Monitoring** | Paramiko (SSH), Linux system monitoring |
| **Container** | Docker, docker-compose |

---

## 8. LCWAIKIKI ENTEGRASYON YAPISI

### LCWGPT (Kurumsal LLM)
- **Connector:** `LCWGPTConnector` (`src/connectors/lcwgpt_connector.py` — 380 satir)
- **API Endpoint:** `https://lcwgpt-test.lcwaikiki.com/api/service/message`
- **Model:** sonnet3.5, Temperature: 0, Timeout: 180s
- **Kullanim:** Anomali aciklama, chat, oneri uretimi
- **Prompt Dili:** Turkce DBA perspektifi
- **Fallback:** OpenAI gpt-4o (`LLM_PROVIDER` env var)

### OpenSearch
- **Host:** `opslog.lcwaikiki.com:443`
- **Index Patterns:** `db-mongodb-*`, `db-mssql-*`, `db-elasticsearch-*`
- **Auth:** db_admin / credentials
- **Scroll API:** 5m timeout, 10000 batch size

### Cluster Mapping
- `config/cluster_mapping.json` — 19 cluster tanimli
- Environment: prod, test, dev, regional
- FQDN -> hostname normalization

---

## 9. PROMPT MUHENDISLIGI VE LLM DAVRANIS KONTROLU

### Anomali Aciklama Prompt'u
- **System prompt (satirlar 3729-3749):** MongoDB DBA uzmani rolunde, 6 bolumlu format (durum degerlendirmesi, kritik bulgular, kok neden, tahmin & trend, acil aksiyonlar, izleme onerisi). Max 600 kelime.
- **User prompt (satirlar 3772-3789):** Top-10 anomali + component analizi + security alerts + temporal dagilim + feature importance + prediction context
- **Token optimizasyonu:** Digest sistemi, top-N kisitlama, numpy type conversion
- **Response parsing:** `_parse_ai_explanation_structured()` -> 4 alan (ne_tespit_edildi, potansiyel_etkiler, muhtemel_nedenler, onerilen_aksiyonlar)
- **Fallback:** LLM bos/hatali donerse `_create_fallback_explanation()` statik aciklama

### Chat Sistemi
- Anomaly digest: Token-efficient ozet (en onemli 5-10 anomali)
- Conversation memory: Son 5 mesaj baglamda tutuluyor
- Sunucu izolasyonu: Her yanit basinda sunucu adi belirtilmeli

### Context Binding
- Run ID: `run_{server}_{timestamp}_{random}` formati
- Server-specific context block: LCWGPT'nin sadece ilgili sunucuyu yorumlamasi
- Prediction context: Trend/rate/forecast bilgisi LLM prompt'una ekleniyor

---

## 10. CONFIG SEMASI OZETI

### `config/anomaly_config.json` (Ana Config)
```json
{
  "model_version": "2.1",
  "server_management": { "model_strategy": "per_server" },
  "model": { "type": "IsolationForest", "parameters": {
    "contamination": 0.03, "n_estimators": 300, "random_state": 42
  }},
  "online_learning": { "enabled": true, "max_history_size": 100000,
    "ensemble": { "max_models": 10 }
  },
  "prediction": {
    "enabled": true,
    "trend_detection": {
      "enabled": true, "min_history_count": 3, "lookback_analyses": 10,
      "anomaly_rate_increase_threshold": 50.0,
      "component_concentration_threshold": 60.0,
      "severity_escalation_threshold": 30.0
    },
    "rate_alerting": {
      "enabled": true, "alert_cooldown_minutes": 30,
      "windows": [
        {"name": "short", "minutes": 15, "auth_failure_threshold": 50, "error_burst_threshold": 100},
        {"name": "medium", "minutes": 60, "auth_failure_threshold": 150, "error_burst_threshold": 300},
        {"name": "long", "minutes": 360, "auth_failure_threshold": 500, "error_burst_threshold": 1000}
      ]
    },
    "scheduler": { "enabled": false, "interval_minutes": 30 },
    "forecasting": {
      "enabled": true, "min_data_points": 5, "forecast_horizon_hours": 6,
      "confidence_interval": 0.95, "seasonality_enabled": true,
      "ewma_fast_alpha": 0.3, "ewma_slow_alpha": 0.1
    }
  },
  "false_positive_reduction": {
    "known_benign_signatures": [
      {"pattern": "privileges on resource", "component": "ACCESS"},
      {"pattern": "serverStatus", "component": "COMMAND"}
    ]
  }
}
```

---

## 11. TEST EDILMEYEN / EKSIK KONULAR

| Konu | Durum |
|------|-------|
| **Multi-tenant load test** | Concurrent 10+ analiz yuk testi yapilmadi |
| **ES/MSSQL prediction e2e** | Prediction layer entegre ama cross-source e2e test eksik |
| **optimize_feature_selection UI** | Fonksiyon yazildi ama hicbir yerden cagrilmiyor |
| **Model retrain scheduler** | Scheduler modulu var, cron entegrasyonu yapilmadi |
| **GitHub Actions CI/CD** | Yok — testler manual/exploratory |

---

## 12. GUNCEL DURUM VE SON ASAMA

### Tamamlanan Moduller (Production-Ready)

| Modul | Durum |
|-------|-------|
| MongoDB anomaly pipeline | Tamamlandi |
| MSSQL anomaly pipeline | Tamamlandi |
| Elasticsearch anomaly pipeline | Tamamlandi |
| Feature engineering (3 kaynak) | Tamamlandi |
| ML model (train/predict/ensemble) | Tamamlandi (F1-F6 fix'li) |
| Storage layer (hybrid) | Tamamlandi |
| LCWGPT entegrasyonu | Tamamlandi |
| Prediction layer (backend) | Tamamlandi |
| Forecaster (tiered) | Tamamlandi |
| User feedback sistemi | Tamamlandi |
| Anomaly digest / chat | Tamamlandi |
| Prediction UI (Studio) | Tamamlandi (full-screen modal, Chart.js) |
| ML Signal Integration | Tamamlandi (PATCH 1-6 + bug fix) |
| Unit Tests (ML signals) | 13/13 PASSED |

### Su An Sistemin Durumu
- **Backend/ML:** Tum kritik buglar cozuldu, dead code temizlendi, production-ready
- **Prediction Layer:** 3 katman (trend + rate + forecast) tam calisir, ML signal overlay aktif
- **API:** Tum endpoint'ler fonksiyonel, prediction + scheduler dahil
- **Frontend:** Anomaly analiz, ML panel, feedback, Prediction Studio, ML badge'lar tam calisir
- **Test:** 13 unit test (ML signal integration) gecti, bug fix dogrulandi

### Son Yapilan Degisiklikler (Bu Oturum)
1. Tum PATCH 1-6 (ML Signal Integration) audit edildi: trend_analyzer, rate_alert, forecaster, orchestrator, UI, CSS
2. 1 bug tespit edildi ve duzeltildi: rate_alert.py window ML density ust sinir eksik (`e02f5df`)
3. 13/13 test basariyla gecti

---

## 13. KALDIGIMIZ YER VE SONRAKI ADIMLAR

### Mevcut Asama
**ML Signal Integration TAMAMLANDI ve AUDIT EDILDI.** Tum prediction katmanlari (trend, rate, forecast) IsolationForest ML sinyalleri ile zenginlestirildi. UI'da badge'lar ve risk gostergeleri aktif. 13 unit test yazildi ve gecti.

### Siradaki Adimlar (Oncelik Sirasina)

1. **Cross-Source Prediction E2E Test**
   - MSSQL ve Elasticsearch icin prediction layer'in end-to-end testi
   - Gercek OpenSearch verileriyle dogrulama

2. **Model Retrain Scheduler Aktiflestime**
   - `scheduler.py` mevcut, cron entegrasyonu yapilabilir
   - Config: `prediction.scheduler.enabled: true, interval_minutes: 30`

3. **Multi-Tenant Load Testing**
   - 10+ concurrent analiz senaryosu
   - Thread safety ve async bridge'in stress testi

4. **Opsiyonel Iyilestirmeler**
   - `optimize_feature_selection()` -> admin endpoint'e baglama
   - CI/CD pipeline (GitHub Actions)
   - Drift detection otomatik retrain tetiklemesi

### Branch Bilgisi
- **Branch:** `claude/verify-prediction-system-JkhT9`
- **Son Commit:** `e02f5df` — "fix(rate-alert): add upper bound check for ML anomaly density window"
- **Push Durumu:** Guncel, origin ile sync

---

> **Bu belge, yeni bir Claude oturumunda ilk mesaj olarak gonderildiginde, projenin tum baglamini sifirdan yukleyecek sekilde hazirlanmistir. Gereksiz tekrar analiz yerine bu belgeyi referans alarak devam edin.**
