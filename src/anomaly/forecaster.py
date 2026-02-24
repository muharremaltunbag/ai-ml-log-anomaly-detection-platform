# src/anomaly/forecaster.py

"""
Forecaster - MongoDB Anomaly Detection Prediction Layer (Katman 3)

Anomaly history'den geçmiş metrikleri alarak ileriye dönük tahmin üretir.
Linear regression bazlı basit time series forecasting.

Mevcut pipeline'dan tamamen izole çalışır. Çağrılmazsa bile hiçbir şey bozulmaz.
Feature flag: config.prediction.forecasting.enabled

Kullanım:
    forecaster = AnomalyForecaster(config)
    report = forecaster.forecast(history_records, current_analysis, server_name)
"""

import logging
import math
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, asdict, field

logger = logging.getLogger(__name__)


@dataclass
class ForecastAlert:
    """Tek bir forecast alert"""
    alert_type: str          # "forecast_anomaly_rate_rising", "forecast_critical_ratio_rising"
    severity: str            # "INFO", "WARNING", "CRITICAL"
    title: str
    description: str
    metric_name: str         # Tahmin edilen metrik
    current_value: float     # Şu anki değer
    forecast_value: float    # Tahmini değer (horizon sonunda)
    forecast_horizon_hours: int
    trend_slope: float       # Eğim (birim zaman başına artış)
    confidence: float        # Tahmin güveni (R² veya basit korelasyon)
    data_points_used: int    # Kaç veri noktası kullanıldı
    server_name: Optional[str] = None
    timestamp: str = ""
    explainability: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ForecastReport:
    """Forecasting raporu"""
    server_name: Optional[str]
    data_points: int             # Kaç geçmiş analiz kullanıldı
    forecast_horizon_hours: int
    forecasts: Dict[str, Any] = field(default_factory=dict)  # Metrik bazlı tahminler
    alerts: List[ForecastAlert] = field(default_factory=list)
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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "server_name": self.server_name,
            "data_points": self.data_points,
            "forecast_horizon_hours": self.forecast_horizon_hours,
            "forecasts": self.forecasts,
            "alerts": [a.to_dict() for a in self.alerts],
            "timestamp": self.timestamp,
            "max_severity": self.max_severity(),
            "has_alerts": self.has_alerts()
        }


# ──────────────────────────────────────────────
# Pure math: Simple linear regression
# ──────────────────────────────────────────────

def _linear_regression(x: List[float], y: List[float]) -> Tuple[float, float, float]:
    """
    Simple linear regression: y = slope * x + intercept.
    Dış kütüphane (numpy/scipy) kullanmadan saf hesaplama.

    Args:
        x: Bağımsız değişken (ör: analiz sırası 0,1,2,...)
        y: Bağımlı değişken (ör: anomaly_rate)

    Returns:
        (slope, intercept, r_squared)
    """
    n = len(x)
    if n < 2:
        return 0.0, y[0] if y else 0.0, 0.0

    sum_x = sum(x)
    sum_y = sum(y)
    sum_xy = sum(xi * yi for xi, yi in zip(x, y))
    sum_x2 = sum(xi * xi for xi in x)

    denom = n * sum_x2 - sum_x * sum_x
    if denom == 0:
        return 0.0, sum_y / n, 0.0

    slope = (n * sum_xy - sum_x * sum_y) / denom
    intercept = (sum_y - slope * sum_x) / n

    # R² hesapla
    y_mean = sum_y / n
    ss_tot = sum((yi - y_mean) ** 2 for yi in y)
    ss_res = sum((yi - (slope * xi + intercept)) ** 2 for xi, yi in zip(x, y))

    r_squared = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 0.0
    # Clamp to [0, 1]
    r_squared = max(0.0, min(1.0, r_squared))

    return slope, intercept, r_squared


# ──────────────────────────────────────────────
# Metric extractors: history record → float value
# ──────────────────────────────────────────────

def _extract_anomaly_rate(record: Dict[str, Any]) -> Optional[float]:
    """anomaly_rate çıkar"""
    rate = record.get('anomaly_rate')
    if rate is None:
        rate = record.get('summary', {}).get('anomaly_rate')
    if rate is not None:
        return float(rate)
    return None


def _extract_anomaly_count(record: Dict[str, Any]) -> Optional[float]:
    """n_anomalies çıkar"""
    count = record.get('n_anomalies')
    if count is None:
        count = record.get('summary', {}).get('n_anomalies')
    if count is not None:
        return float(count)
    return None


def _extract_critical_ratio(record: Dict[str, Any]) -> Optional[float]:
    """CRITICAL+HIGH anomali oranını çıkar"""
    dist = record.get('severity_distribution', {})
    if not dist:
        return None
    total = sum(dist.values())
    if total == 0:
        return None
    critical = dist.get('CRITICAL', 0) + dist.get('HIGH', 0)
    return (critical / total) * 100


