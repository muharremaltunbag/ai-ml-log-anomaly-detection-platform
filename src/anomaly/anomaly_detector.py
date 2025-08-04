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
        
        self.model = None
        self.is_trained = False
        self.feature_names = None
        self.training_stats = {}
        
        print(f"[DEBUG] Model config loaded: {self.model_config['type']}")
        logger.info(f"Anomaly detector initialized with {self.model_config['type']} model")
    
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
    
    def train(self, X: pd.DataFrame, save_model: bool = None) -> Dict[str, Any]:
        """
        Anomali modelini eğit
        
        Args:
            X: Feature matrix
            save_model: Modeli kaydet (None ise config'den al)
            
        Returns:
            Training sonuçları
        """
        print(f"[DEBUG] Starting training - Shape: {X.shape}, Features: {list(X.columns)}")
        logger.info(f"Training model on {X.shape[0]} samples with {X.shape[1]} features...")
        
        # Feature isimlerini sakla
        self.feature_names = list(X.columns)
        print(f"[DEBUG] Feature names stored: {len(self.feature_names)} features")
        
        # Model parametreleri
        params = self.model_config['parameters'].copy()
        print(f"[DEBUG] Model parameters: {params}")
        
        # Model oluştur
        if self.model_config['type'] == 'IsolationForest':
            print(f"[DEBUG] Creating IsolationForest model...")
            self.model = IsolationForest(**params)
        else:
            raise ValueError(f"Unknown model type: {self.model_config['type']}")
        
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
        
        return self.training_stats
    
    def predict(self, X: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
        """
        Anomali tahminleri yap
        
        Args:
            X: Feature matrix
            
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
        
        # Tahminler
        print(f"[DEBUG] Generating predictions...")
        predictions = self.model.predict(X)
        print(f"[DEBUG] Calculating anomaly scores...")
        anomaly_scores = self.model.score_samples(X)
        
        n_anomalies = (predictions == -1).sum()
        anomaly_rate = n_anomalies / len(predictions) * 100
        
        print(f"[DEBUG] Prediction results: {n_anomalies}/{len(predictions)} anomalies ({anomaly_rate:.1f}%)")
        logger.info(f"Predictions completed: {n_anomalies} anomalies ({anomaly_rate:.1f}%)")
        
        return predictions, anomaly_scores
    
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
            "component_analysis": {},
            "temporal_analysis": {},
            "feature_importance": {},
            "critical_anomalies": []
        }
        
        # Component bazlı analiz
        if 'c' in df.columns:
            print(f"[DEBUG] Analyzing component distribution...")
            anomaly_components = df[anomaly_mask]['c'].value_counts()
            total_components = df['c'].value_counts()
            
            for comp in anomaly_components.index[:10]:  # Top 10
                analysis["component_analysis"][comp] = {
                    "anomaly_count": int(anomaly_components[comp]),
                    "total_count": int(total_components[comp]),
                    "anomaly_rate": float(anomaly_components[comp] / total_components[comp] * 100)
                }
            print(f"[DEBUG] Component analysis completed for {len(analysis['component_analysis'])} components")
        
        # Temporal analiz
        if 'hour_of_day' in X.columns:
            print(f"[DEBUG] Analyzing temporal patterns...")
            anomaly_hours = df[anomaly_mask]['hour_of_day'].value_counts().sort_index()
            analysis["temporal_analysis"]["hourly_distribution"] = {
                int(hour): int(count) for hour, count in anomaly_hours.items()
            }
            analysis["temporal_analysis"]["peak_hours"] = list(anomaly_hours.nlargest(3).index.astype(int))
            print(f"[DEBUG] Temporal analysis completed - Peak hours: {analysis['temporal_analysis']['peak_hours']}")
        
        # Feature importance (binary features)
        print(f"[DEBUG] Calculating feature importance...")
        binary_features = ['severity_W', 'is_rare_component', 'is_rare_combo', 'has_error_key',
                          'is_drop_operation', 'is_rare_message', 'extreme_burst_flag',
                          'is_collscan', 'is_index_build', 'is_slow_query', 'is_high_doc_scan',
                          'is_shutdown', 'is_assertion', 'is_fatal', 'is_error', 'is_replication_issue']
        
        for feature in binary_features:
            if feature in X.columns:
                anomaly_rate = anomaly_data[feature].mean() * 100
                normal_rate = normal_data[feature].mean() * 100
                
                analysis["feature_importance"][feature] = {
                    "anomaly_rate": float(anomaly_rate),
                    "normal_rate": float(normal_rate),
                    "ratio": float(anomaly_rate / normal_rate) if normal_rate > 0 else float('inf')
                }
        print(f"[DEBUG] Feature importance calculated for {len(analysis['feature_importance'])} features")
        
        # En kritik anomaliler
        print(f"[DEBUG] Identifying critical anomalies...")
        top_anomaly_indices = np.argsort(anomaly_scores)[:20]  # En düşük 20 skor
        
        for idx in top_anomaly_indices:
            anomaly_info = {
                "index": int(idx),
                "score": float(anomaly_scores[idx]),
                "timestamp": str(df.iloc[idx]['timestamp']) if 'timestamp' in df.columns else None,
                "severity": df.iloc[idx]['s'] if 's' in df.columns else None,
                "component": df.iloc[idx]['c'] if 'c' in df.columns else None,
                "message": df.iloc[idx]['msg'][:100] if 'msg' in df.columns else None
            }
            analysis["critical_anomalies"].append(anomaly_info)
        
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
        
        # Security and critical alerts
        security_alerts = {}
        
        # DROP operasyonları kontrolü
        if 'is_drop_operation' in X.columns:
            print(f"[DEBUG] Checking for DROP operations...")
            drop_mask = (df['is_drop_operation'] == 1) & anomaly_mask
            if drop_mask.sum() > 0:
                print(f"[DEBUG] SECURITY ALERT: {drop_mask.sum()} DROP operations detected in anomalies!")
                security_alerts["drop_operations"] = {
                    "count": int(drop_mask.sum()),
                    "indices": list(np.where(drop_mask)[0][:10])
                }
        
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
        print(f"[DEBUG] Anomaly analysis completed")
        return analysis
    
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
                'config': self.config
            }
            
            joblib.dump(model_data, path)
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