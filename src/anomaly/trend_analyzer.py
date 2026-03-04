# src/anomaly/trend_analyzer.py

"""
Trend Analyzer - MongoDB Anomaly Detection Prediction Layer (Katman 1)

Mevcut anomaly detection pipeline'ına izole bir ek katman.
anomaly_history collection'ından son N analizi okuyarak:
- Anomaly rate trend'i (artış/azalış/stabil)
- Component yoğunlaşma tespiti
- Severity escalation (ciddiyet artışı)
- Temporal pattern değişimi

Bu modül anomaly_tools.py'den çağrılır ama çağrılmasa da mevcut pipeline çalışmaya devam eder.
Feature flag: config.prediction.trend_detection.enabled
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field, asdict

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


@dataclass
class TrendAlert:
    """Tek bir trend alert'ini temsil eder"""
    alert_type: str          # "anomaly_rate_increase", "component_concentration", "severity_escalation", "temporal_shift"
    severity: str            # "INFO", "WARNING", "CRITICAL"
    title: str               # Kısa başlık
    description: str         # Detaylı açıklama
    metric_name: str         # Hangi metrik izlendi
    baseline_value: float    # Normal baseline
    current_value: float     # Şu anki değer
    change_pct: float        # Değişim yüzdesi
    window_size: int         # Kaç analiz karşılaştırıldı
    server_name: Optional[str] = None
    timestamp: str = ""
    explainability: str = "" # "Neye göre alarm verdi?" açıklaması

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TrendReport:
    """Trend analizi raporu"""
    server_name: Optional[str]
    analysis_count: int          # Kaç geçmiş analiz kullanıldı
    trend_direction: str         # "improving", "stable", "degrading", "critical"
    alerts: List[TrendAlert] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)
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
            "analysis_count": self.analysis_count,
            "trend_direction": self.trend_direction,
            "alerts": [a.to_dict() for a in self.alerts],
            "summary": self.summary,
            "timestamp": self.timestamp,
            "max_severity": self.max_severity(),
            "has_alerts": self.has_alerts()
        }


