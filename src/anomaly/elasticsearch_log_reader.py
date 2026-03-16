# src/anomaly/elasticsearch_log_reader.py
"""
Elasticsearch Log Reader Module
OpenSearch'ten Elasticsearch loglarını okuma ve parse etme

Yapı: MSSQLOpenSearchReader ile aynı, Elasticsearch'e özgü parsing.
Index pattern: db-elasticsearch-*
Host field: cloud.instance.name.keyword
Message field: message (array — message[0] kullanılır)
"""

import re
import json
import logging
import os
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)


# =============================================================================
# ELASTICSEARCH LOG PARSING PATTERNS
# =============================================================================

# Elasticsearch log line format:
# [2026-02-19T10:30:00,000][WARN ][o.e.c.r.a.DiskThresholdMonitor][ECAZTRDBESRW003] flood stage disk watermark...
ES_LOG_LINE_PATTERN = re.compile(
    r'^\[([^\]]+)\]\[([^\]]+)\]\[([^\]]+)\]\s*\[([^\]]+)\]\s*(.*)',
    re.DOTALL
)

# GC overhead patterns
GC_PATTERN = re.compile(
    r'\[gc\]|JvmGcMonitorService|GC overhead|garbage collector|'
    r'spent \[.+\] collecting in the last|overhead',
    re.IGNORECASE
)

# Circuit breaker patterns
CIRCUIT_BREAKER_PATTERN = re.compile(
    r'CircuitBreakingException|circuit breaker|Data too large|'
    r'parent circuit breaker',
    re.IGNORECASE
)

# OOM patterns
OOM_PATTERN = re.compile(
    r'OutOfMemoryError|java\.lang\.OutOfMemoryError|out of memory',
    re.IGNORECASE
)

# Disk watermark patterns
DISK_WATERMARK_PATTERN = re.compile(
    r'disk watermark|flood stage|low disk|DiskThresholdMonitor|'
    r'high disk watermark|disk usage',
    re.IGNORECASE
)

# Shard failure patterns
SHARD_FAILURE_PATTERN = re.compile(
    r'shard failed|unassigned shard|ShardNotFoundException|'
    r'AllocationFailed|failed to execute|shard not available',
    re.IGNORECASE
)

# Node event patterns
NODE_EVENT_PATTERN = re.compile(
    r'node.*joined|node.*left|node.*disconnected|'
    r'NodeDisconnectedException|removed \{',
    re.IGNORECASE
)

# Master election patterns
MASTER_ELECTION_PATTERN = re.compile(
    r'master not discovered|elected-as-master|no master|'
    r'MasterNotDiscoveredException|master changed|'
    r'no known master node|not_master_exception',
    re.IGNORECASE
)

# Slow log patterns
SLOW_LOG_PATTERN = re.compile(
    r'slowlog|took\[',
    re.IGNORECASE
)

# Connection error patterns
CONNECTION_ERROR_PATTERN = re.compile(
    r'ConnectException|ConnectionClosed|connect timed out|'
    r'NodeNotConnectedException|connection reset|'
    r'transport.*exception|ChannelClosedException',
    re.IGNORECASE
)

# Exception patterns
EXCEPTION_PATTERN = re.compile(
    r'Exception|Caused by|at org\.elasticsearch|'
    r'java\.\w+Exception|Throwable',
    re.IGNORECASE
)

# Shard relocation patterns
SHARD_RELOCATION_PATTERN = re.compile(
    r'relocating|shard started|unassigned|'
    r'IndexShardRelocatedException|moving shard',
    re.IGNORECASE
)

# CPU patterns
HIGH_CPU_PATTERN = re.compile(
    r'high cpu|cpu usage|process cpu|hot_threads|'
    r'cpu time|blocked for',
    re.IGNORECASE
)

