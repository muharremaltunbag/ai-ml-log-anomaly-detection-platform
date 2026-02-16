// web_ui/static/script-ml-panel.js
/**
 * ML Model Panel Management Module
 * ML Metrics Sidebar gorünürlüğü ve veri yönetimi
 *
 * GUNCELLENDİ: Figma sidebar layout'una uyarlandı.
 * - showMLPanel / hideMLPanel artık CSS class 'open' ile çalışıyor
 * - Yeni element ID'leri (mlServerName, mlModelType, vb.) destekleniyor
 * - /api/ml/model-info endpoint'i de çekilip sidebar'a yansitiliyor
 * - Feature listesi dinamik render ediliyor (lastAnomalyResult'tan)
 * - Backward compatibility (window.showMLPanel vb.) korunuyor
 */

(function() {
    'use strict';

    console.log('🤖 Loading script-ml-panel.js...');

    /**
     * ML Panel'i initialize et
     */
    function initializeMLPanel() {
        console.log('Initializing ML Panel (sidebar mode)...');

        // Close butonu event listener
        var closeBtn = document.getElementById('mlSidebarCloseBtn');
        if (closeBtn) {
            closeBtn.addEventListener('click', hideMLPanel);
        }

        // Validate log butonu
        var validateBtn = document.getElementById('validateLogBtn');
        if (validateBtn) {
            validateBtn.addEventListener('click', handleLogValidation);
        }

        // Eğer API zaten bağlıysa metrikleri yükle
        if (window.isConnected) {
            console.log('API already connected, loading ML metrics...');
            loadMLMetrics();
        }

        console.log('✅ ML Panel initialized (sidebar mode)');
    }

    /**
     * ML Sidebar'i göster (CSS class toggle — LCWGPT ile aynı mantık)
     */
    function showMLPanel() {
        var panel = document.getElementById('mlModelPanel');
        if (panel) {
            panel.classList.add('open');
            console.log('✅ ML Sidebar opened');

            // Metrikleri yükle
            loadMLMetrics();
        }
    }

    /**
     * ML Sidebar'i gizle
     */
    function hideMLPanel() {
        var panel = document.getElementById('mlModelPanel');
        if (panel) {
            panel.classList.remove('open');
            console.log('ML Sidebar closed');
        }
    }

    /**
     * ML Sidebar'i toggle et (aç/kapat)
     */
    function toggleMLPanel() {
        var panel = document.getElementById('mlModelPanel');
        if (!panel) return;

        if (panel.classList.contains('open')) {
            hideMLPanel();
        } else {
            showMLPanel();
        }
    }

    /**
     * ML Model metriklerini yükle ve sidebar'ı güncelle
     * İki endpoint çağrılır: /api/ml/metrics + /api/ml/model-info
     */
    async function loadMLMetrics() {
        console.log('Loading ML metrics for sidebar...');

        // 1) /api/ml/metrics — performans + istatistik
        try {
            var response = await fetch('/api/ml/metrics?api_key=' + encodeURIComponent(window.apiKey));
            if (response.ok) {
                var data = await response.json();
                if (data.status === 'success' && data.metrics) {
                    var metrics = data.metrics;

                    // Model Performansı — ID-based update
                    updateElement('modelAccuracy', '%' + metrics.model_accuracy.toFixed(1));
                    updateElement('modelF1', metrics.f1_score.toFixed(2));
                    updateElement('modelPrecision', metrics.precision.toFixed(2));
                    updateElement('modelRecall', metrics.recall.toFixed(2));

                    // Anomali İstatistikleri — ID-based update
                    updateElement('totalLogs', metrics.total_logs_analyzed.toLocaleString('tr-TR'));
                    updateElement('detectedAnomalies', metrics.total_anomalies_detected.toLocaleString('tr-TR'));
                    updateElement('anomalyRate', '%' + metrics.anomaly_rate.toFixed(2));

                    // Model versiyonu ve eğitim tarihi
                    updateElement('modelVersion', metrics.model_version);
                    updateElement('lastTrainingDate', new Date(metrics.last_training_date).toLocaleDateString('tr-TR'));

                    console.log('✅ ML metrics loaded from /api/ml/metrics');
                }
            }
        } catch (error) {
            console.error('Error loading ML metrics:', error);
            updateMLPanelWithDefaults();
        }

        // 2) /api/ml/model-info — model detay bilgileri
        try {
            var infoResponse = await fetch('/api/ml/model-info?api_key=' + encodeURIComponent(window.apiKey));
            if (infoResponse.ok) {
                var infoData = await infoResponse.json();
                if (infoData.status === 'success' && infoData.model_info) {
                    var info = infoData.model_info;

                    updateElement('mlModelType', info.model_type || 'Isolation Forest');
                    updateElement('mlTrainingSamples', info.training_samples ? info.training_samples.toLocaleString('tr-TR') + ' Satir' : '--');
                    updateElement('mlFeatureCount', info.features_count ? info.features_count.toString() : '--');

                    if (info.buffer_samples !== undefined) {
                        var bufferMB = info.buffer_size_mb ? info.buffer_size_mb.toFixed(1) + ' MB' : '';
                        updateElement('mlBufferInfo', info.buffer_samples.toLocaleString('tr-TR') + (bufferMB ? ' / ' + bufferMB : ''));
                    }

                    console.log('✅ Model info loaded from /api/ml/model-info');
                }
            }
        } catch (error) {
            console.warn('Could not load model info:', error);
        }

        // 3) lastAnomalyResult varsa, onunla üzerine yaz (en güncel veri)
        if (window.lastAnomalyResult && window.lastAnomalyResult.sonuç) {
            var result = window.lastAnomalyResult.sonuç;
            var summary = result.summary || (result.data ? result.data.summary : null) || {};

            if (summary.n_anomalies !== undefined) {
                updateElement('detectedAnomalies', summary.n_anomalies.toLocaleString('tr-TR'));
            }
            if (summary.anomaly_rate !== undefined) {
                updateElement('anomalyRate', '%' + summary.anomaly_rate.toFixed(2));
            }
            if (summary.total_logs !== undefined) {
                updateElement('totalLogs', summary.total_logs.toLocaleString('tr-TR'));
            }

            // Sunucu adı — storage_info veya analysis metadata'dan
            var serverName = null;
            if (result.storage_info && result.storage_info.host) {
                serverName = result.storage_info.host;
            } else if (window.lastAnomalyResult.storage_info && window.lastAnomalyResult.storage_info.host) {
                serverName = window.lastAnomalyResult.storage_info.host;
            } else if (window.selectedChatServer) {
                serverName = window.selectedChatServer;
            }
            if (serverName) {
                updateElement('mlServerName', serverName.split('.')[0]);
            }

            // Model info from analysis result
            var mlData = result.data || result;
            var modelInfo = result.model_info || mlData.model_info || {};
            if (modelInfo.model_version) {
                updateElement('modelVersion', modelInfo.model_version);
            }
            if (modelInfo.feature_count) {
                updateElement('mlFeatureCount', modelInfo.feature_count.toString());
            }

            // Feature importance varsa, feature listesini dinamik guncelle
            var featureImportance = mlData.feature_importance || {};
            if (Object.keys(featureImportance).length > 0) {
                renderDynamicFeatures(featureImportance);
            }

            console.log('✅ ML sidebar updated from lastAnomalyResult');
        }
    }

    /**
     * Analiz sonucundan metrikleri güncelle (backward compat)
     */
    function updateMetricsFromAnalysis(summary) {
        var accuracy = summary.anomaly_rate ? (100 - summary.anomaly_rate).toFixed(1) : '95.2';
        var f1Score = summary.f1_score || '0.89';
        var precision = summary.precision || '0.92';
        var recall = summary.recall || '0.87';

        updateElement('modelAccuracy', '%' + accuracy);
        updateElement('modelF1', f1Score);
        updateElement('modelPrecision', precision);
        updateElement('modelRecall', recall);

        updateElement('totalLogs', (summary.total_logs || 0).toLocaleString('tr-TR'));
        updateElement('detectedAnomalies', (summary.n_anomalies || 0).toLocaleString('tr-TR'));
        updateElement('anomalyRate', '%' + (summary.anomaly_rate || 0).toFixed(2));
    }

    /**
     * ML Panel'i default değerlerle güncelle
     */
    function updateMLPanelWithDefaults() {
        var defaults = {
            modelAccuracy: '%95.2',
            modelF1: '0.89',
            modelPrecision: '0.92',
            modelRecall: '0.87',
            totalLogs: '0',
            detectedAnomalies: '0',
            anomalyRate: '%0.00',
            modelVersion: 'v2.1.0',
            lastTrainingDate: new Date().toLocaleDateString('tr-TR'),
            mlServerName: '--',
            mlModelType: 'Isolation Forest',
            mlTrainingSamples: '--',
            mlFeatureCount: '--',
            mlBufferInfo: '--'
        };

        Object.keys(defaults).forEach(function(key) {
            updateElement(key, defaults[key]);
        });

        console.log('✅ ML sidebar updated with default values');
    }

    /**
     * Element'i güncelle (ID-based — yeni DOM yapısı ile uyumlu)
     */
    function updateElement(elementId, value) {
        var element = document.getElementById(elementId);
        if (element) {
            element.textContent = value;
            element.classList.remove('loading');
        }
    }

    /**
     * Feature importance verisinden dinamik feature listesi render et
     * Mevcut statik listeyi korur, sadece importance badge'lerini günceller
     */
    function renderDynamicFeatures(featureImportance) {
        // Kritik feature'lar
        var criticalFeatures = ['is_fatal', 'is_out_of_memory', 'is_shutdown', 'is_memory_limit', 'is_assertion'];
        // Diger feature'lar
        var otherFeatures = ['query_duration_ms', 'docs_examined_count', 'keys_examined_count', 'is_restart',
                             'is_collscan', 'is_index_build', 'is_slow_query', 'is_high_doc_scan', 'is_replication_issue'];

        // Kisa isim mapping (UI icin)
        var shortNames = {
            'is_fatal': 'is_fatal',
            'is_out_of_memory': 'is_out_of_mem',
            'is_shutdown': 'is_shutdown',
            'is_memory_limit': 'is_mem_limit',
            'is_assertion': 'is_assertion',
            'query_duration_ms': 'query_dur',
            'docs_examined_count': 'docs_exam',
            'keys_examined_count': 'keys_exam',
            'is_restart': 'is_restart',
            'is_collscan': 'is_collscan',
            'is_index_build': 'is_idx_build',
            'is_slow_query': 'is_slow_qry',
            'is_high_doc_scan': 'is_hi_scan',
            'is_replication_issue': 'is_repl_iss'
        };

        // Kritik container'i guncelle
        var criticalContainer = document.getElementById('mlCriticalFeatures');
        if (criticalContainer) {
            var criticalHtml = '';
            criticalFeatures.forEach(function(feat) {
                var importance = featureImportance[feat];
                var shortName = shortNames[feat] || feat;
                var isWide = feat === 'is_assertion';
                var isCritical = feat === 'is_fatal' || feat === 'is_out_of_memory' || feat === 'is_shutdown';

                if (importance !== undefined && importance > 0.01) {
                    criticalHtml += '<div class="ml-feature-item' + (isCritical ? ' ml-feature-critical' : '') + (isWide ? ' ml-feature-wide' : '') + '">';
                    criticalHtml += '<span class="ml-feature-name">' + shortName + '</span>';
                    if (isWide) {
                        var level = importance > 0.1 ? 'Yuksek' : 'Normal';
                        criticalHtml += '<span class="ml-feature-badge-warning">' + level + '</span>';
                    } else {
                        var dotClass = isCritical ? 'ml-feature-dot-red' : 'ml-feature-dot-orange';
                        criticalHtml += '<span class="ml-feature-dot ' + dotClass + '"></span>';
                    }
                    criticalHtml += '</div>';
                }
            });
            if (criticalHtml) {
                criticalContainer.innerHTML = criticalHtml;
            }
        }

        // Diger container'i guncelle
        var otherContainer = document.getElementById('mlOtherFeatures');
        if (otherContainer) {
            var otherHtml = '';
            var dotColors = ['ml-feature-dot-blue', 'ml-feature-dot-blue', 'ml-feature-dot-blue', 'ml-feature-dot-purple',
                           'ml-feature-dot-orange', 'ml-feature-dot-blue', 'ml-feature-dot-orange', 'ml-feature-dot-blue', 'ml-feature-dot-purple'];

            otherFeatures.forEach(function(feat, idx) {
                var importance = featureImportance[feat];
                var shortName = shortNames[feat] || feat;

                if (importance !== undefined && importance > 0.005) {
                    var dotClass = dotColors[idx] || 'ml-feature-dot-blue';
                    otherHtml += '<div class="ml-feature-item">';
                    otherHtml += '<span class="ml-feature-name">' + shortName + '</span>';
                    otherHtml += '<span class="ml-feature-dot ' + dotClass + '"></span>';
                    otherHtml += '</div>';
                }
            });
            if (otherHtml) {
                otherContainer.innerHTML = otherHtml;
            }
        }
    }

    /**
     * Canlı log validasyonu (mevcut işlevsellik korunuyor)
     */
    async function handleLogValidation() {
        var input = document.getElementById('sampleLogInput');
        var resultDiv = document.getElementById('validationResult');

        if (!input || !resultDiv) {
            // Fallback: window.elements uzerinden
            input = input || (window.elements ? window.elements.sampleLogInput : null);
            resultDiv = resultDiv || (window.elements ? window.elements.validationResult : null);
        }
        if (!input || !resultDiv) return;

        var logSample = input.value.trim();
        if (!logSample) {
            if (window.showNotification) {
                window.showNotification('Lutfen test edilecek log satirini girin', 'warning');
            }
            return;
        }

        resultDiv.style.display = 'block';
        resultDiv.innerHTML = '<div class="loading">Analiz ediliyor...</div>';

        try {
            var response = await fetch('/api/ml/validate-log', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    api_key: window.apiKey,
                    log_text: logSample
                })
            });

            if (response.ok) {
                var data = await response.json();
                if (data.status === 'success' && data.analysis) {
                    var analysis = data.analysis;
                    var isAnomaly = analysis.is_anomaly;

                    resultDiv.innerHTML =
                        '<div class="validation-result-content ' + (isAnomaly ? 'anomaly' : 'normal') + '">' +
                            '<div class="result-label">' + (isAnomaly ? '⚠️ ANOMALI TESPIT EDILDI' : '✅ NORMAL LOG') + '</div>' +
                            '<div class="result-score">Anomali Skoru: ' + analysis.anomaly_score.toFixed(3) + '</div>' +
                            '<div class="result-severity">Severity: ' + analysis.severity + '</div>' +
                            '<div class="result-details">' + analysis.explanation + '</div>' +
                            (analysis.recommendations && analysis.recommendations.length > 0 ?
                                '<div class="result-recommendations">' +
                                analysis.recommendations.map(function(r) { return '<li>' + r + '</li>'; }).join('') +
                                '</div>' : ''
                            ) +
                        '</div>';

                    console.log('✅ Log validation completed via backend');
                    return;
                }
            }
            throw new Error('Backend validation failed');

        } catch (error) {
            console.error('Validation error:', error);
            var anomalyScore = simulateAnomalyScore(logSample);
            var isAnomaly2 = anomalyScore > 0.5;

            resultDiv.innerHTML =
                '<div class="validation-result-content ' + (isAnomaly2 ? 'anomaly' : 'normal') + '">' +
                    '<div class="result-label">' + (isAnomaly2 ? '⚠️ ANOMALI TESPIT EDILDI (Offline)' : '✅ NORMAL LOG (Offline)') + '</div>' +
                    '<div class="result-score">Anomali Skoru: ' + anomalyScore.toFixed(3) + '</div>' +
                    '<div class="result-details">' +
                        (isAnomaly2 ?
                            'Bu log satiri anormal pattern iceriyor. Detayli analiz icin tam log dosyasini yukleyin.' :
                            'Bu log satiri normal gorunuyor.') +
                    '</div>' +
                '</div>';
        }
    }

    /**
     * Basit anomali skoru simülasyonu (test amaçlı)
     */
    function simulateAnomalyScore(logText) {
        var anomalyKeywords = ['error', 'fatal', 'exception', 'failed', 'crash', 'timeout', 'refused'];
        var lowerLog = logText.toLowerCase();

        var score = 0.1;
        anomalyKeywords.forEach(function(keyword) {
            if (lowerLog.includes(keyword)) {
                score += 0.15;
            }
        });

        return Math.min(score, 0.99);
    }

    /**
     * Panel'i anomali analizi sonrası otomatik güncelle
     */
    function autoUpdatePanelAfterAnalysis(analysisResult) {
        if (!analysisResult || !analysisResult.sonuç) return;

        var summary = analysisResult.sonuç.summary || (analysisResult.sonuç.data ? analysisResult.sonuç.data.summary : null);
        if (summary) {
            updateMetricsFromAnalysis(summary);
            console.log('✅ ML Sidebar auto-updated after analysis');
        }
    }

    // Public API (tüm eski fonksiyonlar + yeniler)
    window.MLPanel = {
        initialize: initializeMLPanel,
        show: showMLPanel,
        hide: hideMLPanel,
        toggle: toggleMLPanel,
        loadMetrics: loadMLMetrics,
        updateWithDefaults: updateMLPanelWithDefaults,
        autoUpdate: autoUpdatePanelAfterAnalysis,
        toggleMinimize: toggleMLPanel  // backward compat: eski toggleMinimize artik toggle yapar
    };

    // Backward compatibility — eski global fonksiyonlar
    window.showMLPanel = showMLPanel;
    window.hideMLPanel = hideMLPanel;
    window.loadMLMetrics = loadMLMetrics;
    window.updateMLPanelWithDefaults = updateMLPanelWithDefaults;
    window.toggleMLPanel = toggleMLPanel;

    console.log('✅ ML Panel module loaded successfully (sidebar mode)');

})();
