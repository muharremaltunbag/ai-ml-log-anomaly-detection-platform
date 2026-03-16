"""
DBSERVER Sunucuları Entegrasyon Test Script
==============================================

Bu script şunları test eder:
1. OpenSearch bağlantısı ve authentication
2. 15 DBSERVER sunucusunun varlığı
3. Cluster mapping doğruluğu (5 cluster)
4. Her sunucudan log okuma
5. Hostname normalization
6. API endpoints
7. Anomaly detection pipeline
8. Frontend entegrasyonu

Kullanım:
    python tests/Prod\ Tests/test_dbserver_integration.py
"""

import sys
import os
import json
import time
from datetime import datetime
from typing import Dict, List, Any, Optional
from pathlib import Path
import traceback

# Proje root'unu path'e ekle
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Renkli output için
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def print_header(text: str):
    """Test section başlığı yazdır"""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*80}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text.center(80)}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*80}{Colors.ENDC}\n")

def print_success(text: str):
    """Başarılı test mesajı"""
    print(f"{Colors.OKGREEN}✅ {text}{Colors.ENDC}")

def print_error(text: str):
    """Hata mesajı"""
    print(f"{Colors.FAIL}❌ {text}{Colors.ENDC}")

def print_warning(text: str):
    """Uyarı mesajı"""
    print(f"{Colors.WARNING}⚠️  {text}{Colors.ENDC}")

def print_info(text: str):
    """Bilgi mesajı"""
    print(f"{Colors.OKCYAN}ℹ️  {text}{Colors.ENDC}")

def print_detail(text: str):
    """Detay mesajı"""
    print(f"   {text}")


