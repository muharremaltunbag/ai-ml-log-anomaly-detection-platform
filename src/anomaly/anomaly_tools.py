#src/anomaly/anomaly_tools.py
"""
MongoDB Anomaly Detection LangChain Tools
Anomali tespiti için LangChain tool tanımları
"""
from typing import Dict, Any, List, Optional
try:
    from langchain.tools import Tool, StructuredTool
except ImportError:
    from langchain_classic.tools import Tool, StructuredTool
from pydantic import BaseModel, Field
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

# MSSQL Modülleri
from .mssql_log_reader import MSSQLOpenSearchReader
from .mssql_feature_engineer import MSSQLFeatureEngineer
from .mssql_anomaly_detector import MSSQLAnomalyDetector

# Elasticsearch Modülleri
from .elasticsearch_log_reader import ElasticsearchOpenSearchReader
from .elasticsearch_feature_engineer import ElasticsearchFeatureEngineer
from .elasticsearch_anomaly_detector import ElasticsearchAnomalyDetector

from ..connectors.openai_connector import OpenAIConnector
from ..connectors.lcwgpt_connector import LCWGPTConnector
try:
    from langchain.schema import HumanMessage, SystemMessage
except ImportError:
    from langchain_core.messages import HumanMessage, SystemMessage


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
        # Başlangıçta boş, analiz anında Singleton üzerinden sunucuya özel alınacak
        self.detector = None 
        logger.debug("Feature engineer initialized. Detector will be fetched on-demand via Singleton.")
        
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
                # False positive filter config'i top-level anomaly_detection'dan al
                self.fp_filter_config = full_config.get('anomaly_detection', {}).get('false_positive_filter', {})
                logger.debug(f"Config loaded successfully for environment: {self.environment}")
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            self.config = {}
            self.fp_filter_config = {}
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
                # Doğrudan response dict'ten say (regex nested array'lerde hata yapıyor)
                critical_count = len(response.get("sonuç", {}).get("critical_anomalies", []))
                all_count = len(response.get("sonuç", {}).get("all_anomalies", []))
                print(f"[DEBUG] JSON RESULT: Serialized JSON contains {critical_count} critical + {all_count} all anomaly objects")
            
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
                                  source_name="unknown", use_incremental=True, server_name=None):
        """
        Tüm veri kaynakları için ortak gelişmiş analiz fonksiyonu
        
        Args:
            df_filtered: Filtrelenmiş DataFrame
            X_filtered: Feature matrix
            predictions: Model tahminleri
            anomaly_scores: Anomali skorları
            source_name: Veri kaynağı adı
            use_incremental: Incremental learning kullan
            server_name: Sunucu adı (model yönetimi için)
        
        Returns:
            Enhanced analysis dictionary
        """
        if server_name:
            logger.info(f"Performing enhanced analysis for {source_name} source, server: {server_name}...")
        else:
            logger.info(f"Performing enhanced analysis for {source_name} source...")
        
        # 1. Model Training/Update (eğer gerekiyorsa)
        if not self.detector.is_trained:
            logger.info("Training new model with incremental learning...")
            
            if use_incremental and hasattr(self.detector, 'train_incremental'):
                # Incremental training
                batch_id = f"{source_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                if server_name:
                    batch_id = f"{server_name}_{source_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                training_stats = self.detector.train_incremental(X_filtered, batch_id=batch_id)
                logger.info(f"Incremental training completed - Ensemble size: {len(self.detector.incremental_models)}")
            else:
                # Fallback to standard training
                self.detector.train(X_filtered, server_name=server_name)
                logger.info(f"Standard training completed{f' for server: {server_name}' if server_name else ''}")
            
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

    def _extract_server_from_filename(self, filename: str) -> 'Optional[str]':
        """
        Upload edilen dosya adından MongoDB server adını çıkar

        Desteklenen LC Waikiki MongoDB hostname pattern'leri:
        - lcwmongodb01n2.log -> lcwmongodb01n2
        - ECAZTRDBMNG019.log -> ecaztrdbmng019
        - PPLMNGDBN2.log -> pplmngdbn2
        - mongod_lcwmongodb01n2.log -> lcwmongodb01n2
        - mongod.log.ECAZTRDBMNG005 -> ecaztrdbmng005

        Args:
            filename: Dosya adı
        Returns:
            Server adı (lowercase) veya None
        """
        import re

        if not filename:
            return None

        # Dosya adını normalize et (lowercase)
        filename_lower = filename.lower()

        # LC Waikiki MongoDB server hostname pattern'leri (gerçek envanter bazlı)
        patterns = [
            # LCW MongoDB cluster: lcwmongodb01n1, lcwmongodb01n2, lcwmongodb01n3
            r'(lcwmongodb\d+n\d+)',

            # ECAZ TR DB MNG: ECAZTRDBMNG004 - ECAZTRDBMNG021
            r'(ecaztrdbmng\d+)',

            # ECAZ GL DB MNG: ECAZGLDBMNG001, ECAZGLDBMNG002, ECAZGLDBMNG003
            r'(ecazgldbmng\d+)',

            # PPL MongoDB: PPLMNGDBN1, PPLMNGDBN2, PPLMNGDBN3
            r'(pplmngdbn\d+)',
            r'(drpplmngdbn\d+)',  # DR node

            # KZN MongoDB: kznmngdbn1, kznmngdbn2, kznmngdbn3
            r'(kznmngdbn\d+)',
            r'(drkznmngdbn\d+)',  # DR node

            # NTFC MongoDB: ntfcmongodb01, ntfcmongodb02, ntfcmongodb04
            r'(ntfcmongodb\d+)',

            # ECOMFIX MongoDB: ECOMFIXMONGODB01, ECOMFIXMONGODB02, ECOMFIXMONGODB03
            r'(ecomfixmongodb\d+)',

            # PPL AZ MongoDB: pplazmongodbn1, pplazmongodbn2, pplazmongodbn3
            r'(pplazmongodbn\d+)',

            # RU MongoDB: rumongo02
            r'(rumongo\d+)',

            # HQ SEC TWRAP: hqsectwrapmdbn1, hqsectwrapmdbn2, hqsectwrapmdbn3
            r'(hqsectwrapmdbn\d+)',
            r'(drhqsectmdbn\d+)',  # DR node

            # WPOS MongoDB: WPOSMNG1, WPOSMNG2, WPOSMNG3
            r'(wposmng\d+)',

            # Logistic MongoDB: LGSTMNGDB01, LGSTMNGDB02, LGSTMNGDB03
            r'(lgstmngdb\d+)',

            # Test/Dev environments
            r'(testmongodb\d+)',
            r'(devmongodb\d+)',
        ]

        for pattern in patterns:
            match = re.search(pattern, filename_lower)
            if match:
                server_name = match.group(1)
                logger.info(f"Extracted server name from filename: {filename} -> {server_name}")
                return server_name

        logger.debug(f"Could not extract server name from filename: {filename}")
        return None

    def _extract_server_from_log_content(self, df: 'pd.DataFrame') -> 'Optional[str]':
        """
        Log içeriğinden (DataFrame) server adını çıkar

        MongoDB log'larında host bilgisi şu alanlarda bulunabilir:
        - attr.host (Process Details mesajında)
        - host alanı (OpenSearch'ten gelen loglarda)

        Args:
            df: Log DataFrame'i
        Returns:
            Server adı (lowercase) veya None
        """
        import re

        if df is None or df.empty:
            return None

        try:
            # 1. 'host' sütunu varsa kontrol et
            if 'host' in df.columns:
                host_values = df['host'].dropna().unique()
                for host in host_values:
                    if host and host != 'unknown':
                        # FQDN'den hostname'i çıkar
                        hostname = str(host).split('.')[0].lower()
                        # Pattern kontrolü yap
                        server_name = self._extract_server_from_filename(hostname)
                        if server_name:
                            logger.info(f"Extracted server from 'host' column: {server_name}")
                            return server_name

            # 2. 'attr' sütununda host bilgisi ara (Process Details mesajı)
            if 'attr' in df.columns:
                for idx, row in df.head(100).iterrows():  # İlk 100 satıra bak
                    attr = row.get('attr')
                    if isinstance(attr, dict) and 'host' in attr:
                        host = attr['host']
                        hostname = str(host).split('.')[0].lower()
                        server_name = self._extract_server_from_filename(hostname)
                        if server_name:
                            logger.info(f"Extracted server from attr.host: {server_name}")
                            return server_name

            # 3. 'msg' sütununda "Process Details" mesajını ara
            if 'msg' in df.columns:
                process_details = df[df['msg'] == 'Process Details']
                if not process_details.empty:
                    first_row = process_details.iloc[0]
                    attr = first_row.get('attr')
                    if isinstance(attr, dict) and 'host' in attr:
                        host = attr['host']
                        hostname = str(host).split('.')[0].lower()
                        server_name = self._extract_server_from_filename(hostname)
                        if server_name:
                            logger.info(f"Extracted server from Process Details: {server_name}")
                            return server_name

            logger.debug("Could not extract server name from log content")
            return None

        except Exception as e:
            logger.error(f"Error extracting server from log content: {e}")
            return None
            
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

            # Host filter güvenli kontrolü
            host_filter = args_dict.get("host_filter")
            if host_filter and isinstance(host_filter, str) and ',' in host_filter:
                # Virgülle ayrılmış string ise listeye çevir
                host_filter = [h.strip() for h in host_filter.split(',') if h.strip()]
                args_dict['host_filter'] = host_filter

            # Sunucu bazlı Singleton instance'ı al
            # host_filter string ise direkt, list ise ilk elemanı referans al
            server_ref = host_filter[0] if isinstance(host_filter, list) and host_filter else host_filter
            self.detector = MongoDBAnomalyDetector.get_instance(server_name=server_ref, config_path=self.config_path)
            logger.info(f"Using shared detector instance for: {server_ref}")

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

                # ✅ YENİ: Dosya adını sakla
                uploaded_filename = Path(file_path).name
                logger.info(f"Using uploaded file: {file_path} (filename: {uploaded_filename})")

                # ✅ YENİ: Dosya adından server name çıkarmaya çalış
                server_for_model = self._extract_server_from_filename(uploaded_filename)

                # Log reader başlat ve logları oku
                self.log_reader = MongoDBLogReader(file_path, 'auto')

                # Upload için zaman filtresini devre dışı bırak - dosyanın tamamı okunmalı
                logger.info("Upload source detected: Disabling time filter to read FULL file content.")
                last_hours = None 
                time_range = "Tüm Dosya İçeriği"

                # Logları oku (last_hours=None ile tüm dosya)
                logger.info(f"Reading ALL logs from uploaded file...")
                df = self.log_reader.read_logs(last_hours=None)

                if df.empty:
                    logger.error("No logs read from uploaded file")
                    return self._format_result(
                        {"error": "Upload dosyasından log okunamadı veya dosya boş"},
                        "anomaly_analysis"
                    )

                logger.info(f"Read {len(df)} logs from uploaded file")

                # ✅ YENİ: Log içeriğinden server name çıkarmayı dene (dosya adından bulunamadıysa)
                if not server_for_model:
                    server_for_model = self._extract_server_from_log_content(df)
                    if server_for_model:
                        logger.info(f"Extracted server name from log content: {server_for_model}")

                # Feature engineering
                logger.info("Creating features for uploaded file...")
                X, df_enriched = self.feature_engineer.create_features(df)

                # Filtreleri uygula
                df_filtered, X_filtered = self.feature_engineer.apply_filters(df_enriched, X)
                logger.info(f"After filtering: {len(df_filtered)} logs, {X_filtered.shape[1]} features")

                # ✅ YENİ: Model yükleme mekanizması - OpenSearch ile aynı
                model_loaded = False
                if not self.detector.is_trained:
                    logger.info(f"Attempting to load existing model{f' for server: {server_for_model}' if server_for_model else ''}...")
                    model_loaded = self.detector.load_model(server_name=server_for_model)
                    if model_loaded:
                        logger.info(f"✅ Existing model loaded successfully{f' for server: {server_for_model}' if server_for_model else ''}")
                    else:
                        logger.info(f"⚠️ No existing model found, will train new model")
                else:
                    model_loaded = True

                # Model kontrolü ve tahmin
                if not self.detector.is_trained:
                    logger.info(f"Training model for uploaded file{f' (server: {server_for_model})' if server_for_model else ''}...")
                    if hasattr(self.detector, 'train_incremental'):
                        batch_id = f"{server_for_model or 'opensearch'}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                        self.detector.train_incremental(X_filtered, batch_id=batch_id)
                        logger.info(f"Initial training completed - Ensemble size: {len(self.detector.incremental_models)}")
                        # ÖNEMLİ: Incremental training sonrası ana modeli de set et
                        if self.detector.incremental_models and not self.detector.model:
                            self.detector.model = self.detector.incremental_models[-1]
                            self.detector.feature_names = list(X_filtered.columns)
                            self.detector.is_trained = True
                            logger.info("✅ Main model set from incremental ensemble")

                    else:
                        self.detector.train(X_filtered, save_model=True)
                        logger.info("Standard training completed")
                else:
                    # Incremental update
                    logger.info("📊 Performing incremental training to update historical buffer...")
                    self.detector.train(X_filtered, save_model=True, incremental=True, server_name=server_for_model)
                    logger.info(f"✅ Model incrementally updated with {len(X_filtered)} new samples")

                # Tahmin yap
                predictions, anomaly_scores = self.detector.predict(X_filtered, df=df_filtered)
                anomaly_count = sum(predictions == -1)
                logger.info(f"Found {anomaly_count} anomalies in uploaded file")

                # Enhanced analiz
                analysis = self._perform_enhanced_analysis(
                    df_filtered, X_filtered, predictions, anomaly_scores,
                    source_name="upload", use_incremental=True, server_name=server_for_model
                )

                # ✅ YENİ: Filtreleme öncesi orijinal anomali sayısını sakla
                unfiltered_anomaly_count = len(analysis.get('critical_anomalies', []))
                unfiltered_analysis = analysis.copy()
                logger.info(f"Unfiltered anomaly count: {unfiltered_anomaly_count}")

                # False positive filtering
                analysis = self._filter_false_positives(analysis, source_name="upload")

                # Sonuçları sakla
                self.last_analysis = {
                    "df": df_filtered,
                    "predictions": predictions,
                    "anomaly_scores": anomaly_scores,
                    "analysis": analysis
                }

                # ✅ YENİ: AI explanation - OpenSearch ile aynı
                ai_explanation = {}
                if self.llm_connector and self.llm_connector.is_connected():
                    logger.info("Generating AI-powered explanation for uploaded file...")
                    limited_analysis = {
                        "summary": {
                            "total_logs": analysis["summary"]["total_logs"],
                            "n_anomalies": analysis["summary"]["n_anomalies"],
                            "anomaly_rate": analysis["summary"]["anomaly_rate"],
                            "score_range": analysis["summary"]["score_range"]
                        },
                        "critical_anomalies": analysis["critical_anomalies"][:20],
                        "security_alerts": analysis.get("security_alerts", {}),
                        "component_analysis": dict(list(analysis.get("component_analysis", {}).items())[:10]),
                        "temporal_analysis": {
                            "peak_hours": analysis.get("temporal_analysis", {}).get("peak_hours", [])[:3]
                        },
                        "feature_importance": dict(list(analysis.get("feature_importance", {}).items())[:10])
                    }
                    ai_explanation = self._generate_ai_explanation(limited_analysis, server_name=server_for_model)

                # Açıklama ve öneriler
                if ai_explanation:
                    server_desc = f" ({server_for_model} sunucusu)" if server_for_model else ""
                    model_desc = " ✅ Mevcut model güncellendi" if model_loaded else " 🆕 Yeni model eğitildi"
                    time_desc = f"son {last_hours} saatteki" if last_hours else "tüm"

                    description = f"Upload edilen dosyadan ({uploaded_filename}) {time_desc} {len(df)} log analiz edildi{server_desc}.{model_desc}\n\n" + \
                                 self._create_enriched_description(analysis, time_range, ai_explanation)[len("🤖 **AI DESTEKLİ ANOMALİ ANALİZİ**\n\n"):]
                    suggestions = ai_explanation.get("onerilen_aksiyonlar", [])
                else:
                    description = f"Upload edilen dosyadan ({uploaded_filename}) {len(df)} log analiz edildi. " + \
                                 self._create_analysis_description(analysis, time_range)
                    suggestions = self._create_suggestions(analysis)

                # ✅ YENİ: OpenSearch ile uyumlu result yapısı
                result = {
                    "description": description,
                    "data": {
                        "source": "UploadedFile",
                        "uploaded_filename": uploaded_filename,
                        "server_info": {
                            "server_name": server_for_model or "unknown",
                            "model_status": "existing" if model_loaded else "newly_trained",
                            "model_path": f"models/isolation_forest_{server_for_model}.pkl" if server_for_model else "models/isolation_forest.pkl",
                            "historical_buffer_size": self.detector.historical_data['metadata']['total_samples'],
                            "last_update": self.detector.historical_data['metadata'].get('last_update', 'N/A')
                        },
                        "time_range_info": {
                            "custom_range": False,
                            "start_time": None,
                            "end_time": None,
                            "last_hours": last_hours,
                            "description": f"son {last_hours} saat" if last_hours else "tüm dosya"
                        },
                        "logs_analyzed": len(df),
                        "filtered_logs": len(df_filtered),
                        "summary": analysis["summary"],
                        "critical_anomalies": self._enhance_critical_anomalies_with_messages(analysis["critical_anomalies"]),
                        "all_anomalies": self._select_diverse_anomalies(analysis.get("all_anomalies", []), limit=100),
                        "unfiltered_anomalies": unfiltered_analysis.get('critical_anomalies', []),
                        "unfiltered_count": unfiltered_anomaly_count,
                        "security_alerts": analysis.get("security_alerts", {}),
                        "temporal_analysis": analysis.get("temporal_analysis", {}),
                        "component_analysis": analysis.get("component_analysis", {}),
                        "feature_importance": analysis.get("feature_importance", {}),
                        "anomaly_score_stats": {
                            "min": analysis["summary"]["score_range"]["min"],
                            "max": analysis["summary"]["score_range"]["max"],
                            "mean": analysis["summary"]["score_range"]["mean"]
                        }
                    },
                    "suggestions": suggestions,
                    "ai_explanation": ai_explanation,
                    "model_info": self._get_model_info_for_storage()
                }

                return self._format_result(result, "anomaly_analysis")
                
            elif source_type == "mongodb_direct":
                # MongoDB'den doğrudan okuma için özel işlem
                conn_string = args_dict.get("connection_string", 
                                          self.config['data_sources']['mongodb_direct']['default_connection'])
                logger.info(f"Using MongoDB direct connection: {conn_string[:20]}...")
                
                # YENİ: Tarih parametrelerini MongoDB Direct'e de ilet
                return self._analyze_mongodb_direct(
                    conn_string, 
                    time_range, 
                    threshold,
                    start_time=args_dict.get('start_time'),
                    end_time=args_dict.get('end_time')
                )
                
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
                    # Paylaşımlı reader'ı al (Gereksiz login'i önler)
                    opensearch_reader = OpenSearchProxyReader.get_instance()

                    # Not: get_instance içinde connect() çağrıldığı için 
                    # burada sadece bağlantı durumunu kontrol etmek yeterlidir
                    if not opensearch_reader:
                        logger.error("Failed to get OpenSearch reader instance")
                        return self._format_result(
                            {"error": "OpenSearch'e bağlanılamadı. Lütfen bağlantı bilgilerini kontrol edin."},
                            "anomaly_analysis"
                        )
                    
                    # YENİ: Tarih parametrelerini kontrol et
                    start_time = args_dict.get('start_time')
                    end_time = args_dict.get('end_time')

                    # Zaman aralığını belirle
                    if start_time and end_time:
                        # Kesin tarih aralığı verilmişse
                        logger.info(f"Using specific date range: {start_time} to {end_time}")
                        last_hours = None  # last_hours kullanma
                    else:
                        # Zaman aralığını saat cinsine çevir
                        if time_range == "last_hour":
                            last_hours = 1
                        elif time_range == "last_day":
                            last_hours = 24
                        elif time_range == "last_week":
                            last_hours = 168
                        elif time_range == "last_month":
                            last_hours = 720
                        else:
                            last_hours = args_dict.get("last_hours", 24)
                        
                        logger.info(f"Reading logs from OpenSearch for last {last_hours} hours...")

                    # Host filter'a FQDN düzeltmesi uygula
                    host_filter = args_dict.get("host_filter", None)
                    is_cluster_analysis = False
                    cluster_hosts = []

                    if host_filter:
                        # Multiple host kontrolü
                        if isinstance(host_filter, list):
                            is_cluster_analysis = True
                            cluster_hosts = []
                            for h in host_filter:
                                fixed_h = self._fix_mongodb_hostname_fqdn(h)
                                cluster_hosts.append(fixed_h)
                                if h != fixed_h:
                                    logger.info(f"Host filter FQDN correction: {h} -> {fixed_h}")
                            host_filter = cluster_hosts
                            logger.info(f"CLUSTER ANALYSIS: {len(cluster_hosts)} hosts will be analyzed")
                        else:
                            original_host = host_filter
                            host_filter = self._fix_mongodb_hostname_fqdn(host_filter)
                            if original_host != host_filter:
                                logger.info(f"Host filter FQDN correction: {original_host} -> {host_filter}")

                    # OpenSearch'ten logları oku
                    if start_time and end_time:
                        # Tarih aralığı ile oku
                        df = opensearch_reader.read_logs(
                            limit=None,
                            host_filter=host_filter,
                            start_time=start_time,
                            end_time=end_time
                        )
                        logger.info(f"Retrieved {len(df)} logs from OpenSearch for date range: {start_time} to {end_time}")
                    else:
                        # last_hours ile oku
                        df = opensearch_reader.read_logs(
                            limit=None,
                            last_hours=last_hours,
                            host_filter=host_filter
                        )
                        logger.info(f"Retrieved {len(df)} logs from OpenSearch for last {last_hours} hours")
                    
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
                    
                    # ✅ YENİ: Model yükleme mekanizması - Production continuity için KRİTİK
                    # Host filter'dan sunucu adını çıkar
                    server_for_model = None
                    if host_filter:
                        if is_cluster_analysis:
                            # Cluster için cluster adını kullan (örn: lcwmongodb01_cluster)
                            # İlk host'tan cluster adını çıkar
                            first_host = cluster_hosts[0] if cluster_hosts else host_filter[0]
                            cluster_name = first_host.split('.')[0].rsplit('n', 1)[0]  # lcwmongodb01n2 -> lcwmongodb01
                            server_for_model = f"{cluster_name}_cluster"
                            logger.info(f"Using cluster model for: {server_for_model}")
                        else:
                            # FQDN'den sunucu adını çıkar (örn: lcwmongodb01n2.lcwaikiki.local -> lcwmongodb01n2)
                            server_for_model = host_filter.split('.')[0] if '.' in host_filter else host_filter
                            logger.info(f"Using server-specific model for: {server_for_model}")
                    
                    # Model yükleme durumunu sakla
                    model_loaded = False
                    if not self.detector.is_trained:
                        logger.info(f"Attempting to load existing model from storage{f' for server: {server_for_model}' if server_for_model else ''}...")
                        # Önce diskten model yüklemeyi dene
                        model_loaded = self.detector.load_model(server_name=server_for_model)
                        if model_loaded:
                            logger.info(f"✅ Existing model loaded successfully from storage{f' for server: {server_for_model}' if server_for_model else ''}")
                            logger.info(f"   📍 Model features: {len(self.detector.feature_names)} features")
                            logger.info(f"   📍 Historical buffer: {self.detector.historical_data['metadata']['total_samples']} samples")
                        else:
                            logger.info(f"⚠️ No existing model found{f' for server: {server_for_model}' if server_for_model else ''}, will train new model")
                    else:
                        model_loaded = True  # Zaten yüklü
                            
                    # Model kontrolü ve tahmin
                    if not self.detector.is_trained:
                        logger.info(f"Training model first before prediction{f' for server: {server_for_model}' if server_for_model else ''}...")
                        if hasattr(self.detector, 'train_incremental'):
                            batch_id = f"{server_for_model or 'opensearch'}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                            self.detector.train_incremental(X_filtered, batch_id=batch_id)
                            logger.info(f"Initial training completed - Ensemble size: {len(self.detector.incremental_models)}")
                            # ÖNEMLİ: Incremental training sonrası ana modeli de set et
                            if self.detector.incremental_models and not self.detector.model:
                                self.detector.model = self.detector.incremental_models[-1]
                                self.detector.feature_names = list(X_filtered.columns)
                                self.detector.is_trained = True
                                logger.info("✅ Main model set from incremental ensemble")
                            # Model'i diske kaydet
                            saved_path = self.detector.save_model(server_name=server_for_model)
                            logger.info(f"✅ Model saved to: {saved_path}")
                        else:
                            self.detector.train(X_filtered, save_model=True)  # Auto-save enabled
                            logger.info("Standard training completed and saved")
                    else:
                        logger.info("✅ Using existing trained model")
                        
                        # ÖNEMLİ: Incremental training yaparak historical buffer'ı güncelle
                        logger.info("📊 Performing incremental training to update historical buffer...")
                        
                        # Training öncesi buffer durumu
                        buffer_before = self.detector.historical_data['metadata']['total_samples']
                        logger.info(f"   Historical buffer before: {buffer_before} samples")
                        
                        # Incremental training yap
                        training_result = self.detector.train(X_filtered, save_model=True, incremental=True, server_name=server_for_model)
                        
                        # Training sonrası buffer durumu
                        buffer_after = self.detector.historical_data['metadata']['total_samples']
                        logger.info(f"   Historical buffer after: {buffer_after} samples (+{buffer_after - buffer_before} new)")
                        logger.info(f"✅ Model incrementally updated with {len(X_filtered)} new samples")

                    # Şimdi tahmin yap
                    predictions, anomaly_scores = self.detector.predict(X_filtered, df=df_filtered)
                    anomaly_count = sum(predictions == -1)
                    logger.info(f"Found {anomaly_count} anomalies in OpenSearch logs")

                    # Enhanced analiz kullan (training zaten yapıldı, tekrar yapmayacak)
                    analysis = self._perform_enhanced_analysis(
                        df_filtered, X_filtered, predictions, anomaly_scores,
                        source_name="opensearch", use_incremental=True, server_name=server_for_model
                    )
                    
                    # YENİ: False positive filtering
                    # YENİ - Filtreleme öncesi orijinal veriyi sakla:
                    # Filtreleme öncesi orijinal anomali sayısını sakla
                    unfiltered_analysis = analysis.copy()
                    unfiltered_anomaly_count = len(analysis.get('critical_anomalies', []))
                    logger.info(f"Unfiltered anomaly count: {unfiltered_anomaly_count}")

                    # YENİ: False positive filtering  
                    analysis = self._filter_false_positives(analysis, source_name="opensearch")

                    # Filtreleme sonrası istatistikleri ekle
                    analysis["unfiltered_stats"] = {
                        "total_anomalies_before_filter": unfiltered_anomaly_count,
                        "unfiltered_anomalies": unfiltered_analysis.get('critical_anomalies', [])
                    }
                    
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
                        
                        ai_explanation = self._generate_ai_explanation(limited_analysis, server_name=server_for_model)

                    
                    # Açıklama ve öneriler
                    if ai_explanation:
                        if is_cluster_analysis:
                            server_desc = f" (CLUSTER: {', '.join([h.split('.')[0] for h in cluster_hosts])})"
                        else:
                            server_desc = f" ({server_for_model} sunucusu)" if server_for_model else ""
                            
                        model_desc = " ✅ Mevcut model güncellendi" if model_loaded else " 🆕 Yeni model eğitildi"
                        # Zaman açıklamasını düzenle
                        if start_time and end_time:
                            time_desc = f"{start_time} - {end_time} arasındaki"
                        else:
                            time_desc = f"son {last_hours} saatteki"

                        description = f"OpenSearch'ten {time_desc} {len(df)} log analiz edildi{server_desc}.{model_desc}\n\n" + \
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

                    
                    # Cluster bilgisini ekle
                    cluster_info = {}
                    if is_cluster_analysis:
                        cluster_info = {
                            "is_cluster": True,
                            "cluster_hosts": cluster_hosts,
                            "cluster_name": server_for_model.replace("_cluster", ""),
                            "host_count": len(cluster_hosts)
                        }
                    
                    result = {
                        "description": description,
                        "data": {
                            "source": "OpenSearch",
                            "server_info": {
                                "server_name": server_for_model or "global",
                                "model_status": "existing" if model_loaded else "newly_trained",
                                "model_path": f"models/isolation_forest_{server_for_model}.pkl" if server_for_model else "models/isolation_forest.pkl",
                                "historical_buffer_size": self.detector.historical_data['metadata']['total_samples'],
                                "last_update": self.detector.historical_data['metadata'].get('last_update', 'N/A'),
                                **cluster_info  # Cluster bilgisini ekle
                            },
                            "time_range_info": {  # YENİ
                                "custom_range": True if (start_time and end_time) else False,
                                "start_time": start_time,
                                "end_time": end_time,
                                "last_hours": last_hours if not (start_time and end_time) else None,
                                "description": time_desc  # "2025-09-15T16:09:00Z - 2025-09-15T16:11:00Z arasındaki" gibi
                            },
                            "logs_analyzed": len(df),
                            "filtered_logs": len(df_filtered),  # YENİ
                            "summary": analysis["summary"],
                            "critical_anomalies": self._enhance_critical_anomalies_with_messages(analysis["critical_anomalies"]),
                            "all_anomalies": self._select_diverse_anomalies(analysis.get("all_anomalies", []), limit=100),
                            "unfiltered_anomalies": unfiltered_analysis.get('critical_anomalies', []),  # TÜM anomaliler
                            "unfiltered_count": unfiltered_anomaly_count,  # Filtrelenmemiş sayı
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
                        "ai_explanation": ai_explanation,
                        "model_info": self._get_model_info_for_storage()  
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
            
            # ✅ YENİ: Model yükleme mekanizması - Production continuity için KRİTİK
            # File source için opsiyonel server_name parametresi
            file_server_name = args_dict.get("server_name", None)
            
            if not self.detector.is_trained:
                logger.info(f"Attempting to load existing model from storage{f' for server: {file_server_name}' if file_server_name else ''}...")
                # Önce diskten model yüklemeyi dene
                model_loaded = self.detector.load_model(server_name=file_server_name)
                if model_loaded:
                    logger.info("✅ Existing model loaded successfully from storage")
                    logger.info(f"   📍 Model features: {len(self.detector.feature_names)} features")
                    logger.info(f"   📍 Historical buffer: {self.detector.historical_data['metadata']['total_samples']} samples")
                else:
                    logger.info("⚠️ No existing model found, will train new model")
            
            # Model kontrolü ve tahmin
            if not self.detector.is_trained:
                logger.info("Training model first before prediction...")
                if hasattr(self.detector, 'train_incremental'):
                    batch_id = f"file_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    self.detector.train_incremental(X_filtered, batch_id=batch_id)
                    logger.info(f"Initial training completed - Ensemble size: {len(self.detector.incremental_models)}")
                    # ÖNEMLİ: Incremental training sonrası ana modeli de set et
                    if self.detector.incremental_models and not self.detector.model:
                        self.detector.model = self.detector.incremental_models[-1]
                        self.detector.feature_names = list(X_filtered.columns)
                        self.detector.is_trained = True
                        logger.info("✅ Main model set from incremental ensemble")
                    # Model'i diske kaydet
                    saved_path = self.detector.save_model(server_name=file_server_name)
                    logger.info(f"✅ Model saved to: {saved_path}")
                else:
                    self.detector.train(X_filtered, save_model=True, server_name=file_server_name)
                    logger.info(f"Standard training completed and saved{f' for server: {file_server_name}' if file_server_name else ''}")

            # Tahmin yap
            logger.debug("Starting anomaly prediction...")
            predictions, anomaly_scores = self.detector.predict(X_filtered, df=df_filtered)
            anomaly_count = sum(predictions == -1)
            logger.info(f"Anomaly detection completed. Found {anomaly_count} anomalies")
            logger.debug(f"Anomaly scores range: min={min(anomaly_scores):.4f}, max={max(anomaly_scores):.4f}")
            
            # Enhanced analiz kullan
            analysis = self._perform_enhanced_analysis(
                df_filtered, X_filtered, predictions, anomaly_scores,
                source_name="file", use_incremental=True, server_name=file_server_name
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
                
                ai_explanation = self._generate_ai_explanation(limited_analysis, server_name=file_server_name)

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
            if "all_anomalies" in analysis:
                enhanced_analysis["all_anomalies"] = self._select_diverse_anomalies(analysis.get("all_anomalies", []), limit=100)

            # Server bilgisini enhanced_analysis'e ekle
            enhanced_analysis["server_info"] = {
                "server_name": file_server_name or "global",
                "model_status": "existing" if self.detector.is_trained else "newly_trained",
                "model_path": f"models/isolation_forest_{file_server_name}.pkl" if file_server_name else "models/isolation_forest.pkl",
                "historical_buffer_size": self.detector.historical_data['metadata']['total_samples'] if self.detector.historical_data['features'] is not None else 0,
                "last_update": self.detector.historical_data['metadata'].get('last_update', 'N/A') if self.detector.historical_data['features'] is not None else 'N/A'
            }
            
            result = {
                "description": description,
                "data": enhanced_analysis, # Enhanced analiz verisini gönder
                "suggestions": suggestions,
                "ai_explanation": ai_explanation,
                "model_info": self._get_model_info_for_storage()
            }
            
            print(f"[DEBUG] MAIN FUNCTION: Final result data critical_anomalies count: {len(result['data'].get('critical_anomalies', []))}")
            
            self.last_analysis = result
            return self._format_result(result, "anomaly_analysis")
            
        except Exception as e:
            logger.error(f"Anomaly analysis error: {e}", exc_info=True)
            return self._format_result({"error": str(e)}, "anomaly_analysis")
    
    def _analyze_mongodb_direct(self, connection_string: str, time_range: str, threshold: float,
                               start_time: str = None, end_time: str = None) -> str:
        """MongoDB'den doğrudan log okuyup analiz et"""
        logger.debug(f"Starting MongoDB direct analysis with time_range={time_range}, threshold={threshold}")
        
        # YENİ: Tarih parametrelerini logla
        if start_time and end_time:
            logger.info(f"Using custom date range: {start_time} to {end_time}")
        
        try:
            logger.debug("Connecting to MongoDB...")
            client = MongoClient(connection_string)
            db = client.get_database()
            
            # System.profile collection'ından slow query logları al
            profile_collection = db.system.profile
            logger.debug("Accessing system.profile collection")
            
            # YENİ: Zaman filtresini ayarla - tarih parametrelerini destekle
            time_filter = {}
            if start_time and end_time:
                # Custom tarih aralığı
                from dateutil import parser
                start_dt = parser.parse(start_time)
                end_dt = parser.parse(end_time)
                time_filter = {"ts": {"$gte": start_dt, "$lte": end_dt}}
                logger.info(f"Custom time filter applied: {start_dt} to {end_dt}")
            elif time_range == "last_hour":
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
            
            # ✅ YENİ: Model yükleme mekanizması - Production continuity için KRİTİK
            # Connection string'den server adını çıkarmaya çalış
            mongodb_server_name = None
            if connection_string:
                # mongodb://host:port/db formatından host'u çıkar
                import re
                host_match = re.search(r'mongodb://([^:/?]+)', connection_string)
                if host_match:
                    mongodb_server_name = host_match.group(1).split('.')[0]  # FQDN'den sadece hostname
                    logger.info(f"Extracted server name from connection: {mongodb_server_name}")
            
            if not self.detector.is_trained:
                logger.info(f"Attempting to load existing model from storage{f' for server: {mongodb_server_name}' if mongodb_server_name else ''}...")
                # Önce diskten model yüklemeyi dene
                model_loaded = self.detector.load_model(server_name=mongodb_server_name)
                if model_loaded:
                    logger.info("✅ Existing model loaded successfully from storage")
                    logger.info(f"   📍 Model features: {len(self.detector.feature_names)} features")
                    logger.info(f"   📍 Historical buffer: {self.detector.historical_data['metadata']['total_samples']} samples")
                else:
                    logger.info("⚠️ No existing model found, will train new model")
            
            # Model kontrolü ve eğitim
            if not self.detector.is_trained:
                logger.info("Training model first...")
                if hasattr(self.detector, 'train_incremental'):
                    batch_id = f"mongodb_direct_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    self.detector.train_incremental(X_filtered, batch_id=batch_id)
                else:
                    self.detector.train(X_filtered, server_name=mongodb_server_name)

            # Tahmin yap
            predictions, anomaly_scores = self.detector.predict(X_filtered, df=df_filtered)
            logger.debug(f"Found {sum(predictions == -1)} anomalies in MongoDB logs")

            # Enhanced analiz
            analysis = self._perform_enhanced_analysis(
                df_filtered, X_filtered, predictions, anomaly_scores,
                source_name="mongodb_direct", use_incremental=True, server_name=mongodb_server_name
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
                    "server_info": {
                        "server_name": mongodb_server_name or "global",
                        "model_status": "existing" if model_loaded else "newly_trained",
                        "model_path": f"models/isolation_forest_{mongodb_server_name}.pkl" if mongodb_server_name else "models/isolation_forest.pkl",
                        "historical_buffer_size": self.detector.historical_data['metadata']['total_samples'],
                        "connection_string": connection_string[:30] + "..." if len(connection_string) > 30 else connection_string
                    },
                    "summary": analysis["summary"],
                    "critical_anomalies": self._enhance_critical_anomalies_with_messages(analysis["critical_anomalies"]),  # Tüm kritik anomaliler - Enhanced
                    "all_anomalies": self._select_diverse_anomalies(analysis.get("all_anomalies", []), limit=100),
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

    def _get_model_info_for_storage(self) -> Dict[str, Any]:
        """
        Detector'dan model metadata bilgilerini topla (Storage için)
        
        Returns:
            Model metadata dictionary
        """
        if not self.detector:
            return None
        
        try:
            return {
                "model_version": getattr(self.detector, 'model_version', None),
                "model_path": f"models/isolation_forest_{self.detector.current_server}.pkl" if self.detector.current_server else "models/isolation_forest.pkl",
                "server_name": self.detector.current_server,
                "is_ensemble_mode": bool(self.detector.incremental_models) and self.detector.incremental_config.get('enabled', True),
                "ensemble_model_count": len(self.detector.incremental_models) if self.detector.incremental_models else 0,
                "historical_buffer_samples": self.detector.historical_data['metadata']['total_samples'] if self.detector.historical_data.get('features') is not None else 0,
                "training_samples": self.detector.training_stats.get('n_samples', 0) if self.detector.training_stats else 0,
                "model_trained_at": self.detector.training_stats.get('timestamp') if self.detector.training_stats else None,
                "feature_count": len(self.detector.feature_names) if self.detector.feature_names else 0,
                "contamination": self.detector.model_config['parameters'].get('contamination') if self.detector.model_config else None
            }
        except Exception as e:
            logger.error(f"Error getting model info for storage: {e}")
            return None

    def _get_mssql_model_info_for_storage(self, mssql_detector, host_filter: str = None) -> Dict[str, Any]:
        """
        MSSQL Detector'dan model metadata bilgilerini topla (Storage için)
        MongoDB'nin _get_model_info_for_storage() ile paralel yapı.

        Args:
            mssql_detector: MSSQLAnomalyDetector instance
            host_filter: MSSQL host adı

        Returns:
            Model metadata dictionary
        """
        if not mssql_detector:
            return None

        try:
            safe_host = host_filter.lower().replace('.', '_').replace('/', '_') if host_filter else None
            return {
                "model_version": getattr(mssql_detector, 'model_version', None),
                "model_path": f"models/mssql_isolation_forest_{safe_host}.pkl" if safe_host else "models/mssql_isolation_forest.pkl",
                "server_name": mssql_detector.current_server or host_filter,
                "database_type": "mssql",
                "is_ensemble_mode": bool(mssql_detector.incremental_models) and mssql_detector.incremental_config.get('enabled', True),
                "ensemble_model_count": len(mssql_detector.incremental_models) if mssql_detector.incremental_models else 0,
                "historical_buffer_samples": mssql_detector.historical_data['metadata']['total_samples'] if mssql_detector.historical_data.get('features') is not None else 0,
                "model_trained_at": mssql_detector.training_stats.get('timestamp') if mssql_detector.training_stats else None,
                "feature_count": len(mssql_detector.feature_names) if mssql_detector.feature_names else 0,
                "contamination": mssql_detector.model_config['parameters'].get('contamination') if mssql_detector.model_config else None
            }
        except Exception as e:
            logger.error(f"Error getting MSSQL model info for storage: {e}")
            return None

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

        # Config'den false positive filter threshold'ları oku (fallback: hardcoded defaults)
        fpc = getattr(self, 'fp_filter_config', {})
        stage2_min_score = fpc.get('severity_min_score_stage2', 30)
        slow_query_threshold = fpc.get('slow_query_severity_threshold', 45)
        collscan_threshold = fpc.get('collscan_severity_threshold', 40)
        high_doc_scan_threshold = fpc.get('high_doc_scan_severity_threshold', 40)
        suspicious_rate = fpc.get('suspicious_component_anomaly_rate', 99.5)
        suspicious_min_count = fpc.get('suspicious_component_min_count', 100)
        max_filtered = fpc.get('max_filtered_anomalies', 2000)

        # Orijinal anomali sayısını logla
        original_count = len(analysis.get('critical_anomalies', []))
        logger.info(f"Original critical anomalies: {original_count}")

        # Component analysis debug logs
        logger.info(f"Input critical_anomalies count: {original_count}")
        if original_count > 0:
            logger.info(f"First anomaly sample: {analysis['critical_anomalies'][0]}")

        # 1. Component-based filtering
        suspicious_components = []
        if 'component_analysis' in analysis:
            logger.debug(f"Component analysis found, checking {len(analysis['component_analysis'])} components")
            for comp, stats in analysis['component_analysis'].items():
                # ÖZEL DURUM: Bazı component'ler her zaman önemlidir
                important_components = ['COMMAND', 'REPL', 'CONTROL', 'NETWORK', 'STORAGE']

                # Eğer önemli component ise filtreleme
                if comp in important_components:
                    logger.debug(f"Component {comp} is important, skipping filter")
                    continue

                # Şüpheli component tespiti (config'den threshold)
                if (stats.get('anomaly_rate', 0) > suspicious_rate and
                    stats.get('total_count', 0) > suspicious_min_count):
                    suspicious_components.append(comp)
                    logger.warning(f"Component {comp} has {stats['anomaly_rate']:.1f}% anomaly rate - marking as suspicious")
                    logger.warning(f"Component {comp} marked as suspicious")
        else:
            logger.debug("No component_analysis in analysis dict")
        
        logger.info(f"Suspicious components identified: {suspicious_components}")
        
        # 2. Known benign signatures — anomaliyi silmez, sadece etiketler
        benign_signatures = fpc.get('known_benign_signatures', [])
        benign_tag_count = 0
        if benign_signatures and 'critical_anomalies' in analysis:
            for anomaly in analysis['critical_anomalies']:
                msg = anomaly.get('message', '').lower()
                comp = anomaly.get('component', '')
                for sig in benign_signatures:
                    sig_pattern = sig.get('pattern', '').lower()
                    sig_comp = sig.get('component', '')
                    # Pattern eşleşmesi (component opsiyonel — boşsa sadece pattern yeter)
                    if sig_pattern and sig_pattern in msg:
                        if not sig_comp or sig_comp == comp:
                            anomaly['is_known_benign'] = True
                            anomaly['benign_reason'] = sig.get('reason', 'Known benign pattern')
                            benign_tag_count += 1
                            break
            if benign_tag_count > 0:
                logger.info(f"Known benign signatures tagged: {benign_tag_count} anomalies")

        # 3. Critical anomalies filtreleme
        if 'critical_anomalies' in analysis:
            filtered_anomalies = []
            filtered_out_count = 0

            for i, anomaly in enumerate(analysis['critical_anomalies']):
                # Skip suspicious components
                if 'component_analysis' in analysis:
                    comp = anomaly.get('component', '')
                    if comp in suspicious_components:
                        filtered_out_count += 1
                        logger.debug(f"Anomaly {i} filtered out - suspicious component: {comp}")
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
                    'restart' in msg,
                    'slow query' in msg and severity_score > slow_query_threshold
                ]
                
                if any(critical_patterns):
                    is_critical = True
                    logger.debug(f"Critical pattern matched for anomaly {i}")
                
                # Yüksek severity score olanlar (config'den threshold)
                elif severity_score > stage2_min_score:
                    is_critical = True
                    logger.debug(f"High severity score: {severity_score} for anomaly {i}")
                
                # CRITICAL veya HIGH severity level
                elif severity_level in ['CRITICAL', 'HIGH','MEDIUM']:
                    is_critical = True
                    logger.debug(f"Severity level: {severity_level} for anomaly {i}")

                # Performance kritik anomaliler (config'den threshold)
                elif any([
                    'collscan' in msg and severity_score > collscan_threshold,
                    'slow' in msg and 'ms' in msg and severity_score > slow_query_threshold,
                    'high_doc_scan' in anomaly.get('anomaly_type', '') and severity_score > high_doc_scan_threshold
                ]):
                    is_critical = True
                    logger.debug(f"Performance critical anomaly {i}")
                
                if is_critical:
                    filtered_anomalies.append(anomaly)
                else:
                    filtered_out_count += 1
            
            logger.info(f"Filter results: {len(filtered_anomalies)} anomalies kept, {filtered_out_count} filtered out")
            
            # Maximum anomali limiti (config'den, fallback: 2000)
            if len(filtered_anomalies) > max_filtered:

                logger.info(f"Limiting from {len(filtered_anomalies)} to {max_filtered} most critical")

                # Severity score'a göre sırala ve ilk max_filtered kadarını al
                filtered_anomalies.sort(key=lambda x: x.get('severity_score', 0), reverse=True)
                filtered_anomalies = filtered_anomalies[:max_filtered]

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
                    'false_positive_rate': false_positive_rate,
                    'known_benign_tagged': benign_tag_count
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
            def get_feat_value(stats):
                if isinstance(stats, (int, float)):
                    return float(stats)
                elif isinstance(stats, dict):
                    return float(stats.get('ratio', stats.get('importance', 0)))
                return 0.0
            
            critical_features = [(feat, stats) for feat, stats in analysis["feature_importance"].items() 
                               if get_feat_value(stats) > 0.5]
            if critical_features:
                desc += f"• Yüksek risk faktörleri: "
                desc += ", ".join([f"{feat} ({get_feat_value(stats):.2f})" for feat, stats in critical_features[:3]])
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

    # =========================================================================
    # MSSQL LOG ANALİZİ
    # =========================================================================

    def analyze_mssql_logs(self, args_input) -> str:
        """
        MSSQL loglarında anomali analizi yap

        MongoDB analyze_mongodb_logs() ile aynı yapı, MSSQL modülleri kullanılır.
        OpenSearch'ten db-mssql-* index'inden logları çeker.

        Args:
            args_input: {
                'host_filter': str,  # MSSQL sunucu adı
                'time_range': str,   # last_hour, last_24h, last_7d
                'start_time': str,   # ISO format (optional)
                'end_time': str,     # ISO format (optional)
                'threshold': float   # Anomaly threshold
            }

        Returns:
            JSON formatted analysis result
        """
        logger.info("=" * 60)
        logger.info("MSSQL LOG ANALİZİ BAŞLADI")
        logger.info("=" * 60)

        try:
            # Argümanları parse et
            if isinstance(args_input, str):
                try:
                    args_dict = json.loads(args_input)
                except:
                    args_dict = {"time_range": "last_hour", "threshold": 0.05}
            else:
                args_dict = args_input

            logger.info(f"MSSQL analysis args: {args_dict}")

            # Parametreleri al
            host_filter = args_dict.get("host_filter")
            time_range = args_dict.get("time_range", "last_hour")
            start_time = args_dict.get("start_time")
            end_time = args_dict.get("end_time")
            threshold = args_dict.get("threshold", 0.05)

            # Time range dönüşümü
            time_range_hours = {
                "last_hour": 1,
                "last_24h": 24,
                "last_day": 24,
                "last_7d": 168,
                "last_week": 168,
                "last_30d": 720,
                "last_month": 720
            }
            last_hours = time_range_hours.get(time_range, 24)

            # =====================================================
            # 1. MSSQL LOG READER - OpenSearch'ten log çekme
            # =====================================================
            logger.info("Initializing MSSQL OpenSearch Reader (singleton)...")
            mssql_reader = MSSQLOpenSearchReader.get_instance(
                config_path="config/mssql_anomaly_config.json"
            )

            if not mssql_reader.is_connected():
                # Singleton zaten connect() çağırır, ama bağlantı
                # kopmuş olabilir — yeniden dene
                if not mssql_reader.connect():
                    logger.error("MSSQL OpenSearch connection failed")
                    return self._format_result(
                        {"error": "MSSQL OpenSearch bağlantısı kurulamadı"},
                        "mssql_anomaly_analysis"
                    )

            logger.info(f"Reading MSSQL logs from OpenSearch (host={host_filter}, hours={last_hours})")

            df = mssql_reader.read_logs(
                limit=50000,
                last_hours=last_hours,
                host_filter=host_filter,
                start_time=start_time,
                end_time=end_time
            )

            if df.empty:
                logger.warning("No MSSQL logs found")
                return self._format_result(
                    {"error": f"Belirtilen kriterlerde MSSQL logu bulunamadı (host={host_filter}, last_hours={last_hours})"},
                    "mssql_anomaly_analysis"
                )

            logger.info(f"Fetched {len(df)} MSSQL logs")

            # =====================================================
            # 2. MSSQL FEATURE ENGINEERING
            # =====================================================
            logger.info("Starting MSSQL feature engineering...")
            mssql_feature_engineer = MSSQLFeatureEngineer(config_path="config/mssql_anomaly_config.json")

            X, df_enriched = mssql_feature_engineer.create_features(df)

            logger.info(f"Feature engineering completed: {X.shape[0]} samples, {X.shape[1]} features")

            # =====================================================
            # 3. MSSQL ANOMALY DETECTOR
            # =====================================================
            logger.info(f"Getting MSSQL detector for server: {host_filter or 'global'}")
            mssql_detector = MSSQLAnomalyDetector.get_instance(
                server_name=host_filter or "global",
                config_path="config/mssql_anomaly_config.json"
            )

            # Model training/update
            if not mssql_detector.is_trained:
                logger.info("Training new MSSQL anomaly model...")
                mssql_detector.train(X, save_model=True, server_name=host_filter)
                logger.info("MSSQL model training completed")
            else:
                logger.info("Using existing MSSQL model, performing incremental update...")
                mssql_detector.train(X, save_model=True, incremental=True, server_name=host_filter)

            # =====================================================
            # 4. PREDICTION
            # =====================================================
            logger.info("Running MSSQL anomaly predictions...")
            predictions, anomaly_scores = mssql_detector.predict(X, df=df_enriched)

            anomaly_count = sum(predictions == -1)
            anomaly_rate = (anomaly_count / len(predictions)) * 100
            logger.info(f"Found {anomaly_count} anomalies ({anomaly_rate:.2f}%)")

            # =====================================================
            # 5. ANALİZ VE SONUÇLAR
            # =====================================================
            logger.info("Analyzing MSSQL anomalies...")
            analysis = mssql_detector.analyze_anomalies(df_enriched, X, predictions, anomaly_scores)

            # MSSQL'e özgü ek analizler
            mssql_specific_analysis = self._analyze_mssql_specific(df_enriched, predictions)
            analysis['mssql_specific'] = mssql_specific_analysis

            # =====================================================
            # 6. AI EXPLANATION (Opsiyonel)
            # =====================================================
            ai_explanation = {}
            if self.llm_connector and self.llm_connector.is_connected():
                logger.info("Generating AI explanation for MSSQL anomalies...")
                limited_analysis = {
                    "summary": analysis.get("summary", {}),
                    "critical_anomalies": analysis.get("critical_anomalies", [])[:15],
                    "mssql_specific": mssql_specific_analysis
                }
                ai_explanation = self._generate_mssql_ai_explanation(limited_analysis, server_name=host_filter)

            # =====================================================
            # 7. SONUÇ OLUŞTURMA
            # =====================================================
            # Özet açıklama
            server_desc = f" ({host_filter})" if host_filter else ""
            time_desc = f"son {last_hours} saat" if not (start_time and end_time) else f"{start_time} - {end_time}"

            # Confidence flag — anomali oranı çok yüksekse uyar
            low_confidence = anomaly_rate > 50
            if low_confidence:
                logger.warning(f"MSSQL anomaly rate very high ({anomaly_rate:.1f}%) — results may have low confidence")

            description = f"MSSQL Log Anomali Analizi{server_desc}\n\n"
            description += f"• Analiz edilen log: {len(df):,}\n"
            description += f"• Zaman aralığı: {time_desc}\n"
            description += f"• Tespit edilen anomali: {anomaly_count:,} ({anomaly_rate:.2f}%)\n"

            if low_confidence:
                description += f"• ⚠️ Güvenilirlik: DÜŞÜK — anomali oranı %{anomaly_rate:.0f} (beklenen <%25). İlk eğitim veya düşük log çeşitliliği nedeniyle olabilir.\n"

            # Login istatistikleri
            if 'is_failed_login' in df_enriched.columns:
                failed_logins = df_enriched['is_failed_login'].sum()
                total_logins = len(df_enriched)
                description += f"• Başarısız login: {int(failed_logins):,} ({failed_logins/total_logins*100:.1f}%)\n"

            # MSSQL özel bulgular
            if mssql_specific_analysis.get('security_concerns'):
                description += f"\n⚠️ Güvenlik Uyarıları:\n"
                for concern in mssql_specific_analysis['security_concerns'][:3]:
                    description += f"  - {concern}\n"

            # Critical anomalies'i zenginleştir
            critical_anomalies = analysis.get("critical_anomalies", [])
            for anomaly in critical_anomalies:
                # MSSQL'e özgü alanları ekle
                idx = anomaly.get('index', 0)
                if idx < len(df_enriched):
                    row = df_enriched.iloc[idx]
                    anomaly['username'] = row.get('username', 'unknown')
                    anomaly['client_ip'] = row.get('client_ip', 'unknown')
                    anomaly['logintype'] = row.get('logintype', 'unknown')
                    anomaly['raw_message'] = row.get('raw_message', '')[:500]

            # Tüm anomalileri de zenginleştir (UI'da kritik yoksa bunları göstermek için)
            all_anomalies = analysis.get("all_anomalies", [])
            for anomaly in all_anomalies:
                idx = anomaly.get('index', 0)
                if idx < len(df_enriched):
                    row = df_enriched.iloc[idx]
                    anomaly['username'] = row.get('username', 'unknown')
                    anomaly['client_ip'] = row.get('client_ip', 'unknown')
                    anomaly['logintype'] = row.get('logintype', 'unknown')
                    anomaly['raw_message'] = row.get('raw_message', '')[:500]
                    # MSSQL mesaj düzeltmesi (raw_message varsa kullan)
                    raw_msg = row.get('raw_message', '')
                    if raw_msg and isinstance(raw_msg, str) and len(raw_msg) > 0:
                        anomaly['message'] = raw_msg[:1000]
                    anomaly['component'] = row.get('logtype', anomaly.get('component'))
                    anomaly['severity'] = row.get('log_level', row.get('logtype', anomaly.get('severity')))

            # Öneriler
            suggestions = self._create_mssql_suggestions(analysis, mssql_specific_analysis)

            # MSSQL model metadata — storage'a kaydedilecek zengin bilgi
            mssql_model_info = self._get_mssql_model_info_for_storage(mssql_detector, host_filter)

            result = {
                "description": description,
                "data": {
                    "source": "MSSQL_OpenSearch",
                    "index_pattern": "db-mssql-*",
                    "host_filter": host_filter,
                    "time_range_info": {
                        "last_hours": last_hours,
                        "start_time": start_time,
                        "end_time": end_time,
                        "description": time_desc
                    },
                    "logs_analyzed": len(df),
                    "summary": analysis.get("summary", {}),
                    "total_critical_count": len(critical_anomalies),
                    "critical_anomalies": self._select_diverse_anomalies(critical_anomalies, limit=75, is_mssql=True),
                    "all_anomalies": self._select_diverse_anomalies(analysis.get("all_anomalies", []), limit=100, is_mssql=True),
                    "mssql_specific": mssql_specific_analysis,
                    "temporal_analysis": analysis.get("temporal_analysis", {}),
                    "feature_importance": analysis.get("feature_importance", {}),
                    "model_info": {
                        "is_trained": mssql_detector.is_trained,
                        "model_type": "IsolationForest",
                        "rules_count": len(mssql_detector.critical_rules),
                        **(mssql_model_info or {})
                    },
                    "server_info": {
                        "server_name": host_filter or "global",
                        "model_status": "existing" if mssql_detector.is_trained else "newly_trained",
                        "model_path": f"models/mssql_isolation_forest_{host_filter.lower()}.pkl" if host_filter else "models/mssql_isolation_forest.pkl",
                        "historical_buffer_size": mssql_detector.historical_data['metadata']['total_samples'] if mssql_detector.historical_data.get('features') is not None else 0,
                        "last_update": mssql_detector.historical_data['metadata'].get('last_update', 'N/A')
                    }
                },
                "suggestions": suggestions,
                "ai_explanation": ai_explanation,
                "model_info": mssql_model_info
            }

            logger.info("MSSQL analysis completed successfully")
            return self._format_result(result, "mssql_anomaly_analysis")

        except Exception as e:
            logger.error(f"MSSQL analysis error: {e}", exc_info=True)
            return self._format_result(
                {"error": f"MSSQL analiz hatası: {str(e)}"},
                "mssql_anomaly_analysis"
            )

    # =========================================================================
    # ELASTICSEARCH LOG ANALİZİ
    # =========================================================================

    def analyze_elasticsearch_logs(self, args_input) -> str:
        """
        Elasticsearch loglarında anomali analizi yap.

        MSSQL analyze_mssql_logs() ile aynı yapı, Elasticsearch modülleri kullanılır.
        OpenSearch'ten db-elasticsearch-* index'inden logları çeker.

        Args:
            args_input: dict veya Pydantic model
                'host_filter': str,  # Elasticsearch node adı (ör. ECAZTRDBESRW003)
                'last_hours': int,   # Son kaç saat
                'time_range': str,   # last_hour, last_day, last_week
        """
        logger.info("ELASTICSEARCH LOG ANALİZİ BAŞLADI")

        try:
            # Args parse
            if isinstance(args_input, dict):
                args_dict = args_input
            elif isinstance(args_input, str):
                try:
                    args_dict = json.loads(args_input)
                except json.JSONDecodeError:
                    args_dict = {"time_range": "last_hour"}
            else:
                args_dict = vars(args_input) if hasattr(args_input, '__dict__') else {"time_range": "last_hour"}

            host_filter = args_dict.get('host_filter')
            time_range = args_dict.get('time_range', 'last_hour')

            # Time range → hours
            time_map = {
                "last_hour": 1, "last_4hours": 4, "last_day": 24,
                "last_week": 168, "last_month": 720
            }
            last_hours = args_dict.get('last_hours') or time_map.get(time_range, 24)

            logger.info(f"ES analysis args: host={host_filter}, hours={last_hours}")

            server_desc = f" — {host_filter}" if host_filter else " — Tüm ES node'lar"

            # 1. ELASTICSEARCH LOG READER
            logger.info("Initializing Elasticsearch OpenSearch Reader (singleton)...")
            es_reader = ElasticsearchOpenSearchReader.get_instance(
                config_path="config/elasticsearch_anomaly_config.json"
            )

            if not es_reader.is_connected():
                logger.info("Elasticsearch reader not connected, connecting...")
                if not es_reader.connect():
                    logger.error("Elasticsearch OpenSearch connection failed")
                    return self._format_result(
                        {"error": "Elasticsearch OpenSearch bağlantısı kurulamadı"},
                        "es_anomaly_analysis"
                    )

            logger.info(f"Reading ES logs from OpenSearch (host={host_filter}, hours={last_hours})")
            df = es_reader.read_logs(
                limit=50000,
                last_hours=last_hours,
                host_filter=host_filter
            )

            if df.empty:
                logger.warning("No Elasticsearch logs found")
                return self._format_result(
                    {"error": f"Belirtilen kriterlerde Elasticsearch logu bulunamadı (host={host_filter}, last_hours={last_hours})"},
                    "es_anomaly_analysis"
                )

            logger.info(f"Fetched {len(df)} Elasticsearch logs")

            # 2. FEATURE ENGINEERING
            logger.info("Starting Elasticsearch feature engineering...")
            es_feature_engineer = ElasticsearchFeatureEngineer(
                config_path="config/elasticsearch_anomaly_config.json"
            )
            X, df_enriched = es_feature_engineer.create_features(df)

            # Filter
            df_enriched, X = es_feature_engineer.apply_filters(df_enriched, X)
            logger.info(f"After filtering: {len(df_enriched)} logs, {X.shape[1]} features")

            # 3. ANOMALY DETECTOR
            logger.info(f"Getting ES detector for: {host_filter or 'global'}")
            es_detector = ElasticsearchAnomalyDetector.get_instance(
                server_name=host_filter or "global",
                config_path="config/elasticsearch_anomaly_config.json"
            )

            # Train or incremental update
            if not es_detector.is_trained:
                logger.info("Training new Elasticsearch anomaly model...")
                train_result = es_detector.train(X, save_model=True, server_name=host_filter)
                if isinstance(train_result, dict) and train_result.get('status') == 'skipped':
                    logger.warning(f"Training skipped: {train_result.get('reason')}")
                    return self._format_result(
                        {"error": f"Yetersiz veri: {len(X)} log (minimum {es_detector.min_training_samples} gerekli). Daha geniş zaman aralığı deneyin."},
                        "es_anomaly_analysis"
                    )
                logger.info("Elasticsearch model training completed")
            else:
                logger.info("Using existing ES model, performing incremental update...")
                es_detector.train(X, save_model=True, incremental=True, server_name=host_filter)

            # 4. PREDICTION
            logger.info("Running Elasticsearch anomaly predictions...")
            predictions, anomaly_scores = es_detector.predict(X, df=df_enriched)

            anomaly_count = int((predictions == -1).sum())
            anomaly_rate = (anomaly_count / len(predictions)) * 100 if len(predictions) > 0 else 0
            logger.info(f"ES anomalies found: {anomaly_count}/{len(predictions)} ({anomaly_rate:.1f}%)")

            # 5. ANALYSIS
            logger.info("Analyzing Elasticsearch anomalies...")
            analysis = es_detector.analyze_anomalies(df_enriched, X, predictions, anomaly_scores)

            # ES-specific analysis
            es_specific = self._analyze_es_specific(df_enriched, X, predictions)
            analysis['es_specific'] = es_specific

            # 6. AI EXPLANATION (optional)
            ai_explanation = None
            if self.llm_connector and self.llm_connector.is_connected() and analysis.get('critical_anomalies'):
                try:
                    logger.info("Generating AI explanation for ES anomalies...")
                    limited_analysis = {
                        "summary": analysis.get("summary", {}),
                        "critical_anomalies": analysis.get("critical_anomalies", [])[:10],
                        "es_specific": es_specific
                    }
                    ai_explanation = self._generate_es_ai_explanation(
                        limited_analysis, server_name=host_filter
                    )
                except Exception as e:
                    logger.warning(f"AI explanation failed: {e}")

            # 7. RESULT FORMATTING
            critical_anomalies = analysis.get("critical_anomalies", [])

            description = f"Elasticsearch Log Anomali Analizi{server_desc}\n\n"
            description += f"📊 Toplam Log: {len(df_enriched):,}\n"
            description += f"🔍 Anomali: {anomaly_count:,} ({anomaly_rate:.1f}%)\n"
            description += f"⚠️ Kritik: {len(critical_anomalies)}\n"

            # ES specific findings
            if es_specific.get('health_concerns'):
                description += "\n🏥 Sağlık Sorunları:\n"
                for concern in es_specific['health_concerns'][:5]:
                    description += f"  • {concern}\n"

            # Format critical anomalies for output — preserve all fields from detector
            formatted_anomalies = []
            for anomaly in critical_anomalies[:75]:
                formatted = anomaly.copy()
                # Truncate message for transport size
                if 'message' in formatted and formatted['message']:
                    formatted['message'] = str(formatted['message'])[:500]
                formatted_anomalies.append(formatted)

            suggestions = self._create_es_suggestions(analysis, es_specific)

            result = {
                "description": description,
                "data": {
                    "source": "Elasticsearch_OpenSearch",
                    "index_pattern": "db-elasticsearch-*",
                    "host_filter": host_filter,
                    "time_range": f"last_{last_hours}h",
                    "total_logs": len(df_enriched),
                    "anomaly_count": anomaly_count,
                    "anomaly_rate": round(anomaly_rate, 2),
                    "summary": analysis.get("summary", {}),
                    "critical_anomalies": formatted_anomalies,
                    "all_anomalies": self._select_diverse_anomalies(
                        analysis.get("all_anomalies", []), limit=100
                    ),
                    "es_specific": es_specific,
                    "security_alerts": analysis.get("security_alerts", {}),
                    "model_info": {
                        "is_trained": es_detector.is_trained,
                        "rules_count": len(es_detector.critical_rules),
                        "min_training_samples": es_detector.min_training_samples,
                    },
                    "training_info": {
                        "model_status": "existing" if es_detector.is_trained else "newly_trained",
                        "model_path": f"models/es_isolation_forest_{host_filter.upper()}.pkl" if host_filter else "models/es_isolation_forest.pkl",
                    }
                },
                "ai_explanation": ai_explanation,
                "suggestions": suggestions,
            }

            logger.info("Elasticsearch analysis completed successfully")
            return self._format_result(result, "es_anomaly_analysis")

        except Exception as e:
            logger.error(f"Elasticsearch analysis error: {e}", exc_info=True)
            return self._format_result(
                {"error": f"Elasticsearch analiz hatası: {str(e)}"},
                "es_anomaly_analysis"
            )

    def _analyze_es_specific(self, df: pd.DataFrame, X: pd.DataFrame,
                             predictions: np.ndarray) -> Dict[str, Any]:
        """
        Elasticsearch'e özgü analizler.

        Args:
            df: Enriched ES DataFrame
            X: Feature matrix
            predictions: Anomaly predictions

        Returns:
            ES specific analysis dict
        """
        try:
            anomaly_mask = predictions == -1
            es_analysis = {
                'health_concerns': [],
                'node_role_distribution': {},
                'log_level_distribution': {},
                'logger_distribution': {},
                'critical_patterns': {},
            }

            # Node role distribution
            if 'host_role' in df.columns:
                es_analysis['node_role_distribution'] = (
                    df['host_role'].value_counts().to_dict()
                )

            # Log level distribution
            if 'log_level' in df.columns:
                es_analysis['log_level_distribution'] = (
                    df['log_level'].value_counts().to_dict()
                )

            # Logger distribution (top 10)
            if 'logger_name' in df.columns:
                es_analysis['logger_distribution'] = (
                    df['logger_name'].value_counts().head(10).to_dict()
                )

            # Critical pattern counts
            pattern_cols = [
                'is_oom_error', 'is_circuit_breaker', 'is_high_disk_watermark',
                'is_shard_failure', 'is_node_event', 'is_master_election',
                'is_gc_overhead', 'is_connection_error', 'is_slow_log'
            ]
            for col in pattern_cols:
                if col in X.columns:
                    anomaly_count = int(((X[col] == 1) & anomaly_mask).sum()) if anomaly_mask.any() else 0
                    total_count = int((X[col] == 1).sum())
                    if total_count > 0:
                        es_analysis['critical_patterns'][col] = {
                            'total': total_count,
                            'anomalous': anomaly_count
                        }

            # Health concerns (human-readable)
            if 'is_oom_error' in X.columns and X['is_oom_error'].sum() > 0:
                es_analysis['health_concerns'].append(
                    f"OOM: {int(X['is_oom_error'].sum())} OutOfMemoryError tespit edildi"
                )
            if 'is_circuit_breaker' in X.columns and X['is_circuit_breaker'].sum() > 0:
                es_analysis['health_concerns'].append(
                    f"Circuit Breaker: {int(X['is_circuit_breaker'].sum())} kez tetiklendi"
                )
            if 'is_high_disk_watermark' in X.columns and X['is_high_disk_watermark'].sum() > 0:
                es_analysis['health_concerns'].append(
                    f"Disk: {int(X['is_high_disk_watermark'].sum())} disk watermark uyarısı"
                )
            if 'is_master_election' in X.columns and X['is_master_election'].sum() > 0:
                es_analysis['health_concerns'].append(
                    f"Cluster: {int(X['is_master_election'].sum())} master election olayı"
                )
            if 'is_node_event' in X.columns and X['is_node_event'].sum() > 0:
                es_analysis['health_concerns'].append(
                    f"Node: {int(X['is_node_event'].sum())} node join/leave olayı"
                )
            if 'is_shard_failure' in X.columns and X['is_shard_failure'].sum() > 0:
                es_analysis['health_concerns'].append(
                    f"Shard: {int(X['is_shard_failure'].sum())} shard hatası"
                )
            if 'is_gc_overhead' in X.columns and X['is_gc_overhead'].sum() > 0:
                es_analysis['health_concerns'].append(
                    f"GC: {int(X['is_gc_overhead'].sum())} garbage collection olayı"
                )

            return es_analysis

        except Exception as e:
            logger.error(f"ES specific analysis error: {e}")
            return {'health_concerns': [], 'error': str(e)}

    def _generate_es_ai_explanation(self, analysis: Dict[str, Any],
                                    server_name: str = None) -> Dict[str, Any]:
        """
        Elasticsearch anomalileri için AI açıklaması üret.
        """
        try:
            if not self.llm_connector:
                return None

            system_prompt = """Sen bir Elasticsearch cluster yönetimi ve performans uzmanısın.
Sana verilen Elasticsearch log anomali analizini değerlendir.
Özellikle şunlara odaklan:
1. JVM heap basıncı (OOM, Circuit Breaker)
2. Disk doluluk uyarıları (watermark, flood stage)
3. Cluster stabilitesi (master election, node event)
4. Shard sağlığı (unassigned, relocation)
5. GC performansı

Türkçe yanıt ver. Kısa ve öz tut."""

            es_specific = analysis.get("es_specific", {})
            user_prompt = f"""Elasticsearch Anomali Analiz Sonuçları:

Özet: {json.dumps(analysis.get('summary', {}), indent=2, ensure_ascii=False)}

Sağlık Sorunları:
{json.dumps(es_specific.get('health_concerns', []), indent=2, ensure_ascii=False)}

Kritik Pattern'lar:
{json.dumps(es_specific.get('critical_patterns', {}), indent=2, ensure_ascii=False)}

En Kritik 5 Anomali:
"""
            for a in analysis.get("critical_anomalies", [])[:5]:
                user_prompt += f"\n- [{a.get('severity_level')}] Score:{a.get('severity_score')} | {a.get('message', '')[:200]}"

            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]

            response = self.llm_connector.invoke(messages)
            explanation_text = response.content if hasattr(response, 'content') else str(response)

            return {
                "özet": explanation_text[:2000],
                "server": server_name,
                "generated_at": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"ES AI explanation error: {e}")
            # Fallback: LLM başarısız olsa bile temel özet döndür
            summary = analysis.get('summary', {})
            return {
                "özet": (
                    f"Elasticsearch anomali analizi tamamlandı. "
                    f"Toplam {summary.get('n_anomalies', 0)} anomali tespit edildi "
                    f"(oran: %{summary.get('anomaly_rate', 0):.1f}). "
                    f"AI açıklama üretilemedi: {str(e)[:100]}"
                ),
                "server": server_name,
                "generated_at": datetime.now().isoformat(),
                "is_fallback": True
            }

    def _create_es_suggestions(self, analysis: Dict,
                               es_specific: Dict) -> List[str]:
        """Elasticsearch analizi için öneriler oluştur."""
        suggestions = []

        anomaly_rate = analysis.get('summary', {}).get('anomaly_rate', 0)
        if isinstance(anomaly_rate, str):
            try:
                anomaly_rate = float(anomaly_rate.replace('%', ''))
            except ValueError:
                anomaly_rate = 0

        if anomaly_rate > 20:
            suggestions.append("Yüksek anomali oranı! Elasticsearch cluster sağlığını kontrol edin.")

        health = es_specific.get('health_concerns', [])
        for concern in health:
            if 'OOM' in concern:
                suggestions.append("JVM heap boyutunu artırın veya circuit breaker limitlerini ayarlayın.")
            if 'Disk' in concern:
                suggestions.append("Disk alanı temizliği yapın veya ILM politikalarını gözden geçirin.")
            if 'master election' in concern.lower():
                suggestions.append("Master node stabilitesini kontrol edin. Dedicated master node kullanın.")
            if 'GC' in concern:
                suggestions.append("GC ayarlarını optimize edin. G1GC kullanmayı düşünün.")
            if 'Shard' in concern:
                suggestions.append("Unassigned shard'ları reroute edin veya shard allocation ayarlarını kontrol edin.")

        if not suggestions:
            suggestions.append("Elasticsearch cluster normal görünüyor.")

        return suggestions

    def _analyze_mssql_specific(self, df: pd.DataFrame, predictions: np.ndarray) -> Dict[str, Any]:
        """
        MSSQL'e özgü analizler

        Args:
            df: Enriched MSSQL DataFrame
            predictions: Anomaly predictions

        Returns:
            MSSQL specific analysis dict
        """
        result = {
            'login_analysis': {},
            'user_analysis': {},
            'client_analysis': {},
            'security_concerns': []
        }

        try:
            # Login analizi
            if 'is_failed_login' in df.columns:
                failed_count = int(df['is_failed_login'].sum())
                success_count = int(df.get('is_successful_login', pd.Series([0])).sum())
                total = len(df)

                result['login_analysis'] = {
                    'total_logins': total,
                    'failed_logins': failed_count,
                    'successful_logins': success_count,
                    'failed_ratio': failed_count / total if total > 0 else 0
                }

                # Yüksek failed login oranı uyarısı
                if failed_count / total > 0.2:
                    result['security_concerns'].append(
                        f"Yüksek başarısız login oranı: {failed_count/total*100:.1f}%"
                    )

            # Kullanıcı analizi
            username_col = 'username' if 'username' in df.columns else 'USERNAME'
            if username_col in df.columns:
                user_stats = df.groupby(username_col).agg({
                    'is_failed_login': 'sum' if 'is_failed_login' in df.columns else 'count'
                }).sort_values('is_failed_login', ascending=False)

                top_failed_users = user_stats.head(5).to_dict()['is_failed_login']
                result['user_analysis'] = {
                    'unique_users': int(df[username_col].nunique()),
                    'top_failed_users': {str(k): int(v) for k, v in top_failed_users.items()}
                }

                # Çok fazla failed login olan kullanıcı uyarısı
                for user, count in top_failed_users.items():
                    if count > 100:
                        result['security_concerns'].append(
                            f"Kullanıcı '{user}' için {count} başarısız login"
                        )

            # Client IP analizi
            if 'client_ip' in df.columns:
                ip_stats = df.groupby('client_ip').size().sort_values(ascending=False)
                result['client_analysis'] = {
                    'unique_ips': int(df['client_ip'].nunique()),
                    'top_ips': {str(k): int(v) for k, v in ip_stats.head(10).to_dict().items()},
                    'local_connections': int(df.get('is_local_client', pd.Series([0])).sum())
                }

            # Gece login'leri kontrolü
            if 'is_night_login' in df.columns:
                night_logins = int(df['is_night_login'].sum())
                if night_logins > 0 and 'is_service_account' in df.columns:
                    non_service_night = int(((df['is_night_login'] == 1) & (df['is_service_account'] == 0)).sum())
                    if non_service_night > 10:
                        result['security_concerns'].append(
                            f"{non_service_night} gece saati login'i (servis hesabı dışı)"
                        )

            # Availability Group hataları
            if 'is_availability_group_error' in df.columns:
                ag_errors = int(df['is_availability_group_error'].sum())
                if ag_errors > 0:
                    result['security_concerns'].append(
                        f"{ag_errors} Availability Group erişim hatası"
                    )

        except Exception as e:
            logger.error(f"MSSQL specific analysis error: {e}")

        return result

    def _generate_mssql_ai_explanation(self, analysis: Dict[str, Any], server_name: str = None) -> Dict[str, Any]:
        """
        MSSQL anomalileri için AI açıklaması üret

        Args:
            analysis: Analysis data
            server_name: MSSQL server name

        Returns:
            AI explanation dict
        """
        if not self.llm_connector or not self.llm_connector.is_connected():
            return {}

        try:
            # MSSQL'e özgü prompt
            system_prompt = """Sen bir MSSQL veritabanı güvenlik ve performans uzmanısın.
Sana verilen MSSQL login logları anomali analizini değerlendir.
Özellikle şunlara dikkat et:
- Brute force saldırı belirtileri
- Olağandışı saatlerde login'ler
- Başarısız login pattern'leri
- Servis hesabı anormallikleri
- Availability Group sorunları

Yanıtını Türkçe ver ve şu formatta JSON döndür:
{
  "ozet": "Kısa analiz özeti",
  "kritik_bulgular": ["bulgu1", "bulgu2"],
  "guvenlik_degerlendirmesi": "Düşük/Orta/Yüksek risk",
  "onerilen_aksiyonlar": ["aksiyon1", "aksiyon2"]
}"""

            # Analysis verilerini hazırla
            summary = analysis.get("summary", {})
            mssql_specific = analysis.get("mssql_specific", {})
            critical_anomalies = analysis.get("critical_anomalies", [])[:10]

            user_prompt = f"""MSSQL Anomali Analiz Sonuçları:

Sunucu: {server_name or 'Tüm sunucular'}
Toplam Log: {summary.get('total_logs', 'N/A')}
Anomali Sayısı: {summary.get('n_anomalies', 'N/A')}
Anomali Oranı: {summary.get('anomaly_rate', 0):.2f}%

Login İstatistikleri:
{json.dumps(mssql_specific.get('login_analysis', {}), indent=2, ensure_ascii=False)}

Güvenlik Endişeleri:
{json.dumps(mssql_specific.get('security_concerns', []), indent=2, ensure_ascii=False)}

İlk 10 Kritik Anomali:
{json.dumps(critical_anomalies, indent=2, ensure_ascii=False, default=str)[:3000]}

Bu verileri analiz et ve JSON formatında yanıt ver."""

            from langchain.schema import HumanMessage, SystemMessage
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]

            response = self.llm_connector.invoke(messages)

            if response and hasattr(response, 'content'):
                # JSON parse
                content = response.content
                # JSON bloğunu bul
                import re
                json_match = re.search(r'\{[\s\S]*\}', content)
                if json_match:
                    return json.loads(json_match.group())

            return {}

        except Exception as e:
            logger.error(f"MSSQL AI explanation error: {e}")
            return {}

    def _create_mssql_suggestions(self, analysis: Dict, mssql_specific: Dict) -> List[str]:
        """
        MSSQL analizi için öneriler oluştur

        Args:
            analysis: General analysis
            mssql_specific: MSSQL specific analysis

        Returns:
            List of suggestions
        """
        suggestions = []

        # Anomali oranına göre
        anomaly_rate = analysis.get("summary", {}).get("anomaly_rate", 0)
        if anomaly_rate > 50:
            suggestions.append("⚠️ DÜŞÜK GÜVENİLİRLİK: Anomali oranı çok yüksek (%{:.0f}). İlk eğitim veya düşük log çeşitliliği nedeniyle sonuçlar güvenilir olmayabilir. Daha geniş zaman aralığı veya farklı host ile tekrar deneyin.".format(anomaly_rate))
        elif anomaly_rate > 5:
            suggestions.append("🔴 ACİL: Yüksek anomali oranı! MSSQL güvenlik ekibine bildirin.")
        elif anomaly_rate > 2:
            suggestions.append("🟡 ORTA: Normal üstü anomali. Login pattern'lerini inceleyin.")
        else:
            suggestions.append("🟢 NORMAL: Anomali seviyesi kabul edilebilir.")

        # Failed login oranı
        login_analysis = mssql_specific.get('login_analysis', {})
        if login_analysis.get('failed_ratio', 0) > 0.2:
            suggestions.append("🚨 GÜVENLİK: Yüksek başarısız login oranı! Brute force kontrolü yapın.")
            suggestions.append("🔐 YAPILACAK: Account lockout policy'yi gözden geçirin.")

        # Güvenlik endişeleri
        security_concerns = mssql_specific.get('security_concerns', [])
        if security_concerns:
            suggestions.append("⚠️ UYARI: Güvenlik endişeleri tespit edildi:")
            for concern in security_concerns[:3]:
                suggestions.append(f"  → {concern}")

        # Availability Group hataları
        if any('Availability Group' in str(c) for c in security_concerns):
            suggestions.append("🔧 YAPILACAK: Always On Availability Group durumunu kontrol edin.")
            suggestions.append("📊 YAPILACAK: Secondary replica'ların erişilebilirliğini doğrulayın.")

        return suggestions

    def _generate_ai_explanation(self, anomaly_data: Dict[str, Any], server_name: str = None) -> Dict[str, Any]:
        """LCWGPT kullanarak anomali verisi için zengin açıklama üret"""
        logger.info(f"=== AI EXPLANATION DEBUG ===")
        logger.info(f"LLM connected: {self.llm_connector.is_connected() if self.llm_connector else False}")
        if server_name:
            logger.info(f"Generating AI explanation for server: {server_name}")
        
        if not self.llm_connector or not self.llm_connector.is_connected():
            logger.warning("LLM not connected, returning basic explanation")
            return self._create_fallback_explanation(anomaly_data)
        
        try:
            logger.info("Starting AI explanation generation...")
            
            # anomaly_tools.py içinde numpy float kontrolü ekle
            def convert_numpy_values(data):
                if isinstance(data, dict):
                    return {k: convert_numpy_values(v) for k, v in data.items()}
                elif isinstance(data, list):
                    return [convert_numpy_values(item) for item in data]
                elif isinstance(data, (np.float64, np.float32)):
                    return float(data)
                elif isinstance(data, (np.int64, np.int32)):
                    return int(data)
                return data
            
            anomaly_data = convert_numpy_values(anomaly_data)
            
            # Summary'den büyük verileri temizle
            summary = anomaly_data.get("summary", {}).copy()
            # Sadece gerekli özet bilgileri kalsın
            summary_keys_to_keep = ['total_logs', 'n_anomalies', 'anomaly_rate', 'score_range']
            summary = {k: v for k, v in summary.items() if k in summary_keys_to_keep}
            critical_anomalies = anomaly_data.get("critical_anomalies", [])[:10]
            security_alerts = anomaly_data.get("security_alerts", {})
            
            # Numpy float tiplerini handle et
            def clean_floats(obj):
                import numpy as np  
                if isinstance(obj, (np.float32, np.float64, float)):
                    if np.isnan(obj) or np.isinf(obj):
                        return 0.0
                    return float(obj)
                elif isinstance(obj, dict):
                    return {k: clean_floats(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [clean_floats(item) for item in obj]
                return obj

            anomaly_data = clean_floats(anomaly_data)

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
1. ÖZET (4-5 cümle): Ne bulundu, kritik mi?
2. TOP 10 KRİTİK SORUN: Component, sebep, risk, feature, log mesajı
3. ACİL AKSİYONLAR: Max 3 madde, spesifik ol, rastgele verme, genel geçer bilgiler sunma işe yarar öneriler ver.
4. İZLEME ÖNERİSİ: 1 cümle

Türkçe yaz. MongoDB best practice'lerini kullan. Rastgele öneri verme. Teknik ol ama anlaşılır ol. Gereksiz tekrar yapma"""
            
            # Optimize edilmiş user prompt - daha fazla context ile
            server_info = f"Sunucu: {server_name}\n" if server_name else ""
            
            # FIX: score_range bazen doğrudan float gelebilir, get() çağırmadan önce kontrol et
            score_range = summary.get('score_range', {})
            
            mean_score = 0
            min_score = 0
            max_score = 0

            if isinstance(score_range, dict):
                mean_score = score_range.get('mean', 0)
                min_score = score_range.get('min', 0)
                max_score = score_range.get('max', 0)
            elif isinstance(score_range, (int, float)):
                mean_score = float(score_range)
                min_score = float(score_range)
                max_score = float(score_range)

            # User prompt oluşturulurken bu değişkenler kullanılacak
            
            user_prompt = f"""{server_info}Analiz Özeti: {summary.get('n_anomalies', 0)} anomali / {summary.get('total_logs', 0):,} log (%{summary.get('anomaly_rate', 0):.1f})

Ortalama anomali skoru: {mean_score:.3f}

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
                f"Yüksek anomali oranına sahip bileşenlere odaklanın",
                f"Kritik anomalileri öncelikle çözün"
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

    def _format_feature_importance_for_prompt(self, features: Dict) -> str:
        """Feature importance'ı prompt için formatla"""
        if not features:
            return "Feature analizi mevcut değil."
        
        result = []
        
        def get_importance_value(stats):
            """Feature importance değerini güvenli şekilde al"""
            if isinstance(stats, (int, float)):
                return float(stats)
            elif isinstance(stats, dict):
                return float(stats.get('ratio', stats.get('importance', 0)))
            else:
                return 0.0
        
        sorted_features = sorted(features.items(), 
                               key=lambda x: get_importance_value(x[1]), 
                               reverse=True)
        
        for feat, stats in sorted_features[:5]:
            importance = get_importance_value(stats)
            if importance > 0.1:
                result.append(f"- {feat}: {importance:.2f} importance")
        
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

    def _select_diverse_anomalies(self, anomalies: List[Dict], limit: int = 75, is_mssql: bool = False) -> List[Dict]:
        """
        Kategori çeşitliliği sağlayan akıllı anomali örneklemesi.

        Sadece severity_score'a göre top-N almak yerine, farklı kategorilerden
        temsil sağlar. Bu sayede nadir ama önemli anomali tipleri kaçırılmaz.

        Algoritma:
        1. Anomalileri kategoriye göre grupla
        2. Her kategoriden en az min_per_category adet al (en yüksek severity)
        3. Kalan slotları en yüksek severity'den doldur
        """
        if not anomalies or len(anomalies) <= limit:
            return anomalies

        # Kategori belirleme
        categorized = {}
        for a in anomalies:
            if is_mssql:
                # MSSQL: logtype veya mesaj pattern'ına göre
                cat = a.get('component') or 'general'
                msg = (a.get('message') or '').lower()
                if 'login failed' in msg or 'authentication failed' in msg:
                    cat = 'failed_login'
                elif 'availability group' in msg or 'not accessible' in msg:
                    cat = 'availability_group'
                elif 'cannot open database' in msg or 'database' in msg:
                    cat = 'database_access'
                elif 'permission' in msg or 'access denied' in msg:
                    cat = 'permission_error'
                elif 'connection' in msg or 'socket' in msg:
                    cat = 'connection_error'
            else:
                # MongoDB: component veya anomaly_type'a göre
                cat = a.get('component') or a.get('anomaly_type') or 'general'

            cat = str(cat).lower()
            if cat not in categorized:
                categorized[cat] = []
            categorized[cat].append(a)

        n_categories = len(categorized)
        if n_categories <= 1:
            return sorted(anomalies, key=lambda x: x.get('severity_score', 0), reverse=True)[:limit]

        # Her kategoriden minimum temsil
        min_per_category = max(2, limit // (n_categories * 2))
        selected = []
        selected_indices = set()

        # 1. aşama: Her kategoriden min_per_category kadar al
        for cat, items in categorized.items():
            items_sorted = sorted(items, key=lambda x: x.get('severity_score', 0), reverse=True)
            for item in items_sorted[:min_per_category]:
                idx = item.get('index')
                if idx not in selected_indices:
                    selected.append(item)
                    selected_indices.add(idx)

        # 2. aşama: Kalan slotları en yüksek severity'den doldur
        remaining_limit = limit - len(selected)
        if remaining_limit > 0:
            all_sorted = sorted(anomalies, key=lambda x: x.get('severity_score', 0), reverse=True)
            for item in all_sorted:
                if len(selected) >= limit:
                    break
                idx = item.get('index')
                if idx not in selected_indices:
                    selected.append(item)
                    selected_indices.add(idx)

        # Final sıralama: severity_score'a göre
        selected.sort(key=lambda x: x.get('severity_score', 0), reverse=True)

        logger.info(f"Diverse sampling: {len(anomalies)} anomalies -> {len(selected)} selected "
                     f"({n_categories} categories, min {min_per_category}/category)")
        return selected

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

            # Safe access to score_range which can be float or dict
            score_range_data = summary.get('score_range', {})
            avg_score = 0.0

            if isinstance(score_range_data, (int, float)):
                avg_score = float(score_range_data)
            elif isinstance(score_range_data, dict):
                avg_score = float(score_range_data.get('mean', 0))
                
            desc += f"• Ortalama Anomali Skoru: {avg_score:.3f}\n"
        
        return desc

    async def query_anomalies_from_storage(self, query: str, analysis_id: str = None, limit: int = 50) -> Dict[str, Any]:
        """
        Storage'daki anomalileri LCWGPT ile sorgula
        
        Args:
            query: Kullanıcı sorusu
            analysis_id: Specific analysis ID (optional)
            limit: Max anomalies to process per chunk
            
        Returns:
            AI processed response
        """
        try:
            # Storage manager'ı import et
            from src.storage.storage_manager import StorageManager
            storage = StorageManager()
            await storage.initialize()
            
            # Son analizi veya belirli analizi al
            if analysis_id:
                filters = {"analysis_id": analysis_id}
            else:
                filters = {}
                
            analyses = await storage.get_anomaly_history(
                filters=filters,
                limit=1,
                include_details=True
            )
            
            if not analyses:
                return {"error": "Henüz kayıtlı anomali analizi yok"}
                
            analysis = analyses[0]
            
            # Unfiltered anomalileri al (yoksa filtered kullan)
            all_anomalies = (
                analysis.get("unfiltered_anomalies", []) or 
                analysis.get("critical_anomalies_full", []) or
                analysis.get("critical_anomalies_display", [])
            )
            
            if not all_anomalies:
                return {"error": "Kayıtlı anomali bulunamadı"}
                
            # LCWGPT ile işle (chunked)
            if not self.llm_connector or not self.llm_connector.is_connected():
                return {"error": "LCWGPT bağlantısı yok"}
                
            # Token limit için chunk'lara böl
            chunks = [all_anomalies[i:i+limit] for i in range(0, len(all_anomalies), limit)]
            
            system_prompt = """MongoDB anomali uzmanısın. Kullanıcı sorusuna göre anomalileri analiz et.
            Kullanıcı şunları sorabilir:
            - Belirli component'teki anomaliler
            - Belirli severity'deki anomaliler
            - Zaman bazlı filtreleme
            - Pattern analizi
            
            Kısa, net ve aksiyona yönelik yanıt ver."""
            
            # İlk chunk'ı işle (token limiti için)
            first_chunk = chunks[0]
            
            user_prompt = f"""
            Kullanıcı Sorusu: {query}
            
            Toplam Anomali: {len(all_anomalies)}
            İşlenen Chunk: 1/{len(chunks)} ({len(first_chunk)} anomali)
            
            Anomali Detayları:
            {self._format_anomalies_for_ai_query(first_chunk)}
            
            Component Dağılımı:
            {self._get_component_distribution(all_anomalies)}
            """
            
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]
            
            response = self.llm_connector.invoke(messages)
            
            return {
                "query": query,
                "total_anomalies": len(all_anomalies),
                "processed_chunk": f"1/{len(chunks)}",
                "ai_response": response.content,
                "analysis_id": analysis.get("analysis_id"),
                "timestamp": analysis.get("timestamp")
            }
            
        except Exception as e:
            logger.error(f"Storage query error: {e}")
            return {"error": str(e)}

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


class AnalyzeMSSQLLogsArgs(BaseModel):
    """MSSQL Log Anomali Analizi Argümanları"""
    time_range: str = Field(default="last_hour", description="Zaman aralığı: last_hour, last_day, last_week, last_month")
    threshold: float = Field(default=0.03, description="Anomali eşik değeri")
    source_type: Optional[str] = Field(default="opensearch", description="Veri kaynağı: opensearch")
    last_hours: Optional[int] = Field(default=None, description="Kaç saatlik log okunacak (OpenSearch için)")
    host_filter: Optional[str] = Field(default=None, description="Belirli bir MSSQL sunucusundan logları filtrele")


class AnalyzeESLogsArgs(BaseModel):
    """Elasticsearch Log Anomali Analizi Argümanları"""
    time_range: str = Field(default="last_hour", description="Zaman aralığı: last_hour, last_day, last_week, last_month")
    threshold: float = Field(default=0.03, description="Anomali eşik değeri")
    source_type: Optional[str] = Field(default="opensearch", description="Veri kaynağı: opensearch")
    last_hours: Optional[int] = Field(default=None, description="Kaç saatlik log okunacak (OpenSearch için)")
    host_filter: Optional[str] = Field(default=None, description="Belirli bir Elasticsearch node'undan logları filtrele (ör. ECAZTRDBESRW003)")


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
                name="analyze_mssql_logs",
                description="MSSQL loglarında anomali analizi yap (OpenSearch üzerinden)",
                func=lambda **kwargs: anomaly_tools.analyze_mssql_logs(kwargs),
                args_schema=AnalyzeMSSQLLogsArgs
            ),

            StructuredTool(
                name="analyze_elasticsearch_logs",
                description="Elasticsearch loglarında anomali analizi yap (OpenSearch üzerinden, db-elasticsearch-* index)",
                func=lambda **kwargs: anomaly_tools.analyze_elasticsearch_logs(kwargs),
                args_schema=AnalyzeESLogsArgs
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