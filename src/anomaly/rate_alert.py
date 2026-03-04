# src/anomaly/rate_alert.py

"""
Rate-Based Alerting - Cross-Source Prediction Layer (Katman 2)

Time-window bazlı event sayacı. Feature matrix ve enriched DataFrame kullanarak
belirli event türlerinin threshold'u aşıp aşmadığını kontrol eder.

Source-aware: MongoDB / MSSQL / Elasticsearch DataFrame column isimlerine uyumlu
ayrı detector registry'leri. check(df, server_name, source_type) ile çağrılır.

Mevcut pipeline'dan bağımsız çalışır. anomaly_tools.py tarafından
analiz sonrasında opsiyonel olarak çağrılır.

Feature flag: config.prediction.rate_alerting.enabled
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict, field

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class RateAlert:
    """Tek bir rate-based alert"""
    alert_type: str          # "auth_failure_spike", "error_burst", "slow_query_spike", "collscan_spike"
    severity: str            # "WARNING", "CRITICAL"
    title: str
    description: str
    window_name: str         # "short" (15min), "medium" (1h), "long" (6h)
    window_minutes: int
    event_type: str          # Hangi event tipi
    event_count: int         # Penceredeki toplam sayı
    threshold: int           # Config'deki eşik
    exceed_ratio: float      # Eşiği ne kadar aştı (count/threshold)
    time_range_start: Optional[str] = None
    time_range_end: Optional[str] = None
    server_name: Optional[str] = None
    timestamp: str = ""
    explainability: str = ""
    sample_messages: List[str] = field(default_factory=list)
    ml_context: Optional[Dict[str, Any]] = None  # ML-derived overlay (anomaly density, corroboration)
    confidence: float = 0.5  # 0-1 arası normalize güven skoru

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RateAlertReport:
    """Rate alert raporu"""
    server_name: Optional[str]
    windows_checked: int
    alerts: List[RateAlert] = field(default_factory=list)
    event_counts: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat()

    def has_alerts(self) -> bool:
        return len(self.alerts) > 0

    def max_severity(self) -> str:
        if not self.alerts:
            return "OK"
        severity_order = {"WARNING": 1, "CRITICAL": 2}
        return max(self.alerts, key=lambda a: severity_order.get(a.severity, 0)).severity

    def to_dict(self) -> Dict[str, Any]:
        return {
            "server_name": self.server_name,
            "windows_checked": self.windows_checked,
            "alerts": [a.to_dict() for a in self.alerts],
            "event_counts": self.event_counts,
            "timestamp": self.timestamp,
            "max_severity": self.max_severity(),
            "has_alerts": self.has_alerts()
        }


# ──────────────────────────────────────────────
# Event detectors: DataFrame'den event tiplerini sayar
# Her biri (count, sample_messages) döner
# ──────────────────────────────────────────────

def _count_auth_failures(df_window: pd.DataFrame) -> tuple:
    """Authentication failure sayısını hesapla"""
    if 'is_auth_failure' in df_window.columns:
        mask = df_window['is_auth_failure'] == 1
        count = int(mask.sum())
        samples = _extract_samples(df_window, mask, 3)
        return count, samples
    # Fallback: msg alanında ara
    if 'msg' in df_window.columns:
        mask = df_window['msg'].fillna('').str.lower().str.contains('authentication failed|auth failure|login failed')
        count = int(mask.sum())
        samples = _extract_samples(df_window, mask, 3)
        return count, samples
    return 0, []


def _count_error_bursts(df_window: pd.DataFrame) -> tuple:
    """Error/Fatal log sayısını hesapla"""
    if 's' in df_window.columns:
        mask = df_window['s'].isin(['E', 'F'])  # Error + Fatal
        count = int(mask.sum())
        samples = _extract_samples(df_window, mask, 3)
        return count, samples
    return 0, []


def _count_slow_queries(df_window: pd.DataFrame) -> tuple:
    """Slow query sayısını hesapla"""
    if 'is_slow_query' in df_window.columns:
        mask = df_window['is_slow_query'] == 1
        count = int(mask.sum())
        samples = _extract_samples(df_window, mask, 3)
        return count, samples
    return 0, []


def _count_collscans(df_window: pd.DataFrame) -> tuple:
    """COLLSCAN (full table scan) sayısını hesapla"""
    if 'is_collscan' in df_window.columns:
        mask = df_window['is_collscan'] == 1
        count = int(mask.sum())
        samples = _extract_samples(df_window, mask, 3)
        return count, samples
    return 0, []


def _count_drop_operations(df_window: pd.DataFrame) -> tuple:
    """DROP (collection/index) operasyonlarını say"""
    if 'is_drop_operation' in df_window.columns:
        mask = df_window['is_drop_operation'] == 1
        count = int(mask.sum())
        samples = _extract_samples(df_window, mask, 3)
        return count, samples
    return 0, []


def _count_oom_events(df_window: pd.DataFrame) -> tuple:
    """Out of Memory event'lerini say"""
    if 'is_out_of_memory' in df_window.columns:
        mask = df_window['is_out_of_memory'] == 1
        count = int(mask.sum())
        samples = _extract_samples(df_window, mask, 3)
        return count, samples
    return 0, []


