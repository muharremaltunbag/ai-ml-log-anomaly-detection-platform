// web_ui\static\script-core.js
/**
 * LC Waikiki MongoDB Assistant - Core Configuration Module
 * 
 * Bu modül tüm diğer modüllerin kullanacağı merkezi konfigürasyonu sağlar:
 * - Global değişkenler (window objesi üzerinden erişilebilir)
 * - API endpoint tanımları
 * - DOM element referansları
 * 
 * ÖNEMLİ: Bu dosya diğer tüm script dosyalarından ÖNCE yüklenmeli!
 */

console.log('🔧 Loading script-core.js...');

// ============================================
// GLOBAL DEĞİŞKENLER - Window objesine atanır
// ============================================
window.apiKey = '';
window.isConnected = false;
window.selectedDataSource = 'upload';  // Varsayılan veri kaynağı
window.currentSessionId = `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
console.log('Session initialized:', window.currentSessionId);

// ============================================
// LCWGPT ASSISTANT STATE
// ============================================
window.selectedChatServer = null;   // Seçilen sunucu (LCWGPT chat için)
window.chatServerList = [];         // Analiz yapılmış sunucu listesi

// ============================================
// KONUŞMA GEÇMİŞİ SABİTLERİ
// ============================================
window.HISTORY_KEY = 'mongodb_query_history';
window.MAX_HISTORY_ITEMS = 50;
window.queryHistory = [];

// ============================================
// API ENDPOINTS
// ============================================
window.API_BASE = window.location.origin;
window.API_ENDPOINTS = {
    query: '/api/query',
    status: '/api/status',
    collections: '/api/collections',
    schema: '/api/schema',
    analyzeLog: '/api/analyze-uploaded-log',  // analyzeLog yerine analyze-uploaded-log
    uploadLog: '/api/upload-log',              
    uploadedLogs: '/api/uploaded-logs',        
    deleteUploadedLog: '/api/uploaded-log',    
    mongodbHosts: '/api/mongodb/hosts',         
    mongodbClusters: '/api/mongodb/clusters',   // CLUSTER SUPPORT
    mongodbClusterHosts: '/api/mongodb/cluster', // CLUSTER SUPPORT
    analyzeCluster: '/api/analyze-cluster',     // CLUSTER SUPPORT
    // YENİ STORAGE ENDPOINTS
    anomalyHistory: '/api/anomaly-history',
    storageStats: '/api/storage-stats',
    modelRegistry: '/api/model-registry',
    storageCleanup: '/api/storage-cleanup',
    anomalyDetail: '/api/anomaly-history',
    exportAnalysis: '/api/export-analysis',
    // MSSQL ENDPOINTS
    mssqlHosts: '/api/mssql/available-hosts',
    analyzeMSSQLLog: '/api/analyze-mssql-logs',
    // LCWGPT ASSISTANT
    analyzedServers: '/api/analyzed-servers',
    // SYSTEM RESET
    systemReset: '/api/system-reset'
};

// ============================================
// DOM ELEMENTS CACHE
// ============================================
// Not: Bu obje DOMContentLoaded'dan sonra doldurulacak
window.elements = {};

/**
 * DOM element referanslarını initialize et
 * Bu fonksiyon DOMContentLoaded event'inde çağrılmalı
 */
window.initializeElements = function() {
    window.elements = {
        apiKeyInput: document.getElementById('apiKey'),
        connectBtn: document.getElementById('connectBtn'),
        mainContent: document.getElementById('mainContent'),
        queryInput: document.getElementById('queryInput'),
        queryBtn: document.getElementById('queryBtn'),
        resultSection: document.getElementById('resultSection'),
        resultContent: document.getElementById('resultContent'),
        loader: document.getElementById('loader'),
        statusElement: document.getElementById('status'),
        statusText: document.querySelector('.status-text'),
        modal: document.getElementById('modal'),
        modalTitle: document.getElementById('modalTitle'),
        modalBody: document.getElementById('modalBody'),
        // ML Metrics Sidebar Elementleri
        mlPanel: document.getElementById('mlModelPanel'),
        modelAccuracy: document.getElementById('modelAccuracy'),
        modelF1: document.getElementById('modelF1'),
        modelPrecision: document.getElementById('modelPrecision'),
        modelRecall: document.getElementById('modelRecall'),
        totalLogs: document.getElementById('totalLogs'),
        detectedAnomalies: document.getElementById('detectedAnomalies'),
        anomalyRate: document.getElementById('anomalyRate'),
        modelVersion: document.getElementById('modelVersion'),
        lastTrainingDate: document.getElementById('lastTrainingDate'),
        mlServerName: document.getElementById('mlServerName'),
        mlModelType: document.getElementById('mlModelType'),
        mlTrainingSamples: document.getElementById('mlTrainingSamples'),
        mlFeatureCount: document.getElementById('mlFeatureCount'),
        mlBufferInfo: document.getElementById('mlBufferInfo'),
        mlModelFilePath: document.getElementById('mlModelFilePath')
    };
    console.log('✅ DOM elements initialized');
    return window.elements;
};

// ============================================
// GLOBAL DEĞİŞKEN GÜNCELLEME FONKSİYONLARI
// ============================================
/**
 * API anahtarını güncelle
 * @param {string} newKey - Yeni API anahtarı
 */
window.updateApiKey = function(newKey) {
    window.apiKey = newKey;
    console.log('✅ API key updated');
};

/**
 * Bağlantı durumunu güncelle
 * @param {boolean} status - Bağlantı durumu
 */
window.updateConnectionStatus = function(status) {
    window.isConnected = status;
    console.log(`✅ Connection status updated: ${status}`);
};

/**
 * Veri kaynağını güncelle
 * @param {string} source - Yeni veri kaynağı
 */
window.updateDataSource = function(source) {
    window.selectedDataSource = source;
    console.log(`✅ Data source updated: ${source}`);
};

// ============================================
// STORAGE MANAGEMENT FUNCTIONS
// ============================================

/**
 * Model'i aktif et
 */
window.activateModel = async function(versionId) {
    if (!confirm(`${versionId} versiyonunu aktif model olarak ayarlamak istiyor musunuz?`)) {
        return;
    }
    try {
        const response = await fetch(`${window.API_ENDPOINTS.modelRegistry}/${versionId}/activate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ api_key: window.apiKey })
        });
        if (!response.ok) throw new Error('Model aktif edilemedi');
        window.showNotification('Model başarıyla aktif edildi', 'success');
        window.closeModal();
        setTimeout(() => window.showModelRegistry(), 500);
    } catch (error) {
        console.error('[MODEL REGISTRY] Error activating model:', error);
        window.showNotification('Model aktif edilirken hata oluştu', 'error');
    }
};

