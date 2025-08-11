#src\anomaly\anomaly_detector.py
"""
MongoDB Log Anomaly Detection Module
Isolation Forest ile anomali tespiti
"""
import pandas as pd
import numpy as np
from sklearn.ensemble import IsolationForest
import joblib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional

# YENİ: Message extraction import
from .log_reader import extract_mongodb_message

logger = logging.getLogger(__name__)

class MongoDBAnomalyDetector:
    """MongoDB logları için anomali tespiti"""
    
    def __init__(self, config_path: str = "config/anomaly_config.json"):
        """
        Anomaly Detector başlat
        
        Args:
            config_path: Konfigürasyon dosyası yolu
        """
        print(f"[DEBUG] Initializing anomaly detector with config: {config_path}")
        self.config = self._load_config(config_path)
        self.model_config = self.config['anomaly_detection']['model']
        self.output_config = self.config['anomaly_detection']['output']
        # Ensemble config
        self.ensemble_config = self.config['anomaly_detection'].get('ensemble', {
            'enabled': True,
            'rule_weight': 1.0,  # Rule override'ların ağırlığı
            'combine_method': 'override'  # 'override' veya 'weighted'
        })

        self.model = None
        self.is_trained = False
        self.feature_names = None
        self.training_stats = {}

        # Online Learning - Historical Pattern Buffer
        self.historical_data = {
            'features': None,  # Historical feature DataFrame
            'predictions': None,  # Historical predictions
            'scores': None,  # Historical anomaly scores
            'metadata': {
                'total_samples': 0,
                'anomaly_samples': 0,
                'last_update': None,
                'buffer_version': 1.0
            }
        }
        self.online_learning_config = self.config['anomaly_detection'].get('online_learning', {
            'enabled': True,
            'history_retention': 'full',  # 'full', 'sliding_window', 'smart_sampling'
            'max_history_size': None,  # None = unlimited for full history
            'update_frequency': 1000,  # Update model every N new samples
            'weight_decay': 0.95  # Eski verilere verilecek ağırlık
        })

        # Critical rules engine
        self.critical_rules = self._initialize_critical_rules()
        self.rule_stats = {'total_overrides': 0, 'rule_hits': {}}
        
        print(f"[DEBUG] Model config loaded: {self.model_config['type']}")
        print(f"[DEBUG] Ensemble mode: {self.ensemble_config.get('enabled', False)}")
        logger.info(f"Anomaly detector initialized with {self.model_config['type']} model")
    
    def _initialize_critical_rules(self) -> Dict[str, Any]:
        """
        Kritik anomali kurallarını tanımla
        
        Returns:
            Rule dictionary
        """
        print(f"[DEBUG] Initializing critical anomaly rules...")
        
        rules = {
            # Sistem kritik hatalar
            'system_failure': {
                'condition': lambda row: (
                    row.get('is_fatal', 0) == 1 or 
                    row.get('is_out_of_memory', 0) == 1 or
                    row.get('is_shutdown', 0) == 1
                ),
                'severity': 1.0,  # En yüksek
                'description': 'Critical system failure detected'
            },
            
            # Bellek sorunları
            'memory_crisis': {
                'condition': lambda row: (
                    row.get('is_out_of_memory', 0) == 1 or
                    row.get('is_memory_limit', 0) == 1
                ),
                'severity': 0.95,
                'description': 'Memory crisis detected'
            },
            
            # Performans kritik
            'performance_critical': {
                'condition': lambda row: (
                    row.get('is_collscan', 0) == 1 and 
                    row.get('docs_examined_count', 0) > 100000
                ),
                'severity': 0.85,
                'description': 'Critical performance issue'
            },
            
            # Multi-error burst
            'error_burst': {
                'condition': lambda row: (
                    row.get('is_error', 0) == 1 and
                    row.get('extreme_burst_flag', 0) == 1
                ),
                'severity': 0.90,
                'description': 'Error burst detected'
            },
            
            # Güvenlik kritik
            'security_alert': {
                'condition': lambda row: (
                    row.get('is_drop_operation', 0) == 1 or
                    row.get('is_assertion', 0) == 1
                ),
                'severity': 0.88,
                'description': 'Security-critical operation'
            },
            
            # Restart sonrası hatalar
            'post_restart_errors': {
                'condition': lambda row: (
                    row.get('is_restart', 0) == 1 or
                    (row.get('is_error', 0) == 1 and row.get('is_restart', 0) == 1)
                ),
                'severity': 0.85,
                'description': 'Post-restart anomaly'
            }
        }
        
        print(f"[DEBUG] Initialized {len(rules)} critical rules")
        return rules

    def _load_config(self, config_path: str) -> Dict:
        """Config dosyasını yükle"""
        try:
            print(f"[DEBUG] Loading config from: {config_path}")
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                print(f"[DEBUG] Config loaded successfully")
                return config
        except Exception as e:
            print(f"[DEBUG] Config load failed, using defaults: {e}")
            logger.error(f"Error loading config: {e}")
            # Varsayılan config
            return {
                "anomaly_detection": {
                    "model": {
                        "type": "IsolationForest",
                        "parameters": {
                            "contamination": 0.03,
                            "n_estimators": 300,
                            "random_state": 42
                        }
                    },
                    "output": {}
                }
            }

    def _combine_with_history(self, X_new: pd.DataFrame) -> pd.DataFrame:
        """
        Yeni veriyi historical data ile birleştir
        
        Args:
            X_new: Yeni feature matrix
            
        Returns:
            Birleştirilmiş feature matrix
        """
        print(f"[DEBUG] Combining new data with historical buffer...")
        
        try:
            # Historical features'ı al
            X_historical = self.historical_data['features']
            
            # Feature uyumluluğunu kontrol et
            if list(X_historical.columns) != list(X_new.columns):
                print(f"[DEBUG] WARNING: Feature mismatch detected!")
                print(f"[DEBUG] Historical features: {list(X_historical.columns)}")
                print(f"[DEBUG] New features: {list(X_new.columns)}")
                # Ortak feature'ları kullan
                common_features = list(set(X_historical.columns) & set(X_new.columns))
                X_historical = X_historical[common_features]
                X_new = X_new[common_features]
            
            # Full History Strategy - Tüm historical data'yı koru
            X_combined = pd.concat([X_historical, X_new], ignore_index=True)
            
            # Duplicate kontrolü (opsiyonel - performans için kapatılabilir)
            initial_size = len(X_combined)
            X_combined = X_combined.drop_duplicates()
            if initial_size != len(X_combined):
                print(f"[DEBUG] Removed {initial_size - len(X_combined)} duplicate samples")
            
            # İstatistikleri logla
            print(f"[DEBUG] Historical samples: {len(X_historical)}")
            print(f"[DEBUG] New samples: {len(X_new)}")
            print(f"[DEBUG] Combined samples: {len(X_combined)}")
            
            # Anomaly oranını hesapla (bilgi amaçlı)
            if self.historical_data['predictions'] is not None:
                historical_anomaly_rate = (self.historical_data['predictions'] == -1).mean() * 100
                print(f"[DEBUG] Historical anomaly rate: {historical_anomaly_rate:.2f}%")
            
            return X_combined
            
        except Exception as e:
            print(f"[DEBUG] Error combining with history: {e}")
            logger.error(f"Failed to combine with historical data: {e}")
            # Hata durumunda sadece yeni veriyi kullan
            return X_new

    def _calculate_sample_weights(self, X_combined: pd.DataFrame, X_new_size: int) -> np.ndarray:
        """
        Combined dataset için sample weight'leri hesapla
        Historical data'ya azalan weight, yeni data'ya full weight
        
        Args:
            X_combined: Birleştirilmiş dataset
            X_new_size: Yeni data'nın boyutu
            
        Returns:
            Sample weights array
        """
        total_size = len(X_combined)
        historical_size = total_size - X_new_size
        
        # Weight decay factor from config
        weight_decay = self.online_learning_config.get('weight_decay', 0.95)
        
        # Historical data weights (decayed)
        historical_weights = np.full(historical_size, weight_decay)
        
        # New data weights (full weight = 1.0)
        new_weights = np.ones(X_new_size)
        
        # Combine weights
        weights = np.concatenate([historical_weights, new_weights])
        
        print(f"[DEBUG] Sample weights - Historical: {weight_decay}, New: 1.0")
        
        return weights

    def train(self, X: pd.DataFrame, save_model: bool = None, incremental: bool = None) -> Dict[str, Any]:
        """
        Anomali modelini eğit (Online Learning desteği ile)
        
        Args:
            X: Feature matrix
            save_model: Modeli kaydet (None ise config'den al)
            incremental: Online learning kullan (None ise config'den al)
            
        Returns:
            Training sonuçları
        """
        print(f"[DEBUG] Starting training - Shape: {X.shape}, Features: {list(X.columns)}")
        logger.info(f"Training model on {X.shape[0]} samples with {X.shape[1]} features...")
        
        # Online learning kontrolü
        if incremental is None:
            incremental = self.online_learning_config.get('enabled', True)
        
        # Feature isimlerini sakla
        self.feature_names = list(X.columns)
        print(f"[DEBUG] Feature names stored: {len(self.feature_names)} features")
        
        # Historical data ile birleştir
        X_train = X.copy()
        training_mode = "new"
        
        if incremental and self.is_trained and self.historical_data['features'] is not None:
            print(f"[DEBUG] Online Learning Mode: Combining with historical data")
            print(f"[DEBUG] Historical samples: {len(self.historical_data['features'])}")
            print(f"[DEBUG] New samples: {len(X)}")
            
            # Historical data ile birleştir
            X_train = self._combine_with_history(X)
            training_mode = "incremental"
            
            print(f"[DEBUG] Combined dataset size: {X_train.shape}")
        else:
            print(f"[DEBUG] Standard training mode (no historical data)")
        
        # Model parametreleri
        params = self.model_config['parameters'].copy()
        print(f"[DEBUG] Model parameters: {params}")
        
        # Model oluştur veya mevcut modeli kullan
        if not incremental or not self.is_trained:
            # Yeni model oluştur
            if self.model_config['type'] == 'IsolationForest':
                print(f"[DEBUG] Creating NEW IsolationForest model...")
                self.model = IsolationForest(**params)
            else:
                raise ValueError(f"Unknown model type: {self.model_config['type']}")
        else:
            print(f"[DEBUG] Using existing model for incremental update")
            # Mevcut model parametrelerini güncelle (contamination gibi)
            if hasattr(self.model, 'contamination'):
                self.model.contamination = params.get('contamination', 0.03)
        
        # Eğitim
        print(f"[DEBUG] Starting model fitting...")
        start_time = datetime.now()
        self.model.fit(X)
        training_time = (datetime.now() - start_time).total_seconds()
        print(f"[DEBUG] Model fitting completed in {training_time:.2f} seconds")
        
        # Eğitim istatistikleri
        self.training_stats = {
            "n_samples": X.shape[0],
            "n_features": X.shape[1],
            "feature_names": self.feature_names,
            "training_time_seconds": training_time,
            "model_type": self.model_config['type'],
            "parameters": params,
            "timestamp": datetime.now().isoformat()
        }
        
        self.is_trained = True
        print(f"[DEBUG] Training completed - Model is now ready for predictions")
        logger.info(f"Model training completed in {training_time:.2f} seconds")
        
        # Model kaydetme
        if save_model is None:
            save_model = self.output_config.get('save_model', True)
            
        if save_model:
            print(f"[DEBUG] Saving model...")
            self.save_model()

        # Online Learning: Historical buffer'ı güncelle
        if incremental and self.online_learning_config.get('enabled', True):
            print(f"[DEBUG] Updating historical buffer...")
            self._update_historical_buffer(X, X_train, training_mode)
        
        return self.training_stats

    def _update_historical_buffer(self, X_new: pd.DataFrame, X_train: pd.DataFrame, 
                             training_mode: str) -> None:
        """
        Training sonrası historical buffer'ı güncelle
        
        Args:
            X_new: Bu training'de kullanılan yeni veri
            X_train: Training'de kullanılan tüm veri (historical + new)
            training_mode: 'new' veya 'incremental'
        """
        try:
            print(f"[DEBUG] Updating historical buffer - Mode: {training_mode}")
            
            # İlk training ise veya yeni training mode
            if training_mode == "new" or self.historical_data['features'] is None:
                # Direkt yeni veriyi historical olarak sakla
                self.historical_data['features'] = X_new.copy()
                
                # Predictions ve scores'u hesapla ve sakla
                predictions = self.model.predict(X_new)
                scores = self.model.score_samples(X_new)
                
                self.historical_data['predictions'] = predictions
                self.historical_data['scores'] = scores
                
            else:  # incremental mode
                # Full history strategy - tüm combined data'yı sakla
                self.historical_data['features'] = X_train.copy()
                
                # Yeni predictions ve scores hesapla
                predictions = self.model.predict(X_train)
                scores = self.model.score_samples(X_train)
                
                self.historical_data['predictions'] = predictions
                self.historical_data['scores'] = scores
            
            # Metadata güncelle
            self.historical_data['metadata']['total_samples'] = len(self.historical_data['features'])
            self.historical_data['metadata']['anomaly_samples'] = int((self.historical_data['predictions'] == -1).sum())
            self.historical_data['metadata']['last_update'] = datetime.now().isoformat()
            
            # İstatistikleri logla
            anomaly_rate = (self.historical_data['predictions'] == -1).mean() * 100
            print(f"[DEBUG] Historical buffer updated:")
            print(f"[DEBUG]   Total samples: {self.historical_data['metadata']['total_samples']}")
            print(f"[DEBUG]   Anomaly samples: {self.historical_data['metadata']['anomaly_samples']}")
            print(f"[DEBUG]   Anomaly rate: {anomaly_rate:.2f}%")
            
            # Bellek kullanımı uyarısı
            buffer_size_mb = self.historical_data['features'].memory_usage(deep=True).sum() / 1024 / 1024
            print(f"[DEBUG]   Buffer size: {buffer_size_mb:.2f} MB")
            
            if buffer_size_mb > 1000:  # 1 GB'dan büyükse uyar
                logger.warning(f"Historical buffer size is large: {buffer_size_mb:.2f} MB")
                
        except Exception as e:
            logger.error(f"Error updating historical buffer: {e}")
            print(f"[DEBUG] ERROR: Failed to update historical buffer: {e}")

    def predict(self, X: pd.DataFrame, df: Optional[pd.DataFrame] = None) -> Tuple[np.ndarray, np.ndarray]:
        """
        Anomali tahminleri yap (Ensemble model ile)
        
        Args:
            X: Feature matrix
            df: Original dataframe (rule engine için gerekli)
            
        Returns:
            (predictions, anomaly_scores): -1=anomaly, 1=normal ve anomaly skorları
        """
        print(f"[DEBUG] Starting prediction - Input shape: {X.shape}")
        if not self.is_trained:
            raise ValueError("Model is not trained yet!")
        
        # Feature sıralamasını kontrol et
        if list(X.columns) != self.feature_names:
            print(f"[DEBUG] Feature mismatch detected - reordering columns")
            logger.warning("Feature names mismatch, reordering...")
            X = X[self.feature_names]
            print(f"[DEBUG] Features reordered successfully")
        
        # ML tahminleri
        print(f"[DEBUG] Generating ML predictions...")
        predictions = self.model.predict(X)
        print(f"[DEBUG] Calculating anomaly scores...")
        anomaly_scores = self.model.score_samples(X)
        
        # Ensemble mode: Critical rules override
        if self.ensemble_config.get('enabled', True) and df is not None:
            print(f"[DEBUG] Applying ensemble rules...")
            predictions, anomaly_scores = self._apply_critical_rules(
                predictions, anomaly_scores, X, df
            )
        
        n_anomalies = (predictions == -1).sum()
        anomaly_rate = n_anomalies / len(predictions) * 100
        
        print(f"[DEBUG] Final prediction results: {n_anomalies}/{len(predictions)} anomalies ({anomaly_rate:.1f}%)")
        logger.info(f"Predictions completed: {n_anomalies} anomalies ({anomaly_rate:.1f}%)")
        
        return predictions, anomaly_scores
    
    def _apply_critical_rules(self, predictions: np.ndarray, anomaly_scores: np.ndarray,
                         X: pd.DataFrame, df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
        """
        Critical rule override'ları uygula
        
        Args:
            predictions: ML model tahminleri
            anomaly_scores: ML model skorları
            X: Feature matrix
            df: Original dataframe
            
        Returns:
            Updated (predictions, anomaly_scores)
        """
        print(f"[DEBUG] Applying critical rules to {len(predictions)} predictions")
        
        # Kopya oluştur
        ensemble_predictions = predictions.copy()
        ensemble_scores = anomaly_scores.copy()
        
        # Rule hit counters
        rule_overrides = 0
        
        # Her satır için rule kontrolü
        for idx in range(len(df)):
            row_features = X.iloc[idx].to_dict()
            
            # Her rule'u kontrol et
            for rule_name, rule_config in self.critical_rules.items():
                try:
                    # Rule condition'ı kontrol et
                    if rule_config['condition'](row_features):
                        # Eğer ML normal dedi ama rule anomali diyorsa override et
                        if ensemble_predictions[idx] == 1:  # Normal
                            ensemble_predictions[idx] = -1  # Anomaly'ye çevir
                            # Score'u da kritiklik seviyesine göre ayarla
                            ensemble_scores[idx] = min(ensemble_scores[idx], 
                                                      -rule_config['severity'])
                            rule_overrides += 1
                            
                            # İstatistik güncelle
                            if rule_name not in self.rule_stats['rule_hits']:
                                self.rule_stats['rule_hits'][rule_name] = 0
                            self.rule_stats['rule_hits'][rule_name] += 1
                            
                            print(f"[DEBUG] Rule override at idx {idx}: {rule_name} - {rule_config['description']}")
                            
                except Exception as e:
                    logger.warning(f"Error applying rule {rule_name}: {e}")
        
        self.rule_stats['total_overrides'] += rule_overrides
        print(f"[DEBUG] Total rule overrides in this batch: {rule_overrides}")
        
        return ensemble_predictions, ensemble_scores
        
    def analyze_anomalies(self, df: pd.DataFrame, X: pd.DataFrame, 
                         predictions: np.ndarray, anomaly_scores: np.ndarray) -> Dict[str, Any]:
        """
        Anomalileri detaylı analiz et
        
        Args:
            df: Enriched DataFrame
            X: Feature matrix
            predictions: Model tahminleri
            anomaly_scores: Anomali skorları
            
        Returns:
            Analiz sonuçları
        """
        print(f"[DEBUG] Starting anomaly analysis...")

        # ÖNEMLİ: security_alerts ve performance_alerts'i BAŞTA tanımla!
        security_alerts = {
            "drop_operations": {"count": 0, "indices": []},
            "out_of_memory": {"count": 0, "indices": []}, 
            "restarts": {"count": 0, "indices": []},
            "memory_limits": {"count": 0, "indices": []},
            "shutdowns": {"count": 0, "indices": []},
            "assertions": {"count": 0, "indices": []},
            "fatal_errors": {"count": 0, "indices": []}
        }

        performance_alerts = {}

        anomaly_mask = predictions == -1
        anomaly_data = X[anomaly_mask]
        normal_data = X[~anomaly_mask]
        
        print(f"[DEBUG] Anomaly mask created - {anomaly_mask.sum()} anomalies found")
        analysis = {
            "summary": {
                "total_logs": len(predictions),
                "n_anomalies": int(anomaly_mask.sum()),
                "anomaly_rate": float(anomaly_mask.mean() * 100),
                "score_range": {
                    "min": float(anomaly_scores.min()),
                    "max": float(anomaly_scores.max()),
                    "mean": float(anomaly_scores.mean())
                }
            },
            "temporal_analysis": {},
            "critical_anomalies": []
        }
        
        # Temporal analiz
        if 'hour_of_day' in X.columns:
            print(f"[DEBUG] Analyzing temporal patterns...")
            anomaly_hours = df[anomaly_mask]['hour_of_day'].value_counts().sort_index()
            analysis["temporal_analysis"]["hourly_distribution"] = {
                int(hour): int(count) for hour, count in anomaly_hours.items()
            }
            analysis["temporal_analysis"]["peak_hours"] = list(anomaly_hours.nlargest(3).index.astype(int))
            print(f"[DEBUG] Temporal analysis completed - Peak hours: {analysis['temporal_analysis']['peak_hours']}")
        
        
        # En kritik anomaliler - SEVERITY SKORUNA GÖRE SIRALA
        print(f"[DEBUG] Identifying critical anomalies with severity scores...")

        # Tüm anomalilerin severity skorlarını hesapla
        anomaly_indices = np.where(anomaly_mask)[0]
        anomaly_severities = []

        for idx in anomaly_indices:
            # Feature dict oluştur
            row_features = X.iloc[idx].to_dict()
            df_row = df.iloc[idx]
            
            # Severity hesapla
            severity_info = self.calculate_severity_score(
                idx, 
                anomaly_scores[idx], 
                row_features,
                df_row
            )
            
            # YENİ: Akıllı mesaj çıkarma ile formatted mesaj al
            log_entry_dict = df.iloc[idx].to_dict()
            full_message = extract_mongodb_message(log_entry_dict)
            
            # Fallback: Eğer extract_mongodb_message boş dönerse, raw_log kullan
            if not full_message or full_message in ['No detailed message available', 'Message extraction failed']:
                if 'raw_log' in df.columns and pd.notna(df.iloc[idx]['raw_log']):
                    full_message = str(df.iloc[idx]['raw_log'])
                elif 'msg' in df.columns and pd.notna(df.iloc[idx]['msg']):
                    full_message = str(df.iloc[idx]['msg'])
                else:
                    full_message = "No message available"
            
            # message_summary KULLANMA, direkt full_message kullan
            anomaly_severities.append({
                "index": int(idx),
                "severity_score": severity_info["score"],
                "severity_level": severity_info["level"],
                "severity_color": severity_info["color"],
                "anomaly_score": float(anomaly_scores[idx]),
                "timestamp": str(df.iloc[idx]['timestamp']) if 'timestamp' in df.columns else None,
                "severity": df.iloc[idx]['s'] if 's' in df.columns else None,
                "component": df.iloc[idx]['c'] if 'c' in df.columns else None,
                "message": full_message,  # TAM MESAJ
                "severity_factors": None  # Frontend'de gösterme
            })

        # Severity skoruna göre sırala ve top 20'yi al
        anomaly_severities.sort(key=lambda x: x['severity_score'], reverse=True)
        
        # Sadece severity score > 30 olanları al (MEDIUM, HIGH ve CRITICAL)
        critical_only = [a for a in anomaly_severities if a['severity_score'] > 30]
        
        # YENİ: En az 20 anomali garantisi
        if len(critical_only) < 20 and len(anomaly_severities) >= 20:
            # Eğer yeterli anomali yoksa threshold'u düşür
            critical_only = anomaly_severities[:20]  # En yüksek skorlu 20 tanesini al
            print(f"[DEBUG] Threshold lowered to ensure minimum 20 anomalies")
        elif len(critical_only) < 20 and len(anomaly_severities) > 0:
            # Eğer toplam anomali sayısı 20'den azsa, hepsini al
            critical_only = anomaly_severities
            print(f"[DEBUG] Taking all {len(anomaly_severities)} available anomalies")
        
        # Maximum 20 kritik anomali göster
        analysis["critical_anomalies"] = critical_only[:20]
        
        print(f"[DEBUG] Filtered to {len(critical_only)} critical anomalies (severity > 40)")
        print(f"[DEBUG] Showing top {min(20, len(critical_only))} critical anomalies")

        # Severity distribution ekle
        severity_dist = {
            "CRITICAL": sum(1 for a in anomaly_severities if a['severity_level'] == 'CRITICAL'),
            "HIGH": sum(1 for a in anomaly_severities if a['severity_level'] == 'HIGH'),
            "MEDIUM": sum(1 for a in anomaly_severities if a['severity_level'] == 'MEDIUM'),
            "LOW": sum(1 for a in anomaly_severities if a['severity_level'] == 'LOW'),
            "INFO": sum(1 for a in anomaly_severities if a['severity_level'] == 'INFO')
        }
        analysis["severity_distribution"] = severity_dist

        print(f"[DEBUG] Severity analysis completed - Distribution: {severity_dist}")
        
        # Performance critical logs analysis
        print(f"[DEBUG] Analyzing performance critical logs...")
        performance_alerts = {}
        
        # COLLSCAN analysis
        if 'is_collscan' in X.columns:
            collscan_mask = (df['is_collscan'] == 1) & anomaly_mask
            if collscan_mask.sum() > 0:
                print(f"[DEBUG] PERFORMANCE ALERT: {collscan_mask.sum()} COLLSCAN queries in anomalies!")
                
                # Get average documents examined for COLLSCAN queries
                if 'docs_examined_count' in df.columns:
                    avg_docs = df[collscan_mask]['docs_examined_count'].mean()
                    max_docs = df[collscan_mask]['docs_examined_count'].max()
                else:
                    avg_docs = None
                    max_docs = None
                
                performance_alerts["collscan"] = {
                    "count": int(collscan_mask.sum()),
                    "indices": list(np.where(collscan_mask)[0][:10]),
                    "avg_docs_examined": float(avg_docs) if avg_docs else None,
                    "max_docs_examined": float(max_docs) if max_docs else None
                }
        
        # Slow query analysis
        if 'is_slow_query' in X.columns:
            slow_mask = (df['is_slow_query'] == 1) & anomaly_mask
            if slow_mask.sum() > 0:
                print(f"[DEBUG] PERFORMANCE ALERT: {slow_mask.sum()} slow queries in anomalies!")
                
                # Get query durations
                if 'query_duration_ms' in df.columns:
                    avg_duration = df[slow_mask]['query_duration_ms'].mean()
                    max_duration = df[slow_mask]['query_duration_ms'].max()
                else:
                    avg_duration = None
                    max_duration = None
                
                performance_alerts["slow_queries"] = {
                    "count": int(slow_mask.sum()),
                    "indices": list(np.where(slow_mask)[0][:10]),
                    "avg_duration_ms": float(avg_duration) if avg_duration else None,
                    "max_duration_ms": float(max_duration) if max_duration else None
                }
        
        # Index build analysis
        if 'is_index_build' in X.columns:
            index_mask = (df['is_index_build'] == 1) & anomaly_mask
            if index_mask.sum() > 0:
                print(f"[DEBUG] INDEX ALERT: {index_mask.sum()} index builds in anomalies!")
                performance_alerts["index_builds"] = {
                    "count": int(index_mask.sum()),
                    "indices": list(np.where(index_mask)[0][:10])
                }
        
        # High document scan analysis
        if 'is_high_doc_scan' in X.columns:
            high_scan_mask = (df['is_high_doc_scan'] == 1) & anomaly_mask
            if high_scan_mask.sum() > 0:
                print(f"[DEBUG] SCAN ALERT: {high_scan_mask.sum()} high document scans in anomalies!")
                performance_alerts["high_doc_scans"] = {
                    "count": int(high_scan_mask.sum()),
                    "indices": list(np.where(high_scan_mask)[0][:10])
                }
        
        # Add performance alerts to analysis
        if performance_alerts:
            analysis["performance_alerts"] = performance_alerts
            print(f"[DEBUG] Performance analysis completed - {len(performance_alerts)} alert types found")
            
        
        # Shutdown detection
        if 'is_shutdown' in X.columns:
            shutdown_mask = (df['is_shutdown'] == 1) & anomaly_mask
            if shutdown_mask.sum() > 0:
                print(f"[DEBUG] CRITICAL: {shutdown_mask.sum()} shutdown events in anomalies!")
                security_alerts["shutdowns"] = {
                    "count": int(shutdown_mask.sum()),
                    "indices": list(np.where(shutdown_mask)[0][:10])
                }
        
        # Assertion errors
        if 'is_assertion' in X.columns:
            assertion_mask = (df['is_assertion'] == 1) & anomaly_mask
            if assertion_mask.sum() > 0:
                print(f"[DEBUG] ERROR ALERT: {assertion_mask.sum()} assertion errors in anomalies!")
                security_alerts["assertions"] = {
                    "count": int(assertion_mask.sum()),
                    "indices": list(np.where(assertion_mask)[0][:10])
                }
        
        # Fatal errors
        if 'is_fatal' in X.columns:
            fatal_mask = (df['is_fatal'] == 1) & anomaly_mask
            if fatal_mask.sum() > 0:
                print(f"[DEBUG] FATAL ALERT: {fatal_mask.sum()} fatal errors in anomalies!")
                security_alerts["fatal_errors"] = {
                    "count": int(fatal_mask.sum()),
                    "indices": list(np.where(fatal_mask)[0][:10])
                }

        # Out of Memory errors
        if 'is_out_of_memory' in X.columns:
            oom_mask = (df['is_out_of_memory'] == 1) & anomaly_mask
            if oom_mask.sum() > 0:
                print(f"[DEBUG] MEMORY ALERT: {oom_mask.sum()} Out of Memory errors in anomalies!")
                security_alerts["out_of_memory"] = {
                    "count": int(oom_mask.sum()),
                    "indices": list(np.where(oom_mask)[0][:10])
                }

        # Restart events
        if 'is_restart' in X.columns:
            restart_mask = (df['is_restart'] == 1) & anomaly_mask
            if restart_mask.sum() > 0:
                print(f"[DEBUG] RESTART ALERT: {restart_mask.sum()} restart events in anomalies!")
                security_alerts["restarts"] = {
                    "count": int(restart_mask.sum()),
                    "indices": list(np.where(restart_mask)[0][:10])
                }

        # Memory limit exceeded
        if 'is_memory_limit' in X.columns:
            mem_limit_mask = (df['is_memory_limit'] == 1) & anomaly_mask
            if mem_limit_mask.sum() > 0:
                print(f"[DEBUG] MEMORY LIMIT ALERT: {mem_limit_mask.sum()} memory limit exceeded errors in anomalies!")
                security_alerts["memory_limits"] = {
                    "count": int(mem_limit_mask.sum()),
                    "indices": list(np.where(mem_limit_mask)[0][:10])
                }

        # Add security alerts to analysis
        if security_alerts:
            analysis["security_alerts"] = security_alerts
            print(f"[DEBUG] Security analysis completed - {len(security_alerts)} alert types found")

        # Ensemble stats'i summary içine ekle (frontend buradan alıyor)
        if self.ensemble_config:
            analysis['summary']['ensemble_stats'] = {
                'total_rule_overrides': self.rule_stats['total_overrides'],
                'rules_active': len(self.critical_rules),
                'ensemble_method': 'override',
                'rule_hits': dict(self.rule_stats['rule_hits'])
            }
            print("[DEBUG] Ensemble stats added to summary")

        print(f"[DEBUG] Anomaly analysis completed")
        return analysis
    def calculate_severity_score(self, anomaly_idx: int, anomaly_score: float, 
                               row_features: Dict, df_row: pd.Series) -> Dict[str, Any]:
        """
        Anomali için severity skoru hesapla (0-100)
        
        Args:
            anomaly_idx: Anomali index
            anomaly_score: ML anomaly score (-1 to 0)
            row_features: Feature dictionary
            df_row: Original dataframe row
            
        Returns:
            Severity bilgileri
        """
        severity_score = 0
        factors = []
        
        # 1. Base ML Score (0-40 puan)
        # ML skoru -1'e yaklaştıkça daha yüksek
        ml_contribution = abs(anomaly_score) * 40
        severity_score += ml_contribution
        factors.append(f"ML Score: +{ml_contribution:.1f}")
        
        # 2. Component Criticality (0-20 puan)
        component_scores = {
            'REPL': 20,      # Replikasyon kritik
            'ACCESS': 18,    # Erişim kontrolü kritik
            'STORAGE': 15,   # Storage önemli
            'COMMAND': 12,   # Command önemli
            'NETWORK': 10,   # Network orta
            'QUERY': 8,      # Query normal
            'INDEX': 8,      # Index normal
            '-': 5           # Diğer
        }
        
        component = df_row.get('c', '-')
        comp_score = component_scores.get(component, 5)
        severity_score += comp_score
        factors.append(f"Component ({component}): +{comp_score}")
        
        # 3. Critical Features (0-30 puan)
        feature_score = 0
        
        # Fatal errors - en kritik
        if row_features.get('is_fatal', 0) == 1:
            feature_score += 30
            factors.append("Fatal Error: +30")
        # Out of memory
        elif row_features.get('is_out_of_memory', 0) == 1:
            feature_score += 28
            factors.append("Out of Memory: +28")
        # Shutdown
        elif row_features.get('is_shutdown', 0) == 1:
            feature_score += 25
            factors.append("Shutdown: +25")
        # Drop operation
        elif row_features.get('is_drop_operation', 0) == 1:
            feature_score += 25
            factors.append("DROP Operation: +25")
        # Assertion failure
        elif row_features.get('is_assertion', 0) == 1:
            feature_score += 22
            factors.append("Assertion Failure: +22")
        # Memory limit
        elif row_features.get('is_memory_limit', 0) == 1:
            feature_score += 20
            factors.append("Memory Limit: +20")
        # Restart
        elif row_features.get('is_restart', 0) == 1:
            feature_score += 18
            factors.append("Restart Event: +18")
        # Slow query with high docs
        elif (row_features.get('is_slow_query', 0) == 1 and 
              row_features.get('docs_examined_count', 0) > 100000):
            feature_score += 15
            factors.append("Slow Query (High Docs): +15")
        # COLLSCAN
        elif row_features.get('is_collscan', 0) == 1:
            feature_score += 12
            factors.append("COLLSCAN: +12")
        # Regular slow query
        elif row_features.get('is_slow_query', 0) == 1:
            feature_score += 8
            factors.append("Slow Query: +8")
        
        severity_score += feature_score
        
        # 4. Temporal Factor (0-10 puan)
        # Peak saatlerde daha kritik
        hour = row_features.get('hour_of_day', 0)
        if hour in [8, 9, 10, 17, 18, 19]:  # İş saatleri
            temporal_score = 10
            factors.append(f"Peak Hour ({hour}:00): +10")
        elif hour in [0, 1, 2, 3, 4, 5]:  # Gece
            temporal_score = 5
            factors.append(f"Night Hour ({hour}:00): +5")
        else:
            temporal_score = 7
            factors.append(f"Normal Hour ({hour}:00): +7")
        
        severity_score += temporal_score
        
        # 5. Rule Engine Bonus (ek 20 puan)
        if anomaly_score == -1.0:  # Rule override edilmiş
            severity_score += 20
            factors.append("Rule Override: +20")
        
        # Normalize to 0-100
        severity_score = min(100, max(0, severity_score))
        
        # Severity level
        if severity_score >= 80:
            level = "CRITICAL"
            color = "#e74c3c"
        elif severity_score >= 60:
            level = "HIGH"
            color = "#e67e22"
        elif severity_score >= 40:
            level = "MEDIUM"
            color = "#f39c12"
        elif severity_score >= 20:
            level = "LOW"
            color = "#3498db"
        else:
            level = "INFO"
            color = "#95a5a6"
        
        return {
            "score": severity_score,
            "level": level,
            "color": color,
            "factors": factors
        }
        
    def export_results(self, df: pd.DataFrame, predictions: np.ndarray, 
                      anomaly_scores: np.ndarray, analysis: Dict[str, Any]) -> Dict[str, str]:
        """
        Sonuçları dışa aktar
        
        Args:
            df: Enriched DataFrame
            predictions: Model tahminleri
            anomaly_scores: Anomali skorları
            analysis: Analiz sonuçları
            
        Returns:
            Export edilen dosya yolları
        """
        export_paths = {}
        
        try:
            # Timestamp ekle
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Anomalileri DataFrame'e ekle
            df['anomaly_score'] = anomaly_scores
            df['is_anomaly'] = predictions == -1
            
            # Anomalileri CSV olarak export
            if self.output_config.get('export_anomalies', True):
                anomaly_path = self.output_config.get('anomaly_path', 'output/anomalies_{timestamp}.csv')
                anomaly_path = anomaly_path.replace('{timestamp}', timestamp)
                
                # Output klasörünü oluştur
                Path(anomaly_path).parent.mkdir(parents=True, exist_ok=True)
                
                # Sadece anomalileri export et
                anomaly_df = df[df['is_anomaly']].sort_values('anomaly_score')
                anomaly_df.to_csv(anomaly_path, index=False)
                export_paths['anomalies'] = anomaly_path
                
                logger.info(f"Anomalies exported to: {anomaly_path}")
            
            # Analiz sonuçlarını JSON olarak export
            analysis_path = f"output/anomaly_analysis_{timestamp}.json"
            Path(analysis_path).parent.mkdir(parents=True, exist_ok=True)
            
            with open(analysis_path, 'w', encoding='utf-8') as f:
                json.dump(analysis, f, indent=2, ensure_ascii=False)
            
            export_paths['analysis'] = analysis_path
            logger.info(f"Analysis exported to: {analysis_path}")
            
        except Exception as e:
            logger.error(f"Error exporting results: {e}")
        
        return export_paths
    
    def save_model(self, path: str = None) -> str:
        """
        Modeli kaydet
        
        Args:
            path: Model dosya yolu (None ise config'den al)
            
        Returns:
            Kaydedilen dosya yolu
        """
        if not self.is_trained:
            raise ValueError("Model is not trained yet!")
        
        if path is None:
            path = self.output_config.get('model_path', 'models/isolation_forest.pkl')
        
        try:
            print(f"[DEBUG] Saving model to: {path}")
            # Klasörü oluştur
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            
            # Model ve metadata'yı kaydet
            model_data = {
                'model': self.model,
                'feature_names': self.feature_names,
                'training_stats': self.training_stats,
                'config': self.config,
                # Online Learning - Historical Buffer
                'historical_data': self.historical_data if self.online_learning_config.get('enabled', True) else None,
                'online_learning_config': self.online_learning_config,
                'model_version': '2.0'  # Version tracking for compatibility
            }

            # Historical buffer size kontrolü
            if self.historical_data['features'] is not None:
                buffer_size_mb = self.historical_data['features'].memory_usage(deep=True).sum() / 1024 / 1024
                print(f"[DEBUG] Saving historical buffer: {buffer_size_mb:.2f} MB")
                
                # Büyük dosya uyarısı
                if buffer_size_mb > 500:
                    logger.warning(f"Large model file warning: Historical buffer is {buffer_size_mb:.2f} MB")

            joblib.dump(model_data, path)

            # Dosya boyutu bilgisi
            file_size_mb = Path(path).stat().st_size / 1024 / 1024
            print(f"[DEBUG] Model file saved: {file_size_mb:.2f} MB")
            print(f"[DEBUG] Model saved successfully")
            logger.info(f"Model saved to: {path}")
            
            return path
            
        except Exception as e:
            print(f"[DEBUG] Error saving model: {e}")
            logger.error(f"Error saving model: {e}")
            raise
    
    def load_model(self, path: str = None) -> bool:
        """
        Modeli yükle
        
        Args:
            path: Model dosya yolu (None ise config'den al)
            
        Returns:
            Başarılı olup olmadığı
        """
        if path is None:
            path = self.output_config.get('model_path', 'models/isolation_forest.pkl')
        
        try:
            print(f"[DEBUG] Loading model from: {path}")
            if not Path(path).exists():
                print(f"[DEBUG] Model file not found: {path}")
                logger.error(f"Model file not found: {path}")
                return False
            # Model ve metadata'yı yükle
            model_data = joblib.load(path)
            
            self.model = model_data['model']
            self.feature_names = model_data['feature_names']
            self.training_stats = model_data.get('training_stats', {})
            
            # Online Learning - Historical Buffer'ı yükle
            model_version = model_data.get('model_version', '1.0')
            print(f"[DEBUG] Loading model version: {model_version}")
            
            if model_version >= '2.0' and 'historical_data' in model_data:
                if model_data['historical_data'] is not None:
                    self.historical_data = model_data['historical_data']
                    print(f"[DEBUG] Historical buffer loaded:")
                    print(f"[DEBUG]   Total samples: {self.historical_data['metadata']['total_samples']}")
                    print(f"[DEBUG]   Last update: {self.historical_data['metadata']['last_update']}")
                    
                    # Buffer size info
                    if self.historical_data['features'] is not None:
                        buffer_size_mb = self.historical_data['features'].memory_usage(deep=True).sum() / 1024 / 1024
                        print(f"[DEBUG]   Buffer size: {buffer_size_mb:.2f} MB")
                else:
                    print(f"[DEBUG] No historical buffer found in model file")
            else:
                print(f"[DEBUG] Legacy model format - no historical buffer")
                # Legacy model için boş buffer initialize et
                self.historical_data = {
                    'features': None,
                    'predictions': None,
                    'scores': None,
                    'metadata': {
                        'total_samples': 0,
                        'anomaly_samples': 0,
                        'last_update': None,
                        'buffer_version': 1.0
                    }
                }
            
            # Online learning config'i güncelle
            if 'online_learning_config' in model_data:
                self.online_learning_config.update(model_data['online_learning_config'])
            
            self.is_trained = True
            print(f"[DEBUG] Model loaded successfully - Features: {len(self.feature_names)}")
            logger.info(f"Model loaded from: {path}")
            
            return True
            
        except Exception as e:
            print(f"[DEBUG] Error loading model: {e}")
            logger.error(f"Error loading model: {e}")
            return False
    
    def get_model_info(self) -> Dict[str, Any]:
        """Model bilgilerini döndür"""
        info = {
            "is_trained": self.is_trained,
            "model_type": self.model_config['type'],
            "parameters": self.model_config['parameters']
        }
        
        if self.is_trained:
            info.update({
                "feature_names": self.feature_names,
                "n_features": len(self.feature_names) if self.feature_names else 0,
                "training_stats": self.training_stats
            })
        
        return info
    
    def get_historical_buffer_info(self) -> Dict[str, Any]:
        """
        Historical buffer bilgilerini döndür
        
        Returns:
            Buffer istatistikleri
        """
        info = {
            "enabled": self.online_learning_config.get('enabled', False),
            "retention_strategy": self.online_learning_config.get('history_retention', 'none'),
            "buffer_stats": {
                "total_samples": 0,
                "anomaly_samples": 0,
                "anomaly_rate": 0.0,
                "size_mb": 0.0,
                "last_update": None
            }
        }
        
        if self.historical_data['features'] is not None:
            # Buffer istatistikleri
            info["buffer_stats"]["total_samples"] = self.historical_data['metadata']['total_samples']
            info["buffer_stats"]["anomaly_samples"] = self.historical_data['metadata']['anomaly_samples']
            info["buffer_stats"]["anomaly_rate"] = (
                self.historical_data['metadata']['anomaly_samples'] / 
                self.historical_data['metadata']['total_samples'] * 100
                if self.historical_data['metadata']['total_samples'] > 0 else 0
            )
            info["buffer_stats"]["last_update"] = self.historical_data['metadata']['last_update']
            
            # Buffer boyutu
            buffer_size_mb = self.historical_data['features'].memory_usage(deep=True).sum() / 1024 / 1024
            info["buffer_stats"]["size_mb"] = round(buffer_size_mb, 2)
            
            # Feature breakdown
            if self.historical_data['predictions'] is not None:
                # Component distribution in buffer
                if 'c' in self.historical_data['features'].columns:
                    component_dist = self.historical_data['features']['c'].value_counts().to_dict()
                    info["buffer_stats"]["component_distribution"] = {
                        str(k): int(v) for k, v in list(component_dist.items())[:10]
                    }
                
                # Temporal distribution
                if 'hour_of_day' in self.historical_data['features'].columns:
                    hour_dist = self.historical_data['features']['hour_of_day'].value_counts().sort_index().to_dict()
                    info["buffer_stats"]["hourly_distribution"] = {
                        int(k): int(v) for k, v in hour_dist.items()
                    }
        
        return info

    def clear_historical_buffer(self) -> bool:
        """
        Historical buffer'ı temizle (reset)
        
        Returns:
            Başarılı olup olmadığı
        """
        try:
            print(f"[DEBUG] Clearing historical buffer...")
            
            # Buffer'ı sıfırla
            self.historical_data = {
                'features': None,
                'predictions': None,
                'scores': None,
                'metadata': {
                    'total_samples': 0,
                    'anomaly_samples': 0,
                    'last_update': None,
                    'buffer_version': 1.0
                }
            }
            
            print(f"[DEBUG] Historical buffer cleared successfully")
            logger.info("Historical buffer cleared")
            return True
            
        except Exception as e:
            print(f"[DEBUG] Error clearing historical buffer: {e}")
            logger.error(f"Error clearing historical buffer: {e}")
            return False

    def validate_online_learning(self) -> Dict[str, Any]:
        """
        Online learning sisteminin doğru çalıştığını kontrol et
        
        Returns:
            Validation sonuçları
        """
        validation_results = {
            "status": "OK",
            "checks": {},
            "warnings": [],
            "errors": []
        }
        
        # 1. Config kontrolü
        validation_results["checks"]["config_loaded"] = self.online_learning_config.get('enabled', False)
        if not validation_results["checks"]["config_loaded"]:
            validation_results["warnings"].append("Online learning is disabled in config")
        
        # 2. Historical buffer kontrolü
        has_buffer = self.historical_data['features'] is not None
        validation_results["checks"]["has_historical_buffer"] = has_buffer
        
        if has_buffer:
            # Buffer size kontrolü
            buffer_size_mb = self.historical_data['features'].memory_usage(deep=True).sum() / 1024 / 1024
            validation_results["checks"]["buffer_size_mb"] = round(buffer_size_mb, 2)
            
            # Size warnings
            warn_size = self.online_learning_config.get('buffer_management', {}).get('warn_size_mb', 500)
            max_size = self.online_learning_config.get('buffer_management', {}).get('max_size_mb', 2000)
            
            if buffer_size_mb > max_size:
                validation_results["errors"].append(f"Buffer size ({buffer_size_mb:.0f}MB) exceeds maximum ({max_size}MB)")
                validation_results["status"] = "ERROR"
            elif buffer_size_mb > warn_size:
                validation_results["warnings"].append(f"Buffer size ({buffer_size_mb:.0f}MB) is large (warning at {warn_size}MB)")
                if validation_results["status"] == "OK":
                    validation_results["status"] = "WARNING"
            
            # Feature consistency kontrolü
            if self.feature_names:
                buffer_features = set(self.historical_data['features'].columns)
                model_features = set(self.feature_names)
                
                missing_features = model_features - buffer_features
                extra_features = buffer_features - model_features
                
                validation_results["checks"]["feature_consistency"] = len(missing_features) == 0 and len(extra_features) == 0
                
                if missing_features:
                    validation_results["errors"].append(f"Missing features in buffer: {missing_features}")
                    validation_results["status"] = "ERROR"
                if extra_features:
                    validation_results["warnings"].append(f"Extra features in buffer: {extra_features}")
        
        # 3. Model state kontrolü
        validation_results["checks"]["model_trained"] = self.is_trained
        validation_results["checks"]["model_type"] = self.model_config['type']
        
        # 4. Performance metrics
        if has_buffer and self.historical_data['predictions'] is not None:
            anomaly_rate = (self.historical_data['predictions'] == -1).mean() * 100
            validation_results["checks"]["historical_anomaly_rate"] = round(anomaly_rate, 2)
            
            # Anomaly rate kontrolü
            if anomaly_rate > 10:
                validation_results["warnings"].append(f"High historical anomaly rate: {anomaly_rate:.1f}%")
            elif anomaly_rate < 0.1:
                validation_results["warnings"].append(f"Very low historical anomaly rate: {anomaly_rate:.1f}%")
        
        return validation_results