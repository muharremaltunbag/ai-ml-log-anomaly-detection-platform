# MongoDB LangChain Assistant

**Natural Language Query Assistant for MongoDB (LLM-Powered)**
This project is a CLI + Web-based assistant that enables secure natural language querying on MongoDB using GPT-4o + LangChain, combined with ML-powered anomaly detection, prediction/forecasting, and multi-source log analysis. It is tailored for DBAs and system administrators.

> **Branch:** `claude/add-prediction-ui-oiluN`
> **Toplam Commit:** 57 | **Son Commit:** `b199be3`
> **Tarih:** 2026-02-26

---

## Features

- Natural language to MongoDB query transformation (LLM-based)
- Secure query validator (blocks `$where`, `$function`, JS injection)
- Schema analysis and index suggestions
- Detection of data inconsistency (nulls, mixed types)
- ML-powered anomaly detection (IsolationForest) for MongoDB, MSSQL, Elasticsearch logs
- Prediction layer: Trend analysis, rate alerting, forecasting (EWMA, regression, WMA)
- Multi-source support: MongoDB / MSSQL / Elasticsearch via OpenSearch
- AI-powered anomaly explanations (LCWGPT / OpenAI)
- Web UI with real-time analysis, ML panel, prediction dashboard
- User feedback system (True Positive / False Alarm)
- CLI-based management interface
- Fully configurable via `.env` file and JSON config files
- Docker support via docker-compose

---

## Project Structure

```
MongoDB-LLM-assistant/
├── config/                     # 5 JSON config (anomaly, cluster, es, mssql, monitoring)
├── src/
│   ├── agents/                 # LLM agent: query translator, validator, schema analyzer
│   ├── anomaly/                # ML pipeline: detector, feature engineer, log reader (x3 source)
│   │   ├── anomaly_detector.py       # 3188 lines — Core ML (Isolation Forest)
│   │   ├── anomaly_tools.py          # 5161 lines — Orchestrator + LangChain tools
│   │   ├── feature_engineer.py       #  823 lines — MongoDB feature engineering (40+ features)
│   │   ├── mssql_anomaly_detector.py #  711 lines — MSSQL detector (extends base)
│   │   ├── mssql_feature_engineer.py #  807 lines — MSSQL features
│   │   ├── mssql_log_reader.py       # 1150 lines — MSSQL WMI log reader
│   │   ├── elasticsearch_anomaly_detector.py # 697 — ES detector (extends base)
│   │   ├── elasticsearch_feature_engineer.py # 774 — ES features
│   │   ├── elasticsearch_log_reader.py       # 1044 — ES OpenSearch reader
│   │   ├── log_reader.py             # 1814 lines — MongoDB log reader (JSON/text/OpenSearch)
│   │   ├── forecaster.py             # 1143 lines — Tiered forecaster (EWMA, regression, WMA)
│   │   ├── rate_alert.py             #  676 lines — Rate-based alerting
│   │   ├── trend_analyzer.py         #  623 lines — Trend detection
│   │   ├── scheduler.py              #  226 lines — Auto scheduling
│   │   └── retrain_all_models.py     #  744 lines — Batch retrain
│   ├── connectors/             # MongoDB, LCWGPT, OpenAI connection adapters
│   ├── monitoring/             # SSH-based Linux monitoring
│   ├── performance/            # Query performance (slow queries, explain)
│   └── storage/                # Storage manager, MongoDB handler, fallback
│       ├── storage_manager.py  # 1234 lines — Hybrid storage orchestrator
│       ├── mongodb_handler.py  # 1026 lines — Async MongoDB client
│       └── fallback_storage.py #  188 lines — File-only fallback
├── web_ui/
│   ├── api.py                  # 5755 lines — FastAPI REST API
│   └── static/                 # SPA: index.html + 11 JS modules + CSS
├── tests/                      # 50+ test files
├── docs/                       # Context transfer documents
├── main.py                     # CLI entry point
├── docker-compose.yml          # Container orchestration
└── requirements.txt            # fastapi, langchain, scikit-learn, pymongo, motor, pandas, paramiko
```

