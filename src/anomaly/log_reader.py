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
                return str(path)
        
        # Hiçbiri yoksa varsayılan
        return "/var/log/mongodb/mongod.log"
    
    def _detect_log_format(self) -> str:
        """Log formatını otomatik tespit et"""
        try:
            logger.debug(f"Detecting log format for file: {self.log_path}")
            with open(self.log_path, 'r', encoding=self.encoding) as f:
                first_line = f.readline().strip()
                logger.debug(f"First line sample: {first_line[:100]}...")
                
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
                    return "text"
                    
        except Exception as e:
            logger.error(f"Format detection error: {e}")
            logger.debug(f"Format detection failed for: {self.log_path}", exc_info=True)
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
            with open(self.log_path, 'r', encoding=self.encoding) as f:
                for line_num, line in enumerate(f, 1):
                    if limit and count >= limit:
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
        
        if file_size < 50 * 1024 * 1024:  # 50MB'dan küçükse normal oku
            logger.debug("File size < 50MB, using normal read instead of parallel")
            return self.read_logs(limit)
        
        # Satır sayısını hesapla
        total_lines = self._count_lines()
        logger.debug(f"Total lines in file: {total_lines}")
        
        if limit and limit < total_lines:
            total_lines = limit
        
        # Chunk'lara böl
        chunk_size = total_lines // max_workers
        ranges = [(i * chunk_size, (i + 1) * chunk_size if i != max_workers - 1 else total_lines) 
                  for i in range(max_workers)]
        
        logger.debug(f"Split into {len(ranges)} chunks of ~{chunk_size} lines each")
        
        # Paralel okuma
        all_logs = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(self._read_chunk, start, end) for start, end in ranges]
            
            for i, future in enumerate(futures):
                result = future.result()
                logger.debug(f"Chunk {i+1} completed: {len(result)} logs")
                all_logs.extend(result)
                gc.collect()
        
        # DataFrame oluştur
        if self.format == "json":
            df = pd.DataFrame(all_logs)
        else:
            # Text format için özel işlem
            df = pd.DataFrame(all_logs)
        
        logger.info(f"Parallel read completed: {len(df)} logs")
        return df
    
    def _count_lines(self) -> int:
        """Dosyadaki satır sayısını hızlı hesapla"""
        with open(self.log_path, 'rb') as f:
            return sum(chunk.count(b'\n') for chunk in iter(lambda: f.read(self.buffer_size), b''))
    
    def _read_chunk(self, start: int, end: int) -> List[Dict]:
        """Belirli bir aralıktaki logları oku"""
        logs = []
        
        logger.debug(f"Reading chunk: lines {start}-{end}")
        
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
        return logs
    
    def get_log_stats(self) -> Dict[str, Any]:
        """Log dosyası istatistiklerini döndür"""
        logger.debug(f"Calculating log stats for: {self.log_path}")
        
        stats = {
            "path": self.log_path,
            "format": self.format,
            "size_mb": os.path.getsize(self.log_path) / (1024 * 1024),
            "exists": os.path.exists(self.log_path),
            "readable": os.access(self.log_path, os.R_OK),
            "line_count": self._count_lines()
        }
        
        logger.debug(f"Basic stats: size={stats['size_mb']:.2f}MB, lines={stats['line_count']}")
        
        # İlk ve son log zamanı
        try:
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
        
        logger.debug(f"Log stats completed: {stats}")
        return stats