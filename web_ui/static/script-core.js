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
    exportAnalysis: '/api/export-analysis'
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