# ──────────────────────────────────────────────
# MSSQL Event Detectors
# MSSQL feature columns: is_failed_login, is_connection_error,
#   is_permission_error, is_high_severity_error, is_fdhost_crash,
#   is_availability_group_error, is_database_access_error, is_grok_failure
# ──────────────────────────────────────────────

def _count_mssql_failed_logins(df_window: pd.DataFrame) -> tuple:
    """MSSQL başarısız login sayısı (is_failed_login column)"""
    if 'is_failed_login' in df_window.columns:
        mask = df_window['is_failed_login'] == 1
        count = int(mask.sum())
        samples = _extract_samples(df_window, mask, 3)
        return count, samples
    # Fallback: raw_message'da ara
    for col in ('raw_message', 'message'):
        if col in df_window.columns:
            mask = df_window[col].fillna('').str.lower().str.contains(
                'login failed|logon failed')
            count = int(mask.sum())
            samples = _extract_samples(df_window, mask, 3)
            return count, samples
    return 0, []


def _count_mssql_connection_errors(df_window: pd.DataFrame) -> tuple:
    """MSSQL bağlantı hataları (is_connection_error column)"""
    if 'is_connection_error' in df_window.columns:
        mask = df_window['is_connection_error'] == 1
        count = int(mask.sum())
        samples = _extract_samples(df_window, mask, 3)
        return count, samples
    return 0, []


def _count_mssql_permission_errors(df_window: pd.DataFrame) -> tuple:
    """MSSQL izin hataları (is_permission_error column)"""
    if 'is_permission_error' in df_window.columns:
        mask = df_window['is_permission_error'] == 1
        count = int(mask.sum())
        samples = _extract_samples(df_window, mask, 3)
        return count, samples
    return 0, []


def _count_mssql_high_severity(df_window: pd.DataFrame) -> tuple:
    """MSSQL Severity >= 17 hatalar (is_high_severity_error column)"""
    if 'is_high_severity_error' in df_window.columns:
        mask = df_window['is_high_severity_error'] == 1
        count = int(mask.sum())
        samples = _extract_samples(df_window, mask, 3)
        return count, samples
    return 0, []


def _count_mssql_ag_errors(df_window: pd.DataFrame) -> tuple:
    """MSSQL Availability Group hataları"""
    if 'is_availability_group_error' in df_window.columns:
        mask = df_window['is_availability_group_error'] == 1
        count = int(mask.sum())
        samples = _extract_samples(df_window, mask, 3)
        return count, samples
    return 0, []


def _count_mssql_fdhost_crash(df_window: pd.DataFrame) -> tuple:
    """MSSQL FDHost crash event'leri"""
    if 'is_fdhost_crash' in df_window.columns:
        mask = df_window['is_fdhost_crash'] == 1
        count = int(mask.sum())
        samples = _extract_samples(df_window, mask, 3)
        return count, samples
    return 0, []


# ──────────────────────────────────────────────
# Elasticsearch Event Detectors
# ES feature columns: is_oom_error, is_circuit_breaker, is_shard_failure,
#   is_gc_overhead, is_high_disk_watermark, is_connection_error,
#   is_master_election, is_node_event, is_shard_relocation,
#   is_exception, is_error, is_warn
# ──────────────────────────────────────────────

def _count_es_oom(df_window: pd.DataFrame) -> tuple:
    """ES OutOfMemory event'leri (is_oom_error column)"""
    if 'is_oom_error' in df_window.columns:
        mask = df_window['is_oom_error'] == 1
        count = int(mask.sum())
        samples = _extract_samples(df_window, mask, 3)
        return count, samples
    return 0, []


