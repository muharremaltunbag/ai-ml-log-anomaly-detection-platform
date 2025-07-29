#src/anomaly/log_reader.py
"""
MongoDB Log Reader Module
Hem JSON hem de legacy text formatını destekler
"""
import os
import json
import re
import pandas as pd
from pathlib import Path
from typing import List, Dict, Any, Optional, Union
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import logging
import gc
import requests
from requests.auth import HTTPBasicAuth
from urllib.parse import quote
import urllib3
from datetime import datetime, timedelta

from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)


class MongoDBLogReader:
    """MongoDB log dosyalarını okuma ve parse etme"""
    
    def __init__(self, log_path: str = None, format: str = "auto"):
        """
        MongoDB Log Reader başlat
        
        Args:
            log_path: Log dosyası yolu
            format: Log formatı ("json", "text", "auto")
        """
        print(f"[DEBUG] MongoDBLogReader init started - log_path: {log_path}, format: {format}")
        self.log_path = log_path or self._find_mongod_log()
        print(f"[DEBUG] Final log_path: {self.log_path}")
        self.format = format
        self.encoding = 'utf-8'
        self.buffer_size = 8192
        
        # Format otomatik tespit
        if self.format == "auto":
            print("[DEBUG] Auto-detecting log format...")
            self.format = self._detect_log_format()
            print(f"[DEBUG] Detected format: {self.format}")
            
        logger.info(f"Log reader initialized - Path: {self.log_path}, Format: {self.format}")
        print(f"[DEBUG] MongoDBLogReader init completed")
    
    def _find_mongod_log(self) -> str:
        """MongoDB log dosyasını otomatik bul"""
        print("[DEBUG] Searching for MongoDB log file...")
        possible_paths = [
            # Linux/Production
            Path("/var/log/mongodb/mongod.log"),
            # Windows test ortamı
            Path("C:/Users/muharrem.altunbag/Desktop/Anomaly_Detection/Latest/log dosya/mongod.log"),
            # Vagrant test
            Path("/home/vagrant/mongod.log"),
        ]
        
        for path in possible_paths:
            print(f"[DEBUG] Checking path: {path}")
            if path.exists():
                print(f"[DEBUG] Found log file at: {path}")
                return str(path)
        
        # Hiçbiri yoksa varsayılan
        print("[DEBUG] No log file found, using default path")
        return "/var/log/mongodb/mongod.log"
    
    def _detect_log_format(self) -> str:
        """Log formatını otomatik tespit et"""
        try:
            logger.debug(f"Detecting log format for file: {self.log_path}")
            print(f"[DEBUG] Opening file for format detection: {self.log_path}")
            with open(self.log_path, 'r', encoding=self.encoding) as f:
                first_line = f.readline().strip()
                logger.debug(f"First line sample: {first_line[:100]}...")
                print(f"[DEBUG] First line sample: {first_line[:100]}...")
                
                # JSON formatı kontrolü
                if first_line.startswith('{') and '"t":' in first_line:
                    logger.debug("Detected JSON format")
                    print("[DEBUG] Format detected as JSON")
                    return "json"
                # Legacy text format kontrolü (timestamp ile başlar)
                elif re.match(r'^\d{4}-\d{2}-\d{2}T', first_line):
                    logger.debug("Detected text format")
                    print("[DEBUG] Format detected as text")
                    return "text"
                else:
                    logger.warning("Log format could not be detected, defaulting to text")
                    print("[DEBUG] Format could not be detected, defaulting to text")
                    return "text"
                    
        except Exception as e:
            logger.error(f"Format detection error: {e}")
            logger.debug(f"Format detection failed for: {self.log_path}", exc_info=True)
            print(f"[DEBUG] Format detection error: {e}")
            return "text"
    
    def read_logs(self, limit: int = None, last_hours: int = None) -> pd.DataFrame:
        """
        Log dosyasını oku ve DataFrame'e dönüştür
        
        Args:
            limit: Okunacak maksimum satır sayısı
            last_hours: Son N saatteki logları oku
            
        Returns:
            pd.DataFrame: Log verileri
        """
        print(f"[DEBUG] read_logs called - limit: {limit}, last_hours: {last_hours}, format: {self.format}")
        if self.format == "json":
            print("[DEBUG] Using JSON log reader")
            return self._read_json_logs(limit, last_hours)
        else:
            print("[DEBUG] Using text log reader")
            return self._read_text_logs(limit, last_hours)
    
    def _read_json_logs(self, limit: int = None, last_hours: int = None) -> pd.DataFrame:
        """JSON formatındaki logları oku"""
        logs = []
        count = 0
        parse_errors = 0
        
        logger.debug(f"Starting JSON log reading - limit: {limit}, last_hours: {last_hours}")
        print(f"[DEBUG] Starting JSON log reading - limit: {limit}, last_hours: {last_hours}")
        
        try:
            print(f"[DEBUG] Opening JSON log file: {self.log_path}")
            with open(self.log_path, 'r', encoding=self.encoding) as f:
                for line_num, line in enumerate(f, 1):
                    if limit and count >= limit:
                        print(f"[DEBUG] Limit reached: {count}")
                        break
                        
                    try:
                        log_entry = json.loads(line.strip())
                        
                        # Zaman filtresi
                        if last_hours and 't' in log_entry:
                            log_time = pd.to_datetime(log_entry['t']['$date'])
                            cutoff_time = datetime.now() - pd.Timedelta(hours=last_hours)
                            if log_time < cutoff_time:
                                continue
                                
                        logs.append(log_entry)
                        count += 1
                        
                        if count % 10000 == 0:
                            logger.debug(f"Processed {count} JSON log entries")
                            print(f"[DEBUG] Processed {count} JSON log entries")
                        
                    except json.JSONDecodeError:
                        parse_errors += 1
                        if parse_errors <= 5:  # Log only first 5 errors
                            logger.debug(f"JSON parse error at line {line_num}: {line[:100]}...")
                            print(f"[DEBUG] JSON parse error at line {line_num}")
                        continue
                    except Exception as e:
                        logger.warning(f"Error parsing log line {line_num}: {e}")
                        print(f"[DEBUG] Error parsing log line {line_num}: {e}")
                        continue
            
            logger.info(f"Read {len(logs)} JSON log entries")
            print(f"[DEBUG] Completed JSON reading: {len(logs)} entries, {parse_errors} errors")
            if parse_errors > 0:
                logger.debug(f"Total JSON parse errors: {parse_errors}")
            return pd.DataFrame(logs)
            
        except Exception as e:
            logger.error(f"Error reading JSON logs: {e}")
            logger.debug("JSON log reading failed", exc_info=True)
            print(f"[DEBUG] JSON log reading failed: {e}")
            return pd.DataFrame()
    
    def _read_text_logs(self, limit: int = None, last_hours: int = None) -> pd.DataFrame:
        """Legacy text formatındaki logları oku ve JSON benzeri formata dönüştür"""
        logs = []
        count = 0
        parse_errors = 0
        
        logger.debug(f"Starting text log reading - limit: {limit}, last_hours: {last_hours}")
        print(f"[DEBUG] Starting text log reading - limit: {limit}, last_hours: {last_hours}")
        
        # Text log pattern
        # Format: 2025-06-22T06:25:06.125+0300 I  ACCESS   [conn1661946] message...
        pattern = re.compile(
            r'^(?P<timestamp>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}[+-]\d{4})\s+'
            r'(?P<severity>[IWEF])\s+'
            r'(?P<component>\S+)\s+'
            r'\[(?P<context>[^\]]+)\]\s+'
            r'(?P<message>.*)'
        )
        
        try:
            print(f"[DEBUG] Opening text log file: {self.log_path}")
            with open(self.log_path, 'r', encoding=self.encoding) as f:
                for line_num, line in enumerate(f, 1):
                    if limit and count >= limit:
                        print(f"[DEBUG] Limit reached: {count}")
                        break
                    
                    match = pattern.match(line.strip())
                    if match:
                        data = match.groupdict()
                        
                        # Zaman filtresi
                        if last_hours:
                            log_time = pd.to_datetime(data['timestamp'])
                            cutoff_time = datetime.now() - pd.Timedelta(hours=last_hours)
                            if log_time < cutoff_time:
                                continue
                        
                        # JSON formatına dönüştür
                        log_entry = {
                            't': {'$date': data['timestamp']},
                            's': data['severity'],
                            'c': data['component'],
                            'ctx': data['context'],
                            'msg': data['message'],
                            'attr': {}  # Text formatta attr yok
                        }
                        
                        # Özel mesaj parse işlemleri
                        self._parse_text_message_attributes(log_entry)
                        
                        logs.append(log_entry)
                        count += 1
                        
                        if count % 10000 == 0:
                            logger.debug(f"Processed {count} text log entries")
                            print(f"[DEBUG] Processed {count} text log entries")
                    else:
                        parse_errors += 1
                        if parse_errors <= 5:  # Log only first 5 errors
                            logger.debug(f"Text pattern mismatch at line {line_num}: {line[:100]}...")
                            print(f"[DEBUG] Text pattern mismatch at line {line_num}")
            
            logger.info(f"Read {len(logs)} text log entries")
            print(f"[DEBUG] Completed text reading: {len(logs)} entries, {parse_errors} errors")
            if parse_errors > 0:
                logger.debug(f"Total text parse errors: {parse_errors}")
            return pd.DataFrame(logs)
            
        except Exception as e:
            logger.error(f"Error reading text logs: {e}")
            logger.debug("Text log reading failed", exc_info=True)
            print(f"[DEBUG] Text log reading failed: {e}")
            return pd.DataFrame()
    
    def read_logs_parallel(self, limit: int = None, max_workers: int = 4) -> pd.DataFrame:
        """Büyük log dosyalarını paralel oku"""
        # Dosya boyutunu kontrol et
        file_size = os.path.getsize(self.log_path)
        
        logger.debug(f"Starting parallel read - file_size: {file_size/1024/1024:.2f}MB, max_workers: {max_workers}")
        print(f"[DEBUG] Starting parallel read - file_size: {file_size/1024/1024:.2f}MB, max_workers: {max_workers}")
        
        if file_size < 50 * 1024 * 1024:  # 50MB'dan küçükse normal oku
            logger.debug("File size < 50MB, using normal read instead of parallel")
            print("[DEBUG] File size < 50MB, using normal read instead of parallel")
            return self.read_logs(limit)
        
        # Satır sayısını hesapla
        total_lines = self._count_lines()
        logger.debug(f"Total lines in file: {total_lines}")
        print(f"[DEBUG] Total lines in file: {total_lines}")
        
        if limit and limit < total_lines:
            total_lines = limit
        
        # Chunk'lara böl
        chunk_size = total_lines // max_workers
        ranges = [(i * chunk_size, (i + 1) * chunk_size if i != max_workers - 1 else total_lines) 
                  for i in range(max_workers)]
        
        logger.debug(f"Split into {len(ranges)} chunks of ~{chunk_size} lines each")
        print(f"[DEBUG] Split into {len(ranges)} chunks of ~{chunk_size} lines each")
        
        # Paralel okuma
        all_logs = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(self._read_chunk, start, end) for start, end in ranges]
            
            for i, future in enumerate(futures):
                result = future.result()
                logger.debug(f"Chunk {i+1} completed: {len(result)} logs")
                print(f"[DEBUG] Chunk {i+1} completed: {len(result)} logs")
                all_logs.extend(result)
                gc.collect()
        
        # DataFrame oluştur
        if self.format == "json":
            df = pd.DataFrame(all_logs)
        else:
            # Text format için özel işlem
            df = pd.DataFrame(all_logs)
        
        logger.info(f"Parallel read completed: {len(df)} logs")
        print(f"[DEBUG] Parallel read completed: {len(df)} logs")
        return df
    
    def _count_lines(self) -> int:
        """Dosyadaki satır sayısını hızlı hesapla"""
        print(f"[DEBUG] Counting lines in file: {self.log_path}")
        with open(self.log_path, 'rb') as f:
            line_count = sum(chunk.count(b'\n') for chunk in iter(lambda: f.read(self.buffer_size), b''))
        print(f"[DEBUG] Line count: {line_count}")
        return line_count
    
    def _read_chunk(self, start: int, end: int) -> List[Dict]:
        """Belirli bir aralıktaki logları oku"""
        logs = []
        
        logger.debug(f"Reading chunk: lines {start}-{end}")
        print(f"[DEBUG] Reading chunk: lines {start}-{end}")
        
        with open(self.log_path, 'r', encoding=self.encoding) as f:
            for i, line in enumerate(f):
                if i < start:
                    continue
                if i >= end:
                    break
                
                if self.format == "json":
                    try:
                        logs.append(json.loads(line.strip()))
                    except:
                        continue
                else:
                    # Text format parse (yukarıdaki pattern kullanılacak)
                    pass
        
        logger.debug(f"Chunk {start}-{end} completed: {len(logs)} logs")
        print(f"[DEBUG] Chunk {start}-{end} completed: {len(logs)} logs")
        return logs
    
    def get_log_stats(self) -> Dict[str, Any]:
        """Log dosyası istatistiklerini döndür"""
        logger.debug(f"Calculating log stats for: {self.log_path}")
        print(f"[DEBUG] Calculating log stats for: {self.log_path}")
        
        stats = {
            "path": self.log_path,
            "format": self.format,
            "size_mb": os.path.getsize(self.log_path) / (1024 * 1024),
            "exists": os.path.exists(self.log_path),
            "readable": os.access(self.log_path, os.R_OK),
            "line_count": self._count_lines()
        }
        
        logger.debug(f"Basic stats: size={stats['size_mb']:.2f}MB, lines={stats['line_count']}")
        print(f"[DEBUG] Basic stats: size={stats['size_mb']:.2f}MB, lines={stats['line_count']}")
        
        # İlk ve son log zamanı
        try:
            print("[DEBUG] Getting first and last log times...")
            df = self.read_logs(limit=1)
            if not df.empty:
                stats["first_log_time"] = df.iloc[0].get('t', {}).get('$date', 'Unknown')
            
            # Son satır için
            with open(self.log_path, 'rb') as f:
                f.seek(-2048, os.SEEK_END)
                last_lines = f.read().decode(self.encoding, errors='ignore').strip().split('\n')
                if last_lines:
                    if self.format == "json":
                        last_log = json.loads(last_lines[-1])
                        stats["last_log_time"] = last_log.get('t', {}).get('$date', 'Unknown')
                    else:
                        stats["last_log_time"] = "Parse required"
                        
        except Exception as e:
            logger.error(f"Error getting log stats: {e}")
            logger.debug("Log stats calculation failed", exc_info=True)
            print(f"[DEBUG] Error getting log stats: {e}")
        
        logger.debug(f"Log stats completed: {stats}")
        print(f"[DEBUG] Log stats completed")
        return stats

