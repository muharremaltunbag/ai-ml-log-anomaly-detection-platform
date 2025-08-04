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
        
        # Sırasıyla feature extraction
        df = self.extract_timestamp_features(df)
        df = self.extract_message_features(df)
        df = self.extract_severity_features(df)
        df = self.extract_component_features(df)
        df = self.extract_combination_features(df)
        df = self.extract_attr_features(df)
        
        # Feature seçimi
        feature_columns = [col for col in self.enabled_features if col in df.columns]
        X = df[feature_columns].copy()
        
        # Problemli feature'ları temizle (config'den)
        if 'time_since_last_log' in X.columns and 'time_since_last_log' not in self.enabled_features:
            X = X.drop('time_since_last_log', axis=1)
        if 'log_burst_flag' in X.columns and 'log_burst_flag' not in self.enabled_features:
            X = X.drop('log_burst_flag', axis=1)
        
        logger.info(f"Feature engineering completed. Shape: {X.shape}")
        logger.info(f"Features: {list(X.columns)}")
        
        return X, df
    
    def extract_timestamp_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Temporal features extraction"""
        try:
            # Timestamp parse
            if 't' in df.columns:
                if isinstance(df['t'].iloc[0], dict):
                    df['timestamp'] = pd.to_datetime(df['t'].apply(lambda x: x.get('$date') if isinstance(x, dict) else None))
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
            
            logger.info(f"✅ Temporal features extracted")
            logger.info(f"   Extreme bursts: {df['extreme_burst_flag'].sum()} ({df['extreme_burst_flag'].mean()*100:.1f}%)")
            
        except Exception as e:
            logger.error(f"Error in timestamp features: {e}")
            
        return df
    def extract_message_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Message-based features"""
        try:
            # Authorization failure flag
            df['is_auth_failure'] = (df['msg'] == 'Checking authorization failed').astype(int)
            
            # Authentication succeeded flag (filtreleme için)
            df['is_auth_success'] = (df['msg'] == 'Authentication succeeded').astype(int)
            
            # Reauthenticate flag (filtreleme için)
            df['is_reauthenticate'] = (df['msg'] == 'Client has attempted to reauthenticate as a single user').astype(int)
            
            # DROP operasyonları için flag
            df['is_drop_operation'] = df['msg'].str.contains('CMD: drop|dropIndexes', case=False, na=False).astype(int)
            
            
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
            
            # Fatal errors (memory related dahil)
            df['is_fatal'] = df['msg'].str.contains(
                'fatal|FATAL|Applied op|memory', 
                case=False, na=False
            ).astype(int)
            
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
            
            logger.info(f"✅ Message features extracted")
            logger.info(f"   Auth failures: {df['is_auth_failure'].sum()} ({df['is_auth_failure'].mean()*100:.1f}%)")
            logger.info(f"   Drop operations: {df['is_drop_operation'].sum()}")
            logger.info(f"   COLLSCAN queries: {df['is_collscan'].sum()}")
            logger.info(f"   Slow queries: {df['is_slow_query'].sum()}")
            logger.info(f"   Index builds: {df['is_index_build'].sum()}")
            logger.info(f"   High doc scans: {df['is_high_doc_scan'].sum()}")
            logger.info(f"   Out of Memory errors: {df['is_out_of_memory'].sum()}")
            logger.info(f"   Restart events: {df['is_restart'].sum()}")
            logger.info(f"   Memory limit exceeded: {df['is_memory_limit'].sum()}")
            
            # === NUMERIC VALUE EXTRACTION BAŞLANGIÇ ===
            
            # Duration extraction helper function
            def extract_duration(text):
                """Extract durationMillis from log message"""
                try:
                    match = re.search(r'"durationMillis":(\d+)', str(text))
                    return int(match.group(1)) if match else 0
                except:
                    return 0
            
            # Documents examined extraction helper function
            def extract_docs_examined(text):
                """Extract docsExamined count from log message"""
                try:
                    match = re.search(r'"docsExamined":(\d+)', str(text))
                    return int(match.group(1)) if match else 0
                except:
                    return 0
            
            # Keys examined extraction helper function
            def extract_keys_examined(text):
                """Extract keysExamined count from log message"""
                try:
                    match = re.search(r'"keysExamined":(\d+)', str(text))
                    return int(match.group(1)) if match else 0
                except:
                    return 0
            
            # Apply numeric extractions
            df['query_duration_ms'] = df['msg'].apply(extract_duration)
            df['docs_examined_count'] = df['msg'].apply(extract_docs_examined)
            df['keys_examined_count'] = df['msg'].apply(extract_keys_examined)
            
            # Performance score (yüksek değer = kötü performans)
            # COLLSCAN'de keys_examined 0 olur, bu da kötü performans göstergesi
            df['performance_score'] = np.where(
                df['is_collscan'] == 1,
                df['docs_examined_count'] * 2,  # COLLSCAN'de çarpan uygula
                df['docs_examined_count'] - df['keys_examined_count']
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
            
            logger.info(f"✅ Severity features extracted")
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
            
            logger.info(f"✅ Component features extracted")
            logger.info(f"   Unique components: {df['c'].nunique()}")
            logger.info(f"   Rare components: {len(rare_components)}")
            
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
            
            logger.info(f"✅ Combination features extracted")
            logger.info(f"   Rare combos: {df['is_rare_combo'].sum()}")
            
        except Exception as e:
            logger.error(f"Error in combination features: {e}")
            
        return df
    
    def extract_attr_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Attribute dictionary features"""
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
            
            logger.info(f"✅ Attr features extracted")
            if 'has_error_key' in df.columns:
                logger.info(f"   Error logs: {df['has_error_key'].sum()} ({df['has_error_key'].mean()*100:.1f}%)")
            
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
            
            # Auth success filter
            if self.filters.get('exclude_auth_success', True) and 'is_auth_success' in df.columns:
                filter_mask &= (df['is_auth_success'] == 0)
                
            # Reauthenticate filter
            if self.filters.get('exclude_reauthenticate', True) and 'is_reauthenticate' in df.columns:
                filter_mask &= (df['is_reauthenticate'] == 0)
            
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
        
        # Binary features
        binary_features = ['severity_W', 'is_rare_component', 'is_rare_combo', 'has_error_key', 
                          'is_auth_failure', 'is_drop_operation', 'is_rare_message',
                          'extreme_burst_flag', 'is_weekend', 'component_changed', 'has_many_attrs',
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