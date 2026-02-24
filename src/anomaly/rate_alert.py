# src/anomaly/rate_alert.py

"""
Rate-Based Alerting - MongoDB Anomaly Detection Prediction Layer (Katman 2)

Time-window bazlı event sayacı. Feature matrix ve enriched DataFrame kullanarak
belirli event türlerinin threshold'u aşıp aşmadığını kontrol eder.

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


def _extract_samples(df: pd.DataFrame, mask: pd.Series, n: int) -> List[str]:
    """Matching log'lardan örnek mesajlar çıkar"""
    try:
        sample_rows = df[mask].head(n)
        messages = []
        for _, row in sample_rows.iterrows():
            msg = ''
            if 'full_message' in df.columns and pd.notna(row.get('full_message')):
                msg = str(row['full_message'])[:200]
            elif 'msg' in df.columns and pd.notna(row.get('msg')):
                msg = str(row['msg'])[:200]
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

    def check(self, df: pd.DataFrame, server_name: Optional[str] = None) -> RateAlertReport:
        """
        Enriched DataFrame üzerinde rate-based alert kontrolü yap.

        Args:
            df: Enriched DataFrame (timestamp sütunu gerekli)
            server_name: Sunucu adı

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

            for event_name, detector_cfg in EVENT_DETECTORS.items():
                threshold = window_cfg.get(detector_cfg['threshold_key'], None)
                if threshold is None:
                    continue  # Bu pencere için bu event tipi tanımlı değil

                count, samples = detector_cfg['func'](df_window)
                window_counts[event_name] = count

                if count >= threshold:
                    exceed_ratio = count / threshold
                    is_critical = exceed_ratio >= detector_cfg['severity_multiplier']
                    severity = "CRITICAL" if is_critical else "WARNING"

                    # Cooldown kontrolü
                    cooldown_key = f"{server_name}_{event_name}_{window_name}"
                    if self._is_in_cooldown(cooldown_key):
                        logger.debug(f"Rate alert in cooldown: {cooldown_key}")
                        continue

                    window_label = f"{window_minutes}dk" if window_minutes < 60 else f"{window_minutes // 60}saat"
                    title = detector_cfg['title_template'].format(
                        count=count, window=window_label
                    )

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
                                       f"Aşım: {exceed_ratio:.1f}x. "
                                       f"{'CRITICAL çünkü ' + str(detector_cfg['severity_multiplier']) + 'x üstü.' if is_critical else 'WARNING seviyesinde.'}"
                    )
                    alerts.append(alert)
                    self._record_alert_time(cooldown_key)

            all_event_counts[window_name] = window_counts

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
