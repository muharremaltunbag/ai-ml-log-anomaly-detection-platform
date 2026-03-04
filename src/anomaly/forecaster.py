# src/anomaly/forecaster.py

"""
Production-Grade Anomaly Forecaster — Prediction Layer (Katman 3)

Tiered multi-method forecasting:
  Tier 0  (N < min_points)  : Direction indicator only, no numeric forecast
  Tier 1  (min ≤ N < 10)    : Weighted Moving Average (WMA) + recent bias
  Tier 2  (10 ≤ N < 20)     : Linear Regression + prediction interval
  Tier 3  (N ≥ 20)          : EWMA trend decomposition + volatility-adjusted confidence

Cross-source (MongoDB / MSSQL / Elasticsearch) metric registry.
Pure Python — no numpy/scipy/pandas dependency.

Mevcut pipeline'dan tamamen izole. Çağrılmazsa hiçbir şey bozulmaz.
Feature flag: config.prediction.forecasting.enabled

Kullanım:
    forecaster = AnomalyForecaster(config)
    report = forecaster.forecast(history_records, current_analysis, server_name, source_type)
"""

import logging
import math
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, asdict, field

logger = logging.getLogger(__name__)


# Source type normalization map
_SOURCE_TYPE_MAP = {
    "opensearch": "mongodb",
    "mssql_opensearch": "mssql",
    "elasticsearch_opensearch": "elasticsearch",
    "mongodb": "mongodb",
    "mssql": "mssql",
    "elasticsearch": "elasticsearch",
}


def _normalize_source_type(raw: str) -> str:
    """Storage-level source type → prediction module source type."""
    return _SOURCE_TYPE_MAP.get(raw.lower().strip(), raw.lower().strip())


# ═══════════════════════════════════════════════════════════
# Data Classes (public API — backward compatible)
# ═══════════════════════════════════════════════════════════

@dataclass
class ForecastAlert:
    """Tek bir forecast alert"""
    alert_type: str          # "forecast_anomaly_rate_rising", ...
    severity: str            # "INFO", "WARNING", "CRITICAL"
    title: str
    description: str
    metric_name: str
    current_value: float
    forecast_value: float
    forecast_horizon_hours: int
    trend_slope: float
    confidence: float        # 0-1 arası güven skoru
    data_points_used: int
    server_name: Optional[str] = None
    timestamp: str = ""
    explainability: str = ""
    forecast_method: str = ""
    volatility: float = 0.0
    upper_bound: float = 0.0
    lower_bound: float = 0.0
    change_point_detected: bool = False

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ForecastReport:
    """Forecasting raporu"""
    server_name: Optional[str]
    data_points: int
    forecast_horizon_hours: int
    forecasts: Dict[str, Any] = field(default_factory=dict)
    alerts: List[ForecastAlert] = field(default_factory=list)
    model_tier: str = ""
    change_points: List[Dict] = field(default_factory=list)
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat()

    def has_alerts(self) -> bool:
        return len(self.alerts) > 0

    def max_severity(self) -> str:
        if not self.alerts:
            return "OK"
        severity_order = {"INFO": 0, "WARNING": 1, "CRITICAL": 2}
        return max(self.alerts, key=lambda a: severity_order.get(a.severity, 0)).severity

    def summary(self) -> Dict[str, Any]:
        """Tüm metriklerin toplu risk/confidence/yön özeti."""
        if not self.forecasts:
            return {"overall_risk": "OK", "metrics_assessed": 0}

        confidences = []
        directions: Dict[str, int] = {}
        for metric_data in self.forecasts.values():
            if isinstance(metric_data, dict):
                conf = metric_data.get("confidence")
                if conf is not None and isinstance(conf, (int, float)):
                    confidences.append(conf)
                d = metric_data.get("direction", "unknown")
                directions[d] = directions.get(d, 0) + 1

        avg_conf = sum(confidences) / len(confidences) if confidences else 0

        return {
            "overall_risk": self.max_severity(),
            "alert_count": len(self.alerts),
            "metrics_assessed": len(self.forecasts),
            "avg_confidence": round(avg_conf, 4),
            "direction_distribution": {k: v for k, v in directions.items() if v > 0},
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "server_name": self.server_name,
            "data_points": self.data_points,
            "forecast_horizon_hours": self.forecast_horizon_hours,
            "forecasts": self.forecasts,
            "alerts": [a.to_dict() for a in self.alerts],
            "model_tier": self.model_tier,
            "change_points": self.change_points,
            "timestamp": self.timestamp,
            "max_severity": self.max_severity(),
            "has_alerts": self.has_alerts(),
            "summary": self.summary(),
        }


# ═══════════════════════════════════════════════════════════
# Pure Math — zero external dependency
# ═══════════════════════════════════════════════════════════

def _linear_regression(x: List[float], y: List[float]) -> Tuple[float, float, float]:
    """y = slope * x + intercept.  Returns (slope, intercept, r_squared)."""
    n = len(x)
    if n < 2:
        return 0.0, y[0] if y else 0.0, 0.0

    sx = sum(x)
    sy = sum(y)
    sxy = sum(a * b for a, b in zip(x, y))
    sx2 = sum(a * a for a in x)

    denom = n * sx2 - sx * sx
    if denom == 0:
        return 0.0, sy / n, 0.0

    slope = (n * sxy - sx * sy) / denom
    intercept = (sy - slope * sx) / n

    y_mean = sy / n
    ss_tot = sum((yi - y_mean) ** 2 for yi in y)
    ss_res = sum((yi - (slope * xi + intercept)) ** 2 for xi, yi in zip(x, y))
    r2 = max(0.0, min(1.0, 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 0.0))
    return slope, intercept, r2


def _weighted_moving_average(values: List[float], weights: Optional[List[float]] = None) -> float:
    """Ağırlıklı hareketli ortalama.  weights=None ise linearly-increasing."""
    n = len(values)
    if n == 0:
        return 0.0
    if n == 1:
        return values[0]
    if weights is None:
        weights = [float(i + 1) for i in range(n)]
    tw = sum(weights)
    if tw == 0:
        return sum(values) / n
    return sum(v * w for v, w in zip(values, weights)) / tw


def _ewma(values: List[float], alpha: float = 0.3) -> List[float]:
    """Exponentially Weighted Moving Average series."""
    if not values:
        return []
    result = [values[0]]
    for i in range(1, len(values)):
        result.append(alpha * values[i] + (1 - alpha) * result[-1])
    return result


def _std_dev(values: List[float]) -> float:
    """Sample standard deviation."""
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    return math.sqrt(sum((v - mean) ** 2 for v in values) / (n - 1))


def _coefficient_of_variation(values: List[float]) -> float:
    """CV = std / |mean|.  Volatility measure: 0 = stable, high = volatile."""
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    if mean == 0:
        return 0.0
    return _std_dev(values) / abs(mean)


