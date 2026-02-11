# src/anomaly/mssql_anomaly_detector.py
"""
MSSQL Log Anomaly Detection Module
MongoDBAnomalyDetector'dan inheritance - MSSQL'e özgü kurallar

Yapı: MongoDBAnomalyDetector ile aynı, sadece critical rules MSSQL'e uyarlanmış
"""

import logging
from typing import Dict, Any
from pathlib import Path

from .anomaly_detector import MongoDBAnomalyDetector

logger = logging.getLogger(__name__)


class MSSQLAnomalyDetector(MongoDBAnomalyDetector):
    """
    MSSQL logları için anomali tespiti

    MongoDBAnomalyDetector'dan inheritance alır.
    Sadece critical rules MSSQL'e özgü olarak override edilir.
    Model, training, prediction, online learning aynı kalır.
    """

    # Class-level instance cache (MongoDB ile ayrı)
    _mssql_instances = {}

    @classmethod
    def get_instance(cls, server_name: str = "global", config_path: str = "config/mssql_anomaly_config.json"):
        """
        Belirli bir MSSQL sunucusu için bellekteki mevcut modeli döndürür, yoksa oluşturur.

        Args:
            server_name: MSSQL sunucu adı
            config_path: MSSQL config dosyası

        Returns:
            MSSQLAnomalyDetector instance
        """
        # FQDN NORMALIZATION
        raw_name = server_name or "global"

        if '.' in raw_name and raw_name != "global":
            hostname = raw_name.split('.')[0]
            logger.debug(f"FQDN normalized: {raw_name} -> {hostname}")
        else:
            hostname = raw_name

        safe_name = hostname.lower().replace('/', '_')

        # MSSQL için ayrı instance cache kullan
        with cls._instance_lock:
            if safe_name not in cls._mssql_instances:
                logger.info(f"Creating NEW MSSQL detector instance for server: {safe_name}")
                instance = cls(config_path)
                instance.load_model(server_name=safe_name if safe_name != "global" else None)
                cls._mssql_instances[safe_name] = instance
            else:
                logger.debug(f"Using EXISTING MSSQL detector instance for server: {safe_name}")

            return cls._mssql_instances[safe_name]

    def __init__(self, config_path: str = "config/mssql_anomaly_config.json"):
        """
        MSSQL Anomaly Detector başlat

        Args:
            config_path: MSSQL konfigürasyon dosyası yolu
        """
        # Parent class'ı MSSQL config ile başlat
        super().__init__(config_path)

        # MSSQL'e özgü critical rules ile override et
        self.critical_rules = self._initialize_mssql_critical_rules()

        logger.info(f"MSSQLAnomalyDetector initialized with {len(self.critical_rules)} MSSQL-specific rules")

    def _initialize_mssql_critical_rules(self) -> Dict[str, Any]:
        """
        MSSQL'e özgü kritik anomali kurallarını tanımla

        Returns:
            MSSQL rule dictionary
        """

        rules = {
            # =================================================================
            # GÜVENLİK KURALLARI
            # =================================================================

            # Brute Force Attack Detection
            # Aynı IP'den veya kullanıcıdan hızlı ardışık failed login'ler
            'brute_force_attempt': {
                'condition': lambda row: (
                    row.get('is_failed_login', 0) == 1 and
                    row.get('login_burst_flag', 0) == 1
                ),
                'severity': 0.95,
                'description': 'Possible brute force attack - rapid failed login attempts'
            },

            # Credential Stuffing Detection
            # Farklı kullanıcılarla aynı IP'den failed login'ler
            'credential_stuffing': {
                'condition': lambda row: (
                    row.get('is_failed_login', 0) == 1 and
                    row.get('is_rare_client_ip', 0) == 0 and  # Sık görülen IP
                    row.get('is_rare_username', 0) == 1       # Nadir kullanıcı
                ),
                'severity': 0.92,
                'description': 'Possible credential stuffing - failed login from known IP with rare username'
            },

            # After Hours Login (Suspicious)
            # Gece saatlerinde başarılı login (servis hesabı değilse şüpheli)
            'after_hours_login': {
                'condition': lambda row: (
                    row.get('is_failed_login', 0) == 0 and   # Başarılı login
                    row.get('is_night_login', 0) == 1 and    # Gece saati
                    row.get('is_service_account', 0) == 0    # Servis hesabı değil
                ),
                'severity': 0.85,
                'description': 'Successful login during unusual hours (non-service account)'
            },

            # Weekend Login (Suspicious)
            # Hafta sonu başarılı login (servis hesabı değilse dikkat)
            'weekend_login': {
                'condition': lambda row: (
                    row.get('is_failed_login', 0) == 0 and   # Başarılı login
                    row.get('is_weekend', 0) == 1 and        # Hafta sonu
                    row.get('is_service_account', 0) == 0 and  # Servis hesabı değil
                    row.get('is_local_client', 0) == 0       # Uzaktan bağlantı
                ),
                'severity': 0.80,
                'description': 'Successful remote login during weekend (non-service account)'
            },

            # Suspicious Service Account Activity
            # Servis hesabı olağandışı IP'den bağlanıyor
            'suspicious_service_account': {
                'condition': lambda row: (
                    row.get('is_service_account', 0) == 1 and
                    row.get('is_local_client', 0) == 0 and
                    row.get('is_rare_client_ip', 0) == 1
                ),
                'severity': 0.88,
                'description': 'Service account login from unusual/rare IP address'
            },

            # =================================================================
            # SİSTEM SAĞLIĞI KURALLARI
            # =================================================================

            # Availability Group Crisis
            # Always On AG erişim sorunu - kritik
            'availability_group_crisis': {
                'condition': lambda row: row.get('is_availability_group_error', 0) == 1,
                'severity': 0.90,
                'description': 'Availability Group accessibility issue - database not accessible'
            },

            # Database Access Failure
            # Veritabanına erişim hatası
            'database_access_failure': {
                'condition': lambda row: row.get('is_database_access_error', 0) == 1,
                'severity': 0.85,
                'description': 'Failed to access specified database'
            },

            # Connection Error
            # Bağlantı hatası
            'connection_crisis': {
                'condition': lambda row: row.get('is_connection_error', 0) == 1,
                'severity': 0.80,
                'description': 'Connection error detected'
            },

            # =================================================================
            # PATTERN KURALLARI
            # =================================================================

            # Mass Failed Logins
            # Yüksek failed login oranı
            'mass_failed_logins': {
                'condition': lambda row: (
                    row.get('is_failed_login', 0) == 1 and
                    row.get('failed_login_ratio_1h', 0) > 0.3  # %30'dan fazla failed
                ),
                'severity': 0.90,
                'description': 'High ratio of failed logins in time window'
            },

            # Login Burst Storm
            # Aşırı yoğun login trafiği
            'login_burst_storm': {
                'condition': lambda row: (
                    row.get('extreme_burst_flag', 0) == 1 and
                    row.get('burst_density', 0) > 0.5  # Yüksek yoğunluk
                ),
                'severity': 0.85,
                'description': 'Extreme login burst detected - possible automated attack'
            },

            # Grok Parse Failure with Error
            # Parse edilemeyen ama önemli olabilecek log
            'unparsed_critical_log': {
                'condition': lambda row: (
                    row.get('is_grok_failure', 0) == 1 and
                    (row.get('is_availability_group_error', 0) == 1 or
                     row.get('is_database_access_error', 0) == 1)
                ),
                'severity': 0.82,
                'description': 'Critical event in unparsed log entry'
            },

            # New IP for User
            # Kullanıcı yeni bir IP'den bağlanıyor
            'new_ip_for_user': {
                'condition': lambda row: (
                    row.get('is_failed_login', 0) == 0 and   # Başarılı login
                    row.get('is_rare_client_ip', 0) == 1 and  # Nadir IP
                    row.get('is_service_account', 0) == 0     # Normal kullanıcı
                ),
                'severity': 0.75,
                'description': 'User logged in from rare/new IP address'
            }
        }

        return rules

    def get_rule_descriptions(self) -> Dict[str, str]:
        """
        Tüm MSSQL kurallarının açıklamalarını döndür

        Returns:
            {rule_name: description} dictionary
        """
        return {
            name: rule['description']
            for name, rule in self.critical_rules.items()
        }

    def get_rule_stats(self) -> Dict[str, Any]:
        """
        Rule istatistiklerini döndür

        Returns:
            Rule stats dictionary
        """
        return {
            'total_rules': len(self.critical_rules),
            'rule_names': list(self.critical_rules.keys()),
            'severity_distribution': {
                name: rule['severity']
                for name, rule in self.critical_rules.items()
            },
            'override_stats': self.rule_stats if hasattr(self, 'rule_stats') else {}
        }

    # =================================================================
    # MODEL PATH İZOLASYONU
    # MongoDB modelleri: models/isolation_forest_{hostname}.pkl
    # MSSQL modelleri:   models/mssql_isolation_forest_{hostname}.pkl
    # Bu override'lar sayesinde iki DB tipi asla çakışmaz.
    # =================================================================

    def save_model(self, path: str = None, server_name: str = None) -> str:
        """
        MSSQL modeli kaydet — ayrı path prefix ile.
        Tüm ağır iş (joblib, lock, buffer, ensemble) parent'ta kalır.

        Path convention: models/mssql_isolation_forest_{safe_server_name}.pkl
        """
        if path is None:
            if server_name:
                safe_server_name = server_name.replace('.', '_').replace('/', '_')
                path = f'models/mssql_isolation_forest_{safe_server_name}.pkl'
            else:
                path = self.output_config.get('model_path', 'models/mssql_isolation_forest.pkl')
        return super().save_model(path=path, server_name=server_name)

    def load_model(self, path: str = None, server_name: str = None) -> bool:
        """
        MSSQL modeli yükle — ayrı path prefix ile.
        Tüm ağır iş (joblib, lock, buffer, ensemble) parent'ta kalır.

        Path convention: models/mssql_isolation_forest_{safe_server_name}.pkl
        """
        if path is None:
            if server_name:
                safe_server_name = server_name.replace('.', '_').replace('/', '_')
                path = f'models/mssql_isolation_forest_{safe_server_name}.pkl'
            else:
                path = self.output_config.get('model_path', 'models/mssql_isolation_forest.pkl')

            # MSSQL'e özel model yoksa, global MSSQL modeli dene (fallback)
            if not Path(path).exists() and server_name:
                fallback_path = self.output_config.get('model_path', 'models/mssql_isolation_forest.pkl')
                if Path(fallback_path).exists():
                    logger.info(f"Server-specific MSSQL model not found, using global: {fallback_path}")
                    path = fallback_path

        return super().load_model(path=path, server_name=server_name)


# =============================================================================
# MODULE-LEVEL HELPER FUNCTIONS
# =============================================================================

def get_mssql_detector(server_name: str = "global") -> MSSQLAnomalyDetector:
    """
    Module-level function to get MSSQL detector instance

    Args:
        server_name: MSSQL sunucu adı

    Returns:
        MSSQLAnomalyDetector instance
    """
    return MSSQLAnomalyDetector.get_instance(server_name)
