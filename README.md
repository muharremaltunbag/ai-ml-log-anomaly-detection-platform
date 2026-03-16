[English](README.md) | [Türkçe](README.tr.md)

# AI / ML Log Anomaly Detection Platform

AI- and ML-powered platform for log anomaly detection, forecasting, and LLM-assisted operational analysis across MongoDB, MSSQL, and Elasticsearch.

## Overview

Modern systems produce enormous volumes of logs, but most of that data is never interpreted in a proactive, operationally useful way. In practice, incidents are often detected too late, investigated from the wrong layer, or hidden inside noisy, fragmented log streams.

This project was built to solve that problem.

Instead of treating logs as static text that must be manually scanned, the platform converts operational logs into structured signals, analyzes them with machine learning, estimates short-term risk direction, and presents the results through a unified web interface. The goal is not just to say that an anomaly exists, but to help answer:

- what is happening,
- where it is concentrated,
- how severe it is,
- whether it is getting worse,
- and what it likely means operationally.

This is not a single-source script or a narrow anomaly detector. It is a modular, multi-source observability and anomaly analysis platform designed to support:

- **MongoDB**
- **MSSQL**
- **Elasticsearch**

all within one shared analysis pipeline.


## Why This Project Exists

When something goes wrong in a large environment, one of two things usually happens:

1. the issue is noticed too late, or
2. the investigation starts in the wrong place.

The root problem is rarely the absence of logs. In most systems, there are already too many logs. The real difficulty is identifying which signals matter before they grow into larger operational problems.

This project was created to make operational data:

- more readable,
- more interpretable,
- more predictable,
- and more actionable.

The design therefore goes beyond anomaly detection alone. The platform combines:

- log ingestion,
- source-aware parsing,
- feature engineering,
- anomaly detection,
- trend analysis,
- rate-based alerting,
- forecasting,
- AI-assisted explanation,
- storage/history,
- and scheduler-driven orchestration.

## What the Platform Does

At a high level, the platform does five things:

1. **Collects logs from multiple technologies into one platform**
2. **Detects unusual behavior with machine learning**
3. **Surfaces risk without requiring constant manual inspection**
4. **Estimates near-term direction through forecasting**
5. **Explains results in natural language for faster investigation**

In technical terms, this is a **multi-source anomaly detection and forecasting platform**.

In day-to-day use, its value is simpler:

- it gives an earlier signal before a problem grows,
- it shows where the issue is concentrated,
- it makes temporal escalation easier to see,
- and it helps turn noisy logs into understandable operational context.


## Supported Sources

The platform currently supports:

- **MongoDB**
- **MSSQL**
- **Elasticsearch**

The architecture is intentionally modular, so additional sources can be added by following the same pattern:

- source-specific reader,
- source-specific feature engineering,
- source-specific detector,
- shared prediction layer,
- shared storage/history,
- shared API/UI integration.

## Core Features

### 1. Multi-source log analysis

Logs from different systems are read through source-aware readers and normalized into a shared analysis flow.

### 2. Machine learning-based anomaly detection

The platform uses **Isolation Forest** as the core anomaly detection model and manages models at the **per-server** level, preserving behavioral context instead of forcing all hosts into one universal profile.

### 3. Prediction layer

The platform does not stop at current anomalies. It also provides:

- **trend detection**
- **rate-based alerting**
- **short-term forecasting**

This makes it possible to analyze both current deviation and likely direction.

### 4. AI-assisted interpretation

Findings can be translated into natural language through LLM integration, making raw ML results easier to understand and act on.

### 5. Historical context and adaptive behavior

The system preserves historical context and supports adaptive behavior over time through:

- historical buffers,
- incremental learning structures,
- mini-model / ensemble-style updates,
- feature alignment and schema stabilization.

### 6. Unified web interface

A FastAPI backend and Vanilla JavaScript frontend provide one interface for:

- anomaly analysis,
- prediction dashboards,
- risk views,
- scheduler controls,
- historical analysis,
- ML metrics and visualizations,
- alert drill-down,
- and operational context panels.

## High-Level Architecture

The platform is built as a layered system rather than a single model wrapped in an API.

### Main layers

1. **Log ingestion**
2. **Source-aware parsing**
3. **Feature engineering**
4. **Anomaly detection**
5. **Prediction layer**
6. **AI explanation**
7. **Storage and history**
8. **Scheduler / orchestration**

### Data flow

