# src/anomaly/elasticsearch_feature_engineer.py
"""
Elasticsearch Log Feature Engineering Module
Anomali tespiti için Elasticsearch loglarından 25 feature extraction

Yapı: MSSQLFeatureEngineer ile aynı, Elasticsearch'e uyarlanmış
"""

import pandas as pd
import numpy as np
from datetime import datetime
import json
import logging
import re
from typing import Dict, List, Tuple, Any, Optional
from pathlib import Path

from .elasticsearch_log_reader import (
    parse_es_log_line,
    classify_logger,
    detect_host_role,
    GC_PATTERN,
    CIRCUIT_BREAKER_PATTERN,
    OOM_PATTERN,
    DISK_WATERMARK_PATTERN,
    SHARD_FAILURE_PATTERN,
    NODE_EVENT_PATTERN,
    MASTER_ELECTION_PATTERN,
    SLOW_LOG_PATTERN,
    CONNECTION_ERROR_PATTERN,
    EXCEPTION_PATTERN,
    SHARD_RELOCATION_PATTERN,
    HIGH_CPU_PATTERN,
    DEPRECATION_PATTERN,
)

logger = logging.getLogger(__name__)


class ElasticsearchFeatureEngineer:
    """Elasticsearch logları için feature engineering — 25 feature"""

    def __init__(self, config_path: str = "config/elasticsearch_anomaly_config.json"):
        """
        Feature Engineer başlat.

        Args:
            config_path: Elasticsearch konfigürasyon dosyası yolu
        """
        self.config = self._load_config(config_path)
        self.features_config = self.config.get('anomaly_detection', {}).get('features', {})
        self.enabled_features = self.features_config.get('enabled_features', [])
        self.filters = self.features_config.get('filters', {})
        self.thresholds = self.features_config.get('thresholds', {})

        # Model feature schema holder (stabilization için)
        self.model_feature_schema = None

        # Logger frequency cache (rare logger tespiti için)
        self._logger_counts = {}

        logger.info(f"ElasticsearchFeatureEngineer initialized with "
                    f"{len(self.enabled_features)} features")

    def _load_config(self, config_path: str) -> Dict:
        """Config dosyasını yükle"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            return {
                "anomaly_detection": {
                    "features": {
                        "enabled_features": [],
                        "filters": {},
                        "thresholds": {}
                    }
                }
            }

    def stabilize_features(self, df: pd.DataFrame,
                           expected_schema: Dict[str, Any]) -> pd.DataFrame:
        """
        Modelin eğitimde kullandığı feature schema'ya göre DataFrame'i stabilize eder.

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
            logger.warning(f"[Feature Stabilizer] Extra features ignored: {extra_cols}")

        # 3) Expected schema kolonlarını al ve sırayı düzelt
        df = df[expected_cols]

        # 4) Float cast (ML uyumluluğu)
        df = df.astype(float)

        return df

    def stabilize_features_for_model(self, X: pd.DataFrame,
                                     feature_schema: Optional[Dict[str, Any]]) -> pd.DataFrame:
        """
        Model prediction için feature stabilization wrapper.

        Args:
            X: Feature matrix
            feature_schema: Model training'den gelen feature schema

        Returns:
            Stabilize edilmiş feature matrix
        """
        if feature_schema is None or not feature_schema.get("names"):
            logger.debug("No feature schema provided, returning original features")
            return X

        logger.info(f"Stabilizing features for model prediction "
                    f"({len(feature_schema.get('names', []))} expected features)")

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
        Tüm Elasticsearch feature'larını oluştur (25 feature).

        Args:
            df: Raw Elasticsearch log DataFrame (elasticsearch_log_reader çıktısı)

        Returns:
            Tuple[features_df, enriched_df]: Feature matrisi ve zenginleştirilmiş DataFrame
        """
        logger.info(f"Starting Elasticsearch feature engineering on {len(df)} logs...")

        # DataFrame kopyası
        df = df.copy()

        # Raw message'ı koru
        if 'raw_message' not in df.columns and 'message' in df.columns:
            df['raw_message'] = df['message']

        # Sırasıyla feature extraction
        df = self.extract_timestamp_features(df)
        df = self.extract_severity_features(df)
        df = self.extract_logger_features(df)
        df = self.extract_error_pattern_features(df)
        df = self.extract_performance_features(df)
        df = self.extract_cluster_health_features(df)
        df = self.extract_burst_features(df)

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

        # NaN → 0
        X = X.fillna(0)

        # Boolean → int
        for col in X.columns:
            if X[col].dtype == bool:
                X[col] = X[col].astype(int)

        # Zero-variance feature'ları logla ama DROP ETME
        zero_var_cols = [col for col in X.columns if X[col].nunique() <= 1]
        if zero_var_cols:
            logger.info(f"[Feature Stability] {len(zero_var_cols)} zero-variance features "
                        f"(kept for consistency): {zero_var_cols}")

        logger.info(f"Feature engineering completed. Shape: {X.shape}")
        logger.info(f"Features: {list(X.columns)}")

        return X, df

    # =====================================================================
    # TEMPORAL FEATURES (4)
    # =====================================================================

    def extract_timestamp_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Temporal features extraction.

        Features:
        - hour_of_day (0-23)
        - is_weekend (0/1)
        - is_business_hours (0/1)
        - time_since_last_log (seconds)
        """
        try:
            # Timestamp parse — event_timestamp (log satırından) HER ZAMAN tercih edilir
            # @timestamp Filebeat ingest time olabilir (aylarca sapma görüldü)
            # NOT: reader.read_logs() 'timestamp'i @timestamp'den oluşturur,
            # bu yüzden 'timestamp not in df' koşulu HER ZAMAN False olurdu.
            # event_timestamp varsa mevcut timestamp'i override etmeliyiz.
            if 'event_timestamp' in df.columns:
                # Log satırından parse edilen gerçek olay zamanı
                df['timestamp'] = pd.to_datetime(
                    df['event_timestamp'], format='mixed',
                    errors='coerce', utc=True
                )
                valid_count = df['timestamp'].notna().sum()
                logger.info(f"[Timestamp] Using event_timestamp from log line "
                            f"({valid_count}/{len(df)} valid)")
                # Parse edilemeyenler için @timestamp fallback
                if valid_count < len(df) and '@timestamp' in df.columns:
                    fallback = pd.to_datetime(
                        df['@timestamp'], errors='coerce', utc=True
                    )
                    df['timestamp'] = df['timestamp'].fillna(fallback)
                    logger.info(f"[Timestamp] Fallback to @timestamp for "
                                f"{len(df) - valid_count} rows")
            elif 'timestamp' not in df.columns and '@timestamp' in df.columns:
                df['timestamp'] = pd.to_datetime(
                    df['@timestamp'], errors='coerce', utc=True
                )

            if 'timestamp' in df.columns:
                # Timestamp'e göre sırala
                df = df.sort_values('timestamp').reset_index(drop=True)

                # hour_of_day
                df['hour_of_day'] = df['timestamp'].dt.hour

                # is_weekend
                df['is_weekend'] = (df['timestamp'].dt.dayofweek >= 5).astype(int)

                # is_business_hours
                bh_start = self.thresholds.get('business_hour_start', 8)
                bh_end = self.thresholds.get('business_hour_end', 18)
                df['is_business_hours'] = (
                    (df['hour_of_day'] >= bh_start) &
                    (df['hour_of_day'] < bh_end) &
                    (df['is_weekend'] == 0)
                ).astype(int)

                # time_since_last_log
                df['time_since_last_log'] = (
                    df['timestamp'].diff().dt.total_seconds().fillna(0)
                )
            else:
                df['hour_of_day'] = 0
                df['is_weekend'] = 0
                df['is_business_hours'] = 0
                df['time_since_last_log'] = 0

            logger.info("[OK] Temporal features extracted")

        except Exception as e:
            logger.error(f"Error in timestamp features: {e}")
            for col in ['hour_of_day', 'is_weekend', 'is_business_hours', 'time_since_last_log']:
                if col not in df.columns:
                    df[col] = 0

        return df

    # =====================================================================
    # SEVERITY FEATURES (3)
    # =====================================================================

    def extract_severity_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Log severity features extraction.

        Features:
        - is_warn (0/1)
        - is_error (0/1)
        - is_deprecation (0/1)
        """
        try:
            # log_level alanı enrichment'ta parse edilmiş olmalı
            if 'log_level' in df.columns:
                level_upper = df['log_level'].str.upper().str.strip()
                df['is_warn'] = (level_upper == 'WARN').astype(int)
                # CRITICAL da is_error olarak sayılır (en tehlikeli seviye)
                df['is_error'] = (
                    (level_upper == 'ERROR') | (level_upper == 'CRITICAL')
                ).astype(int)
                # is_deprecation: 3 kaynağın OR birleşimi
                # 1) Enrichment'ta raw_message pattern'dan set edilmiş olabilir
                enrichment_deprecation = pd.Series(0, index=df.index)
                if 'is_deprecation' in df.columns:
                    enrichment_deprecation = df['is_deprecation'].fillna(0).astype(int)
                # 2) log_level içinde DEPRECAT (bazı ES versiyonları)
                level_deprecation = level_upper.str.contains(
                    'DEPRECAT', na=False
                ).astype(int)
                # 3) event_dataset içinde deprecation (en güvenilir sinyal)
                dataset_deprecation = pd.Series(0, index=df.index)
                if 'event_dataset' in df.columns:
                    dataset_deprecation = df['event_dataset'].str.contains(
                        'deprecation', case=False, na=False
                    ).astype(int)
                # OR birleşimi
                df['is_deprecation'] = (
                    (enrichment_deprecation == 1) |
                    (level_deprecation == 1) |
                    (dataset_deprecation == 1)
                ).astype(int)
            else:
                # Fallback: raw_message'dan parse
                if 'raw_message' in df.columns:
                    df['is_warn'] = df['raw_message'].str.contains(
                        r'\[WARN\s*\]', na=False, regex=True
                    ).astype(int)
                    # CRITICAL da yakalanmalı
                    df['is_error'] = df['raw_message'].str.contains(
                        r'\[(ERROR|CRITICAL)\s*\]', na=False, regex=True
                    ).astype(int)
                    # raw_message + event_dataset OR birleşimi
                    msg_deprecation = df['raw_message'].str.contains(
                        r'deprecat', case=False, na=False
                    ).astype(int)
                    dataset_deprecation = pd.Series(0, index=df.index)
                    if 'event_dataset' in df.columns:
                        dataset_deprecation = df['event_dataset'].str.contains(
                            'deprecation', case=False, na=False
                        ).astype(int)
                    df['is_deprecation'] = (
                        (msg_deprecation == 1) | (dataset_deprecation == 1)
                    ).astype(int)
                else:
                    df['is_warn'] = 0
                    df['is_error'] = 0
                    df['is_deprecation'] = 0

            logger.info(f"[OK] Severity features extracted")
            logger.info(f"   WARN: {df['is_warn'].sum()} ({df['is_warn'].mean()*100:.1f}%)")
            logger.info(f"   ERROR: {df['is_error'].sum()} ({df['is_error'].mean()*100:.1f}%)")
            logger.info(f"   DEPRECATION: {df['is_deprecation'].sum()}")

        except Exception as e:
            logger.error(f"Error in severity features: {e}")
            for col in ['is_warn', 'is_error', 'is_deprecation']:
                if col not in df.columns:
                    df[col] = 0

        return df

    # =====================================================================
    # LOGGER/COMPONENT FEATURES (4)
    # =====================================================================

    def extract_logger_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Logger/component features extraction.

        Features:
        - is_cluster_logger (0/1)
        - is_index_logger (0/1)
        - is_transport_logger (0/1)
        - is_rare_logger (0/1)
        """
        try:
            if 'logger_category' in df.columns:
                df['is_cluster_logger'] = (
                    df['logger_category'] == 'cluster'
                ).astype(int)
                df['is_index_logger'] = (
                    df['logger_category'] == 'index'
                ).astype(int)
                df['is_transport_logger'] = (
                    df['logger_category'] == 'transport'
                ).astype(int)
            elif 'logger_name' in df.columns:
                # Fallback: doğrudan logger_name'den
                df['is_cluster_logger'] = df['logger_name'].apply(
                    lambda x: 1 if classify_logger(str(x)) == 'cluster' else 0
                )
                df['is_index_logger'] = df['logger_name'].apply(
                    lambda x: 1 if classify_logger(str(x)) == 'index' else 0
                )
                df['is_transport_logger'] = df['logger_name'].apply(
                    lambda x: 1 if classify_logger(str(x)) == 'transport' else 0
                )
            else:
                df['is_cluster_logger'] = 0
                df['is_index_logger'] = 0
                df['is_transport_logger'] = 0

            # Rare logger — batch-relative frequency
            if 'logger_name' in df.columns:
                rare_threshold = self.filters.get('rare_threshold', 50)
                logger_counts = df['logger_name'].value_counts()
                df['is_rare_logger'] = df['logger_name'].map(
                    lambda x: 1 if logger_counts.get(x, 0) < rare_threshold else 0
                )
                # Cache for later use
                self._logger_counts = logger_counts.to_dict()
            else:
                df['is_rare_logger'] = 0

            logger.info(f"[OK] Logger features extracted")
            logger.info(f"   Cluster loggers: {df['is_cluster_logger'].sum()}")
            logger.info(f"   Index loggers: {df['is_index_logger'].sum()}")
            logger.info(f"   Transport loggers: {df['is_transport_logger'].sum()}")
            logger.info(f"   Rare loggers: {df['is_rare_logger'].sum()}")

        except Exception as e:
            logger.error(f"Error in logger features: {e}")
            for col in ['is_cluster_logger', 'is_index_logger',
                        'is_transport_logger', 'is_rare_logger']:
                if col not in df.columns:
                    df[col] = 0

        return df

    # =====================================================================
    # ERROR PATTERN FEATURES (5)
    # =====================================================================

    def extract_error_pattern_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Error pattern features extraction (regex-based).

        Features:
        - is_exception (0/1)
        - is_circuit_breaker (0/1)
        - is_oom_error (0/1)
        - is_connection_error (0/1)
        - is_shard_failure (0/1)
        """
        try:
            msg_col = 'raw_message' if 'raw_message' in df.columns else 'message'

            if msg_col in df.columns:
                # Eğer enrichment'ta zaten hesaplandıysa, olanı koru
                if 'is_exception' not in df.columns:
                    df['is_exception'] = df[msg_col].apply(
                        lambda x: 1 if EXCEPTION_PATTERN.search(str(x)) else 0
                    )
                else:
                    df['is_exception'] = df['is_exception'].astype(int)

                if 'is_circuit_breaker' not in df.columns:
                    df['is_circuit_breaker'] = df[msg_col].apply(
                        lambda x: 1 if CIRCUIT_BREAKER_PATTERN.search(str(x)) else 0
                    )
                else:
                    df['is_circuit_breaker'] = df['is_circuit_breaker'].astype(int)

                if 'is_oom_error' not in df.columns:
                    df['is_oom_error'] = df[msg_col].apply(
                        lambda x: 1 if OOM_PATTERN.search(str(x)) else 0
                    )
                else:
                    df['is_oom_error'] = df['is_oom_error'].astype(int)

                if 'is_connection_error' not in df.columns:
                    df['is_connection_error'] = df[msg_col].apply(
                        lambda x: 1 if CONNECTION_ERROR_PATTERN.search(str(x)) else 0
                    )
                else:
                    df['is_connection_error'] = df['is_connection_error'].astype(int)

                if 'is_shard_failure' not in df.columns:
                    df['is_shard_failure'] = df[msg_col].apply(
                        lambda x: 1 if SHARD_FAILURE_PATTERN.search(str(x)) else 0
                    )
                else:
                    df['is_shard_failure'] = df['is_shard_failure'].astype(int)
            else:
                for col in ['is_exception', 'is_circuit_breaker', 'is_oom_error',
                            'is_connection_error', 'is_shard_failure']:
                    df[col] = 0

            logger.info(f"[OK] Error pattern features extracted")
            logger.info(f"   Exceptions: {df['is_exception'].sum()}")
            logger.info(f"   Circuit breaker: {df['is_circuit_breaker'].sum()}")
            logger.info(f"   OOM errors: {df['is_oom_error'].sum()}")
            logger.info(f"   Connection errors: {df['is_connection_error'].sum()}")
            logger.info(f"   Shard failures: {df['is_shard_failure'].sum()}")

        except Exception as e:
            logger.error(f"Error in error pattern features: {e}")
            for col in ['is_exception', 'is_circuit_breaker', 'is_oom_error',
                        'is_connection_error', 'is_shard_failure']:
                if col not in df.columns:
                    df[col] = 0

        return df

    # =====================================================================
    # PERFORMANCE FEATURES (4)
    # =====================================================================

    def extract_performance_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Performance-related features extraction.

        Features:
        - is_slow_log (0/1)
        - is_gc_overhead (0/1)
        - is_high_disk_watermark (0/1)
        - is_high_cpu (0/1)
        """
        try:
            msg_col = 'raw_message' if 'raw_message' in df.columns else 'message'

            if msg_col in df.columns:
                if 'is_slow_log' not in df.columns:
                    df['is_slow_log'] = df[msg_col].apply(
                        lambda x: 1 if SLOW_LOG_PATTERN.search(str(x)) else 0
                    )
                else:
                    df['is_slow_log'] = df['is_slow_log'].astype(int)

                if 'is_gc_overhead' not in df.columns:
                    df['is_gc_overhead'] = df[msg_col].apply(
                        lambda x: 1 if GC_PATTERN.search(str(x)) else 0
                    )
                else:
                    df['is_gc_overhead'] = df['is_gc_overhead'].astype(int)

                if 'is_high_disk_watermark' not in df.columns:
                    df['is_high_disk_watermark'] = df[msg_col].apply(
                        lambda x: 1 if DISK_WATERMARK_PATTERN.search(str(x)) else 0
                    )
                else:
                    df['is_high_disk_watermark'] = df['is_high_disk_watermark'].astype(int)

                if 'is_high_cpu' not in df.columns:
                    df['is_high_cpu'] = df[msg_col].apply(
                        lambda x: 1 if HIGH_CPU_PATTERN.search(str(x)) else 0
                    )
                else:
                    df['is_high_cpu'] = df['is_high_cpu'].astype(int)
            else:
                for col in ['is_slow_log', 'is_gc_overhead',
                            'is_high_disk_watermark', 'is_high_cpu']:
                    df[col] = 0

            logger.info(f"[OK] Performance features extracted")
            logger.info(f"   Slow logs: {df['is_slow_log'].sum()}")
            logger.info(f"   GC overhead: {df['is_gc_overhead'].sum()}")
            logger.info(f"   Disk watermark: {df['is_high_disk_watermark'].sum()}")
            logger.info(f"   High CPU: {df['is_high_cpu'].sum()}")

        except Exception as e:
            logger.error(f"Error in performance features: {e}")
            for col in ['is_slow_log', 'is_gc_overhead',
                        'is_high_disk_watermark', 'is_high_cpu']:
                if col not in df.columns:
                    df[col] = 0

        return df

    # =====================================================================
    # CLUSTER HEALTH FEATURES (3)
    # =====================================================================

    def extract_cluster_health_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Cluster health features extraction.

        Features:
        - is_node_event (0/1)
        - is_master_election (0/1)
        - is_shard_relocation (0/1)
        """
        try:
            msg_col = 'raw_message' if 'raw_message' in df.columns else 'message'

            if msg_col in df.columns:
                if 'is_node_event' not in df.columns:
                    df['is_node_event'] = df[msg_col].apply(
                        lambda x: 1 if NODE_EVENT_PATTERN.search(str(x)) else 0
                    )
                else:
                    df['is_node_event'] = df['is_node_event'].astype(int)

                if 'is_master_election' not in df.columns:
                    df['is_master_election'] = df[msg_col].apply(
                        lambda x: 1 if MASTER_ELECTION_PATTERN.search(str(x)) else 0
                    )
                else:
                    df['is_master_election'] = df['is_master_election'].astype(int)

                if 'is_shard_relocation' not in df.columns:
                    df['is_shard_relocation'] = df[msg_col].apply(
                        lambda x: 1 if SHARD_RELOCATION_PATTERN.search(str(x)) else 0
                    )
                else:
                    df['is_shard_relocation'] = df['is_shard_relocation'].astype(int)
            else:
                df['is_node_event'] = 0
                df['is_master_election'] = 0
                df['is_shard_relocation'] = 0

            logger.info(f"[OK] Cluster health features extracted")
            logger.info(f"   Node events: {df['is_node_event'].sum()}")
            logger.info(f"   Master elections: {df['is_master_election'].sum()}")
            logger.info(f"   Shard relocations: {df['is_shard_relocation'].sum()}")

        except Exception as e:
            logger.error(f"Error in cluster health features: {e}")
            for col in ['is_node_event', 'is_master_election', 'is_shard_relocation']:
                if col not in df.columns:
                    df[col] = 0

        return df

    # =====================================================================
    # BURST/PATTERN FEATURES (2)
    # =====================================================================

    def extract_burst_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Burst/Pattern features extraction.

        Features:
        - extreme_burst_flag (0/1) — aynı saniyede birden fazla log
        - burst_density — son 100 log içindeki burst yoğunluğu
        """
        try:
            if 'time_since_last_log' in df.columns:
                extreme_threshold = self.thresholds.get('extreme_burst_seconds', 0.1)
                df['extreme_burst_flag'] = (
                    (df['time_since_last_log'] >= 0) &
                    (df['time_since_last_log'] < extreme_threshold)
                ).astype(int)

                # Burst density (rolling window)
                df['burst_density'] = df['extreme_burst_flag'].rolling(
                    window=100, min_periods=1
                ).mean()
            else:
                df['extreme_burst_flag'] = 0
                df['burst_density'] = 0.0

            logger.info(f"[OK] Burst features extracted")
            logger.info(f"   Extreme bursts: {df['extreme_burst_flag'].sum()}")
            logger.info(f"   Avg burst density: {df['burst_density'].mean():.3f}")

        except Exception as e:
            logger.error(f"Error in burst features: {e}")
            if 'extreme_burst_flag' not in df.columns:
                df['extreme_burst_flag'] = 0
            if 'burst_density' not in df.columns:
                df['burst_density'] = 0.0

        return df

    # =====================================================================
    # FILTER & SUMMARY
    # =====================================================================

    def apply_filters(self, df: pd.DataFrame,
                      X: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Gürültü loglarını filtrele.

        Filters:
        - exclude_deprecation_info: Deprecation INFO loglarını atla (config)

        Args:
            df: Enriched DataFrame
            X: Feature matrix

        Returns:
            Tuple[filtered_df, filtered_X]
        """
        filter_mask = pd.Series([True] * len(df), index=df.index)

        # Deprecation info loglarını atla
        if self.filters.get('exclude_deprecation_info', True):
            if 'is_deprecation' in df.columns and 'is_warn' in df.columns:
                # Sadece WARN/ERROR olmayan deprecation loglarını at
                deprecation_info = (
                    (df['is_deprecation'] == 1) &
                    (df['is_warn'] == 0) &
                    (df['is_error'] == 0)
                )
                filter_mask &= ~deprecation_info
                excluded = deprecation_info.sum()
                if excluded > 0:
                    logger.info(f"Filtered {excluded} deprecation INFO logs")

        df_filtered = df[filter_mask].reset_index(drop=True)
        X_filtered = X[filter_mask].reset_index(drop=True)

        reduction = (1 - len(df_filtered) / len(df)) * 100 if len(df) > 0 else 0
        logger.info(f"Filters applied. Reduction: {reduction:.1f}% "
                    f"({len(df)} -> {len(df_filtered)})")

        return df_filtered, X_filtered

    def get_feature_summary(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Feature özeti döndür.

        Args:
            df: Feature DataFrame

        Returns:
            Feature summary dict
        """
        summary = {
            'total_logs': len(df),
            'features_count': len(self.enabled_features),
            'severity_stats': {},
            'logger_stats': {},
            'error_stats': {},
            'performance_stats': {},
            'cluster_stats': {},
        }

        # Severity stats
        for col in ['is_warn', 'is_error', 'is_deprecation']:
            if col in df.columns:
                summary['severity_stats'][col] = int(df[col].sum())

        # Logger stats
        for col in ['is_cluster_logger', 'is_index_logger',
                     'is_transport_logger', 'is_rare_logger']:
            if col in df.columns:
                summary['logger_stats'][col] = int(df[col].sum())

        # Error stats
        for col in ['is_exception', 'is_circuit_breaker', 'is_oom_error',
                     'is_connection_error', 'is_shard_failure']:
            if col in df.columns:
                summary['error_stats'][col] = int(df[col].sum())

        # Performance stats
        for col in ['is_slow_log', 'is_gc_overhead',
                     'is_high_disk_watermark', 'is_high_cpu']:
            if col in df.columns:
                summary['performance_stats'][col] = int(df[col].sum())

        # Cluster stats
        for col in ['is_node_event', 'is_master_election', 'is_shard_relocation']:
            if col in df.columns:
                summary['cluster_stats'][col] = int(df[col].sum())

        # Host role distribution
        if 'host_role' in df.columns:
            summary['host_roles'] = df['host_role'].value_counts().to_dict()

        return summary
