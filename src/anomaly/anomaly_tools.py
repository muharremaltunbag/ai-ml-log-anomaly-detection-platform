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
from pymongo import MongoClient
import numpy as np

from .log_reader import MongoDBLogReader, OpenSearchProxyReader
from .feature_engineer import MongoDBFeatureEngineer
from .anomaly_detector import MongoDBAnomalyDetector

from ..connectors.openai_connector import OpenAIConnector
from ..connectors.lcwgpt_connector import LCWGPTConnector
from langchain.schema import HumanMessage, SystemMessage


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
        logger.debug(f"Initializing AnomalyDetectionTools with config_path={config_path}, environment={environment}")
        self.config_path = config_path
        self.environment = environment
        
        # Config yükle
        self._load_config()
        
        # Modülleri başlat
        self.log_reader = None
        self.feature_engineer = MongoDBFeatureEngineer(config_path)
        self.detector = MongoDBAnomalyDetector(config_path)
        logger.debug("Feature engineer and detector modules initialized")
        
        # YENİ: LLM connector'ı başlat (OpenAI veya LCWGPT)
        llm_provider = os.getenv('LLM_PROVIDER', 'lcwgpt').lower()

        if llm_provider == 'lcwgpt':
            self.llm_connector = LCWGPTConnector()
            self.llm_connector.connect()
            logger.info("LCWGPT connector initialized for anomaly explanations")
        elif llm_provider == 'openai':
            self.llm_connector = OpenAIConnector()
            self.llm_connector.connect()
            logger.info("OpenAI connector initialized for anomaly explanations")
        else:
            logger.error(f"Unknown LLM provider: {llm_provider}")
            self.llm_connector = None
        
        # Son analiz sonuçlarını sakla
        self.last_analysis = None
        
        logger.info(f"AnomalyDetectionTools initialized for {environment} environment")
    
    def _load_config(self):
        """Config dosyasını yükle"""
        logger.debug(f"Loading config from: {self.config_path}")
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                full_config = json.load(f)
                self.config = full_config['environments'][self.environment]
                logger.debug(f"Config loaded successfully for environment: {self.environment}")
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            self.config = {}
            logger.debug("Using empty config as fallback")
    
    def _format_result(self, result: Dict[str, Any], operation: str) -> str:
        """Sonuçları MongoDB Agent formatına uygun şekilde formatla"""
        logger.debug(f"Formatting result for operation: {operation}")
        
        # CRITICAL DEBUG: Input critical_anomalies count
        if "data" in result and "critical_anomalies" in result["data"]:
            print(f"[DEBUG] FORMAT_RESULT INPUT: {len(result['data']['critical_anomalies'])} critical anomalies")
        
        try:
            def convert_numpy_types(obj):
                if isinstance(obj, np.integer):
                    return int(obj)
                elif isinstance(obj, np.floating):
                    # YENİ: Infinity ve NaN kontrolü
                    if np.isinf(obj):
                        return 999999.0 if obj > 0 else -999999.0
                    elif np.isnan(obj):
                        return 0.0
                    return float(obj)
                elif isinstance(obj, float):  # YENİ: Python float için de kontrol
                    if np.isinf(obj):
                        return 999999.0 if obj > 0 else -999999.0
                    elif np.isnan(obj):
                        return 0.0
                    return obj
                elif isinstance(obj, np.ndarray):
                    return obj.tolist()
                elif isinstance(obj, dict):
                    return {k: convert_numpy_types(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [convert_numpy_types(item) for item in obj]
                return obj
            
            # Result'ı temizle
            result = convert_numpy_types(result)

            if "error" in result:
                logger.debug(f"Formatting error result: {result.get('error', 'Unknown error')}")
                return json.dumps({
                    "durum": "hata",
                    "işlem": operation,
                    "açıklama": result.get("error", "Bilinmeyen hata"),
                    "sonuç": None
                }, ensure_ascii=False, indent=2)
            
            logger.debug("Formatting successful result")
            
            # Response yapısını oluştur
            response = {
                "durum": "başarılı",
                "işlem": operation,
                "açıklama": result.get("description", f"{operation} işlemi tamamlandı"),
                "sonuç": result.get("data", result),
                "öneriler": result.get("suggestions", [])
            }
            
            # CRITICAL DEBUG: Output critical_anomalies count
            if "critical_anomalies" in response["sonuç"]:
                print(f"[DEBUG] FORMAT_RESULT OUTPUT: {len(response['sonuç']['critical_anomalies'])} critical anomalies")
            
            # YENİ: AI explanation varsa ekle
            if "ai_explanation" in result and result["ai_explanation"]:
                # data içindeyse oraya, değilse direkt sonuç'a ekle
                if isinstance(response["sonuç"], dict):
                    response["sonuç"]["ai_explanation"] = result["ai_explanation"]
                logger.debug("AI explanation added to response")
            
            # FINAL DEBUG: Before JSON serialization
            if "critical_anomalies" in response["sonuç"]:
                print(f"[DEBUG] JSON SERIALIZATION: About to serialize {len(response['sonuç']['critical_anomalies'])} critical anomalies")
            
            json_result = json.dumps(response, ensure_ascii=False, indent=2)
            
            # Check if JSON result contains expected number
            if '"critical_anomalies"' in json_result:
                import re
                matches = re.findall(r'"critical_anomalies":\s*\[([^\]]*)\]', json_result)
                if matches:
                    # Count objects in the array (rough estimate)
                    content = matches[0]
                    object_count = content.count('"index"')
                    print(f"[DEBUG] JSON RESULT: Serialized JSON contains approximately {object_count} critical anomaly objects")
            
            return json_result
        except Exception as e:
            logger.error(f"Format hatası: {e}")
            return json.dumps({
                "durum": "hata",
                "işlem": operation,
                "açıklama": f"Format hatası: {str(e)}",
                "sonuç": str(result)
            }, ensure_ascii=False, indent=2)

    def _perform_enhanced_analysis(self, df_filtered, X_filtered, predictions, anomaly_scores, 
                                  source_name="unknown", use_incremental=True):
        """
        Tüm veri kaynakları için ortak gelişmiş analiz fonksiyonu
        
        Args:
            df_filtered: Filtrelenmiş DataFrame
            X_filtered: Feature matrix
            predictions: Model tahminleri
            anomaly_scores: Anomali skorları
            source_name: Veri kaynağı adı
            use_incremental: Incremental learning kullan
        
        Returns:
            Enhanced analysis dictionary
        """
        logger.info(f"Performing enhanced analysis for {source_name} source...")
        
        # 1. Model Training/Update (eğer gerekiyorsa)
        if not self.detector.is_trained:
            logger.info("Training new model with incremental learning...")
            
            if use_incremental and hasattr(self.detector, 'train_incremental'):
                # Incremental training
                batch_id = f"{source_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                training_stats = self.detector.train_incremental(X_filtered, batch_id=batch_id)
                logger.info(f"Incremental training completed - Ensemble size: {len(self.detector.incremental_models)}")
            else:
                # Fallback to standard training
                self.detector.train(X_filtered)
                logger.info("Standard training completed")
            
            # İlk training'de feature importance hesapla
            try:
                logger.info("Calculating initial feature importance...")
                importance_scores = self.detector.calculate_feature_importance(
                    X_filtered, 
                    sample_size=min(5000, len(X_filtered))
                )
                
                # Top features'ı logla
                top_features = list(importance_scores.keys())[:5]
                logger.info(f"Top 5 important features: {top_features}")
                
                # Dead features tespit et
                dead_features, low_impact = self.detector.detect_dead_features(importance_scores)
                if dead_features:
                    logger.warning(f"Found {len(dead_features)} dead features: {dead_features[:5]}")
                
                # Cache for later use
                self.detector.last_importance_scores = importance_scores
                
            except Exception as e:
                logger.error(f"Feature importance calculation failed: {e}")
                importance_scores = {}
            
            # Model evaluation
            try:
                logger.info("Evaluating initial model performance...")
                eval_metrics = self.detector.evaluate_model(X_filtered, df=df_filtered)
                logger.info(f"Model Performance - Precision: {eval_metrics['precision']:.3f}, "
                           f"Recall: {eval_metrics['recall']:.3f}, F1: {eval_metrics['f1_score']:.3f}")
                self.detector.last_eval_metrics = eval_metrics
            except Exception as e:
                logger.error(f"Model evaluation failed: {e}")
        
        else:
            # Model varsa drift kontrolü ve incremental update
            if use_incremental and hasattr(self.detector, 'train_incremental'):
                try:
                    # Drift kontrolü
                    drift_analysis = self.detector.detect_model_drift(X_filtered)
                    if drift_analysis['drift_detected']:
                        logger.warning(f"Model drift detected! Average drift: {drift_analysis['average_drift']:.3f}")
                        
                        if drift_analysis['average_drift'] > 0.5:
                            # Yüksek drift - full retrain
                            logger.info("High drift - performing full retrain...")
                            self.detector.train(X_filtered)
                        else:
                            # Normal incremental update
                            batch_id = f"{source_name}_update_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                            self.detector.train_incremental(X_filtered, batch_id=batch_id)
                    else:
                        # Drift yok - sadece prediction yap
                        logger.info("No significant drift detected - using existing model")
                        
                except Exception as e:
                    logger.error(f"Incremental update failed: {e}")
        
        # 2. Standart anomali analizi
        analysis = self.detector.analyze_anomalies(df_filtered, X_filtered, predictions, anomaly_scores)
        
        # 3. Feature importance ekle
        if hasattr(self.detector, 'last_importance_scores'):
            analysis["feature_importance"] = dict(list(self.detector.last_importance_scores.items())[:10])
        else:
            # İlk kez hesapla
            try:
                logger.info("Calculating feature importance for analysis...")
                importance_scores = self.detector.calculate_feature_importance(
                    X_filtered, 
                    sample_size=min(2000, len(X_filtered))  # Daha küçük sample
                )
                analysis["feature_importance"] = dict(list(importance_scores.items())[:10])
                self.detector.last_importance_scores = importance_scores
            except Exception as e:
                logger.error(f"Feature importance failed: {e}")
                analysis["feature_importance"] = {}
        
        # 4. Component analysis ekle (eğer yoksa)
        if "component_analysis" not in analysis and 'c' in df_filtered.columns:
            component_stats = {}
            for component in df_filtered['c'].unique()[:20]:  # İlk 20 component
                component_mask = df_filtered['c'] == component
                component_anomaly_mask = (predictions == -1) & component_mask
                component_stats[str(component)] = {
                    'total_count': int(component_mask.sum()),
                    'anomaly_count': int(component_anomaly_mask.sum()),
                    'anomaly_rate': float(component_anomaly_mask.sum() / component_mask.sum() * 100) if component_mask.sum() > 0 else 0
                }
            # En yüksek anomali oranına göre sırala
            analysis["component_analysis"] = dict(sorted(component_stats.items(), 
                                                        key=lambda x: x[1]['anomaly_rate'], 
                                                        reverse=True)[:10])
        
        # 5. Ensemble statistics ekle
        if hasattr(self.detector, 'incremental_models') and self.detector.incremental_models:
            ensemble_info = self.detector.get_ensemble_info()
            analysis["ensemble_stats"] = {
                'model_count': ensemble_info['model_count'],
                'total_samples_seen': ensemble_info.get('total_samples_seen', 0),
                'average_anomaly_ratio': ensemble_info.get('average_anomaly_ratio', 0)
            }
            logger.info(f"Ensemble statistics: {ensemble_info['model_count']} models, "
                       f"{ensemble_info.get('total_samples_seen', 0)} total samples")
        
        # 6. Model performance metrics ekle
        if hasattr(self.detector, 'last_eval_metrics'):
            analysis["model_performance"] = {
                'precision': self.detector.last_eval_metrics['precision'],
                'recall': self.detector.last_eval_metrics['recall'],
                'f1_score': self.detector.last_eval_metrics['f1_score']
            }
        
        logger.info(f"Enhanced analysis completed for {source_name}")
        return analysis
    
    def _fix_mongodb_hostname_fqdn(self, hostname: str) -> str:
        """MongoDB hostname'ine gerekirse FQDN ekle"""
        import re
        
        if not hostname:
            return hostname
            
        # Zaten FQDN varsa dokunma
        if hostname.endswith('.lcwaikiki.local'):
            logger.debug(f"Hostname already has FQDN: {hostname}")
            return hostname
        
        # ÖNEMLI: Case-insensitive kontrol yap ama orijinal case'i koru!
        hostname_lower = hostname.lower()
        
        # FQDN eklenmesi gereken pattern'ler (whitelist)
        fqdn_required_patterns = [
            r'^lcwmongodb\d+n\d+$',           # lcwmongodb01n2
            r'^testmongodb\d+$',               # testmongodb01
            r'^devmongodb\d+$',                # devmongodb02
            r'^pplmongodbn\d+$',               # pplmongodbn1 (az'sız!)
            r'^kznmongodbn\d+$',               # kznmongodbn1, KZNMONGODBN2
            r'^ntfcmongodb\d+$',               # NTFCMONGODB01
        ]
        
        # Pattern kontrolü - küçük harfle kontrol et
        for pattern in fqdn_required_patterns:
            if re.match(pattern, hostname_lower):
                # ORİJİNAL CASE'İ KORUYARAK FQDN EKLE!
                fixed_hostname = f"{hostname}.lcwaikiki.local"
                logger.debug(f"FQDN added: {hostname} -> {fixed_hostname}")
                return fixed_hostname
        
        # Whitelist'te değilse olduğu gibi döndür
        logger.debug(f"FQDN not required for: {hostname}")
        return hostname
    
    def analyze_mongodb_logs(self, args_input) -> str:
        """MongoDB loglarında anomali analizi yap"""
        logger.debug(f"Starting MongoDB log analysis with input: {args_input}")
        try:
            # Argümanları parse et
            if isinstance(args_input, str):
                try:
                    args_dict = json.loads(args_input)
                    logger.debug("Successfully parsed string input to dict")
                except:
                    args_dict = {"time_range": "last_hour", "threshold": 0.03}
                    logger.debug("Failed to parse string input, using defaults")
            else:
                args_dict = args_input
                logger.debug("Using dict input directly")
            
            logger.info(f"Anomaly analysis started with args: {args_dict}")
            
            time_range = args_dict.get("time_range", "last_hour")
            threshold = args_dict.get("threshold", 0.03)
            
            # Frontend'den gelen değerleri dönüştür
            if args_dict.get("time_range") == "last_24h":
                time_range = "last_day"
            elif args_dict.get("time_range") == "last_7d":
                time_range = "last_week"
            elif args_dict.get("time_range") == "last_30d":  # YENİ
                time_range = "last_month"
            
            logger.debug(f"Analysis parameters: time_range={time_range}, threshold={threshold}")
            
            # YENİ: Veri kaynağı seçimi
            source_type = args_dict.get("source_type", "file")
            logger.info(f"Using data source type: {source_type}")
            
            # Log reader'ı kaynak tipine göre başlat
            if source_type == "upload":
                file_path = args_dict.get("file_path")
                logger.info(f"Processing upload file: {file_path}")
                if not file_path or not os.path.exists(file_path):
                    logger.error(f"Upload file not found: {file_path}")
                    return self._format_result(
                        {"error": f"Upload dosyası bulunamadı: {file_path}"},
                        "anomaly_analysis"
                    )
                self.log_reader = MongoDBLogReader(file_path, 'auto')
                logger.info(f"Using uploaded file: {file_path}")
                
            elif source_type == "mongodb_direct":
                # MongoDB'den doğrudan okuma için özel işlem
                conn_string = args_dict.get("connection_string", 
                                          self.config['data_sources']['mongodb_direct']['default_connection'])
                logger.info(f"Using MongoDB direct connection: {conn_string[:20]}...")
                return self._analyze_mongodb_direct(conn_string, time_range, threshold)
                
            elif source_type == "test_servers":
                server_name = args_dict.get("server_name")
                logger.info(f"Processing test server: {server_name}")
                if not server_name:
                    logger.error("Test server name not specified")
                    return self._format_result(
                        {"error": "Test sunucu adı belirtilmedi"},
                        "anomaly_analysis"
                    )
                # Test sunucusu log yolunu al
                log_path = self._get_test_server_log_path(server_name)
                logger.debug(f"Test server log path: {log_path}")
                self.log_reader = MongoDBLogReader(log_path, 'auto')
                
            elif source_type == "opensearch":
                logger.info("Using OpenSearch data source")
                try:
                    # OpenSearch reader'ı başlat
                    opensearch_reader = OpenSearchProxyReader()
                    
                    # Bağlantıyı kontrol et
                    if not opensearch_reader.connect():
                        logger.error("Failed to connect to OpenSearch")
                        return self._format_result(
                            {"error": "OpenSearch'e bağlanılamadı. Lütfen bağlantı bilgilerini kontrol edin."},
                            "anomaly_analysis"
                        )
                    
                    # Zaman aralığını saat cinsine çevir
                    if time_range == "last_hour":
                        last_hours = 1
                    elif time_range == "last_day":
                        last_hours = 24
                    elif time_range == "last_week":
                        last_hours = 168
                    elif time_range == "last_month":  # YENİ
                        last_hours = 720
                    else:
                        last_hours = args_dict.get("last_hours", 24)
                    
                    # OpenSearch'ten logları oku
                    logger.info(f"Reading logs from OpenSearch for last {last_hours} hours...")
                    
                    # YENİ: Host filter'a FQDN düzeltmesi uygula
                    host_filter = args_dict.get("host_filter", None)
                    if host_filter:
                        original_host = host_filter
                        host_filter = self._fix_mongodb_hostname_fqdn(host_filter)
                        if original_host != host_filter:
                            logger.info(f"Host filter FQDN correction: {original_host} -> {host_filter}")
                
                    df = opensearch_reader.read_logs(
                        limit=None,  # Tüm logları al
                        last_hours=last_hours,
                        host_filter=host_filter  # Düzeltilmiş host filter
                    )
                    
                    if df.empty:
                        logger.error("No logs retrieved from OpenSearch")
                        return self._format_result(
                            {"error": "OpenSearch'ten log alınamadı"},
                            "anomaly_analysis"
                        )
                    
                    logger.info(f"Retrieved {len(df)} logs from OpenSearch")
                    
                    # Normal analiz akışına devam et
                    # Feature engineering
                    logger.info("Creating features...")
                    X, df_enriched = self.feature_engineer.create_features(df)
                    
                    # Filtreleri uygula
                    df_filtered, X_filtered = self.feature_engineer.apply_filters(df_enriched, X)
                    logger.info(f"After filtering: {len(df_filtered)} logs, {X_filtered.shape[1]} features")
                    
                    # Model kontrolü ve tahmin
                    if not self.detector.is_trained:
                        logger.info("Model not trained, will train during analysis...")
                    else:
                        logger.info("Model already trained, will use existing model...")
                    
                    # Model eğitilmemişse önce eğit
                    if not self.detector.is_trained:
                        logger.info("Training model first before prediction...")
                        if hasattr(self.detector, 'train_incremental'):
                            batch_id = f"opensearch_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                            self.detector.train_incremental(X_filtered, batch_id=batch_id)
                            logger.info(f"Initial training completed - Ensemble size: {len(self.detector.incremental_models)}")
                        else:
                            self.detector.train(X_filtered)
                            logger.info("Standard training completed")

                    # Şimdi tahmin yap
                    predictions, anomaly_scores = self.detector.predict(X_filtered, df=df_filtered)
                    anomaly_count = sum(predictions == -1)
                    logger.info(f"Found {anomaly_count} anomalies in OpenSearch logs")
                    
                    # Enhanced analiz kullan (training zaten yapıldı, tekrar yapmayacak)
                    analysis = self._perform_enhanced_analysis(
                        df_filtered, X_filtered, predictions, anomaly_scores,
                        source_name="opensearch", use_incremental=True
                    )
                    
                    # YENİ: False positive filtering
                    analysis = self._filter_false_positives(analysis, source_name="opensearch")
                    
                    # Sonuçları sakla
                    self.last_analysis = {
                        "df": df_filtered,
                        "predictions": predictions,
                        "anomaly_scores": anomaly_scores,
                        "analysis": analysis
                    }

                    ai_explanation = {}
                    # OpenAI bağlantısı varsa AI destekli açıklama üret
                    if self.llm_connector and self.llm_connector.is_connected():
                        logger.info("Generating AI-powered explanation for OpenSearch data...")
                        # AI'ya gönderilecek veriyi sınırla - token limit aşımını önle
                        limited_analysis = {
                            "summary": {
                                "total_logs": analysis["summary"]["total_logs"],
                                "n_anomalies": analysis["summary"]["n_anomalies"],
                                "anomaly_rate": analysis["summary"]["anomaly_rate"],
                                "score_range": analysis["summary"]["score_range"]
                            },
                            "critical_anomalies": analysis["critical_anomalies"][:20],  # AI için sadece ilk 20
                            "security_alerts": analysis.get("security_alerts", {}),
                            "component_analysis": dict(list(analysis.get("component_analysis", {}).items())[:10]),  # İlk 10 component
                            "temporal_analysis": {
                                "peak_hours": analysis.get("temporal_analysis", {}).get("peak_hours", [])[:3]  # Sadece peak hours
                            },
                            "feature_importance": dict(list(analysis.get("feature_importance", {}).items())[:10])  # İlk 10 feature
                        }
                        logger.info(f"[DEBUG] Limiting AI analysis to first 20 anomalies (was {len(analysis['critical_anomalies'])})")
                        ai_explanation = self._generate_ai_explanation(limited_analysis)

                    
                    # Açıklama ve öneriler
                    if ai_explanation:
                        description = f"OpenSearch'ten son {last_hours} saatteki {len(df)} log analiz edildi.\n\n" + \
                                    self._create_enriched_description(analysis, time_range, ai_explanation)[len("🤖 **AI DESTEKLİ ANOMALİ ANALİZİ**\n\n"):]
                        suggestions = ai_explanation.get("onerilen_aksiyonlar", [])
                        logger.info("AI-powered explanation and suggestions created for OpenSearch.")
                    else:
                        # Fallback: AI başarısız olursa standart raporlamayı kullan
                        description = f"OpenSearch'ten son {last_hours} saatteki {len(df)} log analiz edildi. " + \
                                     self._create_analysis_description(analysis, time_range)
                        suggestions = self._create_suggestions(analysis)
                        logger.warning("Fell back to basic description and suggestions for OpenSearch.")
                    
                    # DEBUG: OpenSearch analysis'den önce critical_anomalies sayısını logla
                    print(f"[DEBUG] OPENSEARCH: Before enhancement - analysis['critical_anomalies'] count: {len(analysis['critical_anomalies'])}")
                    logger.debug(f"OpenSearch analysis before enhancement: {len(analysis['critical_anomalies'])} critical anomalies")
                    
                    result = {
                        "description": description,
                        "data": {
                            "source": "OpenSearch",
                            "logs_analyzed": len(df),
                            "filtered_logs": len(df_filtered),  # YENİ
                            "summary": analysis["summary"],
                            "critical_anomalies": self._enhance_critical_anomalies_with_messages(analysis["critical_anomalies"]),
                            "security_alerts": analysis.get("security_alerts", {}),
                            "temporal_analysis": analysis.get("temporal_analysis", {}),
                            "component_analysis": analysis.get("component_analysis", {}),  # YENİ
                            "feature_importance": analysis.get("feature_importance", {}),  # YENİ
                            "anomaly_score_stats": {  # YENİ
                                "min": analysis["summary"]["score_range"]["min"],
                                "max": analysis["summary"]["score_range"]["max"],
                                "mean": analysis["summary"]["score_range"]["mean"]
                            }
                        },
                        "suggestions": suggestions,
                        "ai_explanation": ai_explanation  
                    }
                    
                    return self._format_result(result, "anomaly_analysis")
                    
                except Exception as e:
                    logger.error(f"OpenSearch analysis error: {e}", exc_info=True)
                    return self._format_result(
                        {"error": f"OpenSearch analiz hatası: {str(e)}"},
                        "anomaly_analysis"
                    )
                
            else:  # default: file
                if self.log_reader is None:
                    log_path = self.config['data_sources']['file']['path']
                    log_format = self.config['data_sources']['file'].get('format', 'auto')
                    logger.info(f"Using default file source: {log_path}")
                    self.log_reader = MongoDBLogReader(log_path, log_format)
            
            uploaded_file_path = args_dict.get('uploaded_file_path')
            logger.debug(f"Uploaded file path from args: {uploaded_file_path}")
            
            # Zaman aralığını belirle
            last_hours = None
            if time_range == "last_hour":
                last_hours = 1
            elif time_range == "last_day":
                last_hours = 24
            elif time_range == "last_week":
                last_hours = 168
            elif time_range == "last_month":  # YENİ
                last_hours = 720
            
            # Log reader'ı başlat
            if self.log_reader is None:
                if uploaded_file_path and os.path.exists(uploaded_file_path):
                    # Upload edilen dosyayı oku
                    logger.info(f"Using uploaded file path: {uploaded_file_path}")
                    self.log_reader = MongoDBLogReader(uploaded_file_path, 'auto')
                else:
                    # Normal config'den oku
                    log_path = self.config['data_sources']['file']['path']
                    log_format = self.config['data_sources']['file'].get('format', 'auto')
                    logger.debug(f"Using config file source: {log_path}, format: {log_format}")
                    self.log_reader = MongoDBLogReader(log_path, log_format)
            
            # Logları oku
            logger.info(f"Reading logs for {time_range}...")
            df = self.log_reader.read_logs(last_hours=last_hours)
            
            if df.empty:
                logger.error("No logs read or empty DataFrame")
                return self._format_result(
                    {"error": "Log okunamadı veya boş"},
                    "anomaly_analysis"
                )
            
            logger.info(f"Successfully read {len(df)} logs")
            logger.debug(f"DataFrame columns: {list(df.columns)}")
            
            # Feature engineering
            logger.info("Creating features...")
            X, df_enriched = self.feature_engineer.create_features(df)
            logger.debug(f"Features created: {X.shape}")
            
            # Filtreleri uygula
            df_filtered, X_filtered = self.feature_engineer.apply_filters(df_enriched, X)
            logger.info(f"After filtering: {len(df_filtered)} logs, {X_filtered.shape[1]} features")
            
            # Model kontrolü
            if not self.detector.is_trained:
                logger.info("Model not trained, will train during analysis...")
            else:
                logger.info("Model already trained, will use existing model...")
            
            # Tahmin yap
            # Model eğitilmemişse önce eğit
            if not self.detector.is_trained:
                logger.info("Training model first before prediction...")
                if hasattr(self.detector, 'train_incremental'):
                    batch_id = f"file_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    self.detector.train_incremental(X_filtered, batch_id=batch_id)
                    logger.info(f"Initial training completed - Ensemble size: {len(self.detector.incremental_models)}")
                else:
                    self.detector.train(X_filtered)
                    logger.info("Standard training completed")

            # Tahmin yap
            logger.debug("Starting anomaly prediction...")
            predictions, anomaly_scores = self.detector.predict(X_filtered, df=df_filtered)
            anomaly_count = sum(predictions == -1)
            logger.info(f"Anomaly detection completed. Found {anomaly_count} anomalies")
            logger.debug(f"Anomaly scores range: min={min(anomaly_scores):.4f}, max={max(anomaly_scores):.4f}")
            
            # Enhanced analiz kullan
            analysis = self._perform_enhanced_analysis(
                df_filtered, X_filtered, predictions, anomaly_scores,
                source_name="file", use_incremental=True
            )
            
            # YENİ: False positive filtering
            analysis = self._filter_false_positives(analysis, source_name="file")
            # Sonuçları sakla
            self.last_analysis = {
                "df": df_filtered,
                "predictions": predictions,
                "anomaly_scores": anomaly_scores,
                "analysis": analysis
            }
            logger.debug("Analysis results stored")
            
            # YENİ: AI Entegrasyon Kısmı
            ai_explanation = {}
            # LLM bağlantısı varsa AI destekli açıklama üret
            if self.llm_connector and self.llm_connector.is_connected():
                logger.info("Generating AI-powered explanation...")
                # AI'ya gönderilecek veriyi sınırla - token limit aşımını önle
                limited_analysis = {
                    "summary": {
                        "total_logs": analysis["summary"]["total_logs"],
                        "n_anomalies": analysis["summary"]["n_anomalies"],
                        "anomaly_rate": analysis["summary"]["anomaly_rate"],
                        "score_range": analysis["summary"]["score_range"]
                    },
                    "critical_anomalies": analysis["critical_anomalies"][:20],  # AI için sadece ilk 20
                    "security_alerts": analysis.get("security_alerts", {}),
                    "component_analysis": dict(list(analysis.get("component_analysis", {}).items())[:10]),  # İlk 10 component
                    "temporal_analysis": {
                        "peak_hours": analysis.get("temporal_analysis", {}).get("peak_hours", [])[:3]  # Sadece peak hours
                    },
                    "feature_importance": dict(list(analysis.get("feature_importance", {}).items())[:10])  # İlk 10 feature
                }
                logger.info(f"[DEBUG] Limiting AI analysis to first 20 anomalies (was {len(analysis['critical_anomalies'])})")
                ai_explanation = self._generate_ai_explanation(limited_analysis)

            # AI'dan başarılı bir yanıt geldiyse onu kullan, gelmediyse eskiye dön
            if ai_explanation:
                description = self._create_enriched_description(analysis, time_range, ai_explanation)
                suggestions = ai_explanation.get("onerilen_aksiyonlar", [])
                logger.info("AI-powered explanation and suggestions created.")
            else:
                # Fallback: AI başarısız olursa standart raporlamayı kullan
                description = self._create_analysis_description(analysis, time_range)
                suggestions = self._create_suggestions(analysis)
                logger.warning("Fell back to basic description and suggestions.")

            # YENİ: Critical anomalies'i enhance et - MEMORY OPTIMIZED
            enhanced_analysis = {
                "summary": analysis["summary"],
                "security_alerts": analysis.get("security_alerts", {}),
                "temporal_analysis": analysis.get("temporal_analysis", {}),
                "component_analysis": analysis.get("component_analysis", {}),
                "feature_importance": analysis.get("feature_importance", {}),
                "anomaly_score_stats": analysis.get("anomaly_score_stats", {})
            }
            if "critical_anomalies" in analysis:
                print(f"[DEBUG] MAIN FUNCTION: Original analysis has {len(analysis['critical_anomalies'])} critical anomalies")
                enhanced_analysis["critical_anomalies"] = self._enhance_critical_anomalies_with_messages(
                    analysis["critical_anomalies"]
                )
                print(f"[DEBUG] MAIN FUNCTION: After enhancement, we have {len(enhanced_analysis['critical_anomalies'])} critical anomalies")

            result = {
                "description": description,
                "data": enhanced_analysis, # Enhanced analiz verisini gönder
                "suggestions": suggestions,
                "ai_explanation": ai_explanation # Yapılandırılmış AI çıktısını da ekleyelim
            }
            
            print(f"[DEBUG] MAIN FUNCTION: Final result data critical_anomalies count: {len(result['data'].get('critical_anomalies', []))}")
            
            return self._format_result(result, "anomaly_analysis")
            
        except Exception as e:
            logger.error(f"Anomaly analysis error: {e}", exc_info=True)
            return self._format_result({"error": str(e)}, "anomaly_analysis")
    
    def _analyze_mongodb_direct(self, connection_string: str, time_range: str, threshold: float) -> str:
        """MongoDB'den doğrudan log okuyup analiz et"""
        logger.debug(f"Starting MongoDB direct analysis with time_range={time_range}, threshold={threshold}")
        try:
            logger.debug("Connecting to MongoDB...")
            client = MongoClient(connection_string)
            db = client.get_database()
            
            # System.profile collection'ından slow query logları al
            profile_collection = db.system.profile
            logger.debug("Accessing system.profile collection")
            
            # Zaman filtresini ayarla
            time_filter = {}
            if time_range == "last_hour":
                time_filter = {"ts": {"$gte": datetime.now() - timedelta(hours=1)}}
            elif time_range == "last_day":
                time_filter = {"ts": {"$gte": datetime.now() - timedelta(days=1)}}
            
            logger.debug(f"Time filter: {time_filter}")
            
            # Logları DataFrame'e dönüştür
            logger.debug("Querying MongoDB logs...")
            logs = list(profile_collection.find(time_filter).limit(10000))
            if not logs:
                logger.error("No logs found in MongoDB")
                return self._format_result(
                    {"error": "MongoDB'de log bulunamadı"},
                    "anomaly_analysis"
                )
            
            logger.debug(f"Found {len(logs)} logs in MongoDB")
            df = pd.DataFrame(logs)
            # MongoDB log formatına dönüştür
            logger.debug("Converting MongoDB logs to standard format...")
            df = self._convert_mongodb_logs_to_standard_format(df)
            logger.debug(f"Converted DataFrame shape: {df.shape}")
            
            # Normal analiz devam eder
            X, df_enriched = self.feature_engineer.create_features(df)
            # Filtreleri uygula
            df_filtered, X_filtered = self.feature_engineer.apply_filters(df_enriched, X)
            logger.debug(f"After filtering: {len(df_filtered)} logs, {X_filtered.shape[1]} features")
            
  
            # Model kontrolü ve eğitim
            if not self.detector.is_trained:
                logger.info("Training model first...")
                if hasattr(self.detector, 'train_incremental'):
                    batch_id = f"mongodb_direct_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    self.detector.train_incremental(X_filtered, batch_id=batch_id)
                else:
                    self.detector.train(X_filtered)

            # Tahmin yap
            predictions, anomaly_scores = self.detector.predict(X_filtered, df=df_filtered)
            logger.debug(f"Found {sum(predictions == -1)} anomalies in MongoDB logs")

            # Enhanced analiz
            analysis = self._perform_enhanced_analysis(
                df_filtered, X_filtered, predictions, anomaly_scores,
                source_name="mongodb_direct", use_incremental=True
            )
            
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
                    "critical_anomalies": self._enhance_critical_anomalies_with_messages(analysis["critical_anomalies"]),  # Tüm kritik anomaliler - Enhanced
                    "security_alerts": analysis.get("security_alerts", {}),
                    "temporal_analysis": analysis.get("temporal_analysis", {})
                },
                "suggestions": suggestions
            }
            
            logger.debug("MongoDB direct analysis completed successfully")
            return self._format_result(result, "anomaly_analysis")
            
        except Exception as e:
            logger.error(f"MongoDB direct analysis error: {e}", exc_info=True)
            return self._format_result(
                {"error": f"MongoDB bağlantı hatası: {str(e)}"},
                "anomaly_analysis"
            )

    def _get_test_server_log_path(self, server_name: str) -> str:
        """Test sunucusu log path'ini al"""
        logger.debug(f"Getting log path for test server: {server_name}")
        try:
            # monitoring_servers.json'u oku
            config_path = self.config['data_sources']['test_servers']['config_path']
            logger.debug(f"Reading test servers config from: {config_path}")
            with open(config_path, 'r') as f:
                servers_config = json.load(f)
            
            env = self.config['data_sources']['test_servers']['environment']
            server = servers_config['environments'][env]['servers'].get(server_name)
            
            if not server:
                logger.error(f"Server not found in config: {server_name}")
                raise ValueError(f"Sunucu bulunamadı: {server_name}")
            
            # MongoDB config'den log path al
            if 'mongodb_config' in server:
                log_path = server['mongodb_config']['log_path']
                logger.debug(f"Found MongoDB log path for {server_name}: {log_path}")
                return log_path
            else:
                default_path = self.config['data_sources']['test_servers']['default_log_path']
                logger.debug(f"Using default log path for {server_name}: {default_path}")
                return default_path
                
        except Exception as e:
            logger.error(f"Test server log path error: {e}")
            fallback_path = self.config['data_sources']['file']['path']
            logger.debug(f"Using fallback path: {fallback_path}")
            return fallback_path  # Fallback

    def _convert_mongodb_logs_to_standard_format(self, df: pd.DataFrame) -> pd.DataFrame:
        """MongoDB system.profile formatını standart log formatına dönüştür"""
        logger.debug(f"Converting {len(df)} MongoDB logs to standard format")
        converted_df = pd.DataFrame()
        
        # Timestamp
        converted_df['t'] = df['ts'].apply(lambda x: {'$date': x.isoformat()})
        
        # Severity (slow query'ler için W)
        converted_df['s'] = 'W'
        
        # Component
        converted_df['c'] = df.get('ns', 'QUERY').apply(lambda x: 'QUERY')
        
        # Context
        converted_df['ctx'] = df.get('appName', 'conn-unknown')
        
        # Message
        converted_df['msg'] = df.apply(lambda row: f"Slow query: {row.get('command', {})} ms: {row.get('millis', 0)}", axis=1)
        
        # Attributes
        converted_df['attr'] = df.apply(lambda row: {
            'millis': row.get('millis', 0),
            'ns': row.get('ns', ''),
            'command': row.get('command', {})
        }, axis=1)
        
        logger.debug(f"Successfully converted to standard format with {len(converted_df)} rows")
        return converted_df
    
    def get_anomaly_summary(self, args_input) -> str:
        """Son anomali analizi özetini getir"""
        logger.debug(f"Getting anomaly summary with input: {args_input}")
        try:
            # Argümanları parse et
            if isinstance(args_input, str):
                try:
                    args_dict = json.loads(args_input)
                    logger.debug("Successfully parsed string input to dict")
                except:
                    args_dict = {"top_n": 10}
                    logger.debug("Failed to parse string input, using defaults")
            else:
                args_dict = args_input
            
            top_n = args_dict.get("top_n", 10)
            logger.debug(f"Summary for top {top_n} anomalies")
            
            if self.last_analysis is None:
                logger.error("No analysis has been performed yet")
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
            
            logger.debug(f"Found {len(anomaly_df)} anomalies for summary")
            
            # Top N anomali
            top_anomalies = anomaly_df.nsmallest(top_n, 'anomaly_score')
            logger.debug(f"Selected top {len(top_anomalies)} anomalies")
            
            # Özet oluştur
            summary_data = {
                "total_anomalies": int(anomaly_mask.sum()),
                "anomaly_rate": float(anomaly_mask.mean() * 100),
                "top_anomalies": [],
                "component_summary": analysis.get("component_analysis", {}),
                "temporal_summary": analysis.get("temporal_analysis", {})
            }
            
            # Top anomalileri formatla - ENHANCED with formatted messages
            for idx, row in top_anomalies.iterrows():
                # Original data structure
                anomaly_data = {
                    "timestamp": str(row['timestamp']) if 'timestamp' in row else None,
                    "score": float(row['anomaly_score']),
                    "severity": row['s'] if 's' in row else None,
                    "component": row['c'] if 'c' in row else None,
                    "message": row['msg'][:150] if 'msg' in row else None
                }
                
                # YENİ: Formatlı mesaj üret
                try:
                    formatted_message = self._generate_anomaly_message({
                        'component': anomaly_data["component"],
                        'severity': anomaly_data["severity"], 
                        'score': anomaly_data["score"],
                        'message': row['msg'] if 'msg' in row else '',  # Tam mesaj
                        'timestamp': anomaly_data["timestamp"]
                    })
                    anomaly_data["formatted_message"] = formatted_message
                    logger.debug(f"Generated formatted message for anomaly {idx}")
                except Exception as e:
                    logger.error(f"Error generating formatted message for anomaly {idx}: {e}")
                    # Fallback: basit formatlı mesaj
                    anomaly_data["formatted_message"] = f"Anomali tespit edildi (Skor: {anomaly_data['score']:.3f})"
                
                # YENİ: Anomali tipi de ekle
                try:
                    anomaly_type = self._detect_anomaly_type_from_message(
                        row['msg'] if 'msg' in row else '',
                        anomaly_data["component"] or '',
                        anomaly_data["severity"] or 'W'
                    )
                    anomaly_data["anomaly_type"] = anomaly_type
                except Exception as e:
                    logger.error(f"Error detecting anomaly type for {idx}: {e}")
                    anomaly_data["anomaly_type"] = 'unknown'
                
                summary_data["top_anomalies"].append(anomaly_data)
            
            # DROP operasyonları varsa ekle
            if "security_alerts" in analysis:
                summary_data["security_alerts"] = analysis["security_alerts"]
                logger.debug("Added security alerts to summary")
            
            description = f"Son analizde {summary_data['total_anomalies']} anomali tespit edildi " \
                         f"(toplam logların %{summary_data['anomaly_rate']:.1f}'i). " \
                         f"En kritik {top_n} anomali listelendi."
            
            result = {
                "description": description,
                "data": summary_data
            }
            
            logger.debug("Anomaly summary prepared successfully")
            return self._format_result(result, "anomaly_summary")
            
        except Exception as e:
            logger.error(f"Anomaly summary error: {e}", exc_info=True)
            return self._format_result({"error": str(e)}, "anomaly_summary")
    
    def train_anomaly_model(self, args_input) -> str:
        """Anomali modelini yeniden eğit"""
        logger.debug(f"Training anomaly model with input: {args_input}")
        try:
            # Argümanları parse et
            if isinstance(args_input, str):
                try:
                    args_dict = json.loads(args_input)
                    logger.debug("Successfully parsed string input to dict")
                except:
                    args_dict = {"sample_size": 10000}
                    logger.debug("Failed to parse string input, using defaults")
            else:
                args_dict = args_input
            
            sample_size = args_dict.get("sample_size", 10000)
            logger.debug(f"Training with sample size: {sample_size}")
            
            # Log reader'ı başlat
            if self.log_reader is None:
                log_path = self.config['data_sources']['file']['path']
                log_format = self.config['data_sources']['file'].get('format', 'auto')
                logger.debug(f"Initializing log reader with path: {log_path}, format: {log_format}")
                self.log_reader = MongoDBLogReader(log_path, log_format)
            
            # Logları oku
            logger.info(f"Reading {sample_size} logs for training...")
            df = self.log_reader.read_logs(limit=sample_size)
            
            if df.empty:
                logger.error("No logs read for training")
                return self._format_result(
                    {"error": "Log okunamadı veya boş"},
                    "model_training"
                )
            
            logger.debug(f"Read {len(df)} logs for training")
            
            # Feature engineering
            logger.info("Creating features...")
            X, df_enriched = self.feature_engineer.create_features(df)
            logger.debug(f"Created features with shape: {X.shape}")
            
            # Filtreleri uygula
            df_filtered, X_filtered = self.feature_engineer.apply_filters(df_enriched, X)
            logger.debug(f"After filtering: {len(df_filtered)} logs, {X_filtered.shape[1]} features")
            
            # Model eğit
            logger.info("Training model...")
            training_stats = self.detector.train(X_filtered, save_model=True)
            logger.debug(f"Model training completed in {training_stats.get('training_time_seconds', 0):.2f} seconds")
            
            # Feature istatistikleri
            feature_stats = self.feature_engineer.get_feature_statistics(X_filtered)
            logger.debug("Feature statistics calculated")
            
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
            
            logger.debug("Model training result prepared successfully")
            return self._format_result(result, "model_training")
            
        except Exception as e:
            logger.error(f"Model training error: {e}", exc_info=True)
            return self._format_result({"error": str(e)}, "model_training")
    def _filter_false_positives(self, analysis: Dict[str, Any], source_name: str = "unknown") -> Dict[str, Any]:
        """
        Analiz sonuçlarından false positive'leri filtrele
        
        Args:
            analysis: Enhanced analysis sonucu
            source_name: Veri kaynağı adı
            
        Returns:
            Filtrelenmiş analiz sonucu
        """
        logger.info(f"Applying smart post-processing filter for {source_name}...")
        
        # Orijinal anomali sayısını logla
        original_count = len(analysis.get('critical_anomalies', []))
        logger.info(f"Original critical anomalies: {original_count}")
        
        # 1. Component-based filtering
        # ACCESS gibi %100 anomali olan componentleri temizle
        if 'component_analysis' in analysis:
            suspicious_components = []
            for comp, stats in analysis['component_analysis'].items():
                # %97'ten fazla anomali oranı varsa şüpheli
                if stats.get('anomaly_rate', 0) > 97:
                    suspicious_components.append(comp)
                    logger.warning(f"Component {comp} has {stats['anomaly_rate']:.1f}% anomaly rate - marking as suspicious")
        
        # 2. Critical anomalies filtreleme
        if 'critical_anomalies' in analysis:
            filtered_anomalies = []
            
            for anomaly in analysis['critical_anomalies']:
                # Skip suspicious components
                if 'component_analysis' in analysis:
                    comp = anomaly.get('component', '')
                    if comp in suspicious_components:
                        continue
                
                # Gerçek kritik anomali kriterleri
                is_critical = False
                msg = anomaly.get('message', '').lower()
                severity_score = anomaly.get('severity_score', 0)
                severity_level = anomaly.get('severity_level', '')
                
                # Kritik tipler her zaman dahil
                critical_patterns = [
                    'drop' in msg and ('collection' in msg or 'index' in msg),
                    'authentication failed' in msg,
                    'fatal' in msg,
                    'out of memory' in msg,
                    'oom' in msg,
                    'assertion' in msg,
                    'shutdown' in msg,
                    'restart' in msg
                ]
                
                if any(critical_patterns):
                    is_critical = True
                
                # Yüksek severity score olanlar
                elif severity_score > 65:  # Daha yüksek threshold
                    is_critical = True
                
                # CRITICAL veya HIGH severity level
                elif severity_level in ['CRITICAL', 'HIGH']:
                    is_critical = True
                
                # Performance kritik anomaliler
                elif any([
                    'collscan' in msg and severity_score > 50,
                    'slow' in msg and 'ms' in msg and severity_score > 60,
                    'high_doc_scan' in anomaly.get('anomaly_type', '') and severity_score > 50
                ]):
                    is_critical = True
                
                if is_critical:
                    filtered_anomalies.append(anomaly)
            
            # Maximum 500 anomali limiti
            if len(filtered_anomalies) > 500:
                logger.info(f"Limiting from {len(filtered_anomalies)} to 500 most critical")
                # Severity score'a göre sırala ve ilk 500'ü al
                filtered_anomalies.sort(key=lambda x: x.get('severity_score', 0), reverse=True)
                filtered_anomalies = filtered_anomalies[:500]
            
            # Analizi güncelle
            analysis['critical_anomalies'] = filtered_anomalies
            
            # Summary'yi güncelle
            if 'summary' in analysis:
                filtered_count = len(filtered_anomalies)
                total_logs = analysis['summary'].get('total_logs', 1)
                
                analysis['summary']['n_anomalies'] = filtered_count
                analysis['summary']['anomaly_rate'] = (filtered_count / total_logs * 100) if total_logs > 0 else 0
                
                # False positive oranını ekle
                false_positive_rate = ((original_count - filtered_count) / original_count * 100) if original_count > 0 else 0
                analysis['summary']['false_positive_filtered'] = {
                    'original_count': original_count,
                    'filtered_count': filtered_count,
                    'false_positive_rate': false_positive_rate
                }
        
        logger.info(f"Post-processing complete: {original_count} -> {len(analysis.get('critical_anomalies', []))} anomalies")
        logger.info(f"Filtered out {original_count - len(analysis.get('critical_anomalies', []))} false positives")
        
        return analysis
    
    def _create_analysis_description(self, analysis: Dict, time_range: str) -> str:
        """Analiz sonucu için kullanıcı dostu açıklama oluştur"""
        summary = analysis["summary"]
        
        # Temel bilgiler
        desc = f"📊 **ÖZET**: {time_range} zaman aralığında {summary['total_logs']:,} log analiz edildi.\n\n"
        
        # Ne oldu?
        desc += f"🔍 **NE OLDU?**\n"
        desc += f"• {summary['n_anomalies']} adet anomali tespit edildi (%{summary['anomaly_rate']:.1f})\n"
        
        # Ne zaman oldu?
        if "temporal_analysis" in analysis and "peak_hours" in analysis["temporal_analysis"]:
            peak_hours = analysis["temporal_analysis"]["peak_hours"]
            desc += f"\n⏰ **NE ZAMAN OLDU?**\n"
            desc += f"• En yoğun anomali saatleri: {', '.join(map(str, peak_hours))}\n"
        
        # Neden oldu? (En sık görülen anomali tipleri)
        desc += f"\n❓ **NEDEN OLDU?**\n"
        if "component_analysis" in analysis:
            top_components = sorted(analysis["component_analysis"].items(), 
                                   key=lambda x: x[1]["anomaly_count"], 
                                   reverse=True)[:3]
            for comp, stats in top_components:
                desc += f"• {comp}: {stats['anomaly_count']} anomali (%{stats['anomaly_rate']:.1f})\n"
        
        # Kritik bulgular
        desc += f"\n⚠️ **KRİTİK BULGULAR**\n"
        if "security_alerts" in analysis:
            if "drop_operations" in analysis["security_alerts"]:
                drop_count = analysis["security_alerts"]["drop_operations"]["count"]
                desc += f"• 🚨 {drop_count} adet DROP operasyonu tespit edildi!\n"
        
        if "feature_importance" in analysis:
            critical_features = [(feat, stats) for feat, stats in analysis["feature_importance"].items() 
                               if stats.get("ratio", 0) > 5]
            if critical_features:
                desc += f"• Yüksek risk faktörleri: "
                desc += ", ".join([f"{feat} (x{stats['ratio']:.1f})" for feat, stats in critical_features[:3]])
                desc += "\n"
        
        logger.debug("Analysis description created successfully")
        return desc
    
    def _create_suggestions(self, analysis: Dict) -> List[str]:
        """Analiz sonucuna göre aksiyona yönelik öneriler oluştur"""
        suggestions = []
        
        # Anomali oranına göre
        anomaly_rate = analysis["summary"]["anomaly_rate"]
        if anomaly_rate > 5:
            suggestions.append("🔴 ACİL: Yüksek anomali oranı! Sistem yöneticilerine hemen bilgi verin.")
            suggestions.append("📋 YAPILACAK: Son 1 saatteki sistem değişikliklerini kontrol edin.")
        elif anomaly_rate > 2:
            suggestions.append("🟡 ORTA: Normal üstü anomali seviyesi. Yakından takip edin.")
        else:
            suggestions.append("🟢 NORMAL: Anomali seviyesi kabul edilebilir sınırlarda.")
        
        # DROP operasyonları
        if "security_alerts" in analysis:
            suggestions.append("🚨 GÜVENLİK: DROP operasyonları tespit edildi!")
            suggestions.append("🔐 YAPILACAK: Veritabanı yetkilerini ve erişim loglarını kontrol edin.")
            suggestions.append("💾 YAPILACAK: Etkilenen koleksiyonların yedeklerini kontrol edin.")
        
        # Component bazlı öneriler
        if "component_analysis" in analysis:
            high_anomaly_components = [(comp, stats) for comp, stats in analysis["component_analysis"].items() 
                                      if stats["anomaly_rate"] > 20]
            if high_anomaly_components:
                comp_names = [comp for comp, _ in high_anomaly_components[:3]]
                suggestions.append(f"🔧 YAPILACAK: {', '.join(comp_names)} componentlerini inceleyin.")
                suggestions.append("📊 YAPILACAK: Bu componentlerin performans metriklerini kontrol edin.")
        
        # Temporal pattern önerileri
        if "temporal_analysis" in analysis and "peak_hours" in analysis["temporal_analysis"]:
            peak_hours = analysis["temporal_analysis"]["peak_hours"]
            suggestions.append(f"⏰ BİLGİ: Anomaliler genelde saat {peak_hours[0]} civarında yoğunlaşıyor.")
            suggestions.append("📅 YAPILACAK: Bu saatlerdeki planlı işlemleri gözden geçirin.")
        
        return suggestions

    def _generate_ai_explanation(self, anomaly_data: Dict[str, Any]) -> Dict[str, Any]:
        """LCWGPT kullanarak anomali verisi için zengin açıklama üret"""
        logger.info(f"=== AI EXPLANATION DEBUG ===")
        logger.info(f"LLM connected: {self.llm_connector.is_connected() if self.llm_connector else False}")
        
        if not self.llm_connector or not self.llm_connector.is_connected():
            logger.warning("LLM not connected, returning basic explanation")
            return self._create_fallback_explanation(anomaly_data)
        
        try:
            logger.info("Starting AI explanation generation...")
            # Summary'den büyük verileri temizle
            summary = anomaly_data.get("summary", {}).copy()
            # Sadece gerekli özet bilgileri kalsın
            summary_keys_to_keep = ['total_logs', 'n_anomalies', 'anomaly_rate', 'score_range']
            summary = {k: v for k, v in summary.items() if k in summary_keys_to_keep}
            critical_anomalies = anomaly_data.get("critical_anomalies", [])[:10]
            security_alerts = anomaly_data.get("security_alerts", {})
            
            # Component analysis - sadece ilk 10 component
            component_analysis = anomaly_data.get("component_analysis", {})
            if len(component_analysis) > 10:
                component_analysis = dict(list(component_analysis.items())[:10])
            
            # Temporal analysis - hourly_distribution'ı sınırla
            temporal_analysis = anomaly_data.get("temporal_analysis", {})
            feature_importance = anomaly_data.get("feature_importance", {})
            if len(feature_importance) > 10:
                feature_importance = dict(list(feature_importance.items())[:10])
            
            # DEBUG: Log actual sizes
            logger.info(f"[DEBUG AI] Summary keys: {list(summary.keys())}")
            logger.info(f"[DEBUG AI] Critical anomalies count: {len(critical_anomalies)}")
            logger.info(f"[DEBUG AI] Component analysis count: {len(component_analysis)}")
            logger.info(f"[DEBUG AI] Temporal analysis keys: {list(temporal_analysis.keys())}")
            if 'hourly_distribution' in temporal_analysis:
                logger.info(f"[DEBUG AI] Hourly distribution size: {len(temporal_analysis['hourly_distribution'])}")
            logger.info(f"[DEBUG AI] Feature importance count: {len(feature_importance)}")
            
            # Summary içindeki büyük verileri de kontrol et
            if 'score_distribution' in summary:
                logger.info(f"[DEBUG AI] Score distribution size: {len(summary.get('score_distribution', {}))}")
            if 'anomaly_indices' in summary:
                logger.info(f"[DEBUG AI] Anomaly indices size: {len(summary.get('anomaly_indices', []))}")
            
            # Optimize edilmiş system prompt - token tasarrufu ve odaklı analiz
            system_prompt = """MongoDB anomali uzmanısın. Kısa, net, anlamlı ve aksiyona yönelik analiz yap.

FORMATIN (MAX 500 kelime):
1. ÖZET (3-4 cümle): Ne bulundu, kritik mi?
2. TOP 5 KRİTİK SORUN: Component, sebep, risk, feature, log mesajı
3. ACİL AKSİYONLAR: Max 3 madde, spesifik ol, rastgele verme 
4. İZLEME ÖNERİSİ: 1 cümle

Türkçe yaz. MongoDB best practice'lerini kullan. Rastgele öneri verme. Teknik ol ama anlaşılır ol. Gereksiz tekrar yapma"""
            
            # Optimize edilmiş user prompt - daha fazla context ile
            user_prompt = f"""Analiz Özeti: {summary.get('n_anomalies', 0)} anomali / {summary.get('total_logs', 0):,} log (%{summary.get('anomaly_rate', 0):.1f})
Ortalama anomali skoru: {summary.get('score_range', {}).get('mean', 0):.3f}

TOP 10 KRİTİK ANOMALİ:
{self._format_critical_anomalies_for_prompt(critical_anomalies[:10])}

COMPONENT ANALİZİ:
{self._format_component_analysis_for_prompt(component_analysis)}

{self._format_security_alerts_for_prompt(security_alerts)}

ZAMANSAL DAĞILIM:
Peak saat: {temporal_analysis.get('peak_hours', [0])[0] if temporal_analysis.get('peak_hours') else 'N/A'}
En yoğun 3 saat: {', '.join(map(str, temporal_analysis.get('peak_hours', [])[:3]))}

ÖNEMLİ FEATURE'LAR:
{self._format_feature_importance_for_prompt(feature_importance)}"""
            
            # DEBUG: Log prompt size
            logger.info(f"[DEBUG AI] System prompt length: {len(system_prompt)} chars")
            logger.info(f"[DEBUG AI] User prompt length: {len(user_prompt)} chars")
            logger.info(f"[DEBUG AI] Total prompt length: {len(system_prompt) + len(user_prompt)} chars")
            
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]
            
            response = self.llm_connector.invoke(messages)
            ai_explanation = response.content
            
            logger.info(f"AI response received, length: {len(ai_explanation)}")
            
            # Yeni parse fonksiyonu - LCWGPT'nin yeni formatı için
            parsed_explanation = self._parse_ai_explanation_structured(ai_explanation)
            
            logger.info(f"AI explanation parsed successfully: {list(parsed_explanation.keys())}")
            return parsed_explanation
            
        except Exception as e:
            logger.error(f"Error generating AI explanation: {e}")
            return self._create_fallback_explanation(anomaly_data)

    def _parse_ai_explanation(self, ai_text: str) -> Dict[str, Any]:
        """AI metnini yapılandırılmış formata dönüştür"""
        sections = {
            "ne_tespit_edildi": "",
            "potansiyel_etkiler": [],
            "muhtemel_nedenler": [],
            "onerilen_aksiyonlar": []
        }
        current_section_key = None
        
        section_map = {
            "ne_tespit_edildi": ["NE TESPİT EDİLDİ"],
            "potansiyel_etkiler": ["POTANSİYEL ETKİLER", "NEDEN ÖNEMLİ"],
            "muhtemel_nedenler": ["MUHTEMEL NEDENLER"],
            "onerilen_aksiyonlar": ["ÖNERİLEN AKSİYONLAR", "NE YAPILMALI"]
        }

        for line in ai_text.split('\n'):
            line_upper = line.upper()
            found_new_section = False
            for key, keywords in section_map.items():
                for keyword in keywords:
                    if keyword in line_upper:
                        current_section_key = key
                        found_new_section = True
                        break
                if found_new_section:
                    break
            
            if found_new_section:
                continue

            if current_section_key:
                clean_line = line.strip().lstrip('•-*0123456789. ')
                if not clean_line:
                    continue
                if current_section_key == "ne_tespit_edildi":
                    sections[current_section_key] += clean_line + " "
                else:
                    sections[current_section_key].append(clean_line)
        
        sections["ne_tespit_edildi"] = sections["ne_tespit_edildi"].strip()
        return sections
    
    def _parse_ai_explanation_improved(self, ai_text: str) -> Dict[str, Any]:
        """AI metnini yapılandırılmış formata dönüştür - LCWGPT markdown formatı için optimize edilmiş"""
        sections = {
            "ne_tespit_edildi": "",
            "potansiyel_etkiler": [],
            "muhtemel_nedenler": [],
            "onerilen_aksiyonlar": []
        }
        
        # Eğer metin çok kısa veya boşsa fallback kullan
        if not ai_text or len(ai_text) < 50:
            return sections
        
        # Markdown başlıklarını temizle
        clean_text = ai_text.replace('```markdown', '').replace('```', '').strip()
        
        # Bölümleri ayır
        import re
        
        # Özet bölümünü bul
        ozet_match = re.search(r'#### Özet\s*(.*?)(?=####|\Z)', clean_text, re.DOTALL)
        if ozet_match:
            ozet_lines = ozet_match.group(1).strip().split('\n')
            ozet_items = []
            for line in ozet_lines:
                if line.strip() and '**' in line:
                    # Markdown bold'ları temizle ve liste öğesi yap
                    clean_line = line.replace('**', '').replace('- ', '').strip()
                    ozet_items.append(f"• {clean_line}")
            sections["ne_tespit_edildi"] = "\n".join(ozet_items)
        
        # Kritik Anomaliler bölümünü bul
        kritik_match = re.search(r'#### Kritik Anomaliler\s*(.*?)(?=####|\Z)', clean_text, re.DOTALL)
        if kritik_match:
            kritik_text = kritik_match.group(1).strip()
            # Her bileşen için anomalileri bul
            component_matches = re.findall(r'\*\*([^*]+) Bileşeni[^:]*:\*\*', kritik_text)
            for comp in component_matches[:3]:  # İlk 3 bileşen
                sections["potansiyel_etkiler"].append(f"{comp} bileşeninde kritik anomaliler tespit edildi")
            
            # En yüksek skorlu anomaliyi bul
            skor_matches = re.findall(r'\*\*Skor:\*\* ([0-9.-]+)', kritik_text)
            if skor_matches:
                max_skor = max(float(s) for s in skor_matches)
                sections["potansiyel_etkiler"].append(f"En kritik anomali skoru: {max_skor}")
        
        # Component Analizi bölümünü bul
        component_match = re.search(r'#### (Bileşen Analizi|Component Analizi)\s*(.*?)(?=####|\Z)', clean_text, re.DOTALL)
        if component_match:
            component_text = component_match.group(2).strip()
            # %100 anomali oranına sahip bileşenleri bul
            full_anomaly_components = re.findall(r'\*\*([^*]+) Bileşeni:\*\*.*?anomali oranı:\*\* %100', component_text, re.DOTALL)
            for comp in full_anomaly_components[:3]:  # İlk 3 tanesi
                sections["muhtemel_nedenler"].append(f"{comp} bileşeninde tüm loglar anomali olarak işaretlenmiş (%100)")
            
            # Yüksek anomali oranına sahip diğer bileşenleri bul
            high_anomaly = re.findall(r'\*\*([^*]+) Bileşeni:\*\*.*?anomali oranı:\*\* %([0-9.]+)', component_text, re.DOTALL)
            for comp, rate in high_anomaly:
                if float(rate) > 50 and comp not in [c for c in full_anomaly_components]:
                    sections["muhtemel_nedenler"].append(f"{comp} bileşeninde yüksek anomali oranı (%{rate})")
        
        # Güvenlik Uyarıları bölümünü kontrol et
        guvenlik_match = re.search(r'#### Güvenlik Uyarıları\s*(.*?)(?=####|\Z)', clean_text, re.DOTALL)
        if guvenlik_match:
            guvenlik_text = guvenlik_match.group(1).strip()
            if "güvenlik uyarısı yok" not in guvenlik_text.lower():
                # Güvenlik uyarıları varsa ekle
                guvenlik_items = re.findall(r'- \*\*([^*]+)\*\*', guvenlik_text)
                for item in guvenlik_items:
                    sections["potansiyel_etkiler"].append(f"GÜVENLİK UYARISI: {item}")
        
        # Zaman bazlı analizi ekle
        saat_match = re.search(r'en yoğun anomali saatleri[^:]*:\s*\[([^\]]+)\]', clean_text, re.IGNORECASE)
        if saat_match:
            saatler = saat_match.group(1)
            sections["muhtemel_nedenler"].append(f"Anomaliler özellikle saat {saatler} arasında yoğunlaşmış")
        
        # Önerilen aksiyonları oluştur
        if sections["potansiyel_etkiler"] or sections["muhtemel_nedenler"]:
            # Kritik anomali varsa
            if any("kritik" in etki.lower() for etki in sections["potansiyel_etkiler"]):
                sections["onerilen_aksiyonlar"].append("Kritik anomalileri acil olarak inceleyin")
            
            # %100 anomali oranı varsa
            if any("%100" in neden for neden in sections["muhtemel_nedenler"]):
                sections["onerilen_aksiyonlar"].append("Tüm logları anomali olarak işaretleyen bileşenlerde sistem kontrolü yapın")
            
            # Plan executor error varsa
            if "Plan executor error" in clean_text:
                sections["onerilen_aksiyonlar"].append("Query plan executor hatalarını gidermek için index optimizasyonu yapın")
            
            # Oplog fetcher error varsa
            if "Oplog fetcher stopped" in clean_text:
                sections["onerilen_aksiyonlar"].append("Replication oplog hatalarını kontrol edin, replica set sağlığını doğrulayın")
            
            # Authentication failure varsa
            if "Authentication failed" in clean_text:
                sections["onerilen_aksiyonlar"].append("Authentication hatalarını inceleyin, güvenlik loglarını kontrol edin")
            
            # Zaman bazlı öneriler
            if saat_match:
                sections["onerilen_aksiyonlar"].append(f"Saat {saatler} arasındaki yoğun aktiviteleri ve scheduled job'ları kontrol edin")
        
        # Varsayılan öneriler
        if not sections["onerilen_aksiyonlar"]:
            sections["onerilen_aksiyonlar"] = [
                "Anomali tespit edilen bileşenleri detaylı inceleyin",
                "Sistem performans metriklerini kontrol edin",
                "MongoDB replica set durumunu doğrulayın"
            ]
        
        # Boş bölümleri doldur
        if not sections["ne_tespit_edildi"]:
            sections["ne_tespit_edildi"] = "MongoDB log analizi tamamlandı"
        
        if not sections["potansiyel_etkiler"]:
            sections["potansiyel_etkiler"] = ["Sistem performansında düşüş riski"]
        
        if not sections["muhtemel_nedenler"]:
            sections["muhtemel_nedenler"] = ["Normal operasyon dışı aktiviteler tespit edildi"]
        
        return sections
    def _parse_ai_explanation_structured(self, ai_text: str) -> Dict[str, Any]:
        """LCWGPT'nin kısa formatını parse et - Optimize versiyon"""
        sections = {
            "ne_tespit_edildi": "",
            "potansiyel_etkiler": [],
            "muhtemel_nedenler": [],
            "onerilen_aksiyonlar": []
        }
        
        if not ai_text or len(ai_text) < 20:
            return sections
        
        import re
        
        # Temiz metin al
        clean_text = ai_text.strip()
        
        # ÖZET bölümünü bul (ilk paragraf)
        lines = clean_text.split('\n')
        ozet_lines = []
        
        for i, line in enumerate(lines):
            if line.strip():
                if 'ÖZET' in line or i < 3:  # İlk 3 satır özet olabilir
                    ozet_lines.append(line.strip())
                elif any(marker in line.upper() for marker in ['TOP', 'KRİTİK', 'SORUN']):
                    break
        
        sections["ne_tespit_edildi"] = ' '.join(ozet_lines)
        
        # TOP 3 KRİTİK SORUN bölümünü parse et
        kritik_start = False
        for line in lines:
            if 'TOP' in line.upper() and 'KRİTİK' in line.upper():
                kritik_start = True
                continue
            elif 'ACİL' in line.upper() and 'AKSİYON' in line.upper():
                kritik_start = False
            elif kritik_start and line.strip() and not line.strip().startswith('#'):
                sections["potansiyel_etkiler"].append(line.strip())
        
        # ACİL AKSİYONLAR bölümünü parse et
        aksiyon_start = False
        for line in lines:
            if 'ACİL' in line.upper() and 'AKSİYON' in line.upper():
                aksiyon_start = True
                continue
            elif 'İZLEME' in line.upper():
                aksiyon_start = False
            elif aksiyon_start and line.strip() and not line.strip().startswith('#'):
                sections["onerilen_aksiyonlar"].append(line.strip())
        
        # İZLEME ÖNERİSİ - muhtemel nedenler olarak ekle
        for line in lines:
            if 'İZLEME' in line.upper():
                idx = lines.index(line)
                if idx + 1 < len(lines) and lines[idx + 1].strip():
                    sections["muhtemel_nedenler"].append(lines[idx + 1].strip())
        
        # Boş bölümleri doldur
        if not sections["potansiyel_etkiler"]:
            sections["potansiyel_etkiler"] = ["Sistem performansında anomali tespit edildi"]
        
        if not sections["muhtemel_nedenler"]:
            sections["muhtemel_nedenler"] = ["Detaylı inceleme gerekiyor"]
        
        if not sections["onerilen_aksiyonlar"]:
            sections["onerilen_aksiyonlar"] = ["Anomali loglarını inceleyin"]
        
        return sections


    def _create_fallback_explanation(self, anomaly_data: Dict[str, Any]) -> Dict[str, Any]:
        """AI başarısız olursa kullanılacak detaylı fallback açıklama"""
        summary = anomaly_data.get('summary', {})
        component_analysis = anomaly_data.get('component_analysis', {})
        temporal_analysis = anomaly_data.get('temporal_analysis', {})
        critical_anomalies = anomaly_data.get('critical_anomalies', [])[:3]
        
        ne_tespit_edildi = f"• Toplam {summary.get('total_logs', 0):,} log içinde {summary.get('n_anomalies', 0)} anomali tespit edildi (%{summary.get('anomaly_rate', 0):.1f})\n"
        
        # Component detayları ekle
        for comp, stats in list(component_analysis.items())[:3]:
            ne_tespit_edildi += f"• {comp} bileşeninde {stats.get('anomaly_count', 0)} anomali (%{stats.get('anomaly_rate', 0):.1f})\n"
        
        # Kritik anomaliler
        if critical_anomalies:
            ne_tespit_edildi += f"• En kritik anomali skoru: {critical_anomalies[0].get('score', 0):.3f} ({critical_anomalies[0].get('component', 'N/A')} bileşeni)"
        
        # Zamansal analiz
        if temporal_analysis.get('peak_hours'):
            peak_hours = temporal_analysis['peak_hours']
            ne_tespit_edildi += f"\n• Anomaliler en çok saat {', '.join(map(str, peak_hours))} arasında yoğunlaşmış"
        
        return {
            "ne_tespit_edildi": ne_tespit_edildi,
            "potansiyel_etkiler": [
                f"Sistem performansı %{summary.get('anomaly_rate', 0):.1f} oranında etkilenebilir",
                f"En kritik {len(component_analysis)} bileşende sorun tespit edildi",
                f"Ortalama anomali skoru {summary.get('score_range', {}).get('mean', 0):.3f} seviyesinde"
            ],
            "muhtemel_nedenler": [
                "Yoğun kullanım veya sistem sorunu",
                f"Saat {temporal_analysis.get('peak_hours', [0])[0] if temporal_analysis.get('peak_hours') else 'belirli'} civarında artan yük",
                f"En yüksek anomali oranı %{max([s.get('anomaly_rate', 0) for s in component_analysis.values()] or [0]):.1f} ile tespit edildi"
            ],
            "onerilen_aksiyonlar": [
                f"{summary.get('n_anomalies', 0)} anomaliyi detaylı inceleyin",
                f"Özellikle %{max([s.get('anomaly_rate', 0) for s in component_analysis.values()] or [0]):.1f} anomali oranına sahip bileşenlere odaklanın",
                f"Skor değeri {summary.get('score_range', {}).get('min', 0):.3f} altındaki kritik anomalileri öncelikle çözün"
            ]
        }

    def _format_critical_anomalies_detailed(self, anomalies: List[Dict]) -> str:
        """Prompt için kritik anomalileri detaylı formatlar"""
        if not anomalies: 
            return "Kritik anomali tespit edilmedi."
        
        result = []
        # Component bazlı gruplama yap
        component_groups = {}
        for a in anomalies:
            comp = a.get('component', 'N/A')
            if comp not in component_groups:
                component_groups[comp] = []
            component_groups[comp].append(a)
        
        # Her component için detaylı bilgi ver
        for comp, comp_anomalies in component_groups.items():
            result.append(f"\n{comp} Bileşeni ({len(comp_anomalies)} anomali):")
            for i, a in enumerate(comp_anomalies[:3], 1):  # Her component'ten ilk 3
                result.append(f"  {i}. Skor: {a.get('score', 0):.3f}")
                result.append(f"     Zaman: {a.get('timestamp', 'N/A')}")
                result.append(f"     Mesaj: {a.get('message', '')[:80]}...")
                result.append(f"     Önem: {a.get('severity', 'N/A')}")
        
        return "\n".join(result)
    
    def _format_critical_anomalies_for_prompt(self, anomalies: List[Dict]) -> str:
        """Kritik anomalileri prompt için formatla"""
        if not anomalies:
            return "Kritik anomali tespit edilmedi."
        
        result = []
        for i, a in enumerate(anomalies, 1):
            comp = a.get('component', 'N/A')
            severity = a.get('severity', 'W')
            score = a.get('score', 0)
            msg = a.get('message', '')
            
            # Mesajdan önemli bilgileri çıkar
            msg_extract = msg[:80] if msg else 'N/A'
            
            # MongoDB spesifik pattern'leri tespit et
            if 'slow' in msg.lower() or 'ms' in msg.lower():
                # Milisaniye bilgisini çıkar
                import re
                ms_match = re.search(r'(\d+)ms', msg)
                if ms_match:
                    msg_extract = f"Slow query: {ms_match.group(1)}ms"
            elif 'collscan' in msg.lower():
                msg_extract = "COLLSCAN detected - no index used"
            elif 'authentication failed' in msg.lower():
                msg_extract = "Auth failure"
            elif 'drop' in msg.lower():
                msg_extract = "DROP operation"
            
            result.append(f"{i}. [{comp}] {msg_extract}")
            result.append(f"   Skor: {score:.3f} | Severity: {severity}")
            
        return "\n".join(result)

    def _format_component_analysis_for_prompt(self, components: Dict) -> str:
        """Component analizini prompt için formatla"""
        if not components:
            return "Component analizi mevcut değil."
        
        result = []
        # En yüksek anomali oranına göre sırala
        sorted_components = sorted(components.items(), 
                                 key=lambda x: x[1].get('anomaly_rate', 0), 
                                 reverse=True)
        
        for comp, stats in sorted_components[:5]:
            anomaly_count = stats.get('anomaly_count', 0)
            total_count = stats.get('total_count', 0)
            anomaly_rate = stats.get('anomaly_rate', 0)
            
            result.append(f"- {comp}: {anomaly_count}/{total_count} anomali (%{anomaly_rate:.1f})")
        
        return "\n".join(result)

    def _create_fallback_explanation(self, anomaly_data: Dict[str, Any]) -> Dict[str, Any]:
        """AI başarısız olursa kullanılacak detaylı fallback açıklama"""
        summary = anomaly_data.get('summary', {})
        component_analysis = anomaly_data.get('component_analysis', {})
        temporal_analysis = anomaly_data.get('temporal_analysis', {})
        critical_anomalies = anomaly_data.get('critical_anomalies', [])[:3]
        
        ne_tespit_edildi = f"• Toplam {summary.get('total_logs', 0):,} log içinde {summary.get('n_anomalies', 0)} anomali tespit edildi (%{summary.get('anomaly_rate', 0):.1f})\n"
        
        # Component detayları ekle
        for comp, stats in list(component_analysis.items())[:3]:
            ne_tespit_edildi += f"• {comp} bileşeninde {stats.get('anomaly_count', 0)} anomali (%{stats.get('anomaly_rate', 0):.1f})\n"
        
        # Kritik anomaliler
        if critical_anomalies:
            ne_tespit_edildi += f"• En kritik anomali skoru: {critical_anomalies[0].get('score', 0):.3f} ({critical_anomalies[0].get('component', 'N/A')} bileşeni)"
        
        # Zamansal analiz
        if temporal_analysis.get('peak_hours'):
            peak_hours = temporal_analysis['peak_hours']
            ne_tespit_edildi += f"\n• Anomaliler en çok saat {', '.join(map(str, peak_hours))} arasında yoğunlaşmış"
        
        return {
            "ne_tespit_edildi": ne_tespit_edildi,
            "potansiyel_etkiler": [
                f"Sistem performansı %{summary.get('anomaly_rate', 0):.1f} oranında etkilenebilir",
                f"En kritik {len(component_analysis)} bileşende sorun tespit edildi",
                f"Ortalama anomali skoru {summary.get('score_range', {}).get('mean', 0):.3f} seviyesinde"
            ],
            "muhtemel_nedenler": [
                "Yoğun kullanım veya sistem sorunu",
                f"Saat {temporal_analysis.get('peak_hours', [0])[0] if temporal_analysis.get('peak_hours') else 'belirli'} civarında artan yük",
                f"En yüksek anomali oranı %{max([s.get('anomaly_rate', 0) for s in component_analysis.values()] or [0]):.1f} ile tespit edildi"
            ],
            "onerilen_aksiyonlar": [
                f"{summary.get('n_anomalies', 0)} anomaliyi detaylı inceleyin",
                f"Özellikle %{max([s.get('anomaly_rate', 0) for s in component_analysis.values()] or [0]):.1f} anomali oranına sahip bileşenlere odaklanın",
                f"Skor değeri {summary.get('score_range', {}).get('min', 0):.3f} altındaki kritik anomalileri öncelikle çözün"
            ]
        }

    def _format_critical_anomalies_detailed(self, anomalies: List[Dict]) -> str:
        """Prompt için kritik anomalileri detaylı formatlar"""
        if not anomalies: 
            return "Kritik anomali tespit edilmedi."
        
        result = []
        # Component bazlı gruplama yap
        component_groups = {}
        for a in anomalies:
            comp = a.get('component', 'N/A')
            if comp not in component_groups:
                component_groups[comp] = []
            component_groups[comp].append(a)
        
        # Her component için detaylı bilgi ver
        for comp, comp_anomalies in component_groups.items():
            result.append(f"\n{comp} Bileşeni ({len(comp_anomalies)} anomali):")
            for i, a in enumerate(comp_anomalies[:3], 1):  # Her component'ten ilk 3
                result.append(f"  {i}. Skor: {a.get('score', 0):.3f}")
                result.append(f"     Zaman: {a.get('timestamp', 'N/A')}")
                result.append(f"     Mesaj: {a.get('message', '')[:80]}...")
                result.append(f"     Önem: {a.get('severity', 'N/A')}")
        
        return "\n".join(result)
    
    def _format_critical_anomalies_for_prompt(self, anomalies: List[Dict]) -> str:
        """Kritik anomalileri prompt için formatla"""
        if not anomalies:
            return "Kritik anomali tespit edilmedi."
        
        result = []
        for i, a in enumerate(anomalies, 1):
            result.append(f"{i}. {a.get('timestamp', 'N/A')} - {a.get('component', 'N/A')}")
            result.append(f"   Mesaj: {a.get('message', '')[:100]}...")
            result.append(f"   Skor: {a.get('score', 0):.3f} (Önem: {a.get('severity', 'N/A')})")
            result.append("")
        
        return "\n".join(result)

    def _format_component_analysis_for_prompt(self, components: Dict) -> str:
        """Component analizini prompt için formatla"""
        if not components:
            return "Component analizi mevcut değil."
        
        result = []
        # En yüksek anomali oranına göre sırala
        sorted_components = sorted(components.items(), 
                                 key=lambda x: x[1].get('anomaly_rate', 0), 
                                 reverse=True)
        
        for comp, stats in sorted_components[:5]:
            anomaly_count = stats.get('anomaly_count', 0)
            total_count = stats.get('total_count', 0)
            anomaly_rate = stats.get('anomaly_rate', 0)
            
            result.append(f"- {comp}: {anomaly_count}/{total_count} anomali (%{anomaly_rate:.1f})")
        
        return "\n".join(result)

    def _format_feature_importance_for_prompt(self, features: Dict) -> str:
        """Feature importance'ı prompt için formatla"""
        if not features:
            return "Feature analizi mevcut değil."
        
        result = []
        # Ratio'ya göre sırala (yüksek ratio = önemli)
        sorted_features = sorted(features.items(), 
                               key=lambda x: x[1].get('ratio', 0), 
                               reverse=True)
        
        for feat, stats in sorted_features[:3]:
            if stats.get('ratio', 0) > 10:  # Sadece önemli olanları göster
                result.append(f"- {feat}: {stats.get('ratio', 0):.1f}x normal değerden sapma")
        
        return "\n".join(result) if result else "Normal değerler içinde."

    def _format_security_alerts_for_prompt(self, alerts: Dict) -> str:
        """Güvenlik uyarılarını prompt için formatla"""
        if not alerts:
            return "Güvenlik uyarısı yok."
        
        result = []
        if "drop_operations" in alerts:
            result.append(f"- DROP operasyonları: {alerts['drop_operations'].get('count', 0)} adet")
        if "auth_failures" in alerts:
            result.append(f"- Authentication hataları: {alerts['auth_failures'].get('count', 0)} adet")
        
        return "\n".join(result) if result else "Güvenlik uyarısı yok."
    
    def _format_security_alerts_detailed(self, alerts: Dict) -> str:
        """Prompt için güvenlik uyarılarını detaylı formatlar"""
        if not alerts: 
            return "Güvenlik uyarısı yok."
        
        result = []
        if "drop_operations" in alerts:
            drop_info = alerts['drop_operations']
            result.append(f"🚨 DROP Operasyonları Tespit Edildi:")
            result.append(f"   - Toplam sayı: {drop_info.get('count', 0)}")
            result.append(f"   - İlk 5 index: {drop_info.get('indices', [])[:5]}")
            result.append(f"   - Risk seviyesi: YÜKSEK")
        
        # Diğer güvenlik uyarıları için yer
        if "auth_failures" in alerts:
            auth_info = alerts['auth_failures']
            result.append(f"🔐 Authentication Hataları:")
            result.append(f"   - Toplam: {auth_info.get('count', 0)}")
            result.append(f"   - Benzersiz IP sayısı: {auth_info.get('unique_ips', 0)}")
        
        return "\n".join(result) if result else "Güvenlik uyarısı yok."

    def _format_component_analysis_detailed(self, components: Dict) -> str:
        """Prompt için component analizini detaylı formatlar"""
        if not components: 
            return "Component analizi mevcut değil."
        
        result = ["\nBileşen Bazlı Anomali Dağılımı:"]
        
        # En yüksek anomali oranına göre sırala
        sorted_components = sorted(components.items(), 
                                 key=lambda x: x[1].get('anomaly_rate', 0), 
                                 reverse=True)
        
        total_anomalies = sum(stats.get('anomaly_count', 0) for _, stats in components.items())
        
        for comp, stats in sorted_components[:5]:
            anomaly_count = stats.get('anomaly_count', 0)
            anomaly_rate = stats.get('anomaly_rate', 0)
            total_count = stats.get('total_count', 0)
            percentage_of_all = (anomaly_count / total_anomalies * 100) if total_anomalies > 0 else 0
            
            result.append(f"\n{comp} Bileşeni:")
            result.append(f"  - Anomali sayısı: {anomaly_count} / {total_count} toplam log")
            result.append(f"  - Bileşen içi anomali oranı: %{anomaly_rate:.1f}")
            result.append(f"  - Tüm anomaliler içindeki payı: %{percentage_of_all:.1f}")
        
        return "\n".join(result)

    def _format_critical_anomalies(self, anomalies: List[Dict]) -> str:
        """Prompt için kritik anomalileri formatlar"""
        if not anomalies: return "Kritik anomali tespit edilmedi."
        result = [f"{i}. Skor: {a.get('score', 0):.3f}, Component: {a.get('component', 'N/A')}, Mesaj: {a.get('message', '')[:80]}..." 
                  for i, a in enumerate(anomalies, 1)]
        return "\n".join(result)

    def _format_security_alerts(self, alerts: Dict) -> str:
        """Prompt için güvenlik uyarılarını formatlar"""
        if not alerts: return "Güvenlik uyarısı yok."
        result = [f"DROP operasyonları: {alerts['drop_operations'].get('count', 0)} adet" 
                  if "drop_operations" in alerts else ""]
        return "\n".join(filter(None, result)) or "Güvenlik uyarısı yok."
    
    def _generate_anomaly_message(self, anomaly_data: Dict) -> str:
        """Anomali kaydı için kullanıcı dostu mesaj üretir"""
        try:
            component = anomaly_data.get('component', 'N/A')
            severity = anomaly_data.get('severity', 'W')
            score = float(anomaly_data.get('score', 0))
            original_msg = anomaly_data.get('message', '')
            timestamp = anomaly_data.get('timestamp', '')
            
            # Anomali tipini belirle
            anomaly_type = self._detect_anomaly_type_from_message(original_msg, component, severity)
            
            # MongoDB-spesifik mesaj şablonları
            message_templates = {
                'auth_failure': '🔐 Kimlik doğrulama hatası tespit edildi',
                'drop_operation': '🗑️ DROP işlemi - Veri silme operasyonu',
                'index_build': '🏗️ Index oluşturma işlemi başlatıldı',
                'index_drop': '📑 Index silme işlemi gerçekleştirildi',
                'collection_scan': '🔍 COLLSCAN - Tüm koleksiyon tarandı (performans riski)',
                'high_doc_scan': '📊 Yüksek doküman tarama - Çok sayıda kayıt okundu',
                'slow_query': '🐌 Yavaş sorgu tespit edildi',
                'aggregation_issue': '⚙️ Aggregation pipeline sorunu',
                'out_of_memory': '💾 Bellek yetersizliği (OOM) uyarısı',
                'connection_limit': '🔗 Bağlantı limiti aşıldı',
                'assertion_failure': '❗ Assertion hatası - Sistem tutarsızlığı',
                'replication_issue': '🔄 Replikasyon sorunu tespit edildi',
                'replica_set_issue': '👥 Replica Set konfigürasyon sorunu',
                'storage_operation': '💿 Storage işlemi (Compact/Reindex)',
                'storage_sync': '🔄 Storage senkronizasyon işlemi',
                'shutdown': '⏹️ MongoDB kapanma olayı',
                'service_restart': '🔄 Servis yeniden başlatma',
                'fatal_error': '💀 Kritik sistem hatası',
                'connection_drop': '🔌 Bağlantı kopması',
                'network_issue': '🌐 Ağ bağlantı sorunu',
                'error': '❌ Sistem hatası',
                'warning': '⚠️ Sistem uyarısı',
                'query_issue': '❓ Sorgu işlem sorunu',
                'unknown': '❔ Sınıflandırılamayan anomali'
            }
            
            # Risk seviyesi belirleme
            if score < -0.8:
                risk_level = '🔴 KRİTİK'
                risk_desc = 'Acil müdahale gerekiyor'
            elif score < -0.75:
                risk_level = '🟡 YÜKSEK'
                risk_desc = 'Yakın takip gerekli'
            elif score < -0.7:
                risk_level = '🟠 ORTA'
                risk_desc = 'İzleme önerilen'
            else:
                risk_level = '🟢 DÜŞÜK'
                risk_desc = 'Bilgilendirme amaçlı'
            
            # Temel mesaj şablonu
            base_template = message_templates.get(anomaly_type, message_templates['unknown'])
            
            # Özel durumlar için mesajı zenginleştir
            enhanced_msg = base_template
            
            # Zaman bilgisi ekle
            if timestamp:
                time_str = str(timestamp)[:19] if len(str(timestamp)) > 19 else str(timestamp)
                enhanced_msg += f" ({time_str})"
            
            # Component bilgisi ekle
            if component and component != 'N/A':
                enhanced_msg += f" - {component} bileşeni"
            
            # Risk seviyesi ve skor ekle
            enhanced_msg += f" | {risk_level} (Skor: {score:.3f})"
            
            # Özel tip açıklamaları
            if anomaly_type == 'slow_query':
                # Mesajdan milisaniye bilgisini çıkar
                import re
                ms_match = re.search(r'(\d+)ms', original_msg)
                if ms_match:
                    ms = int(ms_match.group(1))
                    if ms > 5000:
                        enhanced_msg += f" - {ms}ms (çok yavaş)"
                    elif ms > 1000:
                        enhanced_msg += f" - {ms}ms (yavaş)"
            
            elif anomaly_type == 'collection_scan':
                enhanced_msg += " - Index kullanımı önerilen"
            
            elif anomaly_type == 'drop_operation':
                enhanced_msg += " - Güvenlik kontrolü gerekli"
            
            elif anomaly_type == 'auth_failure':
                enhanced_msg += " - Erişim logları kontrol edilmeli"
            
            elif anomaly_type == 'out_of_memory':
                enhanced_msg += " - Bellek kullanımı kritik seviyede"
            
            # Aksiyon önerisi ekle
            action_suggestions = {
                'slow_query': 'Index optimizasyonu yapın',
                'collection_scan': 'Sorgu için uygun index oluşturun', 
                'drop_operation': 'Yetkileri ve backup\'ları kontrol edin',
                'auth_failure': 'Güvenlik loglarını inceleyin',
                'out_of_memory': 'Bellek ayarlarını optimize edin',
                'replication_issue': 'Replica set durumunu kontrol edin',
                'assertion_failure': 'Sistem loglarını detaylı inceleyin',
                'fatal_error': 'Acil sistem müdahalesi gerekli'
            }
            
            if anomaly_type in action_suggestions:
                enhanced_msg += f" → {action_suggestions[anomaly_type]}"
            
            return enhanced_msg
            
        except Exception as e:
            logger.error(f"Error generating anomaly message: {e}")
            # Fallback basit mesaj
            return f"Anomali tespit edildi (Skor: {anomaly_data.get('score', 0):.3f})"
    
    def _detect_anomaly_type_from_message(self, message: str, component: str, severity: str) -> str:
        """Mesaj içeriğinden anomali tipini tespit eder"""
        if not message:
            return 'unknown'
        
        msg_lower = message.lower()
        comp_lower = component.lower() if component else ''
        
        # MongoDB-spesifik pattern matching
        if 'authentication failed' in msg_lower or 'unauthorized' in msg_lower:
            return 'auth_failure'
        elif 'drop' in msg_lower and ('collection' in msg_lower or 'index' in msg_lower):
            return 'drop_operation'
        elif 'createindex' in msg_lower or 'index build' in msg_lower:
            return 'index_build'
        elif 'dropindex' in msg_lower:
            return 'index_drop'
        elif 'collscan' in msg_lower or 'collection scan' in msg_lower:
            return 'collection_scan'
        elif 'docsexamined' in msg_lower and any(x in msg_lower for x in ['high', '10000', '50000']):
            return 'high_doc_scan'
        elif 'slow' in msg_lower or 'took' in msg_lower or 'ms' in msg_lower:
            return 'slow_query'
        elif 'aggregate' in msg_lower or 'pipeline' in msg_lower:
            return 'aggregation_issue'
        elif 'out of memory' in msg_lower or 'oom' in msg_lower:
            return 'out_of_memory'
        elif 'too many connections' in msg_lower or 'connection limit' in msg_lower:
            return 'connection_limit'
        elif 'assertion' in msg_lower or 'assert' in msg_lower:
            return 'assertion_failure'
        elif comp_lower == 'repl' or 'oplog' in msg_lower or 'replication' in msg_lower:
            return 'replication_issue'
        elif 'election' in msg_lower or 'primary' in msg_lower or 'secondary' in msg_lower:
            return 'replica_set_issue'
        elif 'compact' in msg_lower or 'reindex' in msg_lower:
            return 'storage_operation'
        elif 'journal' in msg_lower or 'checkpoint' in msg_lower:
            return 'storage_sync'
        elif 'shutdown' in msg_lower:
            return 'shutdown'
        elif 'restart' in msg_lower:
            return 'service_restart'
        elif 'fatal' in msg_lower or severity == 'F':
            return 'fatal_error'
        elif 'connection' in msg_lower and ('drop' in msg_lower or 'closed' in msg_lower):
            return 'connection_drop'
        elif comp_lower == 'network' or 'socket' in msg_lower:
            return 'network_issue'
        elif severity == 'E' or 'error' in msg_lower:
            return 'error'
        elif severity == 'W' or 'warning' in msg_lower:
            return 'warning'
        elif comp_lower == 'query':
            return 'query_issue'
        else:
            return 'unknown'
    
    def _enhance_critical_anomalies_with_messages(self, critical_anomalies: List[Dict]) -> List[Dict]:
        """Kritik anomali listesine formatlı mesajlar ekler"""
        if not critical_anomalies:
            return critical_anomalies
        
        print(f"[DEBUG] Enhancement function received {len(critical_anomalies)} anomalies")
        logger.debug(f"Enhancement input - anomalies count: {len(critical_anomalies)}")
        
        enhanced_anomalies = []
        
        for anomaly in critical_anomalies:
            try:
                # Mevcut anomali datasını kopyala
                enhanced_anomaly = anomaly.copy()
                
                # Formatlı mesaj üret
                formatted_message = self._generate_anomaly_message({
                    'component': anomaly.get('component', 'N/A'),
                    'severity': anomaly.get('severity', 'W'),
                    'score': anomaly.get('score', 0),
                    'message': anomaly.get('message', ''),
                    'timestamp': anomaly.get('timestamp', '')
                })
                
                # Anomali tipini tespit et
                anomaly_type = self._detect_anomaly_type_from_message(
                    anomaly.get('message', ''),
                    anomaly.get('component', ''),
                    anomaly.get('severity', 'W')
                )
                
                # Enhanced fields ekle
                enhanced_anomaly['formatted_message'] = formatted_message
                enhanced_anomaly['anomaly_type'] = anomaly_type
                
                # MongoDB-spesifik risk kategorisi ekle
                score = float(anomaly.get('score', 0))
                if score < -0.8:
                    enhanced_anomaly['risk_category'] = 'critical'
                    enhanced_anomaly['risk_level'] = '🔴 KRİTİK'
                elif score < -0.75:
                    enhanced_anomaly['risk_category'] = 'high'
                    enhanced_anomaly['risk_level'] = '🟡 YÜKSEK'
                elif score < -0.7:
                    enhanced_anomaly['risk_category'] = 'medium'
                    enhanced_anomaly['risk_level'] = '🟠 ORTA'
                else:
                    enhanced_anomaly['risk_category'] = 'low'
                    enhanced_anomaly['risk_level'] = '🟢 DÜŞÜK'
                
                enhanced_anomalies.append(enhanced_anomaly)
                
            except Exception as e:
                logger.error(f"Error enhancing anomaly: {e}")
                # Fallback: orijinal anomali'yi ekle
                enhanced_anomalies.append(anomaly)
        
        logger.debug(f"Enhanced {len(enhanced_anomalies)} critical anomalies with formatted messages")
        print(f"[DEBUG] Enhancement function returning {len(enhanced_anomalies)} enhanced anomalies")
        logger.debug(f"Enhancement output - enhanced anomalies count: {len(enhanced_anomalies)}")
        return enhanced_anomalies

    def _format_component_analysis(self, components: Dict) -> str:
        """Prompt için component analizini formatlar"""
        if not components: return "Component analizi mevcut değil."
        result = [f"- {comp}: {stats.get('anomaly_count', 0)} anomali (%{stats.get('anomaly_rate', 0):.1f})" 
                  for comp, stats in list(components.items())[:5]]
        return "\n".join(result)

    def _create_enriched_description(self, analysis: Dict, time_range: str, ai_explanation: Dict) -> str:
        """AI destekli zengin açıklama oluştur - geliştirilmiş format"""
        desc = "🤖 **AI DESTEKLİ ANOMALİ ANALİZİ**\n\n"
        
        # NE TESPİT EDİLDİ?
        if ai_explanation.get("ne_tespit_edildi"):
            desc += f"🔍 **NE TESPİT EDİLDİ?**\n{ai_explanation['ne_tespit_edildi']}\n\n"
        else:
            return self._create_analysis_description(analysis, time_range)
        
        # POTANSİYEL ETKİLER
        if ai_explanation.get("potansiyel_etkiler"):
            desc += "⚠️ **POTANSİYEL ETKİLER:**\n"
            for etki in ai_explanation["potansiyel_etkiler"]:
                desc += f"• {etki}\n"
            desc += "\n"
        
        # MUHTEMEL NEDENLER
        if ai_explanation.get("muhtemel_nedenler"):
            desc += "🎯 **MUHTEMEL NEDENLER:**\n"
            for neden in ai_explanation["muhtemel_nedenler"]:
                desc += f"• {neden}\n"
            desc += "\n"
        
        # ÖNERİLEN AKSİYONLAR - Numaralı liste ile
        if ai_explanation.get("onerilen_aksiyonlar"):
            desc += "💡 **ÖNERİLEN AKSİYONLAR:**\n"
            for i, aksiyon in enumerate(ai_explanation["onerilen_aksiyonlar"], 1):
                desc += f"{i}. {aksiyon}\n"
        
        # İstatistik özeti ekle
        summary = analysis.get("summary", {})
        if summary:
            desc += f"\n📊 **İSTATİSTİK ÖZETİ:**\n"
            desc += f"• Toplam Log: {summary.get('total_logs', 0):,}\n"
            desc += f"• Anomali Sayısı: {summary.get('n_anomalies', 0)} (%{summary.get('anomaly_rate', 0):.1f})\n"
            desc += f"• Ortalama Anomali Skoru: {summary.get('score_range', {}).get('mean', 0):.3f}\n"
        
        return desc

