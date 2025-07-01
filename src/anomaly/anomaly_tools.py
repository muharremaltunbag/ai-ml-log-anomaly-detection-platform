#src/anomaly/anomaly_tools.py
"""
MongoDB Anomaly Detection LangChain Tools
Anomali tespiti için LangChain tool tanımları
"""
from typing import Dict, Any, List, Optional
from langchain.tools import Tool, StructuredTool
from langchain.pydantic_v1 import BaseModel, Field
import json
import logging
from datetime import datetime, timedelta
import pandas as pd
from pathlib import Path
import os

from .log_reader import MongoDBLogReader
from .feature_engineer import MongoDBFeatureEngineer
from .anomaly_detector import MongoDBAnomalyDetector

logger = logging.getLogger(__name__)

class AnomalyDetectionTools:
    """MongoDB log anomali tespiti için LangChain tool'ları"""
    
    def __init__(self, config_path: str = "config/anomaly_config.json", environment: str = "test"):
        """
        Anomaly Detection Tools başlat
        
        Args:
            config_path: Config dosya yolu
            environment: Çalışma ortamı (test/production)
        """
        self.config_path = config_path
        self.environment = environment
        
        # Config yükle
        self._load_config()
        
        # Modülleri başlat
        self.log_reader = None
        self.feature_engineer = MongoDBFeatureEngineer(config_path)
        self.detector = MongoDBAnomalyDetector(config_path)
        
        # Son analiz sonuçlarını sakla
        self.last_analysis = None
        
        logger.info(f"AnomalyDetectionTools initialized for {environment} environment")
    
    def _load_config(self):
        """Config dosyasını yükle"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                full_config = json.load(f)
                self.config = full_config['environments'][self.environment]
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            self.config = {}
    
    def _format_result(self, result: Dict[str, Any], operation: str) -> str:
        """Sonuçları MongoDB Agent formatına uygun şekilde formatla"""
        try:
            if "error" in result:
                return json.dumps({
                    "durum": "hata",
                    "işlem": operation,
                    "açıklama": result.get("error", "Bilinmeyen hata"),
                    "sonuç": None
                }, ensure_ascii=False, indent=2)
            
            return json.dumps({
                "durum": "başarılı",
                "işlem": operation,
                "açıklama": result.get("description", f"{operation} işlemi tamamlandı"),
                "sonuç": result.get("data", result),
                "öneriler": result.get("suggestions", [])
            }, ensure_ascii=False, indent=2)
            
        except Exception as e:
            logger.error(f"Format hatası: {e}")
            return json.dumps({
                "durum": "hata",
                "işlem": operation,
                "açıklama": f"Format hatası: {str(e)}",
                "sonuç": str(result)
            }, ensure_ascii=False, indent=2)
    
    def analyze_mongodb_logs(self, args_input) -> str:
        """MongoDB loglarında anomali analizi yap"""
        try:
            # Argümanları parse et
            if isinstance(args_input, str):
                try:
                    args_dict = json.loads(args_input)
                except:
                    args_dict = {"time_range": "last_hour", "threshold": 0.03}
            else:
                args_dict = args_input
            
            time_range = args_dict.get("time_range", "last_hour")
            threshold = args_dict.get("threshold", 0.03)
            
            # Zaman aralığını belirle
            last_hours = None
            if time_range == "last_hour":
                last_hours = 1
            elif time_range == "last_day":
                last_hours = 24
            elif time_range == "last_week":
                last_hours = 168
            
            # Log reader'ı başlat
            if self.log_reader is None:
                log_path = self.config['data_sources']['file']['path']
                log_format = self.config['data_sources']['file'].get('format', 'auto')
                self.log_reader = MongoDBLogReader(log_path, log_format)
            
            # Logları oku
            logger.info(f"Reading logs for {time_range}...")
            df = self.log_reader.read_logs(last_hours=last_hours)
            
            if df.empty:
                return self._format_result(
                    {"error": "Log okunamadı veya boş"},
                    "anomaly_analysis"
                )
            
            # Feature engineering
            logger.info("Creating features...")
            X, df_enriched = self.feature_engineer.create_features(df)
            
            # Filtreleri uygula
            df_filtered, X_filtered = self.feature_engineer.apply_filters(df_enriched, X)
            
            # Model var mı kontrol et
            if not self.detector.is_trained:
                # Model yoksa eğit
                logger.info("Training new model...")
                self.detector.train(X_filtered)
            
            # Tahmin yap
            predictions, anomaly_scores = self.detector.predict(X_filtered)
            
            # Analiz et
            analysis = self.detector.analyze_anomalies(df_filtered, X_filtered, predictions, anomaly_scores)
            
            # Sonuçları sakla
            self.last_analysis = {
                "df": df_filtered,
                "predictions": predictions,
                "anomaly_scores": anomaly_scores,
                "analysis": analysis
            }
            
            # Açıklama oluştur
            description = self._create_analysis_description(analysis, time_range)
            
            # Öneriler oluştur
            suggestions = self._create_suggestions(analysis)
            
            result = {
                "description": description,
                "data": {
                    "summary": analysis["summary"],
                    "critical_anomalies": analysis["critical_anomalies"][:10],  # İlk 10
                    "security_alerts": analysis.get("security_alerts", {}),
                    "temporal_analysis": analysis.get("temporal_analysis", {})
                },
                "suggestions": suggestions
            }
            
            return self._format_result(result, "anomaly_analysis")
            
        except Exception as e:
            logger.error(f"Anomaly analysis error: {e}")
            return self._format_result({"error": str(e)}, "anomaly_analysis")
    
    def get_anomaly_summary(self, args_input) -> str:
        """Son anomali analizi özetini getir"""
        try:
            # Argümanları parse et
            if isinstance(args_input, str):
                try:
                    args_dict = json.loads(args_input)
                except:
                    args_dict = {"top_n": 10}
            else:
                args_dict = args_input
            
            top_n = args_dict.get("top_n", 10)
            
            if self.last_analysis is None:
                return self._format_result(
                    {"error": "Henüz bir analiz yapılmamış. Önce 'analyze_mongodb_logs' çalıştırın."},
                    "anomaly_summary"
                )
            
            analysis = self.last_analysis["analysis"]
            df = self.last_analysis["df"]
            anomaly_scores = self.last_analysis["anomaly_scores"]
            
            # En kritik anomalileri bul
            anomaly_mask = self.last_analysis["predictions"] == -1
            anomaly_df = df[anomaly_mask].copy()
            anomaly_df['anomaly_score'] = anomaly_scores[anomaly_mask]
            
            # Top N anomali
            top_anomalies = anomaly_df.nsmallest(top_n, 'anomaly_score')
            
            # Özet oluştur
            summary_data = {
                "total_anomalies": int(anomaly_mask.sum()),
                "anomaly_rate": float(anomaly_mask.mean() * 100),
                "top_anomalies": [],
                "component_summary": analysis.get("component_analysis", {}),
                "temporal_summary": analysis.get("temporal_analysis", {})
            }
            
            # Top anomalileri formatla
            for idx, row in top_anomalies.iterrows():
                anomaly_info = {
                    "timestamp": str(row['timestamp']) if 'timestamp' in row else None,
                    "score": float(row['anomaly_score']),
                    "severity": row['s'] if 's' in row else None,
                    "component": row['c'] if 'c' in row else None,
                    "message": row['msg'][:150] if 'msg' in row else None
                }
                summary_data["top_anomalies"].append(anomaly_info)
            
            # DROP operasyonları varsa ekle
            if "security_alerts" in analysis:
                summary_data["security_alerts"] = analysis["security_alerts"]
            
            description = f"Son analizde {summary_data['total_anomalies']} anomali tespit edildi " \
                         f"(toplam logların %{summary_data['anomaly_rate']:.1f}'i). " \
                         f"En kritik {top_n} anomali listelendi."
            
            result = {
                "description": description,
                "data": summary_data
            }
            
            return self._format_result(result, "anomaly_summary")
            
        except Exception as e:
            logger.error(f"Anomaly summary error: {e}")
            return self._format_result({"error": str(e)}, "anomaly_summary")
    
    def train_anomaly_model(self, args_input) -> str:
        """Anomali modelini yeniden eğit"""
        try:
            # Argümanları parse et
            if isinstance(args_input, str):
                try:
                    args_dict = json.loads(args_input)
                except:
                    args_dict = {"sample_size": 10000}
            else:
                args_dict = args_input
            
            sample_size = args_dict.get("sample_size", 10000)
            
            # Log reader'ı başlat
            if self.log_reader is None:
                log_path = self.config['data_sources']['file']['path']
                log_format = self.config['data_sources']['file'].get('format', 'auto')
                self.log_reader = MongoDBLogReader(log_path, log_format)
            
            # Logları oku
            logger.info(f"Reading {sample_size} logs for training...")
            df = self.log_reader.read_logs(limit=sample_size)
            
            if df.empty:
                return self._format_result(
                    {"error": "Log okunamadı veya boş"},
                    "model_training"
                )
            
            # Feature engineering
            logger.info("Creating features...")
            X, df_enriched = self.feature_engineer.create_features(df)
            
            # Filtreleri uygula
            df_filtered, X_filtered = self.feature_engineer.apply_filters(df_enriched, X)
            
            # Model eğit
            logger.info("Training model...")
            training_stats = self.detector.train(X_filtered, save_model=True)
            
            # Feature istatistikleri
            feature_stats = self.feature_engineer.get_feature_statistics(X_filtered)
            
            description = f"Model {X_filtered.shape[0]} log ile {training_stats['training_time_seconds']:.1f} " \
                         f"saniyede eğitildi. {X_filtered.shape[1]} feature kullanıldı."
            
            result = {
                "description": description,
                "data": {
                    "training_stats": training_stats,
                    "feature_stats": feature_stats,
                    "model_path": self.detector.output_config.get('model_path', 'models/isolation_forest.pkl')
                },
                "suggestions": [
                    "Model başarıyla eğitildi ve kaydedildi",
                    f"Contamination rate: %{self.detector.model_config['parameters']['contamination'] * 100}",
                    "Şimdi 'analyze_mongodb_logs' ile anomali analizi yapabilirsiniz"
                ]
            }
            
            return self._format_result(result, "model_training")
            
        except Exception as e:
            logger.error(f"Model training error: {e}")
            return self._format_result({"error": str(e)}, "model_training")
    
    def _create_analysis_description(self, analysis: Dict, time_range: str) -> str:
        """Analiz sonucu için açıklama oluştur"""
        summary = analysis["summary"]
        
        desc = f"{time_range} zaman aralığında {summary['total_logs']} log analiz edildi. "
        desc += f"{summary['n_anomalies']} anomali tespit edildi (%{summary['anomaly_rate']:.1f}). "
        
        # Kritik bulgular
        if "security_alerts" in analysis:
            if "drop_operations" in analysis["security_alerts"]:
                drop_count = analysis["security_alerts"]["drop_operations"]["count"]
                desc += f"⚠️ {drop_count} adet DROP operasyonu tespit edildi! "
        
        # Temporal pattern
        if "temporal_analysis" in analysis and "peak_hours" in analysis["temporal_analysis"]:
            peak_hours = analysis["temporal_analysis"]["peak_hours"]
            desc += f"En yoğun anomali saatleri: {peak_hours}. "
        
        return desc
    
    def _create_suggestions(self, analysis: Dict) -> List[str]:
        """Analiz sonucuna göre öneriler oluştur"""
        suggestions = []
        
        # Anomali oranına göre
        anomaly_rate = analysis["summary"]["anomaly_rate"]
        if anomaly_rate > 5:
            suggestions.append("Yüksek anomali oranı tespit edildi. Sistem yöneticilerine bilgi verilmeli.")
        
        # DROP operasyonları
        if "security_alerts" in analysis:
            suggestions.append("🚨 Kritik güvenlik uyarısı: DROP operasyonları tespit edildi. Acil inceleme gerekli!")
        
        # Component bazlı öneriler
        if "component_analysis" in analysis:
            high_anomaly_components = [comp for comp, stats in analysis["component_analysis"].items() 
                                      if stats["anomaly_rate"] > 20]
            if high_anomaly_components:
                suggestions.append(f"Şu componentlerde yüksek anomali: {', '.join(high_anomaly_components[:3])}")
        
        # Feature bazlı öneriler
        if "feature_importance" in analysis:
            critical_features = [feat for feat, stats in analysis["feature_importance"].items() 
                               if stats.get("ratio", 0) > 5]
            if critical_features:
                suggestions.append(f"Anomalilerde öne çıkan özellikler: {', '.join(critical_features[:3])}")
        
        return suggestions


# Pydantic modelleri - Tool argümanları için
class AnalyzeLogsArgs(BaseModel):
    time_range: str = Field(default="last_hour", description="Zaman aralığı: last_hour, last_day, last_week, all")
    threshold: float = Field(default=0.03, description="Anomali eşik değeri")


class SummaryArgs(BaseModel):
    top_n: int = Field(default=10, description="Gösterilecek anomali sayısı")

class TrainModelArgs(BaseModel):
    sample_size: int = Field(default=10000, description="Eğitim için kullanılacak log sayısı")


def create_anomaly_tools(config_path: str = "config/anomaly_config.json", 
                        environment: str = "test") -> List[StructuredTool]:
    """Anomaly detection tool'larını oluştur"""
    
    anomaly_tools = AnomalyDetectionTools(config_path, environment)
    
    tools = [
        StructuredTool(
            name="analyze_mongodb_logs",
            description="MongoDB loglarında anomali analizi yap",
            func=anomaly_tools.analyze_mongodb_logs,
            args_schema=AnalyzeLogsArgs
        ),
        
        StructuredTool(
            name="get_anomaly_summary",
            description="Son anomali analizi özetini getir",
            func=anomaly_tools.get_anomaly_summary,
            args_schema=SummaryArgs
        ),
        
        StructuredTool(
            name="train_anomaly_model",
            description="Anomali tespit modelini yeniden eğit",
            func=anomaly_tools.train_anomaly_model,
            args_schema=TrainModelArgs
        )
    ]
    
    return tools