---

## Installation

1. **Clone the repository**
```bash
git clone https://github.com/muharremaltunbag/MongoDB-LLM-assistant.git
cd MongoDB-LLM-assistant
```

2. **Create virtual environment**
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Create and configure `.env` file**

```ini
# MongoDB Connection
MONGODB_URI=mongodb://<username>:<password>@localhost:27017/chatbot_test?authSource=admin
MONGODB_DATABASE=chatbot_test

# OpenAI API
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o

# LLM Provider (lcwgpt or openai)
LLM_PROVIDER=openai

# App Settings
MAX_QUERY_LIMIT=100
QUERY_TIMEOUT=30
LOG_LEVEL=INFO
ENVIRONMENT=development
```

---

## Usage

### CLI Mode
```bash
python main.py
```

Sample commands:
- `schema products` — show schema for the products collection
- `find products where stock is missing`
- `how many products have price as string?`
- `find products with no createdAt field`

### Web UI Mode
```bash
uvicorn web_ui.api:app --host 0.0.0.0 --port 8000
```

Access the web dashboard at `http://localhost:8000`. The UI provides:
- MongoDB / MSSQL / Elasticsearch cluster analysis
- ML model panel with training metrics
- Prediction dashboard (trend, rate, forecast alerts)
- AI-powered chat about anomalies
- User feedback (True Positive / False Alarm)
- Analysis history with export

---

## Security

- All queries pass through a secure validator
- Dangerous operators (`$where`, `$function`, JS injection) are blocked
- Each query is limited to 100 results
- Sensitive collections can be restricted
- API key authentication on all endpoints

---

## Project Purpose and Goals

### Why Was It Started?
LCWaikiki's database team (DBA Team) was monitoring logs from MongoDB / MSSQL / Elasticsearch servers **manually**. Hundreds of servers, thousands of log lines, high MTTR (mean time to resolve). Real issues were getting lost in noise.

### What Problem Does It Solve?
1. **Anomaly Detection:** Automatic anomaly detection from logs using ML (Isolation Forest)
2. **Natural Language Interaction:** DBAs can query the system with natural questions like "what happened in the last hour?" (LLM + LangChain)
3. **Multi-Source Support:** MongoDB, MSSQL, Elasticsearch — all via OpenSearch
4. **Prediction Layer:** Trend analysis, rate alerting, forecasting for anomaly prediction
5. **LCWaikiki Integration:** AI explanations via corporate LCW GPT (LLM)

### Ultimate Goal
- Production-grade, self-service DBA monitoring tool
- Full parity across 3 data sources (MongoDB / MSSQL / Elasticsearch)
- Prediction/forecasting UI integration
- Automatic retrain, drift detection, feedback loop

---

## General Rules and Interaction Principles

| Rule | Description |
|------|-------------|
| **No assumptions** | Always read current repo code before making decisions |
| **Don't break existing** | Don't break the production-running pipeline |
| **Modular progress** | Make isolated, testable changes |
| **Justify every change** | Write file, line range, issue, reason, before/after logic |
| **Watch token limits** | Avoid unnecessary re-analysis, this document carries context |
| **Source parity** | Check MSSQL and ES equivalents for every MongoDB fix |
| **Backward compatibility** | save/load, API response formats, config schemas must not change |

---

## Technical Architecture

### Overall Architecture (3 Layers)

```
User → Web UI (FastAPI) → Agent Layer (LangChain) → ML/Storage/Connectors
                                                          ↓
                                       OpenSearch ← MongoDB / MSSQL / ES logs
```

### Async Architecture (FastAPI + Motor Client)

```
FastAPI Main Loop (asyncio)
    │
    ├── to_thread(run_analysis)  ──→  Worker Thread
    │                                      │
    │                                      ├── Feature Engineering (sync)
    │                                      ├── ML Prediction (sync)
    │                                      └── _run_prediction_sync()
    │                                              │
    │  ◄── run_coroutine_threadsafe(coro) ─────────┘
    │
    ├── Motor client (async, bound to main loop)
    └── StorageManager (async, uses Motor)
```

