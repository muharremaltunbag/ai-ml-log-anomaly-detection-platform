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
from datetime import timezone
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

        self.log_path = log_path or self._find_mongod_log()

        self.format = format
        self.encoding = 'utf-8'
        self.buffer_size = 8192
        
        # Format otomatik tespit
        if self.format == "auto":

            self.format = self._detect_log_format()
            print(f"[DEBUG] Detected format: {self.format}")
            
        logger.info(f"Log reader initialized - Path: {self.log_path}, Format: {self.format}")

    
    def _find_mongod_log(self) -> str:
        """MongoDB log dosyasını otomatik bul"""

        possible_paths = [
            # Linux/Production
            Path("/var/log/mongodb/mongod.log"),
            # Windows test ortamı
            Path("C:/Users/muharrem.altunbag/Desktop/Anomaly_Detection/Latest/log dosya/mongod.log"),
            # Vagrant test
            Path("/home/vagrant/mongod.log"),
        ]
        
        for path in possible_paths:

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

                    return "json"
                # Legacy text format kontrolü (timestamp ile başlar)
                elif re.match(r'^\d{4}-\d{2}-\d{2}T', first_line):
                    logger.debug("Detected text format")

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

            return self._read_json_logs(limit, last_hours)
        else:

            return self._read_text_logs(limit, last_hours)
    
    def _read_json_logs(self, limit: int = None, last_hours: int = None) -> pd.DataFrame:
        """JSON formatındaki logları oku"""
        logs = []
        count = 0
        parse_errors = 0
        
        logger.debug(f"Starting JSON log reading - limit: {limit}, last_hours: {last_hours}")

        
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
                        # ✅ YENİ: Log entry'yi zenginleştir (OpenSearch ile tutarlılık)
                        log_entry = enrich_log_entry(log_entry)
                            
                        logs.append(log_entry)
                        count += 1
                        
                        if count % 10000 == 0:
                            logger.debug(f"Processed {count} JSON log entries")

                        
                    except json.JSONDecodeError:
                        parse_errors += 1
                        if parse_errors <= 5:  # Log only first 5 errors
                            logger.debug(f"JSON parse error at line {line_num}: {line[:100]}...")

                        continue
                    except Exception as e:
                        logger.warning(f"Error parsing log line {line_num}: {e}")

                        continue
            
            logger.info(f"Read {len(logs)} JSON log entries")

            if parse_errors > 0:
                logger.debug(f"Total JSON parse errors: {parse_errors}")
            return pd.DataFrame(logs)
            
        except Exception as e:
            logger.error(f"Error reading JSON logs: {e}")
            logger.debug("JSON log reading failed", exc_info=True)

            return pd.DataFrame()
    
    def _read_text_logs(self, limit: int = None, last_hours: int = None) -> pd.DataFrame:
        """Legacy text formatındaki logları oku ve JSON benzeri formata dönüştür"""
        logs = []
        count = 0
        parse_errors = 0
        
        logger.debug(f"Starting text log reading - limit: {limit}, last_hours: {last_hours}")

        
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
                        
                        # ✅ YENİ: Log entry'yi zenginleştir (OpenSearch ile tutarlılık)
                        log_entry = enrich_log_entry(log_entry)
                        
                        logs.append(log_entry)
                        count += 1
                        
                        if count % 10000 == 0:
                            logger.debug(f"Processed {count} text log entries")

                    else:
                        parse_errors += 1
                        if parse_errors <= 5:  # Log only first 5 errors
                            logger.debug(f"Text pattern mismatch at line {line_num}: {line[:100]}...")

            
            logger.info(f"Read {len(logs)} text log entries")

            if parse_errors > 0:
                logger.debug(f"Total text parse errors: {parse_errors}")
            return pd.DataFrame(logs)
            
        except Exception as e:
            logger.error(f"Error reading text logs: {e}")
            logger.debug("Text log reading failed", exc_info=True)

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
                        log_entry = json.loads(line.strip())
                        # ✅ YENİ: Log entry'yi zenginleştir (OpenSearch ile tutarlılık)
                        log_entry = enrich_log_entry(log_entry)
                        logs.append(log_entry)
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
        
