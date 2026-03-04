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
        loadServerOverview(daysVal);
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
    // SERVER RISK OVERVIEW
    // ============================
    function loadServerOverview(days) {
        var extra = 'days=' + encodeURIComponent(days);
        var st = _getSourceType();
        if (st) extra += '&source_type=' + encodeURIComponent(st);
        var url = _apiUrl('predictionServerOverview', extra);
        if (!url) return;

        var grid = _el('ppdServerGrid');
        if (!grid) return;
        grid.innerHTML = '<div class="ppd-loading"><div class="ppd-loading-spinner"></div><br>Yukleniyor...</div>';

        fetch(url)
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.status !== 'success' || !data.servers || data.servers.length === 0) {
                    grid.innerHTML = '<div class="ppd-server-empty">Sunucu verisi bulunamadi. Analiz calistirildiginda sunucu risk durumu burada gorunecek.</div>';
                    return;
                }
                renderServerOverview(data.servers);
            })
            .catch(function (err) {
                console.warn('[PredictionDashboard] Server overview fetch error:', err);
                grid.innerHTML = '';
            });
    }

    function renderServerOverview(servers) {
        var grid = _el('ppdServerGrid');
        if (!grid) return;

        var html = '';
        for (var i = 0; i < servers.length; i++) {
            var s = servers[i];
            var riskClass = 'ppd-risk-' + (s.risk_level || 'ok').toLowerCase();
            var riskLabel = s.risk_level || 'OK';
            var alertRate = s.alert_rate_pct || 0;
            var lastCheck = s.last_check || '';
            if (lastCheck && lastCheck.length > 16) lastCheck = lastCheck.substring(0, 16).replace('T', ' ');

            // Risk indicator icon
            var riskIcon = '&#x2705;'; // OK
            if (riskLabel === 'CRITICAL') riskIcon = '&#x1F534;';
            else if (riskLabel === 'WARNING') riskIcon = '&#x1F7E0;';
            else if (riskLabel === 'INFO') riskIcon = '&#x1F535;';

            // Alert breakdown mini-bar
            var trendW = 0, rateW = 0, forecastW = 0;
            var totalA = s.total_alerts || 0;
            if (totalA > 0) {
                trendW = Math.round((s.trend_alerts / totalA) * 100);
                rateW = Math.round((s.rate_alerts / totalA) * 100);
                forecastW = 100 - trendW - rateW;
                if (forecastW < 0) forecastW = 0;
            }

            html += '<div class="ppd-server-card ' + riskClass + '" data-server="' + esc(s.server_name) + '">'
                + '<div class="ppd-server-header">'
                +   '<span class="ppd-server-risk-icon">' + riskIcon + '</span>'
                +   '<span class="ppd-server-name">' + esc(s.server_name) + '</span>'
                +   '<span class="ppd-server-risk-badge ' + riskClass + '">' + esc(riskLabel) + '</span>'
                + '</div>'
                + '<div class="ppd-server-stats">'
                +   '<div class="ppd-server-stat">'
                +     '<span class="ppd-stat-label">Kontrol</span>'
                +     '<span class="ppd-stat-value">' + s.total_checks + '</span>'
                +   '</div>'
                +   '<div class="ppd-server-stat">'
                +     '<span class="ppd-stat-label">Uyari</span>'
                +     '<span class="ppd-stat-value ppd-stat-alert">' + s.total_alerts + '</span>'
                +   '</div>'
                +   '<div class="ppd-server-stat">'
                +     '<span class="ppd-stat-label">Alert %</span>'
                +     '<span class="ppd-stat-value">' + alertRate.toFixed(1) + '%</span>'
                +   '</div>'
                +   '<div class="ppd-server-stat">'
                +     '<span class="ppd-stat-label">CRIT/WARN</span>'
                +     '<span class="ppd-stat-value">' + (s.critical_count || 0) + '/' + (s.warning_count || 0) + '</span>'
                +   '</div>'
                + '</div>';

            // Alert type breakdown bar
            if (totalA > 0) {
                html += '<div class="ppd-server-breakdown">'
                    + '<div class="ppd-breakdown-bar">'
                    +   '<div class="ppd-bar-trend" style="width:' + trendW + '%" title="Trend: ' + s.trend_alerts + '"></div>'
                    +   '<div class="ppd-bar-rate" style="width:' + rateW + '%" title="Rate: ' + s.rate_alerts + '"></div>'
                    +   '<div class="ppd-bar-forecast" style="width:' + forecastW + '%" title="Forecast: ' + s.forecast_alerts + '"></div>'
                    + '</div>'
                    + '<div class="ppd-breakdown-legend">'
                    +   '<span class="ppd-legend-item"><span class="ppd-legend-dot ppd-dot-trend"></span>Trend ' + s.trend_alerts + '</span>'
                    +   '<span class="ppd-legend-item"><span class="ppd-legend-dot ppd-dot-rate"></span>Rate ' + s.rate_alerts + '</span>'
                    +   '<span class="ppd-legend-item"><span class="ppd-legend-dot ppd-dot-forecast"></span>Forecast ' + s.forecast_alerts + '</span>'
                    + '</div>'
                    + '</div>';
            }

            html += '<div class="ppd-server-footer">'
                + '<span class="ppd-server-lastcheck">Son: ' + esc(lastCheck || '-') + '</span>'
                + '</div>'
                + '</div>';
        }
        grid.innerHTML = html;

        // Click handler: server card'a tıklayınca o sunucuyu filtrele
        grid.querySelectorAll('.ppd-server-card').forEach(function (card) {
            card.addEventListener('click', function () {
                var serverName = card.getAttribute('data-server');
                var filterEl = _el('ppdServerFilter');
                if (filterEl && serverName) {
                    // Eğer option yoksa ekle
                    var optionExists = false;
                    for (var j = 0; j < filterEl.options.length; j++) {
                        if (filterEl.options[j].value === serverName) {
                            optionExists = true;
                            break;
                        }
                    }
                    if (!optionExists) {
                        var opt = document.createElement('option');
                        opt.value = serverName;
                        opt.textContent = serverName;
                        filterEl.appendChild(opt);
                    }
                    filterEl.value = serverName;
                    refreshAll();
                }
            });
        });
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
                            emptyTbody.innerHTML = '<tr><td colspan="7" class="pps-table-empty">'
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

            // Confidence cell
            var confidenceHtml = _buildConfidenceCell(dataAlerts);

            // Build detail snippet
            var detail = _buildDetailSnippet(a);

            html += '<tr class="ppd-alert-row" data-row-idx="' + i + '">'
                + '<td>' + esc(ts) + '</td>'
                + '<td>' + esc(source) + '</td>'
                + '<td>' + esc(server) + '</td>'
                + '<td><span class="ppd-severity-tag ' + sevClass + '">' + esc(severity) + '</span></td>'
                + '<td>' + confidenceHtml + '</td>'
                + '<td>' + esc(String(alertCount)) + '</td>'
                + '<td class="ppd-detail-cell">' + detail + '</td>'
                + '</tr>';

            // Drill-down row (hidden by default)
            html += '<tr class="ppd-drilldown-row" id="ppdDrill_' + i + '" style="display:none;">'
                + '<td colspan="7" class="ppd-drilldown-cell">'
                + _buildDrillDownPanel(a, dataAlerts)
                + '</td></tr>';
        }
        tbody.innerHTML = html;
        wrapper.style.display = 'block';

        // Attach drill-down click handlers
        _initRowDrillDown();
    }

    function _buildDetailSnippet(alertDoc) {
        var parts = [];

        // Backend stores all alerts in data.alerts (source-specific via alert_source field)
        var dataAlerts = (alertDoc.data && Array.isArray(alertDoc.data.alerts))
            ? alertDoc.data.alerts : [];

        for (var i = 0; i < Math.min(dataAlerts.length, 3); i++) {
            var al = dataAlerts[i];
            var label = esc(al.title || al.alert_type || alertDoc.alert_source || '-');

            // ML corroboration badge for rate alerts
            if (al.ml_context && al.ml_context.ml_corroborated) {
                label += ' <span class="ppd-ml-badge ppd-ml-confirmed" title="ML modeli bu spike\'i destekliyor">ML &#x2713;</span>';
            } else if (al.ml_context && !al.ml_context.ml_corroborated) {
                label += ' <span class="ppd-ml-badge ppd-ml-weak" title="ML destegi zayif">ML ?</span>';
            }

            // ML risk level badge for forecast alerts
            if (al.ml_risk_context) {
                var mlLvl = al.ml_risk_context.ml_risk_level;
                if (mlLvl && mlLvl !== 'OK') {
                    var mlCls = 'ppd-ml-risk-' + mlLvl.toLowerCase();
                    label += ' <span class="ppd-ml-risk ' + mlCls + '" title="ML Risk: ' + mlLvl + '">ML ' + mlLvl + '</span>';
                }
            }
            parts.push(label);
        }
        if (dataAlerts.length > 3) {
            parts.push('+' + (dataAlerts.length - 3) + ' daha');
        }

        if (parts.length === 0) return '<span style="color:#888;">Uyari yok — detay icin tiklayin</span>';
        return parts.join(', ');
    }

    // ============================
    // CONFIDENCE CELL
    // ============================
    function _buildConfidenceCell(dataAlerts) {
        var maxConf = 0;
        var hasConf = false;
        for (var i = 0; i < dataAlerts.length; i++) {
            var c = dataAlerts[i].confidence;
            if (typeof c === 'number') {
                hasConf = true;
                if (c > maxConf) maxConf = c;
            }
        }
        if (!hasConf) return '<span class="ppd-conf-na">-</span>';

        var pct = Math.round(maxConf * 100);
        var cls = 'ppd-conf-low';
        if (pct >= 60) cls = 'ppd-conf-high';
        else if (pct >= 30) cls = 'ppd-conf-med';

        return '<span class="ppd-conf-badge ' + cls + '" title="Maks. guven: %' + pct + '">%' + pct + '</span>';
    }

    // ============================
    // TIER LABEL HELPER
    // ============================
    function _tierLabel(method) {
        var labels = {
            'tier0_no_data': 'Veri Yetersiz',
            'tier0_single_point': 'Tek Nokta',
            'tier0_direction_only': 'Tier 0',
            'tier1_wma': 'Tier 1 — WMA',
            'tier2_linear_regression': 'Tier 2 — LR',
            'tier3_ewma_decomposition': 'Tier 3 — EWMA'
        };
        return labels[method] || method;
    }

    // ============================
    // DRILL-DOWN PANEL
    // ============================
    function _buildDrillDownPanel(alertDoc, dataAlerts) {
        if (dataAlerts.length === 0) {
            // Contextual message based on source
            var src = alertDoc.alert_source || '';
            var msg = 'Bu kontrol sirasinda uyari tespit edilmedi.';
            var extraHtml = '';
            if (src === 'forecast') {
                var forecasts = (alertDoc.data && alertDoc.data.forecasts) || {};
                var insuffCount = 0;
                var maxDp = 0;
                var metricSummaries = [];
                var fKeys = Object.keys(forecasts);
                for (var k = 0; k < fKeys.length; k++) {
                    var fKey = fKeys[k];
                    var fc = forecasts[fKey];
                    if (!fc || typeof fc !== 'object') continue;
                    if (fc.status === 'insufficient_data') {
                        insuffCount++;
                        if (fc.data_points > maxDp) maxDp = fc.data_points;
                        metricSummaries.push({
                            name: fc.label || fKey,
                            status: 'Yetersiz veri (' + (fc.data_points || 0) + '/' + (fc.min_required || 2) + ')',
                            cls: 'ppd-metric-insuff'
                        });
                    } else if (fc.direction) {
                        var dirIcon = fc.direction === 'rising' ? '&#x2197;' :
                                      fc.direction === 'falling' ? '&#x2198;' : '&#x2192;';
                        var confPct = typeof fc.confidence === 'number' ? Math.round(fc.confidence * 100) + '%' : '-';
                        var statConf = typeof fc.statistical_confidence === 'number' ? Math.round(fc.statistical_confidence * 100) + '%' : '';
                        var confLabel = confPct;
                        if (statConf && statConf !== confPct) {
                            confLabel = confPct + ' (istat: ' + statConf + ')';
                        }
                        metricSummaries.push({
                            name: fc.label || fKey,
                            status: dirIcon + ' ' + fc.direction + ' | Guven: ' + confLabel
                                + (fc.current_value != null ? ' | Guncel: ' + parseFloat(fc.current_value).toFixed(2) : '')
                                + (fc.forecast_value != null ? ' → Tahmin: ' + parseFloat(fc.forecast_value).toFixed(2) : ''),
                            cls: fc.direction === 'rising' ? 'ppd-metric-rising' :
                                 fc.direction === 'falling' ? 'ppd-metric-falling' : 'ppd-metric-stable'
                        });
                    }
                }
                if (insuffCount > 0) {
                    msg = insuffCount + ' metrik icin yeterli veri yok (maks. ' + maxDp + ' nokta). '
                        + 'Daha fazla analiz calistirarak tahmin dogrulugunu artirabilirsiniz.';
                } else {
                    msg = 'Tahmin modeli risk artisi tespit etmedi. Tum metrikler normal seyrediyor.';
                }
                // Build metric detail table
                if (metricSummaries.length > 0) {
                    extraHtml = '<div class="ppd-forecast-metrics" style="margin-top:8px;">';
                    for (var m = 0; m < metricSummaries.length; m++) {
                        var ms = metricSummaries[m];
                        extraHtml += '<div class="ppd-metric-row ' + ms.cls + '">'
                            + '<span class="ppd-metric-name">' + esc(ms.name) + '</span>'
                            + '<span class="ppd-metric-status">' + ms.status + '</span>'
                            + '</div>';
                    }
                    extraHtml += '</div>';
                }
            } else if (src === 'trend') {
                // Show trend summary if available
                var trendSummary = (alertDoc.data && alertDoc.data.summary) || {};
                msg = 'Trend analizi anomali degisimi tespit etmedi. Mevcut seyir stabil.';
                if (trendSummary.ml_score_trend) {
                    var mst = trendSummary.ml_score_trend;
                    var scoreParts = [];
                    if (typeof mst.current_mean_score === 'number') {
                        scoreParts.push('ML Skor: ' + mst.current_mean_score.toFixed(4));
                    }
                    if (mst.ml_score_direction) {
                        var dirMap = {worsening: 'Kotulesme', improving: 'Iyilesme', stable: 'Stabil'};
                        scoreParts.push('Yonelim: ' + (dirMap[mst.ml_score_direction] || mst.ml_score_direction));
                    }
                    if (typeof mst.severity_critical_high_pct === 'number') {
                        scoreParts.push('CRIT+HIGH: %' + mst.severity_critical_high_pct.toFixed(1));
                    }
                    if (scoreParts.length > 0) {
                        extraHtml = '<div style="margin-top:6px;font-size:0.82em;color:#666;">' + esc(scoreParts.join(' | ')) + '</div>';
                    }
                }
            } else if (src === 'rate') {
                msg = 'Rate alert modulu esik asimi tespit etmedi. Anomali oranlari normal araliklarda.';
            }
            return '<div class="ppd-drill-empty">' + esc(msg) + extraHtml + '</div>';
        }

        var html = '<div class="ppd-drill-panel">';

        for (var i = 0; i < dataAlerts.length; i++) {
            var al = dataAlerts[i];
            var sevClass = 'ppd-sev-' + (al.severity || 'info').toLowerCase();

            html += '<div class="ppd-drill-alert">';

            // Header row: severity + title + badges
            html += '<div class="ppd-drill-header">'
                + '<span class="ppd-severity-tag ' + sevClass + '">' + esc(al.severity || 'INFO') + '</span>'
                + '<span class="ppd-drill-title">' + esc(al.title || al.alert_type || '-') + '</span>';

            // Confidence badge
            if (typeof al.confidence === 'number') {
                var pct = Math.round(al.confidence * 100);
                var confCls = pct >= 60 ? 'ppd-conf-high' : (pct >= 30 ? 'ppd-conf-med' : 'ppd-conf-low');
                html += '<span class="ppd-conf-badge ' + confCls + '">%' + pct + '</span>';
            }

            // ML corroboration badge
            if (al.ml_context) {
                if (al.ml_context.ml_corroborated) {
                    html += '<span class="ppd-ml-badge ppd-ml-confirmed" title="ML destekli">ML &#x2713;</span>';
                } else {
                    html += '<span class="ppd-ml-badge ppd-ml-weak" title="ML destegi zayif">ML ?</span>';
                }
            }

            // Forecast method badge
            if (al.forecast_method) {
                html += '<span class="ppd-method-badge">' + esc(_tierLabel(al.forecast_method)) + '</span>';
            }

            html += '</div>'; // end header

            // Description
            if (al.description) {
                html += '<div class="ppd-drill-desc">' + esc(al.description) + '</div>';
            }

            // Forecast bounds
            if (typeof al.forecast_value === 'number') {
                var lb = typeof al.lower_bound === 'number' ? al.lower_bound.toFixed(2) : '?';
                var ub = typeof al.upper_bound === 'number' ? al.upper_bound.toFixed(2) : '?';
                html += '<div class="ppd-drill-forecast">'
                    + 'Tahmin: ' + al.forecast_value.toFixed(2)
                    + ' [' + lb + ' \u2013 ' + ub + ']'
                    + '</div>';
            }

            // ML context detail for rate alerts (enriched with severity-weighted data)
            if (al.ml_context && typeof al.ml_context === 'object') {
                var ctx = al.ml_context;
                html += '<div class="ppd-drill-ml-ctx">';
                var ctxParts = [];
                // Corroboration status
                if (ctx.ml_strong_corroboration) {
                    ctxParts.push('<strong style="color:#2e7d32;">ML Guclu Destek</strong>');
                } else if (ctx.ml_corroborated) {
                    ctxParts.push('<span style="color:#ff9800;">ML Destekli</span>');
                } else {
                    ctxParts.push('<span style="color:#999;">ML Destek Yok</span>');
                }
                // Density
                if (typeof ctx.window_anomaly_density_pct === 'number') {
                    ctxParts.push('Density: %' + ctx.window_anomaly_density_pct.toFixed(1));
                }
                if (typeof ctx.window_weighted_density_pct === 'number') {
                    ctxParts.push('Agirlikli: %' + ctx.window_weighted_density_pct.toFixed(1));
                }
                // Global
                if (typeof ctx.global_mean_score === 'number') {
                    ctxParts.push('ML Skor: ' + ctx.global_mean_score.toFixed(4));
                }
                if (typeof ctx.global_anomaly_rate === 'number') {
                    ctxParts.push('Anomali: %' + ctx.global_anomaly_rate.toFixed(1));
                }
                html += ctxParts.join(' | ');

                // Severity breakdown mini-bar (if available)
                var sevBreak = ctx.window_severity_breakdown;
                if (sevBreak && typeof sevBreak === 'object') {
                    var sevParts = [];
                    if (sevBreak.CRITICAL) sevParts.push('<span style="color:#d32f2f;">' + sevBreak.CRITICAL + ' CRIT</span>');
                    if (sevBreak.HIGH) sevParts.push('<span style="color:#e65100;">' + sevBreak.HIGH + ' HIGH</span>');
                    if (sevBreak.MEDIUM) sevParts.push('<span style="color:#f9a825;">' + sevBreak.MEDIUM + ' MED</span>');
                    if (sevBreak.LOW) sevParts.push('<span style="color:#999;">' + sevBreak.LOW + ' LOW</span>');
                    if (sevParts.length > 0) {
                        html += '<div class="ppd-drill-sev-breakdown" style="margin-top:4px;font-size:0.82em;">'
                            + 'Pencere Severity: ' + sevParts.join(' / ') + '</div>';
                    }
                }
                html += '</div>';
            }

            // ML confidence adjustment info for forecast alerts
            if (al.ml_confidence_adjustment) {
                html += '<div class="ppd-drill-ml-adj" style="margin-top:4px;font-size:0.82em;color:#555;font-style:italic;">'
                    + esc(al.ml_confidence_adjustment) + '</div>';
            }

            // ML risk context for forecast alerts
            if (al.ml_risk_context && typeof al.ml_risk_context === 'object') {
                var rc = al.ml_risk_context;
                var rcParts = [];
                rcParts.push('ML Risk: <strong>' + esc(rc.ml_risk_level || 'OK') + '</strong>');
                if (typeof rc.current_mean_score === 'number') {
                    rcParts.push('Skor: ' + rc.current_mean_score.toFixed(4));
                }
                if (rc.score_worsening) rcParts.push('<span style="color:#d32f2f;">Skor Kotulesme</span>');
                if (typeof rc.anomaly_density_ratio === 'number' && rc.anomaly_density_ratio > 1.0) {
                    rcParts.push('Yogunluk: x' + rc.anomaly_density_ratio.toFixed(1));
                }
                html += '<div class="ppd-drill-ml-ctx" style="margin-top:4px;">' + rcParts.join(' | ') + '</div>';
            }

            // Explainability (collapsible)
            if (al.explainability) {
                html += '<details class="ppd-drill-explain">'
                    + '<summary>Aciklama ve Analiz Detayi</summary>'
                    + '<div class="ppd-drill-explain-text">' + esc(al.explainability) + '</div>'
                    + '</details>';
            }

            html += '</div>'; // end ppd-drill-alert
        }

        html += '</div>'; // end ppd-drill-panel
        return html;
    }

    // ============================
    // ROW DRILL-DOWN CLICK HANDLER
    // ============================
    function _initRowDrillDown() {
        var rows = document.querySelectorAll('.ppd-alert-row');
        for (var i = 0; i < rows.length; i++) {
            (function (row) {
                row.addEventListener('click', function () {
                    var idx = row.getAttribute('data-row-idx');
                    var drillRow = _el('ppdDrill_' + idx);
                    if (!drillRow) return;
                    var isVisible = drillRow.style.display !== 'none';
                    drillRow.style.display = isVisible ? 'none' : 'table-row';
                    row.classList.toggle('ppd-row-expanded', !isVisible);
                });
            })(rows[i]);
        }
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

    // Header "Analiz ve Tahmin Çalıştır" button handler
    function runAnalysis() {
        var btn = _el('ppdRunAnalysisBtn');
        if (!btn || btn.disabled) return;

        var serverVal = (_el('ppdServerFilter') || {}).value || '';
        var sourceType = _getSourceType() || 'mongodb';
        var sourceLabel = { mongodb: 'MongoDB', mssql: 'MSSQL', elasticsearch: 'Elasticsearch' }[sourceType] || sourceType;

        var msg = serverVal
            ? '"' + serverVal + '" icin ' + sourceLabel + ' analiz ve tahmin calistirilacak. Devam?'
            : sourceLabel + ' icin analiz ve tahmin calistirilacak. Devam?';

        _showConfirm('Analiz ve Tahmin Calistir', msg, function () {
            // Set loading state on header button
            btn.disabled = true;
            var origText = btn.innerHTML;
            btn.innerHTML = '<span class="pps-run-icon pps-run-spinning">&#x21bb;</span> Calisiyor...';
            btn.classList.add('pps-run-busy');

            var body = {
                api_key: window.apiKey || '',
                source_type: sourceType
            };
            if (serverVal) body.server_name = serverVal;

            // Dedicated on-demand prediction endpoint
            var base = window.API_ENDPOINTS ? window.API_ENDPOINTS['predictionRun'] : null;
            if (!base) {
                // Fallback to scheduler trigger if new endpoint not registered
                base = window.API_ENDPOINTS ? window.API_ENDPOINTS['schedulerTrigger'] : null;
            }
            if (!base) {
                btn.disabled = false;
                btn.innerHTML = origText;
                btn.classList.remove('pps-run-busy');
                return;
            }

            fetch(base, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                btn.classList.remove('pps-run-busy');

                if (data.status === 'success') {
                    btn.classList.add('pps-run-success');
                    var summary = data.analysis_summary || {};
                    var anomalies = summary.n_anomalies || 0;
                    var rate = (summary.anomaly_rate || 0).toFixed(1);

                    // Build rich result text
                    var resultParts = [anomalies + ' anomali (%' + rate + ')'];

                    // Show prediction insight risk level if available
                    var insight = data.prediction_insight || {};
                    if (insight.risk_level && insight.risk_level !== 'OK') {
                        resultParts.push('Risk: ' + insight.risk_level);
                    }
                    // Show convergence if detected
                    if (insight.convergence_boost) {
                        resultParts.push(insight.converging_modules + ' modul yakinsamasi');
                    }

                    btn.innerHTML = '<span class="pps-run-icon">&#x2714;</span> ' +
                        resultParts.join(' | ');
                    console.log('[PredictionDashboard] Analysis completed', data);
                } else {
                    btn.classList.add('pps-run-success');
                    btn.innerHTML = '<span class="pps-run-icon">&#x2714;</span> Tamamlandi';
                    console.log('[PredictionDashboard] Analysis triggered', data);
                }

                loadSchedulerStatus();
                // Refresh prediction panels with fresh data
                refreshAll();
                setTimeout(function () {
                    btn.disabled = false;
                    btn.innerHTML = origText;
                    btn.classList.remove('pps-run-success');
                }, 3000);
            })
            .catch(function (err) {
                btn.classList.remove('pps-run-busy');
                btn.classList.add('pps-run-error');
                btn.innerHTML = '<span class="pps-run-icon">&#x26A0;</span> Hata';
                console.error('[PredictionDashboard] Analysis trigger error:', err);
                setTimeout(function () {
                    btn.disabled = false;
                    btn.innerHTML = origText;
                    btn.classList.remove('pps-run-error');
                }, 3000);
            });
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

        // Header "Analiz ve Tahmin Çalıştır" button
        var runAnalysisBtn = _el('ppdRunAnalysisBtn');
        if (runAnalysisBtn) {
            runAnalysisBtn.addEventListener('click', function () { runAnalysis(); });
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