def _count_es_circuit_breaker(df_window: pd.DataFrame) -> tuple:
    """ES circuit breaker trip event'leri"""
    if 'is_circuit_breaker' in df_window.columns:
        mask = df_window['is_circuit_breaker'] == 1
        count = int(mask.sum())
        samples = _extract_samples(df_window, mask, 3)
        return count, samples
    return 0, []


def _count_es_shard_failure(df_window: pd.DataFrame) -> tuple:
    """ES shard failure event'leri"""
    if 'is_shard_failure' in df_window.columns:
        mask = df_window['is_shard_failure'] == 1
        count = int(mask.sum())
        samples = _extract_samples(df_window, mask, 3)
        return count, samples
    return 0, []


def _count_es_gc_overhead(df_window: pd.DataFrame) -> tuple:
    """ES GC overhead event'leri"""
    if 'is_gc_overhead' in df_window.columns:
        mask = df_window['is_gc_overhead'] == 1
        count = int(mask.sum())
        samples = _extract_samples(df_window, mask, 3)
        return count, samples
    return 0, []


def _count_es_disk_watermark(df_window: pd.DataFrame) -> tuple:
    """ES disk watermark uyarıları"""
    if 'is_high_disk_watermark' in df_window.columns:
        mask = df_window['is_high_disk_watermark'] == 1
        count = int(mask.sum())
        samples = _extract_samples(df_window, mask, 3)
        return count, samples
    return 0, []


def _count_es_master_election(df_window: pd.DataFrame) -> tuple:
    """ES master election event'leri"""
    if 'is_master_election' in df_window.columns:
        mask = df_window['is_master_election'] == 1
        count = int(mask.sum())
        samples = _extract_samples(df_window, mask, 3)
        return count, samples
    return 0, []


def _count_es_connection_errors(df_window: pd.DataFrame) -> tuple:
    """ES connection error event'leri"""
    if 'is_connection_error' in df_window.columns:
        mask = df_window['is_connection_error'] == 1
        count = int(mask.sum())
        samples = _extract_samples(df_window, mask, 3)
        return count, samples
    return 0, []


def _count_es_errors(df_window: pd.DataFrame) -> tuple:
    """ES ERROR level log sayısı"""
    if 'is_error' in df_window.columns:
        mask = df_window['is_error'] == 1
        count = int(mask.sum())
        samples = _extract_samples(df_window, mask, 3)
        return count, samples
    return 0, []


def _extract_samples(df: pd.DataFrame, mask: pd.Series, n: int) -> List[str]:
    """Matching log'lardan örnek mesajlar çıkar (MongoDB/MSSQL/ES uyumlu)"""
    try:
        sample_rows = df[mask].head(n)
        messages = []
        # Mesaj sütunu öncelik sırası: full_message > raw_message > message > msg
        msg_cols = [c for c in ('full_message', 'raw_message', 'message', 'msg')
                    if c in df.columns]
        for _, row in sample_rows.iterrows():
            msg = ''
            for col in msg_cols:
                if pd.notna(row.get(col)):
                    msg = str(row[col])[:200]
                    break
            if msg:
                messages.append(msg)
        return messages
    except Exception:
        return []


# Event detector registry
EVENT_DETECTORS = {
    "auth_failure": {
        "func": _count_auth_failures,
        "threshold_key": "auth_failure_threshold",
        "alert_type": "auth_failure_spike",
        "title_template": "Authentication failure spike ({count} in {window})",
        "severity_multiplier": 1.5,  # 1.5x threshold = CRITICAL
    },
    "error_burst": {
        "func": _count_error_bursts,
        "threshold_key": "error_burst_threshold",
        "alert_type": "error_burst",
        "title_template": "Error burst ({count} errors in {window})",
        "severity_multiplier": 2.0,
    },
    "slow_query": {
        "func": _count_slow_queries,
        "threshold_key": "slow_query_threshold",
        "alert_type": "slow_query_spike",
        "title_template": "Slow query spike ({count} in {window})",
        "severity_multiplier": 2.0,
    },
    "collscan": {
        "func": _count_collscans,
        "threshold_key": "collscan_threshold",
        "alert_type": "collscan_spike",
        "title_template": "COLLSCAN spike ({count} full scans in {window})",
        "severity_multiplier": 1.5,
    },
    "drop_operation": {
        "func": _count_drop_operations,
        "threshold_key": "drop_operation_threshold",
        "alert_type": "drop_operation_alert",
        "title_template": "DROP operations detected ({count} in {window})",
        "severity_multiplier": 1.0,  # Threshold'u geçerse hemen CRITICAL
    },
    "oom": {
        "func": _count_oom_events,
        "threshold_key": "oom_threshold",
        "alert_type": "oom_alert",
        "title_template": "Out of Memory events ({count} in {window})",
        "severity_multiplier": 1.0,
    },
}