# Deprecation patterns
DEPRECATION_PATTERN = re.compile(
    r'deprecat',
    re.IGNORECASE
)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def parse_es_log_line(message: str) -> Dict[str, str]:
    """
    Elasticsearch log satırını parse eder.
    Format: [timestamp][log_level][logger][node_name] message_text

    Args:
        message: Raw log line

    Returns:
        Parsed fields dict
    """
    if not message:
        return {
            'parsed_timestamp': '',
            'log_level': 'UNKNOWN',
            'logger_name': '',
            'node_name': '',
            'message_text': ''
        }

    match = ES_LOG_LINE_PATTERN.match(message.strip())
    if match:
        return {
            'parsed_timestamp': match.group(1).strip(),
            'log_level': match.group(2).strip().upper(),
            'logger_name': match.group(3).strip(),
            'node_name': match.group(4).strip(),
            'message_text': match.group(5).strip()
        }

    # Fallback: pattern'a uymuyorsa tüm satırı message_text olarak al
    return {
        'parsed_timestamp': '',
        'log_level': 'UNKNOWN',
        'logger_name': '',
        'node_name': '',
        'message_text': message.strip()
    }


def parse_es_deprecation_json(message: str) -> Optional[Dict[str, str]]:
    """
    Elasticsearch deprecation JSON log satırını parse eder.

    Deprecation logları message[0] içinde JSON string olarak gelir:
    {"@timestamp":"...", "log.level":"WARN", "event.code":"...", "message":"...",
     "log.logger":"...", "elasticsearch.node.name":"...", ...}

    Server logları [ts][LEVEL][logger] formatında gelir — bu fonksiyon
    sadece JSON formatını handle eder.

    Args:
        message: Raw message string (potansiyel JSON)

    Returns:
        Parsed fields dict if valid JSON, None otherwise
    """
    stripped = message.strip()
    if not stripped.startswith('{'):
        return None

    try:
        data = json.loads(stripped)
    except (json.JSONDecodeError, TypeError):
        return None

    # JSON olsa bile deprecation alanları yoksa None dön (false positive JSON'u önle)
    if 'log.level' not in data and 'message' not in data:
        return None

    return {
        'parsed_timestamp': data.get('@timestamp', ''),
        'log_level': data.get('log.level', 'UNKNOWN').strip().upper(),
        'logger_name': data.get('log.logger', ''),
        'node_name': data.get('elasticsearch.node.name', ''),
        'message_text': data.get('message', ''),
        'event_code': data.get('event.code', ''),
        'event_category': data.get('elasticsearch.event.category', ''),
        'cluster_name': data.get('elasticsearch.cluster.name', ''),
        'cluster_uuid': data.get('elasticsearch.cluster.uuid', ''),
    }


def classify_logger(logger_name: str) -> str:
    """
    Elasticsearch logger adını kategorize eder.

    Args:
        logger_name: Logger name (e.g., 'o.e.c.r.a.DiskThresholdMonitor')

    Returns:
        Category string
    """
    if not logger_name:
        return 'unknown'

    ln = logger_name.lower()

    if ln.startswith('o.e.c.') or ln.startswith('o.e.cluster.'):
        return 'cluster'
    elif ln.startswith('o.e.i.') or ln.startswith('o.e.indices.') or ln.startswith('o.e.index.'):
        return 'index'
    elif ln.startswith('o.e.t.') or ln.startswith('o.e.transport.'):
        return 'transport'
    elif 'jvmgc' in ln or 'gc' in ln:
        return 'gc'
    elif ln.startswith('o.e.d.') or ln.startswith('o.e.discovery.'):
        return 'discovery'
    elif ln.startswith('o.e.x.'):
        return 'xpack'
    elif ln.startswith('o.e.a.') or ln.startswith('o.e.action.'):
        return 'action'
    elif ln.startswith('o.e.n.') or ln.startswith('o.e.node.'):
        return 'node'
    elif ln.startswith('o.e.g.') or ln.startswith('o.e.gateway.'):
        return 'gateway'
    elif ln.startswith('o.e.p.') or ln.startswith('o.e.plugins.'):
        return 'plugin'
    else:
        return 'other'


def detect_host_role(hostname: str) -> str:
    """
    Elasticsearch host adından role tespit eder.
    Pattern: ECAZTRDBES{role}{number}
    - DT = data node
    - MS = master node
    - CR = coordinating node
    - RW = warm node

    Args:
        hostname: Host name (e.g., 'ECAZTRDBESDT011')

    Returns:
        Role string
    """
    if not hostname:
        return 'unknown'

    hn = hostname.upper()

    if 'DT' in hn:
        return 'data'
    elif 'MS' in hn:
        return 'master'
    elif 'CR' in hn:
        return 'coordinating'
    elif 'RW' in hn:
        return 'worker'
    else:
        return 'unknown'