Key insight: `_run_prediction_sync()` uses `asyncio.run_coroutine_threadsafe(coro, main_loop)` to schedule prediction coroutines back on the main event loop where the Motor client lives. This avoids "Future attached to a different loop" errors.

---

## Module Analyses — Detailed

### `anomaly_detector.py` — Core ML Engine (3188 lines)

**Class:** `MongoDBAnomalyDetector`

| Feature | Detail |
|---------|--------|
| **Model** | scikit-learn `IsolationForest` (contamination=0.15, n_estimators=200) |
| **Singleton** | `get_instance(server_name)` — per-server model cache |
| **Thread Safety** | `_instance_lock` (per-subclass), `_training_lock`, `_model_io_lock` |
| **Scaler** | `StandardScaler` + `model_scalers` deque (per-batch snapshot) |
| **Ensemble** | `train_incremental()` — mini batch Isolation Forest ensemble |
| **Feature Alignment** | predict() auto feature reorder/add/drop |
| **Critical Rules** | `_apply_critical_rules()` — rule engine overriding ML (OOM, FATAL, shutdown, etc.) |
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

### `anomaly_tools.py` — Pipeline Orchestrator (5161 lines)

**Class:** `AnomalyDetectionTools`

This file manages the end-to-end pipeline for 3 data sources:

**MongoDB Pipeline:** `analyze_mongodb_logs()`
```
MongoDBLogReader → MongoDBFeatureEngineer → MongoDBAnomalyDetector
→ analyze_anomalies() → LCWGPT AI explanation → StorageManager save
→ Prediction Layer (trend + rate + forecast)
```

**MSSQL Pipeline:** `analyze_mssql_logs()`
```
MSSQLOpenSearchReader → MSSQLFeatureEngineer → MSSQLAnomalyDetector
→ analyze_anomalies() → LCWGPT AI explanation → StorageManager save
→ Prediction Layer
```

**Elasticsearch Pipeline:** `analyze_elasticsearch_logs()`
```
ElasticsearchOpenSearchReader → ElasticsearchFeatureEngineer → ElasticsearchAnomalyDetector
→ analyze_anomalies() → LCWGPT AI explanation → StorageManager save
→ Prediction Layer
```

**LangChain Tools (factory):** `create_anomaly_tools()` → returns 5 StructuredTools:
1. `analyze_mongodb_logs` — MongoDB analysis
2. `analyze_mssql_logs` — MSSQL analysis
3. `analyze_elasticsearch_logs` — ES analysis
4. `get_anomaly_summary` — Past analysis summary
5. `train_anomaly_model` — Model training

**LLM Integration:**
- `LLM_PROVIDER` env var → `lcwgpt` or `openai`
- `LCWGPTConnector` → corporate API
- Prompt: Top-10 anomalies → AI explanation (Turkish)
- Anomaly digest: token-efficient summary (for chat system)

### `forecaster.py` — Prediction Engine (1143 lines)

**Class:** `AnomalyForecaster`

**Tiered Model System:**
| Tier | Data Requirement | Method |
|------|-----------------|--------|
| **Tier 0** | < 3 points | "Insufficient data" |
| **Tier 1** | 3-9 points | Direction prediction (increasing/decreasing) |
| **Tier 2** | 10-19 points | Weighted Moving Average |
| **Tier 3** | 20-49 points | Linear Regression + R² |
| **Tier 4** | 50+ points | EWMA decomposition + seasonality |

**5 Metric Extractors (Cross-Source):**
- `_extract_anomaly_rate()` — anomaly rate (%)
- `_extract_critical_ratio()` — CRITICAL+HIGH percentage
- `_extract_error_rate()` — component-level anomaly
- `_extract_slow_query_count()` — MongoDB slow queries
- `_extract_collscan_count()` — MongoDB collection scans

**Alerting:** `ForecastAlert` dataclass → severity (INFO/WARNING/CRITICAL), confidence, bounds, explainability

### `api.py` — FastAPI Backend (5755 lines)

