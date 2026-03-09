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
import time
from datetime import datetime, timedelta
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

        # CPU guard: batch arası bekleme (saniye)
        self.batch_cooldown_seconds = config.get('batch_cooldown_seconds', 5)
        # Per-host cooldown: aynı host'u tekrar analiz etmeden önce minimum bekleme
        self.per_host_cooldown_minutes = config.get('per_host_cooldown_minutes', 10)
        # Startup delay: sistem açılışında ilk cycle'dan önce bekleme (saniye)
        self._startup_delay_seconds = config.get('startup_delay_seconds', 15)
        # Minimum interval guard: runtime'da interval'ın 5 dk altına düşmesini engelle
        self._min_interval_minutes = 5

        self._timer: Optional[threading.Timer] = None
        self._running = False
        self._lock = threading.Lock()
        self._run_count = 0
        self._last_run: Optional[datetime] = None
        self._last_results: Dict[str, Any] = {}
        self._host_last_analyzed: Dict[str, datetime] = {}  # per-host cooldown tracking
        self._cycle_in_progress = False  # prevent overlapping cycles
        self._last_cycle_duration: Optional[float] = None  # seconds
        self._heartbeat_at: Optional[datetime] = None  # last heartbeat timestamp
        self._cycle_ended_at: Optional[datetime] = None  # last cycle end time
        self._last_cycle_summary: Dict[str, Any] = {}  # last cycle scope summary

        # ── Host-level live state (UI live status feed) ──
        # Updated during each cycle for realtime visibility
        self._current_host: Optional[str] = None       # şu an analiz edilen host
        self._cycle_host_states: Dict[str, Dict[str, Any]] = {}  # host → {state, ...}
        # States: "queued", "processing", "completed", "error", "cooldown"
        self._cycle_started_at: Optional[datetime] = None
        self._cycle_batch: List[str] = []               # bu cycle'daki batch
        self._cycle_queue: List[str] = []                # henüz işlenmemiş host'lar

        # Host-level in-progress registry — prevents scheduler + manual overlap
        self._hosts_in_progress: set = set()

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
        # Startup delay: ilk cycle'ı hemen koşturmak yerine kısa bir süre bekle
        # Böylece sistem (OpenSearch bağlantıları, storage, host discovery) hazır olur
        if not force and self._startup_delay_seconds > 0 and self._run_count == 0:
            logger.info(f"Scheduler startup delay: {self._startup_delay_seconds}s before first cycle")
            self._timer = threading.Timer(self._startup_delay_seconds, self._on_timer)
            self._timer.daemon = True
            self._timer.start()
        elif force:
            # UI'dan başlatıldığında ilk cycle'ı 2 saniye sonra çalıştır
            # (hemen değil — host discovery ve bağlantılar hazır olsun)
            logger.info("Scheduler force-started via UI: first cycle in 2 seconds")
            self._timer = threading.Timer(2, self._on_timer)
            self._timer.daemon = True
            self._timer.start()
        else:
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
        if minutes < self._min_interval_minutes:
            logger.warning(f"Interval must be >= {self._min_interval_minutes} minutes, ignoring (got {minutes})")
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
        now = datetime.utcnow()

        # Next run hesaplama
        next_run = None
        next_run_in_minutes = None
        if self._running and self._last_run:
            next_dt = self._last_run + timedelta(minutes=self.interval_minutes)
            next_run = next_dt.isoformat()
            remaining = (next_dt - now).total_seconds() / 60
            next_run_in_minutes = round(max(remaining, 0), 1)
        elif self._running and not self._last_run:
            # İlk cycle henüz çalışmadı, timer bekliyor
            next_run = "pending"

        # Cycle state: ürün diliyle sade durum
        if self._cycle_in_progress:
            cycle_state = "running"
        elif self._running and self._last_run:
            cycle_state = "waiting"
        elif self._running:
            cycle_state = "starting"
        else:
            cycle_state = "idle"

        # Host-level live state for UI
        live_hosts: Dict[str, Any] = {}
        if self._cycle_in_progress and self._cycle_host_states:
            live_hosts = dict(self._cycle_host_states)
        elif self._last_results:
            # Cycle bitti — son sonuçları göster
            for host, r in self._last_results.items():
                live_hosts[host] = {
                    "state": r.get("status", "unknown"),
                    "anomaly_count": r.get("anomaly_count", 0),
                    "completed_at": r.get("timestamp")
                }
            # Cooldown'daki host'ları da göster
            now = datetime.utcnow()
            cooldown_td = timedelta(minutes=self.per_host_cooldown_minutes)
            for host in self._target_hosts:
                if host not in live_hosts:
                    last = self._host_last_analyzed.get(host)
                    if last and (now - last) < cooldown_td:
                        live_hosts[host] = {
                            "state": "cooldown",
                            "cooldown_until": (last + cooldown_td).isoformat()
                        }
                    else:
                        live_hosts[host] = {"state": "idle"}

        # Active source type
        current_source = getattr(self, '_source_type', 'mongodb')

        # Source label map — dynamic, extensible
        source_labels = {
            'mongodb': 'MongoDB',
            'mssql': 'MSSQL',
            'elasticsearch': 'Elasticsearch',
        }

        # Active sources summary: which sources are available
        available_sources = list(source_labels.keys())

        return {
            "enabled": self.enabled,
            "running": self._running,
            "cycle_state": cycle_state,
            "cycle_in_progress": self._cycle_in_progress,
            "current_host": self._current_host,
            "interval_minutes": self.interval_minutes,
            "max_concurrent": self.max_concurrent,
            "source_type": current_source,
            "source_label": source_labels.get(current_source, current_source),
            "available_sources": available_sources,
            "source_labels": source_labels,
            "host_count": len(self._target_hosts) or len(live_hosts),
            "run_count": self._run_count,
            "last_run": self._last_run.isoformat() if self._last_run else None,
            "next_run": next_run,
            "next_run_in_minutes": next_run_in_minutes,
            "last_cycle_duration_seconds": self._last_cycle_duration,
            "cycle_started_at": self._cycle_started_at.isoformat() if self._cycle_started_at else None,
            "cycle_ended_at": self._cycle_ended_at.isoformat() if self._cycle_ended_at else None,
            "heartbeat_at": self._heartbeat_at.isoformat() if self._heartbeat_at else None,
            "last_cycle_summary": self._last_cycle_summary if self._last_cycle_summary else None,
            "target_hosts": self._target_hosts,
            "host_states": live_hosts,
            "cycle_batch": self._cycle_batch if self._cycle_in_progress else [],
            "cycle_queue": self._cycle_queue if self._cycle_in_progress else [],
            "last_results_summary": {
                host: {
                    "status": r.get("status", "unknown"),
                    "anomaly_count": r.get("anomaly_count", 0)
                }
                for host, r in self._last_results.items()
            }
        }

    def trigger_now(self, server_name: Optional[str] = None) -> Dict[str, Any]:
        """Manuel tetikleme (scheduler çalışmıyorken de kullanılabilir).

        Overlap guard aktif: otomatik cycle sırasında bile çakışmayı engeller.
        """
        if self._cycle_in_progress:
            logger.warning("Manual trigger rejected: a cycle is already in progress")
            return {"status": "rejected", "reason": "cycle_in_progress"}
        if server_name:
            return self._run_analysis(server_name)
        else:
            return self._run_cycle(manual=True)

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

        cycle_start = time.monotonic()
        try:
            logger.info(f"Scheduler cycle #{self._run_count + 1} starting...")
            self._run_cycle()
        except Exception as e:
            logger.error(f"Scheduler cycle error: {e}")
        finally:
            elapsed = round(time.monotonic() - cycle_start, 2)
            self._last_cycle_duration = elapsed
            self._heartbeat_at = datetime.utcnow()
            next_in = self.interval_minutes
            logger.info(f"Scheduler heartbeat: cycle completed in {elapsed}s, "
                        f"next cycle in {next_in} min, "
                        f"total runs={self._run_count}, running={self._running}")
            # Sonraki çalışmayı zamanlayıcıya ekle
            self._schedule_next()

    def _run_cycle(self, manual: bool = False) -> Dict[str, Any]:
        """
        Tek bir scheduler döngüsü — tüm hedef sunucuları analiz et.

        Args:
            manual: True ise trigger_now'dan çağrılmış — _running kontrolü yapılmaz

        CPU korumaları:
        - max_concurrent: Tek cycle'da en fazla N host analiz edilir
        - per_host_cooldown: Aynı host cooldown süresi dolmadan tekrar analiz edilmez
        - batch_cooldown: Her host analizi arasında kısa bekleme (CPU throttle)
        - overlap guard: Önceki cycle bitmeden yeni cycle başlamaz
        """
        # Overlap guard
        if self._cycle_in_progress:
            logger.warning("Previous cycle still in progress, skipping this trigger")
            return {"status": "skipped", "reason": "previous_cycle_in_progress"}

        self._cycle_in_progress = True
        self._cycle_started_at = datetime.utcnow()
        self._cycle_host_states = {}
        self._current_host = None
        self._cycle_batch = []
        self._cycle_queue = []
        try:
            self._run_count += 1
            self._last_run = datetime.utcnow()
            cycle_results = {}

            if not self._target_hosts:
                # Auto-discover hosts based on active source type
                try:
                    source = getattr(self, '_source_type', 'mongodb')
                    discovered = []
                    if source == 'mongodb':
                        from src.anomaly.log_reader import get_available_mongodb_hosts
                        discovered = get_available_mongodb_hosts(last_hours=24)
                    elif source == 'mssql':
                        from src.anomaly.mssql_log_reader import get_available_mssql_hosts
                        discovered = get_available_mssql_hosts(last_hours=24)
                    elif source == 'elasticsearch':
                        from src.anomaly.elasticsearch_log_reader import get_available_es_hosts
                        discovered = get_available_es_hosts(last_hours=24)

                    if discovered:
                        self._target_hosts = list(discovered)
                        logger.info(f"Scheduler auto-discovered {len(discovered)} {source} hosts")
                    else:
                        logger.info(f"No target hosts configured and auto-discovery found none for {source}, skipping cycle")
                        return {"status": "skipped", "reason": "no_target_hosts"}
                except Exception as disc_err:
                    logger.warning(f"Host auto-discovery failed: {disc_err}")
                    logger.info("No target hosts configured, skipping cycle")
                    return {"status": "skipped", "reason": "no_target_hosts"}

            now = datetime.utcnow()
            cooldown_td = timedelta(minutes=self.per_host_cooldown_minutes)

            # Filter hosts by per-host cooldown
            eligible_hosts = []
            skipped_cooldown = []
            for host in self._target_hosts:
                last = self._host_last_analyzed.get(host)
                if last and (now - last) < cooldown_td:
                    skipped_cooldown.append(host)
                    self._cycle_host_states[host] = {
                        "state": "cooldown",
                        "cooldown_until": (last + cooldown_td).isoformat()
                    }
                else:
                    eligible_hosts.append(host)

            if skipped_cooldown:
                logger.debug(f"Hosts skipped (cooldown): {skipped_cooldown}")

            # Batch: take up to max_concurrent from eligible
            batch = eligible_hosts[:self.max_concurrent]
            self._cycle_batch = list(batch)
            self._cycle_queue = list(batch)

            # Mark queued hosts
            for h in batch:
                self._cycle_host_states[h] = {"state": "queued"}

            if not batch:
                logger.info(f"No eligible hosts (all in cooldown). "
                            f"Total: {len(self._target_hosts)}, cooldown: {len(skipped_cooldown)}")
                return {
                    "status": "skipped",
                    "reason": "all_hosts_in_cooldown",
                    "cooldown_hosts": skipped_cooldown
                }

            logger.info(f"Scheduler cycle #{self._run_count}: analyzing {len(batch)}/{len(self._target_hosts)} hosts")

            for i, host in enumerate(batch):
                if not manual and not self._running:
                    logger.info("Scheduler stopped mid-cycle, aborting remaining hosts")
                    break

                # Update live state
                self._current_host = host
                self._cycle_host_states[host] = {
                    "state": "processing",
                    "started_at": datetime.utcnow().isoformat()
                }
                if host in self._cycle_queue:
                    self._cycle_queue.remove(host)

                try:
                    result = self._run_analysis(host)
                    cycle_results[host] = result
                    self._host_last_analyzed[host] = datetime.utcnow()
                    self._cycle_host_states[host] = {
                        "state": "completed",
                        "anomaly_count": result.get("anomaly_count", 0),
                        "completed_at": datetime.utcnow().isoformat()
                    }
                except Exception as e:
                    logger.error(f"Analysis failed for {host}: {e}")
                    cycle_results[host] = {"status": "error", "error": str(e)}
                    self._cycle_host_states[host] = {
                        "state": "error",
                        "error": str(e)
                    }

                # CPU throttle: batch arası bekleme (son host hariç)
                if i < len(batch) - 1 and self.batch_cooldown_seconds > 0:
                    time.sleep(self.batch_cooldown_seconds)

            self._current_host = None
            self._last_results = cycle_results

            total_anomalies = sum(
                r.get("anomaly_count", 0) for r in cycle_results.values()
            )
            hosts_errored = sum(1 for r in cycle_results.values() if r.get("status") == "error")

            logger.info(f"Scheduler cycle #{self._run_count} completed: "
                         f"{len(cycle_results)} hosts analyzed, "
                         f"{total_anomalies} total anomalies, "
                         f"{hosts_errored} errors")

            self._last_cycle_summary = {
                "cycle_number": self._run_count,
                "hosts_analyzed": len(cycle_results),
                "hosts_errored": hosts_errored,
                "hosts_skipped_cooldown": len(skipped_cooldown),
                "total_anomalies": total_anomalies,
                "source_type": getattr(self, '_source_type', 'mongodb'),
            }

            return {
                "status": "completed",
                "cycle": self._run_count,
                "hosts_analyzed": len(cycle_results),
                "total_anomalies": total_anomalies,
                "skipped_cooldown": len(skipped_cooldown),
                "results": cycle_results
            }
        finally:
            self._cycle_ended_at = datetime.utcnow()
            self._cycle_in_progress = False
            self._current_host = None

    def is_host_busy(self, server_name: str) -> bool:
        """Host'un şu an scheduler tarafından analiz edilip edilmediğini kontrol et.

        Manuel analiz başlatmadan önce çağrılır — çakışmayı önler.
        """
        with self._lock:
            return server_name in self._hosts_in_progress

    def get_busy_hosts(self) -> List[str]:
        """Şu an analiz edilen host listesini döndür."""
        with self._lock:
            return list(self._hosts_in_progress)

    def _run_analysis(self, server_name: str) -> Dict[str, Any]:
        """Tek bir sunucu için analiz çalıştır"""
        if not self.analysis_callback:
            return {"status": "error", "error": "no_callback"}

        # Host-level lock
        with self._lock:
            if server_name in self._hosts_in_progress:
                logger.warning(f"Host {server_name} already being analyzed, skipping")
                return {"status": "skipped", "reason": "host_in_progress", "server_name": server_name}
            self._hosts_in_progress.add(server_name)

        try:
            source = getattr(self, '_source_type', 'mongodb')
            logger.info(f"Running scheduled analysis for: {server_name} (source={source})")
            result = self.analysis_callback(server_name, source)

            # Callback sonucundan anomaly count çıkar
            # _format_result çıktısı: {"durum":..., "sonuç": {summary:{n_anomalies:N},...}}
            # Callback parse edip dict döndürür → "sonuç" anahtarı altında aranmalı.
            anomaly_count = 0
            if isinstance(result, dict):
                # Önce "sonuç" altında ara (callback parsed _format_result)
                sonuc = result.get("sonuç") or result.get("data") or {}
                if isinstance(sonuc, dict):
                    summary = sonuc.get("summary", {})
                    anomaly_count = summary.get("n_anomalies", 0)
                # Fallback: doğrudan top-level summary (raw dict dönerse)
                if anomaly_count == 0 and "summary" in result:
                    anomaly_count = result["summary"].get("n_anomalies", 0)
            elif isinstance(result, str):
                import json
                try:
                    parsed = json.loads(result)
                    sonuc = parsed.get("sonuç") or parsed.get("data") or {}
                    if isinstance(sonuc, dict):
                        anomaly_count = sonuc.get("summary", {}).get("n_anomalies", 0)
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
        finally:
            with self._lock:
                self._hosts_in_progress.discard(server_name)
