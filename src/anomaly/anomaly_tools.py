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

        # YENİ: OpenAI connector'ı başlat
        self.openai_connector = OpenAIConnector()
        self.openai_connector.connect()
        logger.info("OpenAI connector initialized for anomaly explanations")
        
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
        try:
            def convert_numpy_types(obj):
                if isinstance(obj, np.integer):
                    return int(obj)
                elif isinstance(obj, np.floating):
                    return float(obj)
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
                        logger.info("Training new model...")
                        self.detector.train(X_filtered)
                    
                    predictions, anomaly_scores = self.detector.predict(X_filtered)
                    anomaly_count = sum(predictions == -1)
                    logger.info(f"Found {anomaly_count} anomalies in OpenSearch logs")
                    
                    # Analiz
                    analysis = self.detector.analyze_anomalies(df_filtered, X_filtered, predictions, anomaly_scores)
                    
                    # Sonuçları sakla
                    self.last_analysis = {
                        "df": df_filtered,
                        "predictions": predictions,
                        "anomaly_scores": anomaly_scores,
                        "analysis": analysis
                    }

                    ai_explanation = {}
                    # OpenAI bağlantısı varsa AI destekli açıklama üret
                    if self.openai_connector.is_connected():
                        logger.info("Generating AI-powered explanation for OpenSearch data...")
                        ai_explanation = self._generate_ai_explanation(analysis)

                    
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
                    
                    result = {
                        "description": description,
                        "data": {
                            "source": "OpenSearch",
                            "logs_analyzed": len(df),
                            "filtered_logs": len(df_filtered),  # YENİ
                            "summary": analysis["summary"],
                            "critical_anomalies": analysis["critical_anomalies"][:10],
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
            
            # Model var mı kontrol et
            if not self.detector.is_trained:
                # Model yoksa eğit
                logger.info("Training new model...")
                self.detector.train(X_filtered)
                logger.debug("Model training completed")
            
            # Tahmin yap
            logger.debug("Starting anomaly prediction...")
            predictions, anomaly_scores = self.detector.predict(X_filtered)
            anomaly_count = sum(predictions == -1)
            logger.info(f"Anomaly detection completed. Found {anomaly_count} anomalies")
            logger.debug(f"Anomaly scores range: min={min(anomaly_scores):.4f}, max={max(anomaly_scores):.4f}")
            
            # Analiz et
            logger.debug("Analyzing anomalies...")
            analysis = self.detector.analyze_anomalies(df_filtered, X_filtered, predictions, anomaly_scores)
            logger.debug("Anomaly analysis completed")
            
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
            # OpenAI bağlantısı varsa AI destekli açıklama üret
            if self.openai_connector.is_connected():
                logger.info("Generating AI-powered explanation...")
                ai_explanation = self._generate_ai_explanation(analysis)

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

            result = {
                "description": description,
                "data": analysis, # Tüm ham analiz verisini de gönderelim
                "suggestions": suggestions,
                "ai_explanation": ai_explanation # Yapılandırılmış AI çıktısını da ekleyelim
            }
            
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
            
            # Model var mı kontrol et
            if not self.detector.is_trained:
                # Model yoksa eğit
                logger.info("Training new model...")
                self.detector.train(X_filtered)
            
            # Tahmin yap
            predictions, anomaly_scores = self.detector.predict(X_filtered)
            logger.debug(f"Found {sum(predictions == -1)} anomalies in MongoDB logs")
            
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
        """OpenAI kullanarak anomali verisi için zengin açıklama üret"""
        if not self.openai_connector.is_connected():
            logger.warning("OpenAI not connected, returning basic explanation")
            return self._create_fallback_explanation(anomaly_data)
        
        try:
            logger.info("Starting AI explanation generation...")
            summary = anomaly_data.get("summary", {})
            critical_anomalies = anomaly_data.get("critical_anomalies", [])[:5]
            security_alerts = anomaly_data.get("security_alerts", {})
            component_analysis = anomaly_data.get("component_analysis", {})
            temporal_analysis = anomaly_data.get("temporal_analysis", {})
            
            # Güçlendirilmiş system prompt - daha detaylı ve sayısal referanslı
            system_prompt = """Sen bir MongoDB veritabanı uzmanısın. Anomali analiz sonuçlarını inceleyip, 
            kullanıcıya anlaşılır ve aksiyona yönelik açıklamalar üretiyorsun. 
            
            MUTLAKA her açıklamanda spesifik sayılar ve yüzdeler kullan!
            
            Açıklamalarında şu başlıkları kullan ve her birini madde işaretleriyle (•) listele:
            
            1. NE TESPİT EDİLDİ? 
               • Her anomali tipini ayrı maddede açıkla
               • Anomali sayılarını ve yüzdelerini belirt
               
            2. POTANSİYEL ETKİLER
               • Her etkiyi ayrı maddede açıkla
               • Hangi bileşenlerin ne kadar etkilendiğini sayılarla belirt
               
            3. MUHTEMEL NEDENLER
               • Her nedeni ayrı maddede açıkla
               • Hangi saatlerde yoğunlaştığını belirt
               
            4. ÖNERİLEN AKSİYONLAR
               • Her öneriyi ayrı maddede açıkla
               • Hangi anomali için hangi öneri olduğunu ve sayısal hedefleri belirt
               
            Türkçe yanıt ver ve her öneride MUTLAKA ilgili anomali sayısına veya yüzdesine referans ver."""
            
            # Daha detaylı user prompt
            user_prompt = f"""
            MongoDB log anomali analiz sonuçları:
            
            ÖZET:
            - Toplam log: {summary.get('total_logs', 0):,}
            - Anomali sayısı: {summary.get('n_anomalies', 0)}
            - Anomali oranı: %{summary.get('anomaly_rate', 0):.1f}
            - Ortalama anomali skoru: {summary.get('score_range', {}).get('mean', 0):.3f}
            - Minimum skor: {summary.get('score_range', {}).get('min', 0):.3f}
            - Maksimum skor: {summary.get('score_range', {}).get('max', 0):.3f}
            
            KRİTİK ANOMALİLER:
            {self._format_critical_anomalies_detailed(critical_anomalies)}
            
            GÜVENLİK UYARILARI:
            {self._format_security_alerts_detailed(security_alerts)}
            
            COMPONENT ANALİZİ:
            {self._format_component_analysis_detailed(component_analysis)}
            
            ZAMANSAL ANALİZ:
            - En yoğun anomali saatleri: {temporal_analysis.get('peak_hours', [])}
            - Saat bazlı dağılım: {temporal_analysis.get('hourly_distribution', {})}
            
            Lütfen bu verileri analiz edip, kullanıcıya yukarıda belirtilen yapıda, 
            maddeler halinde ve her maddede spesifik sayılarla desteklenmiş bir açıklama hazırla.
            """
            
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]
            
            response = self.openai_connector.llm.invoke(messages)
            ai_explanation = response.content
            
            logger.info(f"AI response received, length: {len(ai_explanation)}")
            parsed_explanation = self._parse_ai_explanation_improved(ai_explanation)
            
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
        """AI metnini yapılandırılmış formata dönüştür - geliştirilmiş versiyon"""
        sections = {
            "ne_tespit_edildi": [],
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
            
            # Yeni bölüm kontrolü
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
                if clean_line and len(clean_line) > 5:  # Çok kısa satırları atla
                    sections[current_section_key].append(clean_line)
        
        # İlk bölümü string olarak birleştir
        if sections["ne_tespit_edildi"]:
            sections["ne_tespit_edildi"] = "\n• ".join(sections["ne_tespit_edildi"])
            sections["ne_tespit_edildi"] = "• " + sections["ne_tespit_edildi"]
        else:
            sections["ne_tespit_edildi"] = ""
        
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