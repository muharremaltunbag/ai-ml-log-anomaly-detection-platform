# src/anomaly/mssql_log_reader.py
"""
MSSQL Log Reader Module
OpenSearch'ten MSSQL loglarını okuma ve parse etme
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
# MSSQL MESSAGE PARSING PATTERNS
# =============================================================================

# Client IP: [CLIENT: 10.111.19.20] or [CLIENT: <local machine>]
CLIENT_IP_PATTERN = re.compile(r'\[CLIENT:\s*([^\]]+)\]')

# Login status: Login succeeded/failed for user
LOGIN_STATUS_PATTERN = re.compile(r'Login (succeeded|failed) for user')

# Username: for user 'username'
USERNAME_PATTERN = re.compile(r"for user '([^']+)'")

# Failure reason: Reason: xxx [CLIENT:
FAILURE_REASON_PATTERN = re.compile(r'Reason:\s*(.+?)(?:\s*\[CLIENT:|$)')

# Auth type: Connection made using SQL Server/Windows authentication
AUTH_TYPE_PATTERN = re.compile(r'Connection made using (SQL Server|Windows) authentication')

# Database name: database 'dbname'
DATABASE_PATTERN = re.compile(r"database '([^']+)'")

# Availability Group pattern
AVAILABILITY_GROUP_PATTERN = re.compile(
    r'availability group|not accessible for queries|AlwaysOn',
    re.IGNORECASE
)

# Error patterns
DATABASE_ACCESS_ERROR_PATTERN = re.compile(
    r'Failed to open.*database|database.*not accessible|Cannot open database',
    re.IGNORECASE
)

# =============================================================================
# ERRORLOG STRUCTURED PARSING PATTERNS
# For grok-failed MSSQL ERRORLOG entries (format: "YYYY-MM-DD HH:MM:SS.ms spidNNNs  message")
# =============================================================================

# Error/Severity/State: "Error: 30089, Severity: 17, State: 1."
ERRORLOG_ERROR_PATTERN = re.compile(
    r'Error:\s*(\d+),\s*Severity:\s*(\d+),\s*State:\s*(\d+)'
)

# SPID: "spid25s" or "spid294s"
ERRORLOG_SPID_PATTERN = re.compile(r'spid(\d+)s?')

# Timestamp in message: "2026-02-23 09:41:56.19"
ERRORLOG_TIMESTAMP_PATTERN = re.compile(
    r'^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+)'
)

# Full-Text Filter Daemon (FDHost) patterns
FDHOST_CRASH_PATTERN = re.compile(
    r'fulltext filter daemon host.*stopped abnormally|FDHost.*stopped',
    re.IGNORECASE
)
FDHOST_RESTART_PATTERN = re.compile(
    r'full-text filter daemon host process has been successfully started',
    re.IGNORECASE
)

# Additional ERRORLOG event type patterns (for logtype classification)
BACKUP_PATTERN = re.compile(
    r'BACKUP\s+(DATABASE|LOG)|backed up|restore completed|RESTORE\s+(DATABASE|LOG)',
    re.IGNORECASE
)
STARTUP_PATTERN = re.compile(
    r'Starting up database|Server is listening on|SQL Server is starting|'
    r'Recovery is complete|Service Broker manager has started',
    re.IGNORECASE
)
DEADLOCK_PATTERN = re.compile(
    r'deadlock victim|Error:\s*1205,|deadlock detected',
    re.IGNORECASE
)
MEMORY_PATTERN = re.compile(
    r'memory pressure|Error:\s*701,|Error:\s*802,|out of memory|'
    r'insufficient memory|memory grant',
    re.IGNORECASE
)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def extract_client_ip(message: str) -> str:
    """
    MSSQL log mesajından client IP adresini çıkarır

    Args:
        message: Raw log message

    Returns:
        Client IP or 'unknown'
    """
    if not message:
        return 'unknown'

    match = CLIENT_IP_PATTERN.search(message)
    if match:
        return match.group(1).strip()
    return 'unknown'


def extract_auth_type(message: str) -> str:
    """
    MSSQL log mesajından authentication tipini çıkarır

    Args:
        message: Raw log message

    Returns:
        'SQL Server', 'Windows', or 'unknown'
    """
    if not message:
        return 'unknown'

    match = AUTH_TYPE_PATTERN.search(message)
    if match:
        return match.group(1)
    return 'unknown'


def extract_username_from_message(message: str) -> str:
    """
    MSSQL log mesajından username'i çıkarır

    Args:
        message: Raw log message

    Returns:
        Username or 'unknown'
    """
    if not message:
        return 'unknown'

    match = USERNAME_PATTERN.search(message)
    if match:
        return match.group(1)
    return 'unknown'


def extract_login_status(message: str) -> str:
    """
    MSSQL log mesajından login durumunu çıkarır

    Args:
        message: Raw log message

    Returns:
        'succeeded', 'failed', or 'unknown'
    """
    if not message:
        return 'unknown'

    match = LOGIN_STATUS_PATTERN.search(message)
    if match:
        return match.group(1)
    return 'unknown'


def extract_failure_reason(message: str) -> str:
    """
    MSSQL failed login mesajından hata nedenini çıkarır

    Args:
        message: Raw log message

    Returns:
        Failure reason or empty string
    """
    if not message:
        return ''

    match = FAILURE_REASON_PATTERN.search(message)
    if match:
        return match.group(1).strip()
    return ''


def extract_database_name(message: str) -> str:
    """
    MSSQL log mesajından database adını çıkarır

    Args:
        message: Raw log message

    Returns:
        Database name or empty string
    """
    if not message:
        return ''

    match = DATABASE_PATTERN.search(message)
    if match:
        return match.group(1)
    return ''


def extract_errorlog_error_info(message: str) -> dict:
    """
    MSSQL ERRORLOG mesajından Error/Severity/State bilgilerini çıkarır

    Args:
        message: Raw log message (e.g. "... Error: 30089, Severity: 17, State: 1.")

    Returns:
        Dict with error_number, error_severity, error_state (int or 0)
    """
    result = {'error_number': 0, 'error_severity': 0, 'error_state': 0}
    if not message:
        return result

    match = ERRORLOG_ERROR_PATTERN.search(message)
    if match:
        result['error_number'] = int(match.group(1))
        result['error_severity'] = int(match.group(2))
        result['error_state'] = int(match.group(3))
    return result


def extract_errorlog_spid(message: str) -> int:
    """
    MSSQL ERRORLOG mesajından SPID (Server Process ID) numarasını çıkarır

    Args:
        message: Raw log message

    Returns:
        SPID number or 0
    """
    if not message:
        return 0

    match = ERRORLOG_SPID_PATTERN.search(message)
    if match:
        return int(match.group(1))
    return 0


def extract_errorlog_timestamp(message: str) -> str:
    """
    MSSQL ERRORLOG mesajından yerel zaman damgasını çıkarır

    Args:
        message: Raw log message

    Returns:
        Local timestamp string or empty string
    """
    if not message:
        return ''

    match = ERRORLOG_TIMESTAMP_PATTERN.search(message)
    if match:
        return match.group(1)
    return ''


def classify_errorlog_message(message: str) -> str:
    """
    MSSQL ERRORLOG mesajını içeriğine göre logtype olarak sınıflandırır

    Grok parse failure olan mesajlar için detaylı sınıflandırma sağlar.

    Args:
        message: Raw log message

    Returns:
        Logtype string: 'Logon', 'Error', 'FDHost', 'Backup', 'Startup',
                        'Deadlock', 'Memory', 'Info', 'Unknown'
    """
    if not message:
        return 'Unknown'

    # Login events (en yüksek öncelik — mevcut grok pattern'ın hedefi)
    if LOGIN_STATUS_PATTERN.search(message):
        return 'Logon'

    # FDHost crash/restart — ayrı kategori (çok yüksek hacim)
    if FDHOST_CRASH_PATTERN.search(message) or FDHOST_RESTART_PATTERN.search(message):
        return 'FDHost'

    # Deadlock — kritik performans
    if DEADLOCK_PATTERN.search(message):
        return 'Deadlock'

    # Memory pressure — kritik sistem sağlığı
    if MEMORY_PATTERN.search(message):
        return 'Memory'

    # Availability Group — kritik HA
    if AVAILABILITY_GROUP_PATTERN.search(message):
        return 'Error'

    # Database access error
    if DATABASE_ACCESS_ERROR_PATTERN.search(message):
        return 'Error'

    # Backup/Restore events
    if BACKUP_PATTERN.search(message):
        return 'Backup'

    # Startup/Recovery events
    if STARTUP_PATTERN.search(message):
        return 'Startup'

    # Generic error (has Error/Severity/State pattern)
    if ERRORLOG_ERROR_PATTERN.search(message):
        return 'Error'

    # No known pattern matched
    return 'Unknown'


def normalize_mssql_message(message: str) -> str:
    """
    MSSQL mesajını normalize eder (fingerprinting için)

    - IP adreslerini <IP> ile değiştirir
    - Kullanıcı adlarını <USER> ile değiştirir
    - Sayıları <NUM> ile değiştirir
    - Timestamp'leri <TS> ile değiştirir

    Args:
        message: Raw message

    Returns:
        Normalized message
    """
    if not message:
        return ''

    normalized = message

    # IP adresleri
    normalized = re.sub(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', '<IP>', normalized)

    # Kullanıcı adları (for user 'xxx')
    normalized = re.sub(r"for user '[^']+'", "for user '<USER>'", normalized)

    # Database adları (database 'xxx')
    normalized = re.sub(r"database '[^']+'", "database '<DB>'", normalized)

    # Timestamp'ler (2026-02-05 16:44:20.70)
    normalized = re.sub(
        r'\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+',
        '<TS>',
        normalized
    )

    # Genel sayılar (ama IP ve TS'den sonra)
    normalized = re.sub(r'\b\d+\b', '<NUM>', normalized)

    return normalized


def enrich_mssql_log_entry(log_entry: dict) -> dict:
    """
    MSSQL log kaydını zenginleştirir

    Args:
        log_entry: Raw log entry dict

    Returns:
        Enriched log entry
    """
    enriched = log_entry.copy()

    message = enriched.get('raw_message', '') or enriched.get('message', '')

    # Message fingerprint
    enriched['message_fingerprint'] = normalize_mssql_message(message)

    # Client IP
    if 'client_ip' not in enriched or enriched['client_ip'] == 'unknown':
        enriched['client_ip'] = extract_client_ip(message)

    # Auth type
    if 'auth_type' not in enriched or enriched['auth_type'] == 'unknown':
        enriched['auth_type'] = extract_auth_type(message)

    # Username (from message if not in fields)
    if 'username' not in enriched or enriched['username'] == 'unknown':
        enriched['username'] = extract_username_from_message(message)

    # Login status (from message if not in fields)
    if 'logintype' not in enriched or enriched['logintype'] == 'unknown':
        enriched['logintype'] = extract_login_status(message)

    # Failure reason (for failed logins)
    if enriched.get('logintype') == 'failed':
        enriched['failure_reason'] = extract_failure_reason(message)

    # Database name
    enriched['database_name'] = extract_database_name(message)

    # Error flags
    enriched['is_availability_group_error'] = bool(
        AVAILABILITY_GROUP_PATTERN.search(message)
    )
    enriched['is_database_access_error'] = bool(
        DATABASE_ACCESS_ERROR_PATTERN.search(message)
    )

    return enriched


# =============================================================================
# MSSQL OPENSEARCH READER CLASS
# =============================================================================

class MSSQLOpenSearchReader:
    """
    OpenSearch'ten MSSQL loglarını okuyan sınıf

    MongoDB OpenSearchProxyReader ile aynı yapı, MSSQL'e özgü parsing.
    Singleton pattern: get_instance() ile paylaşımlı instance kullanılır.
    """

    _instance = None
    _instance_lock = threading.Lock()

    @classmethod
    def get_instance(cls, config_path: str = "config/mssql_anomaly_config.json"):
        """Shared MSSQL reader instance döndürür (Thread-safe)"""
        with cls._instance_lock:
            if cls._instance is None:
                logger.info("Creating GLOBAL MSSQL OpenSearch reader instance...")
                cls._instance = cls(config_path)
                cls._instance.connect()
            return cls._instance

    def __init__(self, config_path: str = "config/mssql_anomaly_config.json"):
        """
        MSSQL OpenSearch Reader başlat

        Args:
            config_path: MSSQL config dosyası yolu
        """
        self.config_path = config_path
        self.config = self._load_config()

        # OpenSearch bağlantı bilgileri
        self.base_url = os.getenv(
            'OPENSEARCH_URL',
            'https://opslog.lcwaikiki.com'
        )
        self.index_pattern = "db-mssql-*"  # MSSQL index pattern

        # Proxy API endpoint (log_reader.py ile aynı)
        self.proxy_endpoint = f"{self.base_url}/api/console/proxy"

        # Session ve auth
        self.session = None
        self.cookies = None

        # Auth credentials
        self.username = os.getenv('OPENSEARCH_USER', 'db_admin')
        self.password = os.getenv('OPENSEARCH_PASS', '')

        # Bağlantı durumu
        self._connected = False

        # SSL uyarılarını sustur (log_reader.py ile aynı)
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        logger.info(f"MSSQLOpenSearchReader initialized - Index: {self.index_pattern}")

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
        """Retry mantığı ile session oluştur (log_reader.py ile aynı yapı)"""
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

        # Default headers (log_reader.py ile aynı)
        session.headers.update({
            'Content-Type': 'application/json',
            'osd-version': '2.6.0',
            'Referer': f'{self.base_url}/app/home',
            'Origin': self.base_url
        })

        return session

    def _login(self) -> bool:
        """
        OpenSearch'e login ol (Kibana proxy üzerinden)

        Returns:
            True if successful, False otherwise
        """
        if not self.session:
            self.session = self._create_session()

        login_url = f"{self.base_url}/auth/login"

        try:
            # JSON-based login (OpenSearch Dashboards format)
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
                logger.info("OpenSearch login successful")
                return True
            else:
                logger.error(f"OpenSearch login failed: {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"OpenSearch login error: {e}")
            return False

    def _select_tenant(self, tenant: str = "LCW") -> bool:
        """
        OpenSearch tenant seç

        Args:
            tenant: Tenant adı (default: LCW)

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
                # Devam et, bazı sistemlerde tenant zorunlu değil
                return True

        except Exception as e:
            logger.warning(f"Tenant selection error: {e}")
            return True  # Devam et

    def _make_request(self, path: str, method: str = "GET", body: dict = None, retry_auth: bool = True) -> dict:
        """Proxy API üzerinden request yap (Auto-Relogin destekli - log_reader.py ile aynı)"""
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
                    delattr(self, '_retry_count')

            logger.error(f"Request error: {e}")
            return None

    def connect(self) -> bool:
        """
        OpenSearch bağlantısını test et (log_reader.py ile aynı flow)

        Returns:
            True if connected successfully
        """
        try:
            logger.info("Connecting to OpenSearch for MSSQL logs...")

            # Session oluştur
            self.session = self._create_session()

            # 1. Login
            if not self._login():
                logger.error("OpenSearch login failed")
                return False

            # 2. Tenant seç
            self._select_tenant("LCW")

            # 3. Bağlantı testi - _make_request ile (auto-relogin destekli)
            result = self._make_request(f"{self.index_pattern}/_count", "GET")

            if result is not None:
                count = result.get('count', 0)
                logger.info(f"OpenSearch connected - MSSQL index count: {count:,}")
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
        login_type_filter: Optional[str] = None,
        logtype_filter: Optional[str] = None
    ) -> pd.DataFrame:
        """
        OpenSearch'ten MSSQL loglarını oku

        Args:
            limit: Maximum log sayısı
            last_hours: Son kaç saat (start_time verilmezse)
            host_filter: Belirli bir MSSQL sunucusu
            start_time: Başlangıç zamanı (ISO format)
            end_time: Bitiş zamanı (ISO format)
            login_type_filter: 'succeeded' veya 'failed'
            logtype_filter: 'Logon', 'Error' vb. (None = tüm loglar)

        Returns:
            DataFrame with MSSQL logs
        """
        if not self._connected:
            logger.warning("Not connected, attempting to connect...")
            if not self.connect():
                logger.error("Connection failed")
                return pd.DataFrame()

        logger.info(f"Reading MSSQL logs from OpenSearch (limit={limit}, hours={last_hours})")

        # Zaman aralığı
        if start_time and end_time:
            time_range = {
                "gte": start_time,
                "lte": end_time
            }
        else:
            time_range = {
                "gte": f"now-{last_hours}h",
                "lte": "now"
            }

        # Query oluştur
        must_conditions = [
            {"range": {"@timestamp": time_range}}
        ]

        # Host filter
        if host_filter:
            # FQDN normalize
            host_short = host_filter.split('.')[0] if '.' in host_filter else host_filter
            must_conditions.append({
                "bool": {
                    "should": [
                        {"term": {"host.name.keyword": host_filter}},
                        {"term": {"host.name.keyword": host_short}},
                        {"term": {"host.name.keyword": host_filter.upper()}},
                        {"term": {"host.name.keyword": host_short.upper()}}
                    ],
                    "minimum_should_match": 1
                }
            })

        # Login type filter (succeeded/failed)
        if login_type_filter:
            must_conditions.append({
                "term": {"logintype.keyword": login_type_filter}
            })

        # Log type filter (Logon/Error/Backup vb.)
        if logtype_filter:
            must_conditions.append({
                "term": {"logtype.keyword": logtype_filter}
            })

        # ── search_after pagination ──────────────────────────────
        # OpenSearch max_result_window = 10000 (varsayılan).
        # 10K'dan fazla log çekmek için batch'ler halinde search_after.
        batch_size = min(limit, 10000)  # Her batch max 10K
        max_batches = 10                # Güvenlik limiti: max 100K log

        base_query = {
            "size": batch_size,
            "sort": [
                {"@timestamp": "desc"},
                {"_id": "asc"}         # tie-breaker (aynı timestamp için)
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

            # API çağrısı
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
                record = self._parse_mssql_log(source)
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

        logger.info(f"Fetched {len(all_records)} MSSQL logs total")

        # DataFrame oluştur
        if not all_records:
            return pd.DataFrame()

        df = pd.DataFrame(all_records)

        # Timestamp parsing
        if '@timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['@timestamp'], errors='coerce')
            df = df.sort_values('timestamp').reset_index(drop=True)

        logger.info(f"Fetch completed: {len(df)} records")

        return df

    def _parse_mssql_log(self, source: dict) -> dict:
        """
        OpenSearch'ten gelen MSSQL log kaydını parse et

        Grok parse failure olan logları da message'dan parse eder

        Args:
            source: OpenSearch _source dict

        Returns:
            Parsed and enriched log entry
        """
        # Temel alanlar
        log_entry = {
            'host': source.get('host', {}).get('name', 'unknown'),
            '@timestamp': source.get('@timestamp'),
            'raw_message': source.get('message', ''),
            'tags': source.get('tags', []),
            'agent_hostname': source.get('agent', {}).get('hostname', 'unknown'),
            'log_file_path': source.get('log', {}).get('file', {}).get('path', ''),
        }

        # Grok parse failure kontrolü
        is_grok_failure = '_grokparsefailure' in log_entry['tags']
        log_entry['is_grok_failure'] = is_grok_failure

        if is_grok_failure:
            # Grok failure: message'dan detaylı parse et
            message = log_entry['raw_message']

            # 1. Detaylı logtype sınıflandırma (eski 3-branch yerine)
            log_entry['logtype'] = classify_errorlog_message(message)

            # 2. Login bilgileri (login event ise)
            login_status = extract_login_status(message)
            log_entry['logintype'] = login_status
            log_entry['username'] = extract_username_from_message(message)

            # 3. ERRORLOG yapısal bilgiler (Error/Severity/State)
            error_info = extract_errorlog_error_info(message)
            log_entry['error_number'] = error_info['error_number']
            log_entry['error_severity'] = error_info['error_severity']
            log_entry['error_state'] = error_info['error_state']

            # 4. SPID (SQL Server process ID)
            log_entry['spid'] = extract_errorlog_spid(message)

            # 5. Local timestamp from message (fallback for logtime)
            log_entry['logtime'] = extract_errorlog_timestamp(message)

            # 6. FDHost crash flag
            log_entry['is_fdhost_event'] = bool(
                FDHOST_CRASH_PATTERN.search(message) or
                FDHOST_RESTART_PATTERN.search(message)
            )
        else:
            # Normal parse edilmiş alanları kullan
            log_entry['logtype'] = source.get('logtype', 'Unknown')
            log_entry['logintype'] = source.get('logintype', 'unknown')
            log_entry['username'] = source.get('USERNAME', 'unknown')
            log_entry['logtime'] = source.get('logtime', '')
            log_entry['hostuser'] = source.get('hostuser', '')

            # Yapısal bilgiler (normal parse'da da message'dan çıkar)
            message = log_entry['raw_message']
            error_info = extract_errorlog_error_info(message)
            log_entry['error_number'] = error_info['error_number']
            log_entry['error_severity'] = error_info['error_severity']
            log_entry['error_state'] = error_info['error_state']
            log_entry['spid'] = extract_errorlog_spid(message)
            log_entry['is_fdhost_event'] = bool(
                FDHOST_CRASH_PATTERN.search(message) or
                FDHOST_RESTART_PATTERN.search(message)
            )

        # log_level: MSSQL severity bilgisi
        # OpenSearch mapping'de log_level/loglevel alanı yok —
        # error_severity'den türet (varsa), yoksa 'unknown'
        if log_entry.get('error_severity', 0) > 0:
            sev = log_entry['error_severity']
            if sev >= 20:
                log_entry['log_level'] = 'fatal'
            elif sev >= 17:
                log_entry['log_level'] = 'error'
            elif sev >= 11:
                log_entry['log_level'] = 'warning'
            else:
                log_entry['log_level'] = 'info'
        else:
            log_entry['log_level'] = source.get('log_level', source.get('loglevel', 'unknown'))

        # Zenginleştirme (client IP, auth type, failure reason, etc.)
        log_entry = enrich_mssql_log_entry(log_entry)

        return log_entry

    def get_available_mssql_hosts(self, last_hours: int = 24) -> List[str]:
        """
        Son N saat içinde log üreten MSSQL sunucularını listele

        Args:
            last_hours: Son kaç saat

        Returns:
            List of host names
        """
        if not self._connected:
            if not self.connect():
                return []

        logger.info(f"Getting available MSSQL hosts (last {last_hours}h)")

        # Aggregation query
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
                        "field": "host.name.keyword",
                        "size": 100
                    }
                }
            }
        }

        # _make_request ile (auto-relogin destekli)
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
        logger.info(f"Found {len(hosts)} MSSQL hosts")

        return hosts

    def get_host_log_stats(self, last_hours: int = 24) -> Dict[str, Any]:
        """
        MSSQL sunucularının log istatistiklerini getir

        Args:
            last_hours: Son kaç saat

        Returns:
            Dict with host stats
        """
        if not self._connected:
            if not self.connect():
                return {}

        logger.info(f"Getting MSSQL host stats (last {last_hours}h)")

        # Multi-aggregation query
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
                        "field": "host.name.keyword",
                        "size": 100
                    },
                    "aggs": {
                        "login_types": {
                            "terms": {
                                "field": "logintype.keyword",
                                "size": 10
                            }
                        },
                        "latest_log": {
                            "max": {
                                "field": "@timestamp"
                            }
                        }
                    }
                }
            }
        }

        # _make_request ile (auto-relogin destekli)
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
            login_types = {
                lt['key']: lt['doc_count']
                for lt in bucket.get('login_types', {}).get('buckets', [])
            }

            stats[host] = {
                'total_logs': bucket['doc_count'],
                'succeeded': login_types.get('succeeded', 0),
                'failed': login_types.get('failed', 0),
                'latest_log': bucket.get('latest_log', {}).get('value_as_string', ''),
                'failed_ratio': login_types.get('failed', 0) / bucket['doc_count']
                    if bucket['doc_count'] > 0 else 0
            }

        logger.info(f"Got stats for {len(stats)} MSSQL hosts")
        return stats


# =============================================================================
# MODULE-LEVEL HELPER FUNCTIONS
# =============================================================================

def get_available_mssql_hosts(last_hours: int = 24) -> List[str]:
    """
    Module-level function to get available MSSQL hosts
    Singleton instance kullanır — gereksiz yeni bağlantı açmaz.

    Args:
        last_hours: Son kaç saat

    Returns:
        List of host names
    """
    try:
        reader = MSSQLOpenSearchReader.get_instance()
        return reader.get_available_mssql_hosts(last_hours)
    except Exception as e:
        logger.error(f"Error getting MSSQL hosts: {e}")
        return []


def get_mssql_host_stats(last_hours: int = 24) -> Dict[str, Any]:
    """
    Module-level function to get MSSQL host statistics
    Singleton instance kullanır — gereksiz yeni bağlantı açmaz.

    Args:
        last_hours: Son kaç saat

    Returns:
        Dict with host stats
    """
    try:
        reader = MSSQLOpenSearchReader.get_instance()
        return reader.get_host_log_stats(last_hours)
    except Exception as e:
        logger.error(f"Error getting MSSQL host stats: {e}")
        return {}
