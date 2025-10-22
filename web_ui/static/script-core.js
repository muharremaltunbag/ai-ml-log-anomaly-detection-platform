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
        modalBody: document.getElementById('modalBody')
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
        console.log('Not connected after retry, skipping storage load');
        return;
    }
    
    try {
        console.log('Loading last anomaly analysis from storage...');
        
        // Backend'den storage kontrolü yap
        const response = await fetch(window.API_ENDPOINTS.query, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                query: "son anomali analizi",  // Backend'de anomali keyword'ü tetikler
                api_key: window.apiKey
            })
        });
        
        if (response.ok) {
            const result = await response.json();
            
            // Storage'dan veri geldiyse global değişkene ata ve yapıyı düzelt
            if (result.işlem === 'anomaly_from_storage' && result.sonuç?.from_storage) {
                // Storage info'yu doğru yere koy
                if (!result.storage_info && result.sonuç.storage_info) {
                    result.storage_info = result.sonuç.storage_info;
                }
                window.lastAnomalyResult = result;
                console.log('Storage anomaly loaded successfully:', {
                    analysis_id: result.sonuç.analysis_id,
                    anomaly_count: result.sonuç.anomaly_count,
                    has_critical: !!(result.sonuç.critical_anomalies?.length)
                });
                
                // Kullanıcıya bilgi ver
                const anomalyCount = result.sonuç.anomaly_count || 0;
                const timestamp = result.sonuç.storage_info?.timestamp || 'N/A';
                window.showNotification(
                    `Önceki analiz yüklendi: ${anomalyCount} anomali (${new Date(timestamp).toLocaleString('tr-TR')})`,
                    'info'
                );
                
                // Query input'a ipucu ekle
                if (window.elements.queryInput) {
                    window.elements.queryInput.placeholder = "Önceki analizle ilgili sorularınızı sorabilirsiniz...";
                }
                
                return true;
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

