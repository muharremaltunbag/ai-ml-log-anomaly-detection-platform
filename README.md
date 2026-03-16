# MongoDB Anomaly Detection Platform

ML-powered database log anomaly detection and early-warning system.
Reads **MongoDB**, **MSSQL**, and **Elasticsearch** logs from OpenSearch, detects anomalies with IsolationForest, predicts trends, and shows everything in a web dashboard.

**Bu proje nedir?**
OpenSearch'ten MongoDB/MSSQL/Elasticsearch loglarını okur, IsolationForest ile anomali tespit eder, trend/rate/forecast tahminleri üretir ve sonuçları web arayüzünde gösterir.

---

## Features

- **Multi-source:** MongoDB, MSSQL, Elasticsearch log analysis from OpenSearch
- **ML detection:** IsolationForest + ensemble rules + online learning
- **Prediction:** Trend detection, rate alerting, time-series forecasting
- **AI explanations:** OpenAI or custom LLM endpoint integration
- **Scheduler:** Automated periodic analysis
- **Web UI:** Dashboard with Prediction Studio, DBA Explorer, ML visualization
- **Config-driven:** Everything via `.env` and JSON config files — no hardcoded secrets

## Architecture

```
OpenSearch ──→ Log Reader ──→ Feature Engineer ──→ IsolationForest
                                                        │
                                          ┌─────────────┼──────────────┐
                                          ▼             ▼              ▼
                                    Trend Analyzer  Rate Alert    Forecaster
                                          │             │              │
                                          └─────────────┼──────────────┘
                                                        ▼
                                               StorageManager
                                            (MongoDB or JSON)
                                                        │
                                                        ▼
                                               Web UI + API
```

---

## Quick Start

### Prerequisites

- Python 3.10+
- OpenSearch instance (data source)
- MongoDB (optional — falls back to JSON file storage)

### 1. Clone and install

```bash
git clone <repo-url>
cd MongoDB-LLM-assistant
python -m venv venv
source venv/bin/activate   # Linux/Mac
# venv\Scripts\activate    # Windows
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
```

Open `.env` and set at minimum:

```
OPENSEARCH_URL=https://your-opensearch:9200
OPENSEARCH_USER=your_user
OPENSEARCH_PASS=your_password
API_KEY=any-random-secret-string
```

### 3. Run

```bash
uvicorn web_ui.api:app --host 127.0.0.1 --port 8000
```

Open **http://localhost:8000** in your browser.

### Docker

```bash
cp .env.example .env
# edit .env
docker-compose up -d
```

---

## Hizli Kurulum (TR)

```bash
git clone <repo-url>
cd MongoDB-LLM-assistant
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# .env dosyasini duzenle (OpenSearch URL, sifre, API key)

uvicorn web_ui.api:app --host 127.0.0.1 --port 8000
# Tarayicida http://localhost:8000 ac
```

**Minimum gerekli ayarlar:** `OPENSEARCH_URL`, `OPENSEARCH_PASS`, `API_KEY`
**MongoDB yoksa:** Sistem otomatik olarak JSON dosya depolamaya duser.

---

## Configuration

### Environment Variables (.env)

| Variable | Required | Description | Default |
|----------|----------|-------------|---------|
| `OPENSEARCH_URL` | Yes | OpenSearch endpoint | `https://localhost:9200` |
| `OPENSEARCH_USER` | Yes | OpenSearch username | `admin` |
| `OPENSEARCH_PASS` | Yes | OpenSearch password | (empty) |
| `OPENSEARCH_TENANT` | No | Multi-tenant setup | `default` |
| `OPENSEARCH_VERIFY_SSL` | No | SSL verification | `true` |
| `API_KEY` | Recommended | Web UI API key | (empty) |
| `MONGODB_URI` | No | MongoDB connection | `mongodb://localhost:27017/...` |
| `MONGODB_ENABLED` | No | Enable MongoDB storage | `true` |
| `LLM_PROVIDER` | No | `openai` or `custom` | `openai` |
| `OPENAI_API_KEY` | No | OpenAI API key (for AI explanations) | (empty) |
| `CUSTOM_LLM_API_KEY` | No | Corporate LLM key | (empty) |
| `CUSTOM_LLM_ENDPOINT` | No | Corporate LLM URL | (empty) |
| `MONGODB_FQDN_SUFFIX` | No | FQDN suffix for short hostnames | `.local` |
| `HOSTNAME_STRIP_SUFFIXES` | No | Suffixes to strip during normalization | `.local,.internal,.example.com` |
| `WEB_HOST` | No | Server bind address | `127.0.0.1` |
| `WEB_PORT` | No | Server port | `8000` |
| `LOG_LEVEL` | No | Logging level | `INFO` |
| `ENVIRONMENT` | No | `development` or `production` | `development` |

### Config Files

| File | Purpose | Required |
|------|---------|----------|
| `config/anomaly_config.json` | MongoDB anomaly detection settings, ML model params, feature config | No (safe defaults) |
| `config/mssql_anomaly_config.json` | MSSQL anomaly detection settings | No |
| `config/elasticsearch_anomaly_config.json` | Elasticsearch anomaly detection settings | No |
| `config/cluster_mapping.json` | Maps hostnames to cluster names | No (unmapped hosts still work) |
| `config/monitoring_servers.json` | SSH monitoring targets for Linux metrics | No |