**Main Endpoints:**

| Endpoint | Method | Function |
|----------|--------|----------|
| `/api/analyze-cluster` | POST | MongoDB cluster analysis |
| `/api/analyze-mssql-logs` | POST | MSSQL analysis |
| `/api/analyze-elasticsearch-logs` | POST | ES analysis |
| `/api/chat` | POST | LCWGPT chat (Q&A about anomalies) |
| `/api/get-anomaly-chunk` | POST | Send anomalies to LCWGPT in chunks of 20 |
| `/api/prediction/alerts` | GET | Prediction alerts |
| `/api/prediction/summary` | GET | Alert statistics |
| `/api/prediction/config` | GET | Prediction config status |
| `/api/scheduler/status` | GET | Scheduler status |
| `/api/scheduler/start` | POST | Start scheduler |
| `/api/scheduler/stop` | POST | Stop scheduler |
| `/api/scheduler/trigger` | POST | Trigger immediate analysis |
| `/api/anomaly/feedback` | POST | User feedback (TP/FP) |
| `/api/anomaly-history` | GET | Paginated analysis history |
| `/api/export-analysis/{id}` | POST | Analysis export |
| `/api/progress` | GET | Real-time progress (streaming) |

**Singleton Management:**
- `get_storage_manager()` → async lock with lazy init
- `get_llm_connector()` → LCWGPTConnector/OpenAI singleton
- `get_anomaly_detector()` → per-server detector

### `storage_manager.py` + `mongodb_handler.py` — Persistence (2260 lines)

**StorageManager Pattern:**
```
API/Tools → StorageManager → MongoDB (metadata) + Filesystem (detail JSON, models)
```

**Key Capabilities:**
- Async/await — FastAPI compatible
- LRU cache — recent analyses in memory
- Auto-cleanup — deletes old data when disk exceeds 80%
- Model versioning — backup + restore
- Hybrid search — MongoDB filter + filesystem detail

**mongodb_handler.py:**
- `save_analysis()`, `get_analysis_history()`, `get_analysis_by_id()`
- `save_prediction_alert()`, `get_prediction_alerts()`, `get_prediction_summary()`
- `save_feedback()`, `get_feedback()`
- `save_model_metadata()`, `get_model_metadata()`

### Feature Engineering (3 Sources)

**MongoDB (`feature_engineer.py` — 823 lines):**
40+ features: severity_score, component encoding, message_length, hour_of_day, operation_type, duration_ms, connection features, replication features, query pattern features, transaction indicators, seasonal decomposition

**MSSQL (`mssql_feature_engineer.py` — 807 lines):**
Error code encoding, severity level, login features (failed_login_ratio, time_since_last_login), IP/username frequency baseline, connection error patterns, permission error patterns

**Elasticsearch (`elasticsearch_feature_engineer.py` — 774 lines):**
Log level encoding, GC metrics, index operation features, cluster health features, node statistics, search latency features

### Log Readers (3 Sources)

All read from OpenSearch:
- **MongoDB:** `db-mongodb-*` index pattern
- **MSSQL:** `db-mssql-*` index pattern
- **Elasticsearch:** `db-elasticsearch-*` index pattern

OpenSearch connection: `opslog.lcwaikiki.com:443` (HTTPS, SSL verify=false)
Alternate hosts: `10.29.21.30:443`, `hqopnsrcmstr01-03.lcwaikiki.local:9200`

---

## Development History — Chronological

### Faz 1: MSSQL Pipeline Strengthening (Commit 49eb675 → f50f5fa)
- False positive reduction: Known benign signature allowlist
- Drift detection: Wasserstein distance + KS test
- SLO: Alert budget + contamination tracking
- MSSQL: Rule engine fix, failed_login_ratio fix, time_since_last_login feature
- MSSQL: IP/username frequency baseline, regex narrowing, severity scoring fix
- MSSQL: Template method pattern for message extraction