def extract_mongodb_message(log_entry):
    """
    MongoDB log mesajından GERÇEK HATA MESAJINI çıkar
    Nested JSON yapılarını parse ederek anlamlı mesaj döndürür
    """
    try:
        # 1. Önce attr.error.errmsg kontrol et (MongoDB hata detayları)
        if 'attr' in log_entry and isinstance(log_entry['attr'], dict):
            attr = log_entry['attr']
            
            # Error mesajı varsa o en detaylı bilgiyi içerir
            if 'error' in attr and isinstance(attr['error'], dict):
                error_obj = attr['error']
                if 'errmsg' in error_obj:
                    return error_obj['errmsg']
                elif 'message' in error_obj:
                    return error_obj['message']
            
            # Command failure durumları
            if 'command' in attr and 'error' in attr:
                command = attr.get('command', {})
                if isinstance(command, dict):
                    cmd_name = command.get('find', command.get('insert', command.get('update', 'unknown')))
                    return f"Command '{cmd_name}' failed: {attr.get('error', '')}"
        
        # 2. Standart msg alanı (kısa açıklama)
        msg = log_entry.get('msg', '')
        # YENİ: AppliedOp filtresini anomaly detection katmanına taştık - buradan kaldırıldı
        if msg and msg not in ['Checking authorization failed']:
            
            # YENİ: Özel MongoDB log türleri için akıllı parse
            if msg == "Slow query" and 'attr' in log_entry:
                return _format_slow_query_message(log_entry)
            elif msg.startswith("CMD: ") and 'attr' in log_entry:
                return _format_command_message(log_entry)
            elif "error" in msg.lower() and 'attr' in log_entry:
                return _format_error_message(log_entry)
            else:
                # Normal mesaj döndür
                return msg
        
        # 3. Raw log'dan JSON parse etmeyi dene (nested durumlar için)
        if 'raw_log' in log_entry and log_entry['raw_log']:
            raw_log = log_entry['raw_log']
            if isinstance(raw_log, str) and raw_log.strip().startswith('{'):
                try:
                    import json
                    parsed = json.loads(raw_log.strip())
                    # Recursive call ile nested JSON'u parse et
                    nested_message = extract_mongodb_message(parsed)
                    if nested_message and nested_message != raw_log:
                        return nested_message
                except json.JSONDecodeError:
                    pass
        
        # 4. Son çare olarak msg alanını döndür
        return msg or 'No detailed message available'
        
    except Exception as e:
        # Hata durumunda basit mesajı döndür
        return log_entry.get('msg', 'Message extraction failed')

def _format_slow_query_message(log_entry):
    """Yavaş sorgu mesajını insan tarafından okunabilir formata çevir"""
    try:
        attr = log_entry.get('attr', {})
        namespace = attr.get('ns', 'unknown')
        duration = attr.get('durationMillis', 0)
        
        # Planın type'ını bul (COLLSCAN, IXSCAN vs.)
        plan_summary = attr.get('planSummary', 'unknown')
        
        # Temel mesaj
        message = f"Slow query on '{namespace}' took {duration}ms"
        
        # Plan detayı ekle
        if plan_summary == 'COLLSCAN':
            message += " - FULL TABLE SCAN detected (needs index)"
        elif plan_summary == 'IXSCAN':
            message += " - using index"
        elif plan_summary != 'unknown':
            message += f" - plan: {plan_summary}"
            
        # Documents examined ekle
        docs_examined = attr.get('docsExamined', 0)
        if docs_examined > 0:
            message += f" (scanned {docs_examined:,} docs)"
            
        return message
        
    except Exception:
        return "Slow query detected (details unavailable)"