If a config file is missing, the system logs a warning and continues with empty/default config. No crash.

### Demo Mode / Hostname Masking

The repo includes a **demo UI** at `web_ui/static_demo/` with a 3-layer hostname masking system:

1. **Fetch interceptor** — masks API responses before they reach the app
2. **escapeHtml wrapper** — masks during HTML rendering
3. **MutationObserver** — catches any unmasked text in the DOM

Demo mode is **off by default**. It only activates when accessing `demo-index.html`. The main UI (`index.html`) shows real data unmasked.

To customize demo hostname mappings, edit `web_ui/static_demo/demo-masking.js` → `DEMO_HOST_OVERRIDE_MAP`.

---

## Data Sources

The system reads logs from **OpenSearch** using three specialized readers:

| Source | Index Pattern | Reader |
|--------|---------------|--------|
| MongoDB | `db-mongodb-*` | `OpenSearchProxyReader` |
| MSSQL | `db-mssql-*` | `MSSQLOpenSearchReader` |
| Elasticsearch | `db-elasticsearch-*` | `ElasticsearchOpenSearchReader` |

You can also **upload log files** directly through the Web UI (MongoDB `.log` files).

**Setup:** Point `OPENSEARCH_URL` to your OpenSearch instance. The readers auto-discover available hosts via the configured index patterns.

---

## Storage

Analysis results, predictions, and model metadata are persisted via `StorageManager`:

- **Primary:** MongoDB (if `MONGODB_ENABLED=true` and `MONGODB_URI` is valid)
- **Fallback:** JSON files in `STORAGE_PATH` directory (default: `./data/storage`)

If MongoDB is unavailable, the system automatically falls back to file storage with no data loss. Set `STORAGE_PATH` in `.env` to control where files are saved.

---

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/status` | GET | System health check |
| `/api/anomaly/analyze` | POST | Run anomaly analysis |
| `/api/anomaly/hosts` | GET | List discovered hosts |
| `/api/anomaly/results/{host}` | GET | Get analysis results |
| `/api/anomaly/clusters` | GET | Get cluster-grouped hosts |
| `/api/prediction/risks` | GET | Risk predictions |
| `/api/prediction/forecast/{host}` | GET | Time-series forecast |
| `/api/scheduler/status` | GET | Scheduler status |
| `/api/scheduler/start` | POST | Start automated analysis |
| `/api/chat` | POST | AI-powered Q&A about anomalies |

---

## Project Structure

```
├── src/
│   ├── anomaly/          # Core: detection, feature engineering, prediction, scheduling
│   ├── connectors/       # LLM connectors (OpenAI, corporate LLM)
│   ├── agents/           # LangChain MongoDB agent + query translator
│   ├── storage/          # Persistence (MongoDB + JSON fallback)
│   ├── monitoring/       # Linux server monitoring via SSH
│   └── performance/      # Query performance analysis
├── web_ui/
│   ├── api.py            # FastAPI backend
│   ├── config.py         # Web config (reads .env)
│   ├── static/           # Production frontend
│   └── static_demo/      # Demo frontend with hostname masking
├── config/               # JSON configuration files
├── deploy/               # Docker, systemd, deployment scripts
├── tests/                # Test suites
├── .env.example          # Environment variable template
└── requirements.txt      # Python dependencies
```

---

## Security / Public Release Notes

- **No secrets in this repo.** All API keys, passwords, and credentials are loaded from `.env` (which is in `.gitignore`).
- **No real hostnames.** All server names in config files and code are generic placeholders.
- **Hostname masking** is available in demo mode for screenshots/demos.
- **Example values** (like `CHANGE_ME`, `localhost`) are clearly marked as placeholders.
- To use this system, clone the repo, copy `.env.example` to `.env`, and fill in your own values.

---

## Troubleshooting

**"Config file not found" warning**
Non-critical. The system works with defaults. Create the missing config file from the examples in `config/` if you need custom settings.

**"Failed to connect to OpenSearch"**
Check `OPENSEARCH_URL`, `OPENSEARCH_USER`, `OPENSEARCH_PASS` in `.env`. Verify the OpenSearch instance is reachable and SSL settings match (`OPENSEARCH_VERIFY_SSL`).

**"MongoDB connection failed"**
The system falls back to JSON file storage automatically. If you need MongoDB, check `MONGODB_URI` in `.env`. Set `MONGODB_ENABLED=false` to disable MongoDB entirely.

**"Custom LLM/OpenAI not configured"**
AI-powered explanations are optional. Set `LLM_PROVIDER=openai` and `OPENAI_API_KEY` to enable, or leave empty to skip AI features.

**Import errors (langchain)**
Run `pip install -r requirements.txt` to install all dependencies. The code has fallback imports for both `langchain` and `langchain-core`.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| ML | scikit-learn (IsolationForest), pandas, numpy |
| Backend | FastAPI, uvicorn |
| Frontend | Vanilla JS, Chart.js, CSS Grid |
| Storage | MongoDB (primary), JSON file (fallback) |
| Data Source | OpenSearch |
| LLM | LangChain, OpenAI / Custom LLM |
| Deploy | Docker, systemd |

## License

MIT