class OpenSearchProxyReader:
    """OpenSearch Proxy API üzerinden MongoDB loglarını okuma"""
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        OpenSearch Proxy Reader başlat
        
        Args:
            config: OpenSearch konfigürasyonu
        """
        import requests
        from requests.auth import HTTPBasicAuth
        
        print("[DEBUG] OpenSearchProxyReader init started")
        # .env'den değerleri al
        self.base_url = os.getenv('OPENSEARCH_URL', 'https://opslog.lcwaikiki.com')
        self.username = os.getenv('OPENSEARCH_USER', 'db_admin')
        self.password = os.getenv('OPENSEARCH_PASS', '')
        print(f"[DEBUG] OpenSearch URL: {self.base_url}, User: {self.username}")
        
        # Proxy API endpoint
        self.proxy_endpoint = f"{self.base_url}/api/console/proxy"
        
        # Index pattern
        self.index_pattern = "db-mongodb-*"
        
        # Session oluştur
        self.session = requests.Session()
        self.session.verify = False  # SSL verification kapalı
        self.session.headers.update({
            'Content-Type': 'application/json',
            'osd-version': '2.6.0',
            'Referer': f'{self.base_url}/app/home',
            'Origin': self.base_url
        })
        
        # SSL uyarılarını sustur
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        logger.info(f"OpenSearch Proxy reader initialized - URL: {self.base_url}")
        print("[DEBUG] OpenSearchProxyReader init completed")
    
    def _login(self) -> bool:
        """OpenSearch'e login ol ve cookie al"""
        try:
            print("[DEBUG] Starting OpenSearch login process")
            login_url = f"{self.base_url}/auth/login"
            login_data = {
                "username": self.username,
                "password": self.password
            }
            
            # Login için özel headers
            login_headers = {
                'Content-Type': 'application/json',
                'osd-version': '2.6.0',
                'Referer': f'{self.base_url}/app/login?',  # ÖNEMLİ: /app/login? olmalı
                'Origin': self.base_url
            }
            
            logger.debug(f"Attempting login to: {login_url}")
            logger.debug(f"Login headers: {login_headers}")
            print(f"[DEBUG] Attempting login to: {login_url}")
            
            # Login request - özel headers kullan
            logger.debug(f"Login body: username={self.username}, password={'*' * len(self.password)}")
            print(f"[DEBUG] Login body: username={self.username}, password={'*' * len(self.password)}")
            response = self.session.post(
                login_url,
                json=login_data,
                headers=login_headers,  # Session headers'ı override et
                timeout=30
            )
            
            # YENİ: Response detaylarını yazdırma
            logger.debug(f"Login response status: {response.status_code}")
            logger.debug(f"Response headers: {dict(response.headers)}")
            print(f"[DEBUG] Login response status: {response.status_code}")
            
            if response.status_code == 200:
                # Cookie otomatik olarak session'a kaydedilir
                cookies = self.session.cookies.get_dict()
                
                # YENİ: Cookie bilgilerini yazdırma
                logger.debug(f"Session cookies: {list(cookies.keys())}")
                print(f"[DEBUG] Session cookies: {list(cookies.keys())}")
                
                if 'security_authentication' in cookies:
                    logger.info("Successfully logged in to OpenSearch")
                    print("[DEBUG] Successfully logged in to OpenSearch")
                    return True
                else:
                    logger.error("Login successful but no security cookie received")
                    logger.debug(f"Available cookies: {cookies}")  # YENİ
                    print("[DEBUG] Login successful but no security cookie received")
                    return False
            else:
                logger.error(f"Login failed: {response.status_code}")
                logger.debug(f"Response body: {response.text[:200]}")  # YENİ
                print(f"[DEBUG] Login failed: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Login error: {e}")
            print(f"[DEBUG] Login error: {e}")
            return False
    
    def _select_tenant(self) -> bool:
        """Login sonrası tenant seçimi yap"""
        try:
            print("[DEBUG] Starting tenant selection")
            tenant_url = f"{self.base_url}/api/v1/multitenancy/tenant"
            tenant_data = {
                "tenant": "LCW",
                "username": self.username
            }
            
            logger.debug(f"Selecting tenant: LCW for user: {self.username}")
            print(f"[DEBUG] Selecting tenant: LCW for user: {self.username}")
            
            # POST request yap
            response = self.session.post(
                tenant_url,
                json=tenant_data,
                timeout=30
            )
            
            logger.debug(f"Tenant selection response: {response.status_code}")
            logger.debug(f"Response text: {response.text}")
            logger.debug(f"Response headers: {dict(response.headers)}")
            print(f"[DEBUG] Tenant selection response: {response.status_code}")
            
            if response.status_code == 200:
                # Response "ok" veya "LCW" (tenant adı) olabilir
                if response.status_code == 200 and (
                    response.text.strip() in ['"ok"', 'ok', 'LCW', '"LCW"'] or 
                    len(response.text.strip()) <= 10  # Kısa tenant adı response'u
                ):
                    logger.info(f"Successfully selected tenant: LCW (Response: {response.text.strip()})")
                    print("[DEBUG] Successfully selected tenant: LCW")
                    
                    # Yeni cookie'yi kontrol et
                    cookies = self.session.cookies.get_dict()
                    logger.debug(f"Cookies after tenant selection: {list(cookies.keys())}")
                    print(f"[DEBUG] Cookies after tenant selection: {list(cookies.keys())}")
                    
                    return True
                else:
                    logger.error(f"Unexpected tenant response: {response.text}")
                    print(f"[DEBUG] Unexpected tenant response: {response.text}")
                    return False
            else:
                logger.error(f"Tenant selection failed: {response.status_code}")
                logger.debug(f"Response body: {response.text[:500]}")
                print(f"[DEBUG] Tenant selection failed: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Tenant selection error: {e}")
            logger.debug("Tenant selection exception details:", exc_info=True)
            print(f"[DEBUG] Tenant selection error: {e}")
            return False
    
    def _make_request(self, path: str, method: str = "GET", body: dict = None) -> dict:
        """Proxy API üzerinden request yap"""
        try:
            print(f"[DEBUG] Making request - path: {path}, method: {method}")
            # URL encode path
            from urllib.parse import quote
            # Sadece özel karakterleri encode et, / karakterini koru
            encoded_path = quote(path, safe='/')
            
            # Query parameters
            params = {
                'path': encoded_path,
                'method': method
            }
            
            # Body varsa JSON string'e çevir
            data = json.dumps(body) if body else "{}"
            
            # Request yap
            response = self.session.post(
                self.proxy_endpoint,
                params=params,
                data=data,
                timeout=30
            )
            
            print(f"[DEBUG] Request response status: {response.status_code}")
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Request failed: {response.status_code} - {response.text}")
                print(f"[DEBUG] Request failed: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"Request error: {e}")
            print(f"[DEBUG] Request error: {e}")
            return None
    
    def connect(self) -> bool:
        """OpenSearch'e bağlantıyı test et"""
        try:
            print("[DEBUG] Starting OpenSearch connection test")
            # 1. Önce login ol
            logger.info("Step 1: Logging in to OpenSearch...")
            print("[DEBUG] Step 1: Logging in to OpenSearch...")
            if not self._login():
                logger.error("Failed to login to OpenSearch")
                print("[DEBUG] Failed to login to OpenSearch")
                return False
            
            # 2. Tenant seç
            logger.info("Step 2: Selecting tenant...")
            print("[DEBUG] Step 2: Selecting tenant...")
            if not self._select_tenant():
                logger.error("Failed to select tenant")
                print("[DEBUG] Failed to select tenant")
                return False
                
            # 3. Test için mevcut tenant bilgisini kontrol et
            logger.info("Step 3: Verifying tenant selection...")
            print("[DEBUG] Step 3: Verifying tenant selection...")
            try:
                tenant_check_response = self.session.get(
                    f"{self.base_url}/api/v1/multitenancy/tenant",
                    timeout=30
                )
                if tenant_check_response.status_code == 200:
                    logger.debug(f"Current tenant: {tenant_check_response.text}")
                    print(f"[DEBUG] Current tenant: {tenant_check_response.text}")
                else:
                    logger.warning(f"Could not verify tenant: {tenant_check_response.status_code}")
                    print(f"[DEBUG] Could not verify tenant: {tenant_check_response.status_code}")
            except Exception as e:
                logger.warning(f"Tenant verification failed: {e}")
                print(f"[DEBUG] Tenant verification failed: {e}")
                
            # 4. Cluster health check
            logger.info("Step 4: Checking cluster health...")
            print("[DEBUG] Step 4: Checking cluster health...")
            result = self._make_request("_cluster/health")
            
            if result:
                logger.info(f"Connected to OpenSearch cluster: {result.get('cluster_name', 'Unknown')}")
                logger.info(f"Cluster status: {result.get('status', 'Unknown')}")
                print(f"[DEBUG] Connected to OpenSearch cluster: {result.get('cluster_name', 'Unknown')}")
                print(f"[DEBUG] Cluster status: {result.get('status', 'Unknown')}")
                return True
            else:
                logger.error("Failed to connect to OpenSearch - cluster health check failed")
                print("[DEBUG] Failed to connect to OpenSearch - cluster health check failed")
                return False
                
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            logger.debug("Connection exception details:", exc_info=True)
            print(f"[DEBUG] Connection test failed: {e}")
            return False
    
    def read_logs(self, limit: int = None, last_hours: int = 24, host_filter: str = None) -> pd.DataFrame:
        """
        OpenSearch'ten MongoDB loglarını oku
        
        Args:
            limit: Maksimum log sayısı
            last_hours: Son N saatteki loglar
            host_filter: Sadece belirli bir host'tan logları filtrele
            
        Returns:
            pd.DataFrame: Log verileri
        """
        try:
            print(f"[DEBUG] Reading logs from OpenSearch - limit: {limit}, last_hours: {last_hours}, host_filter: {host_filter}")
            
            # Limit yoksa scroll API kullan
            if limit is None:
                logger.info("No limit specified, using scroll API for complete data retrieval")
                return self._read_logs_with_scroll(last_hours, host_filter)
            
            # Search query
            query = {
                "size": limit,
                "query": {
                    "bool": {
                        "must": [
                            {
                                "range": {
                                    "@timestamp": {
                                        "gte": f"now-{last_hours}h"
                                    }
                                }
                            }
                        ]
                    }
                },
                "sort": [
                    {"@timestamp": {"order": "desc"}}
                ]
            }
            
            # Eğer host_filter varsa, query'ye ekle
            if host_filter:
                query["query"]["bool"]["must"].append({
                    "term": {
                        "host.name": host_filter
                    }
                })
            
            # Search path
            search_path = f"{self.index_pattern}/_search"
            
            logger.info(f"Searching logs from last {last_hours} hours...")
            print(f"[DEBUG] Searching logs from last {last_hours} hours...")
            result = self._make_request(search_path, "GET", query)
            
            if not result or 'hits' not in result:
                logger.error("No results from OpenSearch")
                print("[DEBUG] No results from OpenSearch")
                return pd.DataFrame()
            
            print(f"[DEBUG] OpenSearch returned {result['hits']['total']['value']} total hits")
            
            # Parse results
            logs = []
            for hit in result['hits']['hits']:
                source = hit['_source']
                
                # MongoDB log message'ı parse et
                if 'message' in source and source['message']:
                    # Message bir array olabilir
                    messages = source['message'] if isinstance(source['message'], list) else [source['message']]
                    
                    for msg in messages:
                        try:
                            # JSON log ise parse et
                            if msg.strip().startswith('{'):
                                log_entry = json.loads(msg.strip())
                                # Host bilgisini ekle
                                if 'host' not in log_entry:
                                    log_entry['host'] = source.get('host', {}).get('name', 'unknown')
                                logs.append(log_entry)
                            else:
                                # Text format log
                                log_entry = {
                                    't': {'$date': source.get('@timestamp')},
                                    'msg': msg,
                                    'host': source.get('host', {}).get('name', 'unknown'),
                                    's': 'I',  # Default severity
                                    'c': 'UNKNOWN'  # Default component
                                }
                                logs.append(log_entry)
                        except Exception as e:
                            logger.debug(f"Failed to parse log message: {e}")
                            continue
            
            logger.info(f"Retrieved {len(logs)} logs from OpenSearch")
            print(f"[DEBUG] Retrieved {len(logs)} logs from OpenSearch")
            
            # DataFrame'e dönüştür
            if logs:
                df = pd.DataFrame(logs)
                logger.debug(f"Created DataFrame with shape: {df.shape}")
                print(f"[DEBUG] Created DataFrame with shape: {df.shape}")
                return df
            else:
                logger.warning("No logs parsed successfully")
                print("[DEBUG] No logs parsed successfully")
                return pd.DataFrame()
                
        except Exception as e:
            logger.error(f"Error reading logs from OpenSearch: {e}")
            print(f"[DEBUG] Error reading logs from OpenSearch: {e}")
            return pd.DataFrame()
    
    def _read_logs_with_scroll(self, last_hours: int, host_filter: str = None) -> pd.DataFrame:
        """Timestamp-based slicing ile büyük veri setlerini oku"""
        try:
            logger.info(f"Starting timestamp-sliced read for last {last_hours} hours")
            print(f"[DEBUG] Starting timestamp-sliced read for last {last_hours} hours, host_filter: {host_filter}")
            
            all_logs = []
            batch_size = 10000  # OpenSearch limiti
            
            # Zaman aralığını hesapla
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=last_hours)
            
            # Zaman dilimlerini belirle
            # Eğer 24 saatten az ise 1 saatlik dilimler, 
            # 24-168 saat arası ise 4 saatlik dilimler,
            # 168 saatten fazla ise 12 saatlik dilimler kullan
            if last_hours <= 24:
                slice_hours = 1
            elif last_hours <= 168:  # 1 hafta
                slice_hours = 4
            else:
                slice_hours = 12
                
            time_slices = []
            current_time = start_time
            
            while current_time < end_time:
                slice_end = min(current_time + timedelta(hours=slice_hours), end_time)
                time_slices.append((current_time, slice_end))
                current_time = slice_end
            
            logger.info(f"Created {len(time_slices)} time slices (each {slice_hours} hours)")
            print(f"[DEBUG] Created {len(time_slices)} time slices (each {slice_hours} hours)")
            
            # İlk önce toplam log sayısını kontrol et
            total_check_query = {
                "size": 0,  # Sadece count için
                "query": {
                    "bool": {
                        "must": [
                            {"range": {"@timestamp": {"gte": f"now-{last_hours}h"}}}
                        ]
                    }
                }
            }
            
            if host_filter:
                total_check_query["query"]["bool"]["must"].append({
                    "term": {"host.name": host_filter}
                })
            
            search_path = f"{self.index_pattern}/_search"
            total_result = self._make_request(search_path, "GET", total_check_query)
            
            if total_result and 'hits' in total_result:
                total_expected = total_result['hits']['total']['value']
                logger.info(f"Total logs to retrieve: {total_expected}")
                print(f"[DEBUG] Total logs to retrieve: {total_expected}")
            else:
                total_expected = 0
            
            # Her zaman dilimi için ayrı sorgular çalıştır
            for slice_idx, (slice_start, slice_end) in enumerate(time_slices):
                logger.info(f"Processing slice {slice_idx+1}/{len(time_slices)}: {slice_start.strftime('%Y-%m-%d %H:%M')} to {slice_end.strftime('%Y-%m-%d %H:%M')}")
                print(f"[DEBUG] Processing time slice {slice_idx+1}/{len(time_slices)}")
                
                # Bu zaman dilimi için tüm logları çek
                slice_logs = self._read_time_slice(slice_start, slice_end, batch_size, host_filter)
                all_logs.extend(slice_logs)
                
                logger.info(f"Slice {slice_idx+1} completed: {len(slice_logs)} logs retrieved")
                print(f"[DEBUG] Slice {slice_idx+1}: {len(slice_logs)} logs")
                
                # Progress update
                if len(all_logs) % 50000 == 0 and len(all_logs) > 0:
                    logger.info(f"Progress: {len(all_logs)} logs retrieved so far ({len(all_logs)/total_expected*100:.1f}% of total)")
                    print(f"[DEBUG] Progress update: {len(all_logs)} logs retrieved")
            
            logger.info(f"Timestamp-sliced read completed. Total logs: {len(all_logs)}")
            print(f"[DEBUG] Total logs retrieved: {len(all_logs)}")
            
            if total_expected > 0:
                retrieval_rate = (len(all_logs) / total_expected) * 100
                logger.info(f"Retrieved {retrieval_rate:.1f}% of available logs")
                print(f"[DEBUG] Retrieved {retrieval_rate:.1f}% of available logs")
            
            if len(all_logs) == 0:
                logger.warning("No logs retrieved. Check time range and filters.")
                print("[DEBUG] No logs retrieved. Check time range and filters.")
                return pd.DataFrame()
            
            final_df = pd.DataFrame(all_logs)
            print(f"[DEBUG] Created final DataFrame with shape: {final_df.shape}")
            logger.debug(f"Created final DataFrame with shape: {final_df.shape}")
            return final_df
            
        except Exception as e:
            logger.error(f"Error in timestamp-sliced read: {e}")
            logger.debug("Timestamp-sliced read error details:", exc_info=True)
            print(f"[DEBUG] Error in timestamp-sliced read: {e}")
            logger.warning("Falling back to regular search due to timestamp-sliced read error")
            print("[DEBUG] Falling back to regular search due to timestamp-sliced read error")
            # Hata durumunda normal okumaya dön
            try:
                return self.read_logs(limit=10000, last_hours=last_hours, host_filter=host_filter)
            except Exception as fallback_error:
                logger.error(f"Fallback to regular search also failed: {fallback_error}")
                print(f"[DEBUG] Fallback to regular search also failed: {fallback_error}")
                return pd.DataFrame()
                
    def _read_time_slice(self, start_time: datetime, end_time: datetime, 
                     batch_size: int, host_filter: str = None) -> List[Dict]:
        """Belirli bir zaman dilimi için logları oku"""
        slice_logs = []
        from_offset = 0
        
        # ISO format timestamp'ler
        start_iso = start_time.isoformat() + "Z"
        end_iso = end_time.isoformat() + "Z"
        
        logger.debug(f"Reading time slice: {start_iso} to {end_iso}")
        
        while True:
            query = {
                "size": batch_size,
                "from": from_offset,
                "query": {
                    "bool": {
                        "must": [
                            {
                                "range": {
                                    "@timestamp": {
                                        "gte": start_iso,
                                        "lt": end_iso
                                    }
                                }
                            }
                        ]
                    }
                },
                "sort": [{"@timestamp": {"order": "asc"}}]
            }
            
            if host_filter:
                query["query"]["bool"]["must"].append({
                    "term": {"host.name": host_filter}
                })
            
            # Search yap
            search_path = f"{self.index_pattern}/_search"
            result = self._make_request(search_path, "GET", query)
            
            if not result or 'hits' not in result:
                logger.debug(f"No results for time slice at offset {from_offset}")
                break
            
            hits = result['hits']['hits']
            if not hits:
                logger.debug(f"No more hits in time slice at offset {from_offset}")
                break
            
            # İlk sorguda toplam sayıyı kontrol et
            if from_offset == 0:
                total_in_slice = result['hits']['total']['value']
                logger.debug(f"Time slice has {total_in_slice} total logs")
                
                # Eğer 10K'dan fazla log varsa uyar
                if total_in_slice > 10000:
                    logger.warning(f"Time slice {start_iso} to {end_iso} has {total_in_slice} logs - will be limited to 10K")
                    print(f"[DEBUG] Warning: Time slice has {total_in_slice} logs, limited to 10K")
            
            # Logları işle
            batch_logs = 0
            for hit in hits:
                source = hit['_source']
                if 'message' in source and source['message']:
                    messages = source['message'] if isinstance(source['message'], list) else [source['message']]
                    
                    for msg in messages:
                        try:
                            if msg.strip().startswith('{'):
                                log_entry = json.loads(msg.strip())
                                if 'host' not in log_entry:
                                    log_entry['host'] = source.get('host', {}).get('name', 'unknown')
                                slice_logs.append(log_entry)
                                batch_logs += 1
                            else:
                                log_entry = {
                                    't': {'$date': source.get('@timestamp')},
                                    'msg': msg,
                                    'host': source.get('host', {}).get('name', 'unknown'),
                                    's': 'I',
                                    'c': 'UNKNOWN'
                                }
                                slice_logs.append(log_entry)
                                batch_logs += 1
                        except Exception as e:
                            logger.debug(f"Error parsing log in time slice: {e}")
                            continue
            
            logger.debug(f"Processed {batch_logs} logs in batch at offset {from_offset}")
            
            # Sonraki batch için offset'i artır
            from_offset += batch_size
            
            # 10K limitine ulaştıysak, bu zaman dilimi için dur
            if from_offset >= 10000:
                if len(hits) == batch_size:
                    logger.warning(f"Reached 10K limit for time slice {start_iso} to {end_iso}")
                break
        
        logger.debug(f"Time slice completed: {len(slice_logs)} logs retrieved")
        return slice_logs
        
    def get_available_hosts(self, last_hours: int = 24) -> List[str]:
        """
        OpenSearch'ten belirli bir zaman aralığındaki MongoDB sunucularını listele
        
        Args:
            last_hours: Son N saatteki aktif sunucular
            
        Returns:
            List[str]: MongoDB sunucu listesi
        """
        try:
            logger.info(f"Getting available MongoDB hosts from last {last_hours} hours")
            print(f"[DEBUG] Getting available MongoDB hosts from last {last_hours} hours")
            
            # Aggregation query - unique host'ları al
            query = {
                "size": 0,  # Sadece aggregation sonuçları
                "query": {
                    "bool": {
                        "must": [
                            {
                                "range": {
                                    "@timestamp": {
                                        "gte": f"now-{last_hours}h"
                                    }
                                }
                            }
                        ]
                    }
                },
                "aggs": {
                    "unique_hosts": {
                        "terms": {
                            "field": "host.name",
                            "size": 100,  # Maksimum 100 host
                            "order": {
                                "_count": "desc"  # En çok log üretenden başla
                            }
                        }
                    }
                }
            }
            
            # Request yap
            search_path = f"{self.index_pattern}/_search"
            result = self._make_request(search_path, "GET", query)
            
            if not result or 'aggregations' not in result:
                logger.error("No aggregation results from OpenSearch")
                print("[DEBUG] No aggregation results from OpenSearch")
                return []
            
            # Host listesini çıkar
            hosts = []
            for bucket in result['aggregations']['unique_hosts']['buckets']:
                host_name = bucket['key']
                doc_count = bucket['doc_count']
                hosts.append(host_name)
                logger.debug(f"Host: {host_name} - Log count: {doc_count}")
            
            logger.info(f"Found {len(hosts)} unique MongoDB hosts")
            print(f"[DEBUG] Found {len(hosts)} unique MongoDB hosts")
            
            # MongoDB sunucularını filtrele (opsiyonel)
            mongodb_hosts = []
            for host in hosts:
                # MongoDB sunucu pattern'leri
                if any(pattern in host.lower() for pattern in ['mongodb', 'mongod', 'mongo']):
                    mongodb_hosts.append(host)
            
            if len(mongodb_hosts) != len(hosts):
                logger.info(f"Filtered to {len(mongodb_hosts)} MongoDB-specific hosts")
                print(f"[DEBUG] Filtered to {len(mongodb_hosts)} MongoDB-specific hosts")
                return sorted(mongodb_hosts)
            
            return sorted(hosts)
            
        except Exception as e:
            logger.error(f"Error getting available hosts: {e}")
            print(f"[DEBUG] Error getting available hosts: {e}")
            return []

    def get_host_log_stats(self, host_name: str, last_hours: int = 24) -> Dict[str, Any]:
        """
        Belirli bir sunucunun log istatistiklerini al
        
        Args:
            host_name: Sunucu adı
            last_hours: Son N saat
            
        Returns:
            Dict: Log istatistikleri
        """
        try:
            logger.debug(f"Getting log stats for host: {host_name}")
            print(f"[DEBUG] Getting log stats for host: {host_name}")
            
            query = {
                "size": 0,
                "query": {
                    "bool": {
                        "must": [
                            {"term": {"host.name": host_name}},
                            {"range": {"@timestamp": {"gte": f"now-{last_hours}h"}}}
                        ]
                    }
                },
                "aggs": {
                    "log_count": {
                        "value_count": {"field": "@timestamp"}
                    },
                    "severity_breakdown": {
                        "terms": {
                            "field": "message",
                            "size": 5
                        }
                    },
                    "time_histogram": {
                        "date_histogram": {
                            "field": "@timestamp",
                            "interval": "1h"
                        }
                    }
                }
            }
            
            result = self._make_request(f"{self.index_pattern}/_search", "GET", query)
            
            if result and 'aggregations' in result:
                stats = {
                    "host_name": host_name,
                    "total_logs": result['aggregations']['log_count']['value'],
                    "time_range": f"last_{last_hours}h",
                    "status": "active"
                }
                
                logger.debug(f"Host {host_name} has {stats['total_logs']} logs")
                print(f"[DEBUG] Host {host_name} has {stats['total_logs']} logs")
                
                return stats
            
            return {"host_name": host_name, "total_logs": 0, "status": "not_found"}
            
        except Exception as e:
            logger.error(f"Error getting host stats: {e}")
            print(f"[DEBUG] Error getting host stats: {e}")
            return {"host_name": host_name, "error": str(e)}

    def _parse_text_message_attributes(self, log_entry: Dict[str, Any]):
        """Text formatındaki log mesajından ek attribute'ları çıkar"""
        msg = log_entry.get('msg', '')
        
        # Örnek: error="connection refused" gibi pattern'leri yakala
        attr_pattern = re.compile(r'(\w+)="([^"]+)"')
        matches = attr_pattern.findall(msg)
        
        if matches:
            for key, value in matches:
                log_entry['attr'][key] = value


def get_available_mongodb_hosts(last_hours: int = 24) -> List[str]:
    """
    OpenSearch'teki mevcut MongoDB sunucularını listele
    
    Args:
        last_hours: Son N saatteki aktif sunucular (varsayılan: 24)
    
    Returns:
        List[str]: MongoDB sunucu listesi
    """
    try:
        logger.debug(f"Getting available MongoDB hosts from OpenSearch (last {last_hours} hours)")
        reader = OpenSearchProxyReader()
        if not reader.connect():
            logger.error("Failed to connect to OpenSearch for host listing")
            return []
        
        # Yeni metodu kullan
        return reader.get_available_hosts(last_hours=last_hours)
        
    except Exception as e:
        logger.error(f"Error getting MongoDB hosts: {e}")
        return []