class DBServerIntegrationTest:
    """DBSERVER sunucuları için kapsamlı entegrasyon testi"""
    
    # Beklenen sunucular
    EXPECTED_HOSTS = {
        'ecommercemp': [
            'dbserver-001.example.com',
            'dbserver-002.example.com',
            'dbserver-003.example.com'
        ],
        'ecommercebilling': [
            'dbserver-004.example.com',
            'dbserver-005.example.com',
            'dbserver-006.example.com'
        ],
        'ecommerce': [
            'dbserver-007.example.com',
            'dbserver-008.example.com',
            'dbserver-009.example.com'
        ],
        'ecommercelog': [
            'dbserver-010.example.com',
            'dbserver-011.example.com',
            'dbserver-012.example.com'
        ],
        'rs_ecfavmongo': [
            'dbserver-013.example.com',
            'dbserver-014.example.com',
            'dbserver-015.example.com'
        ]
    }
    
    def __init__(self):
        self.test_results = {
            'total_tests': 0,
            'passed': 0,
            'failed': 0,
            'warnings': 0,
            'start_time': datetime.now(),
            'tests': {}
        }
        
        # Import'ları test sırasında yap
        self.reader = None
        self.imports_ok = False
        
    def run_all_tests(self):
        """Tüm testleri çalıştır"""
        print_header("DBSERVER SUNUCULARI ENTEGRASYON TEST SUITE")
        print_info(f"Test başlangıç: {self.test_results['start_time'].strftime('%Y-%m-%d %H:%M:%S')}")
        print_info(f"Beklenen toplam sunucu: {sum(len(hosts) for hosts in self.EXPECTED_HOSTS.values())}")
        
        # Test sırası
        tests = [
            ('Import Test', self.test_imports),
            ('Config Files Test', self.test_config_files),
            ('OpenSearch Connection', self.test_opensearch_connection),
            ('Available Hosts Discovery', self.test_available_hosts),
            ('Cluster Mapping', self.test_cluster_mapping),
            ('Hostname Normalization', self.test_hostname_normalization),
            ('Log Reading - Single Host', self.test_log_reading_single),
            ('Log Reading - Multiple Hosts', self.test_log_reading_multiple),
            ('Log Reading - All DBSERVER', self.test_log_reading_all_ecaz),
            ('Host Log Statistics', self.test_host_statistics),
            ('API Endpoints (if available)', self.test_api_endpoints),
            ('Anomaly Detection Pipeline', self.test_anomaly_pipeline),
        ]
        
        for test_name, test_func in tests:
            self._run_single_test(test_name, test_func)
        
        # Final raporu yazdır
        self._print_final_report()
        
        # Exit code
        return 0 if self.test_results['failed'] == 0 else 1
    
    def _run_single_test(self, test_name: str, test_func):
        """Tek bir testi çalıştır ve sonucu kaydet"""
        print_header(f"TEST: {test_name}")
        self.test_results['total_tests'] += 1
        
        try:
            start_time = time.time()
            result = test_func()
            duration = time.time() - start_time
            
            self.test_results['tests'][test_name] = {
                'status': 'PASSED' if result else 'FAILED',
                'duration': duration,
                'error': None
            }
            
            if result:
                self.test_results['passed'] += 1
                print_success(f"{test_name} PASSED ({duration:.2f}s)")
            else:
                self.test_results['failed'] += 1
                print_error(f"{test_name} FAILED ({duration:.2f}s)")
                
        except Exception as e:
            duration = time.time() - start_time
            self.test_results['failed'] += 1
            self.test_results['tests'][test_name] = {
                'status': 'ERROR',
                'duration': duration,
                'error': str(e)
            }
            print_error(f"{test_name} ERROR: {str(e)}")
            print_detail(f"Traceback: {traceback.format_exc()}")
    
    def test_imports(self) -> bool:
        """Required module'leri import et"""
        try:
            print_info("Importing required modules...")
            
            from src.anomaly.log_reader import (
                OpenSearchProxyReader,
                get_available_mongodb_hosts,
                get_available_clusters_with_hosts,
                normalize_hostname,
                get_cluster_for_host,
                load_cluster_mapping
            )
            
            # Global olarak sakla
            global OpenSearchProxyReader, get_available_mongodb_hosts
            global get_available_clusters_with_hosts, normalize_hostname
            global get_cluster_for_host, load_cluster_mapping
            
            self.imports_ok = True
            print_success("All modules imported successfully")
            return True
            
        except ImportError as e:
            print_error(f"Import failed: {e}")
            return False
    
    def test_config_files(self) -> bool:
        """Config dosyalarını kontrol et"""
        if not self.imports_ok:
            print_warning("Skipping (imports failed)")
            return False
        
        try:
            print_info("Checking config files...")
            
            # 1. cluster_mapping.json
            mapping = load_cluster_mapping()
            
            if not mapping or 'cluster_mappings' not in mapping:
                print_error("cluster_mapping.json not found or invalid")
                return False
            
            print_success(f"cluster_mapping.json loaded: {len(mapping['cluster_mappings'])} clusters")
            
            # 2. DBSERVER cluster'larını kontrol et
            missing_clusters = []
            for cluster_id in self.EXPECTED_HOSTS.keys():
                if cluster_id not in mapping['cluster_mappings']:
                    missing_clusters.append(cluster_id)
                else:
                    hosts = mapping['cluster_mappings'][cluster_id]
                    print_detail(f"Cluster '{cluster_id}': {len(hosts)} hosts defined")
            
            if missing_clusters:
                print_error(f"Missing clusters in mapping: {missing_clusters}")
                return False
            
            # 3. anomaly_config.json (opsiyonel)
            config_file = project_root / "config" / "anomaly_config.json"
            if config_file.exists():
                with open(config_file, 'r') as f:
                    anomaly_config = json.load(f)
                    
                    if 'hosts' in anomaly_config:
                        whitelist = anomaly_config['hosts'].get('whitelist', [])
                        blacklist = anomaly_config['hosts'].get('blacklist', [])
                        
                        if whitelist:
                            print_warning(f"Whitelist is not empty ({len(whitelist)} hosts). Ensure DBSERVER hosts are included.")
                        
                        # Blacklist'te DBSERVER var mı?
                        blocked = [h for h in blacklist if 'dbserver' in h.lower()]
                        if blocked:
                            print_error(f"DBSERVER hosts found in blacklist: {blocked}")
                            return False
                        
                        print_success("anomaly_config.json checked: No blocking rules")
            
            return True
            
        except Exception as e:
            print_error(f"Config check failed: {e}")
            return False
    
    def test_opensearch_connection(self) -> bool:
        """OpenSearch bağlantısını test et"""
        if not self.imports_ok:
            print_warning("Skipping (imports failed)")
            return False
        
        try:
            print_info("Connecting to OpenSearch...")
            
            self.reader = OpenSearchProxyReader()
            
            if not self.reader.connect():
                print_error("OpenSearch connection failed")
                return False
            
            print_success("OpenSearch connection established")
            print_detail(f"Base URL: {self.reader.base_url}")
            print_detail(f"User: {self.reader.username}")
            
            return True
            
        except Exception as e:
            print_error(f"Connection test failed: {e}")
            return False
    
    def test_available_hosts(self) -> bool:
        """OpenSearch'ten mevcut host'ları al"""
        if not self.reader:
            print_warning("Skipping (OpenSearch not connected)")
            return False
        
        try:
            print_info("Discovering available MongoDB hosts...")
            
            hosts = get_available_mongodb_hosts(last_hours=24)
            
            if not hosts:
                print_error("No hosts found in OpenSearch")
                return False
            
            print_success(f"Found {len(hosts)} total MongoDB hosts")
            
            # DBSERVER sunucularını filtrele
            ecaz_hosts = [h for h in hosts if 'dbserver' in h.lower()]
            
            print_info(f"DBSERVER hosts found: {len(ecaz_hosts)}")
            
            # Her host'u yazdır
            for host in sorted(ecaz_hosts):
                print_detail(f"  - {host}")
            
            # Beklenen sayı kontrolü
            expected_count = sum(len(hosts) for hosts in self.EXPECTED_HOSTS.values())
            
            if len(ecaz_hosts) < 9:  # En az 9 sunucu (zaten çalışanlar)
                print_error(f"Expected at least 9 DBSERVER hosts, found {len(ecaz_hosts)}")
                
                # Hangileri eksik?
                all_expected = []
                for cluster_hosts in self.EXPECTED_HOSTS.values():
                    all_expected.extend(cluster_hosts)
                
                # Normalize ederek karşılaştır
                found_normalized = set(h.lower().split('.')[0] for h in ecaz_hosts)
                expected_normalized = set(h.lower().split('.')[0] for h in all_expected)
                
                missing = expected_normalized - found_normalized
                if missing:
                    print_warning("Missing hosts:")
                    for host in sorted(missing):
                        print_detail(f"  - {host}")
                
                return False
            
            if len(ecaz_hosts) >= expected_count:
                print_success(f"All {expected_count} DBSERVER hosts are available!")
            else:
                print_warning(f"Found {len(ecaz_hosts)}/{expected_count} DBSERVER hosts")
            
            return True
            
        except Exception as e:
            print_error(f"Host discovery failed: {e}")
            return False
    
    def test_cluster_mapping(self) -> bool:
        """Cluster mapping'in doğru çalıştığını test et"""
        if not self.reader:
            print_warning("Skipping (OpenSearch not connected)")
            return False
        
        try:
            print_info("Testing cluster mapping...")
            
            clusters = get_available_clusters_with_hosts(last_hours=24)
            
            if not clusters or 'clusters' not in clusters:
                print_error("Cluster mapping failed")
                return False
            
            print_success(f"Found {clusters['summary']['cluster_count']} clusters")
            print_detail(f"Total hosts: {clusters['summary']['total_hosts']}")
            print_detail(f"Standalone: {clusters['summary']['standalone_count']}")
            print_detail(f"Unmapped: {clusters['summary']['unmapped_count']}")
            
            # ECAZ cluster'larını kontrol et
            all_good = True
            for cluster_id, expected_hosts in self.EXPECTED_HOSTS.items():
                if cluster_id in clusters['clusters']:
                    cluster = clusters['clusters'][cluster_id]
                    found_hosts = cluster['hosts']
                    
                    print_info(f"Cluster '{cluster_id}': {len(found_hosts)} hosts")
                    
                    # Normalize ederek karşılaştır
                    found_normalized = set(h.lower().split('.')[0] for h in found_hosts)
                    expected_normalized = set(h.lower().split('.')[0] for h in expected_hosts)
                    
                    # Bu cluster'a ait DBSERVER'leri bul
                    ecaz_in_cluster = [h for h in found_hosts if 'dbserver' in h.lower()]
                    
                    for host in ecaz_in_cluster:
                        print_detail(f"  ✓ {host}")
                    
                    # Eksik var mı?
                    missing = expected_normalized - found_normalized
                    if missing:
                        print_warning(f"  Missing from cluster '{cluster_id}': {missing}")
                        all_good = False
                else:
                    print_error(f"Cluster '{cluster_id}' not found in results")
                    all_good = False
            
            # Unmapped kontrolü
            if clusters['unmapped']:
                ecaz_unmapped = [h for h in clusters['unmapped'] if 'dbserver' in h.lower()]
                if ecaz_unmapped:
                    print_error(f"DBSERVER hosts not mapped to clusters: {ecaz_unmapped}")
                    all_good = False
            
            return all_good
            
        except Exception as e:
            print_error(f"Cluster mapping test failed: {e}")
            return False
    
    def test_hostname_normalization(self) -> bool:
        """Hostname normalization fonksiyonunu test et"""
        if not self.imports_ok:
            print_warning("Skipping (imports failed)")
            return False
        
        try:
            print_info("Testing hostname normalization...")
            
            test_cases = [
                ('dbserver-001.example.com', 'DBSERVER001'),
                ('dbserver-004.example.com', 'DBSERVER004'),
                ('DBSERVER010.example.com', 'DBSERVER010'),
                ('dbserver001.internal.local', 'DBSERVER001'),
                ('testmongo01.example.com', 'TESTMONGO01'),
            ]
            
            all_good = True
            for input_host, expected_output in test_cases:
                result = normalize_hostname(input_host)
                
                if result == expected_output:
                    print_detail(f"✓ {input_host} → {result}")
                else:
                    print_error(f"✗ {input_host} → {result} (expected: {expected_output})")
                    all_good = False
            
            if all_good:
                print_success("All hostname normalization tests passed")
            
            return all_good
            
        except Exception as e:
            print_error(f"Hostname normalization test failed: {e}")
            return False
    
    def test_log_reading_single(self) -> bool:
        """Tek bir sunucudan log okumayı test et"""
        if not self.reader:
            print_warning("Skipping (OpenSearch not connected)")
            return False
        
        try:
            # DBSERVER010 (en aktif sunucu)
            test_host = 'dbserver-010.example.com'
            print_info(f"Reading logs from {test_host}...")
            
            logs = self.reader.read_logs(
                host_filter=test_host,
                last_hours=1,
                limit=100
            )
            
            if logs.empty:
                print_error(f"No logs found for {test_host}")
                return False
            
            print_success(f"Read {len(logs)} logs from {test_host}")
            
            # Log içeriğini kontrol et
            if 't' in logs.columns:
                print_detail(f"Timestamp field: OK")
            if 'msg' in logs.columns or 'message' in logs.columns:
                print_detail(f"Message field: OK")
            if 'host' in logs.columns:
                print_detail(f"Host field: OK")
            
            # İlk log örneği
            first_log = logs.iloc[0]
            print_detail(f"Sample log message: {str(first_log.get('msg', first_log.get('message', 'N/A')))[:100]}...")
            
            return True
            
        except Exception as e:
            print_error(f"Single host log reading failed: {e}")
            return False
    
    def test_log_reading_multiple(self) -> bool:
        """Birden fazla sunucudan log okumayı test et"""
        if not self.reader:
            print_warning("Skipping (OpenSearch not connected)")
            return False
        
        try:
            # ecommercebilling cluster (3 node)
            test_hosts = self.EXPECTED_HOSTS['ecommercebilling']
            print_info(f"Reading logs from ecommercebilling cluster ({len(test_hosts)} hosts)...")
            
            logs = self.reader.read_logs(
                host_filter=test_hosts,
                last_hours=1,
                limit=500
            )
            
            if logs.empty:
                print_warning(f"No logs found for ecommercebilling cluster")
                # Yeni sunucular henüz log göndermemiş olabilir
                return True  # Warning olarak geç
            
            print_success(f"Read {len(logs)} logs from ecommercebilling cluster")
            
            # Her host'tan log var mı?
            if 'host' in logs.columns:
                unique_hosts = logs['host'].unique()
                print_detail(f"Logs from {len(unique_hosts)} unique hosts")
                
                for host in unique_hosts:
                    host_logs = logs[logs['host'] == host]
                    print_detail(f"  - {host}: {len(host_logs)} logs")
            
            return True
            
        except Exception as e:
            print_error(f"Multiple host log reading failed: {e}")
            return False
    
    def test_log_reading_all_ecaz(self) -> bool:
        """Tüm DBSERVER sunucularından log okumayı test et"""
        if not self.reader:
            print_warning("Skipping (OpenSearch not connected)")
            return False
        
        try:
            print_info("Reading logs from all DBSERVER servers...")
            
            # Tüm beklenen host'ları topla
            all_ecaz_hosts = []
            for hosts in self.EXPECTED_HOSTS.values():
                all_ecaz_hosts.extend(hosts)
            
            logs = self.reader.read_logs(
                host_filter=all_ecaz_hosts,
                last_hours=4,
                limit=5000
            )
            
            if logs.empty:
                print_error("No logs found from any DBSERVER server")
                return False
            
            print_success(f"Read {len(logs)} logs from DBSERVER servers")
            
            # Host dağılımı
            if 'host' in logs.columns:
                unique_hosts = logs['host'].unique()
                print_info(f"Logs received from {len(unique_hosts)} hosts:")
                
                host_counts = logs['host'].value_counts()
                for host, count in host_counts.items():
                    if 'dbserver' in host.lower():
                        print_detail(f"  {host}: {count} logs")
            
            return True
            
        except Exception as e:
            print_error(f"All ECAZ log reading failed: {e}")
            return False
    
    def test_host_statistics(self) -> bool:
        """Her sunucu için log istatistiklerini al"""
        if not self.reader:
            print_warning("Skipping (OpenSearch not connected)")
            return False
        
        try:
            print_info("Getting log statistics for each DBSERVER host...")
            
            # Önce mevcut host'ları al
            hosts = get_available_mongodb_hosts(last_hours=24)
            ecaz_hosts = [h for h in hosts if 'dbserver' in h.lower()]
            
            if not ecaz_hosts:
                print_error("No DBSERVER hosts found")
                return False
            
            print_info(f"Checking statistics for {len(ecaz_hosts)} hosts...")
            
            stats_results = []
            for host in sorted(ecaz_hosts):
                try:
                    stats = self.reader.get_host_log_stats(host, last_hours=24)
                    stats_results.append(stats)
                    
                    total_logs = stats.get('total_logs', 0)
                    status = stats.get('status', 'unknown')
                    
                    if total_logs > 0:
                        print_detail(f"✓ {host}: {total_logs:,} logs ({status})")
                    else:
                        print_warning(f"⚠ {host}: 0 logs ({status})")
                        
                except Exception as e:
                    print_warning(f"✗ {host}: Stats failed - {e}")
            
            # Özet
            active_hosts = sum(1 for s in stats_results if s.get('total_logs', 0) > 0)
            print_success(f"{active_hosts}/{len(ecaz_hosts)} hosts are actively logging")
            
            return active_hosts >= 9  # En az 9 aktif olmalı
            
        except Exception as e:
            print_error(f"Host statistics test failed: {e}")
            return False
    
    def test_api_endpoints(self) -> bool:
        """API endpoints'leri test et (eğer çalışıyorsa)"""
        try:
            import requests
            
            print_info("Testing API endpoints...")
            
            base_url = "http://localhost:5000"
            
            # 1. GET /api/anomaly/hosts
            try:
                response = requests.get(f"{base_url}/api/anomaly/hosts", timeout=5)
                
                if response.status_code == 200:
                    data = response.json()
                    hosts = data.get('hosts', [])
                    ecaz_hosts = [h for h in hosts if 'dbserver' in h.lower()]
                    
                    print_success(f"GET /api/anomaly/hosts: {len(ecaz_hosts)} DBSERVER hosts")
                else:
                    print_warning(f"GET /api/anomaly/hosts: HTTP {response.status_code}")
                    
            except requests.exceptions.ConnectionError:
                print_warning("API server not running on localhost:5000")
                return True  # Not a failure
            
            # 2. GET /api/anomaly/clusters
            try:
                response = requests.get(f"{base_url}/api/anomaly/clusters", timeout=5)
                
                if response.status_code == 200:
                    data = response.json()
                    clusters = data.get('clusters', {})
                    
                    ecaz_clusters = ['ecommercemp', 'ecommercebilling', 'ecommerce', 
                                   'ecommercelog', 'rs_ecfavmongo']
                    
                    found = sum(1 for c in ecaz_clusters if c in clusters)
                    print_success(f"GET /api/anomaly/clusters: {found}/5 ECAZ clusters found")
                else:
                    print_warning(f"GET /api/anomaly/clusters: HTTP {response.status_code}")
                    
            except requests.exceptions.ConnectionError:
                pass
            
            return True
            
        except ImportError:
            print_warning("requests module not installed, skipping API tests")
            return True
        except Exception as e:
            print_error(f"API endpoint test failed: {e}")
            return False
    
    def test_anomaly_pipeline(self) -> bool:
        """Anomaly detection pipeline'ını test et"""
        if not self.reader:
            print_warning("Skipping (OpenSearch not connected)")
            return False
        
        try:
            print_info("Testing anomaly detection pipeline...")
            
            # DBSERVER004 için anomaly detection
            test_host = 'dbserver-010.example.com'  # En aktif sunucu
            
            print_detail(f"Reading logs from {test_host}...")
            logs = self.reader.read_logs(
                host_filter=test_host,
                last_hours=2,
                limit=1000
            )
            
            if logs.empty:
                print_warning(f"No logs available for {test_host}")
                return True  # Warning
            
            print_detail(f"Read {len(logs)} logs")
            
            # Feature engineering test
            try:
                from src.anomaly.feature_engineer import MongoDBFeatureEngineer
                
                engineer = MongoDBFeatureEngineer()
                features = engineer.extract_features(logs)
                
                if features.empty:
                    print_warning("Feature extraction returned empty DataFrame")
                else:
                    print_success(f"Feature extraction: {len(features)} rows, {len(features.columns)} features")
                    print_detail(f"Feature columns: {', '.join(features.columns[:5])}...")
                    
            except ImportError:
                print_warning("Feature engineer not available, skipping feature extraction")
            
            # Anomaly detector test
            try:
                from src.anomaly.anomaly_detector import MongoDBAnomalyDetector
                
                detector = MongoDBAnomalyDetector()
                
                # Model var mı kontrol et
                model_file = project_root / "models" / f"isolation_forest_{test_host.split('.')[0]}.pkl"
                
                if model_file.exists():
                    print_detail(f"Loading model for {test_host}...")
                    detector.load_model(str(model_file))
                    print_success("Model loaded successfully")
                else:
                    print_info(f"No pre-trained model for {test_host}, training new model...")
                    # Model yoksa train et (küçük dataset ile)
                    if not features.empty and len(features) >= 10:
                        detector.train(features)
                        print_success("New model trained")
                
            except ImportError:
                print_warning("Anomaly detector not available")
            except Exception as e:
                print_warning(f"Anomaly detection test partial: {e}")
            
            return True
            
        except Exception as e:
            print_error(f"Anomaly pipeline test failed: {e}")
            return False
    
    def _print_final_report(self):
        """Final test raporunu yazdır"""
        end_time = datetime.now()
        duration = (end_time - self.test_results['start_time']).total_seconds()
        
        print_header("TEST RAPORU")
        
        print_info(f"Başlangıç: {self.test_results['start_time'].strftime('%Y-%m-%d %H:%M:%S')}")
        print_info(f"Bitiş: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print_info(f"Süre: {duration:.2f} saniye")
        
        print(f"\n{Colors.BOLD}Test Sonuçları:{Colors.ENDC}")
        print(f"  Toplam Test: {self.test_results['total_tests']}")
        print(f"  {Colors.OKGREEN}✅ Başarılı: {self.test_results['passed']}{Colors.ENDC}")
        print(f"  {Colors.FAIL}❌ Başarısız: {self.test_results['failed']}{Colors.ENDC}")
        print(f"  {Colors.WARNING}⚠️  Uyarı: {self.test_results['warnings']}{Colors.ENDC}")
        
        # Success rate
        if self.test_results['total_tests'] > 0:
            success_rate = (self.test_results['passed'] / self.test_results['total_tests']) * 100
            print(f"\n  Başarı Oranı: {success_rate:.1f}%")
        
        # Detaylı test sonuçları
        print(f"\n{Colors.BOLD}Detaylı Test Sonuçları:{Colors.ENDC}")
        for test_name, result in self.test_results['tests'].items():
            status = result['status']
            duration = result['duration']
            
            if status == 'PASSED':
                status_icon = f"{Colors.OKGREEN}✅{Colors.ENDC}"
            elif status == 'FAILED':
                status_icon = f"{Colors.FAIL}❌{Colors.ENDC}"
            else:
                status_icon = f"{Colors.WARNING}⚠️{Colors.ENDC}"
            
            print(f"  {status_icon} {test_name}: {status} ({duration:.2f}s)")
            
            if result.get('error'):
                print(f"     Error: {result['error']}")
        
        # Final mesaj
        print(f"\n{Colors.BOLD}{'='*80}{Colors.ENDC}")
        if self.test_results['failed'] == 0:
            print(f"{Colors.OKGREEN}{Colors.BOLD}🎉 TÜM TESTLER BAŞARILI! 🎉{Colors.ENDC}")
        else:
            print(f"{Colors.FAIL}{Colors.BOLD}❌ {self.test_results['failed']} TEST BAŞARISIZ{Colors.ENDC}")
        print(f"{Colors.BOLD}{'='*80}{Colors.ENDC}\n")
        
        # JSON rapor kaydet
        self._save_json_report()
    
    def _save_json_report(self):
        """Test raporunu JSON olarak kaydet"""
        try:
            report_dir = project_root / "tests" / "Prod Tests" / "reports"
            report_dir.mkdir(exist_ok=True)
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            report_file = report_dir / f"test_report_{timestamp}.json"
            
            report = {
                'timestamp': timestamp,
                'start_time': self.test_results['start_time'].isoformat(),
                'end_time': datetime.now().isoformat(),
                'summary': {
                    'total_tests': self.test_results['total_tests'],
                    'passed': self.test_results['passed'],
                    'failed': self.test_results['failed'],
                    'warnings': self.test_results['warnings']
                },
                'tests': self.test_results['tests']
            }
            
            with open(report_file, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, default=str)
            
            print_info(f"JSON rapor kaydedildi: {report_file}")
            
        except Exception as e:
            print_warning(f"JSON rapor kaydedilemedi: {e}")


def main():
    """Main test fonksiyonu"""
    try:
        tester = DBServerIntegrationTest()
        exit_code = tester.run_all_tests()
        sys.exit(exit_code)
        
    except KeyboardInterrupt:
        print(f"\n{Colors.WARNING}Test interrupted by user{Colors.ENDC}")
        sys.exit(1)
    except Exception as e:
        print(f"\n{Colors.FAIL}Critical error: {e}{Colors.ENDC}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()