def _format_command_message(log_entry):
    """MongoDB komut mesajını formatlayacak"""
    try:
        attr = log_entry.get('attr', {})
        msg = log_entry.get('msg', '')
        
        if 'dropIndexes' in msg:
            namespace = attr.get('namespace', 'unknown')
            indexes = attr.get('indexes', 'unknown')
            return f"Index dropped: {indexes} on collection '{namespace}'"
        elif 'createIndex' in msg:
            namespace = attr.get('namespace', 'unknown')
            return f"Index created on collection '{namespace}'"
        else:
            # Diğer komutlar için genel format
            cmd_type = msg.replace('CMD: ', '')
            namespace = attr.get('namespace', attr.get('ns', 'unknown'))
            return f"Command executed: {cmd_type} on '{namespace}'"
            
    except Exception:
        return log_entry.get('msg', 'Command executed')

def _format_error_message(log_entry):
    """Hata mesajını detaylı formatlayacak"""
    try:
        attr = log_entry.get('attr', {})
        msg = log_entry.get('msg', '')
        
        # Error objesi varsa detayları çıkar
        if 'error' in attr:
            error_obj = attr['error']
            if isinstance(error_obj, dict):
                error_code = error_obj.get('code', 'Unknown')
                error_name = error_obj.get('codeName', 'Unknown')
                error_msg = error_obj.get('errmsg', error_obj.get('message', ''))
                
                return f"Error {error_code} ({error_name}): {error_msg}"
        
        # Fallback - orijinal mesaj
        return msg
        
    except Exception:
        return log_entry.get('msg', 'Error occurred')