def _extract_error_count(record: Dict[str, Any]) -> Optional[float]:
    """Error sayısını çıkar (component_analysis'ten)"""
    comp = record.get('component_analysis', {})
    # Tüm component'lerdeki anomaly count toplamını döndür
    if not comp:
        return None
    total = sum(c.get('anomaly_count', 0) for c in comp.values())
    return float(total)


METRIC_EXTRACTORS = {
    "anomaly_rate": {
        "func": _extract_anomaly_rate,
        "label": "Anomali Oranı (%)",
        "unit": "%",
        "warning_threshold_slope": 0.5,    # Her analizde %0.5+ artış → WARNING
        "critical_threshold_slope": 2.0,    # Her analizde %2+ artış → CRITICAL
    },
    "anomaly_count": {
        "func": _extract_anomaly_count,
        "label": "Anomali Sayısı",
        "unit": "adet",
        "warning_threshold_slope": 5.0,     # Her analizde 5+ artış
        "critical_threshold_slope": 20.0,
    },
    "critical_ratio": {
        "func": _extract_critical_ratio,
        "label": "Kritik Anomali Oranı (%)",
        "unit": "%",
        "warning_threshold_slope": 1.0,
        "critical_threshold_slope": 5.0,
    },
    "error_count": {
        "func": _extract_error_count,
        "label": "Error Sayısı",
        "unit": "adet",
        "warning_threshold_slope": 3.0,
        "critical_threshold_slope": 10.0,
    },
}


