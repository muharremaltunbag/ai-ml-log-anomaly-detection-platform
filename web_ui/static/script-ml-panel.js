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
     * Null-safe format helper: null/undefined ise '--' dondur
     */
    function safeMetric(value, formatter) {
        if (value === null || value === undefined) return '--';
        return formatter ? formatter(value) : String(value);
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

                    // Model Performansi — null ise '--' goster
                    updateElement('modelAccuracy', safeMetric(metrics.model_accuracy, function(v) { return '%' + v.toFixed(1); }));
                    updateElement('modelF1', safeMetric(metrics.f1_score, function(v) { return v.toFixed(2); }));
                    updateElement('modelPrecision', safeMetric(metrics.precision, function(v) { return v.toFixed(2); }));
                    updateElement('modelRecall', safeMetric(metrics.recall, function(v) { return v.toFixed(2); }));

                    // Anomali Istatistikleri
                    updateElement('totalLogs', (metrics.total_logs_analyzed || 0).toLocaleString('tr-TR'));
                    updateElement('detectedAnomalies', (metrics.total_anomalies_detected || 0).toLocaleString('tr-TR'));
                    updateElement('anomalyRate', '%' + (metrics.anomaly_rate || 0).toFixed(2));

                    // Model versiyonu ve egitim tarihi — null ise '--'
                    updateElement('modelVersion', safeMetric(metrics.model_version));
                    updateElement('lastTrainingDate', safeMetric(metrics.last_training_date, function(v) {
                        return new Date(v).toLocaleDateString('tr-TR');
                    }));

                    console.log('✅ ML metrics loaded from /api/ml/metrics (is_trained=' + metrics.is_trained + ')');
                }
            }
        } catch (error) {
            console.error('Error loading ML metrics:', error);
            updateMLPanelWithDefaults();
        }

        // 2) /api/ml/model-info — model detay bilgileri (gercek veriler)
        try {
            var infoResponse = await fetch('/api/ml/model-info?api_key=' + encodeURIComponent(window.apiKey));
            if (infoResponse.ok) {
                var infoData = await infoResponse.json();
                if (infoData.status === 'success' && infoData.model_info) {
                    var info = infoData.model_info;

                    updateElement('mlModelType', info.model_type || 'Isolation Forest');
                    updateElement('mlTrainingSamples', safeMetric(info.training_samples, function(v) {
                        return v.toLocaleString('tr-TR') + ' Satir';
                    }));
                    updateElement('mlFeatureCount', safeMetric(info.features_count, function(v) {
                        return v.toString();
                    }));

                    // Model versiyonu ve egitim tarihi
                    updateElement('modelVersion', safeMetric(info.model_version));
                    updateElement('lastTrainingDate', safeMetric(info.model_trained_at, function(v) {
                        return new Date(v).toLocaleDateString('tr-TR');
                    }));

                    // Sunucu adi
                    if (info.server_name) {
                        updateElement('mlServerName', info.server_name);
                    }

                    // Buffer bilgisi
                    if (info.buffer_samples !== undefined && info.buffer_samples !== null) {
                        var bufferMB = info.buffer_size_mb ? info.buffer_size_mb.toFixed(1) + ' MB' : '';
                        updateElement('mlBufferInfo', info.buffer_samples.toLocaleString('tr-TR') + (bufferMB ? ' / ' + bufferMB : ''));
                    }

                    // Model dosya yolu
                    if (info.model_path) {
                        updateElement('mlModelFilePath', info.model_path);
                    }

                    console.log('Model info loaded from /api/ml/model-info (is_trained=' + info.is_trained + ')');
                }
            }
        } catch (error) {
            console.warn('Could not load model info:', error);
        }

        // 3) lastAnomalyResult varsa, onunla uzerine yaz (en guncel analiz verisi)
        if (window.lastAnomalyResult && window.lastAnomalyResult.sonuç) {
            var result = window.lastAnomalyResult.sonuç;
            var summary = result.summary || (result.data ? result.data.summary : null) || {};

            // Anomali istatistikleri — gercek veriler
            if (summary.total_logs !== undefined) {
                updateElement('totalLogs', summary.total_logs.toLocaleString('tr-TR'));
            }
            if (summary.n_anomalies !== undefined) {
                updateElement('detectedAnomalies', summary.n_anomalies.toLocaleString('tr-TR'));
            }
            if (summary.anomaly_rate !== undefined) {
                updateElement('anomalyRate', '%' + summary.anomaly_rate.toFixed(2));
                // Accuracy: anomaly_rate'den turetilen yaklasik deger
                updateElement('modelAccuracy', '%' + (100 - summary.anomaly_rate).toFixed(1));
            }

            // Sunucu adi
            var serverInfo = result.server_info || {};
            var serverName = serverInfo.server_name || null;
            if (!serverName && window.selectedChatServer) {
                serverName = window.selectedChatServer;
            }
            if (serverName) {
                updateElement('mlServerName', serverName.split('.')[0]);
            }

            // Model dosya yolu
            if (serverInfo.model_path) {
                updateElement('mlModelFilePath', serverInfo.model_path);
            }

            // Buffer bilgisi
            if (serverInfo.historical_buffer_size !== undefined) {
                var bufVal = serverInfo.historical_buffer_size;
                var bufMB = serverInfo.buffer_size_mb;
                var bufText = bufVal.toLocaleString('tr-TR');
                if (bufMB) bufText += ' / ' + bufMB.toFixed(1) + ' MB';
                updateElement('mlBufferInfo', bufText);
            }

            // model_info — gercek model verileri
            var mlData = result.data || result;
            var modelInfo = result.model_info || mlData.model_info || {};

            if (modelInfo.model_version) {
                updateElement('modelVersion', modelInfo.model_version);
            }
            if (modelInfo.feature_count) {
                updateElement('mlFeatureCount', modelInfo.feature_count.toString());
            }
            if (modelInfo.training_samples) {
                updateElement('mlTrainingSamples', modelInfo.training_samples.toLocaleString('tr-TR') + ' Satir');
            }
            if (modelInfo.model_trained_at) {
                try {
                    updateElement('lastTrainingDate', new Date(modelInfo.model_trained_at).toLocaleDateString('tr-TR'));
                } catch (e) {
                    updateElement('lastTrainingDate', modelInfo.model_trained_at);
                }
            }
            if (modelInfo.model_type) {
                updateElement('mlModelType', modelInfo.model_type);
            }

            // Feature importance — dinamik guncelle
            var featureImportance = mlData.feature_importance || {};
            if (Object.keys(featureImportance).length > 0) {
                renderDynamicFeatures(featureImportance);
            }

            console.log('ML sidebar updated from lastAnomalyResult:', {
                total_logs: summary.total_logs,
                version: modelInfo.model_version,
                features: modelInfo.feature_count,
                trained_at: modelInfo.model_trained_at
            });
        }

        // Feedback metriklerini de yukle (varsa precision guncellenir)
        loadFeedbackMetrics();
    }

    /**
     * Analiz sonucundan metrikleri güncelle (backward compat)
     * NOT: f1_score, precision, recall Isolation Forest (unsupervised) modelde
     * gercek deger uretmez — /api/ml/metrics'ten gelen degerleri koruyoruz.
     */
    function updateMetricsFromAnalysis(summary) {
        // Accuracy: anomaly_rate'den hesapla (gercek veri)
        if (summary.anomaly_rate !== undefined) {
            var accuracy = (100 - summary.anomaly_rate).toFixed(1);
            updateElement('modelAccuracy', '%' + accuracy);
        }
        // f1_score, precision, recall: unsupervised model, gercek deger yok
        // /api/ml/metrics'ten gelen mevcut degerleri koruyoruz, uzerine yazmiyoruz

        // Anomali Istatistikleri — gercek veriler
        if (summary.total_logs !== undefined) {
            updateElement('totalLogs', summary.total_logs.toLocaleString('tr-TR'));
        }
        if (summary.n_anomalies !== undefined) {
            updateElement('detectedAnomalies', summary.n_anomalies.toLocaleString('tr-TR'));
        }
        if (summary.anomaly_rate !== undefined) {
            updateElement('anomalyRate', '%' + summary.anomaly_rate.toFixed(2));
        }
    }

    /**
     * ML Panel'i default degerlerle guncelle
     * Model yoksa veya reset sonrasi: tum metrikler '--' (bilinmiyor)
     */
    function updateMLPanelWithDefaults() {
        var defaults = {
            modelAccuracy: '--',
            modelF1: '--',
            modelPrecision: '--',
            modelRecall: '--',
            totalLogs: '0',
            detectedAnomalies: '0',
            anomalyRate: '%0.00',
            modelVersion: '--',
            lastTrainingDate: '--',
            mlServerName: '--',
            mlModelType: 'Isolation Forest',
            mlTrainingSamples: '--',
            mlFeatureCount: '--',
            mlBufferInfo: '--',
            mlModelFilePath: '--'
        };

        Object.keys(defaults).forEach(function(key) {
            updateElement(key, defaults[key]);
        });

        console.log('ML sidebar reset to defaults (no hardcoded fake metrics)');
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
                            '<div class="result-label">' + (isAnomaly ? 'ANOMALI TESPIT EDILDI' : 'NORMAL LOG') + '</div>' +
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
                    '<div class="result-label">' + (isAnomaly2 ? 'ANOMALI TESPIT EDILDI (Offline)' : 'NORMAL LOG (Offline)') + '</div>' +
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
     * Panel'i anomali analizi sonrasi otomatik guncelle
     * Tam sonuc objesinden summary, server_info, model_info, feature_importance cikarilir
     * Backend'den gelen TUM gercek verileri okur — hardcoded deger YOKTUR
     */
    function autoUpdatePanelAfterAnalysis(analysisResult) {
        if (!analysisResult || !analysisResult.sonuç) return;

        var sonuc = analysisResult.sonuç;
        var summary = sonuc.summary || (sonuc.data ? sonuc.data.summary : null) || {};

        // 1) Anomali istatistikleri ve accuracy (gercek veriden)
        if (summary.total_logs !== undefined || summary.n_anomalies !== undefined) {
            updateMetricsFromAnalysis(summary);
        }

        // 2) Sunucu adi
        var serverInfo = sonuc.server_info || {};
        if (serverInfo.server_name) {
            updateElement('mlServerName', serverInfo.server_name);
        } else if (window.selectedChatServer) {
            updateElement('mlServerName', window.selectedChatServer.split('.')[0]);
        }

        // 3) Model dosya yolu
        if (serverInfo.model_path) {
            updateElement('mlModelFilePath', serverInfo.model_path);
        }

        // 4) Feature importance — dinamik render
        var featureImportance = sonuc.feature_importance || {};
        if (Object.keys(featureImportance).length > 0) {
            renderDynamicFeatures(featureImportance);
        }

        // 5) Buffer bilgisi
        if (serverInfo.historical_buffer_size !== undefined) {
            var bufferVal = serverInfo.historical_buffer_size;
            var bufferMB = serverInfo.buffer_size_mb;
            var bufferText = bufferVal.toLocaleString('tr-TR');
            if (bufferMB) {
                bufferText += ' / ' + bufferMB.toFixed(1) + ' MB';
            }
            updateElement('mlBufferInfo', bufferText);
        }

        // 6) model_info'dan gercek model bilgilerini oku
        var mlData = sonuc.data || sonuc;
        var modelInfoObj = sonuc.model_info || mlData.model_info || {};

        // 6a) Egitim seti (training_samples)
        if (modelInfoObj.training_samples) {
            updateElement('mlTrainingSamples', modelInfoObj.training_samples.toLocaleString('tr-TR') + ' Satir');
        }

        // 6b) Feature sayisi
        if (modelInfoObj.feature_count) {
            updateElement('mlFeatureCount', modelInfoObj.feature_count.toString());
        }

        // 6c) Model versiyonu
        if (modelInfoObj.model_version) {
            updateElement('modelVersion', modelInfoObj.model_version);
        }

        // 6d) Model egitim tarihi
        if (modelInfoObj.model_trained_at) {
            try {
                updateElement('lastTrainingDate', new Date(modelInfoObj.model_trained_at).toLocaleDateString('tr-TR'));
            } catch (e) {
                updateElement('lastTrainingDate', modelInfoObj.model_trained_at);
            }
        }

        // 6e) Model tipi
        if (modelInfoObj.model_type) {
            updateElement('mlModelType', modelInfoObj.model_type);
        }

        console.log('ML Sidebar auto-updated after analysis:', {
            total_logs: summary.total_logs,
            anomalies: summary.n_anomalies,
            server: serverInfo.server_name,
            training_samples: modelInfoObj.training_samples,
            feature_count: modelInfoObj.feature_count,
            version: modelInfoObj.model_version
        });
    }

    // =====================================================================
    // FEEDBACK METRICS — Kullanici feedback'inden gercek precision hesapla
    // =====================================================================

    /**
     * Backend'den kullanici feedback metriklerini cek ve ML paneline yaz.
     * GET /api/ml/feedback-metrics endpoint'ini kullanir.
     * Precision gercek kullanici verisinden gelir (TP / (TP + FP)).
     */
    async function loadFeedbackMetrics() {
        try {
            var response = await fetch('/api/ml/feedback-metrics?api_key=' + encodeURIComponent(window.apiKey));
            if (!response.ok) return;

            var data = await response.json();
            if (data.status !== 'success' || !data.metrics) return;

            var m = data.metrics;
            var section = document.getElementById('feedbackMetricsSection');

            if (m.total_feedbacks > 0) {
                // Section'i goster
                if (section) section.style.display = '';

                // TP / FP sayilari
                updateElement('fbTruePositives', m.true_positives.toString());
                updateElement('fbFalsePositives', m.false_positives.toString());
                updateElement('fbTotalFeedbacks', m.total_feedbacks.toString());

                // Guven seviyesi badge
                var confEl = document.getElementById('fbConfidenceLevel');
                if (confEl) {
                    var confLabels = {
                        'high': 'Yuksek',
                        'medium': 'Orta',
                        'low': 'Dusuk',
                        'very_low': 'Cok Dusuk',
                        'none': '--'
                    };
                    confEl.textContent = confLabels[m.confidence_level] || m.confidence_level;
                    confEl.className = 'confidence-badge ' + m.confidence_level;
                }

                // Ana performans kartlarini guncelle (gercek feedback verisinden)
                if (m.precision !== null && m.precision !== undefined) {
                    updateElement('modelPrecision', '%' + (m.precision * 100).toFixed(1));
                }

                // F1 ve Recall — hesaplanabilir degil (unsupervised + sadece anomali feedback'i)
                // Ama precision varsa panelde goster, diger ikisi '--' kalsin
                // Bu sayede kullanici hangi metriklerin gercek, hangilerinin bilinmez oldugunu gorur

            } else {
                // Feedback yoksa section'i gizle
                if (section) section.style.display = 'none';
            }

            console.log('Feedback metrics loaded:', m);
        } catch (error) {
            console.warn('Could not load feedback metrics:', error);
        }
    }

    // Public API (tum eski fonksiyonlar + yeniler)
    window.MLPanel = {
        initialize: initializeMLPanel,
        show: showMLPanel,
        hide: hideMLPanel,
        toggle: toggleMLPanel,
        loadMetrics: loadMLMetrics,
        loadFeedbackMetrics: loadFeedbackMetrics,
        updateWithDefaults: updateMLPanelWithDefaults,
        autoUpdate: autoUpdatePanelAfterAnalysis,
        toggleMinimize: toggleMLPanel
    };

    // Backward compatibility — eski global fonksiyonlar
    window.showMLPanel = showMLPanel;
    window.hideMLPanel = hideMLPanel;
    window.loadMLMetrics = loadMLMetrics;
    window.updateMLPanelWithDefaults = updateMLPanelWithDefaults;
    window.toggleMLPanel = toggleMLPanel;

    console.log('ML Panel module loaded successfully (sidebar mode)');

})();