def enrich_log_entry(log_entry):
    """
    Log entry'yi zenginleştir - AKILLI MESAJ ÇIKARMA
    """
    # YENİ: extract_mongodb_message ile akıllı mesaj çıkarma
    extracted_message = extract_mongodb_message(log_entry)
    log_entry['full_message'] = extracted_message
    
    # Ayrıca message alanını da set et (API consistency için)
    log_entry['message'] = extracted_message
    
    # Sadece kritik operation details'i sakla (opsiyonel)
    if 'attr' in log_entry and 'CRUD' in log_entry['attr']:
        crud = log_entry['attr']['CRUD']
        log_entry['operation_type'] = crud.get('op')
        log_entry['namespace'] = crud.get('ns')
        log_entry['duration_ms'] = log_entry['attr'].get('durationMillis')
        
        # BÜYÜK ALANLARI TEMİZLE
        if 'o' in crud:
            del crud['o']
        if 'o2' in crud:
            del crud['o2']
            
    return log_entry

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
                timeout=120  # YENİ: Büyük veri setleri için timeout artırıldı
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Request failed: {response.status_code} - {response.text}")
                print(f"[DEBUG] Request failed: {response.status_code}")
                return None
                
        except Exception as e:
            # YENİ: Timeout durumunda retry dene
            if "Read timed out" in str(e) and not hasattr(self, '_retry_count'):
                logger.warning(f"Timeout detected, retrying with longer timeout: {e}")
                print(f"[DEBUG] Timeout detected, retrying: {e}")
                self._retry_count = True
                try:
                    # Retry with longer timeout
                    response = self.session.post(
                        self.proxy_endpoint,
                        params=params,
                        data=data,
                        timeout=300  # 5 dakika
                    )
                    if response.status_code == 200:
                        return response.json()
                finally:
                    delattr(self, '_retry_count')
            
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
    
    def read_logs(self, limit: int = None, last_hours: int = 24, host_filter: Union[str, List[str]] = None,
                  start_time: str = None, end_time: str = None) -> pd.DataFrame:
        """
        OpenSearch'ten MongoDB loglarını oku
        
        Args:
            limit: Maksimum log sayısı
            last_hours: Son N saatteki loglar (start_time/end_time yoksa kullanılır)
            host_filter: Sadece belirli bir host'tan logları filtrele
            start_time: Başlangıç zamanı (ISO format: "2025-09-15T16:09:00Z")
            end_time: Bitiş zamanı (ISO format: "2025-09-15T16:11:00Z")
            
        Returns:
            pd.DataFrame: Log verileri
        """
        try:
            print(f"[DEBUG] Reading logs from OpenSearch - limit: {limit}, last_hours: {last_hours}, host_filter: {host_filter}")
            print(f"[DEBUG] Date range - start_time: {start_time}, end_time: {end_time}")
            
            # Limit yoksa scroll API kullan
            if limit is None:
                logger.info("No limit specified, using scroll API for complete data retrieval")
                return self._read_logs_with_scroll(last_hours, host_filter)
            
            # Search query
            query = {
                "size": limit,
                "query": {
                    "bool": {
                        "must": []
                    }
                },
                "sort": [
                    {"@timestamp": {"order": "desc"}}
                ]
            }

            # YENİ: Spesifik tarih aralığı desteği
            if start_time and end_time:
                # Kesin tarih aralığı verilmişse onu kullan
                print(f"[DEBUG] Using specific date range: {start_time} to {end_time}")
                query["query"]["bool"]["must"].append({
                    "range": {
                        "@timestamp": {
                            "gte": start_time,
                            "lte": end_time
                        }
                    }
                })
            elif start_time:  # Sadece başlangıç verilmişse
                print(f"[DEBUG] Using start_time only: {start_time}")
                query["query"]["bool"]["must"].append({
                    "range": {
                        "@timestamp": {
                            "gte": start_time
                        }
                    }
                })
            elif end_time:  # Sadece bitiş verilmişse
                print(f"[DEBUG] Using end_time only: {end_time}")
                query["query"]["bool"]["must"].append({
                    "range": {
                        "@timestamp": {
                            "lte": end_time
                        }
                    }
                })
            else:
                # Tarih parametresi yoksa last_hours kullan
                print(f"[DEBUG] Using last_hours: {last_hours}")
                query["query"]["bool"]["must"].append({
                    "range": {
                        "@timestamp": {
                            "gte": f"now-{last_hours}h"
                        }
                    }
                })
            
            # Eğer host_filter varsa, query'ye ekle
            if host_filter:
                if isinstance(host_filter, list):
                    # Multiple hosts için "terms" query
                    query["query"]["bool"]["must"].append({
                        "terms": {
                            "host.name": host_filter
                        }
                    })
                    logger.info(f"Filtering for multiple hosts: {host_filter}")
                else:
                    # Tek host için "term" query
                    query["query"]["bool"]["must"].append({
                        "term": {
                            "host.name": host_filter
                        }
                    })
                    logger.info(f"Filtering for single host: {host_filter}")
            
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
                    
                    # Duplicate mesajları filtrele
                    seen_messages = set()
                    unique_messages = []
                    for msg in messages:
                        msg_hash = hash(msg.strip())
                        if msg_hash not in seen_messages:
                            seen_messages.add(msg_hash)
                            unique_messages.append(msg)
                    
                    for msg in unique_messages:
                        try:
                            # JSON log ise parse et
                            if msg.strip().startswith('{'):
                                log_entry = json.loads(msg.strip())
                                # YENİ: Tam OpenSearch mesajını sakla
                                log_entry['raw_log'] = msg.strip()  # Tam JSON string
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
    
    def _read_logs_with_scroll(self, last_hours: int, host_filter: Union[str, List[str]] = None,
                              start_time: str = None, end_time: str = None) -> pd.DataFrame:
        """
        Timestamp-based slicing ile büyük veri setlerini oku.
        Timeout ve 502 hatalarını önlemek için Micro-Slicing (15dk) kullanır.
        """
        try:
            logger.info(f"Starting timestamp-sliced read for last {last_hours} hours")
            print(f"[DEBUG] Starting timestamp-sliced read for last {last_hours} hours, host_filter: {host_filter}")
            
            all_logs = []
            batch_size = 10000  # OpenSearch limiti
            
            # Zaman aralığını hesapla - UTC kullan
            if start_time and end_time:
                from dateutil import parser
                # String ise parse et, zaten datetime ise olduğu gibi kullan
                start_dt = parser.parse(start_time) if isinstance(start_time, str) else start_time
                end_dt = parser.parse(end_time) if isinstance(end_time, str) else end_time
            else:
                end_dt = datetime.now(timezone.utc)
                start_dt = end_dt - timedelta(hours=last_hours)
            
            # Zaman dilimlerini belirle
            # Eğer 24 saatten az ise 30 dakika lik dilimler, 
            # 24-168 saat arası ise 60 dakika lik dilimler,
            # 168 saatten fazla ise 240 dakika lik dilimler kullan
            if last_hours <= 24:
                slice_minutes = 30  # 30 dakika
            elif last_hours <= 168:  # 1 hafta
                # Orta yoğunluk: 1 saatlik dilimler (60 dakika)
                slice_minutes = 60 
            else:
                # Arşiv: 4 saatlik dilimler (240 dakika)
                slice_minutes = 240 

            time_slices = []
            current_time = start_dt
            
            # Zaman dilimlerini oluştur
            while current_time < end_dt:
                # FIX: slice_minutes kullanarak bitiş zamanını hesapla
                slice_end = min(current_time + timedelta(minutes=slice_minutes), end_dt)
                time_slices.append((current_time, slice_end))
                current_time = slice_end

            logger.info(f"Strategy: Micro-Slicing | Created {len(time_slices)} slices (each {slice_minutes} mins)")
            print(f"[DEBUG] Strategy: Micro-Slicing | Created {len(time_slices)} slices (each {slice_minutes} mins)")
            
            # İlk önce toplam log sayısını kontrol et (Progress bar veya loglama için)
            total_check_query = {
                "size": 0,  # Sadece count için
                "query": {
                    "bool": {
                        "must": []
                    }
                }
            }

            # Range filtresi ekle (Genel aralık için)
            # Not: start_dt ve end_dt'nin strftime metodu olup olmadığını kontrol et
            gte_val = start_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z") if hasattr(start_dt, 'strftime') else str(start_dt)
            lt_val = end_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z") if hasattr(end_dt, 'strftime') else str(end_dt)

            time_range_filter = {
                "range": {
                    "@timestamp": {
                        "gte": gte_val,
                        "lt": lt_val
                    }
                }
            }
            total_check_query["query"]["bool"]["must"].append(time_range_filter)

            if host_filter:
                if isinstance(host_filter, list):
                    total_check_query["query"]["bool"]["must"].append({"terms": {"host.name": host_filter}})
                else:
                    total_check_query["query"]["bool"]["must"].append({"term": {"host.name": host_filter}})
            
            search_path = f"{self.index_pattern}/_search"
            total_result = self._make_request(search_path, "GET", total_check_query)
            
            total_expected = 0
            if total_result and 'hits' in total_result:
                total_expected = total_result['hits']['total']['value']
                logger.info(f"Total expected logs to fetch: {total_expected}")
            
            # Her zaman dilimi için ayrı sorgular çalıştır
            for slice_idx, (slice_start, slice_end) in enumerate(time_slices):
                # Bu zaman dilimi için tüm logları çek
                slice_logs = self._read_time_slice(slice_start, slice_end, batch_size, host_filter)
                all_logs.extend(slice_logs)

                # Progress log (Her 5 dilimde bir veya son dilimde)
                if (slice_idx + 1) % 5 == 0 or (slice_idx + 1) == len(time_slices):
                    progress = ((slice_idx + 1) / len(time_slices)) * 100
                    print(f"[DEBUG] Progress: {progress:.1f}% ({len(all_logs)} logs retrieved)")
            
            if len(all_logs) == 0:
                logger.warning("No logs retrieved. Check time range and filters.")
                print("[DEBUG] No logs retrieved. Check time range and filters.")
                return pd.DataFrame()
            
            final_df = pd.DataFrame(all_logs)
            print(f"[DEBUG] Fetch completed. Final DataFrame shape: {final_df.shape}")
            logger.info(f"Fetch completed. Retrieved {len(final_df)} logs.")
            
            return final_df

        except Exception as e:
            logger.error(f"Error in timestamp-sliced read: {e}")
            logger.debug("Timestamp-sliced read error details:", exc_info=True)
            print(f"[DEBUG] Error in timestamp-sliced read: {e}")
            
            # Hata durumunda Fallback: Basit limitli sorgu (Sistemi kilitlememek için)
            logger.warning("Falling back to regular search due to error (Limited to 10k)")
            try:
                return self.read_logs(limit=10000, last_hours=last_hours, host_filter=host_filter)
            except Exception as fallback_error:
                logger.error(f"Fallback failed: {fallback_error}")
                return pd.DataFrame()
                
    def _read_time_slice(self, start_time: datetime, end_time: datetime, 
                     batch_size: int, host_filter: Union[str, List[str]] = None) -> List[Dict]:
        """Belirli bir zaman dilimi için logları oku"""
        slice_logs = []
        
        # ISO format timestamp'ler - UTC'ye çevir
        from datetime import timezone
        start_iso = start_time.replace(tzinfo=timezone.utc).isoformat().replace('+00:00', 'Z')
        end_iso = end_time.replace(tzinfo=timezone.utc).isoformat().replace('+00:00', 'Z')
        
        logger.debug(f"Reading time slice: {start_iso} to {end_iso}")
        
        # Duplicate kontrolü için set
        seen_messages = set()
        
        # YENİ: Erken boş kontrol - gereksiz pagination önleme
        early_check_query = {
            "size": 0,  # Sadece count için
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
            }
        }
        
        if host_filter:
            early_check_query["query"]["bool"]["must"].append({
                "term": {"host.name": host_filter}
            })
        
        # Erken kontrol yap
        # Search yap
        search_path = f"{self.index_pattern}/_search"
        early_result = self._make_request(search_path, "GET", early_check_query)
        
        if early_result and 'hits' in early_result:
            total_available = early_result['hits']['total']['value']
            if total_available == 0:
                logger.debug(f"Time slice {start_iso} to {end_iso} has no data, skipping pagination")
                return []
        
        # YENİ: search_after pagination değişkenleri
        search_after = None
        
        while True:
            query = {
                "size": batch_size,
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
                "sort": [
                    {"@timestamp": {"order": "asc"}},
                    {"_id": {"order": "asc"}}  # YENİ: Unique sort için _id eklendi
                ]
            }
            
            # YENİ: search_after ekleme
            if search_after:
                query["search_after"] = search_after
            
            if host_filter:
                query["query"]["bool"]["must"].append({
                    "term": {"host.name": host_filter}
                })
            
            # Search yap
            search_path = f"{self.index_pattern}/_search"
            result = self._make_request(search_path, "GET", query)
            
            if not result or 'hits' not in result:
                logger.debug(f"No results for time slice")
                break
            
            hits = result['hits']['hits']
            if not hits:
                logger.debug(f"No more hits in time slice")
                break
            
            # İlk sorguda toplam sayıyı kontrol et
            if search_after is None:
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
                        msg_hash = hash(msg.strip())
                        if msg_hash not in seen_messages:
                            seen_messages.add(msg_hash)
                            try:
                                if msg.strip().startswith('{'):
                                    try:
                                        # Dış JSON'u parse et
                                        outer_json = json.loads(msg.strip())
                                        
                                        # Eğer msg alanı varsa ve string ise, onu da parse etmeyi dene
                                        if 'msg' in outer_json and isinstance(outer_json['msg'], str):
                                            if outer_json['msg'].strip().startswith('{'):
                                                try:
                                                    # İç JSON'u parse et
                                                    inner_json = json.loads(outer_json['msg'])
                                                    # İç JSON'u ana JSON olarak kullan
                                                    log_entry = inner_json
                                                    # Orijinal nested yapıyı da sakla
                                                    log_entry['_original_nested'] = True
                                                    log_entry['_outer_wrapper'] = {
                                                        't': outer_json.get('t'),
                                                        's': outer_json.get('s'),
                                                        'c': outer_json.get('c')
                                                    }
                                                except:
                                                    # İç JSON parse edilemezse, dış JSON'u kullan
                                                    log_entry = outer_json
                                            else:
                                                # msg bir JSON değilse, normal kullan
                                                log_entry = outer_json
                                        else:
                                            # msg alanı yoksa veya string değilse
                                            log_entry = outer_json
                                            
                                        # Her durumda tam raw log'u sakla
                                        log_entry['raw_log'] = msg.strip()
                                        
                                    except json.JSONDecodeError:
                                        # JSON parse edilemezse
                                        log_entry = {'message': msg, 'raw_log': msg}
                                    if 'host' not in log_entry:
                                        log_entry['host'] = source.get('host', {}).get('name', 'unknown')
                                    
                                    # YENİ: Log'u zenginleştir
                                    log_entry = enrich_log_entry(log_entry)
                                    
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
            
            logger.debug(f"Processed {batch_logs} logs in batch with search_after")
            
            # YENİ: search_after için son hit'in sort değerlerini al
            if hits:
                last_hit = hits[-1]
                search_after = last_hit.get('sort')
                if search_after:
                    logger.debug(f"Next search_after: {search_after}")
                else:
                    logger.debug("No sort values found, stopping pagination")
                    break
            else:
                logger.debug("No hits returned, stopping pagination")
                break
            
            # YENİ: Batch sayısı kontrolü (güvenlik için, sınırsız pagination)
            if len(hits) < batch_size:
                logger.debug("Received less than batch_size hits, end of data reached")
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
                if any(pattern in host.lower() for pattern in ['mongodb', 'mongod', 'mongo', 'mng']):
                    mongodb_hosts.append(host)
            
            if len(mongodb_hosts) != len(hosts):
                logger.info(f"Filtered to {len(mongodb_hosts)} MongoDB-specific hosts")

                return sorted(mongodb_hosts)
            
            return sorted(hosts)
            
        except Exception as e:
            logger.error(f"Error getting available hosts: {e}")

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
                

                
                return stats
            
            return {"host_name": host_name, "total_logs": 0, "status": "not_found"}
            
        except Exception as e:

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


