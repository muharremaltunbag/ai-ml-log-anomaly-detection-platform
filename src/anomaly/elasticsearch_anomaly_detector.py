# src/anomaly/elasticsearch_anomaly_detector.py
"""
Elasticsearch Log Anomaly Detection Module
MongoDBAnomalyDetector'dan inheritance — Elasticsearch'e özgü kurallar

Yapı: MSSQLAnomalyDetector ile aynı pattern, Elasticsearch'e uyarlanmış.
Model, training, prediction, online learning parent'tan gelir.
Sadece critical rules, severity scoring, message extraction ve model path override edilir.
"""

import logging
import numpy as np
import pandas as pd
from typing import Dict, Any, List
from pathlib import Path

from .anomaly_detector import MongoDBAnomalyDetector

logger = logging.getLogger(__name__)


class ElasticsearchAnomalyDetector(MongoDBAnomalyDetector):
    """
    Elasticsearch logları için anomali tespiti.

    MongoDBAnomalyDetector'dan inheritance alır.
    Sadece critical rules Elasticsearch'e özgü olarak override edilir.
    Model, training, prediction, online learning aynı kalır.
    """

    # Class-level instance cache (MongoDB ve MSSQL ile ayrı)
    _es_instances = {}

    @classmethod
    def get_instance(cls, server_name: str = "global",
                     config_path: str = "config/elasticsearch_anomaly_config.json"):
        """
        Belirli bir Elasticsearch node'u için bellekteki mevcut modeli döndürür,
        yoksa oluşturur.

        Args:
            server_name: Elasticsearch node adı (e.g., ECAZTRDBESRW003)
            config_path: Elasticsearch config dosyası

        Returns:
            ElasticsearchAnomalyDetector instance
        """
        raw_name = server_name or "global"

        # FQDN normalization (varsa)
        if '.' in raw_name and raw_name != "global":
            hostname = raw_name.split('.')[0]
            logger.debug(f"FQDN normalized: {raw_name} -> {hostname}")
        else:
            hostname = raw_name

        safe_name = hostname.upper()  # ES hostlar UPPERCASE (ECAZTRDBESRW003)

        # Elasticsearch için ayrı instance cache kullan
        with cls._instance_lock:
            if safe_name not in cls._es_instances:
                logger.info(f"Creating NEW Elasticsearch detector instance for: {safe_name}")
                instance = cls(config_path)
                instance.load_model(
                    server_name=safe_name if safe_name != "GLOBAL" else None
                )
                cls._es_instances[safe_name] = instance
            else:
                logger.debug(f"Using EXISTING Elasticsearch detector for: {safe_name}")

            return cls._es_instances[safe_name]

    def __init__(self, config_path: str = "config/elasticsearch_anomaly_config.json"):
        """
        Elasticsearch Anomaly Detector başlat.

        Args:
            config_path: Elasticsearch konfigürasyon dosyası yolu
        """
        # Parent class'ı ES config ile başlat
        super().__init__(config_path)

        # Elasticsearch'e özgü critical rules ile override et
        self.critical_rules = self._initialize_es_critical_rules()

        # Min training sample guard (config'den)
        self.min_training_samples = self.config.get(
            'anomaly_detection', {}
        ).get('min_training_samples', 50)

        logger.info(f"ElasticsearchAnomalyDetector initialized with "
                    f"{len(self.critical_rules)} ES-specific rules, "
                    f"min_samples={self.min_training_samples}")

    def _initialize_es_critical_rules(self) -> Dict[str, Any]:
        """
        Elasticsearch'e özgü kritik anomali kurallarını tanımla.

        Returns:
            Elasticsearch rule dictionary
        """
        rules = {
            # =================================================================
            # CLUSTER STABILITY RULES
            # =================================================================

            # Cluster Instability — master election + node events
            'cluster_instability': {
                'condition': lambda row: (
                    row.get('is_master_election', 0) == 1 or
                    (row.get('is_node_event', 0) == 1 and
                     row.get('is_error', 0) == 1)
                ),
                'severity': 0.95,
                'description': 'Cluster instability - master election or node disconnect with errors'
            },

            # Memory Crisis — OOM + circuit breaker
            'memory_crisis': {
                'condition': lambda row: (
                    row.get('is_oom_error', 0) == 1 or
                    row.get('is_circuit_breaker', 0) == 1
                ),
                'severity': 0.95,
                'description': 'JVM memory crisis - OutOfMemoryError or CircuitBreakingException'
            },

            # =================================================================
            # RESOURCE RULES
            # =================================================================

            # Disk Crisis — high watermark + flood stage
            'disk_crisis': {
                'condition': lambda row: (
                    row.get('is_high_disk_watermark', 0) == 1 and
                    row.get('is_error', 0) == 1
                ),
                'severity': 0.90,
                'description': 'Disk crisis - high watermark or flood stage with errors'
            },

            # Disk Warning — watermark ama error değil (daha düşük severity)
            'disk_warning': {
                'condition': lambda row: (
                    row.get('is_high_disk_watermark', 0) == 1 and
                    row.get('is_warn', 0) == 1
                ),
                'severity': 0.80,
                'description': 'Disk warning - watermark threshold approached'
            },

            # =================================================================
            # SHARD & INDEX RULES
            # =================================================================

            # Shard Failure — shard allocation failures
            'shard_failure': {
                'condition': lambda row: (
                    row.get('is_shard_failure', 0) == 1
                ),
                'severity': 0.88,
                'description': 'Shard allocation failure or unassigned shards'
            },

            # Shard Relocation Storm — yoğun shard hareketi
            'shard_relocation_storm': {
                'condition': lambda row: (
                    row.get('is_shard_relocation', 0) == 1 and
                    row.get('extreme_burst_flag', 0) == 1
                ),
                'severity': 0.82,
                'description': 'Shard relocation storm - excessive shard movement'
            },

            # =================================================================
            # PERFORMANCE RULES
            # =================================================================

            # GC Storm — sık GC pause'ları
            'gc_storm': {
                'condition': lambda row: (
                    row.get('is_gc_overhead', 0) == 1 and
                    row.get('burst_density', 0) > 0.3
                ),
                'severity': 0.85,
                'description': 'GC storm - frequent garbage collection pauses'
            },

            # GC Warning — tek GC event
            'gc_warning': {
                'condition': lambda row: (
                    row.get('is_gc_overhead', 0) == 1
                ),
                'severity': 0.75,
                'description': 'GC overhead detected - JVM pause'
            },

            # =================================================================
            # NETWORK RULES
            # =================================================================

            # Connection Storm — çok sayıda bağlantı hatası
            'connection_storm': {
                'condition': lambda row: (
                    row.get('is_connection_error', 0) == 1 and
                    row.get('extreme_burst_flag', 0) == 1
                ),
                'severity': 0.82,
                'description': 'Connection storm - multiple connection errors in burst'
            },

            # =================================================================
            # PATTERN RULES
            # =================================================================

            # Error Burst — yüksek hata yoğunluğu
            'error_burst': {
                'condition': lambda row: (
                    row.get('is_error', 0) == 1 and
                    row.get('extreme_burst_flag', 0) == 1 and
                    row.get('burst_density', 0) > 0.5
                ),
                'severity': 0.85,
                'description': 'Error burst - high density of errors in short timeframe'
            },

            # Node Event — node join/leave (not necessarily error)
            'node_event': {
                'condition': lambda row: (
                    row.get('is_node_event', 0) == 1
                ),
                'severity': 0.78,
                'description': 'Node join/leave event detected'
            },
        }

        return rules

    def get_rule_descriptions(self) -> Dict[str, str]:
        """Tüm ES kurallarının açıklamalarını döndür"""
        return {
            name: rule['description']
            for name, rule in self.critical_rules.items()
        }

    def get_rule_stats(self) -> Dict[str, Any]:
        """Rule istatistiklerini döndür"""
        return {
            'total_rules': len(self.critical_rules),
            'rule_names': list(self.critical_rules.keys()),
            'severity_distribution': {
                name: rule['severity']
                for name, rule in self.critical_rules.items()
            },
            'override_stats': self.rule_stats if hasattr(self, 'rule_stats') else {}
        }

    # =================================================================
    # MESSAGE EXTRACTION OVERRIDE — ES raw_message kullanır
    # =================================================================

    def _extract_anomaly_message(self, df: pd.DataFrame, idx: int) -> str:
        """
        ES anomali satırından mesaj çıkar — raw_message kullanır.
        Parent'ın MongoDB-specific extract_mongodb_message çağrısını atlar.
        """
        row = df.iloc[idx]
        if 'raw_message' in df.columns and pd.notna(row.get('raw_message')):
            return str(row['raw_message'])[:1000]
        elif 'message' in df.columns and pd.notna(row.get('message')):
            msg = row['message']
            if isinstance(msg, list):
                return str(msg[0])[:1000] if msg else "No message"
            return str(msg)[:1000]
        return "No message available"

    # =================================================================
    # SEVERITY SCORE OVERRIDE — Elasticsearch'e özgü
    # =================================================================

    def calculate_severity_score(self, anomaly_idx: int, anomaly_score: float,
                                 row_features: dict, df_row) -> dict:
        """
        Elasticsearch anomali için severity skoru hesapla (0-100).

        Bölümler:
          1. Base ML Score        (0-40)
          2. Log Level Criticality (0-20)
          3. Critical Features    (0-40)  — ES feature'ları
          4. Temporal Factor      (0-10)
          5. Rule Engine Bonus    (0-20)
        """
        severity_score = 0
        factors = []

        # ── 1. Base ML Score (0-40) ──
        ml_contribution = abs(anomaly_score) * 40
        severity_score += ml_contribution
        factors.append(f"ML Score: +{ml_contribution:.1f}")

        # ── 2. Log Level Criticality (0-20) ──
        log_level = 'UNKNOWN'
        if hasattr(df_row, 'get'):
            log_level = df_row.get('log_level', 'UNKNOWN')
        elif hasattr(df_row, 'log_level'):
            log_level = df_row.log_level

        level_scores = {
            'CRITICAL': 20,
            'ERROR': 20,
            'WARN': 12,
            'INFO': 5,
            'DEBUG': 3,
            'TRACE': 2,
            'UNKNOWN': 8,
        }
        level_str = str(log_level).upper().strip()
        level_score = level_scores.get(level_str, 8)
        severity_score += level_score
        factors.append(f"Log Level ({level_str}): +{level_score}")

        # ── 3. Critical ES Features (0-40) ──
        feature_score = 0

        # OOM — en kritik
        if row_features.get('is_oom_error', 0) == 1:
            feature_score += 40
            factors.append("OOM Error: +40")

        # Circuit breaker
        if row_features.get('is_circuit_breaker', 0) == 1:
            feature_score += 35
            factors.append("Circuit Breaker: +35")

        # Master election
        if row_features.get('is_master_election', 0) == 1:
            feature_score += 35
            factors.append("Master Election: +35")

        # Shard failure
        if row_features.get('is_shard_failure', 0) == 1:
            feature_score += 30
            factors.append("Shard Failure: +30")

        # High disk watermark
        if row_features.get('is_high_disk_watermark', 0) == 1:
            feature_score += 28
            factors.append("Disk Watermark: +28")

        # Node event (join/leave)
        if row_features.get('is_node_event', 0) == 1:
            feature_score += 25
            factors.append("Node Event: +25")

        # Connection error
        if row_features.get('is_connection_error', 0) == 1:
            feature_score += 22
            factors.append("Connection Error: +22")

        # GC overhead
        if row_features.get('is_gc_overhead', 0) == 1:
            feature_score += 20
            factors.append("GC Overhead: +20")

        # Slow log
        if row_features.get('is_slow_log', 0) == 1:
            feature_score += 15
            factors.append("Slow Log: +15")

        # Shard relocation
        if row_features.get('is_shard_relocation', 0) == 1:
            feature_score += 12
            factors.append("Shard Relocation: +12")

        # Exception
        if row_features.get('is_exception', 0) == 1:
            feature_score += 10
            factors.append("Exception: +10")

        # High CPU
        if row_features.get('is_high_cpu', 0) == 1:
            feature_score += 10
            factors.append("High CPU: +10")

        # Cap: 0-40
        feature_score = min(feature_score, 40)
        severity_score += feature_score

        # ── 4. Temporal Factor (0-10) ──
        hour = row_features.get('hour_of_day', 0)
        is_weekend = row_features.get('is_weekend', 0)
        is_business = row_features.get('is_business_hours', 0)

        if is_business == 1:
            temporal_score = 10
            factors.append(f"Business Hours ({hour}:00): +10")
        elif is_weekend == 1:
            temporal_score = 7
            factors.append(f"Weekend ({hour}:00): +7")
        elif hour in [8, 9, 10, 17, 18, 19]:
            temporal_score = 8
            factors.append(f"Peak Hour ({hour}:00): +8")
        else:
            temporal_score = 4
            factors.append(f"Off-hours ({hour}:00): +4")

        severity_score += temporal_score

        # ── 5. Rule Engine Bonus (0-20) ──
        if anomaly_score <= -0.70:
            severity_score += 20
            factors.append(f"Rule Override: +20 (score={anomaly_score:.2f})")

        # ── Normalize & Level ──
        severity_score = min(100, max(0, severity_score))

        if severity_score >= 80:
            level, color = "CRITICAL", "#e74c3c"
        elif severity_score >= 60:
            level, color = "HIGH", "#e67e22"
        elif severity_score >= 40:
            level, color = "MEDIUM", "#f39c12"
        elif severity_score >= 20:
            level, color = "LOW", "#3498db"
        else:
            level, color = "INFO", "#95a5a6"

        return {
            "score": severity_score,
            "level": level,
            "color": color,
            "factors": factors
        }

    # =================================================================
    # ANALYZE ANOMALIES OVERRIDE — ES message & alert uyarlaması
    # =================================================================

    def analyze_anomalies(self, df: pd.DataFrame, X: pd.DataFrame,
                          predictions: np.ndarray,
                          anomaly_scores: np.ndarray) -> Dict[str, Any]:
        """
        Elasticsearch anomali analizi — parent'ı çağırıp post-process yapar.

        Post-process:
          1. critical_anomalies'deki mesajları raw_message ile düzeltir
          2. component alanını logger_name ile doldurur
          3. ES critical pattern taraması (kaçırılmış anomaliler)
          4. ES-özgü alerts ekler
        """
        # Parent çağrısı
        analysis = super().analyze_anomalies(df, X, predictions, anomaly_scores)

        anomaly_mask = predictions == -1

        # ── 1. Message & field düzeltmesi ──
        for anomaly in analysis.get('critical_anomalies', []):
            idx = anomaly.get('index', 0)
            if idx < len(df):
                row = df.iloc[idx]
                raw_msg = ''
                if 'raw_message' in df.columns and pd.notna(row.get('raw_message')):
                    raw_msg = str(row['raw_message'])
                elif 'message' in df.columns and pd.notna(row.get('message')):
                    msg = row['message']
                    raw_msg = str(msg[0]) if isinstance(msg, list) else str(msg)

                if raw_msg:
                    anomaly['message'] = raw_msg[:1000]

                # Component → logger_name
                anomaly['component'] = row.get('logger_name', None)
                # Severity → log_level
                anomaly['severity'] = row.get('log_level', None)
                # Host role ek bilgisi
                anomaly['host_role'] = row.get('host_role', None)

        # ── 1b. all_anomalies için de ──
        for anomaly in analysis.get('all_anomalies', []):
            idx = anomaly.get('index', 0)
            if idx < len(df):
                row = df.iloc[idx]
                raw_msg = ''
                if 'raw_message' in df.columns and pd.notna(row.get('raw_message')):
                    raw_msg = str(row['raw_message'])
                elif 'message' in df.columns and pd.notna(row.get('message')):
                    msg = row['message']
                    raw_msg = str(msg[0]) if isinstance(msg, list) else str(msg)
                if raw_msg:
                    anomaly['message'] = raw_msg[:1000]
                anomaly['component'] = row.get('logger_name', None)
                anomaly['severity'] = row.get('log_level', None)

        # ── 2. ES critical pattern taraması ──
        existing_indices = {a['index'] for a in analysis.get('critical_anomalies', [])}
        anomaly_indices = np.where(anomaly_mask)[0]

        es_critical_patterns = [
            'outofmemoryerror', 'circuitbreakingexception', 'master not discovered',
            'flood stage', 'shard failed', 'unassigned', 'node left',
            'node disconnected', 'data too large',
        ]

        added_count = 0
        for idx in anomaly_indices:
            if int(idx) in existing_indices:
                continue
            if idx >= len(df):
                continue

            row = df.iloc[idx]
            raw_msg = str(row.get('raw_message', '')) if pd.notna(
                row.get('raw_message')) else ''
            msg_lower = raw_msg.lower()

            is_es_critical = any(p in msg_lower for p in es_critical_patterns)
            if not is_es_critical:
                continue

            row_features = X.iloc[idx].to_dict()
            severity_info = self.calculate_severity_score(
                idx, anomaly_scores[idx], row_features, row
            )

            analysis['critical_anomalies'].append({
                "index": int(idx),
                "severity_score": severity_info["score"],
                "severity_level": severity_info["level"],
                "severity_color": severity_info["color"],
                "anomaly_score": float(anomaly_scores[idx]),
                "timestamp": str(row['timestamp']) if 'timestamp' in df.columns else None,
                "severity": row.get('log_level', None),
                "component": row.get('logger_name', None),
                "message": raw_msg[:1000],
                "severity_factors": None
            })
            added_count += 1
            if added_count >= 100:
                break

        # Re-sort by severity
        analysis['critical_anomalies'].sort(
            key=lambda x: x.get('severity_score', 0), reverse=True
        )
        analysis['critical_anomalies'] = analysis['critical_anomalies'][:500]

        logger.info(f"ES analyze_anomalies post-process: "
                    f"{len(analysis['critical_anomalies'])} critical anomalies "
                    f"(+{added_count} from ES pattern scan)")

        # ── 3. ES-Specific Alerts ──
        es_alerts = {
            "oom_errors": {"count": 0, "indices": []},
            "circuit_breakers": {"count": 0, "indices": []},
            "disk_warnings": {"count": 0, "indices": []},
            "shard_failures": {"count": 0, "indices": []},
            "node_events": {"count": 0, "indices": []},
            "master_elections": {"count": 0, "indices": []},
            "gc_events": {"count": 0, "indices": []},
            "connection_errors": {"count": 0, "indices": []},
        }

        alert_features = {
            "oom_errors": "is_oom_error",
            "circuit_breakers": "is_circuit_breaker",
            "disk_warnings": "is_high_disk_watermark",
            "shard_failures": "is_shard_failure",
            "node_events": "is_node_event",
            "master_elections": "is_master_election",
            "gc_events": "is_gc_overhead",
            "connection_errors": "is_connection_error",
        }

        for alert_name, feature_col in alert_features.items():
            if feature_col in X.columns:
                mask = (X[feature_col] == 1) & anomaly_mask
                count = int(mask.sum())
                if count > 0:
                    es_alerts[alert_name] = {
                        "count": count,
                        "indices": list(np.where(mask)[0][:10])
                    }

        analysis["security_alerts"] = es_alerts

        return analysis

    # =================================================================
    # TRAINING GUARD — min_training_samples kontrolü
    # =================================================================

    def train(self, X: pd.DataFrame, save_model=True,
              incremental=True, server_name=None):
        """
        Elasticsearch modeli eğit — min sample guard ile.

        Düşük hacimli host'lar (ör. <50 log) için eğitimi atlar
        ve uyarı verir.
        """
        if len(X) < self.min_training_samples:
            logger.warning(
                f"Insufficient samples for training: {len(X)} < "
                f"{self.min_training_samples}. Skipping training for "
                f"server={server_name}. Use global model as fallback."
            )
            return {
                'status': 'skipped',
                'reason': f'insufficient_samples ({len(X)} < {self.min_training_samples})',
                'n_samples': len(X),
                'server_name': server_name
            }

        return super().train(
            X, save_model=save_model,
            incremental=incremental, server_name=server_name
        )

    # =================================================================
    # MODEL PATH İZOLASYONU
    # MongoDB: models/isolation_forest_{hostname}.pkl
    # MSSQL:   models/mssql_isolation_forest_{hostname}.pkl
    # ES:      models/es_isolation_forest_{hostname}.pkl
    # =================================================================

    @staticmethod
    def _normalize_server_name(server_name: str) -> str:
        """Server name normalize — UPPERCASE + FQDN strip"""
        name = server_name or ""
        if '.' in name and name != "global":
            name = name.split('.')[0]
        return name.upper().replace('/', '_')

    def save_model(self, path: str = None, server_name: str = None) -> str:
        """ES modeli kaydet — ayrı path prefix ile."""
        if path is None:
            if server_name:
                safe_name = self._normalize_server_name(server_name)
                path = f'models/es_isolation_forest_{safe_name}.pkl'
            else:
                safe_name = None
                path = self.output_config.get(
                    'model_path', 'models/es_isolation_forest.pkl'
                )
        else:
            safe_name = self._normalize_server_name(server_name) if server_name else server_name

        return super().save_model(
            path=path, server_name=safe_name or server_name
        )

    def load_model(self, path: str = None, server_name: str = None) -> bool:
        """ES modeli yükle — ayrı path prefix ile."""
        if path is None:
            if server_name:
                safe_name = self._normalize_server_name(server_name)
                path = f'models/es_isolation_forest_{safe_name}.pkl'
            else:
                path = self.output_config.get(
                    'model_path', 'models/es_isolation_forest.pkl'
                )

            # Server-specific model yoksa, global ES modeli dene
            if not Path(path).exists() and server_name:
                fallback = self.output_config.get(
                    'model_path', 'models/es_isolation_forest.pkl'
                )
                if Path(fallback).exists():
                    logger.info(f"Server-specific ES model not found, "
                                f"using global: {fallback}")
                    path = fallback

        return super().load_model(path=path, server_name=server_name)


# =============================================================================
# MODULE-LEVEL HELPER FUNCTIONS
# =============================================================================

def get_es_detector(server_name: str = "global") -> ElasticsearchAnomalyDetector:
    """
    Module-level function to get Elasticsearch detector instance.

    Args:
        server_name: Elasticsearch node adı

    Returns:
        ElasticsearchAnomalyDetector instance
    """
    return ElasticsearchAnomalyDetector.get_instance(server_name)