### Faz 2: ML Panel & Feedback System (4cb0f18 → c472915)
- System reset script (system_reset.py)
- UI: System reset button + modal
- ML panel: Hardcoded metrics → real model data
- User feedback system: True Positive / False Alarm buttons
- UI: Feedback button improvements

### Faz 3: Elasticsearch Pipeline (1062487 → 3aa7c1d)
- Elasticsearch log anomaly detection pipeline built from scratch
- ES pipeline bug fixes (event_timestamp, CRITICAL severity scoring)
- OpenSearch `db-elasticsearch-*` hardening
- ES detector finalize

### Faz 4: UI Integration & Source Parity (d1f9349 → 8250549)
- ES UI integration (same level as MongoDB/MSSQL)
- Storage layer bug fix (all sources)
- LCWGPT invoke path fix
- AI prompt enrichment (3 sources)
- Anomaly digest + conversation memory (token-efficient chat)
- NoneType crash prevention (entire codebase)
- Data source card redesign, MSSQL ERRORLOG integration
- Feature name validation — state mutation prevention
- LCWGPT response validation

### Faz 5: Prediction Layer (d198d81 → 5c24d3b)
- Prediction layer added (trend, rate, forecast)
- Forecaster module: Tiered model (EWMA, regression, WMA)
- Concurrency fix (multi-tenant)
- MSSQL + ES pipeline prediction integration
- Cross-source prediction support strengthening
- Comprehensive prediction improvements (P1-P6):
  - P1: Forecaster `_extract_anomaly_rate` cross-source field map
  - P2: Config `prediction.forecasting.confidence_level` support
  - P3: Trend analyzer `_safe_get_stats` defensive accessor
  - P4: Rate alert `severity_distribution` fallback
  - P5: Storage manager `save_prediction_alert` auto-init
  - P6: API endpoints return all prediction config fields

### Faz 6: Production Readiness (979776b → c76b6f8)
- **F1:** Scaler corruption fix → per-batch `batch_scaler` + `model_scalers` deque
- **F2:** MSSQL `apply_filters()` skip fix
- **F3:** self.model = None sentinel → `_ensemble_mode` flag
- **F4:** Per-subclass `_instance_lock` (MSSQL, ES separate locks)
- **F5:** OpenSearch redundant load_model → verified (no issue)
- **F6:** `evaluate_model()` scaler.transform added
- Dead code cleanup: `_calculate_sample_weights`, `export_results` deleted
- 22 bare `print()` → `logger.info()` / `logger.debug()` conversion
- `create_validation_dataset()` return type annotation fix (2→3 elements)

### Faz 7: Prediction UI Integration (d5090e7 → b199be3)
- **Prediction Dashboard UI:** Standalone prediction dashboard module (`script-prediction.js`, 635 lines)
  - Trend alert widget (increasing/decreasing anomaly rate)
  - Rate alert dashboard (real-time threshold violations)
  - Forecast display with tier information
  - Alert severity coloring and statistics
  - Scheduler management panel (start/stop/trigger)
- **Cache-Busting Fix:** Added `?v=20260226` query strings to all CSS/JS references in `index.html` to force browsers to load fresh assets instead of stale cached versions
- **CSS Grid Fix:** Updated `.quick-actions` grid from `repeat(5, 1fr)` to `repeat(6, 1fr)` to accommodate the new Prediction Dashboard button
- **Scheduler Endpoint NameError Fix:** 4 scheduler endpoints in `api.py` used undefined `validate_api_key()` — fixed to use the correct async `verify_api_key()` function
- **Permanent Async Fix for Motor Client:** Replaced thread+new-event-loop hack in `_run_prediction_sync()` with `asyncio.run_coroutine_threadsafe(coro, main_loop)`:
  - Added `_shared_storage_loop` class variable to store reference to the main event loop
  - Modified `set_shared_storage_manager()` to capture `asyncio.get_running_loop()` at startup
  - Prediction coroutines are now scheduled on the main loop where Motor client lives
  - No deadlock because the main loop is idle (waiting for worker thread via `to_thread`)
  - Removed unused `import threading`

---

## Resolved and Deferred Issues

### Resolved Bugs (All Closed)

