# MongoDB Anomaly Detection Platform

An enterprise-grade, ML-powered database log anomaly detection and early-warning system. Supports **MongoDB**, **MSSQL**, and **Elasticsearch** log sources via OpenSearch.

## Features

- **Multi-source support:** MongoDB, MSSQL, Elasticsearch log analysis
- **ML anomaly detection:** IsolationForest-based with online learning
- **Prediction & forecasting:** Trend detection, rate alerting, time-series forecasting
- **AI-powered explanations:** Integrates with OpenAI or corporate LLM endpoints
- **Scheduler:** Automated periodic analysis with configurable intervals
- **Web UI:** Interactive dashboard with Prediction Studio, DBA Explorer, ML visualization
- **Config-driven:** All settings via `.env` and JSON config files

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
                                                        │
                                                        ▼
                                               Web UI + API
```

## Project Structure

```
├── src/
│   ├── anomaly/              # Core ML pipeline (detection, prediction, scheduling)
│   ├── connectors/           # LLM connectors (OpenAI, corporate LLM)
│   ├── agents/               # LangChain MongoDB agent
│   ├── storage/              # Persistence layer (MongoDB + JSON fallback)
│   ├── monitoring/           # Linux server monitoring via SSH
│   └── performance/          # Query performance analysis
├── web_ui/                   # FastAPI backend + static frontend
├── config/                   # JSON configuration files
├── deploy/                   # Deployment scripts and systemd service
├── tests/                    # Test suites
└── .env.example              # Environment variable template
```

## Quick Start

### 1. Clone and setup
```bash
git clone <repo-url>
cd MongoDB-LLM-assistant
python -m venv venv
source venv/bin/activate  # Linux/Mac
pip install -r requirements.txt
```

### 2. Configure
```bash
cp .env.example .env
# Edit .env with your values:
#   - MongoDB connection string
#   - OpenSearch URL and credentials
#   - LLM API key (OpenAI or corporate endpoint)
#   - Web UI API key
```

### 3. Configure anomaly detection
Edit `config/anomaly_config.json` to set your OpenSearch host, index patterns, and cluster mapping.

### 4. Run
```bash
uvicorn web_ui.api:app --host 127.0.0.1 --port 8000
```

Open http://localhost:8000 in your browser.

### Docker
```bash
cp .env.example .env
# Edit .env with your values
docker-compose up -d
```

## Configuration

### Environment Variables (.env)

| Variable | Description | Default |
|----------|-------------|---------|
| `MONGODB_URI` | MongoDB connection string | `mongodb://localhost:27017/...` |
| `OPENSEARCH_URL` | OpenSearch endpoint URL | `https://localhost:9200` |
| `OPENSEARCH_USER` | OpenSearch username | `admin` |
| `OPENSEARCH_PASS` | OpenSearch password | (empty) |
| `LLM_PROVIDER` | LLM provider (`openai` or `lcwgpt`) | `openai` |
| `OPENAI_API_KEY` | OpenAI API key | (empty) |
| `API_KEY` | Web UI API key | (empty) |
| `WEB_HOST` | Web server host | `127.0.0.1` |
| `WEB_PORT` | Web server port | `8000` |

### Config Files

- `config/anomaly_config.json` - MongoDB anomaly detection settings
- `config/mssql_anomaly_config.json` - MSSQL anomaly detection settings
- `config/elasticsearch_anomaly_config.json` - Elasticsearch anomaly detection settings
- `config/cluster_mapping.json` - Server-to-cluster mapping
- `config/monitoring_servers.json` - SSH monitoring targets

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/status` | GET | System status |
| `/api/anomaly/analyze` | POST | Run anomaly analysis |
| `/api/anomaly/hosts` | GET | List available hosts |
| `/api/anomaly/results/{host}` | GET | Get analysis results |
| `/api/prediction/risks` | GET | Get risk predictions |
| `/api/scheduler/status` | GET | Scheduler status |
| `/api/scheduler/start` | POST | Start scheduler |
| `/api/chat` | POST | AI chat (Q&A about anomalies) |

## Tech Stack

| Layer | Technology |
|-------|-----------|
| ML | scikit-learn (IsolationForest), pandas, numpy |
| Backend | FastAPI, uvicorn |
| Frontend | Vanilla JS, CSS Grid |
| Storage | MongoDB (primary), JSON fallback |
| Data Source | OpenSearch / Elasticsearch |
| LLM | LangChain, OpenAI / Corporate LLM |
| Deploy | Docker, systemd |

## License

MIT