def load_cluster_mapping() -> Dict[str, Any]:
    """
    cluster_mapping.json dosyasını yükle
    
    Returns:
        Dict: Cluster mapping verisi
    """
    import json
    from pathlib import Path
    
    try:
        mapping_file = Path(__file__).parent.parent.parent / "config" / "cluster_mapping.json"
        
        if mapping_file.exists():
            with open(mapping_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            logger.warning("cluster_mapping.json bulunamadı")
            return {
                "cluster_mappings": {},
                "cluster_display_names": {},
                "standalone_hosts": []
            }
    except Exception as e:
        logger.error(f"Error loading cluster mapping: {e}")
        return {"cluster_mappings": {}, "cluster_display_names": {}, "standalone_hosts": []}


def normalize_hostname(host: str) -> str:
    """
    Hostname'i normalize et (suffix temizleme, uppercase)
    
    Args:
        host: Host adı
        
    Returns:
        str: Normalize edilmiş host adı
    """
    # .lcwaikiki.local, .lcwecommerce.com .lcwecomtr.com gibi suffix'leri temizle
    normalized = host.replace('.lcwaikiki.local', '').replace('.lcwecommerce.com', '').replace('.lcwecomtr.com', '')
    # Uppercase yap (karşılaştırma için)
    normalized = normalized.upper()
    
    return normalized


def get_cluster_for_host(host_name: str) -> Optional[str]:
    """
    Host için cluster adını bul
    
    Args:
        host_name: Sunucu adı
        
    Returns:
        str: Cluster adı veya None
    """
    mapping = load_cluster_mapping()
    
    if mapping and 'cluster_mappings' in mapping:
        # Host'u normalize et
        host_normalized = normalize_hostname(host_name)
        
        # Her cluster'ı kontrol et
        for cluster_name, hosts in mapping['cluster_mappings'].items():
            # Cluster'daki host'ları normalize et ve karşılaştır
            normalized_hosts = [normalize_hostname(h) for h in hosts]
            if host_normalized in normalized_hosts:
                return cluster_name
        
        # Standalone hosts kontrolü
        if 'standalone_hosts' in mapping:
            standalone_normalized = [normalize_hostname(h) for h in mapping['standalone_hosts']]
            if host_normalized in standalone_normalized:
                return "standalone"
    
    return None


def get_available_clusters_with_hosts(last_hours: int = 24) -> Dict[str, Any]:
    """
    OpenSearch'ten cluster bazlı host gruplandırması
    
    Args:
        last_hours: Son N saatteki aktif sunucular
        
    Returns:
        Dict: Cluster ve host bilgileri
    """
    try:
        logger.info(f"Getting clusters with hosts from last {last_hours} hours")
        
        # Tüm host'ları al
        all_hosts = get_available_mongodb_hosts(last_hours)
        
        # Cluster mapping'i yükle
        mapping = load_cluster_mapping()
        
        # Sonuç yapısını hazırla
        result = {
            "clusters": {},
            "standalone": [],
            "unmapped": [],  # Mapping'de olmayan host'lar
            "summary": {
                "total_hosts": len(all_hosts),
                "cluster_count": 0,
                "standalone_count": 0,
                "unmapped_count": 0
            }
        }
        
        # Her host'u ilgili cluster'a ata
        for host in all_hosts:
            cluster = get_cluster_for_host(host)
            
            if cluster:
                if cluster == "standalone":
                    result["standalone"].append(host)
                else:
                    # Cluster'ı result'a ekle (ilk kez görülüyorsa)
                    if cluster not in result["clusters"]:
                        display_name = mapping.get("cluster_display_names", {}).get(cluster, cluster)
                        
                        # Environment tespiti
                        environment = "production"  # Default
                        env_mapping = mapping.get("environment_mapping", {})
                        for env, clusters in env_mapping.items():
                            if cluster in clusters:
                                environment = env
                                break
                        
                        result["clusters"][cluster] = {
                            "cluster_id": cluster,
                            "display_name": display_name,
                            "hosts": [],
                            "environment": environment,
                            "node_count": 0
                        }
                    
                    # Host'u cluster'a ekle
                    result["clusters"][cluster]["hosts"].append(host)
            else:
                # Mapping'de bulunamayan host
                result["unmapped"].append(host)
                logger.warning(f"Host not found in cluster mapping: {host}")
        
        # Node count'ları güncelle ve host'ları sırala
        for cluster_id in result["clusters"]:
            cluster = result["clusters"][cluster_id]
            cluster["node_count"] = len(cluster["hosts"])
            cluster["hosts"].sort()
        
        # Summary'yi güncelle
        result["summary"]["cluster_count"] = len(result["clusters"])
        result["summary"]["standalone_count"] = len(result["standalone"])
        result["summary"]["unmapped_count"] = len(result["unmapped"])
        
        # Host'ları sırala
        result["standalone"].sort()
        result["unmapped"].sort()
        
        logger.info(f"Found {result['summary']['cluster_count']} clusters, "
                   f"{result['summary']['standalone_count']} standalone, "
                   f"{result['summary']['unmapped_count']} unmapped hosts")
        
        return result
        
    except Exception as e:
        logger.error(f"Error getting clusters with hosts: {e}")
        return {
            "clusters": {},
            "standalone": [],
            "unmapped": [],
            "summary": {"total_hosts": 0, "cluster_count": 0, "standalone_count": 0, "unmapped_count": 0}
        }


def get_cluster_hosts(cluster_id: str) -> List[str]:
    """
    Belirli bir cluster'ın host listesini getir
    
    Args:
        cluster_id: Cluster ID
        
    Returns:
        List[str]: Host listesi
    """
    try:
        mapping = load_cluster_mapping()
        
        if mapping and 'cluster_mappings' in mapping:
            hosts = mapping['cluster_mappings'].get(cluster_id, [])
            # OpenSearch'teki gerçek host adlarıyla eşleştir
            available_hosts = get_available_mongodb_hosts(last_hours=24)
            
            # Normalize ederek karşılaştır
            cluster_hosts = []
            for available_host in available_hosts:
                if get_cluster_for_host(available_host) == cluster_id:
                    cluster_hosts.append(available_host)
            
            return sorted(cluster_hosts)
        
        return []
        
    except Exception as e:
        logger.error(f"Error getting cluster hosts for {cluster_id}: {e}")
        return []