| # | Bug | Solution | Commit |
|---|-----|----------|--------|
| BUG-1 | `partial_fit()` corrupts StandardScaler | Per-batch scaler + `model_scalers` deque | F1 (979776b) |
| BUG-2 | MSSQL path skips `apply_filters()` | Added `mssql_feature_engineer.apply_filters()` call | F2 (979776b) |
| BUG-3 | `self.model = None` sentinel race | Solved with `_ensemble_mode` flag | F3 (979776b) |
| BUG-4 | `_instance_lock` shared across subclasses | Per-subclass lock definition | F4 (979776b) |
| BUG-5 | OpenSearch redundant `load_model()` | Verified — no issue | F5 (979776b) |
| BUG-6 | MongoDB feature_score uncapped | `min(feature_score, 40)` | F6 (979776b) |
| ISS-6 | `evaluate_model()` not using scaler | Added `scaler.transform` | F6 (979776b) |
| BUG-7 | Scheduler `validate_api_key` NameError | Fixed to `verify_api_key` (async) | Faz 7 (575f14b) |
| BUG-8 | "Future attached to a different loop" | `run_coroutine_threadsafe` to main loop | Faz 7 (b199be3) |

### Consciously Deferred (Low Risk)

| # | Topic | Reason |
|---|-------|--------|
| ISS-1 | Incremental learning full refit | IsolationForest doesn't support `partial_fit`; `train_incremental()` ensemble is the solution |
| ISS-2 | `predict()` training lock scope wide | Narrowing lock risks race conditions; current throughput is sufficient |
| ISS-3 | `_apply_critical_rules` O(n×r) | 11 rules × 500 anomalies = 5500 iterations, negligible |

### Dead Code Decisions

| Function | Decision | Reason |
|----------|----------|--------|
| `_calculate_sample_weights()` | **DELETE** | IsolationForest doesn't support sample_weight |
| `export_results()` | **DELETE** | Storage layer already provides persistence |
| `create_validation_dataset()` | **KEEP** | `evaluate_model()` actively calls it |
| `optimize_feature_selection()` | **DEFER** | Can be integrated into diagnostic dashboard later |
| `get_prediction_summary()` | **KEEP** | `/api/prediction/summary` actively uses it |
| Debug prints | **FIX** | 22 `print()` → `logger` converted |

---

## Technologies Used

| Layer | Technology |
|-------|-----------|
| **ML** | scikit-learn (IsolationForest, StandardScaler), numpy, pandas, joblib |
| **Web** | FastAPI, uvicorn, Jinja2 |
| **LLM** | LangChain 0.3.14, LCWGPTConnector (corporate), OpenAI (fallback) |
| **Database** | MongoDB (pymongo, motor async), OpenSearch (log source) |
| **Frontend** | Vanilla JS (11 modules), Chart.js (ML visualization), CSS |
| **Monitoring** | Paramiko (SSH), Linux system monitoring |
| **Container** | Docker, docker-compose |
| **VCS** | Git |

---

## LCWaikiki Integration

### LCWGPT (Corporate LLM)
- **Connector:** `LCWGPTConnector` (`src/connectors/lcwgpt_connector.py`)
- **API:** Corporate endpoint (env var: `LCWGPT_API_URL`)
- **Usage:** Anomaly explanation, chat, recommendation generation
- **Prompt Language:** Turkish DBA perspective
- **Fallback:** OpenAI (env var: `LLM_PROVIDER`)

### OpenSearch
- **Host:** `opslog.lcwaikiki.com:443`
- **Index Patterns:** `db-mongodb-*`, `db-mssql-*`, `db-elasticsearch-*`
- **Auth:** Credentials (config JSON)
- **Scroll API:** 5m timeout, 10000 batch size

### Cluster Mapping
- `config/cluster_mapping.json` — 19 clusters defined
- Environment: prod, test, dev, regional
- FQDN → hostname normalization (e.g., `ecaztrdbmng015.lcwecomtr.com` → `ecaztrdbmng015`)

---

## Prompt Engineering and LLM Behavior Control

