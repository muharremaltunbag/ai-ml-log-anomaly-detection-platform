# src/anomaly/mssql_feature_engineer.py
"""
MSSQL Log Feature Engineering Module
Anomali tespiti için MSSQL loglarından feature extraction

Yapı: MongoDBFeatureEngineer ile aynı, MSSQL'e uyarlanmış
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import logging
import re
from typing import Dict, List, Tuple, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class MSSQLFeatureEngineer:
    """MSSQL logları için feature engineering"""

    def __init__(self, config_path: str = "config/mssql_anomaly_config.json"):
        """
        Feature Engineer başlat

        Args:
            config_path: MSSQL konfigürasyon dosyası yolu
        """
        self.config = self._load_config(config_path)
        self.features_config = self.config.get('anomaly_detection', {}).get('features', {})
        self.enabled_features = self.features_config.get('enabled_features', [])
        self.filters = self.features_config.get('filters', {})
        self.thresholds = self.features_config.get('thresholds', {})

        # Model feature schema holder (stabilization için)
        self.model_feature_schema = None

        # Timezone config — OpenSearch @timestamp UTC, MSSQL servers local time
        timezone_config = self.config.get('timezone', {})
        self.utc_offset_hours = timezone_config.get('utc_offset_hours', 3)  # Default: Turkey UTC+3

        # Service account patterns (config'den veya default)
        self.service_account_patterns = self.config.get('message_parsing', {}).get(
            'service_account_patterns',
            ['^APP_', '^SQL\\.', '^SVC_', '^SYSTEM$', '^sa$', '^NT AUTHORITY', '^NT SERVICE']
        )

        # Frequency baseline — IP ve username frekanslarini batchler arasi tutarli yapar
        cache_path = self.config.get('processing', {}).get('cache_path', 'cache/mssql_anomaly_cache')
        self._baseline_path = str(Path(cache_path).parent / 'mssql_frequency_baseline.json')
        self._baseline = self._load_baseline()

        logger.info(f"MSSQLFeatureEngineer initialized with {len(self.enabled_features)} features")

    def _load_config(self, config_path: str) -> Dict:
        """Config dosyasını yükle"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            # Varsayılan config
            return {
                "anomaly_detection": {
                    "features": {
                        "enabled_features": [],
                        "filters": {},
                        "thresholds": {}
                    }
                }
            }

    def _load_baseline(self) -> Dict:
        """Frequency baseline dosyasini yukle (IP/username kumulatif frekanslar)"""
        try:
            with open(self._baseline_path, 'r', encoding='utf-8') as f:
                baseline = json.load(f)
                logger.info(f"Frequency baseline loaded: {baseline.get('total_batches', 0)} batches, "
                            f"{len(baseline.get('ip_counts', {}))} IPs, "
                            f"{len(baseline.get('username_counts', {}))} usernames")
                return baseline
        except FileNotFoundError:
            logger.info("No frequency baseline found — first run, will use batch-relative")
            return {}
        except Exception as e:
            logger.warning(f"Error loading frequency baseline: {e}")
            return {}

    def _save_baseline(self, batch_ip_counts: Dict[str, int],
                       batch_username_counts: Dict[str, int]) -> None:
        """Frequency baseline dosyasini guncelle (kumulatif)"""
        try:
            # Mevcut baseline'i al veya bos dict
            ip_counts = dict(self._baseline.get('ip_counts', {}))
            username_counts = dict(self._baseline.get('username_counts', {}))

            # Batch count'lari ekle (kumulatif)
            for ip, count in batch_ip_counts.items():
                ip_counts[ip] = ip_counts.get(ip, 0) + count
            for user, count in batch_username_counts.items():
                username_counts[user] = username_counts.get(user, 0) + count

            # Kaydet
            baseline = {
                'ip_counts': ip_counts,
                'username_counts': username_counts,
                'total_batches': self._baseline.get('total_batches', 0) + 1,
                'last_updated': datetime.now().isoformat()
            }

            Path(self._baseline_path).parent.mkdir(parents=True, exist_ok=True)
            with open(self._baseline_path, 'w', encoding='utf-8') as f:
                json.dump(baseline, f, indent=2)

            # Runtime baseline'i guncelle
            self._baseline = baseline
            logger.info(f"Frequency baseline saved: {len(ip_counts)} IPs, "
                        f"{len(username_counts)} usernames, batch #{baseline['total_batches']}")
        except Exception as e:
            logger.warning(f"Error saving frequency baseline: {e}")

    def stabilize_features(self, df: pd.DataFrame, expected_schema: Dict[str, Any]) -> pd.DataFrame:
        """
        Modelin eğitimde kullandığı feature schema'ya göre DataFrame'i stabilize eder.
        Eksik kolonları ekler, fazla kolonları yok sayar, sıra ve dtype uyumluluğunu sağlar.

        Args:
            df: Feature DataFrame
            expected_schema: {"names": [...], "count": int}

        Returns:
            Stabilize edilmiş DataFrame
        """
        expected_cols = expected_schema.get("names", [])

        # 1) Eksik kolonları ekle (default = 0.0)
        for col in expected_cols:
            if col not in df.columns:
                df[col] = 0.0

        # 2) Fazla kolonları logla
        extra_cols = set(df.columns) - set(expected_cols)
        if extra_cols:
            logger.warning(f"[Feature Stabilizer] Extra features detected and will be ignored: {extra_cols}")

        # 3) Yalnızca expected schema kolonlarını al ve sırayı düzelt
        df = df[expected_cols]

        # 4) Tüm kolonları float olarak cast et (ML uyumluluğu için)
        df = df.astype(float)

        return df

    def stabilize_features_for_model(self, X: pd.DataFrame, feature_schema: Optional[Dict[str, Any]]) -> pd.DataFrame:
        """
        Model prediction için feature stabilization wrapper.

        Args:
            X: Feature matrix (prediction için)
            feature_schema: Model training'den gelen feature schema

        Returns:
            Stabilize edilmiş feature matrix
        """
        if feature_schema is None or not feature_schema.get("names"):
            logger.debug("No feature schema provided, returning original features")
            return X

        logger.info(f"Stabilizing features for model prediction ({len(feature_schema.get('names', []))} expected features)")

        try:
            self.model_feature_schema = feature_schema
            X_stabilized = self.stabilize_features(X.copy(), feature_schema)
            logger.info(f"Feature stabilization completed: {X.shape} -> {X_stabilized.shape}")
            return X_stabilized
        except Exception as e:
            logger.error(f"Feature stabilization failed: {e}")
            return X

    def create_features(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Tüm MSSQL feature'larını oluştur

        Args:
            df: Raw MSSQL log DataFrame

        Returns:
            Tuple[features_df, enriched_df]: Feature matrisi ve zenginleştirilmiş DataFrame
        """
        logger.info(f"Starting MSSQL feature engineering on {len(df)} logs...")

        # DataFrame kopyası oluştur
        df = df.copy()

        # Raw message'ı koru
        if 'raw_message' not in df.columns and 'message' in df.columns:
            df['raw_message'] = df['message']

        # Login event flag — logtype alanından (non-login logları ayrıştırmak için)
        if 'logtype' in df.columns:
            df['is_login_event'] = (df['logtype'].str.lower() == 'logon').astype(int)
        else:
            df['is_login_event'] = 0
        logger.info(f"[OK] Login events: {df['is_login_event'].sum()} / {len(df)} "
                     f"({df['is_login_event'].mean()*100:.1f}%)")

        # Sırasıyla feature extraction
        df = self.extract_timestamp_features(df)
        df = self.extract_login_features(df)
        df = self.extract_client_features(df)
        df = self.extract_user_features(df)
        df = self.extract_error_features(df)
        df = self.extract_errorlog_features(df)
        df = self.extract_burst_features(df)

        # Frequency baseline güncelle (kümülatif IP/username frekansları)
        try:
            batch_ip = df['client_ip'].value_counts().to_dict() if 'client_ip' in df.columns else {}
            username_col = 'username' if 'username' in df.columns else 'USERNAME'
            batch_user = df[username_col].value_counts().to_dict() if username_col in df.columns else {}
            if batch_ip or batch_user:
                self._save_baseline(batch_ip, batch_user)
        except Exception as e:
            logger.warning(f"Baseline save skipped: {e}")

        # Schema stabilizer
        if hasattr(self, "model_feature_schema") and self.model_feature_schema:
            try:
                logger.info("Applying feature schema stabilizer...")
                df = self.stabilize_features(df, self.model_feature_schema)
            except Exception as e:
                logger.error(f"Feature schema stabilizer failed: {e}")

        # Feature seçimi
        feature_columns = [col for col in self.enabled_features if col in df.columns]
        X = df[feature_columns].copy()

        # Non-numeric kolonları filtrele
        numeric_dtypes = ['int16', 'int32', 'int64', 'float16', 'float32', 'float64', 'bool']
        numeric_columns = X.select_dtypes(include=numeric_dtypes).columns.tolist()
        non_numeric_columns = X.select_dtypes(exclude=numeric_dtypes).columns.tolist()

        if non_numeric_columns:
            logger.warning(f"Removing non-numeric columns from features: {non_numeric_columns}")
            X = X[numeric_columns].copy()

        # NaN değerleri 0 ile doldur
        X = X.fillna(0)

        # Boolean'ları int'e çevir
        for col in X.columns:
            if X[col].dtype == bool:
                X[col] = X[col].astype(int)

        # Zero-variance feature'ları logla ama DROP ETME
        # IsolationForest sabit kolonları otomatik ignore eder (tree split'te bilgi kazancı = 0)
        # Drop etmek run'lar arası feature set tutarsızlığına yol açar → incremental training mismatch
        zero_var_cols = [col for col in X.columns if X[col].nunique() <= 1]
        if zero_var_cols:
            logger.info(f"[Feature Stability] {len(zero_var_cols)} zero-variance features detected (kept for consistency): {zero_var_cols}")

        logger.info(f"Feature engineering completed. Shape: {X.shape}")
        logger.info(f"Features: {list(X.columns)}")

        return X, df

    def extract_timestamp_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Temporal features extraction

        MSSQL için:
        - hour_of_day (local time — UTC + offset)
        - is_weekend (local time)
        - is_business_hours (local time)
        - is_night_login (local time)

        OpenSearch @timestamp is UTC. MSSQL servers in Turkey use UTC+3.
        All temporal features are calculated in LOCAL time to ensure correct
        night/business hour detection.
        """
        try:
            # Timestamp parse
            if 'timestamp' not in df.columns:
                if '@timestamp' in df.columns:
                    df['timestamp'] = pd.to_datetime(df['@timestamp'], errors='coerce', utc=True)
                elif 'logtime' in df.columns:
                    df['timestamp'] = pd.to_datetime(df['logtime'], errors='coerce')

            # Timestamp'e göre sırala
            if 'timestamp' in df.columns:
                df = df.sort_values('timestamp').reset_index(drop=True)

                # UTC → Local time conversion for temporal feature calculation
                # @timestamp is UTC; temporal features (night, business hours, weekend)
                # must reflect local time where the MSSQL servers operate
                offset = pd.Timedelta(hours=self.utc_offset_hours)
                local_timestamp = df['timestamp'] + offset
                logger.info(f"[Timezone] UTC → Local conversion applied: UTC+{self.utc_offset_hours}h")

                # Hour of day (LOCAL time)
                df['hour_of_day'] = local_timestamp.dt.hour

                # Weekend flag (LOCAL time — UTC+offset can shift day boundary)
                df['is_weekend'] = (local_timestamp.dt.dayofweek >= 5).astype(int)

                # Business hours flag (config'den veya default 08:00-18:00)
                business_start = self.thresholds.get('business_hour_start', 8)
                business_end = self.thresholds.get('business_hour_end', 18)
                df['is_business_hours'] = (
                    (df['hour_of_day'] >= business_start) &
                    (df['hour_of_day'] < business_end) &
                    (df['is_weekend'] == 0)
                ).astype(int)

                # Night login flag (config'den veya default 00:00-06:00)
                night_start = self.thresholds.get('night_hour_start', 0)
                night_end = self.thresholds.get('night_hour_end', 6)
                df['is_night_login'] = (
                    (df['hour_of_day'] >= night_start) &
                    (df['hour_of_day'] < night_end)
                ).astype(int)

                # Time since last log (tüm log türleri arası — genel aralık bilgisi)
                df['time_since_last_log'] = df['timestamp'].diff().dt.total_seconds().fillna(0)

                # Time since last LOGIN event (sadece login→login arası fark)
                # Burst detection için daha temiz sinyal: error/system logları arası
                # kısa aralıklar bu feature'ı kirletmez.
                if 'is_login_event' in df.columns:
                    login_mask = df['is_login_event'] == 1
                    if login_mask.any():
                        login_timestamps = df.loc[login_mask, 'timestamp']
                        login_diffs = login_timestamps.diff().dt.total_seconds().fillna(0)
                        df['time_since_last_login'] = 0.0
                        df.loc[login_mask, 'time_since_last_login'] = login_diffs.values
                    else:
                        df['time_since_last_login'] = 0.0
                else:
                    df['time_since_last_login'] = 0.0

            logger.info(f"[OK] Temporal features extracted")
            if 'is_night_login' in df.columns:
                logger.info(f"   Night logins: {df['is_night_login'].sum()} ({df['is_night_login'].mean()*100:.1f}%)")
            if 'is_weekend' in df.columns:
                logger.info(f"   Weekend logins: {df['is_weekend'].sum()} ({df['is_weekend'].mean()*100:.1f}%)")

        except Exception as e:
            logger.error(f"Error in timestamp features: {e}")

        return df

    def extract_login_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Login-based features extraction

        MSSQL için:
        - is_failed_login
        - is_successful_login
        - is_windows_auth
        - is_sql_auth
        """
        try:
            # Login status (from logintype field or parsed from message)
            if 'logintype' in df.columns:
                df['is_failed_login'] = (df['logintype'] == 'failed').astype(int)
                df['is_successful_login'] = (df['logintype'] == 'succeeded').astype(int)
            else:
                # Fallback: message'dan parse
                df['is_failed_login'] = df['raw_message'].str.contains(
                    'Login failed', case=False, na=False
                ).astype(int)
                df['is_successful_login'] = df['raw_message'].str.contains(
                    'Login succeeded', case=False, na=False
                ).astype(int)

            # Auth type (from auth_type field or parsed from message)
            if 'auth_type' in df.columns:
                df['is_windows_auth'] = (df['auth_type'] == 'Windows').astype(int)
                df['is_sql_auth'] = (df['auth_type'] == 'SQL Server').astype(int)
            else:
                # Fallback: message'dan parse
                df['is_windows_auth'] = df['raw_message'].str.contains(
                    'Windows authentication', case=False, na=False
                ).astype(int)
                df['is_sql_auth'] = df['raw_message'].str.contains(
                    'SQL Server authentication', case=False, na=False
                ).astype(int)

            # Grok failure flag
            if 'is_grok_failure' not in df.columns:
                if 'tags' in df.columns:
                    df['is_grok_failure'] = df['tags'].apply(
                        lambda x: 1 if isinstance(x, list) and '_grokparsefailure' in x else 0
                    )
                else:
                    df['is_grok_failure'] = 0

            logger.info(f"[OK] Login features extracted")
            logger.info(f"   Failed logins: {df['is_failed_login'].sum()} ({df['is_failed_login'].mean()*100:.1f}%)")
            logger.info(f"   Successful logins: {df['is_successful_login'].sum()}")
            logger.info(f"   Windows auth: {df['is_windows_auth'].sum()}")
            logger.info(f"   SQL auth: {df['is_sql_auth'].sum()}")

        except Exception as e:
            logger.error(f"Error in login features: {e}")

        return df

    def extract_client_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Client/IP-based features extraction

        MSSQL için:
        - is_local_client
        - client_ip_frequency
        - is_rare_client_ip
        """
        try:
            # Local client check
            if 'client_ip' in df.columns:
                df['is_local_client'] = (
                    (df['client_ip'] == '<local machine>') |
                    (df['client_ip'] == 'localhost') |
                    (df['client_ip'] == '127.0.0.1')
                ).astype(int)

                # IP frequency — baseline varsa kümülatif, yoksa batch-relative
                batch_ip_counts = df['client_ip'].value_counts().to_dict()
                baseline_ip = self._baseline.get('ip_counts', {})
                if baseline_ip:
                    # Kümülatif: baseline + batch
                    merged_ip = {ip: baseline_ip.get(ip, 0) + batch_ip_counts.get(ip, 0)
                                 for ip in set(list(baseline_ip.keys()) + list(batch_ip_counts.keys()))}
                    df['client_ip_frequency'] = df['client_ip'].map(
                        lambda ip: merged_ip.get(ip, 0)
                    ).fillna(0).astype(int)
                    logger.debug(f"IP frequency: baseline-enhanced ({len(baseline_ip)} historical IPs)")
                else:
                    df['client_ip_frequency'] = df['client_ip'].map(batch_ip_counts).fillna(0).astype(int)

                # Rare IP flag
                rare_threshold = self.filters.get('rare_threshold', 100)
                df['is_rare_client_ip'] = (df['client_ip_frequency'] < rare_threshold).astype(int)
            else:
                df['is_local_client'] = 0
                df['client_ip_frequency'] = 0
                df['is_rare_client_ip'] = 0

            logger.info(f"[OK] Client features extracted")
            logger.info(f"   Local clients: {df['is_local_client'].sum()}")
            logger.info(f"   Rare IPs: {df['is_rare_client_ip'].sum()}")

        except Exception as e:
            logger.error(f"Error in client features: {e}")

        return df

    def extract_user_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        User-based features extraction

        MSSQL için:
        - is_service_account
        - is_domain_user
        - username_frequency
        - is_rare_username
        """
        try:
            username_col = 'username' if 'username' in df.columns else 'USERNAME'

            if username_col in df.columns:
                # Service account detection
                service_pattern = '|'.join(self.service_account_patterns)
                df['is_service_account'] = df[username_col].str.match(
                    service_pattern, case=False, na=False
                ).astype(int)

                # Domain user detection (contains backslash)
                df['is_domain_user'] = df[username_col].str.contains(
                    r'\\', na=False, regex=True
                ).astype(int)

                # Username frequency — baseline varsa kümülatif, yoksa batch-relative
                batch_user_counts = df[username_col].value_counts().to_dict()
                baseline_user = self._baseline.get('username_counts', {})
                if baseline_user:
                    # Kümülatif: baseline + batch
                    merged_user = {u: baseline_user.get(u, 0) + batch_user_counts.get(u, 0)
                                   for u in set(list(baseline_user.keys()) + list(batch_user_counts.keys()))}
                    df['username_frequency'] = df[username_col].map(
                        lambda u: merged_user.get(u, 0)
                    ).fillna(0).astype(int)
                    logger.debug(f"Username frequency: baseline-enhanced ({len(baseline_user)} historical users)")
                else:
                    df['username_frequency'] = df[username_col].map(batch_user_counts).fillna(0).astype(int)

                # Rare username flag
                rare_threshold = self.filters.get('rare_threshold', 100)
                df['is_rare_username'] = (df['username_frequency'] < rare_threshold).astype(int)
            else:
                df['is_service_account'] = 0
                df['is_domain_user'] = 0
                df['username_frequency'] = 0
                df['is_rare_username'] = 0

            logger.info(f"[OK] User features extracted")
            logger.info(f"   Service accounts: {df['is_service_account'].sum()}")
            logger.info(f"   Domain users: {df['is_domain_user'].sum()}")
            logger.info(f"   Rare usernames: {df['is_rare_username'].sum()}")

        except Exception as e:
            logger.error(f"Error in user features: {e}")

        return df

    def extract_error_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Error pattern features extraction

        MSSQL için:
        - is_availability_group_error
        - is_database_access_error
        - is_connection_error
        """
        try:
            message_col = 'raw_message' if 'raw_message' in df.columns else 'message'

            if message_col in df.columns:
                # Availability Group errors
                if 'is_availability_group_error' not in df.columns:
                    df['is_availability_group_error'] = df[message_col].str.contains(
                        r'availability group|not accessible for queries|AlwaysOn',
                        case=False, na=False, regex=True
                    ).astype(int)

                # Database access errors
                if 'is_database_access_error' not in df.columns:
                    df['is_database_access_error'] = df[message_col].str.contains(
                        r'Failed to open.*database|database.*not accessible|Cannot open database',
                        case=False, na=False, regex=True
                    ).astype(int)

                # Connection errors
                # "timeout" tek basina cok genis — MSSQL'e ozgu kaliplar kullaniliyor
                df['is_connection_error'] = df[message_col].str.contains(
                    r'connection.*failed|cannot connect|connection timeout|'
                    r'TCP Provider.*error|network error|transport-level error|'
                    r'connection.*forcibly closed|login timeout',
                    case=False, na=False, regex=True
                ).astype(int)

                # Permission errors
                # "permission" ve "denied" tek basina cok genis — MSSQL hata mesaj
                # formatlarina ozgu kaliplar kullaniliyor
                df['is_permission_error'] = df[message_col].str.contains(
                    r'permission was denied|access is denied|not authorized|'
                    r'EXECUTE permission|permission denied|'
                    r'server principal.*cannot access|does not have permission',
                    case=False, na=False, regex=True
                ).astype(int)

            else:
                df['is_availability_group_error'] = 0
                df['is_database_access_error'] = 0
                df['is_connection_error'] = 0
                df['is_permission_error'] = 0

            logger.info(f"[OK] Error features extracted")
            logger.info(f"   Availability Group errors: {df['is_availability_group_error'].sum()}")
            logger.info(f"   Database access errors: {df['is_database_access_error'].sum()}")
            logger.info(f"   Connection errors: {df['is_connection_error'].sum()}")

        except Exception as e:
            logger.error(f"Error in error features: {e}")

        return df

    def extract_errorlog_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        ERRORLOG structured features extraction

        Grok-failed ERRORLOG mesajlarından çıkarılan yapısal bilgiler:
        - error_severity_level: MSSQL error severity (0-25)
        - is_high_severity_error: severity >= 17 (system-level)
        - is_system_error: non-login error event
        - is_fdhost_crash: Full-Text Filter Daemon crash pattern
        """
        try:
            # Error severity level (from parsed error_severity field)
            if 'error_severity' in df.columns:
                df['error_severity_level'] = pd.to_numeric(
                    df['error_severity'], errors='coerce'
                ).fillna(0).astype(int)
            else:
                df['error_severity_level'] = 0

            # High severity error (severity >= 17 = system-level in MSSQL)
            df['is_high_severity_error'] = (df['error_severity_level'] >= 17).astype(int)

            # System error: non-login error event (logtype is Error, Deadlock, Memory, FDHost)
            error_logtypes = {'Error', 'Deadlock', 'Memory', 'FDHost'}
            if 'logtype' in df.columns:
                df['is_system_error'] = df['logtype'].isin(error_logtypes).astype(int)
            else:
                df['is_system_error'] = 0

            # FDHost crash detection
            if 'is_fdhost_event' in df.columns:
                df['is_fdhost_crash'] = df['is_fdhost_event'].astype(int)
            else:
                # Fallback: parse from message
                message_col = 'raw_message' if 'raw_message' in df.columns else 'message'
                if message_col in df.columns:
                    df['is_fdhost_crash'] = df[message_col].str.contains(
                        r'fulltext filter daemon host.*stopped abnormally|FDHost.*stopped',
                        case=False, na=False, regex=True
                    ).astype(int)
                else:
                    df['is_fdhost_crash'] = 0

            logger.info(f"[OK] ERRORLOG features extracted")
            logger.info(f"   High severity errors (>=17): {df['is_high_severity_error'].sum()}")
            logger.info(f"   System errors: {df['is_system_error'].sum()}")
            logger.info(f"   FDHost crashes: {df['is_fdhost_crash'].sum()}")

        except Exception as e:
            logger.error(f"Error in ERRORLOG features: {e}")

        return df

    def extract_burst_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Burst/Pattern features extraction

        MSSQL için:
        - login_burst_flag (yalnızca login event'lerde tetiklenir)
        - extreme_burst_flag (yalnızca login event'lerde tetiklenir)
        - burst_density
        - failed_login_ratio_1h
        """
        try:
            # Login burst detection — yalnızca login event'ler için
            # Non-login loglar (error, system vb.) arasındaki kısa zaman aralığı
            # burst değildir; bu loglar doğası gereği rapid-fire gelir.
            is_login = df.get('is_login_event', pd.Series(0, index=df.index))

            if 'time_since_last_log' in df.columns:
                burst_threshold = self.thresholds.get('login_burst_seconds', 1.0)
                raw_burst = (
                    (df['time_since_last_log'] > 0) &
                    (df['time_since_last_log'] < burst_threshold)
                ).astype(int)
                # Gate: sadece login event'ler için burst flag'i aktif
                df['login_burst_flag'] = (raw_burst & (is_login == 1)).astype(int)

                # Extreme burst flag (aynı saniyede) — login gated
                extreme_threshold = self.thresholds.get('extreme_burst_seconds', 0.1)
                raw_extreme = (df['time_since_last_log'] < extreme_threshold).astype(int)
                df['extreme_burst_flag'] = (raw_extreme & (is_login == 1)).astype(int)

                # Burst density (son 100 log içindeki burst yoğunluğu)
                df['burst_density'] = df['extreme_burst_flag'].rolling(window=100, min_periods=1).mean()
            else:
                df['login_burst_flag'] = 0
                df['extreme_burst_flag'] = 0
                df['burst_density'] = 0

            # Failed login ratio (actual 1-hour time-based rolling)
            if 'is_failed_login' in df.columns and 'timestamp' in df.columns and df['timestamp'].notna().all():
                try:
                    # Time-based rolling: timestamp'i index olarak kullan
                    # df zaten extract_timestamp_features'da timestamp'e göre sıralanmış
                    failed_series = df.set_index('timestamp')['is_failed_login'].sort_index()
                    ratio_result = failed_series.rolling('1h', min_periods=1).mean()
                    count_result = failed_series.rolling('1h', min_periods=1).count()
                    # Orijinal sırayı koru (df zaten timestamp'e göre sıralı)
                    df['failed_login_ratio_1h'] = ratio_result.values
                    df['login_count_1h'] = count_result.values
                    logger.debug("Time-based 1h rolling applied for failed_login_ratio_1h")
                except Exception as e:
                    logger.warning(f"Time-based rolling failed, falling back to count-based: {e}")
                    df['failed_login_ratio_1h'] = df['is_failed_login'].rolling(
                        window=1000, min_periods=1
                    ).mean()
                    df['login_count_1h'] = df['is_failed_login'].rolling(
                        window=1000, min_periods=1
                    ).count()
            elif 'is_failed_login' in df.columns:
                # Timestamp yok — count-based fallback
                df['failed_login_ratio_1h'] = df['is_failed_login'].rolling(
                    window=1000, min_periods=1
                ).mean()
                df['login_count_1h'] = df['is_failed_login'].rolling(
                    window=1000, min_periods=1
                ).count()
            else:
                df['failed_login_ratio_1h'] = 0
                df['login_count_1h'] = 0

            login_count = int(is_login.sum())
            logger.info(f"[OK] Burst features extracted (login-gated, {login_count} login events)")
            logger.info(f"   Login bursts: {df['login_burst_flag'].sum()}")
            logger.info(f"   Extreme bursts: {df['extreme_burst_flag'].sum()}")
            logger.info(f"   Avg failed login ratio: {df['failed_login_ratio_1h'].mean():.3f}")

        except Exception as e:
            logger.error(f"Error in burst features: {e}")

        return df

    def get_feature_summary(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Feature özeti döndür

        Args:
            df: Feature DataFrame

        Returns:
            Feature summary dict
        """
        summary = {
            'total_logs': len(df),
            'features_count': len(self.enabled_features),
            'login_stats': {},
            'client_stats': {},
            'user_stats': {},
            'error_stats': {}
        }

        # Login stats
        if 'is_failed_login' in df.columns:
            summary['login_stats'] = {
                'failed_logins': int(df['is_failed_login'].sum()),
                'successful_logins': int(df.get('is_successful_login', pd.Series([0])).sum()),
                'failed_ratio': float(df['is_failed_login'].mean())
            }

        # Client stats
        if 'client_ip' in df.columns:
            summary['client_stats'] = {
                'unique_ips': int(df['client_ip'].nunique()),
                'local_clients': int(df.get('is_local_client', pd.Series([0])).sum()),
                'rare_ips': int(df.get('is_rare_client_ip', pd.Series([0])).sum())
            }

        # User stats
        username_col = 'username' if 'username' in df.columns else 'USERNAME'
        if username_col in df.columns:
            summary['user_stats'] = {
                'unique_users': int(df[username_col].nunique()),
                'service_accounts': int(df.get('is_service_account', pd.Series([0])).sum()),
                'domain_users': int(df.get('is_domain_user', pd.Series([0])).sum())
            }

        # Error stats
        summary['error_stats'] = {
            'availability_group_errors': int(df.get('is_availability_group_error', pd.Series([0])).sum()),
            'database_access_errors': int(df.get('is_database_access_error', pd.Series([0])).sum()),
            'connection_errors': int(df.get('is_connection_error', pd.Series([0])).sum())
        }

        return summary

    def apply_filters(self, df: pd.DataFrame,
                      X: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Config'deki filtreleri uygula — gürültü loglarını çıkar.

        Filters:
        - exclude_service_account_success: Service account başarılı loginlerini atla

        Args:
            df: Enriched DataFrame
            X: Feature matrix

        Returns:
            Tuple[filtered_df, filtered_X]
        """
        try:
            filter_mask = pd.Series([True] * len(df), index=df.index)

            # Service account successful login filter
            if self.filters.get('exclude_service_account_success', False):
                if 'is_service_account' in df.columns and 'is_successful_login' in df.columns:
                    svc_success = (
                        (df['is_service_account'] == 1) &
                        (df['is_successful_login'] == 1)
                    )
                    filter_mask &= ~svc_success
                    excluded = svc_success.sum()
                    if excluded > 0:
                        logger.info(f"Filtered {excluded} service-account successful login logs")

            df_filtered = df[filter_mask].reset_index(drop=True)
            X_filtered = X[filter_mask].reset_index(drop=True)

            reduction = (1 - len(df_filtered) / len(df)) * 100 if len(df) > 0 else 0
            logger.info(f"MSSQL filters applied. Reduction: {reduction:.1f}% "
                        f"({len(df)} -> {len(df_filtered)})")

            return df_filtered, X_filtered

        except Exception as e:
            logger.error(f"Error applying MSSQL filters: {e}")
            return df, X
