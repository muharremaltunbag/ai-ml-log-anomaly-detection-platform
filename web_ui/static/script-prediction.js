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
    var _guideCollapsed = false;  // onboarding guide state
    var _lastTotalChecks = 0;     // for readiness bar
    var _lastSchedulerRunning = false;  // for readiness bar

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

            // Update scheduler source_type (fire-and-forget)
            var st = _getSourceType();
            if (st) {
                _postSchedulerConfig({ source_type: st }, 'Kaynak tipi guncellendi: ' + st);
            }

            // Refresh all data including host list for new source
            // (refreshAll already calls loadAvailableHosts)
            refreshAll();
        });
    }

    // ============================
    // LOAD AVAILABLE HOSTS BY SOURCE
    // ============================
    var _lastLoadedHosts = [];
    var _hostsLoading = false;

    function loadAvailableHosts() {
        if (_hostsLoading) return;  // debounce
        var st = _getSourceType() || 'mongodb';
        var url = _apiUrl('schedulerHosts', 'source_type=' + encodeURIComponent(st));
        if (!url) return;

        var container = _el('ppsHostsList');
        if (container) {
            container.innerHTML = '<span class="pps-hosts-empty">'
                + '<div class="ppd-loading-spinner" style="width:14px;height:14px;border-width:2px;display:inline-block;vertical-align:middle;margin-right:6px;"></div>'
                + 'Sunucu listesi yukleniyor...</span>';
        }

        _hostsLoading = true;
        fetch(url)
            .then(function (r) {
                if (!r.ok) throw new Error('HTTP ' + r.status);
                return r.json();
            })
            .then(function (data) {
                _hostsLoading = false;
                if (data.status !== 'success') {
                    _showHostsError(st, data.message || 'Beklenmeyen hata');
                    return;
                }
                var hosts = data.hosts || [];
                _lastLoadedHosts = hosts;
                _renderHostCheckboxes(hosts);
            })
            .catch(function (err) {
                _hostsLoading = false;
                console.warn('[PredictionDashboard] Host discovery error:', err);
                _showHostsError(st, String(err));
            });
    }

    function _showHostsError(sourceType, detail) {
        var container = _el('ppsHostsList');
        if (!container) return;
        var sourceLabel = { mongodb: 'MongoDB', mssql: 'MSSQL', elasticsearch: 'Elasticsearch' }[sourceType] || sourceType;
        container.innerHTML = '<span class="pps-hosts-empty pps-hosts-error">'
            + sourceLabel + ' sunucu listesi alinamadi. '
            + '<br><small>' + esc(detail) + '</small>'
            + '</span>';
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
        loadLatestContext(serverVal);
        loadSummary(serverVal, daysVal);
        loadServerOverview(daysVal);
        loadAlerts(serverVal, daysVal);
        loadTimeseries(serverVal, daysVal);
        loadSchedulerStatus();
        loadAvailableHosts();
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
            { label: 'Trend Detection', on: !!(cfg.trend_detection && cfg.trend_detection.enabled),
              tip: 'Gecmis analizleri karsilastirarak anomali trend degisimini tespit eder' },
            { label: 'Rate Alerting', on: !!(cfg.rate_alerting && cfg.rate_alerting.enabled),
              tip: 'Zaman pencerelerinde event esik asimlarini anlik kontrol eder' },
            { label: 'Forecasting', on: !!(cfg.forecasting && cfg.forecasting.enabled),
              tip: 'Istatistiksel modeller ile gelecekteki anomali oranini tahmin eder' },
            { label: 'Scheduler', on: !!(cfg.scheduler && cfg.scheduler.enabled),
              tip: 'Duzenli otomatik analiz calistirarak prediction verisini biriktirir' }
        ];

        var html = '';
        var allOff = true;
        for (var i = 0; i < pills.length; i++) {
            var p = pills[i];
            if (p.on) allOff = false;
            html += '<span class="ppd-config-pill ' + (p.on ? 'ppd-config-pill-on' : 'ppd-config-pill-off') + '"'
                + ' title="' + esc(p.tip) + '">'
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
    // LATEST CONTEXT PANEL
    // ============================
    function loadLatestContext(server) {
        var extra = '';
        if (server) extra += 'server_name=' + encodeURIComponent(server);
        var st = _getSourceType();
        if (st) extra += (extra ? '&' : '') + 'source_type=' + encodeURIComponent(st);
        var url = _apiUrl('predictionLatestContext', extra);
        if (!url) return;

        fetch(url)
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.status !== 'success' || !data.context) return;
                renderLatestContext(data.context);
                // Update readiness bar with actual forecast history depth
                if (typeof data.context.forecast_history_count === 'number') {
                    _lastTotalChecks = data.context.forecast_history_count;
                    _renderReadinessBar(_lastTotalChecks, _lastSchedulerRunning);
                }
            })
            .catch(function (err) {
                console.warn('[PredictionDashboard] Latest context fetch error:', err);
            });
    }

    function renderLatestContext(ctx) {
        var panel = _el('ppdContextPanel');
        var body = _el('ppdContextBody');
        var badge = _el('ppdContextBadge');
        if (!panel || !body) return;

        var rs = ctx.risk_summary || {};
        var maxSev = rs.max_severity || 'OK';
        var totalAlerts = rs.total_alerts || 0;
        var lastCheck = ctx.last_check;
        var signals = rs.risk_signals || [];

        // Show panel
        panel.style.display = 'block';

        // Badge
        if (badge) {
            var badgeCls = 'ppd-ctx-badge-ok';
            if (maxSev === 'CRITICAL') badgeCls = 'ppd-ctx-badge-critical';
            else if (maxSev === 'HIGH' || maxSev === 'WARNING') badgeCls = 'ppd-ctx-badge-warn';
            else if (maxSev === 'MEDIUM' || maxSev === 'INFO') badgeCls = 'ppd-ctx-badge-info';
            badge.textContent = maxSev;
            badge.className = 'ppd-context-badge ' + badgeCls;
        }

        // No data state
        if (!lastCheck) {
            body.innerHTML = '<div class="ppd-ctx-empty">'
                + '<p><strong>Henuz prediction verisi yok.</strong></p>'
                + '<p>Prediction verileri anomaly analizi calistirildiktan sonra otomatik olarak olusur. Baslangic icin:</p>'
                + '<ol>'
                + '<li>Ustteki <strong>"Analiz ve Tahmin Calistir"</strong> butonuna basin — ilk analiz ve prediction verisi olusur</li>'
                + '<li>Ardından <strong>scheduler\'i etkinlestirin</strong> (sol panel) — duzenli veri birikimi baslar</li>'
                + '<li><strong>En az 5 analiz</strong> biriktikten sonra Forecasting aktif olur, 20+ ile en iyi kaliteye ulasilir</li>'
                + '</ol>'
                + '<p class="ppd-ctx-hint-text">Her analiz calistirmaniz prediction icin bir veri noktasi olusturur. '
                + 'Scheduler acikken bu islem otomatik tekrarlanir ve tahminler surekli iyilesir.</p>'
                + '</div>';
            return;
        }

        var html = '';

        // Last check info
        var checkTime = lastCheck ? lastCheck.replace('T', ' ').substring(0, 19) : '-';
        html += '<div class="ppd-ctx-row">'
            + '<span class="ppd-ctx-label">Son Analiz</span>'
            + '<span class="ppd-ctx-value">' + esc(checkTime) + '</span>'
            + '</div>';

        // Server
        if (ctx.server_name) {
            html += '<div class="ppd-ctx-row">'
                + '<span class="ppd-ctx-label">Sunucu</span>'
                + '<span class="ppd-ctx-value">' + esc(ctx.server_name) + '</span>'
                + '</div>';
        }

        // Source type
        if (ctx.source_type) {
            var srcLabels = { mongodb: 'MongoDB', opensearch: 'MongoDB (OpenSearch)', mssql: 'MSSQL', mssql_opensearch: 'MSSQL', elasticsearch: 'Elasticsearch', elasticsearch_opensearch: 'Elasticsearch' };
            var srcLabel = srcLabels[ctx.source_type] || ctx.source_type;
            html += '<div class="ppd-ctx-row">'
                + '<span class="ppd-ctx-label">Kaynak</span>'
                + '<span class="ppd-ctx-value">' + esc(srcLabel) + '</span>'
                + '</div>';
        }

        // Module status row
        var modules = ['trend', 'rate', 'forecast'];
        html += '<div class="ppd-ctx-modules">';
        for (var i = 0; i < modules.length; i++) {
            var m = modules[i];
            var rec = ctx[m];
            var mLabel = m === 'trend' ? 'Trend' : (m === 'rate' ? 'Rate Alert' : 'Forecast');
            var mStatus, mCls;
            if (!rec) {
                mStatus = 'Veri yok';
                mCls = 'ppd-ctx-mod-none';
            } else if (rec.has_alerts) {
                mStatus = rec.alert_count + ' uyari (' + rec.max_severity + ')';
                mCls = 'ppd-ctx-mod-alert';
            } else {
                mStatus = 'Normal';
                mCls = 'ppd-ctx-mod-ok';
            }
            html += '<div class="ppd-ctx-mod ' + mCls + '">'
                + '<span class="ppd-ctx-mod-label">' + mLabel + '</span>'
                + '<span class="ppd-ctx-mod-status">' + mStatus + '</span>'
                + '</div>';
        }
        html += '</div>';

        // Risk signals
        if (signals.length > 0) {
            html += '<div class="ppd-ctx-signals">'
                + '<span class="ppd-ctx-signals-title">Aktif Risk Sinyalleri</span>';
            for (var j = 0; j < signals.length; j++) {
                var sig = signals[j];
                var sigSev = (sig.severity || 'OK').toLowerCase();
                html += '<div class="ppd-ctx-signal ppd-ctx-sig-' + sigSev + '">'
                    + '<span class="ppd-ctx-sig-src">' + esc(sig.source) + '</span> '
                    + esc(sig.title)
                    + '</div>';
            }
            html += '</div>';
        } else if (totalAlerts === 0) {
            html += '<div class="ppd-ctx-ok-msg">Aktif risk sinyali tespit edilmedi. Sistem normal.</div>';
        }

        // Forecast Outlook — rising/falling metric summary from latest forecast
        var fcData = (ctx.forecast && ctx.forecast.data && ctx.forecast.data.forecasts) ? ctx.forecast.data.forecasts : null;
        if (fcData) {
            var fcKeys = Object.keys(fcData);
            var risingMetrics = [];
            var fallingMetrics = [];
            var stableCount = 0;
            var insuffCount = 0;
            for (var fi = 0; fi < fcKeys.length; fi++) {
                var fm = fcData[fcKeys[fi]];
                if (!fm || typeof fm !== 'object') continue;
                if (fm.status === 'insufficient_data') { insuffCount++; continue; }
                if (!fm.direction) continue;
                var fcItem = {
                    name: fm.label || fcKeys[fi],
                    direction: fm.direction,
                    current: fm.current_value,
                    forecast: fm.forecast_value,
                    confidence: fm.confidence,
                    method: fm.method || '',
                    unit: fm.unit || ''
                };
                if (fm.direction === 'rising') risingMetrics.push(fcItem);
                else if (fm.direction === 'falling') fallingMetrics.push(fcItem);
                else stableCount++;
            }

            if (risingMetrics.length > 0 || fallingMetrics.length > 0 || stableCount > 0) {
                html += '<div class="ppd-outlook-section">';
                html += '<div class="ppd-outlook-header">Gelecek Tahmin Ozeti</div>';

                // Rising metrics — these are the risks
                if (risingMetrics.length > 0) {
                    html += '<div class="ppd-outlook-group ppd-outlook-rising">';
                    html += '<span class="ppd-outlook-group-title">&#x2197; Yukselis Trendinde (' + risingMetrics.length + ' metrik)</span>';
                    for (var ri2 = 0; ri2 < Math.min(risingMetrics.length, 5); ri2++) {
                        var rm = risingMetrics[ri2];
                        var rmConf = typeof rm.confidence === 'number' ? Math.round(rm.confidence * 100) : 0;
                        var rmConfCls = rmConf >= 60 ? 'ppd-conf-high' : (rmConf >= 30 ? 'ppd-conf-med' : 'ppd-conf-low');
                        html += '<div class="ppd-outlook-metric ppd-outlook-metric-rising">'
                            + '<span class="ppd-outlook-metric-name">' + esc(rm.name) + '</span>'
                            + '<span class="ppd-outlook-metric-arrow">&#x2197;</span>';
                        if (rm.current != null && rm.forecast != null) {
                            html += '<span class="ppd-outlook-metric-vals">'
                                + parseFloat(rm.current).toFixed(2) + ' → ' + parseFloat(rm.forecast).toFixed(2)
                                + (rm.unit ? ' ' + esc(rm.unit) : '')
                                + '</span>';
                        }
                        html += '<span class="ppd-conf-badge ' + rmConfCls + '">%' + rmConf + '</span>'
                            + '</div>';
                    }
                    html += '</div>';
                }

                // Falling metrics — good news
                if (fallingMetrics.length > 0) {
                    html += '<div class="ppd-outlook-group ppd-outlook-falling">';
                    html += '<span class="ppd-outlook-group-title">&#x2198; Dusus Trendinde (' + fallingMetrics.length + ' metrik)</span>';
                    for (var fi2 = 0; fi2 < Math.min(fallingMetrics.length, 3); fi2++) {
                        var fmi = fallingMetrics[fi2];
                        html += '<div class="ppd-outlook-metric ppd-outlook-metric-falling">'
                            + '<span class="ppd-outlook-metric-name">' + esc(fmi.name) + '</span>'
                            + '<span class="ppd-outlook-metric-arrow">&#x2198;</span>';
                        if (fmi.current != null && fmi.forecast != null) {
                            html += '<span class="ppd-outlook-metric-vals">'
                                + parseFloat(fmi.current).toFixed(2) + ' → ' + parseFloat(fmi.forecast).toFixed(2)
                                + '</span>';
                        }
                        html += '</div>';
                    }
                    html += '</div>';
                }

                // Stable + insufficient summary line
                var summaryParts = [];
                if (stableCount > 0) summaryParts.push(stableCount + ' metrik stabil');
                if (insuffCount > 0) summaryParts.push(insuffCount + ' metrik icin yeterli veri yok');
                if (summaryParts.length > 0) {
                    html += '<div class="ppd-outlook-summary">' + summaryParts.join(' · ') + '</div>';
                }

                html += '</div>';
            }
        }

        // ML-Derived Risk Insight (data is nested under ctx.insight.data)
        var insight = (ctx.insight && ctx.insight.data) ? ctx.insight.data : null;
        if (insight) {
            html += '<div class="ppd-insight-section">';
            html += '<div class="ppd-insight-header">ML Risk Insight</div>';

            // Risk direction indicator
            var dirMap = {
                'elevated': { label: 'Yuksek', cls: 'critical' },
                'moderate': { label: 'Orta', cls: 'warning' },
                'low': { label: 'Dusuk', cls: 'ok' },
                'stable': { label: 'Stabil', cls: 'ok' }
            };
            var dir = dirMap[insight.risk_direction] || { label: insight.risk_direction || '-', cls: 'ok' };
            html += '<div class="ppd-insight-direction ppd-insight-dir-' + dir.cls + '">'
                + '<span class="ppd-insight-dir-label">Risk Seviyesi</span>'
                + '<span class="ppd-insight-dir-value">' + dir.label + '</span>'
                + '<span class="ppd-insight-dir-detail">'
                + (insight.anomaly_count || 0) + ' anomali / ' + (insight.total_logs || 0) + ' log'
                + ' (%' + (insight.anomaly_rate || 0) + ')'
                + '</span>'
                + '</div>';

            // Severity distribution bar
            var sevDist = insight.severity_distribution;
            if (sevDist) {
                var sevKeys = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'];
                var sevClsMap = { CRITICAL: 'ppd-sev-bar-critical', HIGH: 'ppd-sev-bar-high', MEDIUM: 'ppd-sev-bar-medium', LOW: 'ppd-sev-bar-low' };
                var sevTotal = 0;
                for (var si = 0; si < sevKeys.length; si++) {
                    sevTotal += (sevDist[sevKeys[si]] || 0);
                }
                if (sevTotal > 0) {
                    html += '<div class="ppd-insight-sev">'
                        + '<span class="ppd-insight-sev-title">Severity Dagilimi</span>'
                        + '<div class="ppd-insight-sev-bar">';
                    for (var sk = 0; sk < sevKeys.length; sk++) {
                        var sVal = sevDist[sevKeys[sk]] || 0;
                        if (sVal > 0) {
                            var pct = ((sVal / sevTotal) * 100).toFixed(1);
                            html += '<div class="ppd-insight-sev-seg ' + sevClsMap[sevKeys[sk]] + '" style="width:' + pct + '%"'
                                + ' title="' + sevKeys[sk] + ': ' + sVal + ' (' + pct + '%)">'
                                + '</div>';
                        }
                    }
                    html += '</div><div class="ppd-insight-sev-legend">';
                    for (var sl = 0; sl < sevKeys.length; sl++) {
                        var sv = sevDist[sevKeys[sl]] || 0;
                        if (sv > 0) {
                            html += '<span class="ppd-insight-sev-leg-item">'
                                + '<span class="ppd-insight-sev-dot ' + sevClsMap[sevKeys[sl]] + '"></span>'
                                + sevKeys[sl] + ': ' + sv
                                + '</span>';
                        }
                    }
                    html += '</div></div>';
                }
            }

            // Dominant patterns
            var patterns = insight.dominant_patterns;
            if (patterns && patterns.length > 0) {
                html += '<div class="ppd-insight-block">'
                    + '<span class="ppd-insight-block-title">Baskin Anomali Kaliplari</span>';
                var maxShow = Math.min(patterns.length, 5);
                for (var pi = 0; pi < maxShow; pi++) {
                    var p = patterns[pi];
                    var pSevCls = (p.max_severity || 'LOW').toLowerCase();
                    html += '<div class="ppd-insight-pattern">'
                        + '<span class="ppd-insight-pat-badge ppd-insight-pat-' + pSevCls + '">'
                        + esc(p.component || '?') + '</span>'
                        + '<span class="ppd-insight-pat-count">' + p.count + 'x</span> '
                        + '<span class="ppd-insight-pat-msg">' + esc(p.sample_message || p.fingerprint_preview || '') + '</span>'
                        + '</div>';
                }
                html += '</div>';
            }

            // Component hotspots
            var hotspots = insight.component_hotspots;
            if (hotspots && hotspots.length > 0) {
                html += '<div class="ppd-insight-block">'
                    + '<span class="ppd-insight-block-title">Component Hotspot\'lar</span>';
                for (var hi = 0; hi < hotspots.length; hi++) {
                    var h = hotspots[hi];
                    html += '<div class="ppd-insight-hotspot">'
                        + '<span class="ppd-insight-hs-name">' + esc(h.component) + '</span>'
                        + '<span class="ppd-insight-hs-bar"><span class="ppd-insight-hs-fill" style="width:'
                        + Math.min(h.anomaly_rate, 100) + '%"></span></span>'
                        + '<span class="ppd-insight-hs-val">' + h.anomaly_count + ' (%' + h.anomaly_rate + ')</span>'
                        + '</div>';
                }
                html += '</div>';
            }

            // Potential risk areas
            var risks = insight.potential_risk_areas;
            if (risks && risks.length > 0) {
                html += '<div class="ppd-insight-block">'
                    + '<span class="ppd-insight-block-title">Potansiyel Risk Alanlari</span>';
                for (var ri = 0; ri < risks.length; ri++) {
                    var rsk = risks[ri];
                    var rCls = (rsk.severity || 'warning').toLowerCase();
                    html += '<div class="ppd-insight-risk ppd-insight-risk-' + rCls + '">'
                        + '<span class="ppd-insight-risk-area">' + esc(rsk.area) + '</span>'
                        + '<span class="ppd-insight-risk-detail">' + esc(rsk.detail) + '</span>'
                        + '</div>';
                }
                html += '</div>';
            }

            // Confidence note
            if (insight.confidence_note) {
                html += '<div class="ppd-insight-conf">' + esc(insight.confidence_note) + '</div>';
            }

            html += '</div>';
        }

        body.innerHTML = html;
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
                var summary = data.summary || {};
                renderSummary(summary);
                // Feed readiness bar with total checks (proxy for history depth)
                _lastTotalChecks = summary.total_checks || 0;
                _renderReadinessBar(_lastTotalChecks, _lastSchedulerRunning);
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
                + '<div class="pps-empty-icon"><svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M18 20V10"/><path d="M12 20V4"/><path d="M6 20v-6"/></svg></div>'
                + '<div class="pps-empty-title">Prediction verisi henuz yok</div>'
                + '<div class="pps-empty-desc">'
                + 'Scheduler\'i etkinlestirin veya manuel analiz calistirin. Her analiz otomatik prediction verisi uretir.</div>'
                + '</div>';
        }

        var cards = [
            { title: 'Toplam Kontrol', value: totalChecks, sub: 'Son ' + periodDays + ' gun', cls: '' },
            { title: 'Toplam Uyari', value: totalAlerts, sub: 'Alert orani: %' + alertRate, cls: totalAlerts > 0 ? 'ppd-card-warn' : '' },
            { title: 'Trend Uyarilari', value: trendAlerts + ' / ' + trendTotal, sub: 'Trend analizi', cls: trendAlerts > 0 ? 'ppd-card-warn' : '' },
            { title: 'Oran Uyarilari', value: rateAlerts + ' / ' + rateTotal, sub: 'Oran izleme', cls: rateAlerts > 0 ? 'ppd-card-warn' : '' },
            { title: 'Tahmin Uyarilari', value: forecastAlerts + ' / ' + forecastTotal, sub: 'Tahmin modeli', cls: forecastAlerts > 0 ? 'ppd-card-warn' : '' }
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

            // Risk indicator dot (professional CSS-based)
            var riskDotClass = 'ppd-risk-dot-ok';
            if (riskLabel === 'CRITICAL') riskDotClass = 'ppd-risk-dot-critical';
            else if (riskLabel === 'WARNING') riskDotClass = 'ppd-risk-dot-warning';
            else if (riskLabel === 'INFO') riskDotClass = 'ppd-risk-dot-info';
            var riskIcon = '<span class="ppd-risk-dot ' + riskDotClass + '"></span>';

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
                    +   '<div class="ppd-bar-rate" style="width:' + rateW + '%" title="Oran: ' + s.rate_alerts + '"></div>'
                    +   '<div class="ppd-bar-forecast" style="width:' + forecastW + '%" title="Tahmin: ' + s.forecast_alerts + '"></div>'
                    + '</div>'
                    + '<div class="ppd-breakdown-legend">'
                    +   '<span class="ppd-legend-item"><span class="ppd-legend-dot ppd-dot-trend"></span>Trend ' + s.trend_alerts + '</span>'
                    +   '<span class="ppd-legend-item"><span class="ppd-legend-dot ppd-dot-rate"></span>Oran ' + s.rate_alerts + '</span>'
                    +   '<span class="ppd-legend-item"><span class="ppd-legend-dot ppd-dot-forecast"></span>Tahmin ' + s.forecast_alerts + '</span>'
                    + '</div>'
                    + '</div>';
            }

            // Actionable DBA guidance based on risk level
            var guidanceText = '';
            var guidanceIcon = '';
            if (riskLabel === 'CRITICAL') {
                guidanceIcon = '&#x26A0; ';
                guidanceText = 'Sunucuyu kontrol edin — ';
                // Add specifics from alert breakdown
                var critParts = [];
                if (s.trend_alerts > 0) critParts.push('trend artisi');
                if (s.rate_alerts > 0) critParts.push('esik asimi');
                if (s.forecast_alerts > 0) critParts.push('risk tahmini');
                guidanceText += critParts.length > 0 ? critParts.join(' + ') + ' tespit edildi' : 'yuksek risk tespit edildi';
            } else if (riskLabel === 'WARNING') {
                guidanceIcon = '&#x1F50D; ';
                guidanceText = 'Izleyin';
                if (s.trend_alerts > 0) guidanceText += ' — anomali trendi yukarida';
                else if (s.rate_alerts > 0) guidanceText += ' — oran artisi mevcut';
                else guidanceText += ' — dikkat gerektiren sinyaller var';
            }
            if (guidanceText) {
                html += '<div class="ppd-server-guidance">'
                    + guidanceIcon + esc(guidanceText) + '</div>';
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
                                + '<div class="pps-empty-title pps-empty-title-sm">Bu aralikta prediction kaydi yok</div>'
                                + '<div class="pps-empty-desc">'
                                + 'Farkli zaman araligi veya filtre deneyin.</div>'
                                + '</td></tr>';
                        }
                    }
                    return;
                }
                renderAlerts(data.alerts);
                renderActiveRisks(data.alerts);
                populateServerFilter(data.alerts);
            })
            .catch(function (err) {
                _loading = false;
                console.warn('[PredictionDashboard] Alerts fetch error:', err);
            });
    }

    // ============================
    // ACTIVE RISKS PANEL
    // ============================
    function renderActiveRisks(alerts) {
        var panel = _el('ppdActiveRisks');
        var list = _el('ppdRiskList');
        if (!panel || !list) return;

        // Extract CRITICAL and WARNING alerts with actual sub-alerts
        var risks = [];
        for (var i = 0; i < alerts.length; i++) {
            var a = alerts[i];
            if (a.max_severity !== 'CRITICAL' && a.max_severity !== 'WARNING') continue;
            var dataAlerts = (a.data && Array.isArray(a.data.alerts)) ? a.data.alerts : [];
            if (dataAlerts.length === 0) continue;

            for (var j = 0; j < dataAlerts.length; j++) {
                var al = dataAlerts[j];
                risks.push({
                    severity: al.severity || a.max_severity,
                    title: al.title || al.alert_type || '-',
                    server: a.server_name || '-',
                    source: ({ trend: 'Trend', rate: 'Oran', forecast: 'Tahmin', insight: 'Ozet' })[a.alert_source] || a.alert_source || '-',
                    sourceType: a.source_type || '',
                    description: al.description || '',
                    sample: (al.sample_messages && al.sample_messages.length > 0)
                        ? al.sample_messages[0] : '',
                    confidence: al.confidence,
                    timestamp: a.timestamp || '',
                    action: al.recommendation || al.description || '',
                    mlSupported: !!(al.ml_context && al.ml_context.ml_corroborated)
                });
            }
        }

        if (risks.length === 0) {
            panel.style.display = 'none';
            return;
        }

        // Sort: CRITICAL first, then by confidence desc
        risks.sort(function (a, b) {
            if (a.severity !== b.severity) {
                return a.severity === 'CRITICAL' ? -1 : 1;
            }
            return (b.confidence || 0) - (a.confidence || 0);
        });

        // Limit to top 8
        var top = risks.slice(0, 8);
        var html = '';
        for (var k = 0; k < top.length; k++) {
            var r = top[k];
            var sevCls = 'ppd-sev-' + r.severity.toLowerCase();
            var ts = r.timestamp;
            if (ts && ts.length > 16) ts = ts.substring(0, 16).replace('T', ' ');

            // Source type label — dynamic from data
            var stLabel = '';
            if (r.sourceType) {
                if (r.sourceType.indexOf('mssql') >= 0) stLabel = 'MSSQL';
                else if (r.sourceType.indexOf('elasticsearch') >= 0) stLabel = 'ES';
                else if (r.sourceType.indexOf('mongodb') >= 0 || r.sourceType.indexOf('opensearch') >= 0) stLabel = 'Mongo';
                else stLabel = r.sourceType;
            }

            html += '<div class="ppd-risk-item">'
                + '<div class="ppd-risk-header">'
                +   '<span class="ppd-severity-tag ' + sevCls + '">' + esc(r.severity) + '</span>'
                +   '<span class="ppd-risk-title">' + esc(r.title) + '</span>';
            if (r.mlSupported) {
                html += '<span class="ppd-ml-badge ppd-ml-confirmed" title="ML destekli">ML &#x2713;</span>';
            }
            if (typeof r.confidence === 'number') {
                var pct = Math.round(r.confidence * 100);
                html += '<span class="ppd-conf-badge ' + (pct >= 60 ? 'ppd-conf-high' : 'ppd-conf-med') + '">%' + pct + '</span>';
            }
            html += '</div>'
                + '<div class="ppd-risk-meta">'
                +   '<span class="ppd-risk-server">' + esc(r.server) + '</span>';
            if (stLabel) html += '<span class="ppd-risk-src">' + stLabel + '</span>';
            html += '<span class="ppd-risk-source">' + esc(r.source) + '</span>'
                +   '<span class="ppd-risk-time">' + esc(ts) + '</span>'
                + '</div>';

            // Sample log message (fingerprint) — wider display
            if (r.sample) {
                var sampleShort = r.sample.length > 180 ? r.sample.substring(0, 180) + '...' : r.sample;
                html += '<div class="ppd-risk-sample">' + esc(sampleShort) + '</div>';
            }

            // Actionable recommendation
            if (r.action) {
                html += '<div class="ppd-risk-action">' + esc(r.action) + '</div>';
            }

            html += '</div>';
        }

        if (risks.length > 8) {
            html += '<div class="ppd-risk-more">+' + (risks.length - 8) + ' daha — detaylar icin alert tablosuna bakin</div>';
        }

        list.innerHTML = html;
        panel.style.display = '';
    }

    // _riskAction() kaldirildi — aksiyon onerileri artik backend'den
    // al.recommendation veya al.description olarak dinamik geliyor.
    // Her alert tipi (RateAlert, TrendAlert, ForecastAlert) kendi
    // metriklerinden otomatik recommendation uretur.

    var _sevOrder = { 'CRITICAL': 0, 'WARNING': 1, 'INFO': 2, 'OK': 3 };

    function renderAlerts(alerts) {
        var wrapper = _el('ppdTableWrapper');
        var tbody = _el('ppdTableBody');
        if (!tbody || !wrapper) return;

        // Sort: severity DESC (CRITICAL first), then timestamp DESC within same severity
        var sorted = alerts.slice().sort(function (a, b) {
            var sa = _sevOrder[a.max_severity || 'INFO'];
            var sb = _sevOrder[b.max_severity || 'INFO'];
            if (sa === undefined) sa = 9;
            if (sb === undefined) sb = 9;
            if (sa !== sb) return sa - sb;
            // Same severity — newest first
            var ta = a.timestamp || '';
            var tb = b.timestamp || '';
            return ta > tb ? -1 : ta < tb ? 1 : 0;
        });

        var html = '';
        for (var i = 0; i < sorted.length; i++) {
            var a = sorted[i];
            var ts = a.timestamp || '';
            if (ts && ts.length > 19) ts = ts.substring(0, 19).replace('T', ' ');
            var rawSource = a.alert_source || '-';
            var sourceLabels = { trend: 'Trend', rate: 'Oran', forecast: 'Tahmin', insight: 'Ozet' };
            var source = sourceLabels[rawSource] || rawSource;
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

            // Source type badge (MongoDB / MSSQL / Elasticsearch)
            var sourceType = a.source_type || '';
            var sourceTypeLabel = '';
            var sourceTypeCls = 'ppd-srctype-default';
            if (sourceType.indexOf('mssql') >= 0) {
                sourceTypeLabel = 'MSSQL';
                sourceTypeCls = 'ppd-srctype-mssql';
            } else if (sourceType.indexOf('elasticsearch') >= 0) {
                sourceTypeLabel = 'ES';
                sourceTypeCls = 'ppd-srctype-es';
            } else if (sourceType.indexOf('opensearch') >= 0 || sourceType.indexOf('mongodb') >= 0) {
                sourceTypeLabel = 'Mongo';
                sourceTypeCls = 'ppd-srctype-mongo';
            }
            var sourceTypeBadge = sourceTypeLabel
                ? '<span class="ppd-srctype-badge ' + sourceTypeCls + '">' + sourceTypeLabel + '</span> '
                : '';

            // Confidence cell
            var confidenceHtml = _buildConfidenceCell(dataAlerts);

            // Build detail snippet
            var detail = _buildDetailSnippet(a);

            html += '<tr class="ppd-alert-row" data-row-idx="' + i + '">'
                + '<td>' + esc(ts) + '</td>'
                + '<td>' + sourceTypeBadge + esc(source) + '</td>'
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

        if (parts.length === 0) return '<span class="ppd-detail-hint">Normal — detay icin tiklayin</span>';
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
    // FORECAST PROJECTION MINI-CHART
    // ============================
    var _projCanvasId = 0;

    /**
     * Renders an inline forecast projection chart using Canvas.
     * @param {number[]} historyValues - historical metric values (up to 15)
     * @param {number|null} forecastValue - projected value
     * @param {number|null} upperBound - upper confidence bound
     * @param {number|null} lowerBound - lower confidence bound
     * @param {string} label - metric label
     * @param {string} direction - rising/falling/stable
     * @returns {string} HTML string with canvas element + initialization script ID
     */
    function _buildProjectionChart(historyValues, forecastValue, upperBound, lowerBound, label, direction) {
        if (!historyValues || historyValues.length < 2) return '';
        var canvasId = 'ppdProjCanvas_' + (++_projCanvasId);
        var hasForecast = forecastValue != null && !isNaN(forecastValue);

        // Build data arrays
        var hist = historyValues.slice();
        var n = hist.length;

        // Calculate y-axis range
        var allVals = hist.slice();
        if (hasForecast) {
            allVals.push(forecastValue);
            if (upperBound != null) allVals.push(upperBound);
            if (lowerBound != null) allVals.push(lowerBound);
        }
        var yMin = Math.min.apply(null, allVals);
        var yMax = Math.max.apply(null, allVals);
        var yPad = (yMax - yMin) * 0.15 || 1;
        yMin = yMin - yPad;
        yMax = yMax + yPad;

        var dirLabel = direction === 'rising' ? 'Yukari' : (direction === 'falling' ? 'Asagi' : 'Stabil');
        var dirCls = direction === 'rising' ? 'ppd-proj-rising' : (direction === 'falling' ? 'ppd-proj-falling' : 'ppd-proj-stable');

        var html = '<div class="ppd-proj-container ' + dirCls + '">'
            + '<div class="ppd-proj-header">'
            + '<span class="ppd-proj-label">' + esc(label) + '</span>'
            + '<span class="ppd-proj-dir">' + dirLabel + '</span>'
            + '</div>'
            + '<canvas id="' + canvasId + '" class="ppd-proj-canvas" width="320" height="120"></canvas>'
            + '</div>';

        // Defer drawing so canvas is in DOM
        setTimeout(function () {
            var canvas = document.getElementById(canvasId);
            if (!canvas) return;
            var ctx = canvas.getContext('2d');
            var W = canvas.width;
            var H = canvas.height;
            var padL = 6, padR = 6, padT = 8, padB = 16;
            var plotW = W - padL - padR;
            var plotH = H - padT - padB;

            var totalPts = hasForecast ? n + 1 : n;
            function xPos(i) { return padL + (i / (totalPts - 1)) * plotW; }
            function yPos(v) { return padT + plotH - ((v - yMin) / (yMax - yMin)) * plotH; }

            // Draw confidence band (shaded region from last history point to forecast)
            if (hasForecast && upperBound != null && lowerBound != null) {
                ctx.fillStyle = 'rgba(33, 150, 243, 0.10)';
                ctx.beginPath();
                ctx.moveTo(xPos(n - 1), yPos(hist[n - 1]));
                ctx.lineTo(xPos(n), yPos(upperBound));
                ctx.lineTo(xPos(n), yPos(lowerBound));
                ctx.closePath();
                ctx.fill();

                // Upper/lower bound dashed lines
                ctx.strokeStyle = 'rgba(33, 150, 243, 0.35)';
                ctx.lineWidth = 1;
                ctx.setLineDash([3, 3]);
                ctx.beginPath();
                ctx.moveTo(xPos(n - 1), yPos(hist[n - 1]));
                ctx.lineTo(xPos(n), yPos(upperBound));
                ctx.stroke();
                ctx.beginPath();
                ctx.moveTo(xPos(n - 1), yPos(hist[n - 1]));
                ctx.lineTo(xPos(n), yPos(lowerBound));
                ctx.stroke();
                ctx.setLineDash([]);
            }

            // Draw history line
            ctx.strokeStyle = '#546e7a';
            ctx.lineWidth = 1.5;
            ctx.beginPath();
            for (var i = 0; i < n; i++) {
                var x = xPos(i);
                var y = yPos(hist[i]);
                if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
            }
            ctx.stroke();

            // Draw history points
            ctx.fillStyle = '#546e7a';
            for (var j = 0; j < n; j++) {
                ctx.beginPath();
                ctx.arc(xPos(j), yPos(hist[j]), 2, 0, Math.PI * 2);
                ctx.fill();
            }

            // Draw forecast projection line + point
            if (hasForecast) {
                var fcColor = direction === 'rising' ? '#d32f2f' : (direction === 'falling' ? '#2e7d32' : '#1565c0');
                ctx.strokeStyle = fcColor;
                ctx.lineWidth = 2;
                ctx.setLineDash([5, 3]);
                ctx.beginPath();
                ctx.moveTo(xPos(n - 1), yPos(hist[n - 1]));
                ctx.lineTo(xPos(n), yPos(forecastValue));
                ctx.stroke();
                ctx.setLineDash([]);

                // Forecast point (larger, filled)
                ctx.fillStyle = fcColor;
                ctx.beginPath();
                ctx.arc(xPos(n), yPos(forecastValue), 4, 0, Math.PI * 2);
                ctx.fill();
                ctx.strokeStyle = '#fff';
                ctx.lineWidth = 1.5;
                ctx.stroke();

                // Value label at forecast point
                ctx.fillStyle = fcColor;
                ctx.font = '10px sans-serif';
                ctx.textAlign = 'center';
                ctx.fillText(forecastValue.toFixed(1), xPos(n), yPos(forecastValue) - 7);
            }

            // Current value label
            ctx.fillStyle = '#546e7a';
            ctx.font = '9px sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText(hist[n - 1].toFixed(1), xPos(n - 1), yPos(hist[n - 1]) - 6);

            // X-axis labels
            ctx.fillStyle = '#999';
            ctx.font = '8px sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText('Gecmis', padL + plotW * 0.3, H - 2);
            if (hasForecast) {
                ctx.fillText('Tahmin', xPos(n), H - 2);
            }
        }, 30);

        return html;
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
                        var insuffStatus = 'Yetersiz veri (' + (fc.data_points || 0) + '/' + (fc.min_required || 2) + ')';
                        // Show tier guidance per metric
                        if (fc.guidance && fc.guidance.next) {
                            var gNeeded = fc.guidance.analyses_needed || 0;
                            if (gNeeded > 0) {
                                insuffStatus += ' — ' + gNeeded + ' analiz → ' + fc.guidance.next;
                            }
                        }
                        metricSummaries.push({
                            name: fc.label || fKey,
                            status: insuffStatus,
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
                    // Show tier guidance from forecaster
                    var guidanceShown = false;
                    for (var gk = 0; gk < fKeys.length && !guidanceShown; gk++) {
                        var gfc = forecasts[fKeys[gk]];
                        if (gfc && gfc.guidance && gfc.guidance.next) {
                            var needed = gfc.guidance.analyses_needed || 0;
                            if (needed > 0) {
                                msg += ' ' + needed + ' analiz daha yapin → ' + esc(gfc.guidance.next) + '.';
                                guidanceShown = true;
                            }
                        }
                    }
                } else {
                    msg = 'Tahmin modeli risk artisi tespit etmedi. Tum metrikler normal seyrediyor.';
                }
                // Build metric detail table
                if (metricSummaries.length > 0) {
                    extraHtml = '<div class="ppd-forecast-metrics">';
                    for (var m = 0; m < metricSummaries.length; m++) {
                        var ms = metricSummaries[m];
                        extraHtml += '<div class="ppd-metric-row ' + ms.cls + '">'
                            + '<span class="ppd-metric-name">' + esc(ms.name) + '</span>'
                            + '<span class="ppd-metric-status">' + ms.status + '</span>'
                            + '</div>';
                    }
                    extraHtml += '</div>';
                }
                // Forecast projection mini-charts for metrics with history
                var projHtml = '';
                for (var p = 0; p < fKeys.length; p++) {
                    var pfc = forecasts[fKeys[p]];
                    if (!pfc || !pfc.history_values || pfc.history_values.length < 2) continue;
                    projHtml += _buildProjectionChart(
                        pfc.history_values,
                        pfc.forecast_value != null ? parseFloat(pfc.forecast_value) : null,
                        pfc.upper_bound != null ? parseFloat(pfc.upper_bound) : null,
                        pfc.lower_bound != null ? parseFloat(pfc.lower_bound) : null,
                        pfc.label || fKeys[p],
                        pfc.direction || 'stable'
                    );
                }
                if (projHtml) {
                    extraHtml += '<div class="ppd-proj-grid">' + projHtml + '</div>';
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
                        extraHtml = '<div class="ppd-drill-score-summary">' + esc(scoreParts.join(' | ')) + '</div>';
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

            // Dynamic recommendation from backend
            if (al.recommendation) {
                html += '<div class="ppd-drill-recommendation">'
                    + '<span class="ppd-rec-icon">&#x2794;</span> '
                    + esc(al.recommendation) + '</div>';
            }

            // Forecast bounds + projection chart
            if (typeof al.forecast_value === 'number') {
                var lb = typeof al.lower_bound === 'number' ? al.lower_bound.toFixed(2) : '?';
                var ub = typeof al.upper_bound === 'number' ? al.upper_bound.toFixed(2) : '?';
                html += '<div class="ppd-drill-forecast">'
                    + 'Tahmin: ' + al.forecast_value.toFixed(2)
                    + ' [' + lb + ' \u2013 ' + ub + ']'
                    + '</div>';

                // Try to get history_values from parent forecast data
                var alertForecasts = (alertDoc.data && alertDoc.data.forecasts) || {};
                var metricKey = al.metric_name || '';
                var fcData = alertForecasts[metricKey];
                var histVals = (fcData && fcData.history_values) || null;
                if (!histVals && typeof al.current_value === 'number') {
                    // Fallback: 2-point chart with current → forecast
                    histVals = [al.current_value];
                }
                if (histVals && histVals.length >= 1) {
                    html += _buildProjectionChart(
                        histVals.length >= 2 ? histVals : [histVals[0], histVals[0]],
                        al.forecast_value,
                        typeof al.upper_bound === 'number' ? al.upper_bound : null,
                        typeof al.lower_bound === 'number' ? al.lower_bound : null,
                        al.title || metricKey,
                        al.direction || 'rising'
                    );
                }
            }

            // ML context detail for rate alerts (enriched with severity-weighted data)
            if (al.ml_context && typeof al.ml_context === 'object') {
                var ctx = al.ml_context;
                html += '<div class="ppd-drill-ml-ctx">';
                var ctxParts = [];
                // Corroboration status
                if (ctx.ml_strong_corroboration) {
                    ctxParts.push('<strong class="ppd-ml-tag-strong">ML Guclu Destek</strong>');
                } else if (ctx.ml_corroborated) {
                    ctxParts.push('<span class="ppd-ml-tag-supported">ML Destekli</span>');
                } else {
                    ctxParts.push('<span class="ppd-ml-tag-none">ML Destek Yok</span>');
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
                    if (sevBreak.CRITICAL) sevParts.push('<span class="ppd-sev-text-critical">' + sevBreak.CRITICAL + ' CRIT</span>');
                    if (sevBreak.HIGH) sevParts.push('<span class="ppd-sev-text-high">' + sevBreak.HIGH + ' HIGH</span>');
                    if (sevBreak.MEDIUM) sevParts.push('<span class="ppd-sev-text-medium">' + sevBreak.MEDIUM + ' MED</span>');
                    if (sevBreak.LOW) sevParts.push('<span class="ppd-sev-text-low">' + sevBreak.LOW + ' LOW</span>');
                    if (sevParts.length > 0) {
                        html += '<div class="ppd-drill-sev-breakdown">'
                            + 'Pencere Severity: ' + sevParts.join(' / ') + '</div>';
                    }
                }
                html += '</div>';
            }

            // ML confidence adjustment info for forecast alerts
            if (al.ml_confidence_adjustment) {
                html += '<div class="ppd-drill-ml-adj">'
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
                if (rc.score_worsening) rcParts.push('<span class="ppd-sev-text-critical">Skor Kotulesme</span>');
                if (typeof rc.anomaly_density_ratio === 'number' && rc.anomaly_density_ratio > 1.0) {
                    rcParts.push('Yogunluk: x' + rc.anomaly_density_ratio.toFixed(1));
                }
                html += '<div class="ppd-drill-ml-ctx ppd-drill-ml-ctx-inline">' + rcParts.join(' | ') + '</div>';
            }

            // Explainability — kısa özet her zaman görünür, uzun metin expandable
            if (al.explainability) {
                var explainText = String(al.explainability);
                // İlk cümle veya ilk 150 karakter
                var shortExplain = explainText;
                var needsExpand = false;
                var dotIdx = explainText.indexOf('. ');
                if (dotIdx > 0 && dotIdx < 160) {
                    shortExplain = explainText.substring(0, dotIdx + 1);
                    needsExpand = explainText.length > dotIdx + 2;
                } else if (explainText.length > 150) {
                    shortExplain = explainText.substring(0, 150) + '...';
                    needsExpand = true;
                }
                html += '<div class="ppd-drill-explain-visible">'
                    + '<span class="ppd-explain-icon">&#x1F4A1;</span> '
                    + esc(shortExplain)
                    + '</div>';
                if (needsExpand) {
                    html += '<details class="ppd-drill-explain">'
                        + '<summary>Detayli Aciklama</summary>'
                        + '<div class="ppd-drill-explain-text">' + esc(explainText) + '</div>'
                        + '</details>';
                }
            }

            // Forecast method badge (shown in drill-down for visibility)
            if (al.forecast_method) {
                html += '<div class="ppd-drill-method">'
                    + '<span class="ppd-method-badge">' + esc(_tierLabel(al.forecast_method)) + '</span>';
                if (typeof al.data_points_used === 'number') {
                    html += ' <span class="ppd-drill-datapoints">(' + al.data_points_used + ' veri noktasi)</span>';
                }
                html += '</div>';
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

    var _schedStatusRetry = 0;
    var _schedStatusMaxRetry = 2;

    function loadSchedulerStatus() {
        var url = _apiUrl('schedulerStatus');
        if (!url) return;

        fetch(url)
            .then(function (r) {
                if (!r.ok) throw new Error('HTTP ' + r.status);
                return r.json();
            })
            .then(function (data) {
                _schedStatusRetry = 0;
                if (data.status !== 'success') return;
                renderSchedulerStatus(data.scheduler || {});
            })
            .catch(function (err) {
                console.warn('[PredictionDashboard] Scheduler status error:', err);
                if (_schedStatusRetry < _schedStatusMaxRetry) {
                    _schedStatusRetry++;
                    var delay = _schedStatusRetry * 2000;
                    console.log('[PredictionDashboard] Retrying scheduler status in ' + delay + 'ms (attempt ' + _schedStatusRetry + ')');
                    setTimeout(loadSchedulerStatus, delay);
                    return;
                }
                var grid = _el('ppdSchedGrid');
                if (grid) grid.innerHTML = '<div class="ppd-error">'
                    + 'Scheduler durumu alinamadi — <a href="#" onclick="window.PredictionDashboard&&window.PredictionDashboard.refresh();return false;">Yenile</a>'
                    + '<br><small style="opacity:0.7">' + esc(String(err)) + '</small>'
                    + '</div>';
            });
    }

    function renderSchedulerStatus(sched) {
        var grid = _el('ppdSchedGrid');
        if (!grid) return;

        var enabled = !!sched.enabled;
        var running = !!sched.running;
        _lastSchedulerRunning = running;
        var interval = sched.interval_minutes || 30;
        var maxConcurrent = sched.max_concurrent || 3;
        var runCount = sched.run_count || 0;
        var lastRun = sched.last_run || null;
        var nextRun = sched.next_run || null;

        // Sync enable toggle
        var enableCheck = _el('ppsSchedEnableCheck');
        var enableText = _el('ppsSchedEnableText');
        if (enableCheck) enableCheck.checked = enabled;
        if (enableText) enableText.textContent = enabled ? 'Scheduler Aktif' : 'Scheduler Kapali';

        // Sync interval select
        var intervalSel = _el('ppsSchedIntervalSelect');
        if (intervalSel) intervalSel.value = String(interval);

        // Format last run time
        var lastRunStr = '-';
        if (lastRun) {
            lastRunStr = String(lastRun);
            if (lastRunStr.length > 19) lastRunStr = lastRunStr.substring(0, 19).replace('T', ' ');
        }

        // Format next run
        var nextRunStr = '-';
        if (nextRun && nextRun !== 'pending') {
            nextRunStr = String(nextRun);
            if (nextRunStr.length > 19) nextRunStr = nextRunStr.substring(0, 19).replace('T', ' ');
        } else if (nextRun === 'pending') {
            nextRunStr = 'Beklemede...';
        }

        // Cycle in progress flag
        var cycleActive = !!sched.cycle_in_progress;

        // Cycle state from backend
        var cycleState = sched.cycle_state || 'idle';
        var nextRunMin = sched.next_run_in_minutes;
        var cycleSummary = sched.last_cycle_summary || null;

        // Status label — ürün diliyle
        var statusLabel, statusClass;
        if (!enabled) { statusLabel = 'DEVRE DISI'; statusClass = 'ppd-sched-status-disabled'; }
        else if (cycleState === 'running') { statusLabel = 'ANALIZ DEVAM EDIYOR'; statusClass = 'ppd-sched-status-running'; }
        else if (cycleState === 'waiting') { statusLabel = 'AKTIF'; statusClass = 'ppd-sched-status-running'; }
        else if (cycleState === 'starting') { statusLabel = 'BASLATILIYOR'; statusClass = 'ppd-sched-status-running'; }
        else { statusLabel = 'HAZIR'; statusClass = 'ppd-sched-status-stopped'; }

        // Source type label — dynamic from backend
        var sourceType = sched.source_type || 'mongodb';
        var backendSrcLabels = sched.source_labels || {};
        var sourceLabel = sched.source_label || backendSrcLabels[sourceType] || sourceType;

        // Cycle duration
        var durationStr = '-';
        if (typeof sched.last_cycle_duration_seconds === 'number') {
            durationStr = sched.last_cycle_duration_seconds.toFixed(1) + 's';
        }

        // Next run countdown
        var nextStr = nextRunStr;
        if (cycleState === 'waiting' && typeof nextRunMin === 'number') {
            nextStr = (nextRunMin < 1 ? '<1' : Math.round(nextRunMin)) + ' dk sonra';
        }

        var stats = [
            { label: 'Durum', value: statusLabel, cls: statusClass },
            { label: 'Kaynak', value: sourceLabel, cls: '' },
            { label: 'Calisma', value: String(runCount), cls: '' },
            { label: 'Son Calisma', value: lastRunStr, cls: '' },
            { label: 'Cycle Suresi', value: durationStr, cls: '' }
        ];
        if (running) {
            stats.push({ label: 'Sonraki', value: nextStr, cls: '' });
        }

        // Last cycle summary — compact
        if (cycleSummary && cycleSummary.hosts_analyzed > 0) {
            var sumParts = [];
            sumParts.push(cycleSummary.hosts_analyzed + ' host');
            if (cycleSummary.total_anomalies > 0) sumParts.push(cycleSummary.total_anomalies + ' anomali');
            if (cycleSummary.hosts_errored > 0) sumParts.push(cycleSummary.hosts_errored + ' hata');
            if (cycleSummary.hosts_skipped_cooldown > 0) sumParts.push(cycleSummary.hosts_skipped_cooldown + ' cooldown');
            stats.push({ label: 'Son Cycle', value: sumParts.join(', '), cls: '' });
        }

        var html = '';
        for (var i = 0; i < stats.length; i++) {
            var s = stats[i];
            html += '<div class="ppd-sched-stat">'
                + '<div class="ppd-sched-stat-label">' + esc(s.label) + '</div>'
                + '<div class="ppd-sched-stat-value ' + s.cls + '">' + esc(s.value) + '</div>'
                + '</div>';
        }

        // ── Host-Level Live Status Panel ──
        var hostStates = sched.host_states || {};
        var hostKeys = Object.keys(hostStates);
        var currentHost = sched.current_host || null;

        if (hostKeys.length > 0) {
            var panelTitle = cycleActive ? 'Aktif Cycle — Sunucu Durumu' : 'Sunucu Durumu';
            html += '<div class="ppd-host-live-panel">'
                + '<div class="ppd-host-live-title">' + esc(panelTitle);
            if (cycleActive) {
                html += ' <span class="ppd-host-live-pulse"></span>';
            }
            html += '</div>';

            // Sort: processing first, then queued, completed, cooldown, idle, error
            var stateOrder = { processing: 0, queued: 1, completed: 2, cooldown: 3, idle: 4, error: 5 };
            hostKeys.sort(function (a, b) {
                var sa = stateOrder[hostStates[a].state] || 9;
                var sb = stateOrder[hostStates[b].state] || 9;
                return sa - sb;
            });

            for (var hi = 0; hi < hostKeys.length; hi++) {
                var hName = hostKeys[hi];
                var hState = hostStates[hName] || {};
                var hStateName = hState.state || 'idle';
                var hCls = 'ppd-hls-' + hStateName;
                var isCurrent = (hName === currentHost && hStateName === 'processing');

                // State label & icon
                var stateLabels = {
                    processing: '&#x25B6; Analiz ediliyor',
                    queued: '&#x23F3; Sirada',
                    completed: '&#x2713; Tamamlandi',
                    cooldown: '&#x23F8; Cooldown',
                    idle: '&#x25CB; Bekliyor',
                    error: '&#x2717; Hata'
                };
                var stateLabel = stateLabels[hStateName] || hStateName;

                // Extra info
                var extra = '';
                if (hStateName === 'completed' && typeof hState.anomaly_count === 'number') {
                    extra = hState.anomaly_count + ' anomali';
                } else if (hStateName === 'error' && hState.error) {
                    extra = String(hState.error).substring(0, 60);
                }

                html += '<div class="ppd-host-live-row ' + hCls + (isCurrent ? ' ppd-hls-active' : '') + '">'
                    + '<span class="ppd-hls-name">' + esc(hName) + '</span>'
                    + '<span class="ppd-hls-state">' + stateLabel + '</span>';
                if (extra) {
                    html += '<span class="ppd-hls-extra">' + esc(extra) + '</span>';
                }
                html += '</div>';
            }
            html += '</div>';
        } else {
            // Fallback: last results summary (if any, backward compat)
            var lastResults = sched.last_results_summary || {};
            var resultKeys = Object.keys(lastResults);
            if (resultKeys.length > 0) {
                html += '<div class="ppd-sched-results">'
                    + '<div class="ppd-sched-results-title">Son Cycle Sonuclari</div>';
                for (var ri = 0; ri < resultKeys.length; ri++) {
                    var rHost = resultKeys[ri];
                    var rData = lastResults[rHost] || {};
                    var rStatus = rData.status || 'unknown';
                    var rAnomalies = rData.anomaly_count || 0;
                    var rCls = rStatus === 'completed' ? (rAnomalies > 0 ? 'ppd-sched-result-warn' : 'ppd-sched-result-ok') : 'ppd-sched-result-err';
                    html += '<div class="ppd-sched-result-row ' + rCls + '">'
                        + '<span class="ppd-sched-result-host">' + esc(rHost) + '</span>'
                        + '<span class="ppd-sched-result-badge">'
                        + (rStatus === 'completed' ? rAnomalies + ' anomali' : 'hata')
                        + '</span>'
                        + '</div>';
                }
                html += '</div>';
            }
        }

        // Guidance messages
        if (!enabled) {
            html += '<div class="ppd-sched-guidance">'
                + '<strong>Scheduler devre disi birakildi.</strong> '
                + 'Yukaridaki toggle ile tekrar etkinlestirebilirsiniz. '
                + 'Scheduler kapaliyken prediction yalnizca manuel analizlerden veri alir — '
                + 'bu tahmin kalitesini onemli olcude dusurur.'
                + '<br><em>Production onerisi: Scheduler\'i surekli aktif tutun. '
                + 'Varsayilan ayar aktif olarak gelmektedir.</em>'
                + '</div>';
        } else if (running && runCount > 0) {
            html += '<div class="ppd-sched-guidance ppd-sched-guidance-ok">'
                + '<strong>Scheduler calisiyor.</strong> '
                + 'Her ' + interval + ' dakikada '
                + maxConcurrent + ' sunucu ' + sourceLabel + ' analizi calistirilacak. '
                + 'Otomatik veri biriktirme aktif.'
                + '<br><em>CPU korumali: Host basi cooldown, batch arasi bekleme ve max ' + maxConcurrent + ' esanli analiz.</em>'
                + '</div>';
        } else if (!running) {
            html += '<div class="ppd-sched-guidance">'
                + '<strong>Scheduler aktif ama henuz baslatilmadi.</strong> '
                + '"Baslat" butonuyla baslatabilirsiniz. '
                + 'Her ' + interval + ' dakikada '
                + maxConcurrent + ' sunucu ' + sourceLabel + ' analizi calistirilacak.'
                + '<br><em>CPU korumali: Host basi cooldown, batch arasi bekleme ve max ' + maxConcurrent + ' esanli analiz.</em>'
                + '</div>';
        }

        grid.innerHTML = html;

        // ── Render top activity strip ──
        _renderActivityStrip(sched);

        // Update button states — start available when enabled but not running
        var startBtn = _el('ppdSchedStartBtn');
        var stopBtn = _el('ppdSchedStopBtn');
        var triggerBtn = _el('ppdSchedTriggerBtn');
        if (startBtn) startBtn.disabled = !enabled || running || _schedBusy;
        if (stopBtn) stopBtn.disabled = !running || _schedBusy;
        if (triggerBtn) triggerBtn.disabled = _schedBusy || cycleActive;

        // Update readiness bar
        _renderReadinessBar(_lastTotalChecks, _lastSchedulerRunning);

        // NOT: Host listesi renderSchedulerStatus'tan değil,
        // loadAvailableHosts'tan yönetilir. Scheduler target_hosts
        // genellikle boştur (runtime set edilir), API'den gelen
        // gerçek host listesini ezmemeli.
    }

    // ============================
    // ACTIVITY STRIP (Modal Top Bar)
    // ============================
    function _renderActivityStrip(sched) {
        var strip = _el('ppsActivityStrip');
        if (!strip) return;

        var enabled = !!sched.enabled;
        var running = !!sched.running;
        var cycleActive = !!sched.cycle_in_progress;
        var currentHost = sched.current_host || null;
        var sourceType = sched.source_type || 'mongodb';
        var targetHosts = sched.target_hosts || [];
        var hostStates = sched.host_states || {};
        var hostKeys = Object.keys(hostStates);
        var runCount = sched.run_count || 0;

        if (!enabled) { strip.style.display = 'none'; return; }
        strip.style.display = '';

        // Dot
        var dot = _el('ppsActivityDot');
        if (dot) {
            dot.className = 'pps-activity-dot';
            if (cycleActive) dot.classList.add('pps-dot-active');
            else if (running) dot.classList.add('pps-dot-running');
            else dot.classList.add('pps-dot-idle');
        }

        // Label
        var label = _el('ppsActivityLabel');
        if (label) {
            if (cycleActive) label.textContent = 'Analiz devam ediyor';
            else if (running) label.textContent = 'Scheduler aktif';
            else label.textContent = 'Scheduler hazir';
        }

        // Source — use backend-provided label dynamically
        var srcEl = _el('ppsActivitySource');
        if (srcEl) {
            var backendLabels = sched.source_labels || {};
            srcEl.textContent = sched.source_label || backendLabels[sourceType] || sourceType;
        }

        // Host count — prefer backend-provided count
        var countEl = _el('ppsActivityHostsCount');
        if (countEl) {
            var hCount = sched.host_count || targetHosts.length || hostKeys.length;
            countEl.textContent = hCount > 0 ? hCount + ' sunucu' : '';
        }

        // Host chips
        var hostsContainer = _el('ppsActivityHosts');
        if (!hostsContainer) return;

        if (hostKeys.length === 0) {
            hostsContainer.innerHTML = '';
            return;
        }

        var stateOrder = { processing: 0, queued: 1, completed: 2, cooldown: 3, idle: 4, error: 5 };
        hostKeys.sort(function (a, b) {
            var sa = stateOrder[hostStates[a].state] || 9;
            var sb = stateOrder[hostStates[b].state] || 9;
            return sa - sb;
        });

        var stateLabels = {
            processing: 'Analiz ediliyor',
            queued: 'Sirada',
            completed: 'Tamamlandi',
            cooldown: 'Bekleniyor',
            idle: 'Bekliyor',
            error: 'Hata'
        };

        var chipHtml = '';
        for (var i = 0; i < hostKeys.length; i++) {
            var hName = hostKeys[i];
            var hInfo = hostStates[hName] || {};
            var hState = hInfo.state || 'idle';
            var sLabel = stateLabels[hState] || hState;
            var shortName = hName.length > 22 ? hName.substring(0, 20) + '..' : hName;

            // Extra info for completed
            var extraHtml = '';
            if (hState === 'completed' && typeof hInfo.anomaly_count === 'number') {
                extraHtml = ' <span class="pps-activity-host-extra">' + hInfo.anomaly_count + ' anomali</span>';
            } else if (hState === 'error' && hInfo.error) {
                extraHtml = ' <span class="pps-activity-host-extra">' + esc(String(hInfo.error).substring(0, 40)) + '</span>';
            }

            chipHtml += '<span class="pps-activity-host pps-activity-host-' + hState + '">'
                + '<span class="pps-activity-host-dot"></span>'
                + '<strong>' + esc(shortName) + '</strong>'
                + ' <span class="pps-activity-host-state">' + esc(sLabel) + '</span>'
                + extraHtml
                + '</span>';
        }
        hostsContainer.innerHTML = chipHtml;
    }

    // ============================
    // HOST CHECKBOX LIST
    // ============================
    function _renderHostCheckboxes(hosts) {
        var container = _el('ppsHostsList');
        if (!container) return;

        // Update count badge
        var countBadge = _el('ppsHostsCount');

        if (hosts.length === 0) {
            if (countBadge) countBadge.textContent = '0';
            var st = _getSourceType() || 'mongodb';
            var sourceLabel = { mongodb: 'MongoDB', mssql: 'MSSQL', elasticsearch: 'Elasticsearch' }[st] || st;
            container.innerHTML = '<span class="pps-hosts-empty">'
                + sourceLabel + ' icin aktif sunucu bulunamadi. '
                + 'Son 24 saatte log gonderimi olan sunucular burada listelenir. '
                + 'Farkli bir veri kaynagi secmeyi deneyin.</span>';
            return;
        }

        if (countBadge) countBadge.textContent = hosts.length;

        var html = '';
        for (var i = 0; i < hosts.length; i++) {
            var id = 'ppsHost_' + i;
            html += '<label class="pps-host-item pps-host-checked" for="' + id + '" title="' + esc(hosts[i]) + '">'
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
            btn.textContent = allSelected ? 'Temizle' : 'Tumu Sec';
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
    // SCHEDULER ENABLE/DISABLE TOGGLE
    // ============================
    function _initSchedEnableToggle() {
        var check = _el('ppsSchedEnableCheck');
        if (!check) return;
        check.addEventListener('change', function () {
            var newEnabled = check.checked;
            _postSchedulerConfig({ enabled: newEnabled },
                newEnabled ? 'Scheduler etkinlestirildi' : 'Scheduler devre disi birakildi');
        });
    }

    // ============================
    // SCHEDULER INTERVAL CHANGE
    // ============================
    function _initSchedIntervalChange() {
        var sel = _el('ppsSchedIntervalSelect');
        if (!sel) return;
        sel.addEventListener('change', function () {
            var minutes = parseInt(sel.value, 10);
            if (!minutes || minutes < 5) return;
            _postSchedulerConfig({ interval_minutes: minutes },
                'Scheduler araligi ' + minutes + ' dk olarak ayarlandi');
        });
    }

    // ============================
    // HOST SEARCH FILTER
    // ============================
    function _initHostSearch() {
        var input = _el('ppsHostsSearch');
        if (!input) return;
        input.addEventListener('input', function () {
            var query = input.value.toLowerCase().trim();
            var container = _el('ppsHostsList');
            if (!container) return;
            var items = container.querySelectorAll('.pps-host-item');
            for (var i = 0; i < items.length; i++) {
                var label = items[i].querySelector('.pps-host-item-label');
                var text = label ? label.textContent.toLowerCase() : '';
                items[i].style.display = (!query || text.indexOf(query) !== -1) ? '' : 'none';
            }
        });
    }

    function _postSchedulerConfig(body, successMsg) {
        var base = window.API_ENDPOINTS ? window.API_ENDPOINTS['schedulerConfigure'] : null;
        if (!base) return;

        body.api_key = window.apiKey || '';
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
        })
        .catch(function (err) {
            _schedBusy = false;
            _updateSchedButtons();
            console.error('[PredictionDashboard] Scheduler config error:', err);
        });
    }

    // ============================
    // SCHEDULER FEEDBACK BANNER
    // ============================
    var _feedbackTimer = null;

    function _showSchedFeedback(type, html, autoDismiss) {
        var el = _el('ppsSchedFeedback');
        if (!el) return;
        if (_feedbackTimer) { clearTimeout(_feedbackTimer); _feedbackTimer = null; }
        el.className = 'pps-sched-feedback pps-sched-feedback-' + type;
        el.innerHTML = html;
        el.style.display = '';
        if (autoDismiss !== false) {
            var ms = (typeof autoDismiss === 'number') ? autoDismiss : 6000;
            _feedbackTimer = setTimeout(function () {
                el.style.display = 'none';
                _feedbackTimer = null;
            }, ms);
        }
    }

    function _hideSchedFeedback() {
        var el = _el('ppsSchedFeedback');
        if (el) el.style.display = 'none';
        if (_feedbackTimer) { clearTimeout(_feedbackTimer); _feedbackTimer = null; }
    }

    // ============================
    // PROGRESS STEPPER
    // ============================
    var _progressSteps = [
        { key: 'connect', label: 'Baglanti', icon: '&#9679;' },
        { key: 'analyze', label: 'Analiz', icon: '&#9679;' },
        { key: 'predict', label: 'Tahmin', icon: '&#9679;' },
        { key: 'done',    label: 'Tamam', icon: '&#10003;' }
    ];

    function _showProgress(activeKey) {
        var wrap = _el('ppsSchedProgress');
        var fill = _el('ppsSchedProgressFill');
        var stepsEl = _el('ppsSchedProgressSteps');
        if (!wrap || !fill || !stepsEl) return;

        var activeIdx = -1;
        for (var i = 0; i < _progressSteps.length; i++) {
            if (_progressSteps[i].key === activeKey) { activeIdx = i; break; }
        }

        // Progress bar percentage
        var pct = activeIdx >= 0 ? Math.round(((activeIdx + 1) / _progressSteps.length) * 100) : 0;
        if (activeKey === 'done') pct = 100;
        fill.style.width = pct + '%';

        // Pulse effect if not done
        if (activeKey !== 'done' && activeKey !== 'error') {
            fill.classList.add('pps-progress-pulse');
        } else {
            fill.classList.remove('pps-progress-pulse');
        }

        // Render steps
        var html = '';
        for (var j = 0; j < _progressSteps.length; j++) {
            var s = _progressSteps[j];
            var cls = 'pps-sched-step';
            if (j < activeIdx) cls += ' pps-step-done';
            else if (j === activeIdx) cls += ' pps-step-active';
            html += '<div class="' + cls + '">'
                + '<span class="pps-sched-step-icon">' + s.icon + '</span>'
                + s.label + '</div>';
        }
        stepsEl.innerHTML = html;
        wrap.style.display = '';
    }

    function _hideProgress() {
        var wrap = _el('ppsSchedProgress');
        if (wrap) wrap.style.display = 'none';
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
        var selectedHosts = _getSelectedHosts();
        var sourceType = _getSourceType() || 'mongodb';
        var intervalSel = _el('ppsSchedIntervalSelect');
        var interval = intervalSel ? parseInt(intervalSel.value, 10) : 30;
        var sourceLabel = { mongodb: 'MongoDB', mssql: 'MSSQL', elasticsearch: 'Elasticsearch' }[sourceType] || sourceType;
        var hostDesc = selectedHosts.length > 0 ? selectedHosts.length + ' sunucu' : 'Tum sunucular';

        var msg = 'Periyodik anomaly analizi baslatilacak.\n'
            + 'Kaynak: ' + sourceLabel + '\n'
            + 'Aralik: ' + interval + ' dk\n'
            + 'Hedef: ' + hostDesc
            + '\nDevam etmek istiyor musunuz?';

        _showConfirm('Scheduler Baslat', msg, function () {
            _showSchedFeedback('info',
                '<strong>Scheduler baslatiliyor...</strong>'
                + '<div class="pps-sched-feedback-detail">'
                + sourceLabel + ' &middot; ' + interval + ' dk &middot; ' + hostDesc
                + '</div>', false);

            var body = {
                api_key: window.apiKey || '',
                source_type: sourceType,
                interval_minutes: interval
            };
            if (selectedHosts.length > 0) body.target_hosts = selectedHosts;

            var base = window.API_ENDPOINTS ? window.API_ENDPOINTS['schedulerStart'] : null;
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
                if (data.scheduler) renderSchedulerStatus(data.scheduler);

                if (data.status === 'success') {
                    _showSchedFeedback('success',
                        '<strong>Scheduler baslatildi</strong>'
                        + '<div class="pps-sched-feedback-detail">'
                        + sourceLabel + ' &middot; Her ' + interval + ' dk &middot; ' + hostDesc
                        + '</div>', 8000);
                } else {
                    _showSchedFeedback('warning',
                        '<strong>Scheduler zaten calisiyor veya devre disi</strong>'
                        + '<div class="pps-sched-feedback-detail">Durumu kontrol edin.</div>');
                }
                loadSchedulerStatus();
                setTimeout(function () { refreshAll(); }, 1500);
            })
            .catch(function (err) {
                _schedBusy = false;
                _updateSchedButtons();
                _showSchedFeedback('error',
                    '<strong>Baslatilamadi</strong>'
                    + '<div class="pps-sched-feedback-detail">' + esc(String(err)) + '</div>');
            });
        });
    }

    function stopScheduler() {
        _showConfirm(
            'Scheduler Durdur',
            'Periyodik analiz durdurulacak. Devam etmek istiyor musunuz?',
            function () {
                _showSchedFeedback('info', '<strong>Scheduler durduruluyor...</strong>', false);

                var base = window.API_ENDPOINTS ? window.API_ENDPOINTS['schedulerStop'] : null;
                if (!base) return;

                _schedBusy = true;
                _updateSchedButtons();

                fetch(base, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ api_key: window.apiKey || '' })
                })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    _schedBusy = false;
                    if (data.scheduler) renderSchedulerStatus(data.scheduler);
                    _showSchedFeedback('success', '<strong>Scheduler durduruldu</strong>');
                    loadSchedulerStatus();
                })
                .catch(function (err) {
                    _schedBusy = false;
                    _updateSchedButtons();
                    _showSchedFeedback('error',
                        '<strong>Durdurulamadi</strong>'
                        + '<div class="pps-sched-feedback-detail">' + esc(String(err)) + '</div>');
                });
            }
        );
    }

    function triggerScheduler() {
        var serverVal = (_el('ppdServerFilter') || {}).value || '';
        var selectedHosts = _getSelectedHosts();
        var sourceType = _getSourceType() || 'mongodb';
        var sourceLabel = { mongodb: 'MongoDB', mssql: 'MSSQL', elasticsearch: 'Elasticsearch' }[sourceType] || sourceType;

        var targetDesc;
        if (serverVal) {
            targetDesc = '"' + serverVal + '"';
        } else if (selectedHosts.length > 0) {
            targetDesc = selectedHosts.length + ' secili sunucu';
        } else {
            targetDesc = 'tum hedef sunucular';
        }

        var msg = 'Manuel analiz ' + targetDesc + ' icin tetiklenecek.\n'
            + 'Kaynak: ' + sourceLabel + '\nDevam?';

        _showConfirm('Manuel Calistir', msg, function () {
            var body = {
                api_key: window.apiKey || '',
                source_type: sourceType
            };
            if (serverVal) {
                body.server_name = serverVal;
            } else if (selectedHosts.length > 0) {
                body.target_hosts = selectedHosts;
            }

            // Show progress stepper + feedback
            _showProgress('connect');
            _showSchedFeedback('info',
                '<strong>Manuel analiz baslatiliyor...</strong>'
                + '<div class="pps-sched-feedback-detail">'
                + sourceLabel + ' &middot; ' + targetDesc + '</div>', false);

            var triggerBtn = _el('ppdSchedTriggerBtn');
            var origText = triggerBtn ? triggerBtn.textContent : '';
            if (triggerBtn) {
                triggerBtn.disabled = true;
                triggerBtn.textContent = 'Calisiyor...';
            }

            _schedBusy = true;
            var base = window.API_ENDPOINTS ? window.API_ENDPOINTS['schedulerTrigger'] : null;
            if (!base) return;

            // Step 2: Analyzing
            setTimeout(function () { _showProgress('analyze'); }, 800);

            fetch(base, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            })
            .then(function (r) {
                // Step 3: Prediction phase
                _showProgress('predict');
                return r.json();
            })
            .then(function (data) {
                _schedBusy = false;
                var result = data.result || {};
                var hostsAnalyzed = result.hosts_analyzed || 0;
                var totalAnomalies = result.total_anomalies || 0;

                // Step 4: Done
                _showProgress('done');

                if (data.status === 'busy') {
                    // Host is being analyzed by scheduler
                    _showSchedFeedback('warning',
                        '<strong>Sunucu mesgul</strong>'
                        + '<div class="pps-sched-feedback-detail">'
                        + esc(data.message || 'Scheduler su an bu sunucu uzerinde calisiyor')
                        + '</div>');
                    _hideProgress();
                    if (triggerBtn) {
                        triggerBtn.textContent = origText;
                        triggerBtn.disabled = false;
                    }
                    return;
                }

                if (result.status === 'completed') {
                    _showSchedFeedback('success',
                        '<strong>Analiz tamamlandi</strong>'
                        + '<div class="pps-sched-feedback-detail">'
                        + hostsAnalyzed + ' host analiz edildi &middot; '
                        + totalAnomalies + ' anomali bulundu'
                        + '</div>', 10000);
                } else if (result.status === 'skipped') {
                    var reason = (result.reason || '').replace(/_/g, ' ');
                    _showSchedFeedback('warning',
                        '<strong>Analiz atlandi</strong>'
                        + '<div class="pps-sched-feedback-detail">' + esc(reason) + '</div>');
                } else {
                    _showSchedFeedback('success', '<strong>Islem tamamlandi</strong>');
                }

                if (triggerBtn) {
                    if (result.status === 'completed') {
                        triggerBtn.textContent = hostsAnalyzed + ' host, ' + totalAnomalies + ' anomali';
                        triggerBtn.classList.add('ppd-sched-btn-success');
                    } else {
                        triggerBtn.textContent = 'Tamamlandi';
                    }
                    setTimeout(function () {
                        triggerBtn.textContent = origText;
                        triggerBtn.disabled = false;
                        triggerBtn.classList.remove('ppd-sched-btn-success');
                    }, 4000);
                }

                // Hide progress after a delay
                setTimeout(function () { _hideProgress(); }, 8000);

                if (data.scheduler) renderSchedulerStatus(data.scheduler);
                setTimeout(function () { refreshAll(); }, 1000);
                console.log('[PredictionDashboard] Trigger completed', data);
            })
            .catch(function (err) {
                _schedBusy = false;
                _hideProgress();
                _showSchedFeedback('error',
                    '<strong>Manuel analiz hatasi</strong>'
                    + '<div class="pps-sched-feedback-detail">' + esc(String(err)) + '</div>');

                if (triggerBtn) {
                    triggerBtn.textContent = 'Hata!';
                    setTimeout(function () {
                        triggerBtn.textContent = origText;
                        triggerBtn.disabled = false;
                    }, 3000);
                }
                console.error('[PredictionDashboard] Trigger error:', err);
            });
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

            // Show progress stepper
            _showProgress('connect');
            _showSchedFeedback('info',
                '<strong>Analiz baslatiliyor...</strong>'
                + '<div class="pps-sched-feedback-detail">'
                + sourceLabel + (serverVal ? ' &middot; ' + esc(serverVal) : '')
                + '</div>', false);

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
                _hideProgress();
                _hideSchedFeedback();
                return;
            }

            // Step 2: Analyzing
            setTimeout(function () { _showProgress('analyze'); }, 600);

            fetch(base, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            })
            .then(function (r) {
                _showProgress('predict');
                if (!r.ok) throw new Error('HTTP ' + r.status + ': ' + r.statusText);
                return r.json();
            })
            .then(function (data) {
                _showProgress('done');
                btn.classList.remove('pps-run-busy');

                if (data.status === 'error') {
                    btn.classList.add('pps-run-error');
                    btn.innerHTML = '<span class="pps-run-icon">&#x26A0;</span> ' + esc(data.message || 'Hata');
                    _showSchedFeedback('error',
                        '<strong>Analiz hatasi</strong>'
                        + '<div class="pps-sched-feedback-detail">' + esc(data.message || 'Bilinmeyen hata') + '</div>');
                    setTimeout(function () {
                        btn.disabled = false;
                        btn.innerHTML = origText;
                        btn.classList.remove('pps-run-error');
                        _hideProgress();
                    }, 3000);
                    return;
                }

                if (data.status === 'success') {
                    btn.classList.add('pps-run-success');
                    var summary = data.analysis_summary || {};
                    var anomalies = summary.n_anomalies || 0;
                    var rate = (summary.anomaly_rate || 0).toFixed(1);

                    // Build rich result text
                    var resultParts = [];
                    // Show server and source context
                    var resServer = data.server_name || serverVal;
                    if (resServer && resServer !== 'global') {
                        resultParts.push(resServer);
                    }
                    resultParts.push(anomalies + ' anomali (%' + rate + ')');

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

                    _showSchedFeedback('success',
                        '<strong>Analiz tamamlandi</strong>'
                        + '<div class="pps-sched-feedback-detail">'
                        + anomalies + ' anomali (%' + rate + ')'
                        + (insight.risk_level && insight.risk_level !== 'OK' ? ' &middot; Risk: ' + esc(insight.risk_level) : '')
                        + '</div>', 10000);
                    console.log('[PredictionDashboard] Analysis completed', data);
                } else {
                    btn.classList.add('pps-run-success');
                    btn.innerHTML = '<span class="pps-run-icon">&#x2714;</span> Tamamlandi';
                    _showSchedFeedback('success', '<strong>Islem tamamlandi</strong>');
                    console.log('[PredictionDashboard] Analysis triggered', data);
                }

                loadSchedulerStatus();
                // Refresh prediction panels with fresh data
                refreshAll();
                setTimeout(function () {
                    btn.disabled = false;
                    btn.innerHTML = origText;
                    btn.classList.remove('pps-run-success');
                    _hideProgress();
                }, 4000);
            })
            .catch(function (err) {
                btn.classList.remove('pps-run-busy');
                btn.classList.add('pps-run-error');
                btn.innerHTML = '<span class="pps-run-icon">&#x26A0;</span> Hata';
                _hideProgress();
                _showSchedFeedback('error',
                    '<strong>Analiz hatasi</strong>'
                    + '<div class="pps-sched-feedback-detail">' + esc(String(err)) + '</div>');
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

        // Scheduler enable toggle
        _initSchedEnableToggle();
        // Scheduler interval change
        _initSchedIntervalChange();
        // Host search filter
        _initHostSearch();

        // Source toggle + host select all
        _initSourceToggle();
        _initHostSelectAll();

        // Guide panel toggle
        _initGuidePanel();

        // Overlay starts hidden (via inline style="display:none")
        console.log('Prediction Studio initialized (modal overlay mode)');
    }

    // ============================
    // GUIDE PANEL TOGGLE
    // ============================
    function _initGuidePanel() {
        var toggle = _el('ppdGuideToggle');
        if (!toggle) return;
        // Restore collapsed state from localStorage
        try {
            _guideCollapsed = localStorage.getItem('ppd_guide_collapsed') === '1';
        } catch (e) { /* ignore */ }
        _applyGuideState();

        toggle.addEventListener('click', function () {
            _guideCollapsed = !_guideCollapsed;
            _applyGuideState();
            try { localStorage.setItem('ppd_guide_collapsed', _guideCollapsed ? '1' : '0'); } catch (e) { /* */ }
        });
    }

    function _applyGuideState() {
        var panel = _el('ppdGuidePanel');
        if (!panel) return;
        if (_guideCollapsed) {
            panel.classList.add('ppd-guide-collapsed');
        } else {
            panel.classList.remove('ppd-guide-collapsed');
        }
    }

    // ============================
    // PREDICTION READINESS INDICATOR
    // ============================
    function _renderReadinessBar(historyCount, schedulerRunning) {
        var container = _el('ppdReadinessBar');
        if (!container) return;

        // Calculate readiness: 0-100
        // Tier thresholds: 5 = Tier1, 10 = Tier2, 20 = Tier3
        var tier = 'Tier 0';
        var pct = 0;
        var text = '';
        if (historyCount >= 20) {
            tier = 'Tier 3 — EWMA';
            pct = 100;
            text = historyCount + ' analiz — en guclu tahmin kalitesi';
        } else if (historyCount >= 10) {
            tier = 'Tier 2 — Linear Regression';
            pct = 60 + ((historyCount - 10) / 10) * 40;
            text = historyCount + '/20 analiz — ' + (20 - historyCount) + ' analiz daha → Tier 3';
        } else if (historyCount >= 5) {
            tier = 'Tier 1 — WMA';
            pct = 30 + ((historyCount - 5) / 5) * 30;
            text = historyCount + '/20 analiz — ' + (20 - historyCount) + ' analiz daha → Tier 3';
        } else if (historyCount >= 1) {
            tier = 'Tier 0 — Yon Gostergesi';
            pct = (historyCount / 5) * 30;
            text = historyCount + '/5 analiz — ' + (5 - historyCount) + ' analiz daha → Tier 1';
        } else {
            text = 'Hic analiz verisi yok — baslatin';
            pct = 0;
        }

        var fillCls = 'ppd-readiness-fill-low';
        if (pct >= 60) fillCls = 'ppd-readiness-fill-high';
        else if (pct >= 30) fillCls = 'ppd-readiness-fill-medium';

        var schedIcon = schedulerRunning
            ? '<span title="Scheduler calisiyor" style="color:#4caf50;margin-left:6px;">&#x25CF; Scheduler aktif</span>'
            : '<span title="Scheduler kapali" style="color:#ff9800;margin-left:6px;">&#x25CB; Scheduler kapali</span>';

        // Tier milestone markers
        var milestones = '<div class="ppd-readiness-milestones">'
            + '<span class="ppd-readiness-ms' + (historyCount >= 5 ? ' ppd-readiness-ms-done' : '') + '">T1:5</span>'
            + '<span class="ppd-readiness-ms' + (historyCount >= 10 ? ' ppd-readiness-ms-done' : '') + '">T2:10</span>'
            + '<span class="ppd-readiness-ms' + (historyCount >= 20 ? ' ppd-readiness-ms-done' : '') + '">T3:20</span>'
            + '</div>';

        // Scheduling guidance when not running and not at full power
        var guidance = '';
        if (!schedulerRunning && historyCount < 20) {
            var interval30 = 30;
            var remaining = 20 - historyCount;
            var hoursToTier3 = Math.ceil(remaining * interval30 / 60);
            guidance = '<div class="ppd-readiness-guidance">'
                + 'Onerilen: Scheduler\'i aktif edin. '
                + '30 dk aralikla ~' + hoursToTier3 + ' saatte Tier 3\'e ulasilir. '
                + 'Surekli calisma tahmin kalitesini onemli olcude arttirir.'
                + '</div>';
        }

        container.innerHTML = '<span class="ppd-readiness-label">Tahmin Kalitesi: ' + esc(tier) + '</span>'
            + '<div class="ppd-readiness-track"><div class="ppd-readiness-fill ' + fillCls + '" style="width:' + pct.toFixed(0) + '%"></div></div>'
            + milestones
            + '<span class="ppd-readiness-text">' + esc(text) + schedIcon + '</span>'
            + guidance;
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
        triggerScheduler: triggerScheduler,
        renderReadiness: _renderReadinessBar
    };

    // Backward compat globals
    window.togglePredictionDashboard = toggleDashboard;

    console.log('Prediction Dashboard module loaded successfully');

})();