```text
User
   Web UI / API
   Analysis Orchestrator
   Source-specific Reader
   Feature Engineering
   Anomaly Detection
   Prediction Layer
   AI Explanation
   Storage / History
```

### Operational structure

```text
Logs (MongoDB / MSSQL / Elasticsearch)
   OpenSearch
   Reader layer
   Feature engineering
   ML anomaly detection
   Trend / rate / forecast checks
   AI explanation
   Storage + API response
   Web UI / dashboards
```

-

## Repository Structure

```text

 config/# Configuration files
 docs/  # Documentation and transfer notes
 src/
   agents/  # Query / LLM-related agent logic
   anomaly/ # Readers, features, detectors, forecasting
   connectors/ # LLM and database connectors
   monitoring/ # Monitoring helpers
   performance/# Performance analysis tools
storage/ # Storage manager, history, fallback logic
tests/ # Test suite
web_ui/
   api.py# FastAPI backend
   static/  # Frontend assets
Dockerfile
docker-compose.yml
main.py
requirements.txt
```


## Technical Breakdown

## Log Readers

The platform reads logs from OpenSearch using source-specific readers.

| Source  | Reader Layer| Purpose|
| - | - |  |
| MongoDB | `log_reader.py`| Reads MongoDB logs, supports structured and text-like ingestion patterns |
| MSSQL| `mssql_log_reader.py`| Reads MSSQL-related logs through source-aware parsing  |
| Elasticsearch | `elasticsearch_log_reader.py` | Reads Elasticsearch operational logs and source-specific patterns  |

## Feature Engineering

A raw log line is not directly usable by a machine learning model. The system therefore transforms logs into structured signals.

### Feature categories include:

- **time signals**
  - hour of day
  - weekday/weekend
  - inter-arrival timing
  - burst density

- **operational flags**
  - authentication failures
  - slow queries
  - scans
  - transactions
  - memory issues
  - restarts
  - replication-related signals
  - source-specific operational markers

- **numeric weight**
  - durations
  - counts
  - volume indicators
  - severity measures
  - source-specific performance metrics

- **component context**
  - subsystem or component source
  - rare component behavior
  - message fingerprint repetition
  - concentration patterns

- **schema stabilization**
  - feature alignment
  - missing-column handling
  - consistent ordering and typing

This allows the model to see not just message text, but behavioral patterns.

## Anomaly Detection Engine

The core anomaly detection model is based on **scikit-learn IsolationForest**.

### Design principles

- **per-server context**
  - one model should not represent all hosts equally

- **feature scaling**
  - numeric fields are standardized before model use

- **incremental behavior**
  - mini-batch or ensemble-style logic helps absorb newer behavior

- **critical override layer**
  - statistically "normal" does not always mean operationally safe

- **severity scoring**
  - anomalies are prioritized rather than returned as an undifferentiated list

### Severity scoring combines

- ML anomaly score
- component criticality
- operational feature flags
- time context
- rule-based override results

The goal is not only detection, but prioritization.


## Historical Buffer and Adaptive Modeling

The platform does not start every cycle from zero.

### Historical buffer

Past features, anomaly scores, and prior results are preserved and aligned before new analysis. This gives the model context beyond the current batch.

### Adaptive behavior

The system supports a more flexible structure than one static model retrained forever. New behavior can be absorbed through incremental or mini-model style updates.

This matters in operational environments where log distributions drift over time.


## Critical Rule Layer

Pure anomaly logic is not enough in production.

Some events are operationally important even if they are not statistically rare. For that reason, the platform includes a rule-based critical override layer.

Examples of operationally important behavior may include:

- severe memory issues
- large scans
- critical system failures
- replication-related risk
- high-impact security events
- long transactions
- repeated error bursts

This layer complements the model instead of replacing it.


## Prediction Layer

One of the most important parts of the platform is that it does not only describe the present. It also estimates short-term direction.

The prediction layer combines:

- **trend detection**
- **rate-based alerting**
- **forecasting**

### Forecasting strategy

The forecasting engine uses a tiered approach depending on available history.

| Data availability | Strategy  |
| - |  |
| Under 5 points | Direction only  |
| 5â€“9 points  | Weighted moving average  |
| 10â€“19 points| Linear regression  |
| 20+ points  | EWMA-based trend decomposition |

### Forecast outputs may include:

- confidence score
- upper/lower bounds
- volatility
- trend explanation
- recommendation field

### Why this matters

Anomaly detection shows current deviation.