# Pydantic modelleri - Tool argümanları için
class AnalyzeLogsArgs(BaseModel):
    time_range: str = Field(default="last_hour", description="Zaman aralığı: last_hour, last_day, last_week, last_month")
    threshold: float = Field(default=0.03, description="Anomali eşik değeri")
    uploaded_file_path: Optional[str] = Field(default=None, description="Upload edilen dosya yolu")
    source_type: Optional[str] = Field(default="file", description="Veri kaynağı: file, upload, mongodb_direct, test_servers, opensearch")
    file_path: Optional[str] = Field(default=None, description="Log dosya yolu")
    connection_string: Optional[str] = Field(default=None, description="MongoDB connection string")
    server_name: Optional[str] = Field(default=None, description="Test sunucu adı")
    last_hours: Optional[int] = Field(default=None, description="Kaç saatlik log okunacak (OpenSearch için)")
    host_filter: Optional[str] = Field(default=None, description="Belirli bir MongoDB sunucusundan logları filtrele")


class SummaryArgs(BaseModel):
    top_n: int = Field(default=10, description="Gösterilecek anomali sayısı")

class TrainModelArgs(BaseModel):
    sample_size: int = Field(default=10000, description="Eğitim için kullanılacak log sayısı")


def create_anomaly_tools(config_path: str = "config/anomaly_config.json", 
                        environment: str = "test") -> List[StructuredTool]:
    """Anomaly detection tool'larını oluştur"""
    
    logger.debug(f"Creating anomaly tools with config_path={config_path}, environment={environment}")
    
    try:
        anomaly_tools = AnomalyDetectionTools(config_path, environment)
        logger.debug("AnomalyDetectionTools instance created successfully")
        
        tools = [
            StructuredTool(
                name="analyze_mongodb_logs",
                description="MongoDB loglarında anomali analizi yap",
                func=lambda **kwargs: anomaly_tools.analyze_mongodb_logs(kwargs),
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
        
        logger.debug(f"Successfully created {len(tools)} anomaly detection tools")
        return tools
        
    except Exception as e:
        logger.error(f"Error creating anomaly tools: {e}", exc_info=True)
        raise