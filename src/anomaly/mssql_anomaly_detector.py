# src/anomaly/mssql_anomaly_detector.py
"""
MSSQL Log Anomaly Detection Module
MongoDBAnomalyDetector'dan inheritance - MSSQL'e özgü kurallar

Yapı: MongoDBAnomalyDetector ile aynı, sadece critical rules MSSQL'e uyarlanmış
"""

import logging
import numpy as np
import pandas as pd
from typing import Dict, Any, List
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
    # SEVERITY SCORE OVERRIDE — MSSQL'e özgü
    # Parent (MongoDB) versiyonu: docs_examined, is_collscan, REPL/ACCESS vb.
    # MSSQL versiyonu: login, AG, permission, burst feature'ları
    # Aynı 0-100 skalası ve return formatı korunur.
    # =================================================================

    def calculate_severity_score(self, anomaly_idx: int, anomaly_score: float,
                                 row_features: dict, df_row) -> dict:
        """
        MSSQL anomali için severity skoru hesapla (0-100).
        Parent'ın MongoDB-specific versiyonunu override eder.

        Bölümler (parent ile aynı skala):
          1. Base ML Score        (0-40)
          2. Log Type Criticality (0-20)  — MSSQL logtype bazlı
          3. Critical Features    (0-40)  — MSSQL feature'ları
          4. Temporal Factor      (0-10)
          5. Rule Engine Bonus    (0-20)
        """
        severity_score = 0
        factors = []

        # ── 1. Base ML Score (0-40) ──────────────────────────────
        ml_contribution = abs(anomaly_score) * 40
        severity_score += ml_contribution
        factors.append(f"ML Score: +{ml_contribution:.1f}")

        # ── 2. Log Type Criticality (0-20) ───────────────────────
        logtype_scores = {
            'Error': 18,
            'Logon': 15,       # Login olayları güvenlik açısından önemli
            'Backup': 8,
            'Unknown': 10,
            'Startup': 12,
            'Recovery': 10,
        }
        logtype = df_row.get('logtype', 'Unknown') if hasattr(df_row, 'get') else 'Unknown'
        logtype_score = logtype_scores.get(logtype, 8)
        severity_score += logtype_score
        factors.append(f"LogType ({logtype}): +{logtype_score}")

        # ── 3. Critical MSSQL Features (0-40) ────────────────────
        feature_score = 0

        # 3a. Availability Group hatası — en kritik (üretim etkisi yüksek)
        if row_features.get('is_availability_group_error', 0) == 1:
            feature_score += 35
            factors.append("Availability Group Error: +35")

        # 3b. Database erişim hatası
        elif row_features.get('is_database_access_error', 0) == 1:
            feature_score += 30
            factors.append("Database Access Error: +30")

        # 3c. Failed login + burst → brute force sinyali
        elif (row_features.get('is_failed_login', 0) == 1 and
              row_features.get('login_burst_flag', 0) == 1):
            feature_score += 35
            factors.append("Failed Login Burst (Brute Force Signal): +35")

        # 3d. Permission / denied hatası
        elif row_features.get('is_permission_error', 0) == 1:
            feature_score += 25
            factors.append("Permission Error: +25")

        # 3e. Connection hatası
        elif row_features.get('is_connection_error', 0) == 1:
            feature_score += 22
            factors.append("Connection Error: +22")

        # 3f. Failed login (burst olmadan)
        elif row_features.get('is_failed_login', 0) == 1:
            feature_score += 20
            factors.append("Failed Login: +20")

        # 3g. Extreme burst (login olmasa bile yoğun trafik)
        elif (row_features.get('extreme_burst_flag', 0) == 1 and
              row_features.get('burst_density', 0) > 0.5):
            feature_score += 18
            factors.append("Extreme Burst Density: +18")

        # 3h. Rare IP + non-service account → olağandışı erişim
        elif (row_features.get('is_rare_client_ip', 0) == 1 and
              row_features.get('is_service_account', 0) == 0):
            feature_score += 15
            factors.append("Rare IP (non-service): +15")

        # 3i. Grok parse failure (bilinmeyen log formatı)
        elif row_features.get('is_grok_failure', 0) == 1:
            feature_score += 8
            factors.append("Grok Parse Failure: +8")

        severity_score += feature_score

        # ── 4. Temporal Factor (0-10) ────────────────────────────
        hour = row_features.get('hour_of_day', 0)
        is_night = row_features.get('is_night_login', 0)
        is_weekend = row_features.get('is_weekend', 0)

        if is_night == 1 and is_weekend == 1:
            temporal_score = 10
            factors.append(f"Weekend Night ({hour}:00): +10")
        elif is_night == 1:
            temporal_score = 8
            factors.append(f"Night Hour ({hour}:00): +8")
        elif is_weekend == 1:
            temporal_score = 7
            factors.append(f"Weekend ({hour}:00): +7")
        elif hour in [8, 9, 10, 17, 18, 19]:
            temporal_score = 6
            factors.append(f"Peak Hour ({hour}:00): +6")
        else:
            temporal_score = 3
            factors.append(f"Normal Hour ({hour}:00): +3")

        severity_score += temporal_score

        # ── 5. Rule Engine Bonus (0-20) ──────────────────────────
        if anomaly_score == -1.0:  # Rule override edilmiş
            severity_score += 20
            factors.append("Rule Override: +20")

        # ── Normalize & Level ────────────────────────────────────
        severity_score = min(100, max(0, severity_score))

        if severity_score >= 80:
            level, color = "CRITICAL", "#e74c3c"
        elif severity_score >= 60:
            level, color = "HIGH", "#e67e22"
        elif severity_score >= 40:
            level, color = "MEDIUM", "#f39c12"
        elif severity_score >= 20:
            level, color = "LOW", "#3498db"
        else:
            level, color = "INFO", "#95a5a6"

        return {
            "score": severity_score,
            "level": level,
            "color": color,
            "factors": factors
        }

    # =================================================================
    # ANALYZE ANOMALIES OVERRIDE — MSSQL message & alert uyarlaması
    # Parent (MongoDB): extract_mongodb_message, 'c'/'s' sütunları,
    #   MongoDB is_critical_type kalıpları, MongoDB performance alerts
    # MSSQL: raw_message direkt, 'logtype' sütunu, MSSQL critical kalıpları,
    #   MSSQL security alerts (login, AG, permission)
    # =================================================================

    def analyze_anomalies(self, df: pd.DataFrame, X: pd.DataFrame,
                          predictions: np.ndarray, anomaly_scores: np.ndarray) -> Dict[str, Any]:
        """
        MSSQL anomali analizi — parent'ı çağırıp post-process yapar.

        Post-process adımları:
          1. critical_anomalies'deki mesajları raw_message ile düzeltir
          2. component alanını logtype ile doldurur
          3. MSSQL is_critical_type kalıpları ile kaçırılan anomalileri ekler
          4. MSSQL'e özgü security alerts ekler
        """
        # ── Parent çağrısı (severity zaten MSSQL override üzerinden hesaplanır) ──
        analysis = super().analyze_anomalies(df, X, predictions, anomaly_scores)

        anomaly_mask = predictions == -1

        # ── 1. Message & field düzeltmesi ────────────────────────
        for anomaly in analysis.get('critical_anomalies', []):
            idx = anomaly.get('index', 0)
            if idx < len(df):
                row = df.iloc[idx]
                # raw_message direkt kullan (MSSQL düz metin)
                raw_msg = ''
                if 'raw_message' in df.columns and pd.notna(row.get('raw_message')):
                    raw_msg = str(row['raw_message'])
                elif 'message' in df.columns and pd.notna(row.get('message')):
                    raw_msg = str(row['message'])
                if raw_msg:
                    anomaly['message'] = raw_msg[:1000]

                # Component → logtype (MSSQL'de 'c' sütunu yok)
                anomaly['component'] = row.get('logtype', None)
                # Severity → log_level veya logtype
                anomaly['severity'] = row.get('log_level', row.get('logtype', None))

        # ── 2. MSSQL is_critical_type taraması (kaçırılmış anomalileri ekle) ──
        existing_indices = {a['index'] for a in analysis.get('critical_anomalies', [])}
        anomaly_indices = np.where(anomaly_mask)[0]

        mssql_critical_patterns = [
            'login failed', 'authentication failed', 'not accessible',
            'availability group', 'cannot open database', 'permission denied',
            'access denied', 'brute force', 'sql injection',
        ]

        added_count = 0
        for idx in anomaly_indices:
            if int(idx) in existing_indices:
                continue
            if idx >= len(df):
                continue

            row = df.iloc[idx]
            raw_msg = str(row.get('raw_message', '')) if pd.notna(row.get('raw_message')) else ''
            msg_lower = raw_msg.lower()

            is_mssql_critical = any(p in msg_lower for p in mssql_critical_patterns)
            if not is_mssql_critical:
                continue

            # Feature dict ve severity hesapla
            row_features = X.iloc[idx].to_dict()
            severity_info = self.calculate_severity_score(
                idx, anomaly_scores[idx], row_features, row
            )

            analysis['critical_anomalies'].append({
                "index": int(idx),
                "severity_score": severity_info["score"],
                "severity_level": severity_info["level"],
                "severity_color": severity_info["color"],
                "anomaly_score": float(anomaly_scores[idx]),
                "timestamp": str(row['timestamp']) if 'timestamp' in df.columns else None,
                "severity": row.get('log_level', row.get('logtype', None)),
                "component": row.get('logtype', None),
                "message": raw_msg[:1000],
                "severity_factors": None
            })
            added_count += 1
            if added_count >= 100:  # Ek limit
                break

        # Yeniden severity sıralaması
        analysis['critical_anomalies'].sort(
            key=lambda x: x.get('severity_score', 0), reverse=True
        )
        # Max 500 limit koru
        analysis['critical_anomalies'] = analysis['critical_anomalies'][:500]

        logger.info(f"MSSQL analyze_anomalies post-process: "
                     f"{len(analysis['critical_anomalies'])} critical anomalies "
                     f"(+{added_count} from MSSQL pattern scan)")

        # ── 3. MSSQL Security Alerts ─────────────────────────────
        mssql_alerts = {
            "failed_logins": {"count": 0, "indices": []},
            "availability_group_errors": {"count": 0, "indices": []},
            "database_access_errors": {"count": 0, "indices": []},
            "connection_errors": {"count": 0, "indices": []},
            "permission_errors": {"count": 0, "indices": []},
        }

        alert_features = {
            "failed_logins": "is_failed_login",
            "availability_group_errors": "is_availability_group_error",
            "database_access_errors": "is_database_access_error",
            "connection_errors": "is_connection_error",
            "permission_errors": "is_permission_error",
        }

        for alert_name, feature_col in alert_features.items():
            if feature_col in df.columns:
                mask = (df[feature_col] == 1) & anomaly_mask
                count = int(mask.sum())
                if count > 0:
                    mssql_alerts[alert_name] = {
                        "count": count,
                        "indices": list(np.where(mask)[0][:10])
                    }

        # Parent'ın security_alerts'ini MSSQL versiyonuyla değiştir
        analysis["security_alerts"] = mssql_alerts

        return analysis

    # =================================================================
    # MODEL PATH İZOLASYONU
    # MongoDB modelleri: models/isolation_forest_{hostname}.pkl
    # MSSQL modelleri:   models/mssql_isolation_forest_{hostname}.pkl
    # Bu override'lar sayesinde iki DB tipi asla çakışmaz.
    # =================================================================

    @staticmethod
    def _normalize_server_name(server_name: str) -> str:
        """
        Server name'i normalize et — get_instance ile tutarlı.
        FQDN strip + lowercase + özel karakter temizliği.
        """
        name = server_name or ""
        # FQDN ise sadece hostname al (get_instance ile aynı mantık)
        if '.' in name and name != "global":
            name = name.split('.')[0]
        return name.lower().replace('/', '_')

    def save_model(self, path: str = None, server_name: str = None) -> str:
        """
        MSSQL modeli kaydet — ayrı path prefix ile.
        Tüm ağır iş (joblib, lock, buffer, ensemble) parent'ta kalır.

        Path convention: models/mssql_isolation_forest_{safe_server_name}.pkl
        """
        if path is None:
            if server_name:
                safe_server_name = self._normalize_server_name(server_name)
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
                safe_server_name = self._normalize_server_name(server_name)
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