def _robust_baseline(values: List[float]) -> Tuple[float, float]:
    """
    Outlier-resistant baseline: median + IQR-based bounds.

    Spike'lara dirençli bir baseline hesaplar. Simple mean yerine:
    1. Median kullanır (outlier'a dayanıklı)
    2. IQR ile extreme değerleri filtreleyerek "temiz ortalama" hesaplar

    Returns:
        (baseline, spread) — baseline: temiz merkezi değer, spread: IQR/2
    """
    if not values:
        return 0.0, 0.0
    if len(values) == 1:
        return values[0], 0.0

    sorted_v = sorted(values)
    n = len(sorted_v)

    # Median
    if n % 2 == 0:
        median = (sorted_v[n // 2 - 1] + sorted_v[n // 2]) / 2
    else:
        median = sorted_v[n // 2]

    if n < 4:
        # Çok az veri varsa sadece median döndür
        return median, _std_dev(values) if n >= 2 else 0.0

    # Q1, Q3 (quartiles)
    q1_idx = n // 4
    q3_idx = (3 * n) // 4
    q1 = sorted_v[q1_idx]
    q3 = sorted_v[q3_idx]
    iqr = q3 - q1

    # IQR-filtered mean: sadece Q1 - 1.5*IQR … Q3 + 1.5*IQR aralığındaki değerler
    lower_fence = q1 - 1.5 * iqr
    upper_fence = q3 + 1.5 * iqr
    filtered = [v for v in values if lower_fence <= v <= upper_fence]

    if filtered:
        baseline = sum(filtered) / len(filtered)
    else:
        baseline = median

    return baseline, iqr / 2 if iqr > 0 else _std_dev(values)


def _hourly_seasonality_adjustment(records_asc: List[Dict[str, Any]],
                                    values: List[float],
                                    forecast_hour: Optional[int] = None) -> float:
    """
    Saatlik mevsimsellik düzeltme katsayısı.

    Her kaydın timestamp'inden saat bilgisini çıkarır, saatlere göre ortalama değer
    hesaplar, sonra forecast hedef saatinin genel ortalamaya oranını döndürür.

    Returns:
        Düzeltme katsayısı (1.0 = düzeltme yok). Örn: 1.3 → %30 artış beklenir.
        Yeterli veri yoksa veya saat bilgisi yoksa 1.0 döner.
    """
    if len(values) < 8 or forecast_hour is None:
        return 1.0

    hourly_buckets: Dict[int, List[float]] = {}
    for rec, val in zip(records_asc, values):
        ts = rec.get('timestamp') or rec.get('analysis_timestamp')
        if not ts:
            continue
        try:
            if isinstance(ts, str):
                dt = datetime.fromisoformat(ts.replace('Z', '').split('+')[0])
            elif isinstance(ts, datetime):
                dt = ts
            else:
                continue
            hour = dt.hour
            hourly_buckets.setdefault(hour, []).append(val)
        except (ValueError, TypeError):
            continue

    if len(hourly_buckets) < 3:
        return 1.0

    hourly_means: Dict[int, float] = {}
    for h, vals in hourly_buckets.items():
        hourly_means[h] = sum(vals) / len(vals)

    global_mean = sum(values) / len(values)
    if global_mean <= 0:
        return 1.0

    target_mean = hourly_means.get(forecast_hour)
    if target_mean is None:
        # Forecast hedef saati için veri yoksa, en yakın saat aralığının ortalamasını al
        nearby = [hourly_means[h] for h in hourly_means
                  if abs(h - forecast_hour) <= 2 or abs(h - forecast_hour) >= 22]
        if not nearby:
            return 1.0
        target_mean = sum(nearby) / len(nearby)

    ratio = target_mean / global_mean
    # Aşırı sapmaları sınırla: [0.5, 2.0]
    return max(0.5, min(2.0, ratio))


def _cusum_change_points(values: List[float], threshold: float = 3.0) -> List[int]:
    """
    CUSUM (Cumulative Sum) change-point detection.
    Returns list of indices where a regime shift is detected.
    """
    if len(values) < 4:
        return []
    mean = sum(values) / len(values)
    std = _std_dev(values)
    if std == 0:
        return []

    drift = std * 0.5
    pos, neg = 0.0, 0.0
    cps: List[int] = []
    for i in range(1, len(values)):
        dev = values[i] - mean
        pos = max(0, pos + dev - drift)
        neg = max(0, neg - dev - drift)
        if pos > threshold * std or neg > threshold * std:
            cps.append(i)
            pos, neg = 0.0, 0.0
    return cps


def _residual_consistency(values: List[float], slope: float, intercept: float) -> float:
    """Residual consistency score (0-1). Model fit kalitesini ölçer.

    Durbin-Watson yaklaşımı ile otokorelasyon ve son residual'larda
    sistematik bias tespit eder. Düşük skor → düşük güvenilirlik.
    """
    n = len(values)
    if n < 4:
        return 0.5

    x = list(range(n))
    residuals = [values[i] - (slope * x[i] + intercept) for i in range(n)]

    # Durbin-Watson: DW ≈ 2 → otokorelasyon yok
    sum_diff_sq = sum((residuals[i] - residuals[i - 1]) ** 2 for i in range(1, n))
    sum_res_sq = sum(r ** 2 for r in residuals)
    if sum_res_sq == 0:
        return 1.0
    dw = sum_diff_sq / sum_res_sq
    dw_score = max(0.0, 1.0 - abs(dw - 2.0) / 2.0)

    # Recent bias: son 3 residual hep aynı işaretse → model sapıyor
    recent_res = residuals[-3:]
    all_same_sign = all(r > 0 for r in recent_res) or all(r < 0 for r in recent_res)
    bias_penalty = 0.15 if all_same_sign else 0.0

    return max(0.0, min(1.0, dw_score - bias_penalty))


def _prediction_interval(values: List[float], slope: float, intercept: float,
                          forecast_x: float, confidence: float = 0.95) -> Tuple[float, float]:
    """Linear regression prediction interval.  Returns (lower, upper)."""
    n = len(values)
    if n < 3:
        mean_v = sum(values) / n if n else 0
        spread = max(abs(v - mean_v) for v in values) if values else 0
        return max(0.0, mean_v - spread * 2), mean_v + spread * 2

    x = list(range(n))
    x_mean = sum(x) / n
    residuals = [values[i] - (slope * x[i] + intercept) for i in range(n)]
    se = math.sqrt(sum(r ** 2 for r in residuals) / (n - 2))
    t_val = 2.0 if confidence >= 0.95 else 1.65

    sx2 = sum((xi - x_mean) ** 2 for xi in x)
    if sx2 == 0:
        margin = t_val * se * 2
    else:
        margin = t_val * se * math.sqrt(1 + 1 / n + (forecast_x - x_mean) ** 2 / sx2)

    point = slope * forecast_x + intercept
    return max(0.0, point - margin), point + margin


# ═══════════════════════════════════════════════════════════
# Cross-Source Metric Extractors
# anomaly_history document → Optional[float]
# ═══════════════════════════════════════════════════════════

def _extract_anomaly_rate(record: Dict[str, Any]) -> Optional[float]:
    """anomaly_rate — tüm kaynaklar"""
    rate = record.get('anomaly_rate')
    if rate is None:
        rate = (record.get('summary') or {}).get('anomaly_rate')
    return float(rate) if rate is not None else None


def _extract_anomaly_count(record: Dict[str, Any]) -> Optional[float]:
    """n_anomalies — tüm kaynaklar"""
    count = record.get('anomaly_count')
    if count is None:
        count = (record.get('summary') or {}).get('n_anomalies')
    return float(count) if count is not None else None


def _extract_critical_ratio(record: Dict[str, Any]) -> Optional[float]:
    """CRITICAL+HIGH / total anomali oranı (%) — tüm kaynaklar"""
    dist = record.get('severity_distribution') or {}
    if not dist:
        return None
    total = sum(v for v in dist.values() if isinstance(v, (int, float)))
    if total == 0:
        return None
    critical = (dist.get('CRITICAL') or 0) + (dist.get('HIGH') or 0)
    return (critical / total) * 100


def _extract_critical_count(record: Dict[str, Any]) -> Optional[float]:
    """Kritik anomali sayısı (CRITICAL+HIGH) — tüm kaynaklar"""
    dist = record.get('severity_distribution') or {}
    if not dist:
        cc = record.get('critical_count')
        return float(cc) if cc is not None else None
    return float((dist.get('CRITICAL') or 0) + (dist.get('HIGH') or 0))


def _extract_error_rate(record: Dict[str, Any]) -> Optional[float]:
    """component_analysis'ten toplam anomaly count — tüm kaynaklar"""
    comp = record.get('component_analysis') or {}
    if not comp:
        return None
    total = sum((c.get('anomaly_count') or 0) for c in comp.values() if isinstance(c, dict))
    return float(total)


def _extract_mean_anomaly_score(record: Dict[str, Any]) -> Optional[float]:
    """IsolationForest mean anomaly score (abs). Daha yüksek = daha anomalous.

    History record'larda score_range top-level veya summary altında bulunabilir.
    abs() kullanılır çünkü raw skor negatiftir (-1.0 = anomaly, 0 = normal).
    """
    sr = record.get('score_range') or (record.get('summary') or {}).get('score_range') or {}
    mean = sr.get('mean')
    if mean is not None and isinstance(mean, (int, float)):
        return abs(float(mean))
    return None


def _extract_slow_query_count(record: Dict[str, Any]) -> Optional[float]:
    """Slow query sayısı — MongoDB specific"""
    perf = record.get('performance_alerts') or {}
    sq = perf.get('slow_queries') or {}
    if isinstance(sq, dict) and sq.get('count') is not None:
        return float(sq['count'])
    return None


def _extract_collscan_count(record: Dict[str, Any]) -> Optional[float]:
    """COLLSCAN sayısı — MongoDB specific"""
    perf = record.get('performance_alerts') or {}
    cs = perf.get('collscans') or perf.get('COLLSCAN') or {}
    if isinstance(cs, dict) and cs.get('count') is not None:
        return float(cs['count'])
    return None


def _extract_auth_failure_count(record: Dict[str, Any]) -> Optional[float]:
    """Authentication failure count — MongoDB / MSSQL"""
    sec = record.get('security_alerts') or {}
    if isinstance(sec, dict):
        for key in ('auth_failures', 'authentication_failures'):
            sub = sec.get(key)
            if isinstance(sub, dict) and sub.get('count') is not None:
                return float(sub['count'])
    mssql = record.get('mssql_specific') or {}
    if isinstance(mssql, dict):
        for key in ('failed_logins', 'failed_login_count'):
            val = mssql.get(key)
            if isinstance(val, (int, float)):
                return float(val)
        # mssql_specific.login_analysis.failed_logins
        login_analysis = mssql.get('login_analysis') or {}
        if isinstance(login_analysis, dict):
            fl = login_analysis.get('failed_logins')
            if isinstance(fl, (int, float)):
                return float(fl)
    return None


# ──────────────────────────────────────────────
# ES-specific Metric Extractors
# es_specific.critical_patterns.is_* → {total, anomalous}
# ──────────────────────────────────────────────

def _es_pattern_count(record: Dict[str, Any], pattern_key: str) -> Optional[float]:
    """Helper: es_specific.critical_patterns'dan total count çek"""
    es = record.get('es_specific') or {}
    patterns = es.get('critical_patterns') or {}
    entry = patterns.get(pattern_key)
    if isinstance(entry, dict) and entry.get('total') is not None:
        return float(entry['total'])
    return None


def _extract_es_oom_count(record: Dict[str, Any]) -> Optional[float]:
    """ES OOM event sayısı"""
    return _es_pattern_count(record, 'is_oom_error')


def _extract_es_circuit_breaker_count(record: Dict[str, Any]) -> Optional[float]:
    """ES circuit breaker trip sayısı"""
    return _es_pattern_count(record, 'is_circuit_breaker')


def _extract_es_shard_failure_count(record: Dict[str, Any]) -> Optional[float]:
    """ES shard failure sayısı"""
    return _es_pattern_count(record, 'is_shard_failure')


def _extract_es_gc_overhead_count(record: Dict[str, Any]) -> Optional[float]:
    """ES GC overhead event sayısı"""
    return _es_pattern_count(record, 'is_gc_overhead')


def _extract_es_disk_watermark_count(record: Dict[str, Any]) -> Optional[float]:
    """ES disk watermark uyarı sayısı"""
    return _es_pattern_count(record, 'is_high_disk_watermark')


def _extract_es_master_election_count(record: Dict[str, Any]) -> Optional[float]:
    """ES master election event sayısı"""
    return _es_pattern_count(record, 'is_master_election')


def _extract_es_connection_error_count(record: Dict[str, Any]) -> Optional[float]:
    """ES connection error sayısı"""
    return _es_pattern_count(record, 'is_connection_error')


# ──────────────────────────────────────────────
# MSSQL-specific Metric Extractors (ek)
# ──────────────────────────────────────────────

def _extract_mssql_high_severity_count(record: Dict[str, Any]) -> Optional[float]:
    """MSSQL Severity >= 17 hata sayısı"""
    mssql = record.get('mssql_specific') or {}
    errorlog = mssql.get('errorlog_analysis') or {}
    if isinstance(errorlog, dict):
        val = errorlog.get('high_severity_errors')
        if isinstance(val, (int, float)):
            return float(val)
    return None


def _extract_mssql_connection_error_count(record: Dict[str, Any]) -> Optional[float]:
    """MSSQL connection error sayısı"""
    mssql = record.get('mssql_specific') or {}
    if isinstance(mssql, dict):
        val = mssql.get('connection_error_count')
        if isinstance(val, (int, float)):
            return float(val)
    return None


# ═══════════════════════════════════════════════════════════
# Metric Registry — source-aware
# ═══════════════════════════════════════════════════════════

COMMON_METRICS: Dict[str, Dict[str, Any]] = {
    "anomaly_rate": {
        "func": _extract_anomaly_rate,
        "label": "Anomali Oranı",
        "unit": "%",
        "warning_pct_above_baseline": 50.0,
        "critical_pct_above_baseline": 100.0,
        "min_absolute_for_alert": 0.5,
    },
    "anomaly_count": {
        "func": _extract_anomaly_count,
        "label": "Anomali Sayısı",
        "unit": " adet",
        "warning_pct_above_baseline": 80.0,
        "critical_pct_above_baseline": 150.0,
        "min_absolute_for_alert": 3,
    },
    "critical_ratio": {
        "func": _extract_critical_ratio,
        "label": "Kritik Anomali Oranı",
        "unit": "%",
        "warning_pct_above_baseline": 30.0,
        "critical_pct_above_baseline": 80.0,
        "min_absolute_for_alert": 5.0,
    },
    "critical_count": {
        "func": _extract_critical_count,
        "label": "Kritik Anomali Sayısı",
        "unit": " adet",
        "warning_pct_above_baseline": 50.0,
        "critical_pct_above_baseline": 100.0,
        "min_absolute_for_alert": 2,
    },
    "error_count": {
        "func": _extract_error_rate,
        "label": "Error Sayısı",
        "unit": " adet",
        "warning_pct_above_baseline": 60.0,
        "critical_pct_above_baseline": 120.0,
        "min_absolute_for_alert": 3,
    },
    "mean_anomaly_score": {
        "func": _extract_mean_anomaly_score,
        "label": "ML Anomaly Skoru (ort.)",
        "unit": "",
        "warning_pct_above_baseline": 40.0,
        "critical_pct_above_baseline": 80.0,
        "min_absolute_for_alert": 0.15,
    },
}

MONGODB_METRICS: Dict[str, Dict[str, Any]] = {
    "slow_query_count": {
        "func": _extract_slow_query_count,
        "label": "Yavaş Sorgu Sayısı",
        "unit": " adet",
        "warning_pct_above_baseline": 60.0,
        "critical_pct_above_baseline": 120.0,
        "min_absolute_for_alert": 5,
    },
    "collscan_count": {
        "func": _extract_collscan_count,
        "label": "COLLSCAN Sayısı",
        "unit": " adet",
        "warning_pct_above_baseline": 50.0,
        "critical_pct_above_baseline": 100.0,
        "min_absolute_for_alert": 3,
    },
    "auth_failure_count": {
        "func": _extract_auth_failure_count,
        "label": "Auth Failure Sayısı",
        "unit": " adet",
        "warning_pct_above_baseline": 40.0,
        "critical_pct_above_baseline": 80.0,
        "min_absolute_for_alert": 5,
    },
}

MSSQL_METRICS: Dict[str, Dict[str, Any]] = {
    "auth_failure_count": {
        "func": _extract_auth_failure_count,
        "label": "Failed Login Sayısı",
        "unit": " adet",
        "warning_pct_above_baseline": 40.0,
        "critical_pct_above_baseline": 80.0,
        "min_absolute_for_alert": 5,
    },
    "high_severity_count": {
        "func": _extract_mssql_high_severity_count,
        "label": "Yüksek Severity Hata Sayısı",
        "unit": " adet",
        "warning_pct_above_baseline": 50.0,
        "critical_pct_above_baseline": 100.0,
        "min_absolute_for_alert": 3,
    },
    "connection_error_count": {
        "func": _extract_mssql_connection_error_count,
        "label": "Connection Error Sayısı",
        "unit": " adet",
        "warning_pct_above_baseline": 60.0,
        "critical_pct_above_baseline": 120.0,
        "min_absolute_for_alert": 5,
    },
}

ES_METRICS: Dict[str, Dict[str, Any]] = {
    "oom_count": {
        "func": _extract_es_oom_count,
        "label": "OOM Event Sayısı",
        "unit": " adet",
        "warning_pct_above_baseline": 30.0,
        "critical_pct_above_baseline": 80.0,
        "min_absolute_for_alert": 1,
    },
    "circuit_breaker_count": {
        "func": _extract_es_circuit_breaker_count,
        "label": "Circuit Breaker Sayısı",
        "unit": " adet",
        "warning_pct_above_baseline": 40.0,
        "critical_pct_above_baseline": 100.0,
        "min_absolute_for_alert": 2,
    },
    "shard_failure_count": {
        "func": _extract_es_shard_failure_count,
        "label": "Shard Failure Sayısı",
        "unit": " adet",
        "warning_pct_above_baseline": 50.0,
        "critical_pct_above_baseline": 100.0,
        "min_absolute_for_alert": 3,
    },
    "gc_overhead_count": {
        "func": _extract_es_gc_overhead_count,
        "label": "GC Overhead Sayısı",
        "unit": " adet",
        "warning_pct_above_baseline": 60.0,
        "critical_pct_above_baseline": 120.0,
        "min_absolute_for_alert": 5,
    },
    "disk_watermark_count": {
        "func": _extract_es_disk_watermark_count,
        "label": "Disk Watermark Uyarı Sayısı",
        "unit": " adet",
        "warning_pct_above_baseline": 30.0,
        "critical_pct_above_baseline": 80.0,
        "min_absolute_for_alert": 2,
    },
    "master_election_count": {
        "func": _extract_es_master_election_count,
        "label": "Master Election Sayısı",
        "unit": " adet",
        "warning_pct_above_baseline": 30.0,
        "critical_pct_above_baseline": 80.0,
        "min_absolute_for_alert": 2,
    },
    "connection_error_count": {
        "func": _extract_es_connection_error_count,
        "label": "Connection Error Sayısı",
        "unit": " adet",
        "warning_pct_above_baseline": 60.0,
        "critical_pct_above_baseline": 120.0,
        "min_absolute_for_alert": 5,
    },
}

SOURCE_METRIC_SETS: Dict[str, Dict[str, Dict[str, Any]]] = {
    "mongodb": {**COMMON_METRICS, **MONGODB_METRICS},
    "mssql": {**COMMON_METRICS, **MSSQL_METRICS},
    "elasticsearch": {**COMMON_METRICS, **ES_METRICS},
    "default": COMMON_METRICS,
}


# ═══════════════════════════════════════════════════════════
# Tier Implementations
# ═══════════════════════════════════════════════════════════

def _forecast_tier0(values: List[float]) -> Dict[str, Any]:
    """Tier 0: yön göstergesi — N < min_data_points.  Sayısal tahmin yok."""
    if not values:
        return {"method": "tier0_no_data", "direction": "unknown", "confidence": 0.0}
    if len(values) == 1:
        return {"method": "tier0_single_point", "direction": "unknown",
                "current_value": values[-1], "confidence": 0.0}
    recent, prev = values[-1], values[-2]
    if recent > prev * 1.05:
        direction = "rising"
    elif recent < prev * 0.95:
        direction = "falling"
    else:
        direction = "stable"
    return {"method": "tier0_direction_only", "direction": direction,
            "current_value": recent, "previous_value": prev, "confidence": 0.1}


def _forecast_tier1(values: List[float], steps_ahead: float) -> Dict[str, Any]:
    """Tier 1: WMA + recent trend projection.  5 ≤ N < 10."""
    n = len(values)
    wma = _weighted_moving_average(values)
    current = values[-1]
    recent_3 = values[-3:] if n >= 3 else values
    trend_per_step = (recent_3[-1] - recent_3[0]) / max(len(recent_3) - 1, 1)
    forecast_value = max(0.0, current + trend_per_step * steps_ahead)
    volatility = _coefficient_of_variation(values)
    # Volatility penalty: noisy data → lower confidence
    vol_factor = max(0.5, 1.0 - min(volatility, 1.0) * 0.4)
    confidence = min(0.4, 0.2 + n * 0.03) * vol_factor
    spread = _std_dev(values) * 2
    return {
        "method": "tier1_wma", "forecast_value": forecast_value,
        "wma_value": wma, "trend_per_step": trend_per_step,
        "slope": trend_per_step,
        "volatility": volatility, "confidence": confidence,
        "upper_bound": forecast_value + spread,
        "lower_bound": max(0.0, forecast_value - spread),
        "direction": "rising" if trend_per_step > 0.001 else (
            "falling" if trend_per_step < -0.001 else "stable"),
    }


def _forecast_tier2(values: List[float], steps_ahead: float,
                     confidence_level: float = 0.95) -> Dict[str, Any]:
    """Tier 2: Linear Regression + prediction interval.  10 ≤ N < 20."""
    x = list(range(len(values)))
    slope, intercept, r2 = _linear_regression(x, values)
    forecast_x = len(values) - 1 + steps_ahead
    forecast_value = max(0.0, slope * forecast_x + intercept)
    lower, upper = _prediction_interval(values, slope, intercept, forecast_x, confidence_level)
    volatility = _coefficient_of_variation(values)
    # Residual consistency + volatility penalty
    res_consistency = _residual_consistency(values, slope, intercept)
    base_conf = r2 * 0.5 + len(values) * 0.01 + res_consistency * 0.15
    vol_factor = max(0.5, 1.0 - min(volatility, 1.0) * 0.3)
    confidence = min(0.7, base_conf) * vol_factor
    return {
        "method": "tier2_linear_regression", "forecast_value": forecast_value,
        "slope": slope, "intercept": intercept, "r_squared": r2,
        "volatility": volatility, "confidence": confidence,
        "upper_bound": upper, "lower_bound": lower,
        "direction": "rising" if slope > 0.001 else (
            "falling" if slope < -0.001 else "stable"),
    }


def _forecast_tier3(values: List[float], steps_ahead: float,
                     confidence_level: float = 0.95,
                     ewma_fast_alpha: float = 0.3,
                     ewma_slow_alpha: float = 0.1) -> Dict[str, Any]:
    """
    Tier 3: EWMA trend decomposition + volatility-adjusted confidence.  N ≥ 20.
    İki EWMA (fast/slow), momentum = fast − slow.
    """
    n = len(values)
    ewma_fast = _ewma(values, alpha=ewma_fast_alpha)
    ewma_slow = _ewma(values, alpha=ewma_slow_alpha)
    momentum = ewma_fast[-1] - ewma_slow[-1]

    half = max(10, n // 2)
    recent = values[-half:]
    x_r = list(range(len(recent)))
    slope, intercept, r2 = _linear_regression(x_r, recent)

    ewma_current = ewma_fast[-1]
    structural_delta = slope * steps_ahead
    momentum_delta = momentum * steps_ahead * 0.5
    forecast_value = max(0.0, ewma_current + structural_delta + momentum_delta)

    volatility = _coefficient_of_variation(values)
    std = _std_dev(values)
    vol_spread = std * (1 + volatility) * math.sqrt(max(steps_ahead, 1))
    upper = forecast_value + vol_spread * 2
    lower = max(0.0, forecast_value - vol_spread * 2)

    change_points = _cusum_change_points(values)
    res_consistency = _residual_consistency(recent, slope, intercept)
    # Recent change-point penalty: son 5 değerde CP varsa model güvenilirliği düşer
    cp_penalty = 0.0
    if change_points and change_points[-1] > n - 5:
        cp_penalty = min(0.15, len([cp for cp in change_points if cp > n - 5]) * 0.07)
    base_conf = (r2 * 0.4
                 + min(n, 50) * 0.005
                 + (1 - min(volatility, 1.0)) * 0.2
                 + res_consistency * 0.1)
    confidence = max(0.1, min(0.9, base_conf - cp_penalty))

    if slope > 0.001 and momentum > 0:
        direction = "rising"
    elif slope < -0.001 and momentum < 0:
        direction = "falling"
    elif momentum > std * 0.5:
        direction = "accelerating"
    elif momentum < -std * 0.5:
        direction = "decelerating"
    else:
        direction = "stable"

    return {
        "method": "tier3_ewma_decomposition", "forecast_value": forecast_value,
        "ewma_fast": ewma_fast[-1], "ewma_slow": ewma_slow[-1],
        "momentum": momentum, "slope": slope, "r_squared": r2,
        "volatility": volatility, "confidence": confidence,
        "upper_bound": upper, "lower_bound": lower,
        "change_points": change_points, "direction": direction,
    }


def _select_and_run_tier(values: List[float], min_points: int,
                          steps_ahead: float,
                          confidence_level: float = 0.95,
                          seasonality_factor: float = 1.0,
                          ewma_fast_alpha: float = 0.3,
                          ewma_slow_alpha: float = 0.1) -> Dict[str, Any]:
    """Veri miktarına göre tier seç ve çalıştır. Seasonality katsayısı uygulanır."""
    n = len(values)
    if n < min_points:
        return _forecast_tier0(values)
    elif n < 10:
        result = _forecast_tier1(values, steps_ahead)
    elif n < 20:
        result = _forecast_tier2(values, steps_ahead, confidence_level)
    else:
        result = _forecast_tier3(values, steps_ahead, confidence_level,
                                  ewma_fast_alpha, ewma_slow_alpha)

    # Seasonality adjustment (Tier 1+ için)
    if seasonality_factor != 1.0 and "forecast_value" in result:
        fv = result["forecast_value"]
        result["forecast_value"] = max(0.0, fv * seasonality_factor)
        result["upper_bound"] = result.get("upper_bound", 0) * seasonality_factor
        result["lower_bound"] = max(0.0, result.get("lower_bound", 0) * seasonality_factor)
        result["seasonality_factor"] = round(seasonality_factor, 4)

    return result


# ═══════════════════════════════════════════════════════════
# Explainability Engine
# ═══════════════════════════════════════════════════════════

def _tier_method_label(method: str) -> str:
    """Tier method string → insan-okunabilir etiket."""
    labels = {
        "tier0_no_data": "Veri Yetersiz",
        "tier0_single_point": "Veri Yetersiz",
        "tier0_direction_only": "Tier 0 — Yön Göstergesi",
        "tier1_wma": "Tier 1 — Ağırlıklı Ortalama",
        "tier2_linear_regression": "Tier 2 — Lineer Regresyon",
        "tier3_ewma_decomposition": "Tier 3 — EWMA Trend Ayrıştırma",
    }
    return labels.get(method, method)


def _build_explanation(metric_cfg: Dict, tier_result: Dict,
                        values: List[float], horizon_hours: int,
                        server_name: Optional[str],
                        min_data_points: int = 5) -> str:
    """İnsan-okunabilir forecast açıklaması."""
    method = tier_result.get("method", "unknown")
    direction = tier_result.get("direction", "unknown")
    confidence = tier_result.get("confidence", 0)
    current = values[-1] if values else 0
    fv = tier_result.get("forecast_value")
    label = metric_cfg.get("label", "Metrik")
    unit = metric_cfg.get("unit", "")
    srv = f" ({server_name})" if server_name else ""
    parts: List[str] = []

    if "tier0" in method:
        needed = max(0, min_data_points - len(values))
        parts.append(
            f"{label}{srv}: Henüz yeterli geçmiş veri yok ({len(values)} nokta). "
            f"Mevcut değer: {current:.2f}{unit}. Yön: {direction}. "
            f"Sayısal tahmin için {needed} analiz daha gerekli "
            f"(min. {min_data_points} nokta)."
        )
    else:
        parts.append(
            f"{label}{srv}: {len(values)} geçmiş analiz kullanıldı. "
            f"Mevcut: {current:.2f}{unit}."
        )
        if fv is not None:
            lb = tier_result.get('lower_bound', 0)
            ub = tier_result.get('upper_bound', 0)
            parts.append(
                f"Tahmini ({horizon_hours}h sonra): {fv:.2f}{unit} "
                f"[{lb:.2f} – {ub:.2f}]."
            )
        method_labels = {
            "tier1_wma": "Ağırlıklı Hareketli Ortalama (son veriler ağırlıklı)",
            "tier2_linear_regression": f"Lineer Regresyon (R²={tier_result.get('r_squared', 0):.2f})",
            "tier3_ewma_decomposition": (
                f"EWMA Trend Decomposition "
                f"(momentum={tier_result.get('momentum', 0):.3f}, "
                f"R²={tier_result.get('r_squared', 0):.2f})"
            ),
        }
        parts.append(f"Yöntem: {method_labels.get(method, method)}.")

        vol = tier_result.get("volatility", 0)
        if vol > 0.5:
            parts.append(f"Yüksek dalgalanma (CV={vol:.2f}), tahmin güvenilirliği düşük.")
        elif vol > 0.2:
            parts.append(f"Orta seviye dalgalanma (CV={vol:.2f}).")

        dir_labels = {
            "rising": "Yükseliş trendi devam ediyor.",
            "falling": "Düşüş trendi devam ediyor.",
            "stable": "Stabil seyir.",
            "accelerating": "Artış hızlanıyor — dikkat.",
            "decelerating": "Artış yavaşlıyor.",
        }
        parts.append(dir_labels.get(direction, ""))

        cps = tier_result.get("change_points", [])
        if cps:
            idx_str = ", #".join(str(c) for c in cps[-3:])
            parts.append(
                f"Uyarı: {len(cps)} rejim değişikliği tespit edildi "
                f"(analiz #{idx_str}). Pattern'in değiştiğini gösterebilir."
            )

        sf = tier_result.get("seasonality_factor")
        if sf is not None and sf != 1.0:
            if sf > 1.05:
                parts.append(f"Saatlik mevsimsellik: hedef saatte anomali oranı "
                             f"ortalamanın %{(sf - 1) * 100:.0f} üstünde (x{sf:.2f}).")
            elif sf < 0.95:
                parts.append(f"Saatlik mevsimsellik: hedef saatte anomali oranı "
                             f"ortalamanın %{(1 - sf) * 100:.0f} altında (x{sf:.2f}).")

        parts.append(f"Güven skoru: {confidence:.0%}.")

    return " ".join(p for p in parts if p)


# ═══════════════════════════════════════════════════════════
# ML-Adjusted Confidence — statistical × ML convergence
# ═══════════════════════════════════════════════════════════

def _adjust_confidence_with_ml(
    statistical_confidence: float,
    direction: str,
    ml_risk_ctx: Optional[Dict[str, Any]],
) -> Tuple[float, str]:
    """
    İstatistiksel forecast confidence'ını ML risk context ile modüle et.

    Mantık:
    - Forecast rising + ML risk yüksek → convergence → confidence boost
    - Forecast rising + ML risk düşük → divergence → confidence dampen
    - Forecast falling/stable → ML context'ten bağımsız, minimal etki
    - ML context yoksa → orijinal confidence aynen döner

    Returns:
        (adjusted_confidence, adjustment_reason)
    """
    if ml_risk_ctx is None:
        return statistical_confidence, ""

    ml_risk = ml_risk_ctx.get("ml_risk_level", "OK")
    score_worsening = ml_risk_ctx.get("score_worsening", False)
    density_ratio = ml_risk_ctx.get("anomaly_density_ratio", 1.0)
    score_slope = ml_risk_ctx.get("score_trajectory_slope", 0.0)

    # Yön bilgisi: sadece rising/accelerating yönlerde ML etkisi güçlü
    is_rising = direction in ("rising", "accelerating")

    # Sinyal puanı hesapla (-2 .. +4 arası)
    signal_score = 0.0
    reasons = []

    if ml_risk == "CRITICAL":
        signal_score += 2.0
        reasons.append("ML risk: CRITICAL")
    elif ml_risk == "WARNING":
        signal_score += 1.0
        reasons.append("ML risk: WARNING")
    elif ml_risk == "OK":
        signal_score -= 0.5
        reasons.append("ML risk: OK")

    if score_worsening:
        signal_score += 1.0
        reasons.append("ML skor kötüleşiyor")

    if density_ratio > 2.0:
        signal_score += 0.5
        reasons.append(f"anomali yoğunluğu x{density_ratio:.1f}")
    elif density_ratio < 0.5:
        signal_score -= 0.5
        reasons.append(f"anomali yoğunluğu düşük x{density_ratio:.1f}")

    if score_slope > 0.02:
        signal_score += 0.5
        reasons.append("ML skor trendi yükseliyor")

    # Adjustment hesapla
    if is_rising:
        # Rising forecast + pozitif ML sinyalleri → convergence boost
        if signal_score >= 2.0:
            # Güçlü convergence: confidence'ı %10-20 boost
            boost = min(0.20, signal_score * 0.05)
            adjusted = min(0.95, statistical_confidence + boost)
            reason = f"ML convergence boost (+{boost:.2f}): {', '.join(reasons)}"
        elif signal_score >= 1.0:
            # Orta convergence: hafif boost
            boost = min(0.10, signal_score * 0.04)
            adjusted = min(0.90, statistical_confidence + boost)
            reason = f"ML hafif convergence (+{boost:.2f}): {', '.join(reasons)}"
        elif signal_score <= -0.5:
            # Divergence: forecast rising ama ML sakin → dampen
            dampen = min(0.15, abs(signal_score) * 0.06)
            adjusted = max(0.05, statistical_confidence - dampen)
            reason = f"ML divergence (−{dampen:.2f}): {', '.join(reasons)}"
        else:
            adjusted = statistical_confidence
            reason = ""
    else:
        # Falling/stable forecast → ML etkisi minimal
        if signal_score >= 2.0:
            # ML kötüleşiyor ama forecast düşüyor → uyarı notu, confidence'a az etki
            boost = min(0.05, signal_score * 0.02)
            adjusted = min(0.90, statistical_confidence + boost)
            reason = f"ML risk yüksek (forecast {direction}): {', '.join(reasons)}"
        else:
            adjusted = statistical_confidence
            reason = ""

    return round(adjusted, 4), reason


# ═══════════════════════════════════════════════════════════
# Alert Decision — baseline-relative
# ═══════════════════════════════════════════════════════════

def _evaluate_alert(metric_name: str, metric_cfg: Dict, tier_result: Dict,
                     values: List[float], horizon_hours: int,
                     server_name: Optional[str],
                     ml_risk_ctx: Optional[Dict[str, Any]] = None,
                     adjusted_confidence: Optional[float] = None) -> Optional[ForecastAlert]:
    """Baseline'a göre yüzdesel karşılaştırma ile alert kararı.

    ml_risk_ctx verilirse: ML risk seviyesi yüksekse ve forecast da artış
    gösteriyorsa, severity boost edilebilir (WARNING → CRITICAL).

    adjusted_confidence verilirse: ML-adjusted confidence kullanılır
    (tier_result'taki statistical confidence yerine).
    """
    fv = tier_result.get("forecast_value")
    confidence = adjusted_confidence if adjusted_confidence is not None else tier_result.get("confidence", 0)
    direction = tier_result.get("direction", "stable")

    if fv is None or confidence < 0.15:
        return None

    current = values[-1] if values else 0

    # Outlier-resistant baseline: median + IQR filtreleme
    # Son değer hariç (current), geçmiş değerlerden baseline hesapla
    baseline_window = values[:-1] if len(values) > 3 else values
    baseline, baseline_spread = _robust_baseline(baseline_window)
    if baseline <= 0 and baseline_window:
        # Fallback: tüm değerlerin ortalaması
        baseline = sum(baseline_window) / len(baseline_window)

    min_abs = metric_cfg.get("min_absolute_for_alert", 0)
    warning_pct = metric_cfg.get("warning_pct_above_baseline", 50.0)
    critical_pct = metric_cfg.get("critical_pct_above_baseline", 100.0)

    if baseline <= 0:
        pct_above = 100.0 if fv > min_abs else 0.0
    else:
        pct_above = ((fv - baseline) / baseline) * 100

    # Volatility-aware threshold adjustment: yüksek spread → threshold yükselt
    # Böylece doğal olarak volatile metrikler daha zor alarm verir
    if baseline_spread > 0 and baseline > 0:
        spread_ratio = baseline_spread / baseline
        if spread_ratio > 0.3:
            # Yüksek spread: threshold'u %20-50 artır (false positive azaltmak için)
            threshold_boost = min(0.5, spread_ratio * 0.8)
            warning_pct *= (1 + threshold_boost)
            critical_pct *= (1 + threshold_boost)

    if pct_above < warning_pct or fv < min_abs:
        return None
    if direction in ("falling", "decelerating", "stable"):
        return None

    severity = "CRITICAL" if pct_above >= critical_pct else "WARNING"
    vol = tier_result.get("volatility", 0)
    if vol > 0.6 and severity == "CRITICAL":
        severity = "WARNING"

    # ML severity boost: çoklu sinyal yakınsaması
    ml_boosted = False
    ml_explain = ""
    if ml_risk_ctx and metric_name != "mean_anomaly_score":
        ml_risk = ml_risk_ctx.get("ml_risk_level", "OK")
        score_worsening = ml_risk_ctx.get("score_worsening", False)
        score_slope = ml_risk_ctx.get("score_trajectory_slope", 0)
        density_ratio = ml_risk_ctx.get("anomaly_density_ratio", 1.0)

        # Sinyal sayımı
        boost_signals = 0
        boost_reasons = []
        if ml_risk in ("CRITICAL", "WARNING"):
            boost_signals += 1
            boost_reasons.append(f"ML risk: {ml_risk}")
        if score_worsening:
            boost_signals += 1
            boost_reasons.append("skor kötüleşiyor")
        if score_slope > 0.01:
            boost_signals += 1
            boost_reasons.append(f"skor trendi yükseliyor (slope={score_slope:.4f})")
        if density_ratio > 1.5:
            boost_signals += 1
            boost_reasons.append(f"anomali yoğunluğu artmış (x{density_ratio:.1f})")

        # 2+ sinyal → WARNING'i CRITICAL'e yükselt
        if severity == "WARNING" and boost_signals >= 2:
            severity = "CRITICAL"
            ml_boosted = True
            ml_explain = (
                f" ML çoklu sinyal yakınsaması ({boost_signals} sinyal: "
                f"{', '.join(boost_reasons)}). "
                f"Forecast severity ML-destekli olarak yükseltildi."
            )
        # Yüksek güven + kritik eşiğe yakın → yükselt
        elif severity == "WARNING" and confidence > 0.65 and pct_above >= critical_pct * 0.8:
            severity = "CRITICAL"
            ml_boosted = True
            ml_explain = (
                f" Yüksek güven ({confidence:.0%}) ile kritik eşiğe yakın "
                f"(%{pct_above:.0f} vs %{critical_pct:.0f}). Severity yükseltildi."
            )

    label = metric_cfg.get("label", metric_name)
    unit = metric_cfg.get("unit", "")
    method = tier_result.get("method", "unknown")
    explanation = _build_explanation(metric_cfg, tier_result, values, horizon_hours, server_name)
    if ml_explain:
        explanation += ml_explain

    return ForecastAlert(
        alert_type=f"forecast_{metric_name}_rising",
        severity=severity,
        title=f"{label} artış tahmini — {horizon_hours}h içinde {fv:.1f}{unit}"
              + (" (ML-destekli)" if ml_boosted else ""),
        description=(
            f"{label} baseline'ın %{pct_above:.0f} üstüne çıkması bekleniyor. "
            f"Baseline: {baseline:.2f}{unit}, Mevcut: {current:.2f}{unit}, "
            f"Tahmini: {fv:.2f}{unit}. Güven: {confidence:.0%}. Yön: {direction}."
        ),
        metric_name=metric_name,
        current_value=round(current, 4),
        forecast_value=round(fv, 4),
        forecast_horizon_hours=horizon_hours,
        trend_slope=round(tier_result.get("slope", tier_result.get("trend_per_step", 0)), 6),
        confidence=round(confidence, 4),
        data_points_used=len(values),
        server_name=server_name,
        explainability=explanation,
        forecast_method=method,
        volatility=round(vol, 4),
        upper_bound=round(tier_result.get("upper_bound", 0), 4),
        lower_bound=round(tier_result.get("lower_bound", 0), 4),
        change_point_detected=bool(tier_result.get("change_points")),
    )


# ═══════════════════════════════════════════════════════════
# Main Forecaster Class
# ═══════════════════════════════════════════════════════════

class AnomalyForecaster:
    """
    Production-grade anomaly forecaster.

    Tiered multi-method: otomatik model seçimi (veri miktarına göre).
    Cross-source: MongoDB / MSSQL / Elasticsearch metric registry.
    Explainable: her tahmin neden/nasıl yapıldığını açıklar.

    Kullanım:
        forecaster = AnomalyForecaster(config)
        report = forecaster.forecast(history, current, server_name, source_type)

    Backward compatible: eski 3-arg çağrılar (source_type default "mongodb") çalışır.
    """

    def __init__(self, config: Dict[str, Any]):
        self.enabled = config.get('enabled', False)
        self.min_data_points = config.get('min_data_points', 5)
        self.forecast_horizon_hours = config.get('forecast_horizon_hours', 6)
        self.confidence_level = config.get('confidence_interval', 0.95)
        self.configured_metrics = config.get('metrics', list(COMMON_METRICS.keys()))

        # Tier strategy: config'deki model_type → tier_strategy olarak kullanılır
        # "auto" (default) = veri miktarına göre otomatik tier seçimi
        # "linear_regression" = geriye uyumluluk, "auto" olarak işlenir
        raw_strategy = config.get('tier_strategy', config.get('model_type', 'auto'))
        self.tier_strategy = 'auto' if raw_strategy in ('auto', 'linear_regression') else raw_strategy

        # Seasonality desteği (default: açık)
        self.seasonality_enabled = config.get('seasonality_enabled', True)

        # EWMA parametreleri (Tier 3 fine-tuning)
        self.ewma_fast_alpha = config.get('ewma_fast_alpha', 0.3)
        self.ewma_slow_alpha = config.get('ewma_slow_alpha', 0.1)

        logger.info(
            f"AnomalyForecaster initialized (enabled={self.enabled}, "
            f"horizon={self.forecast_horizon_hours}h, "
            f"min_points={self.min_data_points}, "
            f"tier_strategy={self.tier_strategy}, "
            f"seasonality={self.seasonality_enabled}, "
            f"metrics={self.configured_metrics})"
        )

    def forecast(self, history_records: List[Dict[str, Any]],
                 current_analysis: Dict[str, Any],
                 server_name: Optional[str] = None,
                 source_type: str = "mongodb") -> ForecastReport:
        """
        Ana forecast fonksiyonu.

        Args:
            history_records: anomaly_history'den son N kayıt (timestamp DESC)
            current_analysis: Şu anki analiz sonucu
            server_name: Sunucu adı
            source_type: "mongodb", "mssql", "elasticsearch"
        """
        if not self.enabled:
            return ForecastReport(
                server_name=server_name, data_points=0,
                forecast_horizon_hours=self.forecast_horizon_hours,
                forecasts={"message": "Forecasting disabled in config"})

        all_records = [current_analysis] + list(history_records)
        n = len(all_records)

        if n < 2:
            return ForecastReport(
                server_name=server_name, data_points=n,
                forecast_horizon_hours=self.forecast_horizon_hours,
                forecasts={"message": "Tek veri noktası. En az 2 analiz gerekli."})

        records_asc = list(reversed(all_records))
        avg_interval = self._estimate_avg_interval(records_asc)
        steps_ahead = self.forecast_horizon_hours / avg_interval if avg_interval > 0 else 12.0

        # Forecast hedef saatini hesapla (seasonality için)
        forecast_target_hour = None
        if self.seasonality_enabled:
            try:
                now = datetime.utcnow()
                forecast_target_hour = (now.hour + self.forecast_horizon_hours) % 24
            except Exception:
                forecast_target_hour = None

        # Source-aware metric set
        src_key = _normalize_source_type(source_type)
        metric_set = SOURCE_METRIC_SETS.get(src_key, COMMON_METRICS)

        active_metrics: Dict[str, Dict] = {}
        for m_name in self.configured_metrics:
            if m_name in metric_set:
                active_metrics[m_name] = metric_set[m_name]
            elif m_name in COMMON_METRICS:
                active_metrics[m_name] = COMMON_METRICS[m_name]

        forecasts: Dict[str, Any] = {}
        alerts: List[ForecastAlert] = []
        all_cps: List[Dict] = []
        tier_used = ""

        # ML risk context: current_analysis'teki IsolationForest sinyalleri
        ml_risk_ctx = self._compute_ml_risk_context(current_analysis, history_records)

        for metric_name, metric_cfg in active_metrics.items():
            extract_fn = metric_cfg["func"]
            values = [v for rec in records_asc
                      for v in [extract_fn(rec)] if v is not None]

            if len(values) < 2:
                forecasts[metric_name] = {
                    "metric": metric_name, "label": metric_cfg["label"],
                    "status": "insufficient_data", "data_points": len(values),
                    "current_value": values[-1] if values else None,
                    "min_required": 2,
                    "analyses_needed": 2 - len(values),
                    "guidance": self._build_tier_guidance(len(values)),
                }
                continue

            # Seasonality katsayısı hesapla
            s_factor = 1.0
            if self.seasonality_enabled and forecast_target_hour is not None and len(values) >= 8:
                s_factor = _hourly_seasonality_adjustment(
                    records_asc, values, forecast_target_hour)

            tier_result = _select_and_run_tier(
                values, self.min_data_points, steps_ahead, self.confidence_level,
                seasonality_factor=s_factor,
                ewma_fast_alpha=self.ewma_fast_alpha,
                ewma_slow_alpha=self.ewma_slow_alpha)

            method = tier_result.get("method", "unknown")
            if not tier_used or "tier3" in method:
                tier_used = method

            # ML-adjusted confidence: istatistiksel confidence'ı ML risk ile modüle et
            stat_confidence = tier_result.get("confidence", 0)
            direction = tier_result.get("direction", "unknown")
            ml_adj_conf = stat_confidence
            ml_conf_reason = ""
            if ml_risk_ctx and metric_name != "mean_anomaly_score":
                ml_adj_conf, ml_conf_reason = _adjust_confidence_with_ml(
                    stat_confidence, direction, ml_risk_ctx)

            forecast_data: Dict[str, Any] = {
                "metric": metric_name, "label": metric_cfg["label"],
                "unit": metric_cfg["unit"], "current_value": round(values[-1], 4),
                "data_points": len(values), "method": method,
                "direction": direction,
                "confidence": round(ml_adj_conf, 4),
                "statistical_confidence": round(stat_confidence, 4),
                "volatility": round(tier_result.get("volatility", 0), 4),
                "history_values": [round(v, 4) for v in values[-15:]],
            }
            if ml_conf_reason:
                forecast_data["ml_confidence_adjustment"] = ml_conf_reason

            fv = tier_result.get("forecast_value")
            if fv is not None:
                forecast_data.update({
                    "forecast_value": round(fv, 4),
                    "upper_bound": round(tier_result.get("upper_bound", 0), 4),
                    "lower_bound": round(tier_result.get("lower_bound", 0), 4),
                    "forecast_horizon_hours": self.forecast_horizon_hours,
                })
            if "slope" in tier_result:
                forecast_data["slope"] = round(tier_result["slope"], 6)
            if "r_squared" in tier_result:
                forecast_data["r_squared"] = round(tier_result["r_squared"], 4)
            if "momentum" in tier_result:
                forecast_data["momentum"] = round(tier_result["momentum"], 4)
            if "seasonality_factor" in tier_result:
                forecast_data["seasonality_factor"] = tier_result["seasonality_factor"]

            forecast_data["explanation"] = _build_explanation(
                metric_cfg, tier_result, values, self.forecast_horizon_hours, server_name,
                min_data_points=self.min_data_points)

            forecast_data["tier_label"] = _tier_method_label(method)
            forecast_data["guidance"] = self._build_tier_guidance(len(values))

            # ML risk context ekle (mean_anomaly_score kendi metriği için ekleme)
            if ml_risk_ctx and metric_name != "mean_anomaly_score":
                forecast_data["ml_risk_context"] = ml_risk_ctx

            forecasts[metric_name] = forecast_data

            cps = tier_result.get("change_points", [])
            if cps:
                all_cps.append({
                    "metric": metric_name, "indices": cps,
                    "message": f"{metric_cfg['label']}'de {len(cps)} rejim değişikliği"})

            alert = _evaluate_alert(
                metric_name, metric_cfg, tier_result, values,
                self.forecast_horizon_hours, server_name,
                ml_risk_ctx=ml_risk_ctx,
                adjusted_confidence=ml_adj_conf)
            if alert:
                alerts.append(alert)

        report = ForecastReport(
            server_name=server_name, data_points=n,
            forecast_horizon_hours=self.forecast_horizon_hours,
            forecasts=forecasts, alerts=alerts,
            model_tier=tier_used, change_points=all_cps)

        if report.has_alerts():
            logger.warning(
                f"Forecast alerts for {server_name or 'global'}: "
                f"{len(alerts)} alerts, tier={tier_used}, "
                f"max_severity={report.max_severity()}")
        else:
            logger.info(
                f"Forecast for {server_name or 'global'}: "
                f"no alerts, tier={tier_used}, {n} data points")

        return report

    @staticmethod
    def _compute_ml_risk_context(current_analysis: Dict[str, Any],
                                  history_records: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        current_analysis ve history'den ML risk context hesapla.

        Returns:
            ML risk context dict veya None (veri yoksa).
            Alanlar:
              - current_mean_score: abs(current mean anomaly score)
              - baseline_mean_score: abs(historical mean anomaly score ort.)
              - score_worsening: bool — skor kötüleşiyor mu
              - anomaly_rate: current anomaly rate
              - critical_count: current CRITICAL + HIGH count
              - ml_risk_level: "CRITICAL" | "WARNING" | "INFO" | "OK"
        """
        try:
            curr_sr = (current_analysis.get('summary') or {}).get('score_range') or {}
            curr_mean_raw = curr_sr.get('mean')
            if curr_mean_raw is None:
                return None
            curr_mean = abs(float(curr_mean_raw))

            curr_rate = float((current_analysis.get('summary') or {}).get('anomaly_rate', 0))
            sev_dist = current_analysis.get('severity_distribution') or {}
            critical_count = int(sev_dist.get('CRITICAL', 0)) + int(sev_dist.get('HIGH', 0))

            # Historical baseline
            past_scores = []
            for rec in history_records:
                sr = rec.get('score_range') or (rec.get('summary') or {}).get('score_range') or {}
                m = sr.get('mean')
                if m is not None and isinstance(m, (int, float)):
                    past_scores.append(abs(float(m)))

            baseline_mean = sum(past_scores) / len(past_scores) if past_scores else curr_mean

            # Statistical worsening: stddev-based threshold (arbitrary 1.15 yerine)
            if past_scores and len(past_scores) >= 3:
                score_std = _std_dev(past_scores)
                worsening_threshold = baseline_mean + max(score_std * 1.5, baseline_mean * 0.1)
                score_worsening = curr_mean > worsening_threshold
            else:
                score_worsening = curr_mean > baseline_mean * 1.15 if baseline_mean > 0 else False

            # Score trajectory: ML skorlarının zaman içindeki trendi
            score_trajectory_slope = 0.0
            all_scores = past_scores + [curr_mean]
            if len(all_scores) >= 3:
                x_scores = list(range(len(all_scores)))
                slope_s, _, _ = _linear_regression(x_scores, all_scores)
                score_trajectory_slope = slope_s

            # Anomaly density: recent vs baseline anomaly rate oranı
            past_rates = []
            for rec in history_records:
                r = rec.get('anomaly_rate') or (rec.get('summary') or {}).get('anomaly_rate')
                if r is not None:
                    past_rates.append(float(r))
            baseline_rate = sum(past_rates) / len(past_rates) if past_rates else curr_rate
            anomaly_density_ratio = curr_rate / baseline_rate if baseline_rate > 0 else 1.0

            # Risk level
            if critical_count >= 3 or curr_rate > 15:
                ml_risk = "CRITICAL"
            elif critical_count >= 1 or curr_rate > 8:
                ml_risk = "WARNING"
            elif curr_rate > 0:
                ml_risk = "INFO"
            else:
                ml_risk = "OK"

            return {
                "current_mean_score": round(curr_mean, 4),
                "baseline_mean_score": round(baseline_mean, 4),
                "score_worsening": score_worsening,
                "score_trajectory_slope": round(score_trajectory_slope, 6),
                "anomaly_rate": round(curr_rate, 2),
                "baseline_anomaly_rate": round(baseline_rate, 2),
                "anomaly_density_ratio": round(anomaly_density_ratio, 2),
                "critical_count": critical_count,
                "ml_risk_level": ml_risk,
            }
        except Exception as e:
            logger.debug(f"ML risk context computation skipped: {e}")
            return None

    def _estimate_avg_interval(self, records_asc: List[Dict]) -> float:
        """Analizler arası ortalama süre (saat cinsinden)."""
        timestamps: List[datetime] = []
        for record in records_asc:
            ts = record.get('timestamp') or record.get('analysis_timestamp')
            if ts:
                try:
                    if isinstance(ts, str):
                        ts_dt = datetime.fromisoformat(
                            ts.replace('Z', '').split('+')[0])
                    elif isinstance(ts, datetime):
                        ts_dt = ts
                    else:
                        continue
                    timestamps.append(ts_dt)
                except (ValueError, TypeError):
                    continue

        if len(timestamps) < 2:
            return 0.5

        intervals = []
        for i in range(1, len(timestamps)):
            diff_h = (timestamps[i] - timestamps[i - 1]).total_seconds() / 3600
            if 0 < diff_h < 168:
                intervals.append(diff_h)
        return sum(intervals) / len(intervals) if intervals else 0.5

    def _build_tier_guidance(self, data_points: int) -> Dict[str, Any]:
        """Veri miktarına göre tier yol haritası ve kullanıcı rehberliği."""
        min_pts = self.min_data_points

        if data_points < 2:
            return {
                "current": "Veri Yetersiz",
                "next": "Tier 0 — Yön Göstergesi",
                "analyses_needed": 2 - data_points,
                "confidence_range": None,
                "message": (
                    f"Tahmin için en az 2 geçmiş analiz gerekli. "
                    f"{2 - data_points} analiz daha çalıştırın."
                ),
            }
        elif data_points < min_pts:
            return {
                "current": "Tier 0 — Yön Göstergesi",
                "next": "Tier 1 — Ağırlıklı Ortalama",
                "analyses_needed": min_pts - data_points,
                "confidence_range": "%0–10",
                "message": (
                    f"Şu an sadece yön bilgisi gösterilebilir. "
                    f"Sayısal tahmin için {min_pts - data_points} analiz daha gerekli."
                ),
            }
        elif data_points < 10:
            return {
                "current": "Tier 1 — Ağırlıklı Ortalama",
                "next": "Tier 2 — Lineer Regresyon",
                "analyses_needed": 10 - data_points,
                "confidence_range": "%20–40",
                "message": (
                    f"Temel tahmin aktif. Daha güvenilir regresyon tahmini "
                    f"için {10 - data_points} analiz daha gerekli."
                ),
            }
        elif data_points < 20:
            return {
                "current": "Tier 2 — Lineer Regresyon",
                "next": "Tier 3 — EWMA Trend Ayrıştırma",
                "analyses_needed": 20 - data_points,
                "confidence_range": "%40–70",
                "message": (
                    f"Regresyon tabanlı tahmin aktif. En yüksek doğruluk "
                    f"için {20 - data_points} analiz daha gerekli."
                ),
            }
        else:
            return {
                "current": "Tier 3 — EWMA Trend Ayrıştırma",
                "next": None,
                "analyses_needed": 0,
                "confidence_range": "%50–90",
                "message": (
                    "En gelişmiş tahmin seviyesi aktif. Trend ayrıştırma, "
                    "momentum analizi ve rejim tespiti kullanılıyor."
                ),
            }
