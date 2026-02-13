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
    analyzedServers: '/api/analyzed-servers'
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
        // ML Panel Elementleri - YENİ
        mlPanel: document.getElementById('mlPanel'),
        mlPanelMinimizeBtn: document.getElementById('panelMinimizeBtn'),
        modelAccuracy: document.getElementById('modelAccuracy'),
        modelF1: document.getElementById('modelF1'),
        modelPrecision: document.getElementById('modelPrecision'),
        modelRecall: document.getElementById('modelRecall'),
        totalLogs: document.getElementById('totalLogs'),
        detectedAnomalies: document.getElementById('detectedAnomalies'),
        anomalyRate: document.getElementById('anomalyRate'),
        modelVersion: document.getElementById('modelVersion'),
        lastTrainingDate: document.getElementById('lastTrainingDate'),
        sampleLogInput: document.getElementById('sampleLogInput'),
        validateLogBtn: document.getElementById('validateLogBtn'),
        validationResult: document.getElementById('validationResult')
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

console.log('✅ Core module loaded successfully');
console.log('📊 Global variables available:', {
    apiKey: typeof window.apiKey,
    isConnected: window.isConnected,
    selectedDataSource: window.selectedDataSource,
    currentSessionId: window.currentSessionId ? 'initialized' : 'missing',
    API_ENDPOINTS: Object.keys(window.API_ENDPOINTS).length + ' endpoints'
});

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

    console.log('✅ LCWGPT Sidebar event listeners initialized');
});