Forecasting helps answer:

- is the situation stabilizing?
- is it escalating?
- is the short-term risk rising?
- which metric is moving toward a more dangerous state?

### AI / LLM Layer

The platform supports AI-assisted explanation on top of anomaly and prediction outputs.

This layer helps convert:

- raw scores,
- feature patterns,
- source-specific findings,
- and prediction context

into natural-language summaries that are easier to interpret operationally.

### Typical goals of the AI layer

- summarize key findings
- explain likely operational meaning
- suggest immediate checks or actions
- provide a clearer narrative for investigation

The project supports both:

- OpenAI-compatible LLM usage
- custom LLM endpoint integration


### Storage and History

The storage layer preserves analysis outputs and makes them reusable.

### Responsibilities include:

- saving anomaly analysis results
- storing prediction alerts and summaries
- retaining model metadata
- preserving history for later comparison
- providing fallback storage paths when needed

This makes the platform useful not just for one-time analysis, but for ongoing operational workflows.

## Scheduler and Orchestration

The platform can run as a repeatable operational process rather than only as a manually triggered script.

### Orchestration safeguards include:

- interval control
- cooldown handling
- overlap protection
- concurrency limits
- host-level tracking

This helps make the platform usable in production-like recurring analysis scenarios.

## Technology Stack

### Backend

- Python
- FastAPI
- Uvicorn

### Machine Learning

- scikit-learn
- pandas
- numpy
- joblib

### Storage / Data

- MongoDB
- OpenSearch

### Frontend

- Vanilla JavaScript
- HTML
- CSS
- Chart.js

### AI / LLM

- OpenAI-compatible models
- custom LLM endpoint support

### Deployment

- Docker
- docker-compose

## Main Functional Areas

### Anomaly Detection

Detects anomalies from MongoDB, MSSQL, and Elasticsearch log streams.

### Prediction Studio

Provides trend analysis, rate alerting, forecasting, and risk context views.

### Analysis History

Stores and retrieves prior analysis results.

### Scheduler Controls

Supports periodic automated workflows.

### AI Explanation

Generates readable summaries of technical findings.

### ML Visualization

Supports metrics and model-related visibility through the web UI.

## Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/muharremaltunbag/ai-ml-log-anomaly-detection-platform.git
cd ai-ml-log-anomaly-detection-platform
```

### 2. Create a virtual environment

```bash
python -m venv venv
```

#### Windows

```bash
venv\Scripts\activate
```

#### Linux / macOS

```bash
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Create your environment file

#### Linux / macOS

```bash
cp .env.example .env
```

#### Windows PowerShell

```powershell
Copy-Item .env.example .env
```

### 5. Fill in required environment variables

Update `.env` with the values appropriate for your environment.

Typical variables include:

- `OPENSEARCH_URL`
- `OPENSEARCH_USER`
- `OPENSEARCH_PASS`
- `MONGODB_URI`
- `OPENAI_API_KEY`
- `LLM_PROVIDER`
- source-specific or storage-related settings

### 6. Run the application

Depending on your setup:

```bash
python main.py
```

or

```bash
uvicorn web_ui.api:app reload
```

## Configuration

The project is configuration-driven and avoids hardcoded credentials in the public release.

Important configuration areas include:

- OpenSearch connectivity
- MongoDB connectivity
- LLM provider selection
- anomaly model behavior
- prediction configuration
- scheduler configuration
- cluster mappings
- monitoring mappings

Relevant files include:

- `.env.example`
- `config/anomaly_config.json`
- `config/cluster_mapping.json`
- `config/monitoring_servers.json`

## Development Notes

This repository is designed to support modular development and extension.

### Principles used in the project

- avoid hardcoded secrets
- preserve backward-compatible data structures where possible
- keep source-specific logic modular
- keep UI logic driven by backend responses
- favor isolated, testable changes
- preserve parity across supported sources where applicable

## Current Status

Implemented and available in the platform:

- multi-source log ingestion
- source-aware feature engineering
- ML-based anomaly detection
- rule-assisted severity logic
- trend analysis
- rate-based alerting
- forecasting
- AI-assisted explanation
- storage and history
- web interface
- scheduler support

## Public Release Notes

This is a sanitized public release of the platform.

Sensitive environment-specific details such as:

- credentials,
- internal endpoints,
- host mappings,
- organization-specific identifiers,
- and internal operational references

have been removed or replaced with configurable placeholders.


-

## License

MIT License


