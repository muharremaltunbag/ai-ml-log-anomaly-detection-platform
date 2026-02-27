// web_ui/static/script-prediction.js
/**
 * LC Waikiki MongoDB Assistant - Prediction Dashboard Module
 *
 * Standalone dashboard that fetches prediction data via API:
 *   - /api/prediction/alerts      → alert history table
 *   - /api/prediction/summary     → summary cards
 *   - /api/prediction/timeseries  → time-series chart data
 *   - /api/prediction/config      → config pills & badge
 *   - /api/scheduler/status    → scheduler status panel
 *   - /api/scheduler/start     → start scheduler (POST, confirmation)
 *   - /api/scheduler/stop      → stop scheduler (POST, confirmation)
 *   - /api/scheduler/trigger   → manual trigger (POST, confirmation)
 *
 * CSS prefix: .ppd-*  (prediction-panel-dashboard)
 * HTML section: #predictionDashboardSection
 * Quick-action button: #predictionDashboardBtn
 */

(function () {
    'use strict';

    console.log('🔧 Loading script-prediction.js...');

    // ── helpers ──
    var esc = function (s) {
        if (window.escapeHtml) return window.escapeHtml(s);
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    };

    function _apiUrl(endpointKey, extra) {
        var base = window.API_ENDPOINTS ? window.API_ENDPOINTS[endpointKey] : null;
        if (!base) {
            console.warn('[PredictionDashboard] Unknown endpoint:', endpointKey);
            return null;
        }
        var key = window.apiKey || '';
        var url = base + '?api_key=' + encodeURIComponent(key);
        if (extra) url += '&' + extra;
        return url;
    }

    // ── state ──
    var _visible = false;
    var _loading = false;

    // ── DOM references (lazy) ──
    function _el(id) { return document.getElementById(id); }

    // ============================
    // MODAL OVERLAY VISIBILITY
    // ============================
    function _getOverlay() { return _el('ppsOverlay'); }

    function toggleDashboard() {
        _visible ? hideDashboard() : showDashboard();
    }

    function showDashboard() {
        var overlay = _getOverlay();
        if (!overlay) return;
        _visible = true;
        overlay.style.display = 'flex';
        document.body.classList.add('pps-body-lock');
        _syncSourceToggle();
        refreshAll();
    }

    // ============================
    // SOURCE TOGGLE
    // ============================
    function _syncSourceToggle() {
        var current = window.selectedDataSource || 'opensearch';
        var container = _el('ppsSourceToggle');
        if (!container) return;
        var btns = container.querySelectorAll('.pps-source-btn');
        for (var i = 0; i < btns.length; i++) {
            if (btns[i].getAttribute('data-source') === current) {
                btns[i].classList.add('pps-source-active');
            } else {
                btns[i].classList.remove('pps-source-active');
            }
        }
    }

    // Map selectedDataSource (storage-level) → prediction source_type
    var _sourceTypeMap = {
        'opensearch': 'mongodb',
        'mssql_opensearch': 'mssql',
        'elasticsearch_opensearch': 'elasticsearch'
    };

    function _getSourceType() {
        var ds = window.selectedDataSource || 'opensearch';
        return _sourceTypeMap[ds] || null;
    }

    function _initSourceToggle() {
        var container = _el('ppsSourceToggle');
        if (!container) return;
        container.addEventListener('click', function (e) {
            var btn = e.target.closest('.pps-source-btn');
            if (!btn) return;
            var source = btn.getAttribute('data-source');
            if (!source) return;

            // Update main page datasource radio (keeps in sync)
            var radio = document.querySelector('input[name="dataSource"][value="' + source + '"]');
            if (radio) {
                radio.checked = true;
                radio.dispatchEvent(new Event('change', { bubbles: true }));
            }
            window.selectedDataSource = source;

            // Update toggle visual
            _syncSourceToggle();

            // Refresh prediction data with new source filter
            refreshAll();
        });
    }

    function hideDashboard() {
        var overlay = _getOverlay();
        if (!overlay) return;
        _visible = false;
        overlay.style.display = 'none';
        document.body.classList.remove('pps-body-lock');
    }

    // ============================
    // REFRESH ALL DATA
    // ============================
    function refreshAll() {
        if (_loading) return;
        var serverVal = (_el('ppdServerFilter') || {}).value || '';
        var daysVal = (_el('ppdDaysFilter') || {}).value || '7';
        loadConfig();
        loadSummary(serverVal, daysVal);
        loadAlerts(serverVal, daysVal);
        loadTimeseries(serverVal, daysVal);
        loadSchedulerStatus();
    }

    // ============================
    // LOAD CONFIG
    // ============================
    function loadConfig() {
        var url = _apiUrl('predictionConfig');
        if (!url) return;

        fetch(url)
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.status !== 'success') return;
                renderConfig(data.prediction_config || {});
            })
            .catch(function (err) {
                console.warn('[PredictionDashboard] Config fetch error:', err);
            });
    }

    function renderConfig(cfg) {
        // Badge
        var badge = _el('ppdConfigBadge');
        if (badge) {
            badge.textContent = cfg.enabled ? 'AKTIF' : 'PASIF';
            badge.className = 'ppd-header-badge ' + (cfg.enabled ? 'ppd-badge-on' : 'ppd-badge-off');
        }

        // Config pills
        var grid = _el('ppdConfigGrid');
        if (!grid) return;

        var pills = [
            { label: 'Trend Detection', on: !!(cfg.trend_detection && cfg.trend_detection.enabled) },
            { label: 'Rate Alerting', on: !!(cfg.rate_alerting && cfg.rate_alerting.enabled) },
            { label: 'Forecasting', on: !!(cfg.forecasting && cfg.forecasting.enabled) },
            { label: 'Scheduler', on: !!(cfg.scheduler && cfg.scheduler.enabled) }
        ];

        var html = '';
        var allOff = true;
        for (var i = 0; i < pills.length; i++) {
            var p = pills[i];
            if (p.on) allOff = false;
            html += '<span class="ppd-config-pill ' + (p.on ? 'ppd-pill-on' : 'ppd-pill-off') + '">'
                + esc(p.label) + ': ' + (p.on ? 'ON' : 'OFF') + '</span>';
        }

        // Hint when all modules disabled
        if (allOff) {
            html += '<div class="pps-config-hint">'
                + 'Tum prediction modulleri devre disi. '
                + 'Etkinlestirmek icin <code>config/anomaly_config.json</code> dosyasindaki '
                + '<code>prediction</code> bolumunu yapilandiriniz.'
                + '</div>';
        }

        grid.innerHTML = html;
    }

    // ============================
    // LOAD SUMMARY
    // ============================
    function loadSummary(server, days) {
        var extra = 'days=' + encodeURIComponent(days);
        if (server) extra += '&server_name=' + encodeURIComponent(server);
        var st = _getSourceType();
        if (st) extra += '&source_type=' + encodeURIComponent(st);
        var url = _apiUrl('predictionSummary', extra);
        if (!url) return;

        var grid = _el('ppdSummaryGrid');
        if (grid) grid.innerHTML = '<div class="ppd-loading"><div class="ppd-loading-spinner"></div><br>Yukleniyor...</div>';

        fetch(url)
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.status !== 'success') {
                    if (grid) grid.innerHTML = '<div class="ppd-empty">Veri alinamadi</div>';
                    return;
                }
                renderSummary(data.summary || {});
            })
            .catch(function (err) {
                console.warn('[PredictionDashboard] Summary fetch error:', err);
                if (grid) grid.innerHTML = '<div class="ppd-error">Baglanti hatasi</div>';
            });
    }

    function renderSummary(summary) {
        var grid = _el('ppdSummaryGrid');
        if (!grid) return;

        var totalChecks = summary.total_checks || 0;
        var totalAlerts = summary.total_alerts || 0;
        var periodDays = summary.period_days || 7;
        var breakdown = summary.breakdown || {};

        // Compute per-source totals
        var trendTotal = 0, trendAlerts = 0;
        var rateTotal = 0, rateAlerts = 0;
        var forecastTotal = 0, forecastAlerts = 0;
        var keys = Object.keys(breakdown);
        for (var i = 0; i < keys.length; i++) {
            var k = keys[i];
            var v = breakdown[k];
            if (k.indexOf('trend') === 0) { trendTotal += v.count; trendAlerts += v.with_alerts; }
            else if (k.indexOf('rate') === 0) { rateTotal += v.count; rateAlerts += v.with_alerts; }
            else if (k.indexOf('forecast') === 0) { forecastTotal += v.count; forecastAlerts += v.with_alerts; }
        }

        var alertRate = totalChecks > 0 ? ((totalAlerts / totalChecks) * 100).toFixed(1) : '0.0';

        var html = '';

        // Empty state banner if no checks at all
        if (totalChecks === 0) {
            html += '<div class="pps-empty-state">'
                + '<div class="pps-empty-icon">&#x1F4CA;</div>'
                + '<div class="pps-empty-title">Henuz prediction verisi yok</div>'
                + '<div class="pps-empty-desc">Bu zaman araliginda hic analiz yapilmamis. '
                + 'Anomali analizi calistirarak veya Scheduler\'i baslat butonuyla otomatik analiz etkinlestirerek baslayabilirsiniz.</div>'
                + '</div>';
        }

        var cards = [
            { title: 'Toplam Kontrol', value: totalChecks, sub: 'Son ' + periodDays + ' gun', cls: '' },
            { title: 'Toplam Uyari', value: totalAlerts, sub: 'Alert orani: %' + alertRate, cls: totalAlerts > 0 ? 'ppd-card-warn' : '' },
            { title: 'Trend Alerts', value: trendAlerts + ' / ' + trendTotal, sub: 'Trend analiz', cls: trendAlerts > 0 ? 'ppd-card-warn' : '' },
            { title: 'Rate Alerts', value: rateAlerts + ' / ' + rateTotal, sub: 'Rate alerting', cls: rateAlerts > 0 ? 'ppd-card-warn' : '' },
            { title: 'Forecast Alerts', value: forecastAlerts + ' / ' + forecastTotal, sub: 'Tahmin modeli', cls: forecastAlerts > 0 ? 'ppd-card-warn' : '' }
        ];

        for (var j = 0; j < cards.length; j++) {
            var c = cards[j];
            html += '<div class="ppd-summary-card ' + c.cls + '">'
                + '<div class="ppd-card-title">' + esc(c.title) + '</div>'
                + '<div class="ppd-card-value">' + esc(String(c.value)) + '</div>'
                + '<div class="ppd-card-sub">' + esc(c.sub) + '</div>'
                + '</div>';
        }
        grid.innerHTML = html;
    }

    // ============================
    // LOAD ALERTS (TABLE)
    // ============================
    function loadAlerts(server, days) {
        var extra = 'days=' + encodeURIComponent(days) + '&limit=50';
        if (server) extra += '&server_name=' + encodeURIComponent(server);
        var st = _getSourceType();
        if (st) extra += '&source_type=' + encodeURIComponent(st);
        var url = _apiUrl('predictionAlerts', extra);
        if (!url) return;

        _loading = true;
        var wrapper = _el('ppdTableWrapper');
        var tbody = _el('ppdTableBody');

        fetch(url)
            .then(function (r) { return r.json(); })
            .then(function (data) {
                _loading = false;
                if (data.status !== 'success' || !data.alerts || data.alerts.length === 0) {
                    if (wrapper) {
                        wrapper.style.display = 'block';
                        var emptyTbody = _el('ppdTableBody');
                        if (emptyTbody) {
                            emptyTbody.innerHTML = '<tr><td colspan="6" class="pps-table-empty">'
                                + '<div class="pps-empty-icon" style="font-size:24px;">&#x1F50D;</div>'
                                + '<div style="margin-top:6px;font-weight:600;color:#555;">Bu zaman araliginda alert kaydi bulunamadi</div>'
                                + '<div style="margin-top:4px;font-size:12px;color:#999;">Farkli bir zaman araligi veya sunucu filtresi deneyin.</div>'
                                + '</td></tr>';
                        }
                    }
                    return;
                }
                renderAlerts(data.alerts);
                populateServerFilter(data.alerts);
            })
            .catch(function (err) {
                _loading = false;
                console.warn('[PredictionDashboard] Alerts fetch error:', err);
            });
    }

    function renderAlerts(alerts) {
        var wrapper = _el('ppdTableWrapper');
        var tbody = _el('ppdTableBody');
        if (!tbody || !wrapper) return;

        var html = '';
        for (var i = 0; i < alerts.length; i++) {
            var a = alerts[i];
            var ts = a.timestamp || '';
            if (ts && ts.length > 19) ts = ts.substring(0, 19).replace('T', ' ');
            var source = a.alert_source || '-';
            var server = a.server_name || '-';
            var severity = a.max_severity || 'INFO';
            var hasAlerts = a.has_alerts;
            var alertCount = 0;

            // Count alerts from nested data.alerts (backend stores alerts in data.alerts)
            var dataAlerts = (a.data && Array.isArray(a.data.alerts)) ? a.data.alerts : [];
            alertCount = dataAlerts.length;
            // Fallback: top-level alert_count field
            if (alertCount === 0 && a.alert_count) alertCount = a.alert_count;
            if (alertCount === 0 && hasAlerts) alertCount = '?';

            var sevClass = 'ppd-sev-' + severity.toLowerCase();

            // Build detail snippet
            var detail = _buildDetailSnippet(a);

            html += '<tr>'
                + '<td>' + esc(ts) + '</td>'
                + '<td>' + esc(source) + '</td>'
                + '<td>' + esc(server) + '</td>'
                + '<td><span class="ppd-severity-tag ' + sevClass + '">' + esc(severity) + '</span></td>'
                + '<td>' + esc(String(alertCount)) + '</td>'
                + '<td class="ppd-detail-cell">' + detail + '</td>'
                + '</tr>';
        }
        tbody.innerHTML = html;
        wrapper.style.display = 'block';
    }

    function _buildDetailSnippet(alertDoc) {
        var parts = [];

        // Backend stores all alerts in data.alerts (source-specific via alert_source field)
        var dataAlerts = (alertDoc.data && Array.isArray(alertDoc.data.alerts))
            ? alertDoc.data.alerts : [];

        for (var i = 0; i < Math.min(dataAlerts.length, 3); i++) {
            var al = dataAlerts[i];
            parts.push(esc(al.title || al.alert_type || alertDoc.alert_source || '-'));
        }
        if (dataAlerts.length > 3) {
            parts.push('+' + (dataAlerts.length - 3) + ' daha');
        }

        if (parts.length === 0) return '<span style="color:#888;">-</span>';
        return parts.join(', ');
    }

    // ============================
    // SERVER FILTER POPULATION
    // ============================
    function populateServerFilter(alerts) {
        var select = _el('ppdServerFilter');
        if (!select) return;

        var current = select.value;
        var servers = {};
        for (var i = 0; i < alerts.length; i++) {
            var s = alerts[i].server_name;
            if (s) servers[s] = true;
        }

        var sorted = Object.keys(servers).sort();
        // Only update if there are new entries
        if (sorted.length === 0) return;

        var html = '<option value="">Tum Sunucular</option>';
        for (var j = 0; j < sorted.length; j++) {
            var sel = sorted[j] === current ? ' selected' : '';
            html += '<option value="' + esc(sorted[j]) + '"' + sel + '>' + esc(sorted[j]) + '</option>';
        }
        select.innerHTML = html;
    }

    // ============================
    // TIME-SERIES CHART
    // ============================
    var _chartInstance = null;

    function loadTimeseries(server, days) {
        var extra = 'days=' + encodeURIComponent(days);
        if (server) extra += '&server_name=' + encodeURIComponent(server);
        var st = _getSourceType();
        if (st) extra += '&source_type=' + encodeURIComponent(st);
        var url = _apiUrl('predictionTimeseries', extra);
        if (!url) return;

        fetch(url)
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.status !== 'success' || !data.timeseries) return;
                renderTimeseries(data.timeseries);
            })
            .catch(function (err) {
                console.warn('[PredictionDashboard] Timeseries fetch error:', err);
            });
    }

    function renderTimeseries(ts) {
        var canvas = _el('ppsTimeseriesCanvas');
        var emptyEl = _el('ppsChartEmpty');
        if (!canvas) return;

        var labels = ts.labels || [];
        var ds = ts.datasets || {};

        // Show empty state if no data
        if (labels.length === 0) {
            canvas.style.display = 'none';
            if (emptyEl) emptyEl.style.display = 'block';
            if (_chartInstance) { _chartInstance.destroy(); _chartInstance = null; }
            return;
        }
        canvas.style.display = 'block';
        if (emptyEl) emptyEl.style.display = 'none';

        // Format labels for display
        var bucketType = ts.bucket_type || 'daily';
        var displayLabels = labels.map(function (lbl) {
            if (bucketType === 'hourly') {
                // "2026-02-27T14:00" → "27 Feb 14:00"
                var parts = lbl.split('T');
                var datePart = parts[0].split('-');
                var months = ['Oca','Sub','Mar','Nis','May','Haz','Tem','Agu','Eyl','Eki','Kas','Ara'];
                return datePart[2] + ' ' + months[parseInt(datePart[1], 10) - 1] + ' ' + (parts[1] || '');
            }
            // "2026-02-27" → "27 Sub"
            var d = lbl.split('-');
            var m = ['Oca','Sub','Mar','Nis','May','Haz','Tem','Agu','Eyl','Eki','Kas','Ara'];
            return d[2] + ' ' + m[parseInt(d[1], 10) - 1];
        });

        // Destroy previous chart
        if (_chartInstance) { _chartInstance.destroy(); _chartInstance = null; }

        // Check for Chart.js
        if (typeof Chart === 'undefined') {
            console.warn('[PredictionDashboard] Chart.js not loaded');
            return;
        }

        var ctx = canvas.getContext('2d');
        _chartInstance = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: displayLabels,
                datasets: [
                    {
                        label: 'Toplam Kontrol',
                        data: ds.total_checks || [],
                        backgroundColor: 'rgba(63, 81, 181, 0.18)',
                        borderColor: 'rgba(63, 81, 181, 0.7)',
                        borderWidth: 1.5,
                        borderRadius: 4,
                        order: 3
                    },
                    {
                        label: 'Trend Alert',
                        data: ds.trend_alerts || [],
                        backgroundColor: 'rgba(255, 152, 0, 0.65)',
                        borderColor: 'rgba(255, 152, 0, 1)',
                        borderWidth: 1.5,
                        borderRadius: 4,
                        order: 2
                    },
                    {
                        label: 'Rate Alert',
                        data: ds.rate_alerts || [],
                        backgroundColor: 'rgba(244, 67, 54, 0.65)',
                        borderColor: 'rgba(244, 67, 54, 1)',
                        borderWidth: 1.5,
                        borderRadius: 4,
                        order: 1
                    },
                    {
                        label: 'Forecast Alert',
                        data: ds.forecast_alerts || [],
                        backgroundColor: 'rgba(76, 175, 80, 0.65)',
                        borderColor: 'rgba(76, 175, 80, 1)',
                        borderWidth: 1.5,
                        borderRadius: 4,
                        order: 0
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    mode: 'index',
                    intersect: false
                },
                plugins: {
                    legend: {
                        position: 'top',
                        labels: {
                            boxWidth: 14,
                            padding: 12,
                            font: { size: 12 }
                        }
                    },
                    tooltip: {
                        backgroundColor: 'rgba(26, 35, 126, 0.9)',
                        titleFont: { size: 13 },
                        bodyFont: { size: 12 },
                        padding: 10,
                        cornerRadius: 6
                    }
                },
                scales: {
                    x: {
                        grid: { display: false },
                        ticks: { font: { size: 11 }, maxRotation: 45, minRotation: 0 }
                    },
                    y: {
                        beginAtZero: true,
                        ticks: { font: { size: 11 }, precision: 0 },
                        grid: { color: 'rgba(0,0,0,0.06)' }
                    }
                }
            }
        });
    }

    // ============================
    // SCHEDULER STATUS
    // ============================
    var _schedBusy = false;  // prevent double-click on scheduler actions

    function loadSchedulerStatus() {
        var url = _apiUrl('schedulerStatus');
        if (!url) return;

        fetch(url)
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.status !== 'success') return;
                renderSchedulerStatus(data.scheduler || {});
            })
            .catch(function (err) {
                console.warn('[PredictionDashboard] Scheduler status error:', err);
                var grid = _el('ppdSchedGrid');
                if (grid) grid.innerHTML = '<div class="ppd-error">Scheduler durumu alinamadi</div>';
            });
    }

    function renderSchedulerStatus(sched) {
        var grid = _el('ppdSchedGrid');
        if (!grid) return;

        var enabled = !!sched.enabled;
        var running = !!sched.running;
        var interval = sched.interval_minutes || '-';
        var runCount = sched.run_count || 0;
        var lastRun = sched.last_run || null;

        // Format last run time
        var lastRunStr = '-';
        if (lastRun) {
            lastRunStr = String(lastRun);
            if (lastRunStr.length > 19) lastRunStr = lastRunStr.substring(0, 19).replace('T', ' ');
        }

        // Status label
        var statusLabel, statusClass;
        if (!enabled) { statusLabel = 'DEVRE DISI'; statusClass = 'ppd-sched-status-disabled'; }
        else if (running) { statusLabel = 'CALISIYOR'; statusClass = 'ppd-sched-status-running'; }
        else { statusLabel = 'DURDU'; statusClass = 'ppd-sched-status-stopped'; }

        var stats = [
            { label: 'Durum', value: statusLabel, cls: statusClass },
            { label: 'Aralik', value: interval + ' dk', cls: '' },
            { label: 'Calisma Sayisi', value: String(runCount), cls: '' },
            { label: 'Son Calisma', value: lastRunStr, cls: '' }
        ];

        var html = '';
        for (var i = 0; i < stats.length; i++) {
            var s = stats[i];
            html += '<div class="ppd-sched-stat">'
                + '<div class="ppd-sched-stat-label">' + esc(s.label) + '</div>'
                + '<div class="ppd-sched-stat-value ' + s.cls + '">' + esc(s.value) + '</div>'
                + '</div>';
        }
        // Disabled hint
        if (!enabled) {
            html += '<div class="pps-sched-hint">'
                + 'Scheduler devre disi. Etkinlestirmek icin '
                + '<code>anomaly_config.json &gt; prediction &gt; scheduler &gt; enabled: true</code> '
                + 'yapilandiriniz.'
                + '</div>';
        }

        grid.innerHTML = html;

        // Update button states
        var startBtn = _el('ppdSchedStartBtn');
        var stopBtn = _el('ppdSchedStopBtn');
        var triggerBtn = _el('ppdSchedTriggerBtn');
        if (startBtn) startBtn.disabled = !enabled || running || _schedBusy;
        if (stopBtn) stopBtn.disabled = !running || _schedBusy;
        // Trigger is independent of scheduler enabled state — trigger_now works standalone
        if (triggerBtn) triggerBtn.disabled = _schedBusy;

        // Render target hosts as interactive checkboxes in sidebar
        var hosts = sched.target_hosts || [];
        _renderHostCheckboxes(hosts);
    }

    // ============================
    // HOST CHECKBOX LIST
    // ============================
    function _renderHostCheckboxes(hosts) {
        var container = _el('ppsHostsList');
        if (!container) return;

        if (hosts.length === 0) {
            container.innerHTML = '<span class="pps-hosts-empty">Hedef sunucu bulunamadi</span>';
            return;
        }

        var html = '';
        for (var i = 0; i < hosts.length; i++) {
            var id = 'ppsHost_' + i;
            html += '<label class="pps-host-item pps-host-checked" for="' + id + '">'
                + '<input type="checkbox" id="' + id + '" value="' + esc(hosts[i]) + '" checked>'
                + '<span class="pps-host-item-label">' + esc(hosts[i]) + '</span>'
                + '</label>';
        }
        container.innerHTML = html;

        // Toggle checked visual
        container.querySelectorAll('input[type="checkbox"]').forEach(function (cb) {
            cb.addEventListener('change', function () {
                var label = cb.closest('.pps-host-item');
                if (label) {
                    if (cb.checked) label.classList.add('pps-host-checked');
                    else label.classList.remove('pps-host-checked');
                }
            });
        });
    }

    function _getSelectedHosts() {
        var container = _el('ppsHostsList');
        if (!container) return [];
        var checked = container.querySelectorAll('input[type="checkbox"]:checked');
        var result = [];
        for (var i = 0; i < checked.length; i++) {
            result.push(checked[i].value);
        }
        return result;
    }

    function _initHostSelectAll() {
        var btn = _el('ppsHostsSelectAll');
        if (!btn) return;
        var allSelected = true;
        btn.addEventListener('click', function () {
            allSelected = !allSelected;
            var container = _el('ppsHostsList');
            if (!container) return;
            btn.textContent = allSelected ? 'Tumu Sec' : 'Temizle';
            container.querySelectorAll('input[type="checkbox"]').forEach(function (cb) {
                cb.checked = allSelected;
                var label = cb.closest('.pps-host-item');
                if (label) {
                    if (allSelected) label.classList.add('pps-host-checked');
                    else label.classList.remove('pps-host-checked');
                }
            });
        });
    }

    // ============================
    // SCHEDULER ACTIONS (with confirmation)
    // ============================
    function _showConfirm(title, message, onYes) {
        // Remove any existing confirm overlay
        _hideConfirm();

        var overlay = document.createElement('div');
        overlay.className = 'ppd-sched-confirm-overlay';
        overlay.id = 'ppdSchedConfirmOverlay';

        overlay.innerHTML = '<div class="ppd-sched-confirm-box">'
            + '<h4>' + esc(title) + '</h4>'
            + '<p>' + esc(message) + '</p>'
            + '<div class="ppd-sched-confirm-actions">'
            + '<button type="button" class="ppd-sched-confirm-yes" id="ppdConfirmYes">Evet</button>'
            + '<button type="button" class="ppd-sched-confirm-no" id="ppdConfirmNo">Iptal</button>'
            + '</div></div>';

        document.body.appendChild(overlay);

        // Event listeners
        document.getElementById('ppdConfirmYes').addEventListener('click', function () {
            _hideConfirm();
            onYes();
        });
        document.getElementById('ppdConfirmNo').addEventListener('click', function () {
            _hideConfirm();
        });
        // Click outside to cancel
        overlay.addEventListener('click', function (e) {
            if (e.target === overlay) _hideConfirm();
        });
    }

    function _hideConfirm() {
        var existing = document.getElementById('ppdSchedConfirmOverlay');
        if (existing) existing.parentNode.removeChild(existing);
    }

    function _postScheduler(endpointKey, body, successMsg) {
        var base = window.API_ENDPOINTS ? window.API_ENDPOINTS[endpointKey] : null;
        if (!base) return;

        _schedBusy = true;
        _updateSchedButtons();

        fetch(base, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            _schedBusy = false;
            if (data.scheduler) {
                renderSchedulerStatus(data.scheduler);
            }
            console.log('[PredictionDashboard] ' + successMsg, data);
            loadSchedulerStatus(); // refresh scheduler status
            // After trigger/start, refresh all prediction data (new results may be available)
            if (endpointKey === 'schedulerTrigger' || endpointKey === 'schedulerStart') {
                setTimeout(function () { refreshAll(); }, 1500);
            }
        })
        .catch(function (err) {
            _schedBusy = false;
            _updateSchedButtons();
            console.error('[PredictionDashboard] Scheduler action error:', err);
        });
    }

    function _updateSchedButtons() {
        var startBtn = _el('ppdSchedStartBtn');
        var stopBtn = _el('ppdSchedStopBtn');
        var triggerBtn = _el('ppdSchedTriggerBtn');
        if (startBtn) startBtn.disabled = _schedBusy;
        if (stopBtn) stopBtn.disabled = _schedBusy;
        if (triggerBtn) triggerBtn.disabled = _schedBusy;
    }

    function startScheduler() {
        _showConfirm(
            'Scheduler Baslat',
            'Periyodik anomaly analizi baslatilacak. Devam etmek istiyor musunuz?',
            function () {
                var body = { api_key: window.apiKey || '' };
                var selectedHosts = _getSelectedHosts();
                if (selectedHosts.length > 0) body.target_hosts = selectedHosts;
                _postScheduler('schedulerStart', body, 'Scheduler started');
            }
        );
    }

    function stopScheduler() {
        _showConfirm(
            'Scheduler Durdur',
            'Periyodik analiz durdurulacak. Devam etmek istiyor musunuz?',
            function () {
                _postScheduler('schedulerStop',
                    { api_key: window.apiKey || '' },
                    'Scheduler stopped');
            }
        );
    }

    function triggerScheduler() {
        var serverVal = (_el('ppdServerFilter') || {}).value || '';
        var msg = serverVal
            ? 'Manuel analiz "' + serverVal + '" icin tetiklenecek. Devam?'
            : 'Manuel analiz tum sunucular icin tetiklenecek. Devam?';

        _showConfirm('Manuel Calistir', msg, function () {
            var body = { api_key: window.apiKey || '' };
            if (serverVal) body.server_name = serverVal;
            _postScheduler('schedulerTrigger', body, 'Scheduler triggered');
        });
    }

    // ============================
    // INITIALIZATION
    // ============================
    function initPredictionDashboard() {
        // Quick-action button → opens modal
        var btn = _el('predictionDashboardBtn');
        if (btn) {
            btn.addEventListener('click', toggleDashboard);
        }

        // Close button inside modal header
        var closeBtn = _el('ppsCloseBtn');
        if (closeBtn) {
            closeBtn.addEventListener('click', hideDashboard);
        }

        // Backdrop click → close modal
        var overlay = _getOverlay();
        if (overlay) {
            overlay.addEventListener('click', function (e) {
                if (e.target === overlay) hideDashboard();
            });
        }

        // ESC key → close modal
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && _visible) {
                hideDashboard();
            }
        });

        // Refresh button
        var refreshBtn = _el('ppdRefreshBtn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', function () {
                refreshAll();
            });
        }

        // Filter change handlers
        var serverFilter = _el('ppdServerFilter');
        if (serverFilter) {
            serverFilter.addEventListener('change', function () {
                refreshAll();
            });
        }

        var daysFilter = _el('ppdDaysFilter');
        if (daysFilter) {
            daysFilter.addEventListener('change', function () {
                refreshAll();
            });
        }

        // Scheduler buttons
        var schedStartBtn = _el('ppdSchedStartBtn');
        if (schedStartBtn) {
            schedStartBtn.addEventListener('click', function () { startScheduler(); });
        }
        var schedStopBtn = _el('ppdSchedStopBtn');
        if (schedStopBtn) {
            schedStopBtn.addEventListener('click', function () { stopScheduler(); });
        }
        var schedTriggerBtn = _el('ppdSchedTriggerBtn');
        if (schedTriggerBtn) {
            schedTriggerBtn.addEventListener('click', function () { triggerScheduler(); });
        }

        // Source toggle + host select all
        _initSourceToggle();
        _initHostSelectAll();

        // Overlay starts hidden (via inline style="display:none")
        console.log('Prediction Studio initialized (modal overlay mode)');
    }

    // Auto-init when DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initPredictionDashboard);
    } else {
        initPredictionDashboard();
    }

    // ============================
    // PUBLIC API
    // ============================
    window.PredictionDashboard = {
        toggle: toggleDashboard,
        show: showDashboard,
        hide: hideDashboard,
        refresh: refreshAll,
        loadConfig: loadConfig,
        loadSummary: loadSummary,
        loadAlerts: loadAlerts,
        loadTimeseries: loadTimeseries,
        loadSchedulerStatus: loadSchedulerStatus,
        startScheduler: startScheduler,
        stopScheduler: stopScheduler,
        triggerScheduler: triggerScheduler
    };

    // Backward compat globals
    window.togglePredictionDashboard = toggleDashboard;

    console.log('Prediction Dashboard module loaded successfully');

})();
