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
        self.config = self._load_config(config_path)
        self.model_config = self.config['anomaly_detection']['model']
        self.output_config = self.config['anomaly_detection']['output']
        
        self.model = None
        self.is_trained = False
        self.feature_names = None
        self.training_stats = {}
        
        logger.info(f"Anomaly detector initialized with {self.model_config['type']} model")
    
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
        logger.info(f"Training model on {X.shape[0]} samples with {X.shape[1]} features...")
        
        # Feature isimlerini sakla
        self.feature_names = list(X.columns)
        
        # Model parametreleri
        params = self.model_config['parameters'].copy()
        
        # Model oluştur
        if self.model_config['type'] == 'IsolationForest':
            self.model = IsolationForest(**params)
        else:
            raise ValueError(f"Unknown model type: {self.model_config['type']}")
        
        # Eğitim
        start_time = datetime.now()
        self.model.fit(X)
        training_time = (datetime.now() - start_time).total_seconds()
        
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
        logger.info(f"Model training completed in {training_time:.2f} seconds")
        
        # Model kaydetme
        if save_model is None:
            save_model = self.output_config.get('save_model', True)
            
        if save_model:
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
        if not self.is_trained:
            raise ValueError("Model is not trained yet!")
        
        # Feature sıralamasını kontrol et
        if list(X.columns) != self.feature_names:
            logger.warning("Feature names mismatch, reordering...")
            X = X[self.feature_names]
        
        # Tahminler
        predictions = self.model.predict(X)
        anomaly_scores = self.model.score_samples(X)
        
        n_anomalies = (predictions == -1).sum()
        anomaly_rate = n_anomalies / len(predictions) * 100
        
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
        anomaly_mask = predictions == -1
        anomaly_data = X[anomaly_mask]
        normal_data = X[~anomaly_mask]
        
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
            anomaly_components = df[anomaly_mask]['c'].value_counts()
            total_components = df['c'].value_counts()
            
            for comp in anomaly_components.index[:10]:  # Top 10
                analysis["component_analysis"][comp] = {
                    "anomaly_count": int(anomaly_components[comp]),
                    "total_count": int(total_components[comp]),
                    "anomaly_rate": float(anomaly_components[comp] / total_components[comp] * 100)
                }
        
        # Temporal analiz
        if 'hour_of_day' in X.columns:
            anomaly_hours = df[anomaly_mask]['hour_of_day'].value_counts().sort_index()
            analysis["temporal_analysis"]["hourly_distribution"] = {
                int(hour): int(count) for hour, count in anomaly_hours.items()
            }
            analysis["temporal_analysis"]["peak_hours"] = list(anomaly_hours.nlargest(3).index.astype(int))
        
        # Feature importance (binary features)
        binary_features = ['severity_W', 'is_rare_component', 'is_rare_combo', 'has_error_key',
                          'is_drop_operation', 'is_rare_message', 'extreme_burst_flag']
        
        for feature in binary_features:
            if feature in X.columns:
                anomaly_rate = anomaly_data[feature].mean() * 100
                normal_rate = normal_data[feature].mean() * 100
                
                analysis["feature_importance"][feature] = {
                    "anomaly_rate": float(anomaly_rate),
                    "normal_rate": float(normal_rate),
                    "ratio": float(anomaly_rate / normal_rate) if normal_rate > 0 else float('inf')
                }
        
        # En kritik anomaliler
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
        
        # DROP operasyonları kontrolü
        if 'is_drop_operation' in X.columns:
            drop_mask = (df['is_drop_operation'] == 1) & anomaly_mask
            if drop_mask.sum() > 0:
                analysis["security_alerts"] = {
                    "drop_operations": {
                        "count": int(drop_mask.sum()),
                        "indices": list(np.where(drop_mask)[0][:10])  # İlk 10
                    }
                }
        
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
            logger.info(f"Model saved to: {path}")
            
            return path
            
        except Exception as e:
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
            if not Path(path).exists():
                logger.error(f"Model file not found: {path}")
                return False
            
            # Model ve metadata'yı yükle
            model_data = joblib.load(path)
            
            self.model = model_data['model']
            self.feature_names = model_data['feature_names']
            self.training_stats = model_data.get('training_stats', {})
            
            self.is_trained = True
            logger.info(f"Model loaded from: {path}")
            
            return True
            
        except Exception as e:
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