class AnomalyForecaster:
    """
    Anomaly history'den basit linear regression ile metrik tahmini yapar.

    Kullanım:
        forecaster = AnomalyForecaster(config)
        report = forecaster.forecast(history_records, current_analysis, server_name)

    Senkron çalışır. IO yapmaz. anomaly_tools.py tarafından history verilir.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Args:
            config: prediction.forecasting bloğu
        """
        self.enabled = config.get('enabled', False)
        self.min_data_points = config.get('min_data_points', 5)
        self.forecast_horizon_hours = config.get('forecast_horizon_hours', 6)
        self.model_type = config.get('model_type', 'linear_regression')
        self.confidence_interval = config.get('confidence_interval', 0.95)
        self.metrics = config.get('metrics', ['anomaly_rate', 'anomaly_count'])

        logger.info(f"AnomalyForecaster initialized (enabled={self.enabled}, "
                     f"model={self.model_type}, horizon={self.forecast_horizon_hours}h, "
                     f"min_points={self.min_data_points}, metrics={self.metrics})")

    def forecast(self, history_records: List[Dict[str, Any]],
                 current_analysis: Dict[str, Any],
                 server_name: Optional[str] = None) -> ForecastReport:
        """
        Geçmiş analizler + mevcut analiz ile ileriye dönük tahmin üret.

        Args:
            history_records: anomaly_history'den son N kayıt (timestamp DESC sıralı)
            current_analysis: Şu anki analiz sonucu
            server_name: Sunucu adı

        Returns:
            ForecastReport
        """
        if not self.enabled:
            return ForecastReport(
                server_name=server_name,
                data_points=0,
                forecast_horizon_hours=self.forecast_horizon_hours,
                forecasts={"message": "Forecasting disabled in config"}
            )

        # Current + history = full dataset (en yeniden en eskiye)
        all_records = [current_analysis] + list(history_records)

        if len(all_records) < self.min_data_points:
            return ForecastReport(
                server_name=server_name,
                data_points=len(all_records),
                forecast_horizon_hours=self.forecast_horizon_hours,
                forecasts={
                    "message": f"Yetersiz veri ({len(all_records)}/{self.min_data_points}). "
                               f"Daha fazla analiz biriktikçe tahmin aktif olacak."
                }
            )

        # Sırayı çevir: en eskiden en yeniye (x=0 en eski, x=N-1 en yeni)
        records_asc = list(reversed(all_records))

        forecasts: Dict[str, Any] = {}
        alerts: List[ForecastAlert] = []

        for metric_name in self.metrics:
            extractor_cfg = METRIC_EXTRACTORS.get(metric_name)
            if not extractor_cfg:
                logger.warning(f"Unknown metric: {metric_name}, skipping")
                continue

            metric_result = self._forecast_metric(
                records_asc, metric_name, extractor_cfg, server_name
            )

            if metric_result:
                forecasts[metric_name] = metric_result["forecast"]
                if metric_result.get("alert"):
                    alerts.append(metric_result["alert"])

        return ForecastReport(
            server_name=server_name,
            data_points=len(all_records),
            forecast_horizon_hours=self.forecast_horizon_hours,
            forecasts=forecasts,
            alerts=alerts
        )

    def _forecast_metric(self, records_asc: List[Dict],
                         metric_name: str,
                         extractor_cfg: Dict[str, Any],
                         server_name: Optional[str]) -> Optional[Dict[str, Any]]:
        """Tek bir metrik için forecast hesapla"""
        extract_fn = extractor_cfg["func"]

        # Değerleri çıkar
        values = []
        for record in records_asc:
            val = extract_fn(record)
            if val is not None:
                values.append(val)

        if len(values) < self.min_data_points:
            return None

        # x = sıra numarası (0, 1, 2, ..., N-1)
        x = list(range(len(values)))
        y = values

        # Linear regression
        slope, intercept, r_squared = _linear_regression(x, y)

        current_value = values[-1]

        # Forecast: slope pozitifse artış trendi var demek
        # Horizon hesabı: Eğer her analiz ~30dk aralıkla geliyorsa,
        # forecast_horizon_hours / 0.5 saat = kaç adım ileri tahmin
        # Ama analizler arası süre değişken. Basit yaklaşım: son N veri noktasının
        # trendini horizon kadar ileriye projekte et.
        # steps_ahead = horizon_hours / avg_interval_hours
        avg_interval_hours = self._estimate_avg_interval(records_asc)
        if avg_interval_hours <= 0:
            avg_interval_hours = 0.5  # default 30dk

        steps_ahead = self.forecast_horizon_hours / avg_interval_hours
        forecast_x = len(values) - 1 + steps_ahead
        forecast_value = slope * forecast_x + intercept

        # Negatif değer anlamsız (oran/sayı negatif olamaz)
        forecast_value = max(0.0, forecast_value)

        forecast_data = {
            "metric": metric_name,
            "label": extractor_cfg["label"],
            "current_value": round(current_value, 4),
            "forecast_value": round(forecast_value, 4),
            "trend_slope": round(slope, 6),
            "trend_direction": "rising" if slope > 0.001 else ("falling" if slope < -0.001 else "stable"),
            "r_squared": round(r_squared, 4),
            "data_points": len(values),
            "forecast_horizon_hours": self.forecast_horizon_hours,
            "avg_interval_hours": round(avg_interval_hours, 2),
            "steps_ahead": round(steps_ahead, 1),
            "history_values": [round(v, 4) for v in values[-10:]],  # Son 10 değer
        }

        # Alert üretme kararı
        alert = None
        warning_slope = extractor_cfg.get("warning_threshold_slope", 0)
        critical_slope = extractor_cfg.get("critical_threshold_slope", 0)

        if slope > 0 and r_squared >= 0.3:
            # Anlamlı artış trendi var
            if slope >= critical_slope:
                severity = "CRITICAL"
            elif slope >= warning_slope:
                severity = "WARNING"
            else:
                severity = None

            if severity:
                alert = ForecastAlert(
                    alert_type=f"forecast_{metric_name}_rising",
                    severity=severity,
                    title=f"{extractor_cfg['label']} artış tahmini",
                    description=(
                        f"{extractor_cfg['label']} son {len(values)} analizde yükseliş trendinde. "
                        f"Mevcut: {current_value:.2f}{extractor_cfg['unit']} → "
                        f"Tahmini ({self.forecast_horizon_hours}h sonra): "
                        f"{forecast_value:.2f}{extractor_cfg['unit']}. "
                        f"Eğim: +{slope:.4f}/analiz, R²={r_squared:.2f}."
                    ),
                    metric_name=metric_name,
                    current_value=round(current_value, 4),
                    forecast_value=round(forecast_value, 4),
                    forecast_horizon_hours=self.forecast_horizon_hours,
                    trend_slope=round(slope, 6),
                    confidence=round(r_squared, 4),
                    data_points_used=len(values),
                    server_name=server_name,
                    explainability=(
                        f"Linear regression analizi: {len(values)} veri noktası kullanıldı. "
                        f"slope={slope:.4f} (her analiz başına +{slope:.4f} {extractor_cfg['unit']}), "
                        f"R²={r_squared:.2f} (model fit kalitesi). "
                        f"{self.forecast_horizon_hours} saat sonrası tahmini: {forecast_value:.2f}. "
                        f"{'CRITICAL: Hızlı artış, acil müdahale gerekebilir.' if severity == 'CRITICAL' else 'WARNING: Artış trendi izlenmeli.'}"
                    )
                )

        return {"forecast": forecast_data, "alert": alert}

    def _estimate_avg_interval(self, records_asc: List[Dict]) -> float:
        """Analizler arası ortalama süreyi saat cinsinden tahmin et"""
        timestamps = []
        for record in records_asc:
            ts = record.get('timestamp') or record.get('analysis_timestamp')
            if ts:
                try:
                    if isinstance(ts, str):
                        # ISO format parse
                        ts_dt = datetime.fromisoformat(ts.replace('Z', '+00:00').replace('+00:00', ''))
                    elif isinstance(ts, datetime):
                        ts_dt = ts
                    else:
                        continue
                    timestamps.append(ts_dt)
                except (ValueError, TypeError):
                    continue

        if len(timestamps) < 2:
            return 0.5  # default 30dk

        # Sıralı timestamp'lar arası farkların ortalaması
        intervals = []
        for i in range(1, len(timestamps)):
            diff = (timestamps[i] - timestamps[i - 1]).total_seconds() / 3600
            if 0 < diff < 168:  # 0-7 gün arası makul aralıkları say
                intervals.append(diff)

        if not intervals:
            return 0.5

        return sum(intervals) / len(intervals)
