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
                server_name: Optional[str] = None) -> TrendReport:
        """
        Geçmiş analizler ile mevcut analizi karşılaştırarak trend raporu üret.

        Args:
            history_records: anomaly_history'den çekilen son N kayıt (timestamp DESC sıralı)
            current_analysis: Şu anki analiz sonucu (analysis dict)
            server_name: Sunucu adı

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
    # Trend Direction & Summary
    # ──────────────────────────────────────────────

    def _determine_trend_direction(self, alerts: List[TrendAlert],
                                   history: List[Dict], current: Dict) -> str:
        """Genel trend yönünü belirle"""
        if not alerts:
            return "stable"

        severity_scores = {"INFO": 1, "WARNING": 2, "CRITICAL": 3}
        max_score = max(severity_scores.get(a.severity, 0) for a in alerts)

        if max_score >= 3:
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

        return {
            "history_window": len(history),
            "current_anomaly_rate": round(current_rate, 4),
            "baseline_anomaly_rate": round(sum(past_rates) / len(past_rates), 4) if past_rates else 0,
            "min_historical_rate": round(min(past_rates), 4) if past_rates else 0,
            "max_historical_rate": round(max(past_rates), 4) if past_rates else 0,
            "alert_count": len(alerts),
            "alert_types": list(set(a.alert_type for a in alerts)),
            "alert_severities": {
                "INFO": sum(1 for a in alerts if a.severity == "INFO"),
                "WARNING": sum(1 for a in alerts if a.severity == "WARNING"),
                "CRITICAL": sum(1 for a in alerts if a.severity == "CRITICAL"),
            }
        }