/**
 * Storage cleanup işlemi
 */
window.performStorageCleanup = async function() {
    if (!confirm('Eski storage verilerini temizlemek istediğinizden emin misiniz?')) {
        return;
    }
    try {
        const response = await fetch(`${window.API_ENDPOINTS.storageCleanup}?api_key=${window.apiKey}`, { 
            method: 'POST' 
        });
        if (!response.ok) throw new Error('Cleanup API call failed');
        const data = await response.json();
        const stats = data?.cleanup_stats || {};
        window.showNotification(
            `Temizlik tamamlandı: ${stats.files_deleted || 0} dosya silindi, ${(stats.space_freed_mb || 0).toFixed(2)} MB alan boşaltıldı`,
            'success'
        );
    } catch (error) {
        console.error('[STORAGE] Error during storage cleanup:', error);
        window.showNotification('Temizlik işlemi başarısız oldu', 'error');
    }
};

/**
 * Storage'dan son anomali analizini yükle
 * Sayfa yenilendiğinde veya ilk bağlantıda otomatik çalışır
 */
window.loadLastAnomalyFromStorage = async function() {
    // Connection durumunu bekle (max 5 saniye)
    let retryCount = 0;
    while ((!window.isConnected || !window.apiKey) && retryCount < 50) {
        await new Promise(resolve => setTimeout(resolve, 100));
        retryCount++;
    }

    if (!window.isConnected || !window.apiKey) {
        console.log('[STORAGE] Not connected after retry, skipping storage load');
        return false;
    }

    try {
        console.log('Loading last anomaly analysis from storage...');

        // ✅ FIX: Direkt anomaly-history endpoint'ini kullan
        const response = await fetch(
            `${window.API_ENDPOINTS.anomalyHistory}?api_key=${window.apiKey}&limit=1`,
            { method: 'GET' }
        );

        if (!response.ok) {
            console.log('Failed to fetch anomaly history');
            return false;
        }

        const data = await response.json();

        if (data.status === 'success' && data.history && data.history.length > 0) {
            const lastAnalysis = data.history[0];

            // Detaylı veriyi çek
            const detailResponse = await fetch(
                `${window.API_ENDPOINTS.anomalyHistory}/${lastAnalysis.analysis_id}?api_key=${window.apiKey}`,
                { method: 'GET' }
            );

            if (detailResponse.ok) {
                const detailData = await detailResponse.json();

                if (detailData.status === 'success' && detailData.analysis) {
                    const analysis = detailData.analysis;

                    // Global değişkene ata (script-history.js formatıyla uyumlu)
                    window.lastAnomalyResult = {
                        durum: 'tamamlandı',
                        işlem: 'anomaly_from_storage',
                        açıklama: `📊 Önceki anomali analizi yüklendi\n\nAnaliz ID: ${analysis.analysis_id}\nZaman: ${analysis.timestamp}`,
                        analysis_id: analysis.analysis_id,
                        sonuç: {
                            from_storage: true,
                            analysis_id: analysis.analysis_id,
                            anomaly_count: analysis.anomaly_count || 0,
                            anomaly_rate: analysis.anomaly_rate || 0,
                            total_logs: analysis.logs_analyzed || 0,
                            critical_anomalies: analysis.critical_anomalies || [],
                            unfiltered_anomalies: analysis.unfiltered_anomalies || [],
                            storage_info: {
                                analysis_id: analysis.analysis_id,
                                timestamp: analysis.timestamp,
                                host: analysis.host,
                                time_range: analysis.time_range
                            }
                        },
                        storage_info: {
                            analysis_id: analysis.analysis_id,
                            timestamp: analysis.timestamp
                        }
                    };

                    console.log('✅ Storage anomaly loaded successfully:', {
                        analysis_id: analysis.analysis_id,
                        anomaly_count: analysis.anomaly_count,
                        has_critical: !!(analysis.critical_anomalies?.length)
                    });

                    // Query input'a ipucu ekle
                    if (window.elements.queryInput) {
                        window.elements.queryInput.placeholder = "Önceki analizle ilgili sorularınızı sorabilirsiniz...";
                    }

                    return true;
                }
            }
        }
    } catch (error) {
        console.error('Error loading from storage:', error);
    }

    console.log('No previous analysis found in storage');
    return false;
};

// ============================================
// LCWGPT SIDEBAR — AI Yanıt Formatlayıcı
// ============================================

/**
 * LCWGPT sidebar AI yanıtını Bento-box "AI Technical Resolution Report" formatında üret.
 * Backend response objesini alır, yapılandırılmış rapor HTML'i döner.
 *
 * chatResult objesi (api.py /api/chat-query-anomalies'den):
 *   .host, .timestamp, .total_anomalies, .analysis_id,
 *   .ai_response (düz metin), .performance_metrics.processing_time_ms,
 *   .chunks_processed, .total_chunks, .processing_mode
 *
 * Geriye dönük uyumlu: herhangi bir alan eksikse zararsız fallback.
 */