# ──────────────────────────────────────────────
# MSSQL Event Detector Registry
# ──────────────────────────────────────────────
MSSQL_EVENT_DETECTORS = {
    "failed_login": {
        "func": _count_mssql_failed_logins,
        "threshold_key": "failed_login_threshold",
        "alert_type": "mssql_failed_login_spike",
        "title_template": "MSSQL failed login spike ({count} in {window})",
        "severity_multiplier": 1.5,
    },
    "connection_error": {
        "func": _count_mssql_connection_errors,
        "threshold_key": "connection_error_threshold",
        "alert_type": "mssql_connection_error",
        "title_template": "MSSQL connection errors ({count} in {window})",
        "severity_multiplier": 2.0,
    },
    "permission_error": {
        "func": _count_mssql_permission_errors,
        "threshold_key": "permission_error_threshold",
        "alert_type": "mssql_permission_error",
        "title_template": "MSSQL permission errors ({count} in {window})",
        "severity_multiplier": 1.5,
    },
    "high_severity_error": {
        "func": _count_mssql_high_severity,
        "threshold_key": "high_severity_threshold",
        "alert_type": "mssql_high_severity_error",
        "title_template": "MSSQL high severity errors (≥17) ({count} in {window})",
        "severity_multiplier": 1.0,
    },
    "ag_error": {
        "func": _count_mssql_ag_errors,
        "threshold_key": "ag_error_threshold",
        "alert_type": "mssql_ag_error",
        "title_template": "MSSQL Availability Group errors ({count} in {window})",
        "severity_multiplier": 1.0,
    },
    "fdhost_crash": {
        "func": _count_mssql_fdhost_crash,
        "threshold_key": "fdhost_crash_threshold",
        "alert_type": "mssql_fdhost_crash",
        "title_template": "MSSQL FDHost crash events ({count} in {window})",
        "severity_multiplier": 1.0,
    },
}

# ──────────────────────────────────────────────
# Elasticsearch Event Detector Registry
# ──────────────────────────────────────────────
ES_EVENT_DETECTORS = {
    "oom": {
        "func": _count_es_oom,
        "threshold_key": "oom_threshold",
        "alert_type": "es_oom_alert",
        "title_template": "ES OutOfMemory events ({count} in {window})",
        "severity_multiplier": 1.0,
    },
    "circuit_breaker": {
        "func": _count_es_circuit_breaker,
        "threshold_key": "circuit_breaker_threshold",
        "alert_type": "es_circuit_breaker",
        "title_template": "ES circuit breaker trips ({count} in {window})",
        "severity_multiplier": 1.0,
    },
    "shard_failure": {
        "func": _count_es_shard_failure,
        "threshold_key": "shard_failure_threshold",
        "alert_type": "es_shard_failure",
        "title_template": "ES shard failures ({count} in {window})",
        "severity_multiplier": 1.5,
    },
    "gc_overhead": {
        "func": _count_es_gc_overhead,
        "threshold_key": "gc_overhead_threshold",
        "alert_type": "es_gc_overhead",
        "title_template": "ES GC overhead events ({count} in {window})",
        "severity_multiplier": 2.0,
    },
    "disk_watermark": {
        "func": _count_es_disk_watermark,
        "threshold_key": "disk_watermark_threshold",
        "alert_type": "es_disk_watermark",
        "title_template": "ES disk watermark warnings ({count} in {window})",
        "severity_multiplier": 1.0,
    },
    "master_election": {
        "func": _count_es_master_election,
        "threshold_key": "master_election_threshold",
        "alert_type": "es_master_election",
        "title_template": "ES master election events ({count} in {window})",
        "severity_multiplier": 1.0,
    },
    "connection_error": {
        "func": _count_es_connection_errors,
        "threshold_key": "connection_error_threshold",
        "alert_type": "es_connection_error",
        "title_template": "ES connection errors ({count} in {window})",
        "severity_multiplier": 2.0,
    },
    "error_burst": {
        "func": _count_es_errors,
        "threshold_key": "error_burst_threshold",
        "alert_type": "es_error_burst",
        "title_template": "ES ERROR level burst ({count} errors in {window})",
        "severity_multiplier": 2.0,
    },
}

