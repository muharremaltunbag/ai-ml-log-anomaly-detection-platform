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
        """Büyük veri setleri için batch okuma (from/size pagination)"""
        try:
            logger.info(f"Starting batch read for last {last_hours} hours")
            print(f"[DEBUG] Starting batch read for last {last_hours} hours, host_filter: {host_filter}")
            all_logs = []
            batch_size = 10000
            from_offset = 0
            max_results = 100000  # OpenSearch limiti
            
            while from_offset < max_results:
                # Normal search query with from/size
                query = {
                    "size": batch_size,
                    "from": from_offset,  # Pagination için offset
                    "query": {
                        "bool": {
                            "must": [
                                {"range": {"@timestamp": {"gte": f"now-{last_hours}h"}}}
                            ]
                        }
                    },
                    "sort": [{"@timestamp": {"order": "desc"}}]
                }
                
                if host_filter:
                    query["query"]["bool"]["must"].append({
                        "term": {"host.name": host_filter}
                    })
                    print(f"[DEBUG] Added host filter: {host_filter}")
                    logger.debug(f"Added host filter to query: {host_filter}")
                
                # Normal search endpoint (scroll YOK)
                search_path = f"{self.index_pattern}/_search"
                print(f"[DEBUG] Making batch request to: {search_path} with offset: {from_offset}")
                logger.debug(f"Batch query: {json.dumps(query, indent=2)}")
                result = self._make_request(search_path, "GET", query)
                
                if not result or 'hits' not in result:
                    logger.error("No results from query")
                    print("[DEBUG] No results from query - breaking loop")
                    break
                
                hits = result['hits']['hits']
                if not hits:
                    logger.info(f"No more results at offset {from_offset}")
                    print(f"[DEBUG] No more results at offset {from_offset}")
                    break
                    
                # İlk batch'te toplam sayıyı logla
                if from_offset == 0:
                    total_hits = result['hits']['total']['value']
                    logger.info(f"Total hits available: {total_hits}")
                    print(f"[DEBUG] Total hits available: {total_hits}")
                    
                    if total_hits > max_results:
                        logger.warning(f"Total hits ({total_hits}) exceeds limit ({max_results}). Only first {max_results} will be retrieved.")
                        print(f"[DEBUG] Total hits ({total_hits}) exceeds limit ({max_results}). Only first {max_results} will be retrieved.")
                
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
                                    all_logs.append(log_entry)
                                    batch_logs += 1
                                else:
                                    log_entry = {
                                        't': {'$date': source.get('@timestamp')},
                                        'msg': msg,
                                        'host': source.get('host', {}).get('name', 'unknown'),
                                        's': 'I',
                                        'c': 'UNKNOWN'
                                    }
                                    all_logs.append(log_entry)
                                    batch_logs += 1
                            except Exception as e:
                                logger.debug(f"Error parsing log: {e}")
                                print(f"[DEBUG] Error parsing log: {e}")
                                continue
                
                logger.info(f"Batch at offset {from_offset}: processed {batch_logs} logs")
                print(f"[DEBUG] Batch at offset {from_offset}: processed {batch_logs} logs")
                
                # Sonraki batch için offset'i artır
                from_offset += batch_size
                
                # Progress log
                if len(all_logs) % 50000 == 0 and len(all_logs) > 0:
                    logger.info(f"Retrieved {len(all_logs)} logs so far...")
                    print(f"[DEBUG] Progress update: {len(all_logs)} logs retrieved")
            
            logger.info(f"Batch read completed. Total logs retrieved: {len(all_logs)}")
            print(f"[DEBUG] Batch read completed. Total logs retrieved: {len(all_logs)}")
            
            if len(all_logs) == 0:
                logger.warning("No logs were retrieved. Check filters and time range.")
                print("[DEBUG] No logs were retrieved. Check filters and time range.")
            
            final_df = pd.DataFrame(all_logs)
            print(f"[DEBUG] Created final DataFrame with shape: {final_df.shape}")
            logger.debug(f"Created final DataFrame with shape: {final_df.shape}")
            return final_df
            
        except Exception as e:
            logger.error(f"Error in batch read: {e}")
            logger.debug("Batch read error details:", exc_info=True)
            print(f"[DEBUG] Error in batch read: {e}")
            logger.warning("Falling back to regular search due to batch read error")
            print("[DEBUG] Falling back to regular search due to batch read error")
            # Hata durumunda normal okumaya dön
            try:
                return self.read_logs(limit=10000, last_hours=last_hours, host_filter=host_filter)
            except Exception as fallback_error:
                logger.error(f"Fallback to regular search also failed: {fallback_error}")
                print(f"[DEBUG] Fallback to regular search also failed: {fallback_error}")
                return pd.DataFrame()

    def _parse_text_message_attributes(self, log_entry: Dict[str, Any]):
        """Text formatındaki log mesajından ek attribute'ları çıkar"""
        msg = log_entry.get('msg', '')
        
        # Örnek: error="connection refused" gibi pattern'leri yakala
        attr_pattern = re.compile(r'(\w+)="([^"]+)"')
        matches = attr_pattern.findall(msg)
        
        if matches:
            for key, value in matches:
                log_entry['attr'][key] = value


def get_available_mongodb_hosts() -> List[str]:
    """
    OpenSearch'teki mevcut MongoDB sunucularını listele
    
    Returns:
        List[str]: MongoDB sunucu listesi
    """
    try:
        logger.debug("Getting available MongoDB hosts from OpenSearch")
        reader = OpenSearchProxyReader()
        if not reader.connect():
            logger.error("Failed to connect to OpenSearch for host listing")
            return []
            
        # Aggregation query
        query = {
            "size": 0,
            "aggs": {
                "hosts": {
                    "terms": {
                        "field": "host.name",
                        "size": 100
                    }
                }
            }
        }
        
        result = reader._make_request(f"{reader.index_pattern}/_search", "GET", query)
        
        if result and 'aggregations' in result:
            hosts = [bucket['key'] for bucket in result['aggregations']['hosts']['buckets']]
            logger.debug(f"Found {len(hosts)} MongoDB hosts")
            return sorted(hosts)
        
        return []
    except Exception as e:
        logger.error(f"Error getting MongoDB hosts: {e}")
        return []