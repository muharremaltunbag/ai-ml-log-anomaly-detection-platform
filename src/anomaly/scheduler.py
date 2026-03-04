# src/anomaly/scheduler.py

"""
Anomaly Detection Scheduler - Periyodik otomatik analiz

Mevcut pipeline'ı periyodik olarak tetikler. İzole katman.
Kapatılabilir: config.prediction.scheduler.enabled = false

Dependency: Yok (Python stdlib threading.Timer kullanır)

Kullanım:
    scheduler = AnomalyScheduler(config, analysis_callback)
    scheduler.start()
    ...
    scheduler.stop()
"""

import logging
import threading
from datetime import datetime
from typing import Dict, Any, Callable, Optional, List

logger = logging.getLogger(__name__)


class AnomalyScheduler:
    """
    Periyodik anomaly analizi scheduler'ı.

    Hafif, threading.Timer bazlı. APScheduler gibi dış dependency gerektirmez.
    Config-driven, runtime'da start/stop edilebilir.
    """

    def __init__(self, config: Dict[str, Any],
                 analysis_callback: Optional[Callable] = None):
        """
        Args:
            config: prediction.scheduler bloğu
            analysis_callback: Her periyotta çağrılacak fonksiyon
                               Signature: callback(server_name: str) -> Dict
        """
        self.enabled = config.get('enabled', False)
        self.interval_minutes = config.get('interval_minutes', 30)
        self.auto_analyze_hosts = config.get('auto_analyze_hosts', True)
        self.max_concurrent = config.get('max_concurrent_analyses', 3)
        self.analysis_callback = analysis_callback

        self._timer: Optional[threading.Timer] = None
        self._running = False
        self._lock = threading.Lock()
        self._run_count = 0
        self._last_run: Optional[datetime] = None
        self._last_results: Dict[str, Any] = {}

        # Analiz edilecek sunucu listesi (runtime'da set edilir)
        self._target_hosts: List[str] = []
        # Aktif veri kaynağı — UI'dan değiştirilebilir
        self._source_type: str = config.get('source_type', 'mongodb')

        logger.info(f"AnomalyScheduler initialized (enabled={self.enabled}, "
                     f"interval={self.interval_minutes}min, "
                     f"max_concurrent={self.max_concurrent})")

    def set_target_hosts(self, hosts: List[str]) -> None:
        """Periyodik analiz yapılacak sunucu listesini ayarla"""
        with self._lock:
            self._target_hosts = list(hosts)
            logger.info(f"Scheduler target hosts updated: {len(hosts)} hosts")

    def start(self, force: bool = False) -> bool:
        """
        Scheduler'ı başlat.

        Args:
            force: True ise config'de disabled olsa bile başlatır.
                   UI'dan başlatıldığında kullanılır.
        """
        if not self.enabled and not force:
            logger.info("Scheduler is disabled in config, not starting")
            return False

        if self._running:
            logger.warning("Scheduler is already running")
            return True

        if not self.analysis_callback:
            logger.error("No analysis callback set, cannot start scheduler")
            return False

        with self._lock:
            self._running = True
            # Runtime enable — UI'dan başlatıldığında config override
            if force and not self.enabled:
                self.enabled = True
                logger.info("Scheduler runtime-enabled via UI/API")

        logger.info(f"Scheduler started: will run every {self.interval_minutes} minutes")
        self._schedule_next()
        return True

    def stop(self) -> None:
        """Scheduler'ı durdur"""
        with self._lock:
            self._running = False
            if self._timer:
                self._timer.cancel()
                self._timer = None

        logger.info(f"Scheduler stopped after {self._run_count} runs")

    def is_running(self) -> bool:
        return self._running

    def set_enabled(self, enabled: bool) -> None:
        """Runtime enable/disable — UI'dan çağrılır, config dosyasını değiştirmez."""
        with self._lock:
            prev = self.enabled
            self.enabled = enabled
            if not enabled and self._running:
                # Disable edilirken çalışıyorsa durdur
                self._running = False
                if self._timer:
                    self._timer.cancel()
                    self._timer = None
                logger.info("Scheduler disabled and stopped via runtime toggle")
            logger.info(f"Scheduler enabled state changed: {prev} -> {enabled}")

    def set_interval(self, minutes: int) -> None:
        """Runtime interval değişikliği. Mevcut timer'ı yeniden planlar."""
        if minutes < 1:
            logger.warning("Interval must be >= 1 minute, ignoring")
            return
        with self._lock:
            self.interval_minutes = minutes
            logger.info(f"Scheduler interval changed to {minutes} min")
            # Çalışıyorsa sonraki cycle yeni interval ile planlanır
            # (mevcut timer dokunulmaz, bir sonrakinde geçerli olur)

    def set_source_type(self, source_type: str) -> None:
        """Scheduler'ın hangi veri kaynağına analiz yapacağını belirle."""
        with self._lock:
            self._source_type = source_type
            logger.info(f"Scheduler source_type set to: {source_type}")

    def get_status(self) -> Dict[str, Any]:
        """Scheduler durumunu döndür"""
        # Next run hesaplama
        next_run = None
        if self._running and self._last_run:
            from datetime import timedelta
            next_dt = self._last_run + timedelta(minutes=self.interval_minutes)
            next_run = next_dt.isoformat()
        elif self._running and not self._last_run:
            # İlk cycle henüz çalışmadı, timer bekliyor
            next_run = "pending"

        return {
            "enabled": self.enabled,
            "running": self._running,
            "interval_minutes": self.interval_minutes,
            "max_concurrent": self.max_concurrent,
            "source_type": getattr(self, '_source_type', 'mongodb'),
            "run_count": self._run_count,
            "last_run": self._last_run.isoformat() if self._last_run else None,
            "next_run": next_run,
            "target_hosts": self._target_hosts,
            "last_results_summary": {
                host: {
                    "status": r.get("status", "unknown"),
                    "anomaly_count": r.get("anomaly_count", 0)
                }
                for host, r in self._last_results.items()
            }
        }

    def trigger_now(self, server_name: Optional[str] = None) -> Dict[str, Any]:
        """Manuel tetikleme (scheduler çalışmıyorken de kullanılabilir)"""
        if server_name:
            return self._run_analysis(server_name)
        else:
            return self._run_cycle()

    def _schedule_next(self) -> None:
        """Sonraki çalışmayı zamanlayıcıya ekle"""
        if not self._running:
            return

        interval_seconds = self.interval_minutes * 60
        self._timer = threading.Timer(interval_seconds, self._on_timer)
        self._timer.daemon = True  # Ana uygulama kapanırsa thread de kapansın
        self._timer.start()

    def _on_timer(self) -> None:
        """Timer tetiklendiğinde çağrılır"""
        if not self._running:
            return

        try:
            logger.info(f"Scheduler cycle #{self._run_count + 1} starting...")
            self._run_cycle()
        except Exception as e:
            logger.error(f"Scheduler cycle error: {e}")
        finally:
            # Sonraki çalışmayı zamanlayıcıya ekle
            self._schedule_next()

    def _run_cycle(self) -> Dict[str, Any]:
        """Tek bir scheduler döngüsü — tüm hedef sunucuları analiz et"""
        self._run_count += 1
        self._last_run = datetime.utcnow()
        cycle_results = {}

        if not self._target_hosts:
            logger.info("No target hosts configured, skipping cycle")
            return {"status": "skipped", "reason": "no_target_hosts"}

        # Sıralı çalıştır (max_concurrent için thread pool eklenebilir ama şimdilik basit)
        for host in self._target_hosts[:self.max_concurrent]:
            try:
                result = self._run_analysis(host)
                cycle_results[host] = result
            except Exception as e:
                logger.error(f"Analysis failed for {host}: {e}")
                cycle_results[host] = {"status": "error", "error": str(e)}

        self._last_results = cycle_results

        total_anomalies = sum(
            r.get("anomaly_count", 0) for r in cycle_results.values()
        )
        logger.info(f"Scheduler cycle #{self._run_count} completed: "
                     f"{len(cycle_results)} hosts analyzed, "
                     f"{total_anomalies} total anomalies")

        return {
            "status": "completed",
            "cycle": self._run_count,
            "hosts_analyzed": len(cycle_results),
            "total_anomalies": total_anomalies,
            "results": cycle_results
        }

    def _run_analysis(self, server_name: str) -> Dict[str, Any]:
        """Tek bir sunucu için analiz çalıştır"""
        if not self.analysis_callback:
            return {"status": "error", "error": "no_callback"}

        try:
            source = getattr(self, '_source_type', 'mongodb')
            logger.info(f"Running scheduled analysis for: {server_name} (source={source})")
            result = self.analysis_callback(server_name, source)

            # Callback sonucundan anomaly count çıkar
            anomaly_count = 0
            if isinstance(result, dict):
                data = result.get("data", {})
                summary = data.get("summary", {})
                anomaly_count = summary.get("n_anomalies", 0)
            elif isinstance(result, str):
                # JSON string olabilir
                import json
                try:
                    parsed = json.loads(result)
                    data = parsed.get("sonuç", {}).get("data", {})
                    anomaly_count = data.get("summary", {}).get("n_anomalies", 0)
                except (json.JSONDecodeError, AttributeError):
                    pass

            return {
                "status": "completed",
                "server_name": server_name,
                "anomaly_count": anomaly_count,
                "timestamp": datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.error(f"Scheduled analysis failed for {server_name}: {e}")
            return {
                "status": "error",
                "server_name": server_name,
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