def normalize_es_message(message: str) -> str:
    """
    Elasticsearch mesajını normalize eder (fingerprinting için).

    - IP adreslerini <IP> ile değiştirir
    - Hex ID'leri <ID> ile değiştirir
    - Sayıları <NUM> ile değiştirir
    - Index isimlerini sadeleştirir

    Args:
        message: Raw message

    Returns:
        Normalized message
    """
    if not message:
        return ''

    normalized = message

    # IP addresses
    normalized = re.sub(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', '<IP>', normalized)

    # Hex IDs (node IDs, shard IDs etc.)
    normalized = re.sub(r'[0-9a-fA-F]{8,}', '<ID>', normalized)

    # Index names with dates (e.g., my-index-2026.02.19)
    normalized = re.sub(r'\b[\w-]+-\d{4}\.\d{2}\.\d{2}\b', '<INDEX>', normalized)

    # Numbers
    normalized = re.sub(r'\b\d+\b', '<NUM>', normalized)

    # Collapse whitespace
    normalized = " ".join(normalized.split())

    return normalized


def enrich_es_log_entry(log_entry: dict) -> dict:
    """
    Elasticsearch log kaydını zenginleştirir.

    İki farklı log formatını destekler:
    1. Server logs: [timestamp][LEVEL][logger] [node] message (regex parse)
    2. Deprecation logs: JSON string inside message (JSON decode)

    Args:
        log_entry: Raw log entry dict

    Returns:
        Enriched log entry
    """
    enriched = log_entry.copy()

    raw_message = enriched.get('raw_message', '')

    # === Deprecation JSON check — JSON ise önce JSON parse dene ===
    deprecation_parsed = parse_es_deprecation_json(raw_message)

    if deprecation_parsed:
        # Deprecation JSON başarıyla parse edildi
        enriched['log_level'] = deprecation_parsed['log_level']
        enriched['logger_name'] = deprecation_parsed['logger_name']
        enriched['node_name'] = deprecation_parsed['node_name']
        enriched['message_text'] = deprecation_parsed['message_text']
        enriched['event_timestamp'] = deprecation_parsed['parsed_timestamp']
        # Deprecation-specific zengin alanlar
        enriched['event_code'] = deprecation_parsed.get('event_code', '')
        enriched['event_category'] = deprecation_parsed.get('event_category', '')
        enriched['cluster_name'] = deprecation_parsed.get('cluster_name', '')
        enriched['is_deprecation_json'] = True
    else:
        # Server log — mevcut regex parse (değişmedi)
        parsed = parse_es_log_line(raw_message)
        enriched['log_level'] = enriched.get('log_level') or parsed['log_level']
        enriched['logger_name'] = enriched.get('logger_name') or parsed['logger_name']
        enriched['node_name'] = enriched.get('node_name') or parsed['node_name']
        enriched['message_text'] = parsed['message_text']
        enriched['event_timestamp'] = parsed['parsed_timestamp']
        # Server loglarında bu alanlar boş (ama DataFrame tutarlılığı için mevcut)
        enriched['event_code'] = ''
        enriched['event_category'] = ''
        enriched['cluster_name'] = ''
        enriched['is_deprecation_json'] = False

    # Logger category (her iki format için de çalışır)
    enriched['logger_category'] = classify_logger(enriched['logger_name'])

    # Host role
    enriched['host_role'] = detect_host_role(enriched.get('host', ''))

    # Message fingerprint (raw_message üzerinde — her iki format)
    enriched['message_fingerprint'] = normalize_es_message(raw_message)

    # Pattern flags (boolean) — raw_message üzerinde çalışır
    # Deprecation JSON'da da "message" key'i raw_message içinde geçer, pattern'lar çalışır
    enriched['is_gc_overhead'] = bool(GC_PATTERN.search(raw_message))
    enriched['is_circuit_breaker'] = bool(CIRCUIT_BREAKER_PATTERN.search(raw_message))
    enriched['is_oom_error'] = bool(OOM_PATTERN.search(raw_message))
    enriched['is_high_disk_watermark'] = bool(DISK_WATERMARK_PATTERN.search(raw_message))
    enriched['is_shard_failure'] = bool(SHARD_FAILURE_PATTERN.search(raw_message))
    enriched['is_node_event'] = bool(NODE_EVENT_PATTERN.search(raw_message))
    enriched['is_master_election'] = bool(MASTER_ELECTION_PATTERN.search(raw_message))
    enriched['is_slow_log'] = bool(SLOW_LOG_PATTERN.search(raw_message))
    enriched['is_connection_error'] = bool(CONNECTION_ERROR_PATTERN.search(raw_message))
    enriched['is_exception'] = bool(EXCEPTION_PATTERN.search(raw_message))
    enriched['is_shard_relocation'] = bool(SHARD_RELOCATION_PATTERN.search(raw_message))
    enriched['is_high_cpu'] = bool(HIGH_CPU_PATTERN.search(raw_message))
    enriched['is_deprecation'] = bool(DEPRECATION_PATTERN.search(raw_message))

    return enriched


# =============================================================================
# ELASTICSEARCH OPENSEARCH READER CLASS
# =============================================================================

class ElasticsearchOpenSearchReader:
    """
    OpenSearch'ten Elasticsearch loglarını okuyan sınıf.

    MSSQLOpenSearchReader ile aynı yapı, Elasticsearch'e özgü parsing.
    Singleton pattern: get_instance() ile paylaşımlı instance kullanılır.
    """

    _instance = None
    _instance_lock = threading.Lock()

    @classmethod
    def get_instance(cls, config_path: str = "config/elasticsearch_anomaly_config.json"):
        """Shared Elasticsearch reader instance döndürür (Thread-safe)"""
        with cls._instance_lock:
            if cls._instance is None:
                logger.info("Creating GLOBAL Elasticsearch OpenSearch reader instance...")
                cls._instance = cls(config_path)
                cls._instance.connect()
            return cls._instance

    def __init__(self, config_path: str = "config/elasticsearch_anomaly_config.json"):
        """
        Elasticsearch OpenSearch Reader başlat.

        Args:
            config_path: Elasticsearch config dosyası yolu
        """
        self.config_path = config_path
        self.config = self._load_config()

        # OpenSearch bağlantı bilgileri
        self.base_url = os.getenv(
            'OPENSEARCH_URL',
            'https://localhost:9200'
        )
        self.index_pattern = "db-elasticsearch-*"  # Elasticsearch index pattern

        # Host field (aggregation ve filter için)
        self.host_field = self.config.get('message_parsing', {}).get(
            'host_field', 'cloud.instance.name.keyword'
        )

        # Proxy API endpoint (mssql_log_reader.py ile aynı)
        self.proxy_endpoint = f"{self.base_url}/api/console/proxy"

        # Session ve auth
        self.session = None
        self.cookies = None

        # Auth credentials
        self.username = os.getenv('OPENSEARCH_USER', 'admin')
        self.password = os.getenv('OPENSEARCH_PASS', '')

        # Bağlantı durumu
        self._connected = False

        # SSL uyarılarını sustur
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        logger.info(f"ElasticsearchOpenSearchReader initialized - "
                    f"Index: {self.index_pattern}, Host field: {self.host_field}")

    def _load_config(self) -> dict:
        """Config dosyasını yükle"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.warning(f"Config file not found: {self.config_path}, using defaults")
            return {}
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in config: {e}")
            return {}

    def _create_session(self) -> requests.Session:
        """Retry mantığı ile session oluştur (mssql_log_reader.py ile aynı yapı)"""
        session = requests.Session()

        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "POST", "DELETE"]
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        # SSL verification
        session.verify = False

        # Default headers (mssql_log_reader.py ile aynı)
        session.headers.update({
            'Content-Type': 'application/json',
            'osd-version': '2.6.0',
            'Referer': f'{self.base_url}/app/home',
            'Origin': self.base_url
        })

        return session

    def _login(self) -> bool:
        """
        OpenSearch'e login ol (Kibana proxy üzerinden).

        Returns:
            True if successful, False otherwise
        """
        if not self.session:
            self.session = self._create_session()

        login_url = f"{self.base_url}/auth/login"

        try:
            login_data = {
                'username': self.username,
                'password': self.password
            }

            login_headers = {
                'Content-Type': 'application/json',
                'osd-version': '2.6.0',
                'Referer': f'{self.base_url}/app/login?',
                'Origin': self.base_url
            }

            response = self.session.post(
                login_url,
                json=login_data,
                headers=login_headers,
                timeout=30,
                allow_redirects=True
            )

            if response.status_code in [200, 302]:
                self.cookies = self.session.cookies
                logger.info("OpenSearch login successful (Elasticsearch reader)")
                return True
            else:
                logger.error(f"OpenSearch login failed: {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"OpenSearch login error: {e}")
            return False

    def _select_tenant(self, tenant: str = None) -> bool:
        """
        OpenSearch tenant seç.

        Args:
            tenant: Tenant name (from OPENSEARCH_TENANT env var)

        Returns:
            True if successful
        """
        tenant_url = f"{self.base_url}/api/v1/multitenancy/tenant"

        try:
            response = self.session.post(
                tenant_url,
                json={"tenant": tenant, "username": self.username},
                timeout=30
            )

            if response.status_code == 200:
                logger.info(f"Tenant selected: {tenant}")
                return True
            else:
                logger.warning(f"Tenant selection failed: {response.status_code}")
                return True  # Devam et

        except Exception as e:
            logger.warning(f"Tenant selection error: {e}")
            return True

    def _make_request(self, path: str, method: str = "GET",
                      body: dict = None, retry_auth: bool = True) -> dict:
        """Proxy API üzerinden request yap (Auto-Relogin destekli)"""
        try:
            from urllib.parse import quote
            encoded_path = quote(path, safe='/')

            params = {
                'path': encoded_path,
                'method': method
            }

            data = json.dumps(body) if body else "{}"

            response = self.session.post(
                self.proxy_endpoint,
                params=params,
                data=data,
                timeout=120
            )

            # Auto-Relogin on 401/403
            if response.status_code in [401, 403] and retry_auth:
                logger.warning(f"Authentication failed ({response.status_code}). Attempting re-login...")
                if self._login() and self._select_tenant():
                    logger.info("Re-login successful. Retrying request...")
                    return self._make_request(path, method, body, retry_auth=False)
                else:
                    logger.error("Auto re-login failed.")

            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Request failed: {response.status_code} - {response.text[:500]}")
                return None

        except Exception as e:
            if "Read timed out" in str(e) and not hasattr(self, '_retry_count'):
                logger.warning(f"Timeout detected, retrying with longer timeout: {e}")
                self._retry_count = True
                try:
                    response = self.session.post(
                        self.proxy_endpoint,
                        params=params,
                        data=data,
                        timeout=300
                    )
                    if response.status_code == 200:
                        return response.json()
                finally:
                    if hasattr(self, '_retry_count'):
                        delattr(self, '_retry_count')

            logger.error(f"Request error: {e}")
            return None

    def connect(self) -> bool:
        """
        OpenSearch bağlantısını test et.

        Returns:
            True if connected successfully
        """
        try:
            logger.info("Connecting to OpenSearch for Elasticsearch logs...")

            # Session oluştur
            self.session = self._create_session()

            # 1. Login
            if not self._login():
                logger.error("OpenSearch login failed")
                return False

            # 2. Tenant seç
            self._select_tenant(os.getenv('OPENSEARCH_TENANT', 'default'))

            # 3. Bağlantı testi
            result = self._make_request(f"{self.index_pattern}/_count", "GET")

            if result is not None:
                count = result.get('count', 0)
                logger.info(f"OpenSearch connected - Elasticsearch index count: {count:,}")
                self._connected = True
                return True
            else:
                logger.error("Connection test failed")
                return False

        except Exception as e:
            logger.error(f"OpenSearch connection error: {e}")
            return False

    def is_connected(self) -> bool:
        """Bağlantı durumunu döndür"""
        return self._connected

    def read_logs(
        self,
        limit: int = 10000,
        last_hours: int = 24,
        host_filter: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        log_level_filter: Optional[str] = None
    ) -> pd.DataFrame:
        """
        OpenSearch'ten Elasticsearch loglarını oku.

        Args:
            limit: Maximum log sayısı
            last_hours: Son kaç saat (start_time verilmezse)
            host_filter: Belirli bir ES node (cloud.instance.name.keyword)
            start_time: Başlangıç zamanı (ISO format)
            end_time: Bitiş zamanı (ISO format)
            log_level_filter: 'WARN', 'ERROR' vb. (None = tüm loglar)

        Returns:
            DataFrame with Elasticsearch logs
        """
        if not self._connected:
            logger.warning("Not connected, attempting to connect...")
            if not self.connect():
                logger.error("Connection failed")
                return pd.DataFrame()

        logger.info(f"Reading Elasticsearch logs from OpenSearch "
                    f"(limit={limit}, hours={last_hours}, host={host_filter})")

        # Zaman aralığı
        if start_time and end_time:
            time_range = {"gte": start_time, "lte": end_time}
        else:
            time_range = {"gte": f"now-{last_hours}h", "lte": "now"}

        # Query oluştur
        must_conditions = [
            {"range": {"@timestamp": time_range}}
        ]

        # Host filter — cloud.instance.name.keyword kullanır
        if host_filter:
            # Hem orijinal hem UPPER hem LOWER dene (case mismatch koruması)
            must_conditions.append({
                "bool": {
                    "should": [
                        {"term": {self.host_field: host_filter}},
                        {"term": {self.host_field: host_filter.upper()}},
                        {"term": {self.host_field: host_filter.lower()}}
                    ],
                    "minimum_should_match": 1
                }
            })

        # Log level filter
        if log_level_filter:
            # Elasticsearch logları message[0] içinde [WARN ] gibi formatında
            # Ancak loglevel alanı varsa onu kullanalım, yoksa message'dan filtreleriz
            must_conditions.append({
                "bool": {
                    "should": [
                        {"match_phrase": {"message": f"[{log_level_filter}"}},
                        {"term": {"log_level.keyword": log_level_filter}}
                    ],
                    "minimum_should_match": 1
                }
            })

        # search_after pagination
        batch_size = min(limit, 10000)
        max_batches = 10  # Güvenlik limiti: max 100K log

        base_query = {
            "size": batch_size,
            "sort": [
                {"@timestamp": "desc"},
                {"_id": "asc"}
            ],
            "query": {
                "bool": {
                    "must": must_conditions
                }
            },
            "_source": True
        }

        all_records = []
        search_after = None

        for batch_num in range(max_batches):
            query = base_query.copy()
            query["size"] = min(batch_size, limit - len(all_records))

            if search_after:
                query["search_after"] = search_after

            result = self._make_request(
                f"{self.index_pattern}/_search",
                method="POST",
                body=query
            )

            if result is None:
                logger.error(f"Search request failed at batch {batch_num}")
                break

            hits = result.get('hits', {}).get('hits', [])

            if not hits:
                logger.info(f"No more hits at batch {batch_num}")
                break

            logger.info(f"Batch {batch_num}: fetched {len(hits)} hits "
                        f"(total so far: {len(all_records) + len(hits)})")

            for hit in hits:
                source = hit.get('_source', {})
                record = self._parse_es_log(source)
                record['_id'] = hit.get('_id', '')
                record['_index'] = hit.get('_index', '')
                all_records.append(record)

            # search_after: son hit'in sort değerleri
            last_hit = hits[-1]
            search_after = last_hit.get('sort')
            if not search_after:
                logger.info("No sort values in last hit, stopping pagination")
                break

            # Limit'e ulaşıldı mı?
            if len(all_records) >= limit:
                logger.info(f"Reached limit ({limit}), stopping pagination")
                break

        logger.info(f"Fetched {len(all_records)} Elasticsearch logs total")

        if not all_records:
            return pd.DataFrame()

        df = pd.DataFrame(all_records)

        # Timestamp parsing
        if '@timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['@timestamp'], errors='coerce')
            df = df.sort_values('timestamp').reset_index(drop=True)

        logger.info(f"Fetch completed: {len(df)} records")

        return df

    def _parse_es_log(self, source: dict) -> dict:
        """
        OpenSearch'ten gelen Elasticsearch log kaydını parse et.

        Elasticsearch logları 'message' alanı array olarak gelir (message[0]).
        cloud.instance.name.keyword host bilgisini taşır.

        Args:
            source: OpenSearch _source dict

        Returns:
            Parsed and enriched log entry
        """
        # Host bilgisi — cloud.instance.name
        host = source.get('cloud', {}).get('instance', {}).get('name', 'unknown')
        if not host or host == 'unknown':
            # Fallback: host.name alanı
            host = source.get('host', {}).get('name', 'unknown')

        # Message — array ise ilk elemanı al
        message_raw = source.get('message', '')
        if isinstance(message_raw, list):
            raw_message = message_raw[0] if message_raw else ''
        else:
            raw_message = str(message_raw) if message_raw else ''

        # Temel alanlar
        log_entry = {
            'host': host,
            '@timestamp': source.get('@timestamp'),
            'raw_message': raw_message,
            'tags': source.get('tags', []),
            'agent_hostname': source.get('agent', {}).get('hostname', 'unknown'),
            'log_file_path': source.get('log', {}).get('file', {}).get('path', ''),
            # Gerçek veriden keşfedilen metadata alanları
            'event_dataset': source.get('event', {}).get('dataset', ''),
            'fileset_name': source.get('fileset', {}).get('name', ''),
        }

        # Zenginleştirme (log_level, logger_name, pattern flags vb.)
        log_entry = enrich_es_log_entry(log_entry)

        return log_entry

    def get_available_es_hosts(self, last_hours: int = 24) -> List[str]:
        """
        Son N saat içinde log üreten Elasticsearch node'larını listele.

        Args:
            last_hours: Son kaç saat

        Returns:
            List of host names
        """
        if not self._connected:
            if not self.connect():
                return []

        logger.info(f"Getting available Elasticsearch hosts (last {last_hours}h)")

        query = {
            "size": 0,
            "query": {
                "range": {
                    "@timestamp": {
                        "gte": f"now-{last_hours}h",
                        "lte": "now"
                    }
                }
            },
            "aggs": {
                "hosts": {
                    "terms": {
                        "field": self.host_field,
                        "size": 100
                    }
                }
            }
        }

        result = self._make_request(
            f"{self.index_pattern}/_search",
            method="POST",
            body=query
        )

        if result is None:
            logger.error("Host query failed")
            return []

        buckets = result.get('aggregations', {}).get('hosts', {}).get('buckets', [])

        hosts = [b['key'] for b in buckets]
        logger.info(f"Found {len(hosts)} Elasticsearch hosts")

        return hosts

    def get_host_log_stats(self, last_hours: int = 24) -> Dict[str, Any]:
        """
        Elasticsearch node'larının log istatistiklerini getir.

        Args:
            last_hours: Son kaç saat

        Returns:
            Dict with host stats
        """
        if not self._connected:
            if not self.connect():
                return {}

        logger.info(f"Getting Elasticsearch host stats (last {last_hours}h)")

        query = {
            "size": 0,
            "query": {
                "range": {
                    "@timestamp": {
                        "gte": f"now-{last_hours}h",
                        "lte": "now"
                    }
                }
            },
            "aggs": {
                "hosts": {
                    "terms": {
                        "field": self.host_field,
                        "size": 100
                    },
                    "aggs": {
                        "latest_log": {
                            "max": {
                                "field": "@timestamp"
                            }
                        }
                    }
                }
            }
        }

        result = self._make_request(
            f"{self.index_pattern}/_search",
            method="POST",
            body=query
        )

        if result is None:
            logger.error("Stats query failed")
            return {}

        buckets = result.get('aggregations', {}).get('hosts', {}).get('buckets', [])

        stats = {}
        for bucket in buckets:
            host = bucket['key']
            role = detect_host_role(host)
            stats[host] = {
                'total_logs': bucket['doc_count'],
                'latest_log': bucket.get('latest_log', {}).get('value_as_string', ''),
                'host_role': role
            }

        logger.info(f"Got stats for {len(stats)} Elasticsearch hosts")
        return stats


# =============================================================================
# MODULE-LEVEL HELPER FUNCTIONS
# =============================================================================

def get_available_es_hosts(last_hours: int = 24) -> List[str]:
    """
    Module-level function to get available Elasticsearch hosts.
    Singleton instance kullanır.

    Args:
        last_hours: Son kaç saat

    Returns:
        List of host names
    """
    try:
        reader = ElasticsearchOpenSearchReader.get_instance()
        return reader.get_available_es_hosts(last_hours)
    except Exception as e:
        logger.error(f"Error getting Elasticsearch hosts: {e}")
        return []


def get_es_host_stats(last_hours: int = 24) -> Dict[str, Any]:
    """
    Module-level function to get Elasticsearch host statistics.
    Singleton instance kullanır.

    Args:
        last_hours: Son kaç saat

    Returns:
        Dict with host stats
    """
    try:
        reader = ElasticsearchOpenSearchReader.get_instance()
        return reader.get_host_log_stats(last_hours)
    except Exception as e:
        logger.error(f"Error getting Elasticsearch host stats: {e}")
        return {}