### Anomaly Explanation Prompt
- Top-10 anomalies → sent to LCWGPT
- Prompt: server name, source type, anomaly count, severity breakdown, top anomalies with details
- Language: Turkish, DBA perspective
- Token limit: Overflow prevented by digest system

### Chat System
- Anomaly digest: Token-efficient summary (top 5-10 anomalies)
- Conversation memory: Last 5 messages kept in context
- Context: Latest analysis results + digest + user question

### Response Validation
- LCWGPT response format check (for 3 sources)
- Fallback explanation: Static explanation if LLM returns empty/error

---

## Config Schema Summary

### `config/anomaly_config.json` (Main Config)
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
  "false_positive_reduction": { "known_benign_signatures": ["..."] }
}
```

---

## MongoDB Test Database Structure

**Collection: `products`**

Sample fields:
- `name`: String or null
- `category`: "Male", "Female", "Child", or "Sensitive"
- `price`: Number or string
- `stock`: Object by size or undefined
- `createdAt`: Date or null
- `manufacturer`: Object (e.g. `{ name: "besttextile" }`) or null
- `description`: Some over 1000 characters
- `tags`, `variants`, `ratings`, `reviews`, `seo`, `campaign`: nested or array fields

**Test scenarios include:**
- `name`: null or empty
- `price`: string type (e.g., "999.99")
- `stock`: missing or undefined
- `createdAt`: old date (e.g., 2020) or null
- `category`: "Sensitive" (policy test)
- `manufacturer`: empty object or null
- `description`: excessively long
- `veryLargeDocument`: true (anomaly test)

---

## Untested / Missing Topics

| Topic | Status |
|-------|--------|
| **Forecasting chart** | `forecaster.py` produces data, frontend displays alerts but no time-series chart yet |
| **Multi-tenant load test** | Concurrent 10+ analysis load test not done |
| **ES/MSSQL prediction e2e** | Prediction layer integrated but cross-source e2e test missing |
| **optimize_feature_selection UI** | Function written but not called from anywhere |
| **Model retrain scheduler** | Scheduler module exists, cron integration not done |

---

## Current Status

### Completed Modules (Production-Ready)

| Module | Status |
|--------|--------|
| MongoDB anomaly pipeline | Production |
| MSSQL anomaly pipeline | Production |
| Elasticsearch anomaly pipeline | Production |
| Feature engineering (3 sources) | Production |
| ML model (train/predict/ensemble) | Production (F1-F6 fixed) |
| Storage layer (hybrid) | Production |
| LCWGPT integration | Production |
| Prediction layer (backend) | Production |
| Forecaster (tiered) | Production |
| User feedback system | Production |
| Anomaly digest / chat | Production |
| Prediction Dashboard UI | Production (Faz 7) |
| Scheduler management UI | Production (Faz 7) |

### System State
- **Backend/ML:** All critical bugs resolved, dead code cleaned, production-ready
- **API:** All endpoints functional, including prediction and scheduler
- **Frontend:** Anomaly analysis, ML panel, feedback, prediction dashboard all working
- **Async Architecture:** Permanent fix for cross-loop Motor client (run_coroutine_threadsafe)

---

## Next Steps (Priority Order)

1. **Forecasting Visualization**
   - Chart.js time series chart for forecast projections
   - Confidence bands visualization
   - Tier information display

2. **Optional Improvements**
   - `optimize_feature_selection()` → connect to admin/diagnostic endpoint
   - Model retrain scheduler → cron integration
   - Multi-tenant load testing
   - ES/MSSQL prediction e2e test

---

## Contribution & Development

Pull requests and suggestions are welcome. The **issues** and **projects** tabs are actively used for development tracking.

---

## Developer

**Muharrem Altunbag**
altunbgmuharrem@gmail.com
[LinkedIn](https://www.linkedin.com/in/muharrem-altunbag/)

---

> **This document serves as both a README and context transfer document. When sent as the first message in a new Claude session, it loads the full project context from scratch. Use this document as reference instead of unnecessary re-analysis.**