class TrendAnalyzer:
    """
    Anomali history'den trend tespiti yapar.

    Kullanım:
        analyzer = TrendAnalyzer(config)
        report = analyzer.analyze(history_records, current_analysis, server_name)

    Senkron çalışır. Async storage okuma anomaly_tools.py tarafında yapılır,
    bu modül sadece pure analysis yapar.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Args:
            config: prediction.trend_detection bloğu
        """
        self.enabled = config.get('enabled', False)
        self.min_history = config.get('min_history_count', 3)
        self.lookback = config.get('lookback_analyses', 10)
        self.rate_increase_threshold = config.get('anomaly_rate_increase_threshold', 50.0)
        self.count_increase_threshold = config.get('anomaly_count_increase_threshold', 100.0)
        self.component_threshold = config.get('component_concentration_threshold', 60.0)
        self.severity_threshold = config.get('severity_escalation_threshold', 30.0)

        logger.info(f"TrendAnalyzer initialized (enabled={self.enabled}, "
                     f"min_history={self.min_history}, lookback={self.lookback})")

    def analyze(self, history_records: List[Dict[str, Any]],
                current_analysis: Dict[str, Any],
                server_name: Optional[str] = None,
                source_type: str = "mongodb") -> TrendReport:
        """
        Geçmiş analizler ile mevcut analizi karşılaştırarak trend raporu üret.

        Args:
            history_records: anomaly_history'den çekilen son N kayıt (timestamp DESC sıralı)
            current_analysis: Şu anki analiz sonucu (analysis dict)
            server_name: Sunucu adı
            source_type: "mongodb", "mssql", "elasticsearch" — source-specific check'ler için

        Returns:
            TrendReport
        """
        if not self.enabled:
            return TrendReport(
                server_name=server_name,
                analysis_count=0,
                trend_direction="disabled",
                summary={"message": "Trend detection is disabled in config"}
            )

        if len(history_records) < self.min_history:
            return TrendReport(
                server_name=server_name,
                analysis_count=len(history_records),
                trend_direction="insufficient_data",
                summary={
                    "message": f"Not enough history ({len(history_records)}/{self.min_history} required)",
                    "suggestion": "Trend analysis requires more historical data points"
                }
            )

        alerts: List[TrendAlert] = []

        # 1. Anomaly rate trend
        rate_alerts = self._check_anomaly_rate_trend(history_records, current_analysis, server_name)
        alerts.extend(rate_alerts)

        # 2. Component concentration
        comp_alerts = self._check_component_concentration(history_records, current_analysis, server_name)
        alerts.extend(comp_alerts)

        # 3. Severity escalation
        sev_alerts = self._check_severity_escalation(history_records, current_analysis, server_name)
        alerts.extend(sev_alerts)

        # 4. Temporal pattern shift
        temp_alerts = self._check_temporal_shift(history_records, current_analysis, server_name)
        alerts.extend(temp_alerts)

        # 5. Source-specific metric trends
        src_alerts = self._check_source_specific_trends(
            history_records, current_analysis, server_name, source_type)
        alerts.extend(src_alerts)

        # 6. ML anomaly score trend (IsolationForest mean score)
        ml_alerts = self._check_ml_score_trend(history_records, current_analysis, server_name)
        alerts.extend(ml_alerts)

        # 7. ML score distribution monitoring (std dev genişleme + severity shift)
        dist_alerts = self._check_ml_score_distribution(history_records, current_analysis, server_name)
        alerts.extend(dist_alerts)

        # 8. Rate acceleration (2. türev — artış hızlanıyor mu?)
        accel_alerts = self._check_rate_acceleration(history_records, current_analysis, server_name)
        alerts.extend(accel_alerts)

        # 9. Volatility indicator (gürültü seviyesi)
        vol_alerts = self._check_volatility(history_records, current_analysis, server_name)
        alerts.extend(vol_alerts)

        # 10. Improvement detection (iyileşme tespiti)
        imp_alerts = self._check_improvement(history_records, current_analysis, server_name)
        alerts.extend(imp_alerts)

        # Trend direction
        direction = self._determine_trend_direction(alerts, history_records, current_analysis)

        # Summary
        summary = self._build_summary(history_records, current_analysis, alerts)

        report = TrendReport(
            server_name=server_name,
            analysis_count=len(history_records),
            trend_direction=direction,
            alerts=alerts,
            summary=summary
        )

        if report.has_alerts():
            logger.warning(f"Trend alerts for {server_name or 'global'}: "
                           f"{len(alerts)} alerts, direction={direction}, "
                           f"max_severity={report.max_severity()}")
        else:
            logger.info(f"Trend analysis for {server_name or 'global'}: "
                        f"no alerts, direction={direction}")

        return report

    # ──────────────────────────────────────────────
    # Check: Anomaly Rate Trend
    # ──────────────────────────────────────────────

    def _check_anomaly_rate_trend(self, history: List[Dict], current: Dict,
                                  server_name: Optional[str]) -> List[TrendAlert]:
        """Anomaly rate'in artış/azalış trendini kontrol et"""
        alerts = []

        # Geçmiş rate'leri çıkar
        past_rates = []
        for record in history:
            rate = record.get('anomaly_rate', 0)
            if rate is None:
                rate = record.get('summary', {}).get('anomaly_rate', 0)
            past_rates.append(float(rate or 0))

        if not past_rates:
            return alerts

        # Current rate
        current_summary = current.get('summary', {})
        current_rate = float(current_summary.get('anomaly_rate', 0))

        # Baseline: geçmiş ortalama
        baseline_rate = sum(past_rates) / len(past_rates)

        if baseline_rate == 0:
            # Baseline 0 ise ve current > 0 ise yeni anomali ortaya çıkmış demek
            if current_rate > 0:
                alerts.append(TrendAlert(
                    alert_type="anomaly_rate_increase",
                    severity="WARNING",
                    title="Yeni anomali trendi başladı",
                    description=f"Geçmiş {len(past_rates)} analizde anomali oranı sıfırdı, "
                                f"şimdi %{current_rate:.2f} seviyesinde.",
                    metric_name="anomaly_rate",
                    baseline_value=0,
                    current_value=current_rate,
                    change_pct=100.0,
                    window_size=len(past_rates),
                    server_name=server_name,
                    explainability=f"Baseline (son {len(past_rates)} analiz ortalaması): %0.00 → "
                                   f"Güncel: %{current_rate:.2f}. İlk kez anomali tespit edildi."
                ))
            return alerts

        # Yüzde değişim
        change_pct = ((current_rate - baseline_rate) / baseline_rate) * 100

        if change_pct > self.rate_increase_threshold:
            severity = "CRITICAL" if change_pct > self.rate_increase_threshold * 2 else "WARNING"
            alerts.append(TrendAlert(
                alert_type="anomaly_rate_increase",
                severity=severity,
                title="Anomali oranı yükseliyor",
                description=f"Anomali oranı geçmiş {len(past_rates)} analize göre "
                            f"%{change_pct:.1f} arttı. "
                            f"Baseline: %{baseline_rate:.2f} → Güncel: %{current_rate:.2f}",
                metric_name="anomaly_rate",
                baseline_value=round(baseline_rate, 4),
                current_value=round(current_rate, 4),
                change_pct=round(change_pct, 2),
                window_size=len(past_rates),
                server_name=server_name,
                explainability=f"Son {len(past_rates)} analiz ortalaması %{baseline_rate:.2f} idi. "
                               f"Güncel analiz %{current_rate:.2f} → %{change_pct:.1f} artış. "
                               f"Eşik: %{self.rate_increase_threshold}."
            ))

        # Monoton artış kontrolü (son 3+ analizde sürekli artıyor mu?)
        if len(past_rates) >= 3:
            recent_3 = past_rates[:3]  # En yeni 3 (DESC sıralı)
            if all(recent_3[i] >= recent_3[i + 1] for i in range(len(recent_3) - 1)):
                # Son 3 analizde monoton artış var ve şimdi daha da yüksek
                if current_rate > recent_3[0]:
                    alerts.append(TrendAlert(
                        alert_type="anomaly_rate_monotonic_increase",
                        severity="WARNING",
                        title="Sürekli artış trendi",
                        description=f"Son 4 analizde anomali oranı kesintisiz artıyor: "
                                    f"{' → '.join(f'%{r:.2f}' for r in reversed(recent_3))} → %{current_rate:.2f}",
                        metric_name="anomaly_rate_trend",
                        baseline_value=round(recent_3[-1], 4),
                        current_value=round(current_rate, 4),
                        change_pct=round(change_pct, 2),
                        window_size=4,
                        server_name=server_name,
                        explainability=f"Son 4 analiz boyunca anomali oranı her seferinde artmış. "
                                       f"Bu, geçici bir spike değil süregelen bir bozulma olabilir."
                    ))

        return alerts

    # ──────────────────────────────────────────────
    # Check: Component Concentration
    # ──────────────────────────────────────────────

    def _check_component_concentration(self, history: List[Dict], current: Dict,
                                       server_name: Optional[str]) -> List[TrendAlert]:
        """Anomalilerin belirli bir component'te yoğunlaşıp yoğunlaşmadığını kontrol et"""
        alerts = []

        current_comp = current.get('component_analysis', {})
        if not current_comp:
            return alerts

        # Current'ta dominant component bul
        total_anomalies = sum(
            c.get('anomaly_count', 0) for c in current_comp.values()
        )
        if total_anomalies == 0:
            return alerts

        for comp_name, comp_stats in current_comp.items():
            comp_anomaly_count = comp_stats.get('anomaly_count', 0)
            comp_rate = comp_stats.get('anomaly_rate', 0)
            concentration_pct = (comp_anomaly_count / total_anomalies * 100) if total_anomalies > 0 else 0

            if concentration_pct < self.component_threshold:
                continue

            # Geçmişte bu component bu kadar dominant mıydı?
            past_concentrations = []
            for record in history:
                hist_comp = record.get('component_analysis', {})
                hist_total = sum(c.get('anomaly_count', 0) for c in hist_comp.values())
                if hist_total > 0 and comp_name in hist_comp:
                    past_conc = hist_comp[comp_name].get('anomaly_count', 0) / hist_total * 100
                    past_concentrations.append(past_conc)

            baseline_conc = (sum(past_concentrations) / len(past_concentrations)) if past_concentrations else 0

            # Yoğunlaşma artışı
            if concentration_pct > baseline_conc * 1.5 or (baseline_conc == 0 and concentration_pct > self.component_threshold):
                alerts.append(TrendAlert(
                    alert_type="component_concentration",
                    severity="WARNING",
                    title=f"{comp_name} component'inde yoğunlaşma",
                    description=f"Anomalilerin %{concentration_pct:.1f}'i {comp_name} component'inde. "
                                f"Geçmiş baseline: %{baseline_conc:.1f}. "
                                f"Bu component'te {comp_anomaly_count} anomali, "
                                f"component anomaly rate: %{comp_rate:.1f}",
                    metric_name=f"component_concentration_{comp_name}",
                    baseline_value=round(baseline_conc, 2),
                    current_value=round(concentration_pct, 2),
                    change_pct=round(concentration_pct - baseline_conc, 2),
                    window_size=len(past_concentrations),
                    server_name=server_name,
                    explainability=f"{comp_name} component'i toplam anomalilerin "
                                   f"%{concentration_pct:.1f}'ini oluşturuyor (geçmiş ort: %{baseline_conc:.1f}). "
                                   f"Bu component'te spesifik bir sorun olabilir."
                ))

        return alerts

    # ──────────────────────────────────────────────
    # Check: Severity Escalation
    # ──────────────────────────────────────────────

    def _check_severity_escalation(self, history: List[Dict], current: Dict,
                                   server_name: Optional[str]) -> List[TrendAlert]:
        """CRITICAL/HIGH severity oranının artıp artmadığını kontrol et"""
        alerts = []

        current_dist = current.get('severity_distribution', {})
        if not current_dist:
            return alerts

        current_total = sum(current_dist.values())
        if current_total == 0:
            return alerts

        current_critical_count = current_dist.get('CRITICAL', 0) + current_dist.get('HIGH', 0)
        current_critical_pct = (current_critical_count / current_total) * 100

        # Geçmiş critical oranları
        past_critical_pcts = []
        for record in history:
            hist_dist = record.get('severity_distribution', {})
            hist_total = sum(hist_dist.values()) if hist_dist else 0
            if hist_total > 0:
                hist_critical = hist_dist.get('CRITICAL', 0) + hist_dist.get('HIGH', 0)
                past_critical_pcts.append((hist_critical / hist_total) * 100)

        if not past_critical_pcts:
            return alerts

        baseline_critical_pct = sum(past_critical_pcts) / len(past_critical_pcts)

        change = current_critical_pct - baseline_critical_pct

        if change > self.severity_threshold:
            severity = "CRITICAL" if current_critical_pct > 50 else "WARNING"
            alerts.append(TrendAlert(
                alert_type="severity_escalation",
                severity=severity,
                title="Ciddiyet seviyesi yükseliyor",
                description=f"CRITICAL+HIGH anomali oranı %{baseline_critical_pct:.1f} → "
                            f"%{current_critical_pct:.1f} (artış: +%{change:.1f}). "
                            f"Toplam {current_critical_count} yüksek ciddiyetli anomali.",
                metric_name="critical_severity_ratio",
                baseline_value=round(baseline_critical_pct, 2),
                current_value=round(current_critical_pct, 2),
                change_pct=round(change, 2),
                window_size=len(past_critical_pcts),
                server_name=server_name,
                explainability=f"Son {len(past_critical_pcts)} analizde CRITICAL+HIGH oranı ortalama "
                               f"%{baseline_critical_pct:.1f} idi. Şimdi %{current_critical_pct:.1f}. "
                               f"Anomaliler daha ciddi hale geliyor."
            ))

        return alerts

    # ──────────────────────────────────────────────
    # Check: Temporal Pattern Shift
    # ──────────────────────────────────────────────

    def _check_temporal_shift(self, history: List[Dict], current: Dict,
                              server_name: Optional[str]) -> List[TrendAlert]:
        """Anomali yoğunluğunun farklı saat dilimlerine kayıp kaymadığını kontrol et"""
        alerts = []

        current_temporal = current.get('temporal_analysis', {})
        current_peaks = current_temporal.get('peak_hours', [])

        if not current_peaks:
            return alerts

        # Geçmiş peak saatlerini topla
        past_peak_freq: Dict[int, int] = {}
        for record in history:
            hist_peaks = record.get('temporal_analysis', {}).get('peak_hours', [])
            for hour in hist_peaks:
                past_peak_freq[int(hour)] = past_peak_freq.get(int(hour), 0) + 1

        if not past_peak_freq:
            return alerts

        # En sık geçmiş peak saat
        common_peaks = sorted(past_peak_freq.keys(), key=lambda h: past_peak_freq[h], reverse=True)[:3]

        # Mevcut peak saatleri geçmiş pattern'den ne kadar farklı?
        current_peak_set = set(int(h) for h in current_peaks[:3])
        common_peak_set = set(common_peaks)

        overlap = current_peak_set & common_peak_set
        shift_ratio = 1 - (len(overlap) / max(len(current_peak_set), 1))

        if shift_ratio > 0.5 and len(current_peak_set) >= 2:
            alerts.append(TrendAlert(
                alert_type="temporal_shift",
                severity="INFO",
                title="Anomali zamanlaması değişti",
                description=f"Anomali peak saatleri değişti. "
                            f"Geçmiş pattern: {sorted(common_peaks)} → "
                            f"Güncel: {sorted(current_peak_set)}. "
                            f"Örtüşme: {len(overlap)}/{len(current_peak_set)}",
                metric_name="peak_hour_shift",
                baseline_value=float(common_peaks[0]) if common_peaks else 0,
                current_value=float(current_peaks[0]) if current_peaks else 0,
                change_pct=round(shift_ratio * 100, 1),
                window_size=len(history),
                server_name=server_name,
                explainability=f"Anomaliler genellikle {sorted(common_peaks)} saatlerinde yoğunlaşıyordu. "
                               f"Şimdi {sorted(current_peak_set)} saatlerinde yoğunlaşıyor. "
                               f"Bu, yeni bir workload pattern'i veya farklı bir sorun kaynağı olabilir."
            ))

        return alerts

    # ──────────────────────────────────────────────
    # Check: Source-Specific Metric Trends
    # ──────────────────────────────────────────────

    # Metric extractors per source — (current_key, history_key, label, threshold_pct)
    _SOURCE_METRICS = {
        "mongodb": [
            ("performance_alerts.slow_queries.count", "performance_alerts.slow_queries.count",
             "Yavaş Sorgu Sayısı", 60.0),
            ("performance_alerts.collscans.count", "performance_alerts.collscans.count",
             "COLLSCAN Sayısı", 50.0),
            ("security_alerts.auth_failures.count", "security_alerts.auth_failures.count",
             "Auth Failure Sayısı", 40.0),
        ],
        "mssql": [
            ("mssql_specific.login_analysis.failed_logins", "mssql_specific.login_analysis.failed_logins",
             "Failed Login Sayısı", 40.0),
            ("mssql_specific.errorlog_analysis.high_severity_errors", "mssql_specific.errorlog_analysis.high_severity_errors",
             "High Severity Error Sayısı", 50.0),
        ],
        "elasticsearch": [
            ("es_specific.critical_patterns.is_oom_error.total", "es_specific.critical_patterns.is_oom_error.total",
             "OOM Event Sayısı", 30.0),
            ("es_specific.critical_patterns.is_circuit_breaker.total", "es_specific.critical_patterns.is_circuit_breaker.total",
             "Circuit Breaker Sayısı", 40.0),
            ("es_specific.critical_patterns.is_shard_failure.total", "es_specific.critical_patterns.is_shard_failure.total",
             "Shard Failure Sayısı", 50.0),
        ],
    }

    @staticmethod
    def _deep_get(d: Dict, dotted_key: str, default=None):
        """Nested dict'ten noktalı key ile değer al. Ör: 'a.b.c' → d['a']['b']['c']"""
        keys = dotted_key.split('.')
        val = d
        for k in keys:
            if isinstance(val, dict):
                val = val.get(k)
            else:
                return default
            if val is None:
                return default
        return val

    def _check_source_specific_trends(self, history: List[Dict], current: Dict,
                                       server_name: Optional[str],
                                       source_type: str) -> List[TrendAlert]:
        """Source-specific metric'lerin trend kontrolü."""
        alerts = []
        src_key = _normalize_source_type(source_type)
        metrics = self._SOURCE_METRICS.get(src_key, [])

        for current_key, history_key, label, threshold_pct in metrics:
            try:
                current_val = self._deep_get(current, current_key)
                if current_val is None or not isinstance(current_val, (int, float)):
                    continue
                current_val = float(current_val)

                # Geçmiş değerleri topla
                past_vals = []
                for record in history:
                    v = self._deep_get(record, history_key)
                    if v is not None and isinstance(v, (int, float)):
                        past_vals.append(float(v))

                if not past_vals:
                    continue

                baseline = sum(past_vals) / len(past_vals)
                if baseline <= 0:
                    if current_val > 0:
                        alerts.append(TrendAlert(
                            alert_type=f"source_metric_new_{src_key}",
                            severity="INFO",
                            title=f"Yeni {label} trendi",
                            description=f"Geçmiş {len(past_vals)} analizde {label} sıfırdı, şimdi {current_val:.0f}.",
                            metric_name=current_key,
                            baseline_value=0,
                            current_value=current_val,
                            change_pct=100.0,
                            window_size=len(past_vals),
                            server_name=server_name,
                            explainability=f"{label} ilk kez sıfırdan farklı değer gösteriyor."
                        ))
                    continue

                change_pct = ((current_val - baseline) / baseline) * 100
                if change_pct > threshold_pct:
                    severity = "CRITICAL" if change_pct > threshold_pct * 2 else "WARNING"
                    alerts.append(TrendAlert(
                        alert_type=f"source_metric_increase_{src_key}",
                        severity=severity,
                        title=f"{label} artıyor",
                        description=f"{label}: baseline {baseline:.1f} → güncel {current_val:.0f} "
                                    f"(%{change_pct:.0f} artış).",
                        metric_name=current_key,
                        baseline_value=round(baseline, 2),
                        current_value=round(current_val, 2),
                        change_pct=round(change_pct, 2),
                        window_size=len(past_vals),
                        server_name=server_name,
                        explainability=f"Son {len(past_vals)} analizde {label} ortalaması {baseline:.1f} idi. "
                                       f"Şimdi {current_val:.0f} → %{change_pct:.0f} artış."
                    ))
            except Exception as e:
                logger.debug(f"Source metric check error for {current_key}: {e}")
                continue

        return alerts

    # ──────────────────────────────────────────────
    # Check: ML Anomaly Score Trend (IsolationForest)
    # ──────────────────────────────────────────────

    def _check_ml_score_trend(self, history: List[Dict], current: Dict,
                              server_name: Optional[str]) -> List[TrendAlert]:
        """
        IsolationForest mean anomaly score trendini kontrol et.

        score_range.mean: Modelin ortalama anomaly skoru.
        Daha negatif → daha anomalous. Skorların sistematik olarak
        kötüleşmesi, anomaly rate artmadan önce erken uyarı verebilir.

        Skor aralığı: tipik olarak -1.0 (çok anomalous) … 0.0 (normal).
        abs(mean) kullanılır: yüksek abs = daha anomalous.
        """
        alerts = []

        # Geçmiş mean score'ları çıkar
        past_scores = []
        for record in history:
            score_range = record.get('score_range') or record.get('summary', {}).get('score_range') or {}
            mean_score = score_range.get('mean')
            if mean_score is not None and isinstance(mean_score, (int, float)):
                past_scores.append(abs(float(mean_score)))

        if len(past_scores) < 2:
            return alerts

        # Current mean score
        current_score_range = current.get('summary', {}).get('score_range', {})
        current_mean = current_score_range.get('mean')
        if current_mean is None or not isinstance(current_mean, (int, float)):
            return alerts
        current_abs = abs(float(current_mean))

        # Baseline: geçmiş ortalama abs(mean_score)
        baseline_abs = sum(past_scores) / len(past_scores)

        if baseline_abs <= 0:
            return alerts

        # Yüzde değişim (abs artıyorsa → daha anomalous)
        change_pct = ((current_abs - baseline_abs) / baseline_abs) * 100

        # Eşik: %30 artış → skorlar belirgin şekilde kötüleşiyor
        ML_SCORE_THRESHOLD = 30.0

        if change_pct > ML_SCORE_THRESHOLD:
            severity = "CRITICAL" if change_pct > ML_SCORE_THRESHOLD * 2 else "WARNING"
            alerts.append(TrendAlert(
                alert_type="ml_score_degradation",
                severity=severity,
                title="ML anomaly skoru kötüleşiyor",
                description=(
                    f"IsolationForest ortalama anomaly skoru son {len(past_scores)} analize göre "
                    f"%{change_pct:.1f} kötüleşti. "
                    f"Baseline |mean|: {baseline_abs:.4f} → Güncel: {current_abs:.4f}. "
                    f"Model daha fazla anomalous davranış tespit ediyor."
                ),
                metric_name="ml_mean_anomaly_score",
                baseline_value=round(baseline_abs, 4),
                current_value=round(current_abs, 4),
                change_pct=round(change_pct, 2),
                window_size=len(past_scores),
                server_name=server_name,
                explainability=(
                    f"IsolationForest modelinin ortalama anomaly skoru (|mean|) "
                    f"son {len(past_scores)} analizde ortalama {baseline_abs:.4f} idi, "
                    f"şimdi {current_abs:.4f}. "
                    f"Bu, sistemde anomaly rate henüz artmamış olsa bile "
                    f"ML modelinin daha fazla anomalous pattern tespit ettiğini gösterir."
                )
            ))

        # Monoton kötüleşme: son 3+ analizde score sürekli artıyor mu?
        if len(past_scores) >= 3:
            recent_3 = past_scores[:3]  # En yeni 3 (DESC sıralı)
            # recent_3[0] en yeni, recent_3[2] en eski → artış = [0] > [1] > [2]
            if all(recent_3[i] >= recent_3[i + 1] for i in range(len(recent_3) - 1)):
                if current_abs > recent_3[0]:
                    alerts.append(TrendAlert(
                        alert_type="ml_score_monotonic_degradation",
                        severity="WARNING",
                        title="ML skoru sürekli kötüleşiyor",
                        description=(
                            f"Son 4 analizde IsolationForest anomaly skoru kesintisiz artıyor: "
                            f"{' → '.join(f'{s:.4f}' for s in reversed(recent_3))} → {current_abs:.4f}. "
                            f"Bu, geçici bir spike değil süregelen bir ML-tespit bozulması olabilir."
                        ),
                        metric_name="ml_score_trend",
                        baseline_value=round(recent_3[-1], 4),
                        current_value=round(current_abs, 4),
                        change_pct=round(change_pct, 2),
                        window_size=4,
                        server_name=server_name,
                        explainability=(
                            f"Son 4 analiz boyunca ML anomaly skoru her seferinde artmış. "
                            f"Anomaly rate henüz eşik aşmamış olsa bile, "
                            f"ML modeli davranış bozulmasını erken tespit ediyor olabilir."
                        )
                    ))

        return alerts

    # ──────────────────────────────────────────────
    # Check: ML Score Distribution Monitoring
    # ──────────────────────────────────────────────

    def _check_ml_score_distribution(self, history: List[Dict], current: Dict,
                                     server_name: Optional[str]) -> List[TrendAlert]:
        """
        ML anomaly score dağılımındaki değişimleri izle.

        Mean score stabil olsa bile:
        - Std dev genişliyorsa → extreme anomaly'ler artıyor
        - Severity distribution kayıyorsa → CRITICAL/HIGH oranı artıyor
        - Score min (en kötü) kötüleşiyorsa → tail risk artıyor

        Bu kontroller mean-based check'in yakalayamadığı erken uyarıları verir.
        """
        alerts = []

        # ── 1. Score spread (std dev) trend ──
        past_stds = []
        past_mins = []
        for record in history:
            sr = record.get('score_range') or record.get('summary', {}).get('score_range') or {}
            std_val = sr.get('std')
            min_val = sr.get('min')
            if std_val is not None and isinstance(std_val, (int, float)):
                past_stds.append(abs(float(std_val)))
            if min_val is not None and isinstance(min_val, (int, float)):
                past_mins.append(abs(float(min_val)))

        current_sr = current.get('summary', {}).get('score_range', {})
        current_std = current_sr.get('std')
        current_min = current_sr.get('min')

        # Std dev genişleme kontrolü
        if past_stds and len(past_stds) >= 2 and current_std is not None:
            current_std_abs = abs(float(current_std))
            baseline_std = sum(past_stds) / len(past_stds)

            if baseline_std > 0:
                std_change_pct = ((current_std_abs - baseline_std) / baseline_std) * 100

                # %50+ std dev artışı → anomaly dağılımı genişliyor
                if std_change_pct > 50.0:
                    severity = "CRITICAL" if std_change_pct > 100.0 else "WARNING"
                    alerts.append(TrendAlert(
                        alert_type="ml_score_spread_widening",
                        severity=severity,
                        title="ML anomaly skor dağılımı genişliyor",
                        description=(
                            f"IsolationForest anomaly skorlarının standart sapması "
                            f"%{std_change_pct:.1f} arttı. "
                            f"Baseline std: {baseline_std:.4f} → Güncel: {current_std_abs:.4f}. "
                            f"Ortalama stabil olsa bile extreme anomaly'ler artıyor olabilir."
                        ),
                        metric_name="ml_score_std_dev",
                        baseline_value=round(baseline_std, 4),
                        current_value=round(current_std_abs, 4),
                        change_pct=round(std_change_pct, 2),
                        window_size=len(past_stds),
                        server_name=server_name,
                        explainability=(
                            f"Anomaly score std dev'i {baseline_std:.4f}'den {current_std_abs:.4f}'e yükseldi "
                            f"(%{std_change_pct:.1f}). Bu, bireysel log'ların anomaly skorlarının "
                            f"daha geniş bir aralığa yayıldığını gösterir. Ortalama skor değişmemiş "
                            f"olsa bile, bazı log'lar çok daha anomalous hale gelmiş olabilir."
                        )
                    ))

        # ── 2. Tail risk: min score (en anomalous) kötüleşme ──
        if past_mins and len(past_mins) >= 2 and current_min is not None:
            current_min_abs = abs(float(current_min))
            baseline_min = sum(past_mins) / len(past_mins)

            if baseline_min > 0:
                min_change_pct = ((current_min_abs - baseline_min) / baseline_min) * 100

                # En anomalous skorun %40+ kötüleşmesi → tail risk
                if min_change_pct > 40.0:
                    severity = "WARNING"
                    alerts.append(TrendAlert(
                        alert_type="ml_tail_risk_increase",
                        severity=severity,
                        title="ML en kötü anomaly skoru kötüleşiyor",
                        description=(
                            f"En anomalous log'ların IsolationForest skoru "
                            f"%{min_change_pct:.1f} kötüleşti. "
                            f"Baseline |min|: {baseline_min:.4f} → Güncel: {current_min_abs:.4f}. "
                            f"Extreme anomaly'ler şiddetleniyor."
                        ),
                        metric_name="ml_score_min",
                        baseline_value=round(baseline_min, 4),
                        current_value=round(current_min_abs, 4),
                        change_pct=round(min_change_pct, 2),
                        window_size=len(past_mins),
                        server_name=server_name,
                        explainability=(
                            f"IsolationForest min score (en anomalous)'un abs değeri "
                            f"{baseline_min:.4f}'den {current_min_abs:.4f}'e yükseldi. "
                            f"Bu, en kötü anomaly'lerin daha da kötüleştiğini gösterir — "
                            f"tail risk artıyor."
                        )
                    ))

        # ── 3. Severity distribution shift ──
        current_sev = current.get('severity_distribution') or {}
        if current_sev:
            current_total = sum(int(v) for v in current_sev.values() if isinstance(v, (int, float)))
            current_critical = int(current_sev.get('CRITICAL', 0)) + int(current_sev.get('HIGH', 0))

            if current_total > 0:
                current_critical_pct = (current_critical / current_total) * 100

                # Geçmiş severity dağılımlarını topla
                past_critical_pcts = []
                for record in history:
                    hist_sev = record.get('severity_distribution') or record.get('summary', {}).get('severity_distribution') or {}
                    if hist_sev:
                        h_total = sum(int(v) for v in hist_sev.values() if isinstance(v, (int, float)))
                        h_crit = int(hist_sev.get('CRITICAL', 0)) + int(hist_sev.get('HIGH', 0))
                        if h_total > 0:
                            past_critical_pcts.append((h_crit / h_total) * 100)

                if past_critical_pcts and len(past_critical_pcts) >= 2:
                    baseline_critical_pct = sum(past_critical_pcts) / len(past_critical_pcts)

                    # Absolute shift: CRITICAL+HIGH oranı %15+ artarsa
                    shift = current_critical_pct - baseline_critical_pct
                    if shift > 15.0:
                        severity = "CRITICAL" if shift > 30.0 else "WARNING"
                        alerts.append(TrendAlert(
                            alert_type="severity_distribution_shift",
                            severity=severity,
                            title="Anomaly ciddiyet dağılımı kötüleşiyor",
                            description=(
                                f"CRITICAL+HIGH anomaly oranı %{baseline_critical_pct:.1f}'den "
                                f"%{current_critical_pct:.1f}'e yükseldi (+{shift:.1f}pp). "
                                f"Anomali sayısı artmasa bile ciddiyeti artıyor."
                            ),
                            metric_name="severity_critical_high_pct",
                            baseline_value=round(baseline_critical_pct, 2),
                            current_value=round(current_critical_pct, 2),
                            change_pct=round(shift, 2),
                            window_size=len(past_critical_pcts),
                            server_name=server_name,
                            explainability=(
                                f"Son {len(past_critical_pcts)} analizde ortalama CRITICAL+HIGH oranı "
                                f"%{baseline_critical_pct:.1f} idi, şimdi %{current_critical_pct:.1f}. "
                                f"Bu, anomali sayısı aynı kalsa bile tespit edilen sorunların "
                                f"daha ciddi hale geldiğini gösterir."
                            )
                        ))

        return alerts

    # ──────────────────────────────────────────────
    # Check: Rate Acceleration (2. türev)
    # ──────────────────────────────────────────────

    def _check_rate_acceleration(self, history: List[Dict], current: Dict,
                                  server_name: Optional[str]) -> List[TrendAlert]:
        """
        Anomaly rate artış hızının artıp artmadığını kontrol et (2. türev).

        Lineer artış: rate 2 → 4 → 6 → 8  (fark: +2, +2, +2)
        İvmelenen artış: rate 2 → 3 → 5 → 9  (fark: +1, +2, +4 — hızlanıyor)

        İvmelenen artış eksponensiyal büyümeye işaret eder ve çok daha ciddidir.
        """
        alerts = []

        # Rate serisi oluştur (en yeniden en eskiye → ters çevir)
        past_rates = []
        for record in history:
            rate = record.get('anomaly_rate', 0)
            if rate is None:
                rate = record.get('summary', {}).get('anomaly_rate', 0)
            past_rates.append(float(rate or 0))

        current_rate = float(current.get('summary', {}).get('anomaly_rate', 0))

        if len(past_rates) < 3:
            return alerts

        # Kronolojik sıra: en eski → en yeni → current
        series = list(reversed(past_rates[:self.lookback])) + [current_rate]

        if len(series) < 4:
            return alerts

        # 1. türev (farklar)
        deltas = [series[i + 1] - series[i] for i in range(len(series) - 1)]

        # 2. türev (farkların farkları)
        accels = [deltas[i + 1] - deltas[i] for i in range(len(deltas) - 1)]

        if not accels:
            return alerts

        # Son 3 ivmelenme pozitifse → artış hızlanıyor
        recent_accels = accels[-min(3, len(accels)):]
        positive_accels = sum(1 for a in recent_accels if a > 0.1)  # gürültü filtresi

        if positive_accels >= 2 and deltas[-1] > 0:
            avg_accel = sum(recent_accels) / len(recent_accels)
            alerts.append(TrendAlert(
                alert_type="rate_acceleration",
                severity="CRITICAL" if avg_accel > 1.0 else "WARNING",
                title="Anomali artış hızı ivmeleniyor",
                description=(
                    f"Anomali oranı artış hızı son {len(recent_accels)} periyotta pozitif ivme gösteriyor. "
                    f"Ortalama ivme: +{avg_accel:.2f} puan/periyot². "
                    f"Son rate serisi: {' → '.join(f'%{r:.1f}' for r in series[-4:])}."
                ),
                metric_name="anomaly_rate_acceleration",
                baseline_value=round(deltas[-2] if len(deltas) >= 2 else 0, 4),
                current_value=round(deltas[-1], 4),
                change_pct=round(avg_accel, 4),
                window_size=len(series),
                server_name=server_name,
                explainability=(
                    f"Anomali oranı sadece artmıyor, artış hızı da hızlanıyor. "
                    f"Bu, lineer bozulma değil üstel büyüme işareti olabilir. "
                    f"İvmelenme devam ederse kısa sürede kontrolden çıkabilir."
                )
            ))

        return alerts

    # ──────────────────────────────────────────────
    # Check: Volatility (Coefficient of Variation)
    # ──────────────────────────────────────────────

    def _check_volatility(self, history: List[Dict], current: Dict,
                          server_name: Optional[str]) -> List[TrendAlert]:
        """
        Anomaly rate'in volatilitesini (dalgalanma) ölç.

        Düşük CV + yükselen trend = güvenilir, sürekli bozulma (daha ciddi)
        Yüksek CV = gürültülü veri, trend yorumları daha az güvenilir

        Coefficient of Variation = std_dev / mean
        """
        alerts = []

        past_rates = []
        for record in history:
            rate = record.get('anomaly_rate', 0)
            if rate is None:
                rate = record.get('summary', {}).get('anomaly_rate', 0)
            past_rates.append(float(rate or 0))

        if len(past_rates) < 4:
            return alerts

        mean_rate = sum(past_rates) / len(past_rates)
        if mean_rate <= 0:
            return alerts

        # Standard deviation (population)
        variance = sum((r - mean_rate) ** 2 for r in past_rates) / len(past_rates)
        std_dev = variance ** 0.5
        cv = std_dev / mean_rate  # Coefficient of Variation

        current_rate = float(current.get('summary', {}).get('anomaly_rate', 0))

        # Düşük volatilite + yükselen trend = güvenilir bozulma sinyali
        if cv < 0.3 and current_rate > mean_rate * 1.3:
            alerts.append(TrendAlert(
                alert_type="stable_degradation",
                severity="WARNING",
                title="Kararlı bozulma trendi",
                description=(
                    f"Anomali oranı düşük volatilite ile (CV={cv:.2f}) sürekli yükseliyor. "
                    f"Baseline ortalama: %{mean_rate:.2f} (σ={std_dev:.2f}) → "
                    f"Güncel: %{current_rate:.2f}. "
                    f"Düşük dalgalanma bu trendin rastgele olmadığını gösterir."
                ),
                metric_name="volatility_cv",
                baseline_value=round(mean_rate, 4),
                current_value=round(current_rate, 4),
                change_pct=round(cv * 100, 2),
                window_size=len(past_rates),
                server_name=server_name,
                explainability=(
                    f"Coefficient of Variation (CV) = {cv:.2f}. "
                    f"CV < 0.3 demek, anomali oranı geçmişte çok stabil değişiyordu. "
                    f"Bu stabil pattern'den belirgin yükselme, rastgele bir spike değil "
                    f"yapısal bir sorunun göstergesidir."
                )
            ))

        return alerts

    # ──────────────────────────────────────────────
    # Check: Improvement Detection
    # ──────────────────────────────────────────────

    def _check_improvement(self, history: List[Dict], current: Dict,
                           server_name: Optional[str]) -> List[TrendAlert]:
        """
        Anomaly rate ve ML score'un belirgin iyileşme gösterip göstermediğini kontrol et.

        Operasyonel değer: fix/config değişikliğinden sonra iyileşme teyidi.
        """
        alerts = []

        past_rates = []
        for record in history:
            rate = record.get('anomaly_rate', 0)
            if rate is None:
                rate = record.get('summary', {}).get('anomaly_rate', 0)
            past_rates.append(float(rate or 0))

        if len(past_rates) < 3:
            return alerts

        current_rate = float(current.get('summary', {}).get('anomaly_rate', 0))
        baseline_rate = sum(past_rates) / len(past_rates)

        if baseline_rate <= 0:
            return alerts

        # Rate %40'tan fazla düştüyse → iyileşme
        change_pct = ((current_rate - baseline_rate) / baseline_rate) * 100

        if change_pct < -40:
            alerts.append(TrendAlert(
                alert_type="improvement_detected",
                severity="INFO",
                title="Anomali oranında iyileşme",
                description=(
                    f"Anomali oranı son {len(past_rates)} analize göre "
                    f"%{abs(change_pct):.0f} azaldı. "
                    f"Baseline: %{baseline_rate:.2f} → Güncel: %{current_rate:.2f}."
                ),
                metric_name="anomaly_rate",
                baseline_value=round(baseline_rate, 4),
                current_value=round(current_rate, 4),
                change_pct=round(change_pct, 2),
                window_size=len(past_rates),
                server_name=server_name,
                explainability=(
                    f"Anomali oranı geçmiş ortalamasının belirgin altına düştü. "
                    f"Bu, yapılan düzeltmelerin veya config değişikliklerinin "
                    f"olumlu etki gösterdiğini işaret edebilir."
                )
            ))

        return alerts

    # ──────────────────────────────────────────────
    # Trend Direction & Summary
    # ──────────────────────────────────────────────

    def _determine_trend_direction(self, alerts: List[TrendAlert],
                                   history: List[Dict], current: Dict) -> str:
        """
        Genel trend yönünü belirle.

        Multi-signal compound logic:
        - Tek WARNING = degrading
        - Tek CRITICAL veya 3+ WARNING = critical
        - Sadece improvement_detected = improving
        - Hiç alert yok = stable
        """
        if not alerts:
            return "stable"

        # İyileşme var mı?
        improvement_only = all(a.alert_type == "improvement_detected" for a in alerts)
        if improvement_only:
            return "improving"

        # Degradation alert'lerini say (improvement hariç)
        degradation_alerts = [a for a in alerts if a.alert_type != "improvement_detected"]
        if not degradation_alerts:
            return "stable"

        severity_scores = {"INFO": 1, "WARNING": 2, "CRITICAL": 3}
        max_score = max(severity_scores.get(a.severity, 0) for a in degradation_alerts)
        warning_count = sum(1 for a in degradation_alerts if a.severity in ("WARNING", "CRITICAL"))

        # Compound risk: 3+ farklı check tipi alarm veriyorsa → critical
        unique_types = set(a.alert_type for a in degradation_alerts if a.severity != "INFO")
        compound_escalation = len(unique_types) >= 3

        if max_score >= 3 or compound_escalation:
            return "critical"
        elif max_score >= 2:
            return "degrading"
        else:
            return "stable"

    def _build_summary(self, history: List[Dict], current: Dict,
                       alerts: List[TrendAlert]) -> Dict[str, Any]:
        """Trend rapor özeti oluştur"""
        # Geçmiş rate'ler
        past_rates = []
        for record in history:
            rate = record.get('anomaly_rate', 0)
            if rate is None:
                rate = record.get('summary', {}).get('anomaly_rate', 0)
            past_rates.append(float(rate or 0))

        current_rate = float(current.get('summary', {}).get('anomaly_rate', 0))

        # ML score trend bilgisi
        past_ml_scores = []
        for record in history:
            sr = record.get('score_range') or record.get('summary', {}).get('score_range') or {}
            m = sr.get('mean')
            if m is not None and isinstance(m, (int, float)):
                past_ml_scores.append(abs(float(m)))

        current_score_range = current.get('summary', {}).get('score_range', {})
        current_mean_raw = current_score_range.get('mean')
        current_ml_score = abs(float(current_mean_raw)) if current_mean_raw is not None else None

        ml_score_summary = {}
        if past_ml_scores and current_ml_score is not None:
            baseline_ml = sum(past_ml_scores) / len(past_ml_scores)
            ml_score_summary = {
                "current_mean_score": round(current_ml_score, 4),
                "baseline_mean_score": round(baseline_ml, 4),
                "ml_score_direction": (
                    "worsening" if current_ml_score > baseline_ml * 1.1 else
                    "improving" if current_ml_score < baseline_ml * 0.9 else
                    "stable"
                ),
            }

        # ML score distribution summary
        current_std_raw = current_score_range.get('std')
        current_min_raw = current_score_range.get('min')
        if current_std_raw is not None:
            ml_score_summary["current_std"] = round(abs(float(current_std_raw)), 4)
        if current_min_raw is not None:
            ml_score_summary["current_min_abs"] = round(abs(float(current_min_raw)), 4)

        # Severity distribution summary
        current_sev = current.get('severity_distribution') or {}
        if current_sev:
            sev_total = sum(int(v) for v in current_sev.values() if isinstance(v, (int, float)))
            if sev_total > 0:
                crit_high = int(current_sev.get('CRITICAL', 0)) + int(current_sev.get('HIGH', 0))
                ml_score_summary["severity_critical_high_pct"] = round(
                    (crit_high / sev_total) * 100, 2)
                ml_score_summary["severity_distribution"] = {
                    k: int(v) for k, v in current_sev.items()
                    if isinstance(v, (int, float))
                }

        # Volatility (coefficient of variation)
        baseline_rate = sum(past_rates) / len(past_rates) if past_rates else 0
        volatility_cv = None
        if past_rates and baseline_rate > 0:
            variance = sum((r - baseline_rate) ** 2 for r in past_rates) / len(past_rates)
            volatility_cv = round((variance ** 0.5) / baseline_rate, 3)

        summary = {
            "history_window": len(history),
            "current_anomaly_rate": round(current_rate, 4),
            "baseline_anomaly_rate": round(baseline_rate, 4),
            "min_historical_rate": round(min(past_rates), 4) if past_rates else 0,
            "max_historical_rate": round(max(past_rates), 4) if past_rates else 0,
            "volatility_cv": volatility_cv,
            "alert_count": len(alerts),
            "alert_types": list(set(a.alert_type for a in alerts)),
            "alert_severities": {
                "INFO": sum(1 for a in alerts if a.severity == "INFO"),
                "WARNING": sum(1 for a in alerts if a.severity == "WARNING"),
                "CRITICAL": sum(1 for a in alerts if a.severity == "CRITICAL"),
            }
        }

        if ml_score_summary:
            summary["ml_score_trend"] = ml_score_summary

        return summary