# Source → detector registry mapping
SOURCE_DETECTOR_REGISTRY = {
    "mongodb": EVENT_DETECTORS,
    "mssql": MSSQL_EVENT_DETECTORS,
    "elasticsearch": ES_EVENT_DETECTORS,
}


class RateAlertEngine:
    """
    Sliding window bazlı event rate kontrolü.

    Kullanım:
        engine = RateAlertEngine(config)
        report = engine.check(df_enriched, server_name)

    df_enriched: Feature engineer'dan geçmiş, timestamp sütunu olan enriched DataFrame.
    Senkron çalışır, IO yapmaz.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Args:
            config: prediction.rate_alerting bloğu
        """
        self.enabled = config.get('enabled', False)
        self.windows = config.get('windows', [])
        self.cooldown_minutes = config.get('alert_cooldown_minutes', 30)
        self._last_alert_times: Dict[str, datetime] = {}  # cooldown tracking

        logger.info(f"RateAlertEngine initialized (enabled={self.enabled}, "
                     f"windows={len(self.windows)})")

    def check(self, df: pd.DataFrame, server_name: Optional[str] = None,
              source_type: str = "mongodb",
              analysis_data: Optional[Dict[str, Any]] = None) -> RateAlertReport:
        """
        Enriched DataFrame üzerinde rate-based alert kontrolü yap.

        Args:
            df: Enriched DataFrame (timestamp sütunu gerekli)
            server_name: Sunucu adı
            source_type: "mongodb", "mssql", "elasticsearch" — hangi detector
                         registry kullanılacak
            analysis_data: Opsiyonel — anomaly detection analiz sonucu.
                          Verilirse all_anomalies'deki timestamp'lar kullanılarak
                          per-window ML anomaly density hesaplanır.

        Returns:
            RateAlertReport
        """
        if not self.enabled:
            return RateAlertReport(
                server_name=server_name,
                windows_checked=0
            )

        if df is None or df.empty:
            return RateAlertReport(server_name=server_name, windows_checked=0)

        # Timestamp kontrolü
        if 'timestamp' not in df.columns:
            logger.warning("RateAlertEngine: 'timestamp' column missing, skipping rate check")
            return RateAlertReport(server_name=server_name, windows_checked=0)

        # Source-aware detector registry seçimi
        detectors = SOURCE_DETECTOR_REGISTRY.get(source_type, EVENT_DETECTORS)
        logger.debug(f"RateAlertEngine: using {source_type} registry "
                     f"({len(detectors)} detectors)")

        alerts: List[RateAlert] = []
        all_event_counts: Dict[str, Any] = {}

        # DataFrame'in zaman aralığını belirle
        try:
            ts_series = pd.to_datetime(df['timestamp'], errors='coerce')
            ts_max = ts_series.max()
            ts_min = ts_series.min()
        except Exception as e:
            logger.warning(f"RateAlertEngine: timestamp parsing failed: {e}")
            return RateAlertReport(server_name=server_name, windows_checked=0)

        if pd.isna(ts_max) or pd.isna(ts_min):
            return RateAlertReport(server_name=server_name, windows_checked=0)

        # ML anomaly timestamp'larını hazırla (per-window density için)
        # Severity-weighted: her anomaly'nin severity level'ını da taşı
        _SEVERITY_WEIGHT = {"CRITICAL": 3.0, "HIGH": 2.0, "MEDIUM": 1.0, "LOW": 0.5}
        ml_anomaly_entries = []  # [(parsed_ts, severity_level, anomaly_score)]
        ml_global_rate = 0.0
        ml_global_mean_score = 0.0
        ml_severity_dist = {}  # Genel severity dağılımı
        if analysis_data:
            try:
                ml_global_rate = float(
                    (analysis_data.get('summary') or {}).get('anomaly_rate', 0))
                score_range = (analysis_data.get('summary') or {}).get('score_range') or {}
                ml_global_mean_score = abs(float(score_range.get('mean', 0)))

                for anom in (analysis_data.get('all_anomalies') or []):
                    ts_val = anom.get('timestamp')
                    if ts_val:
                        parsed = pd.to_datetime(ts_val, errors='coerce')
                        if not pd.isna(parsed):
                            sev_level = anom.get('severity_level', 'MEDIUM')
                            a_score = abs(float(anom.get('anomaly_score', 0)))
                            ml_anomaly_entries.append((parsed, sev_level, a_score))
                            ml_severity_dist[sev_level] = ml_severity_dist.get(sev_level, 0) + 1
            except Exception as e:
                logger.debug(f"RateAlertEngine: ML timestamp parsing skipped: {e}")

        ml_anomaly_entries.sort(key=lambda x: x[0])
        # Backward compat: flat timestamp list
        ml_anomaly_timestamps = [e[0] for e in ml_anomaly_entries]

        windows_checked = 0

        for window_cfg in self.windows:
            window_name = window_cfg.get('name', 'unknown')
            window_minutes = window_cfg.get('minutes', 60)

            # Pencere başlangıcı: ts_max - window_minutes
            window_start = ts_max - timedelta(minutes=window_minutes)
            window_mask = ts_series >= window_start
            df_window = df[window_mask]

            if df_window.empty:
                continue

            windows_checked += 1
            window_counts = {}

            # Per-window ML anomaly density (severity-weighted)
            window_ml_count = 0
            window_ml_weighted_sum = 0.0
            window_ml_severity_counts = {}
            window_ml_density = 0.0
            window_ml_weighted_density = 0.0
            if ml_anomaly_entries:
                for ml_ts, sev_lvl, _a_score in ml_anomaly_entries:
                    if window_start <= ml_ts <= ts_max:
                        window_ml_count += 1
                        window_ml_weighted_sum += _SEVERITY_WEIGHT.get(sev_lvl, 1.0)
                        window_ml_severity_counts[sev_lvl] = window_ml_severity_counts.get(sev_lvl, 0) + 1
                window_total = len(df_window)
                if window_total > 0:
                    window_ml_density = (window_ml_count / window_total * 100)
                    # Weighted density: CRITICAL anomaly'ler 3x, HIGH 2x ağırlıklı
                    window_ml_weighted_density = (window_ml_weighted_sum / window_total * 100)

            for event_name, detector_cfg in detectors.items():
                threshold = window_cfg.get(detector_cfg['threshold_key'], None)
                if threshold is None:
                    continue  # Bu pencere için bu event tipi tanımlı değil

                count, samples = detector_cfg['func'](df_window)
                window_counts[event_name] = count

                if count >= threshold:
                    exceed_ratio = count / threshold
                    is_critical = exceed_ratio >= detector_cfg['severity_multiplier']
                    severity = "CRITICAL" if is_critical else "WARNING"

                    # Baseline rate-of-change: pencere dışı kalan DataFrame'den
                    # aynı event tipinin "normal" oranını hesapla
                    baseline_rate_info = ""
                    baseline_rate_per_min = 0.0
                    window_rate_per_min = count / max(window_minutes, 1)
                    df_outside = df[~window_mask]
                    if len(df_outside) >= 10:
                        outside_count, _ = detector_cfg['func'](df_outside)
                        # Pencere dışı süre (dakika)
                        outside_minutes = max(
                            (ts_max - ts_min).total_seconds() / 60 - window_minutes, 1)
                        baseline_rate_per_min = outside_count / outside_minutes
                        if baseline_rate_per_min > 0:
                            rate_change_ratio = window_rate_per_min / baseline_rate_per_min
                            if rate_change_ratio < 1.2:
                                # Pencere oranı baseline'dan çok farklı değil
                                # → Bu "normal" düzey olabilir, severity düşür
                                if severity == "CRITICAL":
                                    severity = "WARNING"
                                baseline_rate_info = (
                                    f" Pencere oranı ({window_rate_per_min:.2f}/dk) baseline "
                                    f"({baseline_rate_per_min:.2f}/dk) ile benzer "
                                    f"(x{rate_change_ratio:.1f}). Normal düzey olabilir."
                                )
                            elif rate_change_ratio >= 3.0:
                                # 3x+ artış → kesinlikle spike
                                baseline_rate_info = (
                                    f" Pencere oranı baseline'ın {rate_change_ratio:.1f}x üstünde "
                                    f"({window_rate_per_min:.2f}/dk vs {baseline_rate_per_min:.2f}/dk). "
                                    f"Belirgin spike."
                                )
                            else:
                                baseline_rate_info = (
                                    f" Baseline: {baseline_rate_per_min:.2f}/dk → "
                                    f"Pencere: {window_rate_per_min:.2f}/dk "
                                    f"(x{rate_change_ratio:.1f} artış)."
                                )

                    # Cooldown kontrolü
                    cooldown_key = f"{source_type}_{server_name}_{event_name}_{window_name}"
                    if self._is_in_cooldown(cooldown_key):
                        logger.debug(f"Rate alert in cooldown: {cooldown_key}")
                        continue

                    window_label = f"{window_minutes}dk" if window_minutes < 60 else f"{window_minutes // 60}saat"
                    title = detector_cfg['title_template'].format(
                        count=count, window=window_label
                    )

                    # ML context: pencere içi anomaly density (severity-weighted)
                    ml_ctx = None
                    ml_explain_suffix = ""
                    ml_corroborated = False
                    ml_strong_corroboration = False
                    if analysis_data and window_ml_density > 0:
                        # Temel corroboration: unweighted density > 5%
                        ml_corroborated = window_ml_density > 5.0
                        # Güçlü corroboration: weighted density > 8% VEYA
                        # pencerede CRITICAL+HIGH anomaly varsa
                        window_crit_high = (
                            window_ml_severity_counts.get('CRITICAL', 0) +
                            window_ml_severity_counts.get('HIGH', 0))
                        ml_strong_corroboration = (
                            window_ml_weighted_density > 8.0 or
                            (ml_corroborated and window_crit_high >= 2))
                        ml_ctx = {
                            "window_anomaly_count": window_ml_count,
                            "window_anomaly_density_pct": round(window_ml_density, 2),
                            "window_weighted_density_pct": round(window_ml_weighted_density, 2),
                            "window_severity_breakdown": window_ml_severity_counts.copy(),
                            "window_critical_high_count": window_crit_high,
                            "global_anomaly_rate": round(ml_global_rate, 2),
                            "global_mean_score": round(ml_global_mean_score, 4),
                            "global_severity_distribution": ml_severity_dist.copy(),
                            "ml_corroborated": ml_corroborated,
                            "ml_strong_corroboration": ml_strong_corroboration,
                            "baseline_rate_per_min": round(baseline_rate_per_min, 4),
                            "window_rate_per_min": round(window_rate_per_min, 4),
                        }
                        if ml_strong_corroboration:
                            ml_explain_suffix = (
                                f" ML modeli bu pencerede güçlü anomaly yoğunluğu tespit etti "
                                f"(%{window_ml_weighted_density:.1f} weighted density, "
                                f"{window_crit_high} CRITICAL/HIGH). Spike ML-güçlü destekli."
                            )
                        elif ml_corroborated:
                            ml_explain_suffix = (
                                f" ML modeli de bu pencerede anomaly yoğunluğu tespit etti "
                                f"(%{window_ml_density:.1f} density). Spike ML-destekli."
                            )
                        else:
                            ml_explain_suffix = (
                                f" ML anomaly density bu pencerede %{window_ml_density:.1f} — "
                                f"düşük. Spike, ML modeli tarafından güçlü şekilde desteklenmiyor."
                            )

                    # ML severity boost: ML corroborate ediyorsa ve henüz
                    # CRITICAL değilse, severity'yi yükselt
                    # Güçlü corroboration → doğrudan CRITICAL
                    # Temel corroboration → WARNING ise CRITICAL'e yükselt
                    if ml_strong_corroboration and severity == "WARNING":
                        severity = "CRITICAL"
                        ml_explain_suffix += " (ML güçlü destek → CRITICAL'e yükseltildi)"
                    elif ml_corroborated and severity == "WARNING":
                        severity = "CRITICAL"
                        ml_explain_suffix += " (ML destekli → CRITICAL'e yükseltildi)"

                    # Confidence score (0-1):
                    # - Base: exceed_ratio'ya göre (1x=0.5, 2x=0.75, 3x+=0.85)
                    # - Boost: ML corroboration varsa +0.1, güçlü ise +0.15 (max 0.99)
                    base_conf = min(0.5 + (exceed_ratio - 1) * 0.15, 0.85)
                    ml_boost = (0.15 if ml_strong_corroboration
                                else 0.1 if ml_corroborated else 0.0)
                    confidence = min(round(base_conf + ml_boost, 3), 0.99)

                    alert = RateAlert(
                        alert_type=detector_cfg['alert_type'],
                        severity=severity,
                        title=title,
                        description=f"Son {window_label} içinde {count} adet {event_name} event'i tespit edildi. "
                                    f"Eşik: {threshold}, aşım oranı: {exceed_ratio:.1f}x",
                        window_name=window_name,
                        window_minutes=window_minutes,
                        event_type=event_name,
                        event_count=count,
                        threshold=threshold,
                        exceed_ratio=round(exceed_ratio, 2),
                        time_range_start=str(window_start),
                        time_range_end=str(ts_max),
                        server_name=server_name,
                        sample_messages=samples,
                        explainability=f"{event_name} sayısı son {window_label} içinde {count} olarak ölçüldü. "
                                       f"Config eşiği: {threshold}. "
                                       f"Aşım: {exceed_ratio:.1f}x. Güven: %{confidence*100:.0f}. "
                                       f"{'CRITICAL çünkü ' + str(detector_cfg['severity_multiplier']) + 'x üstü.' if is_critical else 'WARNING seviyesinde.'}"
                                       + baseline_rate_info
                                       + ml_explain_suffix,
                        ml_context=ml_ctx,
                        confidence=confidence,
                    )
                    alerts.append(alert)
                    self._record_alert_time(cooldown_key)

            if window_ml_density > 0:
                window_counts["_ml_anomaly_density_pct"] = round(window_ml_density, 2)
                window_counts["_ml_weighted_density_pct"] = round(window_ml_weighted_density, 2)
                window_counts["_ml_anomaly_count"] = window_ml_count
                if window_ml_severity_counts:
                    window_counts["_ml_severity_breakdown"] = window_ml_severity_counts.copy()
            all_event_counts[window_name] = window_counts

        # ── Cross-window escalation ──
        # Aynı event tipi 2+ pencerede alarm veriyorsa → persistent spike
        if alerts:
            event_windows: Dict[str, List[str]] = {}
            for a in alerts:
                event_windows.setdefault(a.event_type, []).append(a.window_name)

            for evt, wins in event_windows.items():
                if len(wins) >= 2:
                    all_event_counts["_cross_window_escalation"] = all_event_counts.get(
                        "_cross_window_escalation", [])
                    all_event_counts["_cross_window_escalation"].append({
                        "event_type": evt,
                        "windows": wins,
                        "persistent": True,
                    })
                    # İlgili event'in tüm alert'lerinin severity'sini kontrol et
                    # 2+ pencerede WARNING ise → CRITICAL'e yükselt
                    for a in alerts:
                        if a.event_type == evt and a.severity == "WARNING" and len(wins) >= 2:
                            a.severity = "CRITICAL"
                            a.explainability += (
                                f" (Cross-window: {evt} {len(wins)} pencerede de eşik aştı → CRITICAL)"
                            )

        # ── Co-occurrence detection ──
        # Aynı pencerede 2+ farklı event tipi spike yapıyorsa
        if alerts:
            window_events: Dict[str, List[str]] = {}
            for a in alerts:
                window_events.setdefault(a.window_name, []).append(a.event_type)

            for win, evts in window_events.items():
                unique_evts = list(set(evts))
                if len(unique_evts) >= 2:
                    all_event_counts["_co_occurrence"] = all_event_counts.get(
                        "_co_occurrence", [])
                    all_event_counts["_co_occurrence"].append({
                        "window": win,
                        "event_types": unique_evts,
                        "count": len(unique_evts),
                    })

        report = RateAlertReport(
            server_name=server_name,
            windows_checked=windows_checked,
            alerts=alerts,
            event_counts=all_event_counts
        )

        if report.has_alerts():
            logger.warning(f"Rate alerts for {server_name or 'global'}: "
                           f"{len(alerts)} alerts across {windows_checked} windows")
        else:
            logger.info(f"Rate check for {server_name or 'global'}: "
                        f"no threshold exceeded ({windows_checked} windows checked)")

        return report

    def _is_in_cooldown(self, key: str) -> bool:
        """Alert'in cooldown süresinde olup olmadığını kontrol et"""
        last_time = self._last_alert_times.get(key)
        if last_time is None:
            return False
        elapsed = (datetime.utcnow() - last_time).total_seconds() / 60
        return elapsed < self.cooldown_minutes

    def _record_alert_time(self, key: str) -> None:
        """Alert zamanını kaydet (cooldown için)"""
        self._last_alert_times[key] = datetime.utcnow()
