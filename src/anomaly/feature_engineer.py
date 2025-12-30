#src\anomaly\feature_engineer.py

"""
MongoDB Log Feature Engineering Module
Anomali tespiti için feature extraction
"""
import pandas as pd
import numpy as np
from datetime import datetime
import json
import logging
from typing import Dict, List, Tuple, Any, Optional
from pathlib import Path
import re

logger = logging.getLogger(__name__)

class MongoDBFeatureEngineer:
    """MongoDB logları için feature engineering"""
    
    def __init__(self, config_path: str = "config/anomaly_config.json"):
        """
        Feature Engineer başlat
        
        Args:
            config_path: Konfigürasyon dosyası yolu
        """
        self.config = self._load_config(config_path)
        self.features_config = self.config['anomaly_detection']['features']
        self.enabled_features = self.features_config['enabled_features']
        self.filters = self.features_config['filters']
        # ===== MODEL FEATURE SCHEMA HOLDER =====
        self.model_feature_schema = None
        
        logger.info(f"Feature engineer initialized with {len(self.enabled_features)} features")
    
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
                        "filters": {}
                    }
                }
            }

    def stabilize_features(self, df: pd.DataFrame, expected_schema: Dict[str, Any]) -> pd.DataFrame:
        """
        Modelin eğitimde kullandığı feature schema'ya göre DataFrame'i stabilize eder.
        Eksik kolonları ekler, fazla kolonları yok sayar, sıra ve dtype uyumluluğunu sağlar.
        """
        expected_cols = expected_schema.get("names", [])
        expected_count = expected_schema.get("count", len(expected_cols))

        # 1) Eksik kolonları ekle (default = 0.0)
        for col in expected_cols:
            if col not in df.columns:
                df[col] = 0.0

        # 2) Fazla kolonları logla (drop etmeye gerek yok — reindex sırasında zaten atılır)
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
        anomaly_detector.py tarafından çağrılır.
        
        Args:
            X: Feature matrix (prediction için)
            feature_schema: Model training'den gelen feature schema
                           Format: {"names": [...], "count": int}
        
        Returns:
            Stabilize edilmiş feature matrix
        """
        # Schema yoksa veya boşsa, orijinal X'i döndür
        if feature_schema is None:
            logger.debug("No feature schema provided, returning original features")
            return X
        
        if not feature_schema.get("names"):
            logger.debug("Empty feature schema names, returning original features")
            return X
        
        # Schema varsa stabilize et
        logger.info(f"Stabilizing features for model prediction ({len(feature_schema.get('names', []))} expected features)")
        
        try:
            # Internal model schema'yı güncelle
            self.model_feature_schema = feature_schema
            
            # Mevcut stabilize_features metodunu kullan
            X_stabilized = self.stabilize_features(X.copy(), feature_schema)
            
            logger.info(f"Feature stabilization completed: {X.shape} -> {X_stabilized.shape}")
            return X_stabilized
            
        except Exception as e:
            logger.error(f"Feature stabilization failed: {e}")
            logger.warning("Returning original features due to stabilization error")
            return X

    def create_features(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Tüm feature'ları oluştur
        
        Args:
            df: Raw log DataFrame
            
        Returns:
            Tuple[features_df, enriched_df]: Feature matrisi ve zenginleştirilmiş DataFrame
        """
        logger.info(f"Starting feature engineering on {len(df)} logs...")
        
        # DataFrame kopyası oluştur
        df = df.copy()
        
        # ÖNEMLİ: raw_log field'ını koru (OpenSearch'ten gelen tam mesaj)
        if 'raw_log' not in df.columns:
            # Eğer raw_log yoksa, mevcut mesajları kullan
            logger.warning("raw_log field not found, using msg field as fallback")
            df['raw_log'] = df['msg'] if 'msg' in df.columns else ''
        else:
            logger.info(f"[OK] raw_log field preserved with {df['raw_log'].notna().sum()} entries")

        # Sırasıyla feature extraction
        df = self.extract_timestamp_features(df)
        df = self.extract_message_features(df)
        df = self.extract_severity_features(df)
        df = self.extract_component_features(df)
        df = self.extract_combination_features(df)
        df = self.extract_attr_features(df)

        # ===================== SCHEMA STABILIZER =====================
        # Eğer model schema bilgisi gönderilmişse stabilize et
        if hasattr(self, "model_feature_schema") and self.model_feature_schema:
            try:
                logger.info("Applying feature schema stabilizer (from model training stats)...")
                df = self.stabilize_features(df, self.model_feature_schema)
            except Exception as e:
                logger.error(f"Feature schema stabilizer failed: {e}")
        # ====================================================================

        # Feature seçimi
        # Feature seçimi
        feature_columns = [col for col in self.enabled_features if col in df.columns]
        X = df[feature_columns].copy()
        
        # Problemli feature'ları temizle (config'den)
        if 'time_since_last_log' in X.columns and 'time_since_last_log' not in self.enabled_features:
            X = X.drop('time_since_last_log', axis=1)
        if 'log_burst_flag' in X.columns and 'log_burst_flag' not in self.enabled_features:
            X = X.drop('log_burst_flag', axis=1)
        
        # YENİ: Non-numeric kolonları filtrele
        numeric_dtypes = ['int16', 'int32', 'int64', 'float16', 'float32', 'float64']
        numeric_columns = X.select_dtypes(include=numeric_dtypes).columns.tolist()
        non_numeric_columns = X.select_dtypes(exclude=numeric_dtypes).columns.tolist()
        
        if non_numeric_columns:
            logger.warning(f"Removing non-numeric columns from features: {non_numeric_columns}")
            X = X[numeric_columns].copy()
        
        # NaN değerleri 0 ile doldur (güvenlik için)
        X = X.fillna(0)
        
        logger.info(f"Final feature matrix: {X.shape} (all numeric)")
        
        logger.info(f"Feature engineering completed. Shape: {X.shape}")
        logger.info(f"Features: {list(X.columns)}")
        
        return X, df
        
    def extract_timestamp_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Temporal features extraction"""
        try:
            # Timestamp parse
            if 't' in df.columns:
                if isinstance(df['t'].iloc[0], dict):
                    df['timestamp'] = pd.to_datetime(
                        df['t'].apply(lambda x: x.get('$date') if isinstance(x, dict) else None),
                        utc=True  # [OK] UTC'ye zorla
                    )
                else:
                    df['timestamp'] = pd.to_datetime(df['t'])
            
            # Timestamp'e göre sırala
            df = df.sort_values('timestamp').reset_index(drop=True)
            
            # Hour of day
            df['hour_of_day'] = df['timestamp'].dt.hour
            
            # Weekend flag
            df['is_weekend'] = (df['timestamp'].dt.dayofweek >= 5).astype(int)
            
            # Time since last log
            df['time_since_last_log'] = df['timestamp'].diff().dt.total_seconds().fillna(0)
            
            # Burst flags
            df['log_burst_flag'] = ((df['time_since_last_log'] > 0) & 
                                   (df['time_since_last_log'] < 0.1)).astype(int)
            
            # Extreme burst flag - aynı milisaniyede
            df['extreme_burst_flag'] = (df['time_since_last_log'] == 0).astype(int)
            
            # Burst density (son 100 log içindeki burst yoğunluğu)
            df['burst_density'] = df['extreme_burst_flag'].rolling(window=100, min_periods=1).mean()
            
            logger.info(f"[OK] Temporal features extracted")
            logger.info(f"   Extreme bursts: {df['extreme_burst_flag'].sum()} ({df['extreme_burst_flag'].mean()*100:.1f}%)")
            
        except Exception as e:
            logger.error(f"Error in timestamp features: {e}")
            
        return df
    def extract_message_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Message-based features"""
        try:
            # Authorization failure flag 
            # Hem "Checking authorization failed" hem de "Authentication failed" yakalanır
            df['is_auth_failure'] = (
                (df['msg'] == 'Checking authorization failed') | 
                (df['msg'] == 'Authentication failed') |
                df['msg'].str.contains('AuthenticationFailed|authentication failed|auth.*failed', 
                                       case=False, na=False, regex=True)
            ).astype(int)

            # Authentication succeeded flag (filtreleme için)
            df['is_auth_success'] = (df['msg'] == 'Authentication succeeded').astype(int)
            
            # Reauthenticate flag (filtreleme için)
            df['is_reauthenticate'] = (df['msg'] == 'Client has attempted to reauthenticate as a single user').astype(int)
            
            # YENİ: GENİŞLETİLMİŞ MongoDB komut operasyonları
            # DROP operasyonları - Veri silme riskli
            df['is_drop_operation'] = df['msg'].str.contains(
                'CMD: drop|dropIndexes|dropDatabase|drop collection|dropCollection', 
                case=False, na=False
            ).astype(int)
            
            # AGGREGATE operasyonları - Pipeline sorgular
            df['is_aggregate_operation'] = df['msg'].str.contains(
                'CMD: aggregate|command.*aggregate|pipeline|$match|$group|$lookup|$unwind', 
                case=False, na=False
            ).astype(int)
            
            # ADMINISTRATIVE operasyonları - Admin komutları
            df['is_admin_operation'] = df['msg'].str.contains(
                'CMD: listCollections|listIndexes|dbStats|collStats|serverStatus|replSetGetStatus|isMaster|hello', 
                case=False, na=False
            ).astype(int)
            
            # BULK operasyonları - Toplu işlemler
            df['is_bulk_operation'] = df['msg'].str.contains(
                'CMD: bulkWrite|bulk|insertMany|updateMany|deleteMany|findAndModify', 
                case=False, na=False
            ).astype(int)
            
            # ABORTED TRANSACTION - İptal edilen işlemler (potansiyel sorun göstergesi)
            # startTransaction ve commitTransaction normal operasyonlar, sadece abort önemli

            df['is_aborted_transaction'] = df['msg'].str.contains(
                'abortTransaction|transaction.*abort|abort.*transaction',
                case=False, na=False, regex=True
            ).astype(int)
            
            # COLLSCAN detection (performans sorunu)
            df['is_collscan'] = df['msg'].str.contains(
                'COLLSCAN|planSummary.*COLLSCAN|"planSummary":"COLLSCAN"', 
                case=False, na=False, regex=True
            ).astype(int)
            
            # Index build detection
            df['is_index_build'] = df['msg'].str.contains(
                'Index build|index.*build.*starting|"msg":"Index build: starting"', 
                case=False, na=False, regex=True
            ).astype(int)
            
            # Slow query detection (Slow query mesajı veya yüksek durationMillis)
            df['is_slow_query'] = df['msg'].str.contains(
                'Slow query|durationMillis":[1-9]\\d{3,}', 
                regex=True, case=False, na=False
            ).astype(int)
            
            # High document scan detection (docsExamined > 10000)
            df['is_high_doc_scan'] = df['msg'].str.contains(
                'docsExamined":[1-9]\\d{4,}', 
                regex=True, na=False
            ).astype(int)
            
            # Shutdown detection
            df['is_shutdown'] = df['msg'].str.contains(
                'shutdown|mongod shutdown complete|dbexit', 
                case=False, na=False
            ).astype(int)
            
            # Assertion errors
            df['is_assertion'] = df['msg'].str.contains(
                'assertion|assert|Assertion|BSONObjectTooLarge', 
                case=False, na=False
            ).astype(int)
            
            # YENİ: GÜÇLENDİRİLMİŞ - Normal replication operations (FILTER OUT)
            # MongoDB-spesifik normal operasyon pattern'leri
            normal_replication_patterns = [
                'Applied op',           # Temel Applied Op
                '"msg":"Applied op"',   # JSON format
                'AppliedOp',           # AppliedOp variant
                'applying batch',      # Batch replication
                'oplog replay',        # Oplog tekrarı
                'replSetMemberState',  # Replica set durum değişimi
                'Primary has changed', # Primary değişimi
                'replica set member state', # Üye durum değişimi
                'heartbeat',           # Heartbeat mesajları
                'election',            # Election süreçleri (normal)
                'member is now in state PRIMARY',  # Normal durum geçişi
                'member is now in state SECONDARY'  # Normal durum geçişi
            ]
            
            # Tüm pattern'leri birleştir
            combined_pattern = '|'.join(normal_replication_patterns)
            df['is_normal_replication'] = df['msg'].str.contains(
                combined_pattern, 
                case=False, na=False
            ).astype(int)
            
            # Fatal errors (APPLIED OP ÇIKARILDİ)
            df['is_fatal'] = df['msg'].str.contains(
                'fatal|FATAL|Out of memory|OOM|OutOfMemory|memory allocation failed', 
                case=False, na=False
            ).astype(int)
            
            # Normal replication işlemlerini fatal'dan çıkar
            df['is_fatal'] = ((df['is_fatal'] == 1) & (df['is_normal_replication'] == 0)).astype(int)
            
            # ERROR severity (JSON formatı için)
            df['is_error'] = ((df['s'] == 'E') | df['msg'].str.contains('"s":"E"', na=False)).astype(int)
            
            # Replication issues
            df['is_replication_issue'] = df['msg'].str.contains(
                'Cannot select sync source|ReplCoordExtern|REPL', 
                case=False, na=False
            ).astype(int)

            # Out of Memory detection (spesifik)
            df['is_out_of_memory'] = df['msg'].str.contains(
                'Out of memory|OOM|OutOfMemory|memory allocation failed|cannot allocate memory|tcmalloc|jemalloc',
                case=False, na=False, regex=True
            ).astype(int)

            # Restart detection
            df['is_restart'] = df['msg'].str.contains(
                'restart|restarted|starting.*mongod|mongod.*starting|server restarted|Recovering journal|STARTUP2',
                case=False, na=False, regex=True
            ).astype(int)

            # Memory limit exceeded detection
            df['is_memory_limit'] = df['msg'].str.contains(
                'memory limit exceeded|exceeded memory limit|memory threshold|WiredTiger cache|cache overflow|eviction',
                case=False, na=False, regex=True
            ).astype(int)

            # Message category (ilk kelime)
            df['msg_category'] = df['msg'].str.split().str[0]
            
            # Rare message flag
            msg_counts = df['msg'].value_counts()
            rare_threshold = self.filters.get('rare_threshold', 100)
            rare_messages = msg_counts[msg_counts < rare_threshold].index
            df['is_rare_message'] = df['msg'].isin(rare_messages).astype(int)
            
            logger.info(f"[OK] Message features extracted")
            logger.info(f"   Auth failures: {df['is_auth_failure'].sum()} ({df['is_auth_failure'].mean()*100:.1f}%)")
            # YENİ: GENİŞLETİLMİŞ komut istatistikleri
            logger.info(f"   DROP operations: {df['is_drop_operation'].sum()}")
            logger.info(f"   AGGREGATE operations: {df['is_aggregate_operation'].sum()}")
            logger.info(f"   ADMIN operations: {df['is_admin_operation'].sum()}")
            logger.info(f"   BULK operations: {df['is_bulk_operation'].sum()}")
            logger.info(f"   ABORTED TRANSACTION operations: {df['is_aborted_transaction'].sum()}")
            # Diğer özellikler
            logger.info(f"   COLLSCAN queries: {df['is_collscan'].sum()}")
            logger.info(f"   Slow queries: {df['is_slow_query'].sum()}")
            logger.info(f"   Index builds: {df['is_index_build'].sum()}")
            logger.info(f"   High doc scans: {df['is_high_doc_scan'].sum()}")
            logger.info(f"   Out of Memory errors: {df['is_out_of_memory'].sum()}")
            logger.info(f"   Restart events: {df['is_restart'].sum()}")
            logger.info(f"   Memory limit exceeded: {df['is_memory_limit'].sum()}")
            logger.info(f"   Normal replication ops: {df['is_normal_replication'].sum()} ({df['is_normal_replication'].mean()*100:.1f}%)")
            
            # === NUMERIC VALUE EXTRACTION BAŞLANGIÇ ===

            # Compiled regex patterns (performans için - fallback olarak kullanılacak)
            DURATION_PATTERN = re.compile(r'"durationMillis":(\d+)')
            DOCS_EXAMINED_PATTERN = re.compile(r'"docsExamined":(\d+)')
            KEYS_EXAMINED_PATTERN = re.compile(r'"keysExamined":(\d+)')

            # YENİ: Hibrit extraction - önce attr dict, sonra msg string

            def extract_duration_hybrid(row):
                """Extract durationMillis from attr dict OR msg string"""
                try:
                    # 1. Önce attr dict'inden dene (TXN logları için kritik)
                    if 'attr' in row and isinstance(row['attr'], dict):
                        attr = row['attr']
                        if 'durationMillis' in attr:
                            return int(attr['durationMillis'])
                    # 2. Fallback: msg string'inden regex ile çek
                    if 'msg' in row and row['msg']:
                        match = DURATION_PATTERN.search(str(row['msg']))
                        if match:
                            return int(match.group(1))
                    # 3. Son çare: raw_log'dan dene
                    if 'raw_log' in row and row['raw_log']:
                        match = DURATION_PATTERN.search(str(row['raw_log']))
                        if match:
                            return int(match.group(1))
                    return 0
                except:
                    return 0

            def extract_docs_examined_hybrid(row):
                """Extract docsExamined from attr dict OR msg string"""
                try:
                    # 1. Önce attr dict'inden dene
                    if 'attr' in row and isinstance(row['attr'], dict):
                        attr = row['attr']
                        if 'docsExamined' in attr:
                            return int(attr['docsExamined'])
                    # 2. Fallback: msg string'inden regex ile çek
                    if 'msg' in row and row['msg']:
                        match = DOCS_EXAMINED_PATTERN.search(str(row['msg']))
                        if match:
                            return int(match.group(1))
                    return 0
                except:
                    return 0

            def extract_keys_examined_hybrid(row):
                """Extract keysExamined from attr dict OR msg string"""
                try:
                    # 1. Önce attr dict'inden dene
                    if 'attr' in row and isinstance(row['attr'], dict):
                        attr = row['attr']
                        if 'keysExamined' in attr:
                            return int(attr['keysExamined'])
                    # 2. Fallback: msg string'inden regex ile çek
                    if 'msg' in row and row['msg']:
                        match = KEYS_EXAMINED_PATTERN.search(str(row['msg']))
                        if match:
                            return int(match.group(1))
                    return 0
                except:
                    return 0

            # YENİ: Transaction-spesifik metrikler
            def extract_txn_metrics(row):
                """Extract transaction-specific metrics from attr"""
                metrics = {
                    'time_active_micros': 0,
                    'time_inactive_micros': 0
                }
                try:
                    if 'attr' in row and isinstance(row['attr'], dict):
                        attr = row['attr']
                        metrics['time_active_micros'] = int(attr.get('timeActiveMicros', 0))
                        metrics['time_inactive_micros'] = int(attr.get('timeInactiveMicros', 0))
                except:
                    pass
                return metrics

            # Apply hibrit numeric extractions (row-based for attr access)
            df['query_duration_ms'] = df.apply(extract_duration_hybrid, axis=1)
            df['docs_examined_count'] = df.apply(extract_docs_examined_hybrid, axis=1)
            df['keys_examined_count'] = df.apply(extract_keys_examined_hybrid, axis=1)

            # [SAFETY LAYER] CONFIG-BASED NUMERICAL CAPPING Devasa sayıların ML modelindeki binary (0/1) uyarıları ezmesini önlemek için
            try:
                cap_config = self.config.get('anomaly_detection', {}).get('capping', {})
                max_dur = cap_config.get('max_query_duration_ms', 60000)
                max_scan = cap_config.get('max_docs_examined', 1000000)
                logger.info(f"Applying numerical capping (Duration Limit: {max_dur}ms, Scan Limit: {max_scan})")
                df['query_duration_ms'] = df['query_duration_ms'].clip(upper=max_dur)
                df['docs_examined_count'] = df['docs_examined_count'].clip(upper=max_scan)
                df['keys_examined_count'] = df['keys_examined_count'].clip(upper=max_scan)
            except Exception as cap_err:
                logger.warning(f"Numerical capping applied with fallback defaults: {cap_err}")
                df['query_duration_ms'] = df['query_duration_ms'].clip(upper=60000)
            # --- END SAFETY LAYER ---

            # YENİ: Transaction metrikleri çıkar
            txn_metrics = df.apply(extract_txn_metrics, axis=1)
            df['txn_time_active_micros'] = txn_metrics.apply(lambda x: x['time_active_micros'])
            df['txn_time_inactive_micros'] = txn_metrics.apply(lambda x: x['time_inactive_micros'])

            # Transaction capping (eğer txn field'ları varsa)
            if 'txn_time_active_micros' in df.columns:
                max_txn = self.config.get('anomaly_detection', {}).get('capping', {}).get('max_txn_active_micros', 30000000)
                df['txn_time_active_micros'] = df['txn_time_active_micros'].clip(upper=max_txn)

            # YENİ: Transaction wait ratio (yüksek değer = blocking sorunu göstergesi)
            # time_inactive / time_active oranı - 100'den büyükse potansiyel lock contention
            df['txn_wait_ratio'] = np.where(
                df['txn_time_active_micros'] > 0,
                df['txn_time_inactive_micros'] / df['txn_time_active_micros'],
                0
            )

            # YENİ: Uzun transaction flag (100ms üzeri)
            df['is_long_transaction'] = (df['query_duration_ms'] > 100).astype(int)
            # Performance score (yüksek değer = kötü performans)
            # COLLSCAN'de keys_examined 0 olur, bu da kötü performans göstergesi
            df['performance_score'] = np.where(
                df['is_collscan'] == 1,
                df['docs_examined_count'] * 2,  # COLLSCAN'de çarpan uygula
                np.maximum(0, df['docs_examined_count'] - df['keys_examined_count'])  # [OK] Minimum 0
            )
            
            # Log numeric extraction stats
            slow_queries = df[df['query_duration_ms'] > 1000]
            if len(slow_queries) > 0:
                logger.info(f"   Avg slow query duration: {slow_queries['query_duration_ms'].mean():.0f}ms")
                logger.info(f"   Max query duration: {df['query_duration_ms'].max():.0f}ms")
            
            high_scan_queries = df[df['docs_examined_count'] > 10000]
            if len(high_scan_queries) > 0:
                logger.info(f"   Avg docs examined (high scan): {high_scan_queries['docs_examined_count'].mean():.0f}")
            
            # === NUMERIC VALUE EXTRACTION BİTİŞ ===
            
        except Exception as e:
            logger.error(f"Error in message features: {e}")
            
        return df

    def extract_severity_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Severity features"""
        try:
            df['severity_W'] = (df['s'] == 'W').astype(int)
            
            logger.info(f"[OK] Severity features extracted")
            logger.info(f"   Warnings: {df['severity_W'].sum()} ({df['severity_W'].mean()*100:.1f}%)")
            
        except Exception as e:
            logger.error(f"Error in severity features: {e}")
            
        return df
    
    def extract_component_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Component features"""
        try:
            # Component frequency
            component_counts = df['c'].value_counts()
            
            # Rare component flag
            rare_threshold = self.filters.get('rare_threshold', 100)
            rare_components = component_counts[component_counts < rare_threshold].index
            df['is_rare_component'] = df['c'].isin(rare_components).astype(int)
            
            # Component ordinal encoding (by frequency)
            component_map = {comp: idx for idx, comp in enumerate(component_counts.index)}
            df['component_encoded'] = df['c'].map(component_map)
            
            # Component transition (component değişimi)
            df['component_changed'] = (df['c'] != df['c'].shift(1)).astype(int)

            # ========== YENİ: MongoDB 8.0 Component Features ==========

            # WiredTiger Storage Engine Components
            # WTRECOV: Recovery işlemleri - startup/crash recovery göstergesi
            df['is_wiredtiger_recovery'] = (df['c'] == 'WTRECOV').astype(int)

            # WTCHKPT: Checkpoint işlemleri - disk I/O ve checkpoint health
            df['is_wiredtiger_checkpoint'] = (df['c'] == 'WTCHKPT').astype(int)

            # Kombine WiredTiger flag (herhangi bir WT component)
            df['is_wiredtiger_event'] = df['c'].isin(['WTRECOV', 'WTCHKPT', 'WT']).astype(int)

            # STORAGE component - genel storage engine olayları
            df['is_storage_event'] = (df['c'] == 'STORAGE').astype(int)

            # Multi-tenant ve Migration Components (MongoDB 8.0+)
            df['is_tenant_operation'] = (df['c'] == 'TENANT_M').astype(int)

            # FTDC - Diagnostik veri toplama (performans monitoring)
            df['is_ftdc_event'] = (df['c'] == 'FTDC').astype(int)

            # ASIO - Async I/O events (network issues)
            df['is_async_io_event'] = (df['c'] == 'ASIO').astype(int)

            # INDEX component - index operasyonları
            df['is_index_event'] = (df['c'] == 'INDEX').astype(int)

            # RECOVERY component - recovery operasyonları
            df['is_recovery_event'] = (df['c'] == 'RECOVERY').astype(int)

            # Boş/Unknown component handling (c = "-")
            df['is_unknown_component'] = (df['c'].isin(['-', '', 'UNKNOWN', None]) | df['c'].isna()).astype(int)

            # ========== Critical Component Kategorileri ==========

            # Network kritik component'ler
            network_components = ['NETWORK', 'CONNPOOL', 'ASIO']
            df['is_network_component'] = df['c'].isin(network_components).astype(int)

            # Access/Security kritik component'ler  
            security_components = ['ACCESS', 'SECURITY']
            df['is_security_component'] = df['c'].isin(security_components).astype(int)

            # Replication kritik component'ler
            replication_components = ['REPL', 'ELECTION', 'ROLLBACK']
            df['is_replication_component'] = df['c'].isin(replication_components).astype(int)

            # Storage kritik component'ler (tüm storage-related)
            storage_components = ['STORAGE', 'WTRECOV', 'WTCHKPT', 'WT', 'JOURNAL']
            df['is_storage_component'] = df['c'].isin(storage_components).astype(int)

            # Control/Startup component'ler
            control_components = ['CONTROL', 'INITSYNC']
            df['is_control_component'] = df['c'].isin(control_components).astype(int)

            # ========== Component Anomaly Scoring ==========

            # Kritik component skoru (ağırlıklı)
            # Daha yüksek skor = daha kritik event
            df['component_criticality_score'] = (
                df['is_security_component'] * 3 +      # Security en kritik
                df['is_storage_component'] * 2 +       # Storage kritik
                df['is_replication_component'] * 2 +   # Replication kritik
                df['is_network_component'] * 1 +       # Network orta
                df['is_unknown_component'] * 1         # Unknown dikkat çeker
            )

            # ========== Loglama ==========

            logger.info(f"[OK] Component features extracted")
            logger.info(f"   Unique components: {df['c'].nunique()}")
            logger.info(f"   Rare components: {len(rare_components)}")

            # MongoDB 8.0 component istatistikleri
            logger.info(f"   WiredTiger Recovery events: {df['is_wiredtiger_recovery'].sum()}")
            logger.info(f"   WiredTiger Checkpoint events: {df['is_wiredtiger_checkpoint'].sum()}")
            logger.info(f"   Tenant Migration events: {df['is_tenant_operation'].sum()}")
            logger.info(f"   FTDC events: {df['is_ftdc_event'].sum()}")
            logger.info(f"   Unknown component events: {df['is_unknown_component'].sum()}")

            # Kritik component dağılımı
            logger.info(f"   Security component logs: {df['is_security_component'].sum()}")
            logger.info(f"   Storage component logs: {df['is_storage_component'].sum()}")
            logger.info(f"   Network component logs: {df['is_network_component'].sum()}")

        except Exception as e:
            logger.error(f"Error in component features: {e}")

        return df
    
    def extract_combination_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Combination features"""
        try:
            # s+c combination
            df['severity_component_combo'] = df['s'] + '_' + df['c']
            
            # Rare combination flag
            combo_counts = df['severity_component_combo'].value_counts()
            rare_threshold = self.filters.get('rare_threshold', 100)
            rare_combos = combo_counts[combo_counts < rare_threshold].index
            df['is_rare_combo'] = df['severity_component_combo'].isin(rare_combos).astype(int)
            
            logger.info(f"[OK] Combination features extracted")
            logger.info(f"   Rare combos: {df['is_rare_combo'].sum()}")
            
        except Exception as e:
            logger.error(f"Error in combination features: {e}")
            
        return df
    
    def extract_attr_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Attribute dictionary features"""
        print(f"DataFrame columns: {df.columns.tolist()}")
        try:
            def safe_parse_attr(attr_obj):
                try:
                    if pd.isna(attr_obj) or attr_obj == 'NaN':
                        return {}
                    if isinstance(attr_obj, dict):
                        return attr_obj
                    if isinstance(attr_obj, str):
                        return eval(attr_obj)
                    return {}
                except:
                    return {}
            
            # Parse attr
            if 'attr' in df.columns:
                df['attr_parsed'] = df['attr'].apply(safe_parse_attr)
                
                # Has error key
                df['has_error_key'] = df['attr_parsed'].apply(lambda x: 1 if 'error' in x.keys() else 0)
                
                # Attr key count
                df['attr_key_count'] = df['attr_parsed'].apply(lambda x: len(x.keys()))
                
                # Has many attrs (5'ten fazla key varsa)
                df['has_many_attrs'] = (df['attr_key_count'] > 5).astype(int)
            else:
                # Text format için varsayılan değerler
                df['has_error_key'] = 0
                df['attr_key_count'] = 0
                df['has_many_attrs'] = 0
                
            logger.info(f"[OK] Attr features extracted")
            if 'has_error_key' in df.columns:
                logger.info(f"   Error logs: {df['has_error_key'].sum()} ({df['has_error_key'].mean()*100:.1f}%)")
            
            # [OK] YENİ: Memory optimization - geçici sütunu temizle
            if 'attr_parsed' in df.columns:
                # Temizlemeden önce bellek kullanımını logla
                memory_before = df.memory_usage(deep=True).sum() / 1024 / 1024
                
                # Geçici parsed sütunu sil
                df = df.drop('attr_parsed', axis=1)
                
                # Temizledikten sonra bellek kullanımını logla
                memory_after = df.memory_usage(deep=True).sum() / 1024 / 1024
                memory_saved = memory_before - memory_after
                
                logger.info(f"   Memory optimized: {memory_saved:.2f} MB saved")
                logger.info(f"   Current DataFrame size: {memory_after:.2f} MB")
            
        except Exception as e:
            logger.error(f"Error in attr features: {e}")
            
        return df
        
    def apply_filters(self, df: pd.DataFrame, X: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Config'deki filtreleri uygula
        
        Args:
            df: Enriched DataFrame
            X: Feature matrix
            
        Returns:
            Filtered DataFrames
        """
        try:
            filter_mask = pd.Series([True] * len(df))
                          
            # Reauthenticate filter
            if self.filters.get('exclude_reauthenticate', True) and 'is_reauthenticate' in df.columns:
                filter_mask &= (df['is_reauthenticate'] == 0)
            
            # YENİ: Normal replication filter
            if self.filters.get('exclude_normal_replication', True) and 'is_normal_replication' in df.columns:
                filter_mask &= (df['is_normal_replication'] == 0)
            
            # Filtrelemeyi uygula
            df_filtered = df[filter_mask].reset_index(drop=True)
            X_filtered = X[filter_mask].reset_index(drop=True)
            
            reduction_rate = (1 - len(df_filtered) / len(df)) * 100
            logger.info(f"Filters applied. Reduction: {reduction_rate:.1f}%")
            logger.info(f"Remaining logs: {len(df_filtered)}")
            
            return df_filtered, X_filtered
            
        except Exception as e:
            logger.error(f"Error applying filters: {e}")
            return df, X
    
    def get_feature_statistics(self, X: pd.DataFrame) -> Dict[str, Any]:
        """Feature istatistiklerini hesapla"""
        stats = {
            "shape": X.shape,
            "features": list(X.columns),
            "binary_features": {},
            "continuous_features": {}
        }
        
        # Binary features - YENİ: GENİŞLETİLMİŞ komut özellikleri dahil
        binary_features = ['severity_W', 'is_rare_component', 'is_rare_combo', 'has_error_key', 
                          'is_auth_failure', 'is_drop_operation', 
                          'is_aggregate_operation', 'is_admin_operation', 'is_bulk_operation',
                          'is_aborted_transaction', 'is_rare_message', 'extreme_burst_flag', 
                          'is_weekend', 'component_changed', 'has_many_attrs',
                          'is_collscan', 'is_index_build', 'is_slow_query', 'is_high_doc_scan',
                          'is_shutdown', 'is_assertion', 'is_fatal', 'is_error', 'is_replication_issue',
                          'is_out_of_memory', 'is_restart', 'is_memory_limit']
        for col in X.columns:
            if col in binary_features:
                stats["binary_features"][col] = {
                    "count": int(X[col].sum()),
                    "percentage": float(X[col].mean() * 100)
                }
            else:
                stats["continuous_features"][col] = {
                    "mean": float(X[col].mean()),
                    "std": float(X[col].std()),
                    "min": float(X[col].min()),
                    "max": float(X[col].max())
                }
        
        return stats