window.formatSidebarAIResponse = function(chatResult) {
    var esc = window.escapeHtml || function(s) { return String(s); };

    // ── 1. Yapısal verileri çıkar ──
    var server = chatResult.host || window.selectedChatServer || '';
    var serverShort = server ? server.split('.')[0] : '';
    var ts = chatResult.timestamp || '';
    var anomalyCount = (typeof chatResult.total_anomalies === 'number') ? chatResult.total_anomalies : '?';
    var analysisId = chatResult.analysis_id || '';
    var reportId = analysisId ? analysisId.replace('analysis_', '').substring(0, 8).toUpperCase() : '';
    var processingTime = (chatResult.performance_metrics && chatResult.performance_metrics.processing_time_ms)
        ? (chatResult.performance_metrics.processing_time_ms / 1000).toFixed(2) + 's'
        : null;
    var chunksProcessed = chatResult.chunks_processed || 1;
    var totalChunks = chatResult.total_chunks || 1;

    // Timestamp'i okunabilir formata çevir
    var tsDisplay = ts;
    if (ts) {
        try {
            var d = new Date(ts);
            if (!isNaN(d.getTime())) {
                tsDisplay = d.toLocaleDateString('tr-TR') + ' ' + d.toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' });
            }
        } catch (e) { /* ham haliyle kullan */ }
    }

    // Source type tespiti (chatServerList'ten)
    var sourceType = 'MongoDB';
    if (window.chatServerList && server) {
        var serverInfo = window.chatServerList.find(function(s) { return s.host === server; });
        if (serverInfo && serverInfo.source) {
            var src = serverInfo.source.toLowerCase();
            if (src.includes('mssql')) sourceType = 'MSSQL';
        }
    }

    var parts = [];
    parts.push('<div class="report-container">');

    // ══════════════════════════════════════
    // REPORT HEADER
    // ══════════════════════════════════════
    parts.push(
        '<div class="report-header">' +
            '<div class="report-header-left">' +
                '<div class="report-header-icon">\uD83E\uDD16</div>' +
                '<div class="report-header-text">' +
                    '<h3>AI Technical Resolution Report</h3>' +
                    '<span class="report-id">' +
                        '<span class="pulse-dot"></span> ' +
                        'Actionable Intelligence' +
                        (reportId ? ' \u2022 #RPT-' + esc(reportId) : '') +
                    '</span>' +
                '</div>' +
            '</div>' +
        '</div>'
    );

    // ══════════════════════════════════════
    // CONTEXT BAR
    // ══════════════════════════════════════
    if (serverShort) {
        parts.push(
            '<div class="report-context-bar">' +
                '<div class="report-context-item">' +
                    '<span class="ctx-label">Target</span>' +
                    '<span class="ctx-value">' + esc(serverShort) + '</span>' +
                '</div>' +
                '<div class="report-context-divider"></div>' +
                '<div class="report-context-item">' +
                    '<span class="ctx-label">Source</span>' +
                    '<span class="ctx-value">' + esc(sourceType) + '</span>' +
                '</div>' +
                '<div class="report-context-divider"></div>' +
                '<div class="report-context-item">' +
                    '<span class="ctx-label">Anomalies</span>' +
                    '<span class="ctx-value">' + anomalyCount + '</span>' +
                '</div>' +
                (tsDisplay ? (
                    '<div class="report-context-divider"></div>' +
                    '<div class="report-context-item">' +
                        '<span class="ctx-label">Analysis</span>' +
                        '<span class="ctx-value">' + esc(tsDisplay) + '</span>' +
                    '</div>'
                ) : '') +
            '</div>'
        );
    }

    // ══════════════════════════════════════
    // LLM RESPONSE BODY — Section Parser (Bento Kartları)
    // Marker'lar: 📊 ÖZET, 🔍 DETAYLI ANALİZ, ⚠️ RİSKLER, ✅ ÖNERİLER
    // Fallback: hiçbir marker bulunamazsa tek kart.
    // ══════════════════════════════════════
    var rawBody = chatResult.ai_response || '';

    // ── Yardımcı: markdown → HTML (code block'lar hariç) ──
    function mdToHtml(text) {
        // Önce code block'ları placeholder'la değiştir
        var codeBlocks = [];
        text = text.replace(/```([\s\S]*?)```/g, function(match, code) {
            var idx = codeBlocks.length;
            codeBlocks.push(code);
            return '%%CODEBLOCK_' + idx + '%%';
        });

        // XSS koruması
        text = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

        // Inline markdown
        text = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        text = text.replace(/`([^`]+)`/g, '<code class="report-inline-code">$1</code>');
        text = text.replace(/^### (.*?)$/gm, '<strong style="display:block;margin:6px 0 2px;">$1</strong>');
        text = text.replace(/^## (.*?)$/gm, '<strong style="display:block;margin:6px 0 2px;">$1</strong>');
        text = text.replace(/^# (.*?)$/gm, '<strong style="display:block;margin:8px 0 3px;">$1</strong>');

        // Satır sonları
        text = text.replace(/\n/g, '<br>');

        // Code block placeholder'ları terminal-pencere HTML'ine dönüştür
        text = text.replace(/%%CODEBLOCK_(\d+)%%/g, function(match, idx) {
            var code = codeBlocks[parseInt(idx)] || '';
            var codeContent = code.trim();

            // İlk satır dil etiketi olabilir (ör: "javascript", "mongodb", "sql")
            var langTag = '';
            var firstLine = codeContent.split('\n')[0].trim().toLowerCase();
            if (firstLine && firstLine.length < 20 && !/[{}\[\]()\s]{2,}/.test(firstLine)) {
                langTag = firstLine;
                codeContent = codeContent.substring(codeContent.indexOf('\n') + 1);
            }

            // Akıllı title: dil etiketine + source type'a göre
            var title = 'code';
            var langLower = langTag.toLowerCase();
            if (langLower === 'mongodb' || langLower === 'mongo' || langLower === 'js' || langLower === 'javascript') {
                title = 'Suggested Fix (MongoDB Shell)';
            } else if (langLower === 'sql' || langLower === 'mssql' || langLower === 'tsql' || langLower === 't-sql') {
                title = 'Suggested Fix (MSSQL Script)';
            } else if (langLower === 'bash' || langLower === 'shell' || langLower === 'sh') {
                title = 'Shell Command';
            } else if (langLower === 'json') {
                title = 'JSON Output';
            } else if (langLower === 'log' || langLower === 'text' || langLower === 'plaintext') {
                title = 'Log Sample';
            } else if (langTag) {
                title = langTag;
            } else {
                // Dil etiketi yoksa, içerikten tahmin et
                if (/\bdb\.\w+\.\w+\(/.test(codeContent)) {
                    title = 'Suggested Fix (MongoDB Shell)';
                } else if (/\b(?:SELECT|INSERT|UPDATE|DELETE|ALTER|CREATE|EXEC)\b/i.test(codeContent)) {
                    title = 'Suggested Fix (MSSQL Script)';
                } else if (/(?:WARN|ERROR|INFO|DEBUG)\s*[:|\s]/.test(codeContent) || /timestamp|severity|component/i.test(codeContent)) {
                    title = 'Raw Log Sample';
                }
            }

            // XSS koruması code içeriği için
            codeContent = codeContent.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

            // Title'a göre header renk tonu
            var headerIcon = '\uD83D\uDCBB'; // 💻
            if (title.indexOf('Suggested Fix') !== -1) headerIcon = '\u26A1'; // ⚡
            if (title.indexOf('Log') !== -1) headerIcon = '\uD83D\uDCC4'; // 📄

            return '</span>' +
                '<div class="report-code-window">' +
                    '<div class="report-code-header">' +
                        '<div class="report-code-dots">' +
                            '<span class="dot-red"></span>' +
                            '<span class="dot-yellow"></span>' +
                            '<span class="dot-green"></span>' +
                        '</div>' +
                        '<span class="report-code-title">' + headerIcon + ' ' + esc(title) + '</span>' +
                        '<div class="report-code-actions">' +
                            '<button type="button" class="report-copy-btn" onclick="window._reportCopyCode(this)">\uD83D\uDCCB Copy</button>' +
                        '</div>' +
                    '</div>' +
                    '<div class="report-code-body">' + codeContent + '</div>' +
                '</div>' +
            '<span>';
        });

        // Boş span tag'lerini temizle
        text = text.replace(/<span><\/span>/g, '');
        text = text.replace(/<\/span><br><span>/g, '');
        // Baştaki/sondaki orphan span'ları temizle
        text = text.replace(/^<\/span>/g, '');
        text = text.replace(/<span>$/g, '');

        return text;
    }

    // ── Section marker tanımları (esnek regex — emoji + metin varyasyonları) ──
    var sectionDefs = [
        { key: 'summary',  icon: '\uD83D\uDCCA', label: 'Summary',                regex: /(?:📊\s*(?:ÖZET|GENEL\s*ÖZET|SUMMARY)\s*:?|##?\s*(?:ÖZET|SUMMARY)\s*:?)/i },
        { key: 'analysis', icon: '\uD83D\uDD0D', label: 'Detailed Analysis',      regex: /(?:🔍\s*(?:DETAYLI?\s*ANALİZ|DETAILED?\s*ANALYSIS?|ANALİZ)\s*:?|##?\s*(?:DETAYLI?\s*ANALİZ|ANALİZ)\s*:?)/i },
        { key: 'risks',    icon: '\u26A0\uFE0F', label: 'Impact & Risks',         regex: /(?:⚠️\s*(?:RİSKLER|RISKLER|RISKS?|ETKİ\s*ANALİZİ|IMPACT)\s*:?|##?\s*(?:RİSKLER|RISKLER)\s*:?)/i },
        { key: 'actions',  icon: '\u2705',        label: 'Resolution Guide',       regex: /(?:✅\s*(?:ÖNERİLER|ONERILER|RECOMMENDATIONS?|ÇÖZÜM|AKSIYONLAR)\s*:?|##?\s*(?:ÖNERİLER|ÇÖZÜM)\s*:?)/i }
    ];

    // ── Marker pozisyonlarını bul ──
    var foundSections = [];
    sectionDefs.forEach(function(def) {
        var match = rawBody.match(def.regex);
        if (match) {
            foundSections.push({
                key:   def.key,
                icon:  def.icon,
                label: def.label,
                start: match.index,
                headerLength: match[0].length
            });
        }
    });

    // Pozisyona göre sırala
    foundSections.sort(function(a, b) { return a.start - b.start; });

    // ── Bölümlere ayır ──
    if (foundSections.length >= 2) {
        // Marker'lardan önceki metin (varsa) — "preamble"
        var preambleEnd = foundSections[0].start;
        var preamble = rawBody.substring(0, preambleEnd).trim();
        if (preamble) {
            parts.push(
                '<div class="report-card">' +
                    '<div class="report-card-body sidebar-response-body">' + mdToHtml(preamble) + '</div>' +
                '</div>'
            );
        }

        // Her bölümü kendi kartına map'le
        for (var si = 0; si < foundSections.length; si++) {
            var sec = foundSections[si];
            var contentStart = sec.start + sec.headerLength;
            var contentEnd = (si + 1 < foundSections.length) ? foundSections[si + 1].start : rawBody.length;
            var sectionContent = rawBody.substring(contentStart, contentEnd).trim();

            if (!sectionContent) continue;

            // Risk/Impact bölümü için özel styling
            if (sec.key === 'risks') {
                parts.push(
                    '<div class="report-impact">' +
                        '<span class="report-impact-icon">\u26A1</span>' +
                        '<div class="report-impact-content">' +
                            '<h4>' + sec.label + '</h4>' +
                            '<p>' + mdToHtml(sectionContent) + '</p>' +
                        '</div>' +
                    '</div>'
                );
            }
            // Resolution/Öneriler bölümü için timeline styling
            else if (sec.key === 'actions') {
                // Numaralı adımları algıla (1., 2., 3. veya - ile başlayan)
                var steps = sectionContent.split(/\n/).filter(function(l) { return l.trim(); });
                var hasNumberedSteps = steps.some(function(l) { return /^\s*\d+[\.\)\-]/.test(l); });

                if (hasNumberedSteps) {
                    var stepsHtml = '<div class="report-steps">';
                    var stepNum = 0;
                    steps.forEach(function(line) {
                        var trimmed = line.trim();
                        if (!trimmed) return;
                        var stepMatch = trimmed.match(/^\s*(\d+)[\.\)\-]\s*(.*)/);
                        if (stepMatch) {
                            stepNum++;
                            var stepTitle = stepMatch[2];
                            // Eğer sonraki satır alt açıklama ise ayrı göster
                            stepsHtml +=
                                '<div class="report-step">' +
                                    '<span class="report-step-number">' + stepNum + '</span>' +
                                    '<h4>' + mdToHtml(stepTitle) + '</h4>' +
                                '</div>';
                        } else if (stepNum > 0 && /^\s*[-•]/.test(trimmed)) {
                            // Alt madde — son step'e ait
                            var subText = trimmed.replace(/^\s*[-•]\s*/, '');
                            stepsHtml +=
                                '<div class="report-step" style="margin-left:12px;">' +
                                    '<p style="font-size:11px;">\u2022 ' + mdToHtml(subText) + '</p>' +
                                '</div>';
                        } else {
                            // Düz metin satırı
                            stepsHtml +=
                                '<div class="report-step">' +
                                    '<p>' + mdToHtml(trimmed) + '</p>' +
                                '</div>';
                        }
                    });
                    stepsHtml += '</div>';

                    parts.push(
                        '<div class="report-card">' +
                            '<div class="report-card-header">' +
                                '<span class="card-icon">' + sec.icon + '</span> ' + sec.label +
                            '</div>' +
                            '<div class="report-card-body">' + stepsHtml + '</div>' +
                        '</div>'
                    );
                } else {
                    // Numaralı adım yoksa normal kart
                    parts.push(
                        '<div class="report-card">' +
                            '<div class="report-card-header">' +
                                '<span class="card-icon">' + sec.icon + '</span> ' + sec.label +
                            '</div>' +
                            '<div class="report-card-body sidebar-response-body">' + mdToHtml(sectionContent) + '</div>' +
                        '</div>'
                    );
                }
            }
            // Standart bölümler (Summary, Analysis)
            else {
                // Summary için ML Insights tarzı (mor vurgu)
                var cardClass = (sec.key === 'summary') ? 'report-card ml-insights' : 'report-card';
                parts.push(
                    '<div class="' + cardClass + '">' +
                        '<div class="report-card-header">' +
                            '<span class="card-icon">' + sec.icon + '</span> ' + sec.label +
                        '</div>' +
                        '<div class="report-card-body sidebar-response-body">' + mdToHtml(sectionContent) + '</div>' +
                    '</div>'
                );
            }
        }
    } else {
        // ── FALLBACK: Marker bulunamadı → tek kart ──
        parts.push(
            '<div class="report-card">' +
                '<div class="report-card-header">' +
                    '<span class="card-icon">\uD83E\uDDE0</span> LLM Technical Interpretation' +
                '</div>' +
                '<div class="report-card-body sidebar-response-body">' + mdToHtml(rawBody) + '</div>' +
            '</div>'
        );
    }

    // ══════════════════════════════════════
    // TECHNICAL SPECS — Response metadata'dan
    // ══════════════════════════════════════
    var specsItems = [];
    specsItems.push({ label: 'Query Type', value: sourceType + ' / Anomaly' });
    specsItems.push({ label: 'Total Anomalies', value: String(anomalyCount) });
    if (chatResult.processing_mode) {
        specsItems.push({ label: 'Processing', value: chatResult.processing_mode === 'multi-chunk' ? 'Multi-Chunk' : 'Single-Chunk' });
    }
    if (chunksProcessed > 1) {
        specsItems.push({ label: 'Chunks', value: chunksProcessed + ' / ' + totalChunks });
    }
    if (chatResult.performance_metrics && chatResult.performance_metrics.tokens_estimated) {
        specsItems.push({ label: 'Tokens Est.', value: '~' + Math.round(chatResult.performance_metrics.tokens_estimated) });
    }

    if (specsItems.length > 0) {
        var specsHtml = '<ul class="report-specs">';
        specsItems.forEach(function(item) {
            specsHtml += '<li><span class="spec-label">' + esc(item.label) + '</span><span class="spec-value">' + esc(item.value) + '</span></li>';
        });
        specsHtml += '</ul>';

        parts.push(
            '<div class="report-card">' +
                '<div class="report-card-header">' +
                    '<span class="card-icon">\u2699\uFE0F</span> Technical Specs' +
                '</div>' +
                '<div class="report-card-body">' + specsHtml + '</div>' +
            '</div>'
        );
    }

    // ══════════════════════════════════════
    // FOOTER
    // ══════════════════════════════════════
    var footerLeft = '';
    if (processingTime) {
        footerLeft = '<span class="pulse-dot"></span> Analysis completed in ' + esc(processingTime);
        if (chunksProcessed > 1) {
            footerLeft += ' (' + chunksProcessed + '/' + totalChunks + ' chunks)';
        }
    }

    parts.push(
        '<div class="report-footer">' +
            '<div class="report-footer-left">' + footerLeft + '</div>' +
            '<div class="report-footer-actions">' +
                '<button type="button" title="Mark as useful" onclick="if(window.showNotification)window.showNotification(\'Geri bildirim kaydedildi\',\'success\');">\uD83D\uDC4D</button>' +
                '<button type="button" title="Report issue" onclick="if(window.showNotification)window.showNotification(\'Sorun bildirildi\',\'info\');">\uD83D\uDEA9</button>' +
            '</div>' +
        '</div>'
    );

    parts.push('</div>'); // close report-container
    return parts.join('');
};

console.log('✅ Core module loaded successfully');
console.log('📊 Global variables available:', {
    apiKey: typeof window.apiKey,
    isConnected: window.isConnected,
    selectedDataSource: window.selectedDataSource,
    currentSessionId: window.currentSessionId ? 'initialized' : 'missing',
    API_ENDPOINTS: Object.keys(window.API_ENDPOINTS).length + ' endpoints'
});

// ============================================================
// BENTO REPORT — Copy Code Butonu Handler
// ============================================================

/**
 * Report code window'larındaki Copy butonunun click handler'ı.
 * Kod içeriğini clipboard'a kopyalar, butonu "Copied!" olarak günceller.
 */
window._reportCopyCode = function(btn) {
    var codeWindow = btn.closest('.report-code-window');
    if (!codeWindow) return;
    var codeBody = codeWindow.querySelector('.report-code-body');
    if (!codeBody) return;

    var codeText = codeBody.innerText || codeBody.textContent || '';

    // Clipboard API (modern) veya fallback (eski tarayıcılar)
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(codeText).then(function() {
            _showCopied(btn);
        }).catch(function() {
            _fallbackCopy(codeText, btn);
        });
    } else {
        _fallbackCopy(codeText, btn);
    }

    function _fallbackCopy(text, button) {
        var ta = document.createElement('textarea');
        ta.value = text;
        ta.style.cssText = 'position:fixed;left:-9999px;';
        document.body.appendChild(ta);
        ta.select();
        try { document.execCommand('copy'); _showCopied(button); }
        catch (e) { console.warn('Copy failed:', e); }
        document.body.removeChild(ta);
    }

    function _showCopied(button) {
        var originalText = button.innerHTML;
        button.innerHTML = '\u2705 Copied!';
        button.classList.add('copied');
        setTimeout(function() {
            button.innerHTML = originalText;
            button.classList.remove('copied');
        }, 2000);
    }
};

// ============================================================
// LCWGPT Sidebar — Toggle, Close, Send (Figma layout)
// Mevcut fonksiyonlara dokunmaz, sadece sidebar UI kontrolu
// ============================================================

window.toggleLcwgptSidebar = function() {
    const sidebar = document.getElementById('lcwgptSidebar');
    if (!sidebar) return;
    sidebar.classList.toggle('open');
    console.log('LCWGPT Sidebar toggled:', sidebar.classList.contains('open') ? 'open' : 'closed');
};

window.closeLcwgptSidebar = function() {
    const sidebar = document.getElementById('lcwgptSidebar');
    if (sidebar) sidebar.classList.remove('open');
};

// Sidebar'a AI mesaji ekle
window.addSidebarAIMessage = function(text) {
    const container = document.getElementById('sidebarChatMessages');
    if (!container) return;
    const bubble = document.createElement('div');
    bubble.className = 'sidebar-ai-bubble';
    bubble.innerHTML = `
        <span class="sidebar-ai-avatar">🤖</span>
        <div class="sidebar-bubble-content">${text}</div>
    `;
    container.appendChild(bubble);
    container.scrollTop = container.scrollHeight;
};

// Sidebar'a kullanici mesaji ekle
window.addSidebarUserMessage = function(text) {
    const container = document.getElementById('sidebarChatMessages');
    if (!container) return;
    const bubble = document.createElement('div');
    bubble.className = 'sidebar-user-bubble';
    bubble.innerHTML = `
        <span class="sidebar-user-avatar">👤</span>
        <div class="sidebar-bubble-content">${window.escapeHtml ? window.escapeHtml(text) : text}</div>
    `;
    container.appendChild(bubble);
    container.scrollTop = container.scrollHeight;
};

// ============================================
// LCWGPT SUNUCU LİSTESİ VE SEÇİM FONKSİYONLARI
// ============================================

// Analiz yapılmış sunucu listesini backend'den çek
window.loadAnalyzedServers = async function() {
    if (!window.apiKey) return;
    try {
        const response = await fetch(`${window.API_ENDPOINTS.analyzedServers}?api_key=${encodeURIComponent(window.apiKey)}`);
        if (!response.ok) return;
        const data = await response.json();
        if (data.status === 'success' && data.servers) {
            window.chatServerList = data.servers;
            console.log('LCWGPT: Loaded', data.servers.length, 'analyzed servers');
        }
    } catch (e) {
        console.warn('LCWGPT: Could not load analyzed servers:', e);
    }
};

// Sidebar'da sunucu seçim butonlarını göster
window.showServerSelection = function() {
    const container = document.getElementById('sidebarChatMessages');
    if (!container) return;

    // Sunucu listesi boşsa bilgi ver
    if (!window.chatServerList || window.chatServerList.length === 0) {
        window.addSidebarAIMessage(
            'Henüz analiz yapılmış sunucu bulunamadı. ' +
            'Önce bir MongoDB veya MSSQL sunucusu için anomali analizi çalıştırın.'
        );
        return;
    }

    // Sunucu seçim mesajı oluştur
    const bubble = document.createElement('div');
    bubble.className = 'sidebar-ai-bubble';

    let serverButtons = window.chatServerList.map(function(server) {
        const shortName = server.host.split('.')[0];
        const src = (server.source || '').toLowerCase();
        const sourceTag = src.includes('mssql') ? 'MSSQL' : src.includes('opensearch') ? 'OpenSearch' : 'MongoDB';
        const anomalyBadge = server.anomaly_count ? ' <span class="server-anomaly-count">' + server.anomaly_count + '</span>' : '';
        return '<button class="server-select-btn" data-server="' + server.host + '" ' +
               'data-analysis-id="' + (server.analysis_id || '') + '" ' +
               'title="Son analiz: ' + (server.last_analysis || 'N/A') + ' | Anomali: ' + (server.anomaly_count || 0) + '">' +
               shortName + anomalyBadge + ' <span class="server-tag">' + sourceTag + '</span></button>';
    }).join('');

    bubble.innerHTML =
        '<span class="sidebar-ai-avatar">&#129302;</span>' +
        '<div class="sidebar-bubble-content">' +
            '<p>Hangi sunucu hakkinda yardimci olabilirim?</p>' +
            '<div class="server-selection-grid">' + serverButtons + '</div>' +
        '</div>';

    container.appendChild(bubble);
    container.scrollTop = container.scrollHeight;

    // Butonlara click handler ekle
    bubble.querySelectorAll('.server-select-btn').forEach(function(btn) {
        btn.addEventListener('click', function() {
            const serverName = this.getAttribute('data-server');
            const analysisId = this.getAttribute('data-analysis-id');
            window.selectChatServer(serverName, analysisId);
        });
    });
};

// ============================================
// ÖRNEK SORULAR — Veri Seti ve Render
// ============================================

/**
 * Source type bazli ornek soru setleri.
 * 'general' → sunucu secilmeden once
 * 'mssql'   → MSSQL sunucu secildiginde
 * 'mongodb' → MongoDB sunucu secildiginde
 */
window.EXAMPLE_QUESTIONS = {
    general: [
        { icon: '📊', text: 'Hangi sunucularda en cok anomali tespit edildi?' },
        { icon: '🔍', text: 'En son yapilan analizlerde kritik bulgular neler?' },
        { icon: '📈', text: 'Anomali analizlerinin genel ozetini goster' },
        { icon: '⚠️', text: 'Son 24 saatteki anomali trendlerini analiz et' },
        { icon: '🏥', text: 'Sunucu saglik durumlarini karsilastir' },
        { icon: '🔁', text: 'Tum analizlerdeki tekrarlayan oruntuleri bul' },
        { icon: '🚨', text: 'Acil mudahale gerektiren anomalileri listele' },
        { icon: '📉', text: 'Anomali sikliginda artis olan sunuculari goster' }
    ],
    mssql: [
        { icon: '🔐', text: 'Basarisiz login denemelerini raporla' },
        { icon: '🔄', text: 'Availability Group erisim sorunlarini incele' },
        { icon: '🛡️', text: 'Yetkilendirme hatalarini analiz et' },
        { icon: '⏱️', text: 'Deadlock ve blocking durumlarini listele' },
        { icon: '👤', text: 'Devre disi hesaplarla yapilan giris denemelerini goster' },
        { icon: '🌐', text: 'Hangi client IP adreslerinden en cok hata geliyor?' },
        { icon: '🗄️', text: 'Veritabani erisim sorunlarini ozetle' },
        { icon: '🔁', text: 'Tekrarlayan login hatasi oruntularini bul' },
        { icon: '📊', text: 'Hata kategorilerine gore dagilimi goster' },
        { icon: '📋', text: 'En kritik 5 anomaliyi ozetle' }
    ],
    mongodb: [
        { icon: '🔑', text: 'DuplicateKey hatalarinin kok nedenini bul' },
        { icon: '⏱️', text: 'Uzun suren transactionlari listele' },
        { icon: '💚', text: 'Replica set saglik durumunu analiz et' },
        { icon: '🔌', text: 'Baglanti havuzu sorunlarini incele' },
        { icon: '🔒', text: 'Unauthorized erisim denemelerini raporla' },
        { icon: '📝', text: 'WiredTiger checkpoint sorunlarini analiz et' },
        { icon: '🔄', text: 'Transaction commit surelerindeki anomalileri goster' },
        { icon: '👤', text: 'Hangi kullanicilar en cok hata uretiyor?' },
        { icon: '🌐', text: 'Baglanti kaynaklarini (client IP) analiz et' },
        { icon: '📋', text: 'En kritik 5 anomaliyi ozetle' }
    ]
};

/**
 * Secili sunucunun source type'ini chatServerList'ten bul.
 * Bulamazsa null doner.
 */
window.getSelectedServerSourceType = function() {
    if (!window.selectedChatServer || !window.chatServerList) return null;
    var server = window.chatServerList.find(function(s) {
        return s.host === window.selectedChatServer;
    });
    if (!server) return null;
    var src = (server.source || '').toLowerCase();
    if (src.includes('mssql')) return 'mssql';
    if (src.includes('mongo') || src.includes('opensearch')) return 'mongodb';
    return null;
};

/**
 * Ornek soru chip'lerini renderla.
 * @param {string|null} sourceType — 'mssql', 'mongodb', veya null (genel)
 */
window.renderExampleQuestions = function(sourceType) {
    var container = document.getElementById('exampleQuestionsContainer');
    if (!container) return;

    var questions = window.EXAMPLE_QUESTIONS[sourceType] || window.EXAMPLE_QUESTIONS.general;
    var dataSource = sourceType || 'general';

    container.innerHTML = '';
    questions.forEach(function(q) {
        var chip = document.createElement('button');
        chip.className = 'example-question-chip';
        chip.setAttribute('data-source', dataSource);
        chip.setAttribute('type', 'button');
        chip.innerHTML = '<span class="chip-icon">' + q.icon + '</span><span>' + q.text + '</span>';
        chip.addEventListener('click', function() {
            var input = document.getElementById('sidebarChatInput');
            if (input) {
                input.value = q.text;
                input.focus();
            }
            // Otomatik gonder
            if (typeof window.handleSidebarSend === 'function') {
                window.handleSidebarSend();
            }
        });
        container.appendChild(chip);
    });

    console.log('LCWGPT: Example questions rendered for source:', dataSource, '(' + questions.length + ' chips)');
};

/**
 * Mevcut secili sunucuya gore ornek sorulari guncelle.
 * Sunucu secilmemisse genel soru setini gosterir.
 */
window.updateExampleQuestions = function() {
    var sourceType = window.getSelectedServerSourceType();
    window.renderExampleQuestions(sourceType);
};

// Sunucu seçimini uygula
window.selectChatServer = function(serverName, analysisId) {
    window.selectedChatServer = serverName;
    // analysis_id'yi her zaman güncelle — boş/null olsa bile eski sunucunun ID'si kalmasın
    window.selectedChatAnalysisId = analysisId || null;

    const shortName = serverName.split('.')[0];

    // Seçim onay mesajı
    window.addSidebarAIMessage(
        '<strong>' + shortName + '</strong> sunucusu secildi. ' +
        'Bu sunucudaki anomaliler hakkinda sorularinizi sorabilirsiniz.<br>' +
        '<small style="opacity:0.6">Farkli bir sunucu secmek icin "sunucu degistir" yazabilirsiniz.</small>'
    );

    // Seçim butonlarını devre dışı bırak (tekrar tıklanmasın)
    document.querySelectorAll('.server-select-btn').forEach(function(btn) {
        btn.disabled = true;
        btn.style.opacity = '0.5';
        if (btn.getAttribute('data-server') === serverName) {
            btn.style.opacity = '1';
            btn.style.border = '2px solid #3498db';
        }
    });

    console.log('LCWGPT: Server selected:', serverName, 'analysis_id:', analysisId);

    // Ornek sorulari secilen sunucunun source type'ina gore guncelle
    if (typeof window.updateExampleQuestions === 'function') {
        window.updateExampleQuestions();
    }
};

// Sidebar send — mevcut handleQuery()'yi kullanir + sunucu seçim kontrolü
window.handleSidebarSend = function() {
    const input = document.getElementById('sidebarChatInput');
    if (!input || !input.value.trim()) return;

    const query = input.value.trim();
    input.value = '';

    // "sunucu değiştir" komutu kontrolü
    if (query.toLowerCase().includes('sunucu degistir') || query.toLowerCase().includes('sunucu değiştir')) {
        window.selectedChatServer = null;
        window.selectedChatAnalysisId = null;
        window.addSidebarUserMessage(query);
        // Ornek sorulari genel sete dondur
        if (typeof window.renderExampleQuestions === 'function') {
            window.renderExampleQuestions(null);
        }
        window.loadAnalyzedServers().then(function() {
            window.showServerSelection();
        });
        return;
    }

    // Sunucu seçilmemişse, önce seçim yaptır
    if (!window.selectedChatServer) {
        window.addSidebarUserMessage(query);
        window.addSidebarAIMessage('Lutfen once bir sunucu secin:');
        window.loadAnalyzedServers().then(function() {
            window.showServerSelection();
        });
        return;
    }

    // Sidebar'a kullanici mesajini goster
    window.addSidebarUserMessage(query);

    // Sunucu adını query'ye ekle (backend server detection için)
    const serverShort = window.selectedChatServer.split('.')[0];
    const enrichedQuery = query.toLowerCase().includes(serverShort.toLowerCase())
        ? query  // Zaten sunucu adı varsa ekleme
        : serverShort + ' ' + query;

    // Mevcut query input'a yaz ve handleQuery cagir
    const queryInput = document.getElementById('queryInput');
    if (queryInput) {
        queryInput.value = enrichedQuery;
    }
    if (window.handleQuery) {
        window.handleQuery();
    }
};

// DOMContentLoaded'da event listener'lari bagla
document.addEventListener('DOMContentLoaded', function() {
    // Sidebar toggle
    const toggleBtn = document.getElementById('sidebarToggleBtn');
    if (toggleBtn) {
        toggleBtn.addEventListener('click', window.toggleLcwgptSidebar);
    }

    // Sidebar close
    const closeBtn = document.getElementById('sidebarCloseBtn');
    if (closeBtn) {
        closeBtn.addEventListener('click', window.closeLcwgptSidebar);
    }

    // Sidebar send
    const sendBtn = document.getElementById('sidebarSendBtn');
    if (sendBtn) {
        sendBtn.addEventListener('click', window.handleSidebarSend);
    }

    // Enter key in sidebar input
    const sidebarInput = document.getElementById('sidebarChatInput');
    if (sidebarInput) {
        sidebarInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') window.handleSidebarSend();
        });
    }

    // Sidebar varsayilan olarak acik gelsin
    const sidebar = document.getElementById('lcwgptSidebar');
    if (sidebar && !sidebar.classList.contains('open')) {
        sidebar.classList.add('open');
    }

    // ML Metrics Sidebar da varsayilan olarak acik gelsin
    var mlSidebar = document.getElementById('mlModelPanel');
    if (mlSidebar && !mlSidebar.classList.contains('open')) {
        mlSidebar.classList.add('open');
    }

    // LCWGPT: Sunucu listesini yükle ve seçim göster
    // apiKey henüz set edilmemiş olabilir — bağlantı kurulunca tekrar çekilecek
    setTimeout(function() {
        if (window.apiKey) {
            window.loadAnalyzedServers().then(function() {
                if (window.chatServerList.length > 0 && !window.selectedChatServer) {
                    window.showServerSelection();
                }
            });
        }
    }, 1500);

    // Baslangicta genel ornek sorulari renderla
    if (typeof window.renderExampleQuestions === 'function') {
        window.renderExampleQuestions(null);
    }

    // ---- ML Metrics Sidebar toggle (header butonu) ----
    var mlToggleBtn = document.getElementById('mlSidebarToggleBtn');
    if (mlToggleBtn) {
        mlToggleBtn.addEventListener('click', function() {
            if (typeof window.toggleMLPanel === 'function') {
                window.toggleMLPanel();
            } else if (window.MLPanel && typeof window.MLPanel.toggle === 'function') {
                window.MLPanel.toggle();
            }
        });
    }

    // Quick-action ML butonunu da yeni toggle'a bagla
    var quickActionMLBtn = document.getElementById('toggleMLPanelBtn');
    if (quickActionMLBtn) {
        quickActionMLBtn.addEventListener('click', function() {
            if (typeof window.toggleMLPanel === 'function') {
                window.toggleMLPanel();
            } else if (window.MLPanel && typeof window.MLPanel.toggle === 'function') {
                window.MLPanel.toggle();
            }
        });
    }

    console.log('✅ LCWGPT Sidebar + ML Sidebar event listeners initialized');
});

