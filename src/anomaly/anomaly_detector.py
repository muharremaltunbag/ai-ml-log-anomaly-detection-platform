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
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional
from collections import deque
from sklearn.preprocessing import StandardScaler
import copy  # ✅ Deep copy for per-model scaler snapshots
import threading  # ✅ Thread synchronization

# YENİ: Message extraction import
from .log_reader import extract_mongodb_message

logger = logging.getLogger(__name__)

class MongoDBAnomalyDetector:
    """MongoDB logları için anomali tespiti"""

    # YENİ: Küresel kilitler ve instance cache (Class level)
    _model_io_lock = threading.Lock()
    _instances = {}  # {server_name: instance_object}
    _instance_lock = threading.Lock()

    @classmethod
    def get_instance(cls, server_name: str = "global", config_path: str = "config/anomaly_config.json"):
        """Belirli bir sunucu için bellekteki mevcut modeli döndürür, yoksa oluşturur."""
        # FQDN NORMALIZATION
        # ecaztrdbmng015.lcwecomtr.com → ecaztrdbmng015
        # ECAZTRDBMNG015.lcwaikiki.local → ecaztrdbmng015
        raw_name = server_name or "global"
        
        # FQDN ise sadece hostname'i al (ilk nokta öncesi)
        if '.' in raw_name and raw_name != "global":
            hostname = raw_name.split('.')[0]
            logger.debug(f"FQDN normalized: {raw_name} -> {hostname}")
        else:
            hostname = raw_name
        
        # Lowercase ve güvenli karakter dönüşümü
        safe_name = hostname.lower().replace('/', '_')


        with cls._instance_lock:
            if safe_name not in cls._instances:
                logger.info(f"Creating NEW shared instance for server: {safe_name}")
                instance = cls(config_path)
                # Nesne oluşturulduğunda modeli diskten yüklemeyi dene
                # load_model'e normalize edilmiş server_name gönder
                instance.load_model(server_name=safe_name if safe_name != "global" else None)
                cls._instances[safe_name] = instance
            else:
                logger.debug(f"Using EXISTING shared instance for server: {safe_name}")

            return cls._instances[safe_name]


    def __init__(self, config_path: str = "config/anomaly_config.json"):
        """
        Anomaly Detector başlat
        
        Args:
            config_path: Konfigürasyon dosyası yolu
        """
        self.config = self._load_config(config_path)
        self.model_config = self.config['anomaly_detection']['model']
        self.output_config = self.config['anomaly_detection']['output']

        # MODEL VERSION — Tek merkez
        self.model_version = self.config.get("model_version", "2.0")
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
        
        # Thread safety için locklar
        self._training_lock = threading.Lock()
        # Instance kilitlerini geriye dönük uyumluluk için sınıf kilidine yönlendiriyoruz
        self._save_lock = self.__class__._model_io_lock
        self._load_lock = self.__class__._model_io_lock        

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
        
        # YENİ: Server-specific model management
        self.current_server = None  # Aktif sunucu adı
        self.server_models = {}     # Her sunucu için model metadata cache
        # Format: {'server_name': {'model_path': 'path', 'last_update': datetime, 'sample_count': int}}

        # Critical rules engine
        self.critical_rules = self._initialize_critical_rules()
        
        # Incremental Learning - Ensemble of Mini Models
        self.incremental_models = deque(maxlen=10)  # Max 10 mini model
        self.model_scalers = deque(maxlen=10)  # Her mini-modelin kendi scaler snapshot'ı
        self.model_weights = []  # Her modelin ağırlığı
        self.model_metadata = []  # Her modelin metadata'sı
        self.incremental_config = {
            'enabled': True,
            'max_models': 10,
            'min_samples_per_model': 1000,
            'weight_decay_factor': 0.9,  # Eski modellerin ağırlığı azalır
            'drift_threshold': 0.3,  # Model drift threshold
            'ensemble_method': 'weighted_voting'  # 'weighted_voting' veya 'stacking'
        }
        self.scaler = StandardScaler()  # Feature normalization için
        self.is_scaler_fitted = False
        self._ensemble_mode = False  # True = ensemble aktif, self.model sentinel olarak None kullanılmaz
        self.rule_stats = {'total_overrides': 0, 'rule_hits': {}}
        
        
        
        logger.info(f"Anomaly detector initialized with {self.model_config['type']} model")
    def _initialize_critical_rules(self) -> Dict[str, Any]:
        """
        Kritik anomali kurallarını tanımla

        Returns:
            Rule dictionary
        """

        rules = {
            # --- SİSTEM SAĞLIĞI ---
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

            # --- PERFORMANS & SORGULAR (PROD OPTIMIZED) ---

            # 1. MASSIVE COLLSCAN (Veri Madenciliği Gibi)
            # Loglarda 3.2M döküman tarayan sorgular görüldü. Bu sunucuyu kilitler.
            'massive_scan': {
                'condition': lambda row: (
                    row.get('docs_examined_count', 0) > 1000000  # 1 Milyon+
                ),
                'severity': 1.0,  # CRITICAL (Fatal kadar önemli)
                'description': 'Massive document scan (>1M docs)'
            },

            # 2. Performans Kritik (Ağır COLLSCAN)
            # Standart kural: Sadece yüksek döküman tarayan COLLSCAN'leri yakala
            'performance_critical': {
                'condition': lambda row: (
                    row.get('is_collscan', 0) == 1 and 
                    row.get('docs_examined_count', 0) > 100000
                ),
                'severity': 0.85,
                'description': 'Critical performance issue (Heavy Scan)'
            },

            # 3. INEFFICIENT INDEX (Verimsiz İndeks)
            # 156ms'de 125k key tarayan sorgular var. İndeks var ama verimsiz.
            'inefficient_index': {
                'condition': lambda row: (
                    row.get('keys_examined_count', 0) > 10000 and
                    row.get('docs_examined_count', 0) > 10000 and
                    # Keys > Docs ise indeks verimsiz çalışıyor demektir
                    row.get('keys_examined_count', 0) > row.get('docs_examined_count', 0) * 2
                ),
                'severity': 0.85,
                'description': 'Inefficient index usage (High Key Scan)'
            },

            # 4. LONG TRANSACTION (Uzun Süren Transaction)
            # 3.6 saniye süren transactionlar görüldü. Locking yaratır.
            'long_transaction': {
                'condition': lambda row: (
                    # TXN logu veya uzun süren işlem
                    (row.get('component_encoded', 0) == 'TXN' or row.get('c') == 'TXN') and
                    row.get('query_duration_ms', 0) > 3000  # 3 saniye üzeri transaction
                ),
                'severity': 0.90,
                'description': 'Long running transaction (>3s)'
            },

            # --- ALTYAPI & REPLİKASYON ---

            # 5. Replikasyon Sorunları (Data Safety)
            'replication_risk': {
                'condition': lambda row: (
                    row.get('is_replication_issue', 0) == 1
                ),
                'severity': 0.90,
                'description': 'Replication integrity risk'
            },

            # 3. Bellek/Cache Baskısı (Stability) - Eviction storm ve memory limit
            'memory_pressure': {
                'condition': lambda row: (
                    row.get('is_memory_limit', 0) == 1 or
                    (row.get('is_wiredtiger_event', 0) == 1 and row.get('severity_W', 0) == 1)
                ),
                'severity': 0.88,
                'description': 'High memory pressure detected'
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

        return rules


    def _load_config(self, config_path: str) -> Dict:
        """Config dosyasını yükle"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                
                # Config validation
                self._validate_config(config)
                
                return config
        except FileNotFoundError:
            logger.warning(f"Config file not found, using defaults: {config_path}")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in config file: {e}")
        except ValueError as e:
            logger.error(f"Config validation failed: {e}")
        except Exception as e:
            logger.error(f"Unexpected error loading config: {e}")
            
        # Varsayılan config
        default_config = {
            "anomaly_detection": {
                "model": {
                    "type": "IsolationForest",
                    "parameters": {
                        "contamination": 0.03,
                        "n_estimators": 300,
                        "random_state": 42
                    }
                },
                "output": {},
                "online_learning": {
                    "enabled": True,
                    "max_history_size": 100000
                }
            }
        }
        logger.info("Using default configuration")
        return default_config
    
    def _validate_config(self, config: Dict) -> None:
        """
        Config validation - kritik parametreleri kontrol et
        
        Args:
            config: Config dictionary
            
        Raises:
            ValueError: Config geçersizse
        """
        # Kritik anahtarları kontrol et
        if 'anomaly_detection' not in config:
            raise ValueError("Missing 'anomaly_detection' in config")
        
        ad_config = config['anomaly_detection']
        
        if 'model' not in ad_config:
            raise ValueError("Missing 'model' in anomaly_detection config")
        
        if 'type' not in ad_config['model']:
            raise ValueError("Missing model type in config")
        
        # Model tipi kontrolü
        supported_models = ['IsolationForest']
        if ad_config['model']['type'] not in supported_models:
            raise ValueError(f"Unsupported model type: {ad_config['model']['type']}")
        
        # Contamination değeri kontrolü
        if 'parameters' in ad_config['model']:
            contamination = ad_config['model']['parameters'].get('contamination', 0.03)
            if not (0 < contamination < 0.5):
                raise ValueError(f"Invalid contamination value: {contamination} (must be between 0 and 0.5)")
        

    def _combine_with_history(self, X_new: pd.DataFrame) -> pd.DataFrame:
        """
        Yeni veriyi historical data ile birleştir
        
        Args:
            X_new: Yeni feature matrix
            
        Returns:
            Birleştirilmiş feature matrix
        """
        logger.debug(f"Combining new data with historical buffer...")
        
        try:
            # Historical features'ı al
            X_historical = self.historical_data['features']
            
            # Feature uyumluluğunu kontrol et
            # === GRACEFUL FEATURE ALIGNMENT BEFORE CONCAT ===
            hist_cols = set(X_historical.columns)
            new_cols = set(X_new.columns)

            if hist_cols != new_cols:
                missing_in_new = hist_cols - new_cols
                missing_in_hist = new_cols - hist_cols

                if missing_in_new or missing_in_hist:
                    logger.warning(
                        f"[Feature Alignment] Feature set difference detected. "
                        f"In historical but not in new: {missing_in_new or 'none'} | "
                        f"In new but not in historical: {missing_in_hist or 'none'}. "
                        f"Aligning both sides with default 0.0"
                    )
                    # Yeni data'da eksik feature'ları 0.0 ile ekle
                    for col in missing_in_new:
                        X_new[col] = 0.0
                    # Historical'da eksik feature'ları 0.0 ile ekle
                    for col in missing_in_hist:
                        X_historical[col] = 0.0

            # Ortak kolon sırasını belirle (new data'nın sırasını temel al)
            unified_cols = list(X_new.columns)
            X_historical = X_historical[unified_cols]
            X_new = X_new[unified_cols]

            # Full History Strategy - Tüm historical data'yı koru
            X_combined = pd.concat([X_historical, X_new], ignore_index=True)
            
            # Basit buffer limiti - En yeni kayıtları tut (FIFO)
            # Config'ten max_history_size oku, yoksa default 100000 kullan
            max_buffer_samples = self.online_learning_config.get('max_history_size', None)
            if max_buffer_samples is None:
                max_buffer_samples = 100000  # Default limit
                
            if len(X_combined) > max_buffer_samples:
                # En eski kayıtları at, en yeni max_buffer_samples kadarını tut
                logger.info(f"Buffer size ({len(X_combined)}) exceeded limit ({max_buffer_samples}), trimming to {max_buffer_samples}")
                X_combined = X_combined.tail(max_buffer_samples)

            # Duplicate kontrolü - SADECE tamamen aynı olan kayıtları kaldır
            initial_size = len(X_combined)

            # Opsiyon 1: Duplicate kontrolünü tamamen kapat
            # X_combined = X_combined  # Hiç duplicate kontrolü yapma

            # Opsiyon 2: Sadece TAMAMEN aynı olan satırları kaldır (tüm feature'lar aynıysa)
            X_combined = X_combined.drop_duplicates()

            if initial_size != len(X_combined):
                logger.debug(f"Removed {initial_size - len(X_combined)} duplicate samples ({(initial_size - len(X_combined))/initial_size*100:.1f}%)")
            
            # IndexError'ı önlemek için index'i reset et
            X_combined = X_combined.reset_index(drop=True)
            
            return X_combined
            
        except Exception as e:
            logger.error(f"Failed to combine with historical data: {e}")
            # Hata durumunda sadece yeni veriyi kullan
            return X_new

    def train(self, X: pd.DataFrame, save_model: bool = None, incremental: bool = None,
              server_name: str = None) -> Dict[str, Any]:
        """
        Anomali modelini eğit (Online Learning desteği ile)

        Args:
            X: Feature matrix
            save_model: Modeli kaydet (None ise config'den al)
            incremental: Online learning kullan (None ise config'den al)
            server_name: Sunucu adı (model yönetimi için)

        Returns:
            Training sonuçları
        """

        # Thread safety - tüm training süreci boyunca lock tut
        self._training_lock.acquire()
        try:
            if server_name:
                logger.debug(f"Training for server: {server_name}")
            logger.info(f"Training model on {X.shape[0]} samples with {X.shape[1]} features...")

            # Current server'ı güncelle
            self.current_server = server_name

            # Online learning kontrolü
            if incremental is None:
                incremental = self.online_learning_config.get('enabled', True)

            # Feature isimlerini sakla
            self.feature_names = list(X.columns)

            # Historical data ile birleştir
            X_train = X.copy()
            training_mode = "new"

            if incremental and self.is_trained and self.historical_data['features'] is not None:
                # Historical data ile birleştir
                X_train = self._combine_with_history(X)
                training_mode = "incremental"
            else:
                logger.debug("Standard training mode (no historical data)")

            # Model parametreleri
            params = self.model_config['parameters'].copy()

            # === DYNAMIC PARAMETER ADJUSTMENT (tüm training modları için) ===
            # Küçük veri setlerinde (< 2000 sample) sabit contamination ve max_samples
            # modelin yeterli anomali üretememesine neden olur. Veri boyutuna göre
            # dinamik ayarlama yaparak her sunucuda anlamlı sonuç üretmeyi garanti ederiz.
            dataset_size = X_train.shape[0]
            original_contamination = params.get('contamination', 0.05)
            original_max_samples = params.get('max_samples', 512)

            if dataset_size < 500:
                # Çok küçük veri seti: daha yüksek contamination, auto max_samples
                params['contamination'] = min(0.10, original_contamination * 2)
                params['max_samples'] = 'auto'
                logger.info(
                    f"[Dynamic Params] Very small dataset ({dataset_size} samples). "
                    f"contamination: {original_contamination} -> {params['contamination']}, "
                    f"max_samples: {original_max_samples} -> auto"
                )
            elif dataset_size < 2000:
                # Küçük veri seti: hafif artırılmış contamination, orantılı max_samples
                params['contamination'] = min(0.08, original_contamination * 1.5)
                adjusted_max_samples = min(int(dataset_size * 0.8), original_max_samples)
                params['max_samples'] = max(adjusted_max_samples, 64)  # Minimum 64
                logger.info(
                    f"[Dynamic Params] Small dataset ({dataset_size} samples). "
                    f"contamination: {original_contamination} -> {params['contamination']}, "
                    f"max_samples: {original_max_samples} -> {params['max_samples']}"
                )
            else:
                # Normal/büyük veri seti: config değerlerini koru
                logger.debug(
                    f"[Dynamic Params] Normal dataset ({dataset_size} samples). "
                    f"Using config values: contamination={original_contamination}, "
                    f"max_samples={original_max_samples}"
                )

            # EK: Incremental mode'da combined dataset boyutuna göre max_samples ayarla
            # (mevcut mantık korundu, dynamic params'ın üzerine yazabilir)
            # NOT: max_samples 'auto' (string) olabilir, bu durumu güvenli şekilde atla
            current_max_samples = params.get('max_samples', 512)
            if (incremental and self.is_trained
                    and isinstance(current_max_samples, (int, float))
                    and dataset_size < current_max_samples * 2):
                # Dataset'in %80'ini kullan veya 256 (hangisi küçükse)
                inc_max_samples = min(int(dataset_size * 0.8), 256)

                # Minimum 10 sample kontrolü
                if inc_max_samples < 10:
                    logger.debug(f"WARNING: Very few samples after deduplication ({dataset_size})")
                    params['max_samples'] = 'auto'  # sklearn'ün otomatik hesaplamasına bırak
                else:
                    params['max_samples'] = inc_max_samples

                logger.debug(f"[Incremental] Adjusted max_samples to {params['max_samples']} (dataset size: {dataset_size})")

            # Index'i reset et (sklearn için kritik!)
            X_train = X_train.reset_index(drop=True)

            # === GRACEFUL FEATURE ALIGNMENT BEFORE MODEL FIT ===

            # 1) Eğer geçmiş feature_names varsa, hizala veya güncelle
            if self.feature_names and list(X_train.columns) != self.feature_names:
                missing = set(self.feature_names) - set(X_train.columns)
                extra   = set(X_train.columns) - set(self.feature_names)
                if missing or extra:
                    # Feature set değişmiş → yeni run'ın feature setini kabul et
                    logger.warning(
                        f"[Feature Alignment] Saved feature_names differ from X_train. "
                        f"Missing: {missing or 'none'} | Extra: {extra or 'none'}. "
                        f"Updating feature_names to current run's feature set."
                    )
                    self.feature_names = list(X_train.columns)
                else:
                    # Sadece order farkı — saved order'a göre sırala
                    X_train = X_train[self.feature_names]
                    logger.debug("Reordered X_train to match saved feature_names before fit().")

            # 2) Eğer incremental retraining ve mevcut model sklearn feature_names_in_ içeriyorsa
            if hasattr(self.model, 'feature_names_in_'):
                sklearn_cols = list(self.model.feature_names_in_)
                if sklearn_cols != list(X_train.columns):
                    missing = set(sklearn_cols) - set(X_train.columns)
                    extra   = set(X_train.columns) - set(sklearn_cols)
                    if missing or extra:
                        # Eski model feature set'i ile uyumsuz → controlled retrain (yeni model)
                        logger.warning(
                            f"[Controlled Retrain] sklearn feature_names_in_ mismatch. "
                            f"Missing: {missing or 'none'} | Extra: {extra or 'none'}. "
                            f"Creating new model instance for clean training."
                        )
                        self.model = IsolationForest(**params)
                    else:
                        # Sadece order farkı — sklearn order'a göre sırala
                        X_train = X_train[sklearn_cols]
                        logger.debug("Reordered X_train to sklearn feature_names_in_ before fit().")

            # Model oluştur veya mevcut modeli kullan
            if not self.is_trained:
                # İlk kez model oluştur
                if self.model_config['type'] == 'IsolationForest':
                    logger.debug("Creating NEW IsolationForest model (first training)...")
                    self.model = IsolationForest(**params)
                else:
                    raise ValueError(f"Unknown model type: {self.model_config['type']}")
            elif incremental and self.is_trained:
                logger.debug("INCREMENTAL MODE: Retraining existing model with combined data")

                # FIX: Ensemble mode'dan yüklenen model None olabilir (train_incremental
                # self.model = None yapar, save_model bu None'ı diske yazar, load_model
                # geri yükler). Bu durumda yeni IsolationForest oluştur.
                if self.model is None:
                    logger.warning(
                        "self.model is None (loaded from ensemble-mode save). "
                        "Creating new IsolationForest for incremental retraining."
                    )
                    self.model = IsolationForest(**params)

                # Mevcut model parametrelerini güncelle ama instance'ı değiştirme
                if hasattr(self.model, 'contamination'):
                    self.model.contamination = params.get('contamination', 0.03)
                # NOT: IsolationForest'ın set_params metodu ile parametreleri güncelleyebiliriz
                # ama model tekrar fit edilecek zaten, bu yüzden yeni instance oluşturmak da sorun değil
                # Ancak historical continuity için mevcut model'i koruyoruz
            else:
                # Non-incremental mode ama model trained - yine de yeni model oluştur
                if self.model_config['type'] == 'IsolationForest':
                    self.model = IsolationForest(**params)

            # Eğitim

            start_time = datetime.now()
            # === FIX: FEATURE SCALING ===
            logger.info("Applying StandardScaler to training data to prevent feature dominance...")
            # Veriyi scale et (normalize et)
            X_train_scaled_np = self.scaler.fit_transform(X_train)
            self.is_scaler_fitted = True

            # DataFrame formatını koru (IsolationForest feature name'leri saklasın diye)
            X_train_scaled = pd.DataFrame(X_train_scaled_np, columns=X_train.columns)
            # X yerine X_train_scaled kullan
            self.model.fit(X_train_scaled)
            training_time = (datetime.now() - start_time).total_seconds()

            # Eğitim istatistikleri
            self.training_stats = {
                "n_samples": X.shape[0],
                "n_features": X.shape[1],
                "feature_names": self.feature_names,
                "feature_schema": {
                    "names": self.feature_names,
                    "count": len(self.feature_names),
                },
                "training_time_seconds": training_time,
                "model_type": self.model_config['type'],
                "parameters": params,
                "contamination_used": params.get('contamination', 0.05),
                "timestamp": datetime.now().isoformat(),
                "server_name": server_name,  # YENİ: Sunucu bilgisi
                "model_version": self.model_version  # MODEL VERSION EKLENDİ
            }
            self.is_trained = True
            logger.debug(f"Training completed - Model is now ready for predictions")
            logger.info(f"Model training completed in {training_time:.2f} seconds")

            # Online Learning: Historical buffer'ı güncelle
            if incremental and self.online_learning_config.get('enabled', True):
                logger.debug(f"Updating historical buffer...")
                self._update_historical_buffer(X, X_train, training_mode)  # ✅ ÖNCE GÜNCELLE

            # Model kaydetme
            if save_model is None:
                save_model = self.output_config.get('save_model', True)

            if save_model:
                self.save_model(server_name=server_name)  # ✅ SONRA KAYDET

            return self.training_stats

        finally:
            # Thread safety - lock'u her durumda (başarı/hata) serbest bırak
            self._training_lock.release()
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
            logger.debug(f"Updating historical buffer - Mode: {training_mode}")

            # İlk training ise veya yeni training mode
            if training_mode == "new" or self.historical_data['features'] is None:
                # Direkt yeni veriyi historical olarak sakla
                self.historical_data['features'] = X_new.copy().reset_index(drop=True)

                # Predictions ve scores'u hesapla ve sakla
                # Model scaled veri ile eğitildi; predict için de scale etmemiz gerekiyor
                if self.is_scaler_fitted:
                    X_for_predict = pd.DataFrame(
                        self.scaler.transform(X_new), columns=X_new.columns
                    )
                else:
                    X_for_predict = X_new

                # Safety: self.model None ise (legacy sentinel) ensemble'dan recover et
                if self.model is None and self.incremental_models:
                    self.model = self.incremental_models[-1]
                    logger.warning("_update_historical_buffer: recovered model from ensemble (legacy None sentinel)")

                predictions = self.model.predict(X_for_predict)
                scores = self.model.score_samples(X_for_predict)

                self.historical_data['predictions'] = predictions
                self.historical_data['scores'] = scores

            else:  # incremental mode

                # FIFO Mantığını bozmadan, bellek kullanımını minimize eden yeni yapı

                # Buffer limit kontrolü - online_learning config'den al
                # max_history_size null ise max_buffer_samples kullan, o da yoksa default 100000
                max_buffer_size = (
                    self.online_learning_config.get('max_history_size') or 
                    self.online_learning_config.get('max_buffer_samples', 100000)
                )
                
                old_buffer = self.historical_data['features']
                new_data_size = len(X_new)

                if old_buffer is not None:
                    # 1. Adım: Eski veriden ne kadarını saklayabileceğimizi hesapla
                    keep_from_old = max_buffer_size - new_data_size
                    
                    if keep_from_old > 0:
                        # Sadece sığacak kadarını kırpıp yeni bir değişkene al
                        trimmed_old = old_buffer.tail(keep_from_old)
                        # 2. Adım: RAM'de yer açmak için büyük objeyi hemen serbest bırak
                        old_buffer = None 
                        # 3. Adım: Küçük parça ile yeni veriyi birleştir
                        self.historical_data['features'] = pd.concat([trimmed_old, X_new], ignore_index=True)
                    else:
                        # Yeni veri zaten limitten büyük veya eşitse eskiyi tamamen at
                        old_buffer = None
                        self.historical_data['features'] = X_new.tail(max_buffer_size).reset_index(drop=True)
                else:
                    self.historical_data['features'] = X_new.tail(max_buffer_size).reset_index(drop=True)

                # 4. Adım: Multi-user yükü altında Python'ın çöp toplayıcısını (GC) tetikle
                import gc
                gc.collect()

                # Yeni predictions ve scores hesapla (güncel buffer için)
                # Model scaled veri ile eğitildi; predict için de scale etmemiz gerekiyor
                if self.is_scaler_fitted:
                    buffer_scaled = pd.DataFrame(
                        self.scaler.transform(self.historical_data['features']),
                        columns=self.historical_data['features'].columns
                    )
                else:
                    buffer_scaled = self.historical_data['features']

                # Safety: self.model None ise (legacy sentinel) ensemble'dan recover et
                if self.model is None and self.incremental_models:
                    self.model = self.incremental_models[-1]
                    logger.warning("_update_historical_buffer: recovered model from ensemble (legacy None sentinel, incremental mode)")

                predictions = self.model.predict(buffer_scaled)
                scores = self.model.score_samples(buffer_scaled)

                self.historical_data['predictions'] = predictions
                self.historical_data['scores'] = scores

            # Metadata güncelle
            self.historical_data['metadata']['total_samples'] = len(self.historical_data['features'])
            self.historical_data['metadata']['anomaly_samples'] = int((self.historical_data['predictions'] == -1).sum())
            self.historical_data['metadata']['last_update'] = datetime.now().isoformat()
            self.historical_data['metadata']['buffer_version'] = 2.0  # Dolu buffer artık v2.0

            # İstatistikleri logla
            anomaly_rate = (self.historical_data['predictions'] == -1).mean() * 100

            logger.info(f"Historical buffer updated:")
            logger.info(f"  Total samples: {self.historical_data['metadata']['total_samples']}")
            logger.info(f"  Anomaly samples: {self.historical_data['metadata']['anomaly_samples']} ({anomaly_rate:.1f}%)")

            # Bellek kullanımı kontrolü
            buffer_size_mb = self.historical_data['features'].memory_usage(deep=True).sum() / 1024 / 1024
            logger.info(f"  Buffer size: {buffer_size_mb:.2f} MB")

            # Kritik bellek yönetimi kısmı aynı kalabilir
            warning_threshold_mb = 1000
            critical_threshold_mb = 2000

            if buffer_size_mb > critical_threshold_mb:
                logger.critical(f"Buffer critically large ({buffer_size_mb:.2f} MB), trimming to 50%...")
                keep_samples = len(self.historical_data['features']) // 2
                self.historical_data['features'] = self.historical_data['features'].tail(keep_samples)
                self.historical_data['predictions'] = self.historical_data['predictions'][-keep_samples:]
                self.historical_data['scores'] = self.historical_data['scores'][-keep_samples:]
                new_size_mb = self.historical_data['features'].memory_usage(deep=True).sum() / 1024 / 1024
                logger.info(f"Buffer trimmed: {buffer_size_mb:.2f} MB -> {new_size_mb:.2f} MB")
            elif buffer_size_mb > warning_threshold_mb:
                logger.warning(f"Historical buffer size is large: {buffer_size_mb:.2f} MB")

        except Exception as e:
            logger.error(f"Error updating historical buffer: {e}", exc_info=True)

    def predict(self, X: pd.DataFrame, df: Optional[pd.DataFrame] = None) -> Tuple[np.ndarray, np.ndarray]:
        """
        Anomali tahminleri yap (Ensemble model ile) - THREAD SAFE
        
        Args:
            X: Feature matrix
            df: Original dataframe (rule engine için gerekli)
            
        Returns:
            (predictions, anomaly_scores): -1=anomaly, 1=normal ve anomaly skorları
        """
        
        if not self.is_trained:
            raise ValueError("Model is not trained yet!")

        # Thread safety - Tahmin sırasında modelin eğitilmediğinden/değiştirilmediğinden emin ol
        with self._training_lock:
            # Feature schema doğrulama — predict'e gelen X ile model'in beklediği feature'ları karşılaştır
            feature_schema = self.training_stats.get("feature_schema") if self.training_stats else None
            if feature_schema and feature_schema.get("names"):
                schema_count = feature_schema.get("count", len(feature_schema["names"]))
                input_count = X.shape[1]
                if input_count != schema_count:
                    logger.info(
                        f"[Feature Schema] Input has {input_count} features, "
                        f"model expects {schema_count}. Alignment will be applied."
                    )

            # Feature isimleri ve sırasını güvenli şekilde hizala
            if self.feature_names is None or not len(self.feature_names):
                # Modelde feature bilgisi yoksa, ilk gelen X'i referans al
                logger.warning(
                    "Model feature_names is empty/None. "
                    "Setting feature_names from current input columns."
                )
                self.feature_names = list(X.columns)
            else:
                input_features = list(X.columns)

                # Aynı feature set'i var mı?
                input_set = set(input_features)
                model_set = set(self.feature_names)

                missing_features = [f for f in self.feature_names if f not in input_set]
                extra_features = [f for f in input_features if f not in model_set]

                if missing_features or extra_features:
                    # Mismatch ciddiyet kontrolü
                    total_expected = len(self.feature_names)
                    mismatch_count = len(missing_features) + len(extra_features)
                    mismatch_ratio = mismatch_count / max(total_expected, 1)

                    if mismatch_ratio > 0.5:
                        # %50'den fazla feature farklı — sonuçlar güvenilir değil
                        logger.error(
                            f"[Predict Alignment] CRITICAL feature mismatch! "
                            f"{mismatch_count}/{total_expected} features differ ({mismatch_ratio:.0%}). "
                            f"Missing: {missing_features} | Extra: {extra_features}. "
                            f"Results may be unreliable — model may need retraining."
                        )
                    elif mismatch_ratio > 0.2:
                        logger.warning(
                            f"[Predict Alignment] Significant feature mismatch: "
                            f"{mismatch_count}/{total_expected} features differ ({mismatch_ratio:.0%}). "
                            f"Missing: {missing_features} | Extra: {extra_features}."
                        )
                    else:
                        logger.warning(
                            f"[Predict Alignment] Minor feature mismatch: "
                            f"Missing: {missing_features or 'none'} | Extra: {extra_features or 'none'}. "
                            f"Aligning input to match model's feature set."
                        )

                    # Eksik feature'ları 0.0 ile ekle
                    for feat in missing_features:
                        X[feat] = 0.0
                    # Fazla feature'ları kaldır
                    if extra_features:
                        X = X.drop(columns=extra_features)
                    # NOT: self.feature_names'i DEĞİŞTİRME — model state predict sırasında
                    # mutate edilmemeli. Train sırasında kaydedilen feature_names korunmalı.

                # Sadece sıra farklıysa reorder et
                # 1) Column presence check (en kritik guard)
                # NOT: Ensemble mode'da self.model None olabilir

                if self.model is not None and hasattr(self.model, 'feature_names_in_'):
                    missing = set(self.model.feature_names_in_) - set(X.columns)
                    if missing:
                        logger.warning(
                            f"[Predict Alignment] Adding {len(missing)} missing features for sklearn model: {missing}"
                        )
                        for col in missing:
                            X[col] = 0.0
                elif self.incremental_models:
                    # Ensemble mode - ilk modeli kontrol et
                    first_model = self.incremental_models[0]
                    if hasattr(first_model, 'feature_names_in_'):
                        missing = set(first_model.feature_names_in_) - set(X.columns)
                        if missing:
                            logger.warning(
                                f"[Predict Alignment] Adding {len(missing)} missing features for ensemble model: {missing}"
                            )
                            for col in missing:
                                X[col] = 0.0

                # 2) Training feature order vs input order mismatch
                input_features = list(X.columns)
                if input_features != self.feature_names:
                    logger.warning(
                        "Feature names order mismatch. Reordering input columns "
                        "to match training feature order."
                    )
                    X = X[self.feature_names]

                # 3) ZORUNLU sklearn hizalaması (kesin sıra)
                # NOT: Ensemble mode'da self.model None olabilir, bu durumda skip et
                if self.model is not None and hasattr(self.model, "feature_names_in_"):
                    logger.debug(
                        f"Applying sklearn feature_names_in_ ordering "
                        f"({len(self.model.feature_names_in_)} features)"
                    )
                    X = X[self.model.feature_names_in_]
                elif self.incremental_models:
                    # Ensemble mode - ilk modelin feature order'ını kullan
                    first_model = self.incremental_models[0]
                    if hasattr(first_model, "feature_names_in_"):
                        logger.debug(f"Using first ensemble model's feature order")
                        X = X[first_model.feature_names_in_]
            
            # Incremental ensemble varsa onu kullan (_ensemble_mode flag veya models varlığı)
            if (self._ensemble_mode or self.incremental_models) and self.incremental_config['enabled']:
                predictions, anomaly_scores = self.predict_ensemble(X)
            else:
                # Legacy single model prediction

                # Safety: self.model None ise (legacy sentinel) ensemble'dan recover et
                if self.model is None:
                    if self.incremental_models:
                        self.model = self.incremental_models[-1]
                        logger.warning(
                            "predict(): self.model was None in single-model path. "
                            f"Recovered from last ensemble model (ensemble size: {len(self.incremental_models)})"
                        )
                    else:
                        raise ValueError(
                            "Cannot predict: self.model is None and no ensemble models available. "
                            "Model may not have been trained or loaded correctly."
                        )

                # === FIX: APPLY SCALING FOR PREDICTION ===
                X_prediction = X

                if self.is_scaler_fitted:
                    logger.debug("Applying scaler transform for single model prediction")
                    X_scaled_np = self.scaler.transform(X)
                    # DataFrame yapısını koru
                    X_prediction = pd.DataFrame(X_scaled_np, columns=X.columns)
                # ========================================

                predictions = self.model.predict(X_prediction)
                anomaly_scores = self.model.score_samples(X_prediction)
            
            # Ensemble mode: Critical rules override
            if self.ensemble_config.get('enabled', True) and df is not None:
                predictions, anomaly_scores = self._apply_critical_rules(
                    predictions, anomaly_scores, X, df
                )
            
            n_anomalies = (predictions == -1).sum()
            anomaly_rate = n_anomalies / len(predictions) * 100
            
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
                            
                            
                            
                except Exception as e:
                    logger.warning(f"Error applying rule {rule_name}: {e}")
        
        self.rule_stats['total_overrides'] += rule_overrides
        
        
        return ensemble_predictions, ensemble_scores
        
    def _extract_anomaly_message(self, df: pd.DataFrame, idx: int) -> str:
        """
        Anomali satırından insan-okunabilir mesaj çıkar.
        Alt sınıflar override edebilir (ör. MSSQL raw_message kullanır).

        Args:
            df: Enriched DataFrame
            idx: Satır index'i

        Returns:
            Mesaj string'i
        """
        log_entry_dict = df.iloc[idx].to_dict()
        full_message = extract_mongodb_message(log_entry_dict)

        # Fallback: extract_mongodb_message boş dönerse raw_log/msg kullan
        if not full_message or full_message in ['No detailed message available', 'Message extraction failed']:
            if 'raw_log' in df.columns and pd.notna(df.iloc[idx]['raw_log']):
                full_message = str(df.iloc[idx]['raw_log'])
            elif 'msg' in df.columns and pd.notna(df.iloc[idx]['msg']):
                full_message = str(df.iloc[idx]['msg'])
            else:
                full_message = "No message available"

        return full_message

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
        
        
        analysis = {
            "summary": {
                "total_logs": len(predictions),
                "n_anomalies": int(anomaly_mask.sum()),
                "anomaly_rate": float(anomaly_mask.mean() * 100),
                "score_range": {
                    "min": float(anomaly_scores.min()),
                    "max": float(anomaly_scores.max()),
                    "mean": float(anomaly_scores.mean())
                },
                "alert_budget": {
                    "contamination_used": self.training_stats.get('contamination_used',
                                                                   self.model_config['parameters'].get('contamination', 0.05)),
                    "raw_anomaly_count": int(anomaly_mask.sum()),
                    "raw_anomaly_rate_pct": round(float(anomaly_mask.mean() * 100), 3),
                    "description": "Raw ML output before false positive filtering. "
                                   "Use anomaly_rate after filtering for operational SLO."
                }
            },
            "temporal_analysis": {},
            "critical_anomalies": []
        }
        
        # Temporal analiz
        if 'hour_of_day' in X.columns:
            
            anomaly_hours = df[anomaly_mask]['hour_of_day'].value_counts().sort_index()
            analysis["temporal_analysis"]["hourly_distribution"] = {
                int(hour): int(count) for hour, count in anomaly_hours.items()
            }
            analysis["temporal_analysis"]["peak_hours"] = list(anomaly_hours.nlargest(3).index.astype(int))
            logger.debug(f"Temporal analysis completed - Peak hours: {analysis['temporal_analysis']['peak_hours']}")
        
        
        # En kritik anomaliler - SEVERITY SKORUNA GÖRE SIRALA
        

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
            
            # Mesaj çıkarma (override edilebilir — MSSQL raw_message kullanır)
            full_message = self._extract_anomaly_message(df, idx)
            
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
                "message_fingerprint": str(df.iloc[idx]['message_fingerprint']) if 'message_fingerprint' in df.columns else None,
                "severity_factors": None  # Frontend'de gösterme
            })

        # Severity skoruna göre sırala ve top 20'yi al
        anomaly_severities.sort(key=lambda x: x['severity_score'], reverse=True)
        
        
        
        
        # YENİ: İki aşamalı akıllı filtreleme
        # Config'den false positive filter threshold'ları oku (fallback: hardcoded defaults)
        fp_config = self.config.get('anomaly_detection', {}).get('false_positive_filter', {})
        stage1_min_score = fp_config.get('severity_min_score_stage1', 40)
        max_critical_stage1 = fp_config.get('max_critical_anomalies_stage1', 500)

        # 1. Aşama: Yüksek severity score veya kritik tip
        critical_only = []
        for a in anomaly_severities:
            # Kritik tipler her zaman dahil edilir
            is_critical_type = False
            if a.get('message'):
                msg_lower = a['message'].lower()
                is_critical_type = any([
                    'drop' in msg_lower and ('collection' in msg_lower or 'index' in msg_lower),
                    'authentication failed' in msg_lower,
                    'fatal' in msg_lower,
                    'out of memory' in msg_lower,
                    'oom' in msg_lower,
                    'assertion' in msg_lower,
                    'shutdown' in msg_lower
                ])
            
            # Severity score threshold veya kritik tip ise ekle
            if a['severity_score'] > stage1_min_score or is_critical_type:
                critical_only.append(a)



        # 2. Aşama: Maximum limit uygula
        if len(critical_only) > max_critical_stage1:
            
            critical_only = critical_only[:max_critical_stage1]

        

        # Kritik anomalileri göster
        analysis["critical_anomalies"] = critical_only

        # Tüm anomalileri de sakla (UI'da kritik yoksa bunları göstermek için)
        analysis["all_anomalies"] = anomaly_severities

        logger.debug(f"Critical anomalies assigned to analysis: {len(critical_only)}")
        logger.debug(f"All anomalies (including non-critical): {len(anomaly_severities)}")
        
        
        
        
        

        # Severity distribution ekle
        severity_dist = {
            "CRITICAL": sum(1 for a in anomaly_severities if a['severity_level'] == 'CRITICAL'),
            "HIGH": sum(1 for a in anomaly_severities if a['severity_level'] == 'HIGH'),
            "MEDIUM": sum(1 for a in anomaly_severities if a['severity_level'] == 'MEDIUM'),
            "LOW": sum(1 for a in anomaly_severities if a['severity_level'] == 'LOW'),
            "INFO": sum(1 for a in anomaly_severities if a['severity_level'] == 'INFO')
        }
        analysis["severity_distribution"] = severity_dist

        logger.debug(f"Severity analysis completed - Distribution: {severity_dist}")
        
        # Performance critical logs analysis
        
        performance_alerts = {}
        
        # COLLSCAN analysis
        if 'is_collscan' in X.columns:
            collscan_mask = (df['is_collscan'] == 1) & anomaly_mask
            if collscan_mask.sum() > 0:
                logger.debug(f"PERFORMANCE ALERT: {collscan_mask.sum()} COLLSCAN queries in anomalies!")
                
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
                logger.debug(f"PERFORMANCE ALERT: {slow_mask.sum()} slow queries in anomalies!")
                
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
                logger.debug(f"INDEX ALERT: {index_mask.sum()} index builds in anomalies!")
                performance_alerts["index_builds"] = {
                    "count": int(index_mask.sum()),
                    "indices": list(np.where(index_mask)[0][:10])
                }
        
        # High document scan analysis
        if 'is_high_doc_scan' in X.columns:
            high_scan_mask = (df['is_high_doc_scan'] == 1) & anomaly_mask
            if high_scan_mask.sum() > 0:
                logger.debug(f"SCAN ALERT: {high_scan_mask.sum()} high document scans in anomalies!")
                performance_alerts["high_doc_scans"] = {
                    "count": int(high_scan_mask.sum()),
                    "indices": list(np.where(high_scan_mask)[0][:10])
                }
        
        # Add performance alerts to analysis
        if performance_alerts:
            analysis["performance_alerts"] = performance_alerts
            logger.debug(f"Performance analysis completed - {len(performance_alerts)} alert types found")
            
        
        # Shutdown detection
        if 'is_shutdown' in X.columns:
            shutdown_mask = (df['is_shutdown'] == 1) & anomaly_mask
            if shutdown_mask.sum() > 0:
                logger.debug(f"CRITICAL: {shutdown_mask.sum()} shutdown events in anomalies!")
                security_alerts["shutdowns"] = {
                    "count": int(shutdown_mask.sum()),
                    "indices": list(np.where(shutdown_mask)[0][:10])
                }
        
        # Assertion errors
        if 'is_assertion' in X.columns:
            assertion_mask = (df['is_assertion'] == 1) & anomaly_mask
            if assertion_mask.sum() > 0:
                logger.debug(f"ERROR ALERT: {assertion_mask.sum()} assertion errors in anomalies!")
                security_alerts["assertions"] = {
                    "count": int(assertion_mask.sum()),
                    "indices": list(np.where(assertion_mask)[0][:10])
                }
        
        # Fatal errors
        if 'is_fatal' in X.columns:
            fatal_mask = (df['is_fatal'] == 1) & anomaly_mask
            if fatal_mask.sum() > 0:
                logger.debug(f"FATAL ALERT: {fatal_mask.sum()} fatal errors in anomalies!")
                security_alerts["fatal_errors"] = {
                    "count": int(fatal_mask.sum()),
                    "indices": list(np.where(fatal_mask)[0][:10])
                }

        # Out of Memory errors
        if 'is_out_of_memory' in X.columns:
            oom_mask = (df['is_out_of_memory'] == 1) & anomaly_mask
            if oom_mask.sum() > 0:
                logger.debug(f"MEMORY ALERT: {oom_mask.sum()} Out of Memory errors in anomalies!")
                security_alerts["out_of_memory"] = {
                    "count": int(oom_mask.sum()),
                    "indices": list(np.where(oom_mask)[0][:10])
                }

        # Restart events
        if 'is_restart' in X.columns:
            restart_mask = (df['is_restart'] == 1) & anomaly_mask
            if restart_mask.sum() > 0:
                logger.debug(f"RESTART ALERT: {restart_mask.sum()} restart events in anomalies!")
                security_alerts["restarts"] = {
                    "count": int(restart_mask.sum()),
                    "indices": list(np.where(restart_mask)[0][:10])
                }

        # Memory limit exceeded
        if 'is_memory_limit' in X.columns:
            mem_limit_mask = (df['is_memory_limit'] == 1) & anomaly_mask
            if mem_limit_mask.sum() > 0:
                logger.debug(f"MEMORY LIMIT ALERT: {mem_limit_mask.sum()} memory limit exceeded errors in anomalies!")
                security_alerts["memory_limits"] = {
                    "count": int(mem_limit_mask.sum()),
                    "indices": list(np.where(mem_limit_mask)[0][:10])
                }

        # Add security alerts to analysis
        if security_alerts:
            analysis["security_alerts"] = security_alerts
            logger.debug(f"Security analysis completed - {len(security_alerts)} alert types found")

        # Ensemble stats'i summary içine ekle (frontend buradan alıyor)
        if self.ensemble_config:
            analysis['summary']['ensemble_stats'] = {
                'total_rule_overrides': self.rule_stats['total_overrides'],
                'rules_active': len(self.critical_rules),
                'ensemble_method': 'override',
                'rule_hits': dict(self.rule_stats['rule_hits'])
            }
            logger.debug("Ensemble stats added to summary")

        logger.debug(f"Anomaly analysis completed")
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
            'TXN': 15,       # Transaction önemli (YENİ)
            '-': 5           # Diğer
        }
        
        component = df_row.get('c', '-')
        comp_score = component_scores.get(component, 5)
        severity_score += comp_score
        factors.append(f"Component ({component}): +{comp_score}")

        # 3. Critical Features (birikimli puanlama — birden fazla kural eşleşebilir)
        # NOT: elif yerine if kullanılıyor, böylece hem slow_query hem collscan
        # hem yüksek docs_examined olan bir log tüm puanları birikimli toplar.
        # Toplam severity_score zaten min(100, ...) ile cap'leniyor.

        feature_score = 0

        # === PROD LOG OPTIMIZASYONU (BİRİKİMLİ PUANLAMA) ===

        # 1. Massive Scan (>1.5M docs) - Sunucu Kilitleyici
        if row_features.get('docs_examined_count', 0) > 1500000:
            feature_score += 40
            factors.append("Massive Scan (>1.5M): +40")

        # 2. Fatal errors
        if row_features.get('is_fatal', 0) == 1:
            feature_score += 30
            factors.append("Fatal Error: +30")

        # 3. Replication issues - Veri güvenliği
        if row_features.get('is_replication_issue', 0) == 1:
            feature_score += 35
            factors.append("Replication Issue: +35")

        # 4. Long Transaction (>5s) - Locking Risk
        if (row_features.get('is_long_transaction', 0) == 1 and
              row_features.get('query_duration_ms', 0) > 5000):
            feature_score += 30
            factors.append("Long Transaction (>5s): +30")

        # 5. Out of memory
        if row_features.get('is_out_of_memory', 0) == 1:
            feature_score += 28
            factors.append("Out of Memory: +28")

        # 6. Memory limit / Eviction
        if row_features.get('is_memory_limit', 0) == 1:
            feature_score += 25
            factors.append("Memory Limit: +25")

        # 7. Shutdown / Restart
        if row_features.get('is_shutdown', 0) == 1 or row_features.get('is_restart', 0) == 1:
            feature_score += 25
            factors.append("System Restart/Shutdown: +25")

        # 8. Drop operation
        if row_features.get('is_drop_operation', 0) == 1:
            feature_score += 25
            factors.append("DROP Operation: +25")

        # 9. Inefficient Index (High Key Scan)
        if row_features.get('keys_examined_count', 0) > 50000:
            feature_score += 15
            factors.append("High Key Scan (>50k): +15")

        # 10. COLLSCAN (Ağır vs Hafif)
        if row_features.get('is_collscan', 0) == 1:
            if row_features.get('docs_examined_count', 0) > 100000:
                feature_score += 20
                factors.append("Heavy COLLSCAN: +20")
            else:
                feature_score += 12
                factors.append("COLLSCAN: +12")

        # 11. Assertion failure
        if row_features.get('is_assertion', 0) == 1:
            feature_score += 22
            factors.append("Assertion Failure: +22")

        # 12. Regular slow query
        if row_features.get('is_slow_query', 0) == 1:
            feature_score += 8
            factors.append("Slow Query: +8")

        # Feature score cap — MSSQL/ES ile tutarlı (0-40 skalası)
        feature_score = min(feature_score, 40)

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
        
    def save_model(self, path: str = None, server_name: str = None) -> str:
        """
        Modeli kaydet (sunucu bazlı)
        
        Args:
            path: Model dosya yolu (None ise config'den al)
            server_name: Sunucu adı (None ise global model)
            
        Returns:
            Kaydedilen dosya yolu
        """
        if not self.is_trained:
            raise ValueError("Model is not trained yet!")
        
        with self.__class__._model_io_lock:  # Küresel kilit
            # Sunucu bazlı dosya adı oluştur
            if path is None:
                if server_name:
                    # Sunucu adını normalize et (özel karakterleri temizle)
                    safe_server_name = server_name.replace('.', '_').replace('/', '_')
                    path = f'models/isolation_forest_{safe_server_name}.pkl'
                    
                else:
                    path = self.output_config.get('model_path', 'models/isolation_forest.pkl')
            
            try:
                
                # Klasörü oluştur
                Path(path).parent.mkdir(parents=True, exist_ok=True)
                
                # Model ve metadata'yı kaydet
                # Ensemble mode kontrolü: flag veya incremental_models varlığı
                is_ensemble_mode = self._ensemble_mode or (
                    bool(self.incremental_models) and self.incremental_config.get('enabled', True))

                # Safety: self.model None ise (legacy sentinel) ensemble'dan recover et
                if self.model is None and self.incremental_models:
                    self.model = self.incremental_models[-1]
                    logger.warning(
                        f"save_model: self.model was None. Recovered from last ensemble model "
                        f"before saving (ensemble size: {len(self.incremental_models)})"
                    )
                elif self.model is None:
                    logger.warning(
                        "save_model: self.model is None and no ensemble models available. "
                        "Saving None model to disk - next load will need retraining."
                    )

                model_data = {
                    'model': self.model,
                    'feature_names': self.feature_names,
                    # === FIX: SAVE SCALER STATE ===
                    'scaler': self.scaler,
                    'is_scaler_fitted': self.is_scaler_fitted,
                    # ==============================
                    'training_stats': self.training_stats,
                    'config': self.config,
                    'server_name': server_name,  # Sunucu bilgisi
                    # Online Learning - Historical Buffer
                    'historical_data': self.historical_data if self.online_learning_config.get('enabled', True) else None,
                    'online_learning_config': self.online_learning_config,
                    # Version tracking: config kontrollü, default 2.0
                    'model_version': self.model_version,
                    'is_ensemble_mode': is_ensemble_mode,
                    'incremental_models': list(self.incremental_models) if is_ensemble_mode else [],
                    'model_weights': self.model_weights.copy() if is_ensemble_mode else [],
                    'model_metadata': self.model_metadata.copy() if is_ensemble_mode else [],
                    'model_scalers': list(self.model_scalers) if is_ensemble_mode else [],
                    'incremental_config': self.incremental_config,
                    # Ensemble rule stats (persistent across restarts)
                    'rule_stats': {
                        'total_overrides': self.rule_stats['total_overrides'],
                        'rule_hits': dict(self.rule_stats['rule_hits'])
                    }
                }

                # Historical buffer save kontrolü
                if self.historical_data['features'] is not None:
                    buffer_size_mb = self.historical_data['features'].memory_usage(deep=True).sum() / 1024 / 1024
                    buffer_samples = len(self.historical_data['features'])
                    logger.info(f"💾 Saving historical buffer: {buffer_samples} samples, {buffer_size_mb:.2f} MB")
                    
                    # Büyük dosya uyarısı
                    if buffer_size_mb > 500:
                        logger.warning(f"Large model file warning: Historical buffer is {buffer_size_mb:.2f} MB")
                else:
                    logger.warning(f"⚠️ Historical buffer is EMPTY - no features to save!")
                
                # Kaydedilecek veriyi logla
                logger.info(f"📦 Model data to save:")
                logger.info(f"   - model: {type(model_data.get('model'))}")
                logger.info(f"   - feature_names: {len(model_data.get('feature_names', [])) if model_data.get('feature_names') else 0} features")
                logger.info(f"   - historical_data: {'Present' if model_data.get('historical_data') else 'None'}")
                if model_data.get('historical_data') and model_data['historical_data'].get('features') is not None:
                    logger.info(f"   - historical_data.features: {len(model_data['historical_data']['features'])} rows")
                    logger.info(f"   - historical_data.metadata: {model_data['historical_data'].get('metadata', {})}")
                logger.info(f"   - model_version: {model_data.get('model_version')}")
                logger.info(f"   - server_name: {model_data.get('server_name')}")

                joblib.dump(model_data, path)

                # Dosya boyutu bilgisi
                file_size_mb = Path(path).stat().st_size / 1024 / 1024

                # Historical buffer backup (ayrı dosya, pkl bozulursa kurtarma)
                self._backup_historical_buffer(path)

                logger.info(f"Model saved to: {path}")

                return path
                
            except Exception as e:
                logger.error(f"Error saving model: {e}", exc_info=True)
                raise
            
    def load_model(self, path: str = None, server_name: str = None) -> bool:
        """
        Modeli yükle (sunucu bazlı)
        
        Args:
            path: Model dosya yolu (None ise config'den al)
            server_name: Sunucu adı (None ise global model)
            
        Returns:
            Başarılı olup olmadığı
        """
        with self.__class__._model_io_lock:  # Küresel kilit
            # Sunucu bazlı dosya yolu oluştur
            if path is None:
                if server_name:
                    # Sunucu adını normalize et (özel karakterleri temizle)
                    safe_server_name = server_name.replace('.', '_').replace('/', '_')
                    path = f'models/isolation_forest_{safe_server_name}.pkl'
                else:
                    # Server name yoksa global model kullan
                    path = self.output_config.get('model_path', 'models/isolation_forest.pkl')
                
                # Eğer sunucuya özel model yoksa, global modeli dene
                if not Path(path).exists():
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

                # === FIX: LOAD SCALER STATE ===
                if 'scaler' in model_data:
                    self.scaler = model_data['scaler']
                    self.is_scaler_fitted = model_data.get('is_scaler_fitted', True)
                    logger.debug("Scaler state loaded successfully.")
                else:
                    logger.warning("No scaler found in model file. Using un-fitted scaler (legacy model).")
                    self.is_scaler_fitted = False
                # ==============================

                # === FEATURE NAME ALIGNMENT STABILIZER ===
                if hasattr(self.model, "feature_names_in_"):
                    # sklearn modelinin kendi garantili feature sırasını kullan
                    self.feature_names = list(self.model.feature_names_in_)
                elif not self.feature_names:
                    # Eski model / eksik metadata → predict() ilk X ile dolduracak
                    logger.warning("Loaded model has no feature_names. Will set on first prediction.")
                
                # YENİ: Server bilgisini kontrol et ve güncelle
                loaded_server = model_data.get('server_name', None)
                if server_name and loaded_server and loaded_server.lower() != server_name.lower():
                    logger.warning(f"Model was trained for server '{loaded_server}' but loading for '{server_name}'")
                
                # Current server'ı güncelle
                self.current_server = server_name or loaded_server
                
                # Server metadata'yı güncelle
                if self.current_server:
                    self.server_models[self.current_server] = {
                        'model_path': path,
                        'last_update': datetime.now(),
                        'sample_count': self.training_stats.get('n_samples', 0)
                    }
                    
                
                # Online Learning - Historical Buffer'ı yükle
                model_version = model_data.get('model_version')

                if model_version is None:
                    # Eğer eski model dosyasıysa - kesin olarak legacy işaretle
                    model_version = "legacy-1.x"
                    logger.warning("Loaded model has no version info. Marked as legacy model.")
                else:
                    # String or numeric → normalize to string
                    model_version = str(model_version).strip()

                # Runtime state
                self.loaded_model_version = model_version
                self.training_stats["model_version"] = model_version

                logger.info(f"Loaded model version: {model_version}")

                # ── Historical buffer yükleme: yapısal doğrulama ──
                # model_version'a bağımlı DEĞİL.  Buffer'ın pkl içinde
                # gerçekten var olup olmadığına ve yapısal bütünlüğüne bakılır.
                # Bu sayede hem v1.0 hem v2.x buffer'ları güvenle yüklenir.
                loaded_hist = model_data.get('historical_data')

                logger.info(f"📂 Loading historical buffer check:")
                logger.info(f"   - model_version: {model_version}")
                logger.info(f"   - 'historical_data' in model_data: {'historical_data' in model_data}")
                logger.info(f"   - historical_data is dict: {isinstance(loaded_hist, dict)}")

                buffer_loaded = False
                if isinstance(loaded_hist, dict) and loaded_hist.get('features') is not None:
                    # Yapısal bütünlük kontrolü: metadata dict olmalı
                    if isinstance(loaded_hist.get('metadata'), dict):
                        logger.info(f"   ✅ historical_data found in model file")
                        logger.info(f"   - features type: {type(loaded_hist['features'])}")
                        logger.info(f"   - metadata: {loaded_hist['metadata']}")
                        if hasattr(loaded_hist['features'], 'shape'):
                            logger.info(f"   - features shape: {loaded_hist['features'].shape}")
                        if hasattr(loaded_hist['features'], 'memory_usage'):
                            buffer_size_mb = loaded_hist['features'].memory_usage(deep=True).sum() / 1024 / 1024
                            logger.info(f"   - features size: {buffer_size_mb:.2f} MB")

                        self.historical_data = loaded_hist
                        # buffer_version yoksa veya eski ise normalize et
                        self.historical_data['metadata'].setdefault('buffer_version', 1.0)
                        logger.info(f"   ✅ Historical buffer loaded: {self.historical_data['metadata'].get('total_samples', 'N/A')} samples (buffer_version={self.historical_data['metadata']['buffer_version']})")
                        buffer_loaded = True
                    else:
                        logger.warning(f"   ⚠️ historical_data.metadata is not a dict — skipping buffer")

                if not buffer_loaded:
                    reason = "not present" if loaded_hist is None else (
                        "features is None" if isinstance(loaded_hist, dict) else "not a dict"
                    )
                    logger.warning(f"   ⚠️ Historical buffer not loaded ({reason}) — trying backup restore...")

                    # Backup'tan kurtarmayı dene
                    if self.restore_historical_buffer_from_backup(path):
                        logger.info("   ✅ Historical buffer recovered from backup file")
                    else:
                        logger.warning("   ⚠️ No backup available — initializing empty buffer")
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

                is_ensemble_mode = model_data.get('is_ensemble_mode', False)
                self._ensemble_mode = is_ensemble_mode

                if is_ensemble_mode:
                    # Ensemble modelleri yükle (list -> deque dönüşümü)
                    loaded_models = model_data.get('incremental_models', [])
                    if loaded_models:
                        # Mevcut deque'i temizle ve yeni modelleri ekle
                        self.incremental_models.clear()
                        for m in loaded_models:
                            self.incremental_models.append(m)
                        
                        # Weights ve metadata yükle
                        self.model_weights = model_data.get('model_weights', [1.0] * len(loaded_models))
                        self.model_metadata = model_data.get('model_metadata', [])

                        # Per-model scaler'ları yükle (backward compatible: eski dosyalarda yoksa boş)
                        loaded_scalers = model_data.get('model_scalers', [])
                        self.model_scalers.clear()
                        for s in loaded_scalers:
                            self.model_scalers.append(s)
                        if loaded_scalers:
                            logger.info(f"   Per-model scalers loaded: {len(loaded_scalers)}")
                        else:
                            logger.debug("   No per-model scalers in file (legacy model) — will use global scaler fallback")

                        # Incremental config güncelle
                        if 'incremental_config' in model_data:
                            self.incremental_config.update(model_data['incremental_config'])

                        logger.info(f"✅ Ensemble models loaded: {len(self.incremental_models)} models")
                        logger.debug(f"   Model weights: {self.model_weights}")
                    else:
                        logger.warning("is_ensemble_mode=True but no incremental_models found in file")
                else:
                    # Ensemble mode değil - incremental_models boş kalacak
                    logger.debug("Single model mode - no ensemble to load")

                # FIX: Ensemble mode'dan kaydedilen model None olabilir.
                # Ensemble models yüklendiyse, son ensemble model'i ana model olarak ata.
                if self.model is None and self.incremental_models:
                    self.model = self.incremental_models[-1]
                    logger.warning(
                        f"Loaded model was None (ensemble-mode save). "
                        f"Recovered main model from last ensemble model. "
                        f"Ensemble size: {len(self.incremental_models)}"
                    )

                # Online learning config'i güncelle
                if 'online_learning_config' in model_data:
                    self.online_learning_config.update(model_data['online_learning_config'])

                # Rule stats'ı geri yükle (persistent across restarts)
                saved_rule_stats = model_data.get('rule_stats')
                if isinstance(saved_rule_stats, dict):
                    self.rule_stats['total_overrides'] = saved_rule_stats.get('total_overrides', 0)
                    saved_hits = saved_rule_stats.get('rule_hits', {})
                    if isinstance(saved_hits, dict):
                        self.rule_stats['rule_hits'] = dict(saved_hits)
                    logger.info(f"Rule stats restored: {self.rule_stats['total_overrides']} total overrides, "
                                f"{len(self.rule_stats['rule_hits'])} rule types")

                self.is_trained = True

                logger.info(f"Model loaded from: {path}")

                return True
            except Exception as e:
                logger.error(f"Error loading model: {e}", exc_info=True)
                # Reset to safe state on load failure
                self.is_trained = False
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
            logger.debug(f"Clearing historical buffer...")
            
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
            
            
            logger.info("Historical buffer cleared")
            return True
            
        except Exception as e:
            logger.debug(f"Error clearing historical buffer: {e}")
            logger.error(f"Error clearing historical buffer: {e}")
            return False

    def _backup_historical_buffer(self, model_path: str) -> None:
        """
        Historical buffer'ı ayrı dosyaya yedekle.
        Model pkl bozulursa bu backup'tan kurtarılabilir.
        """
        try:
            if self.historical_data['features'] is None:
                return

            backup_path = Path(model_path).with_suffix('.buffer_backup.pkl')
            buffer_data = {
                'historical_data': self.historical_data,
                'rule_stats': {
                    'total_overrides': self.rule_stats['total_overrides'],
                    'rule_hits': dict(self.rule_stats['rule_hits'])
                },
                'backup_timestamp': datetime.now().isoformat(),
                'server_name': self.current_server,
                'buffer_samples': self.historical_data['metadata'].get('total_samples', 0)
            }
            joblib.dump(buffer_data, backup_path, compress=3)
            backup_size_mb = backup_path.stat().st_size / 1024 / 1024
            logger.info(f"Historical buffer backup saved: {backup_path} ({backup_size_mb:.2f} MB)")
        except Exception as e:
            logger.warning(f"Historical buffer backup failed (non-critical): {e}")

    def restore_historical_buffer_from_backup(self, model_path: str) -> bool:
        """
        Backup dosyasından historical buffer'ı geri yükle.
        Model pkl bozulduğunda kullanılır.

        Args:
            model_path: Orijinal model dosyasının yolu

        Returns:
            Başarılı mı
        """
        try:
            backup_path = Path(model_path).with_suffix('.buffer_backup.pkl')
            if not backup_path.exists():
                logger.warning(f"No buffer backup found at {backup_path}")
                return False

            buffer_data = joblib.load(backup_path)
            loaded_hist = buffer_data.get('historical_data')

            if not isinstance(loaded_hist, dict) or loaded_hist.get('features') is None:
                logger.warning("Buffer backup exists but contains no valid data")
                return False

            self.historical_data = loaded_hist
            self.historical_data['metadata'].setdefault('buffer_version', 1.0)

            # Rule stats da backup'tan geri yükle
            saved_rule_stats = buffer_data.get('rule_stats')
            if isinstance(saved_rule_stats, dict):
                self.rule_stats['total_overrides'] = saved_rule_stats.get('total_overrides', 0)
                saved_hits = saved_rule_stats.get('rule_hits', {})
                if isinstance(saved_hits, dict):
                    self.rule_stats['rule_hits'] = dict(saved_hits)

            samples = self.historical_data['metadata'].get('total_samples', 0)
            backup_ts = buffer_data.get('backup_timestamp', 'unknown')
            logger.info(f"Historical buffer restored from backup: {samples} samples "
                        f"(backup from {backup_ts})")
            return True

        except Exception as e:
            logger.error(f"Failed to restore buffer from backup: {e}")
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
                # === FEATURE SAFETY CHECK (NEW) ===
                if hasattr(self.model, "feature_names_in_"):
                    model_set = set(self.model.feature_names_in_)
                    if buffer_features != model_set:
                        missing = model_set - buffer_features
                        extra = buffer_features - model_set
                        if missing:
                            validation_results["warnings"].append(
                                f"Historical buffer missing model features: {missing}"
                            )
                        if extra:
                            validation_results["warnings"].append(
                                f"Buffer contains extra unused features: {extra}"
                            )
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

    def calculate_feature_importance(self, X: pd.DataFrame, n_repeats: int = 10,
                                    sample_size: int = None) -> Dict[str, float]:
        """
        Permutation importance yöntemiyle feature importance hesapla
        
        Args:
            X: Feature matrix
            n_repeats: Permutation tekrar sayısı
            sample_size: Örneklem boyutu (None ise tüm veri kullanılır)
            
        Returns:
            Feature importance skorları
        """
        sys.setrecursionlimit(10000)  # Recursion limitini artır
        
        logger.debug(f"Calculating feature importance for {len(X)} samples...")
        
        if not self.is_trained:
            raise ValueError("Model must be trained before calculating feature importance!")
        
        # Sample size kontrolü (büyük veri setleri için)
        if sample_size and len(X) > sample_size:
            logger.debug(f"Sampling {sample_size} from {len(X)} for importance calculation")
            X_sample = X.sample(n=sample_size, random_state=42)
        else:
            X_sample = X
        
        # Baseline score hesapla
        # (EK) Yerel, recursion-safe skorlayıcı
        def _get_scores(X_like):
            # Ensemble ortalaması
            if hasattr(self, "incremental_models") and getattr(self, "incremental_models"):
                scores = []
                for m in self.incremental_models:
                    try:
                        if hasattr(m, "score_samples"):
                            scores.append(m.score_samples(X_like))
                        elif hasattr(m, "decision_function"):
                            scores.append(m.decision_function(X_like))
                    except RecursionError:
                        # Fallback: decision_function deneyelim
                        if hasattr(m, "decision_function"):
                            scores.append(m.decision_function(X_like))
                        else:
                            raise
                if scores:
                    import numpy as np
                    return np.mean(scores, axis=0)
            # Tekil model
            try:
                if hasattr(self.model, "score_samples"):
                    return self.model.score_samples(X_like)
                if hasattr(self.model, "decision_function"):
                    return self.model.decision_function(X_like)
            except RecursionError:
                if hasattr(self.model, "decision_function"):
                    return self.model.decision_function(X_like)
                raise
            raise RuntimeError("No available scorer for feature importance")

        # Baseline score hesapla
        baseline_scores = _get_scores(X_sample)
        baseline_score = baseline_scores.mean()
        
        feature_importance = {}
        
        # Her feature için permutation importance
        for feature in X_sample.columns:
            
            
            importance_scores = []
            for _ in range(n_repeats):
                # Feature'ı karıştır
                X_permuted = X_sample.copy()
                X_permuted[feature] = np.random.permutation(X_permuted[feature].values)
                
                # Yeni score hesapla
                permuted_scores = _get_scores(X_permuted)
                permuted_score = permuted_scores.mean()
                
                # Importance = baseline - permuted (düşüş ne kadar fazlaysa o kadar önemli)
                importance = baseline_score - permuted_score
                importance_scores.append(importance)
            
            # Ortalama importance
            feature_importance[feature] = np.mean(importance_scores)
        
        # Normalize et (0-1 arası)
        max_importance = max(feature_importance.values())
        if max_importance > 0:
            for feature in feature_importance:
                feature_importance[feature] = feature_importance[feature] / max_importance
        
        # Sırala (en önemliden en önemsize)
        feature_importance = dict(sorted(feature_importance.items(), 
                                       key=lambda x: x[1], reverse=True))
        
        
        
        
        return feature_importance
    
    def detect_dead_features(self, importance_scores: Dict[str, float], 
                            threshold: float = 0.01) -> Tuple[List[str], List[str]]:
        """
        Etkisiz ve düşük etkili feature'ları tespit et
        
        Args:
            importance_scores: Feature importance skorları
            threshold: Minimum importance threshold
            
        Returns:
            (dead_features, low_impact_features) tuple'ı
        """
        
        
        dead_features = []
        low_impact_features = []
        
        for feature, score in importance_scores.items():
            if score < threshold:
                dead_features.append(feature)
                
            elif score < threshold * 5:  # Low impact threshold
                low_impact_features.append(feature)
                
        
        
        
        
        return dead_features, low_impact_features
    
    def optimize_feature_selection(self, X: pd.DataFrame, method: str = 'importance',
                                  top_n: int = 20, save_config: bool = False) -> Dict[str, Any]:
        """
        Feature optimization analizi ve önerileri
        
        Args:
            X: Feature matrix
            method: 'importance' veya 'correlation'
            top_n: Seçilecek feature sayısı
            save_config: Optimized config'i kaydet
            
        Returns:
            Optimization sonuçları ve önerileri
        """
        
        
        results = {
            "current_features": list(X.columns),
            "current_feature_count": len(X.columns),
            "optimization_method": method,
            "recommendations": {}
        }
        
        # Feature importance hesapla
        
        importance_scores = self.calculate_feature_importance(X, sample_size=min(5000, len(X)))
        results["feature_importance"] = importance_scores
        
        # Dead features tespit et
        
        dead_features, low_impact_features = self.detect_dead_features(importance_scores)
        results["dead_features"] = dead_features
        results["low_impact_features"] = low_impact_features
        
        # Correlation analizi
        
        correlation_matrix = X.corr()
        
        # Yüksek korelasyonlu feature çiftlerini bul
        high_corr_pairs = []
        for i in range(len(correlation_matrix.columns)):
            for j in range(i+1, len(correlation_matrix.columns)):
                if abs(correlation_matrix.iloc[i, j]) > 0.9:
                    feature1 = correlation_matrix.columns[i]
                    feature2 = correlation_matrix.columns[j]
                    corr_value = correlation_matrix.iloc[i, j]
                    high_corr_pairs.append((feature1, feature2, corr_value))
                    
        
        results["high_correlation_pairs"] = high_corr_pairs
        
        # Top N feature önerisi
        
        top_features = list(importance_scores.keys())[:top_n]
        
        # Dead features'ı çıkar
        recommended_features = [f for f in top_features if f not in dead_features]
        
        results["recommendations"] = {
            "recommended_features": recommended_features,
            "features_to_remove": dead_features,
            "features_to_review": low_impact_features,
            "expected_reduction": f"{len(dead_features)} features ({len(dead_features)/len(X.columns)*100:.1f}%)"
        }
        
        # Model performans tahmini
        
        
        # Sadece recommended features ile mini test
        X_optimized = X[recommended_features]
        
        # Baseline vs Optimized karşılaştırma için skorlar
        baseline_scores = self.score_samples(X)
        
        # Yeni model eğit (test amaçlı)
        from sklearn.ensemble import IsolationForest
        test_model = IsolationForest(**self.model_config['parameters'])
        test_model.fit(X_optimized)
        optimized_scores = test_model.score_samples(X_optimized)
        
        # Anomaly detection consistency kontrolü
        baseline_anomalies = (baseline_scores < np.percentile(baseline_scores, 2)).sum()
        optimized_anomalies = (optimized_scores < np.percentile(optimized_scores, 2)).sum()
        
        results["performance_comparison"] = {
            "baseline_features": len(X.columns),
            "optimized_features": len(recommended_features),
            "baseline_anomalies": int(baseline_anomalies),
            "optimized_anomalies": int(optimized_anomalies),
            "consistency_rate": f"{min(baseline_anomalies, optimized_anomalies) / max(baseline_anomalies, optimized_anomalies) * 100:.1f}%"
        }
        
        # Özet rapor
        logger.info("========== FEATURE OPTIMIZATION REPORT ==========")
        logger.info(f"Current features: {len(X.columns)}")
        logger.info(f"Dead features found: {len(dead_features)}")
        logger.info(f"Low impact features: {len(low_impact_features)}")
        logger.info(f"High correlation pairs: {len(high_corr_pairs)}")
        logger.info(f"Recommended features: {len(recommended_features)}")
        logger.info(f"Expected reduction: {len(X.columns) - len(recommended_features)} features")
        top_features = list(importance_scores.items())[:10]
        logger.info(f"Top 10 Features: {', '.join(f'{f}:{s:.4f}' for f, s in top_features)}")
        if dead_features:
            logger.info(f"Dead Features to Remove: {', '.join(dead_features[:10])}")
        
        
        # Config güncelleme önerisi
        if save_config:
            config_update = {
                "enabled_features": recommended_features,
                "disabled_features": dead_features,
                "optimization_date": datetime.now().isoformat(),
                "optimization_stats": results["performance_comparison"]
            }
            results["config_update"] = config_update
            
        
        return results

    def create_validation_dataset(self, X: pd.DataFrame, df: pd.DataFrame,
                                 method: str = 'rule_based') -> Tuple[pd.DataFrame, np.ndarray, np.ndarray]:
        """
        Semi-supervised validation dataset oluştur
        Rule engine ve statistical methods kullanarak pseudo-labels oluştur
        
        Args:
            X: Feature matrix
            df: Original dataframe
            method: 'rule_based', 'statistical', or 'combined'
            
        Returns:
            (X_validation, y_validation, confidence_scores): Features, labels, confidence per sample
        """
        
        
        # Başlangıç label'ları (0: normal, 1: anomaly)
        y_validation = np.zeros(len(X))
        confidence_scores = np.zeros(len(X))
        
        # Method 1: Rule-based labeling (yüksek güvenilirlik)
        if method in ['rule_based', 'combined']:
            
            
            # Kritik anomaliler (kesin anomaly)
            critical_conditions = [
                ('is_fatal', 1.0),
                ('is_out_of_memory', 1.0),
                ('is_shutdown', 0.9),
                ('is_drop_operation', 0.85),
                ('is_assertion', 0.8),
                ('is_memory_limit', 0.8)
            ]
            
            for feature, confidence in critical_conditions:
                if feature in X.columns:
                    mask = X[feature] == 1
                    y_validation[mask] = 1
                    confidence_scores[mask] = np.maximum(confidence_scores[mask], confidence)
                    
            
            # Performans anomalileri
            if 'is_collscan' in X.columns and 'docs_examined_count' in X.columns:
                perf_mask = (X['is_collscan'] == 1) & (X['docs_examined_count'] > 100000)
                y_validation[perf_mask] = 1
                confidence_scores[perf_mask] = np.maximum(confidence_scores[perf_mask], 0.75)
                
            
            # Kesin normal patterns (yüksek güvenilirlik)
            normal_conditions = []
            
            # Normal replication operations
            if 'is_normal_replication' in df.columns:
                normal_mask = df['is_normal_replication'] == 1
                y_validation[normal_mask] = 0
                confidence_scores[normal_mask] = 0.95
                
        
        # Method 2: Statistical outliers (orta güvenilirlik)
        if method in ['statistical', 'combined']:
            
            
            # Z-score based outliers for numeric features
            numeric_features = ['query_duration_ms', 'docs_examined_count', 
                              'keys_examined_count', 'performance_score']
            
            for feature in numeric_features:
                if feature in X.columns:
                    values = X[feature].values
                    if len(values[values > 0]) > 10:  # Yeterli veri varsa
                        # Log transform for skewed data
                        log_values = np.log1p(values)
                        z_scores = np.abs((log_values - np.mean(log_values)) / (np.std(log_values) + 1e-10))
                        
                        # Z-score > 3 olanlar anomaly
                        stat_anomalies = z_scores > 3
                        y_validation[stat_anomalies] = 1
                        confidence_scores[stat_anomalies] = np.maximum(
                            confidence_scores[stat_anomalies], 0.6
                        )
                        
        
        # Validation istatistikleri
        n_anomalies = (y_validation == 1).sum()
        n_normal = (y_validation == 0).sum()
        n_confident = (confidence_scores > 0.7).sum()
        
        
        logger.debug(f"  Total samples: {len(y_validation)}")
        
        
        
        
        # Confidence score'a göre filtreleme (opsiyonel)
        high_confidence_mask = confidence_scores > 0.7
        
        return X, y_validation, confidence_scores
    
    def evaluate_model(self, X: pd.DataFrame, y_true: np.ndarray = None, 
                      df: pd.DataFrame = None) -> Dict[str, Any]:
        """
        Model performansını değerlendir
        
        Args:
            X: Feature matrix
            y_true: Gerçek labels (opsiyonel)
            df: Original dataframe (rule-based labeling için)
            
        Returns:
            Evaluation metrikleri
        """
        
        
        if not self.is_trained:
            raise ValueError("Model must be trained before evaluation!")
        
        # Eğer y_true yoksa, validation dataset oluştur
        evaluation_method = "ground_truth"
        evaluation_meta = {}

        if y_true is None:
            if df is None:
                raise ValueError("Either y_true or df must be provided for evaluation!")

            evaluation_method = "pseudo_label"
            X, y_true, confidence = self.create_validation_dataset(X, df, method='combined')

            # Sadece yüksek güvenilirlikli samples'ı kullan
            high_conf_mask = confidence > 0.7
            total_before_filter = len(X)
            X = X[high_conf_mask]
            y_true = y_true[high_conf_mask]
            logger.debug(f"Using {len(X)} high-confidence samples for evaluation")

            evaluation_meta = {
                "confidence_threshold": 0.7,
                "total_samples_before_filter": int(total_before_filter),
                "high_confidence_samples": int(len(X)),
                "high_confidence_ratio": round(len(X) / total_before_filter, 4) if total_before_filter > 0 else 0,
                "disclaimer": "Metrics calculated using pseudo-labels (rule-based + statistical). "
                              "Not equivalent to human-verified ground truth. "
                              "Precision/recall may be inflated due to overlap between "
                              "pseudo-label rules and model's critical rules engine."
            }

        # Model predictions (ensemble or single model)
        # Ensemble path (predict_ensemble) kendi içinde per-model scaler uygular (F1).
        # Single model path için burada global scaler uygulanmalı.
        if (self._ensemble_mode or self.incremental_models) and self.incremental_config['enabled']:
            predictions, anomaly_scores = self.predict_ensemble(X)
        elif self.model is not None:
            X_eval = X
            if self.is_scaler_fitted:
                X_eval = pd.DataFrame(
                    self.scaler.transform(X), columns=X.columns
                )
            predictions = self.model.predict(X_eval)
            anomaly_scores = self.model.score_samples(X_eval)
        else:
            raise ValueError("No model available for evaluation")
        # Isolation Forest -1: anomaly, 1: normal -> 1: anomaly, 0: normal'e çevir
        y_pred = (predictions == -1).astype(int)

        # Metrikleri hesapla
        metrics = self.calculate_metrics(y_true, y_pred, anomaly_scores)

        # Evaluation method metadata ekle
        metrics["evaluation_method"] = evaluation_method
        if evaluation_meta:
            metrics["evaluation_meta"] = evaluation_meta

        return metrics
    
    def calculate_metrics(self, y_true: np.ndarray, y_pred: np.ndarray, 
                         scores: np.ndarray = None) -> Dict[str, Any]:
        """
        Detaylı performans metrikleri hesapla
        
        Args:
            y_true: Gerçek labels (1: anomaly, 0: normal)
            y_pred: Tahminler (1: anomaly, 0: normal)
            scores: Anomaly scores (opsiyonel)
            
        Returns:
            Metrics dictionary
        """
        from sklearn.metrics import (
            confusion_matrix, precision_score, recall_score, 
            f1_score, accuracy_score, roc_auc_score
        )
        
        
        
        # Confusion matrix
        tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()
        
        # Basic metrics
        precision = precision_score(y_true, y_pred, zero_division=0)
        recall = recall_score(y_true, y_pred, zero_division=0)
        f1 = f1_score(y_true, y_pred, zero_division=0)
        accuracy = accuracy_score(y_true, y_pred)
        
        # False positive/negative rates
        fpr = fp / (fp + tn) if (fp + tn) > 0 else 0
        fnr = fn / (fn + tp) if (fn + tp) > 0 else 0
        
        # AUC-ROC (eğer scores varsa)
        auc_roc = None
        if scores is not None and len(np.unique(y_true)) > 1:
            try:
                # Normalize scores to [0, 1]
                scores_normalized = (scores - scores.min()) / (scores.max() - scores.min() + 1e-10)
                # Invert for anomaly (lower score = more anomalous)
                scores_for_roc = 1 - scores_normalized
                auc_roc = roc_auc_score(y_true, scores_for_roc)
            except:
                auc_roc = None
        
        metrics = {
            "confusion_matrix": {
                "true_negatives": int(tn),
                "false_positives": int(fp),
                "false_negatives": int(fn),
                "true_positives": int(tp)
            },
            "precision": float(precision),
            "recall": float(recall),
            "f1_score": float(f1),
            "accuracy": float(accuracy),
            "false_positive_rate": float(fpr),
            "false_negative_rate": float(fnr),
            "auc_roc": float(auc_roc) if auc_roc else None,
            "support": {
                "total": len(y_true),
                "anomalies": int((y_true == 1).sum()),
                "normal": int((y_true == 0).sum())
            }
        }
        
        # Matthews Correlation Coefficient (balanced metric)
        if tp + fp > 0 and tp + fn > 0 and tn + fp > 0 and tn + fn > 0:
            mcc_numerator = (tp * tn) - (fp * fn)
            mcc_denominator = np.sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
            mcc = mcc_numerator / mcc_denominator if mcc_denominator > 0 else 0
            metrics["matthews_correlation"] = float(mcc)
        
        
        
        
        
        
        
        
        return metrics
    
    def generate_evaluation_report(self, X: pd.DataFrame, df: pd.DataFrame, 
                                  save_report: bool = True) -> Dict[str, Any]:
        """
        Kapsamlı model değerlendirme raporu oluştur
        
        Args:
            X: Feature matrix
            df: Original dataframe
            save_report: Raporu JSON olarak kaydet
            
        Returns:
            Evaluation report
        """
        
        
        report = {
            "timestamp": datetime.now().isoformat(),
            "model_info": self.get_model_info(),
            "dataset_info": {
                "total_samples": len(X),
                "features": list(X.columns),
                "feature_count": len(X.columns)
            }
        }
        
        # Model performance metrics
        
        metrics = self.evaluate_model(X, df=df)
        report["performance_metrics"] = metrics
        
        # Feature importance analysis
        
        if len(X) > 10000:
            importance = self.calculate_feature_importance(X, sample_size=5000)
        else:
            importance = self.calculate_feature_importance(X)
        
        report["feature_analysis"] = {
            "top_10_features": dict(list(importance.items())[:10]),
            "dead_features": self.detect_dead_features(importance)[0]
        }
        
        # Rule engine statistics
        
        report["ensemble_statistics"] = {
            "rules_enabled": self.ensemble_config.get('enabled', False),
            "total_overrides": self.rule_stats['total_overrides'],
            "rule_hits": dict(self.rule_stats['rule_hits'])
        }
        
        # Historical buffer stats
        logger.debug(f"Step 4: Gathering historical buffer info...")
        report["online_learning"] = self.get_historical_buffer_info()
        
        # Performance assessment
        precision = metrics["precision"]
        recall = metrics["recall"]
        f1 = metrics["f1_score"]
        fpr = metrics["false_positive_rate"]
        
        if f1 >= 0.8:
            assessment = "EXCELLENT"
            color = "green"
        elif f1 >= 0.6:
            assessment = "GOOD"
            color = "yellow"
        elif f1 >= 0.4:
            assessment = "FAIR"
            color = "orange"
        else:
            assessment = "POOR"
            color = "red"
        
        report["assessment"] = {
            "overall_rating": assessment,
            "rating_color": color,
            "strengths": [],
            "weaknesses": [],
            "recommendations": []
        }
        
        # Strengths and weaknesses
        if precision > 0.8:
            report["assessment"]["strengths"].append(f"High precision ({precision:.2f}) - Low false positives")
        else:
            report["assessment"]["weaknesses"].append(f"Low precision ({precision:.2f}) - Too many false positives")
            
        if recall > 0.8:
            report["assessment"]["strengths"].append(f"High recall ({recall:.2f}) - Catches most anomalies")
        else:
            report["assessment"]["weaknesses"].append(f"Low recall ({recall:.2f}) - Missing many anomalies")
            
        if fpr < 0.1:
            report["assessment"]["strengths"].append(f"Low false positive rate ({fpr:.2f})")
        else:
            report["assessment"]["weaknesses"].append(f"High false positive rate ({fpr:.2f})")
        
        # Recommendations
        if precision < 0.7:
            report["assessment"]["recommendations"].append(
                "Consider adjusting contamination parameter or adding more normal pattern rules"
            )
        if recall < 0.7:
            report["assessment"]["recommendations"].append(
                "Consider lowering contamination parameter or reviewing critical rules"
            )
        if len(report["feature_analysis"]["dead_features"]) > 5:
            report["assessment"]["recommendations"].append(
                f"Remove {len(report['feature_analysis']['dead_features'])} dead features to improve performance"
            )
        
        # Save report
        if save_report:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_path = f"output/model_evaluation_{timestamp}.json"
            Path(report_path).parent.mkdir(parents=True, exist_ok=True)
            
            with open(report_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            
            
            report["report_path"] = report_path
        
        # Log summary
        logger.info("========== MODEL EVALUATION SUMMARY ==========")
        logger.info(f"Overall Rating: {assessment}")
        logger.info(f"Precision: {precision:.3f} | Recall: {recall:.3f} | F1: {f1:.3f} | FPR: {fpr:.3f}")
        logger.info(f"Top 3 Features: {', '.join(list(importance.keys())[:3])}")
        logger.info(f"Dead Features: {len(report['feature_analysis']['dead_features'])}")
        if report["assessment"]["recommendations"]:
            logger.info(f"Recommendations: {'; '.join(report['assessment']['recommendations'])}")
        
        
        return report

    def train_incremental(self, X: pd.DataFrame, batch_id: str = None) -> Dict[str, Any]:
        """
        Gerçek incremental learning - Yeni mini model ekle - THREAD SAFE
        
        Args:
            X: Yeni batch feature matrix
            batch_id: Batch identifier
            
        Returns:
            Training sonuçları
        """
        
        # Thread safety - Ensemble'a yeni model eklenirken Predict yapılmasını engelle
        with self._training_lock:
            logger.debug(f"Batch size: {len(X)} samples")
            logger.debug(f"Current ensemble size: {len(self.incremental_models)} models")
            
            # Feature isimlerini sakla
            if self.feature_names is None:
                self.feature_names = list(X.columns)
            
            # Feature normalization — per-model scaler snapshot
            # Her mini-model kendi scaler'ıyla eğitilir ve bu scaler
            # predict_ensemble'da aynı modele özel olarak kullanılır.
            # Bu sayede partial_fit kaynaklı scaler drift'i önlenir.
            batch_scaler = StandardScaler()
            X_scaled = batch_scaler.fit_transform(X)

            # Ana scaler'ı da güncel tut (single-model path ve genel amaçlı)
            if not self.is_scaler_fitted:
                self.scaler.fit(X)
                self.is_scaler_fitted = True
            else:
                self.scaler.partial_fit(X)

            X_scaled_df = pd.DataFrame(X_scaled, columns=X.columns)

            # Yeni mini model oluştur
            mini_model_params = self.model_config['parameters'].copy()
            mini_model_params['n_estimators'] = min(100, mini_model_params.get('n_estimators', 100))  # Daha küçük model

            mini_model = IsolationForest(**mini_model_params)

            # Mini model'i eğit
            start_time = datetime.now()
            mini_model.fit(X_scaled_df)
            training_time = (datetime.now() - start_time).total_seconds()

            # Model metadata
            metadata = {
                'batch_id': batch_id or datetime.now().isoformat(),
                'timestamp': datetime.now().isoformat(),
                'n_samples': len(X),
                'training_time': training_time,
                'anomaly_ratio': 0  # Henüz bilinmiyor
            }

            # Model performansını test et (kendi verisi üzerinde)
            predictions = mini_model.predict(X_scaled_df)
            anomaly_ratio = (predictions == -1).mean()
            metadata['anomaly_ratio'] = float(anomaly_ratio)

            # Model ağırlığını hesapla (yeni model full ağırlık)
            model_weight = 1.0

            # Ensemble'a ekle (model + kendi scaler'ı birlikte)
            self.incremental_models.append(mini_model)
            self.model_scalers.append(batch_scaler)
            self.model_metadata.append(metadata)
            self.model_weights.append(model_weight)
            
            # Eski modellerin ağırlıklarını decay et
            decay_factor = self.incremental_config['weight_decay_factor']
            for i in range(len(self.model_weights) - 1):
                self.model_weights[i] *= decay_factor
            
            # Ağırlıkları normalize et
            total_weight = sum(self.model_weights)
            self.model_weights = [w / total_weight for w in self.model_weights]
            
            # Eğer maksimum model sayısına ulaştıysak, en eski modeli çıkar
            if len(self.incremental_models) > self.incremental_config['max_models']:
                self.incremental_models.popleft()
                if self.model_scalers:
                    self.model_scalers.popleft()
                self.model_metadata.pop(0)
                self.model_weights.pop(0)
            
            # Ensemble mode aktif — flag ile işaretle, model'i None yapmak yerine
            # son mini-model'i fallback olarak tut (concurrent predict güvenliği)
            self._ensemble_mode = True
            self.model = mini_model  # Fallback: concurrent predict için geçerli bir model
            self.is_trained = True
            # Training stats
            training_stats = {
                'method': 'incremental',
                'batch_id': metadata['batch_id'],
                'batch_size': len(X),
                'ensemble_size': len(self.incremental_models),
                'model_weights': self.model_weights.copy(),
                'training_time': training_time,
                'anomaly_ratio': anomaly_ratio
            }
            
            # train_incremental sonrası da buffer'ı güncelle
            try:
                # Anomaly scores hesapla (decision_function) - predictions zaten var
                anomaly_scores = mini_model.decision_function(X_scaled_df)
                
                if self.historical_data['features'] is None:
                    # İlk kez - direkt ata (orijinal X'i kaydet, scaled değil)
                    self.historical_data['features'] = X.copy()
                    self.historical_data['predictions'] = predictions.copy()
                    self.historical_data['scores'] = anomaly_scores.copy()
                    logger.info(f"📥 Historical buffer initialized with {len(X)} samples (incremental)")
                else:
                    # Mevcut buffer'a ekle (FIFO mantığı)
                    max_buffer_size = self.model_config.get('max_history_size', 500000)
                    combined_features = pd.concat([self.historical_data['features'], X], ignore_index=True)
                    combined_predictions = np.concatenate([self.historical_data['predictions'], predictions])
                    combined_scores = np.concatenate([self.historical_data['scores'], anomaly_scores])
                    
                    # Buffer limiti kontrolü
                    if len(combined_features) > max_buffer_size:
                        # FIFO: En eski verileri at
                        combined_features = combined_features.tail(max_buffer_size)
                        combined_predictions = combined_predictions[-max_buffer_size:]
                        combined_scores = combined_scores[-max_buffer_size:]
                        logger.info(f"📦 Historical buffer trimmed to {max_buffer_size} samples (FIFO)")
                    
                    self.historical_data['features'] = combined_features
                    self.historical_data['predictions'] = combined_predictions
                    self.historical_data['scores'] = combined_scores
                    logger.info(f"📥 Historical buffer updated: {len(combined_features)} total samples (incremental)")
                
                # Metadata güncelle
                anomaly_count = int(np.sum(self.historical_data['predictions'] == -1))
                self.historical_data['metadata']['total_samples'] = len(self.historical_data['features'])
                self.historical_data['metadata']['anomaly_samples'] = anomaly_count
                self.historical_data['metadata']['last_update'] = datetime.now().isoformat()
                self.historical_data['metadata']['buffer_version'] = 2.0  # Dolu buffer artık v2.0

            except Exception as e:
                logger.error(f"Error updating historical buffer in train_incremental: {e}")

            logger.debug(f"Incremental training completed:")
            logger.debug(f"  Ensemble size: {len(self.incremental_models)} models")
            
            return training_stats
    def predict_ensemble(self, X: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
        """
        Ensemble prediction - Weighted voting from all mini models
        Her model kendi eğitildiği scaler snapshot'ıyla predict eder.

        Args:
            X: Feature matrix

        Returns:
            (predictions, anomaly_scores)
        """
        if not self.incremental_models:
            raise ValueError("No incremental models available!")

        # Per-model scaler mevcutsa her model kendi scaler'ıyla predict eder
        has_per_model_scalers = len(self.model_scalers) == len(self.incremental_models)

        # Fallback: per-model scaler yoksa (eski model dosyası) genel scaler ile
        if not has_per_model_scalers and self.is_scaler_fitted:
            X_fallback_scaled = self.scaler.transform(X)
            X_fallback_df = pd.DataFrame(X_fallback_scaled, columns=X.columns)
        else:
            X_fallback_df = X

        # Her modelden prediction al
        all_predictions = []
        all_scores = []

        total_weight = 0.0
        for i, (model, weight) in enumerate(zip(self.incremental_models, self.model_weights)):
            try:
                # Per-model scaler varsa onu kullan, yoksa fallback
                if has_per_model_scalers:
                    scaler_i = self.model_scalers[i]
                    X_scaled_i = scaler_i.transform(X)
                    X_input = pd.DataFrame(X_scaled_i, columns=X.columns)
                else:
                    X_input = X_fallback_df

                pred = model.predict(X_input)
                scores = model.score_samples(X_input)

                all_predictions.append(pred * weight)  # Weighted prediction
                all_scores.append(scores * weight)  # Weighted scores
                total_weight += weight

            except Exception as e:

                continue
        
        if not all_predictions:
            raise ValueError("No successful predictions from ensemble!")
        
        # Weighted voting
        weighted_predictions = np.sum(all_predictions, axis=0)
        weighted_scores = np.sum(all_scores, axis=0)
        
        # Final predictions (threshold at 0)
        final_predictions = np.where(weighted_predictions < 0, -1, 1)
        
        # Normalize scores by total weight of contributing models
        final_scores = weighted_scores / total_weight if total_weight > 0 else weighted_scores
        
        n_anomalies = (final_predictions == -1).sum()
        
        
        return final_predictions, final_scores
    
    def detect_model_drift(self, X_new: pd.DataFrame, threshold: float = None) -> Dict[str, Any]:
        """
        Model drift detection - Yeni verinin mevcut modellere uyumunu kontrol et
        
        Args:
            X_new: Yeni veri
            threshold: Drift threshold
            
        Returns:
            Drift analiz sonuçları
        """
        if not self.incremental_models:
            return {"drift_detected": False, "reason": "No models available"}
        
        threshold = threshold or self.incremental_config['drift_threshold']
        
        
        
        # Feature normalization
        if self.is_scaler_fitted:
            X_scaled = self.scaler.transform(X_new)
            X_scaled_df = pd.DataFrame(X_scaled, columns=X_new.columns)
        else:
            X_scaled_df = X_new
        
        # Her modelin yeni veri üzerindeki performansını ölç
        model_performances = []
        
        for i, model in enumerate(self.incremental_models):
            scores = model.score_samples(X_scaled_df)
            mean_score = scores.mean()
            anomaly_ratio = (model.predict(X_scaled_df) == -1).mean()
            
            # Original training anomaly ratio ile karşılaştır
            original_ratio = self.model_metadata[i]['anomaly_ratio']
            ratio_diff = abs(anomaly_ratio - original_ratio)
            
            model_performances.append({
                'model_index': i,
                'mean_score': float(mean_score),
                'anomaly_ratio': float(anomaly_ratio),
                'original_ratio': float(original_ratio),
                'ratio_difference': float(ratio_diff)
            })
        
        # Ortalama drift hesapla
        avg_ratio_diff = np.mean([p['ratio_difference'] for p in model_performances])
        
        drift_detected = avg_ratio_diff > threshold
        
        drift_analysis = {
            'drift_detected': drift_detected,
            'average_drift': float(avg_ratio_diff),
            'threshold': float(threshold),
            'model_performances': model_performances,
            'recommendation': None
        }

        # Feature distribution drift: scaler mean/var ile yeni verinin ortalamalarını karşılaştır
        feature_drift = {}
        if self.is_scaler_fitted and hasattr(self.scaler, 'mean_') and hasattr(self.scaler, 'var_'):
            try:
                new_means = X_new.mean().values
                train_means = self.scaler.mean_
                train_stds = np.sqrt(self.scaler.var_ + 1e-10)  # sıfıra bölme koruması

                drifted_features = []
                feature_names = list(X_new.columns)
                for i, fname in enumerate(feature_names):
                    if i < len(train_means):
                        z_diff = abs(new_means[i] - train_means[i]) / train_stds[i]
                        if z_diff > 2.0:
                            drifted_features.append({
                                'feature': fname,
                                'z_score_diff': round(float(z_diff), 3),
                                'new_mean': round(float(new_means[i]), 4),
                                'train_mean': round(float(train_means[i]), 4)
                            })

                feature_drift = {
                    'drifted_feature_count': len(drifted_features),
                    'total_features': len(feature_names),
                    'drifted_features': sorted(drifted_features, key=lambda x: x['z_score_diff'], reverse=True),
                    'feature_drift_detected': len(drifted_features) > 0
                }

                # Feature drift de genel drift kararına katkıda bulunsun
                if len(drifted_features) >= 3 and not drift_detected:
                    drift_analysis['drift_detected'] = True
                    logger.warning(f"Feature distribution drift detected: {len(drifted_features)} features shifted (z>2)")

            except Exception as e:
                logger.error(f"Feature drift analysis failed: {e}")
                feature_drift = {'error': str(e)}

        drift_analysis['feature_drift'] = feature_drift

        if drift_analysis['drift_detected']:
            drift_analysis['recommendation'] = "High drift detected. Consider retraining or adjusting parameters."
        else:
            drift_analysis['recommendation'] = "No significant drift detected. Model is stable."

        return drift_analysis
    
    def get_ensemble_info(self) -> Dict[str, Any]:
        """
        Ensemble model bilgilerini döndür
        
        Returns:
            Ensemble istatistikleri
        """
        if not self.incremental_models:
            return {
                "enabled": self.incremental_config['enabled'],
                "status": "No models in ensemble",
                "model_count": 0
            }
        
        info = {
            "enabled": self.incremental_config['enabled'],
            "status": "Active",
            "model_count": len(self.incremental_models),
            "max_models": self.incremental_config['max_models'],
            "ensemble_method": self.incremental_config['ensemble_method'],
            "model_weights": [float(w) for w in self.model_weights],
            "models": []
        }
        
        for i, (model, metadata, weight) in enumerate(zip(
            self.incremental_models, self.model_metadata, self.model_weights
        )):
            model_info = {
                "index": i,
                "batch_id": metadata['batch_id'],
                "timestamp": metadata['timestamp'],
                "n_samples": metadata['n_samples'],
                "anomaly_ratio": metadata['anomaly_ratio'],
                "weight": float(weight),
                "weight_percentage": f"{weight * 100:.1f}%"
            }
            info["models"].append(model_info)
        
        # Total samples trained on
        total_samples = sum(m['n_samples'] for m in self.model_metadata)
        info["total_samples_seen"] = total_samples
        
        # Average anomaly ratio
        avg_anomaly_ratio = np.mean([m['anomaly_ratio'] for m in self.model_metadata])
        info["average_anomaly_ratio"] = float(avg_anomaly_ratio)
        
        return info
    
    def score_samples(self, X):
        """
        Calculate anomaly scores for samples
        Lower scores indicate more abnormal samples
        """
        if not self.is_trained:
            raise ValueError("Model is not trained yet!")
        
        # Ensemble mode aktifse ensemble scoring kullan
        if self.incremental_models and self.incremental_config['enabled']:
            # Per-model scaler mevcutsa her model kendi scaler'ıyla score eder
            has_per_model_scalers = len(self.model_scalers) == len(self.incremental_models)

            # Fallback: per-model scaler yoksa (eski model dosyası) genel scaler ile
            if not has_per_model_scalers and self.is_scaler_fitted:
                X_fallback_scaled = self.scaler.transform(X)
                X_fallback_df = pd.DataFrame(X_fallback_scaled, columns=X.columns)
            else:
                X_fallback_df = X

            all_scores = []
            for i, (model, weight) in enumerate(zip(self.incremental_models, self.model_weights)):
                try:
                    if has_per_model_scalers:
                        scaler_i = self.model_scalers[i]
                        X_scaled_i = scaler_i.transform(X)
                        X_input = pd.DataFrame(X_scaled_i, columns=X.columns)
                    else:
                        X_input = X_fallback_df
                    scores = model.score_samples(X_input)
                    all_scores.append(scores * weight)
                except Exception as e:
                    continue
            
            if all_scores:
                return np.sum(all_scores, axis=0)
            else:
                raise ValueError("No successful scoring from ensemble!")
                
        # Single model mode
        elif hasattr(self, 'model') and self.model is not None:
            if self.is_scaler_fitted:
                X_scaled = self.scaler.transform(X)
                X = pd.DataFrame(X_scaled, columns=X.columns)
            return self.model.score_samples(X)
        else:
            raise ValueError("No model available for scoring!")