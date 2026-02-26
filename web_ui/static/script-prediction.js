// web_ui/static/script-prediction.js
/**
 * LC Waikiki MongoDB Assistant - Prediction Dashboard Module
 *
 * Standalone dashboard that fetches prediction data via API:
 *   - /api/prediction/alerts   → alert history table
 *   - /api/prediction/summary  → summary cards
 *   - /api/prediction/config   → config pills & badge
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
    // TOGGLE VISIBILITY
    // ============================
    function toggleDashboard() {
        var section = _el('predictionDashboardSection');
        if (!section) return;
        _visible = !_visible;
        section.style.display = _visible ? 'block' : 'none';
        if (_visible) refreshAll();
    }

    function showDashboard() {
        var section = _el('predictionDashboardSection');
        if (!section) return;
        _visible = true;
        section.style.display = 'block';
        refreshAll();
    }

    function hideDashboard() {
        var section = _el('predictionDashboardSection');
        if (!section) return;
        _visible = false;
        section.style.display = 'none';
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
        for (var i = 0; i < pills.length; i++) {
            var p = pills[i];
            html += '<span class="ppd-config-pill ' + (p.on ? 'ppd-pill-on' : 'ppd-pill-off') + '">'
                + esc(p.label) + ': ' + (p.on ? 'ON' : 'OFF') + '</span>';
        }
        grid.innerHTML = html;
    }

    // ============================
    // LOAD SUMMARY
    // ============================
    function loadSummary(server, days) {
        var extra = 'days=' + encodeURIComponent(days);
        if (server) extra += '&server_name=' + encodeURIComponent(server);
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

        var cards = [
            { title: 'Toplam Kontrol', value: totalChecks, sub: 'Son ' + periodDays + ' gun', cls: '' },
            { title: 'Toplam Uyari', value: totalAlerts, sub: 'Alert orani: %' + alertRate, cls: totalAlerts > 0 ? 'ppd-card-warn' : '' },
            { title: 'Trend Alerts', value: trendAlerts + ' / ' + trendTotal, sub: 'Trend analiz', cls: trendAlerts > 0 ? 'ppd-card-warn' : '' },
            { title: 'Rate Alerts', value: rateAlerts + ' / ' + rateTotal, sub: 'Rate alerting', cls: rateAlerts > 0 ? 'ppd-card-warn' : '' },
            { title: 'Forecast Alerts', value: forecastAlerts + ' / ' + forecastTotal, sub: 'Tahmin modeli', cls: forecastAlerts > 0 ? 'ppd-card-warn' : '' }
        ];

        var html = '';
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
                    if (wrapper) wrapper.style.display = 'none';
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

            // Count alerts from embedded data
            if (a.trend_alerts && Array.isArray(a.trend_alerts)) alertCount += a.trend_alerts.length;
            if (a.rate_alerts && Array.isArray(a.rate_alerts)) alertCount += a.rate_alerts.length;
            if (a.forecast_alerts && Array.isArray(a.forecast_alerts)) alertCount += a.forecast_alerts.length;
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

        // Trend alerts
        if (alertDoc.trend_alerts && alertDoc.trend_alerts.length > 0) {
            for (var i = 0; i < Math.min(alertDoc.trend_alerts.length, 2); i++) {
                parts.push(esc(alertDoc.trend_alerts[i].title || alertDoc.trend_alerts[i].alert_type || 'trend'));
            }
        }
        // Rate alerts
        if (alertDoc.rate_alerts && alertDoc.rate_alerts.length > 0) {
            for (var j = 0; j < Math.min(alertDoc.rate_alerts.length, 2); j++) {
                parts.push(esc(alertDoc.rate_alerts[j].title || alertDoc.rate_alerts[j].alert_type || 'rate'));
            }
        }
        // Forecast alerts
        if (alertDoc.forecast_alerts && alertDoc.forecast_alerts.length > 0) {
            for (var k = 0; k < Math.min(alertDoc.forecast_alerts.length, 2); k++) {
                parts.push(esc(alertDoc.forecast_alerts[k].title || alertDoc.forecast_alerts[k].alert_type || 'forecast'));
            }
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
    // INITIALIZATION
    // ============================
    function initPredictionDashboard() {
        // Quick-action button
        var btn = _el('predictionDashboardBtn');
        if (btn) {
            btn.addEventListener('click', toggleDashboard);
        }

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

        // Start hidden
        var section = _el('predictionDashboardSection');
        if (section) section.style.display = 'none';

        console.log('✅ Prediction Dashboard initialized');
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
        loadAlerts: loadAlerts
    };

    // Backward compat globals
    window.togglePredictionDashboard = toggleDashboard;

    console.log('Prediction Dashboard module loaded successfully');

})();
