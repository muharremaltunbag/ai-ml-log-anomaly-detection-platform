// web_ui\static\script.js

/**
 * LC Waikiki MongoDB Assistant - Frontend JavaScript
 * 
 * Bu dosya UI ile backend API arasındaki iletişimi sağlar.
 * Mevcut MongoDB Agent yapısına hiçbir müdahale yapmadan,
 * sadece API çağrıları üzerinden iletişim kurar.
 * 
 * NOT: Global değişkenler ve API endpoints script-core.js'de tanımlıdır.
 *      script-core.js bu dosyadan ÖNCE yüklenmeli!
web_ui */


//  web_ui/static/script.js

// ============================================
// GLOBAL DEĞİŞKENLERE ERİŞİM
// ============================================
// script-core.js'de tanımlanan global değişkenlere kolay erişim için alias'lar
// Bu değişkenler window objesi üzerinden tüm dosyalarda erişilebilir
var apiKey = window.apiKey;
var isConnected = window.isConnected;
var selectedDataSource = window.selectedDataSource;
var currentSessionId = window.currentSessionId;
var HISTORY_KEY = window.HISTORY_KEY;
var MAX_HISTORY_ITEMS = window.MAX_HISTORY_ITEMS;
var queryHistory = window.queryHistory;
var API_BASE = window.API_BASE;
var API_ENDPOINTS = window.API_ENDPOINTS;
var elements = window.elements;
var activateModel = window.activateModel;
var performStorageCleanup = window.performStorageCleanup;
var addStorageMenuButtons = window.addStorageMenuButtons;
var loadLastAnomalyFromStorage = window.loadLastAnomalyFromStorage;


// Kaydedilmiş analizi görüntüle
var viewStoredAnalysis = window.viewStoredAnalysis;



// ====== UUID Helper ======
function generateUUID() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
        var r = Math.random() * 16 | 0, v = c === 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
}
// Sayfa yüklendiğinde
document.addEventListener('DOMContentLoaded', async () => {
    // DOM element referanslarını initialize et
    window.initializeElements();
    elements = window.elements;
    
    // YENİ: ML Panel'i initialize et
    if (window.MLPanel) {
        window.MLPanel.initialize();
    }
    
    // Session ID oluştur
    if (!window.currentSessionId) {
        window.currentSessionId = `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
        console.log('📍 Session initialized:', window.currentSessionId);
    }
    
    initializeEventListeners();
    checkInitialStatus();
    restoreViewMode();
    
    // ✅ YENİ: Önce MongoDB'den otomatik yüklemeyi dene
    console.log('🚀 Attempting auto-load from MongoDB storage...');
    let dataLoaded = false;
    
    try {
        // autoLoadHistoryOnStartup MongoDB'den API key'i de yükleyecek
        dataLoaded = await window.autoLoadHistoryOnStartup();
        
        if (dataLoaded) {
            console.log('✅ Data successfully auto-loaded from MongoDB');
            
            // API key elementi varsa güncelle
            if (window.apiKey && elements.apiKeyInput) {
                elements.apiKeyInput.value = window.apiKey;
            }
            
            // UI durumunu güncelle
            if (window.isConnected) {
                updateStatus(true, window.apiKey);
            }
        }
    } catch (error) {
        console.error('Auto-load error:', error);
    }
    
    // Auto-load başarısızsa mevcut mantıkla devam et
    if (!dataLoaded) {
        // Boş history ile başla
        loadHistory();
        
        // LocalStorage'dan API key kontrolü
        const savedApiKey = localStorage.getItem('saved_api_key');
        
        if (savedApiKey && elements.apiKeyInput) {
            console.log('📌 Found saved API key in localStorage, auto-connecting...');
            elements.apiKeyInput.value = savedApiKey;
            
            // Otomatik bağlan
            await handleConnect();
            
            // Bağlantı başarılıysa MongoDB verilerini yükle
            if (window.isConnected) {
                console.log('📊 Loading all data from MongoDB...');
                showNotification('MongoDB\'den veriler yükleniyor...', 'info');
                
                try {
                    // Paralel olarak tüm verileri yükle
                    const results = await Promise.all([
                        loadHistory(),
                        loadAnomalyHistoryFromMongoDB({limit: 50}),
                        loadAndMergeDBAHistory(),
                        loadAndMergeMSSQLHistory(),
                        checkStorageSize()
                    ]);

                    console.log('✅ All MongoDB data loaded successfully');
                    console.log(`   📝 Query History: ${queryHistory.length} items`);
                    console.log(`   🔍 Anomaly History: ${results[1]?.length || 0} items`);
                    console.log(`   📊 DBA History merged`);
                    console.log(`   🗄️ MSSQL History merged`);
                    
                    showNotification('Tüm veriler MongoDB\'den yüklendi', 'success');
                    
                    // History display'i güncelle
                    updateHistoryDisplay();
                    
                    // ✅ YENİ: Son anomaly analizini göster
                    if (window.displayLastAnomalyAnalysis) {
                        await window.displayLastAnomalyAnalysis();
                    }
                    
                } catch (error) {
                    console.error('Error loading MongoDB data:', error);
                    showNotification('Bazı veriler yüklenemedi', 'warning');
                }
            }
        } else {
            console.log('ℹ️ No saved API key, manual connection required');
            
            // ✅ YENİ: Development ortamında test API key ile otomatik bağlan
            if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
                console.log('🔧 Development mode - auto-connecting with test API key...');
                
                const testApiKey = 'lcw-test-2024';
                if (elements.apiKeyInput) {
                    elements.apiKeyInput.value = testApiKey;
                    await handleConnect();
                    
                    // Test bağlantısı başarılıysa veri yükle
                    if (window.isConnected) {
                        try {
                            await Promise.all([
                                loadHistory(),
                                loadAnomalyHistoryFromMongoDB({limit: 50}),
                                loadAndMergeDBAHistory(),
                                loadAndMergeMSSQLHistory()
                            ]);
                            updateHistoryDisplay();
                            
                            // Son anomaly analizini göster
                            if (window.displayLastAnomalyAnalysis) {
                                await window.displayLastAnomalyAnalysis();
                            }
                        } catch (error) {
                            console.error('Test data loading error:', error);
                        }
                    }
                }
            }
        }
    }
});


/**
 * Event listener'ları başlat - GÜVENLİ VERSİYON
 */
function initializeEventListeners() {
    console.log('Initializing event listeners... (Robust Version)');
    
    // Bağlan butonu
    if (elements.connectBtn) {
        elements.connectBtn.addEventListener('click', handleConnect);
    }
    
    // Enter tuşu ile bağlan
    if (elements.apiKeyInput) {
        elements.apiKeyInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') handleConnect();
        });
    }
    
    // Sorgu gönder butonu
    if (elements.queryBtn) {
        elements.queryBtn.addEventListener('click', handleQuery);
    }
    
    // Enter tuşu ile sorgu gönder (Ctrl+Enter)
    if (elements.queryInput) {
        elements.queryInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && e.ctrlKey) handleQuery();
        });
    }
    
    // Sistem Reset butonu
    const systemResetBtn = document.getElementById('systemResetBtn');
    if (systemResetBtn) {
        systemResetBtn.addEventListener('click', openSystemResetModal);
    }
    initSystemResetModal();
    
    // Log Yükle butonu
    const logUploadBtn = document.getElementById('logUploadBtn');
    if (logUploadBtn) {
        logUploadBtn.addEventListener('click', () => {
            console.log('Log upload button clicked');
            const fileInput = document.getElementById('logFileInput');
            if (fileInput) fileInput.click();
        });
    }

    // Dosya yükleme için event listener'lar
    const logFileInput = document.getElementById('logFileInput');
    const uploadDropzone = document.getElementById('uploadDropzone');
    
    if (logFileInput) {
        logFileInput.addEventListener('change', (e) => {
            console.log('File input changed event triggered');
            if (window.handleFileUpload) {
                window.handleFileUpload(e);
            } else {
                console.error('❌ CRITICAL: handleFileUpload function not found in window scope!');
                alert('Dosya yükleme modülü yüklenemedi. Lütfen sayfayı yenileyin.');
            }
        });
    }
    
    if (uploadDropzone) {
        uploadDropzone.addEventListener('click', () => {
            if (logFileInput) logFileInput.click();
        });
        
        // Drag and Drop
        uploadDropzone.addEventListener('dragover', (e) => {
            e.preventDefault();
            e.stopPropagation();
            uploadDropzone.classList.add('drag-over');
        });
        
        uploadDropzone.addEventListener('dragleave', (e) => {
            e.preventDefault();
            e.stopPropagation();
            uploadDropzone.classList.remove('drag-over');
        });
        
        uploadDropzone.addEventListener('drop', (e) => {
            e.preventDefault();
            e.stopPropagation();
            uploadDropzone.classList.remove('drag-over');
            
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                console.log('File dropped via drag-and-drop');
                if (window.handleFileUpload) {
                    window.handleFileUpload({ target: { files: files } });
                } else {
                    console.error('❌ CRITICAL: handleFileUpload function not found!');
                }
            }
        });
    }

    // Anomali Analizi butonu
    const anomalyBtn = document.getElementById('anomalyAnalysisBtn');
    if (anomalyBtn) {
        anomalyBtn.addEventListener('click', () => {
            console.log('Anomaly Analysis Button clicked!');

            // Inline config section'a scroll yap (Figma layout)
            const configSection = document.getElementById('analysisConfigSection');
            if (configSection) {
                configSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
                configSection.style.outline = '2px solid var(--lcw-blue)';
                setTimeout(() => { configSection.style.outline = 'none'; }, 2000);
            }
            
            // Dosyaları güncelle ama data source'u resetleme
            if (window.updateUploadedFilesList) window.updateUploadedFilesList();
            else if (typeof updateUploadedFilesList === 'function') updateUploadedFilesList();
            
            // Eğer önceden upload seçiliyse, tekrar seç
            if (typeof selectedDataSource !== 'undefined' && selectedDataSource === 'upload') {
                const uploadRadio = document.querySelector('input[name="dataSource"][value="upload"]');
                if (uploadRadio) uploadRadio.checked = true;
                if (window.updateSourceInputs) window.updateSourceInputs('upload');
                else if (typeof updateSourceInputs === 'function') updateSourceInputs('upload');
            }
            // OpenSearch seçiliyse listeleri yükle
            else if (typeof selectedDataSource !== 'undefined' && selectedDataSource === 'opensearch' && (window.isConnected || isConnected)) {
                const osRadio = document.querySelector('input[name="dataSource"][value="opensearch"]');
                if (osRadio) osRadio.checked = true;
                if (window.updateSourceInputs) window.updateSourceInputs('opensearch');
                else if (typeof updateSourceInputs === 'function') updateSourceInputs('opensearch');
                setTimeout(() => {
                    if (window.loadMongoDBHosts) window.loadMongoDBHosts();
                    else if (typeof loadMongoDBHosts === 'function') loadMongoDBHosts();
                    if (window.loadClusters) window.loadClusters();
                    else if (typeof loadClusters === 'function') loadClusters();
                }, 200);
            }
        });
    }

    // DBA Analizi butonu
    const dbaBtn = document.getElementById('dbaAnalysisBtn');
    if (dbaBtn) {
        dbaBtn.addEventListener('click', () => {
            console.log('DBA Analysis Button clicked!');
            if (window.openDBAAnalysisModal) window.openDBAAnalysisModal();
            else if (typeof openDBAAnalysisModal === 'function') openDBAAnalysisModal();
        });
    }
    
    // Event delegation for dynamically loaded buttons
    document.addEventListener('click', function(e) {
        if (e.target && e.target.id === 'dbaAnalysisBtn') {
            e.preventDefault();
            if (window.openDBAAnalysisModal) window.openDBAAnalysisModal();
            else if (typeof openDBAAnalysisModal === 'function') openDBAAnalysisModal();
        }
    });
    
    // Anomaly Modal içindeki Analizi Başlat butonu
    const startAnalysisBtn = document.getElementById('startAnalysisBtn');
    if (startAnalysisBtn) {
        startAnalysisBtn.addEventListener('click', (e) => {
            console.log('Start Analysis clicked');
            if (window.handleAnalyzeLog) window.handleAnalyzeLog(e);
            else if (typeof handleAnalyzeLog === 'function') handleAnalyzeLog(e);
            else console.error('handleAnalyzeLog function missing');
        });
    }

    // Refresh hosts button - CLUSTER DESTEĞİ İLE
    const refreshBtn = document.getElementById('refreshHostsBtn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', () => {
            const hostMode = document.querySelector('input[name="hostSelectionMode"]:checked')?.value || 'single';
            
            if (hostMode === 'single') {
                if (window.loadMongoDBHosts) window.loadMongoDBHosts();
                else if (typeof loadMongoDBHosts === 'function') loadMongoDBHosts();
                showNotification('Host listesi yenileniyor...', 'info');
            } else if (hostMode === 'cluster') {
                if (window.loadClusters) window.loadClusters();
                else if (typeof loadClusters === 'function') loadClusters();
                showNotification('Cluster listesi yenileniyor...', 'info');
            }
        });
    }

    // MSSQL Refresh hosts button
    const refreshMSSQLBtn = document.getElementById('refreshMSSQLHostsBtn');
    if (refreshMSSQLBtn) {
        refreshMSSQLBtn.addEventListener('click', () => {
            if (window.loadMSSQLHosts) window.loadMSSQLHosts();
            else if (typeof loadMSSQLHosts === 'function') loadMSSQLHosts();
            showNotification('MSSQL host listesi yenileniyor...', 'info');
        });
    }

    // Örnek sorgu chip'leri
    document.querySelectorAll('.chip').forEach(chip => {
        chip.addEventListener('click', (e) => {
            if (elements.queryInput) {
                elements.queryInput.value = e.target.dataset.query;
                elements.queryInput.focus();
            }
        });
    });
    
    // Modal kapatma
    const modalClose = document.querySelector('#modal .close');
    if (modalClose) {
        modalClose.addEventListener('click', closeModal);
    }
    
    window.addEventListener('click', (e) => {
        if (elements.modal && e.target === elements.modal) closeModal();
    });
    
    // Anomaly Modal kapatma butonu için event listener ekle
    const anomalyClose = document.querySelector('#anomalyModal .close');
    if (anomalyClose) {
        anomalyClose.addEventListener('click', () => {
            if (window.closeAnomalyModal) window.closeAnomalyModal();
            else if (typeof closeAnomalyModal === 'function') closeAnomalyModal();
            else {
                const m = document.getElementById('anomalyModal');
                if (m) m.style.display = 'none';
            }
        });
    }
    
    // Anomaly modal dışına tıklama ile kapatma
    window.addEventListener('click', (e) => {
        const anomalyModal = document.getElementById('anomalyModal');
        if (anomalyModal && e.target === anomalyModal) {
            if (window.closeAnomalyModal) window.closeAnomalyModal();
            else if (typeof closeAnomalyModal === 'function') closeAnomalyModal();
            else anomalyModal.style.display = 'none';
        }
    });

    // Veri kaynağı seçimi değiştiğinde
    document.querySelectorAll('input[name="dataSource"]').forEach(radio => {
        radio.addEventListener('change', (e) => {
            console.log('Data source changed from', selectedDataSource, 'to', e.target.value);
            // Global değişkeni güncelle
            window.selectedDataSource = e.target.value;
            selectedDataSource = e.target.value;
            updateSourceInputs(selectedDataSource);
            
            // YENİ: OpenSearch seçildiğinde listeleri otomatik yükle
            if (e.target.value === 'opensearch' && isConnected) {
                setTimeout(() => {
                    loadMongoDBHosts();  // Host listesini yükle
                    loadClusters();      // Cluster listesini yükle
                }, 100);
            }

            // MSSQL OpenSearch seçildiğinde MSSQL listesini yükle
            if (e.target.value === 'mssql_opensearch' && isConnected) {
                setTimeout(() => {
                    loadMSSQLHosts();  // MSSQL Host listesini yükle
                }, 100);
            }
        });
    });

    // Host selection mode (Single/Cluster) değişimi için 
    document.querySelectorAll('input[name="hostSelectionMode"]').forEach(radio => {
        radio.addEventListener('change', (e) => {
            console.log('Host selection mode changed to:', e.target.value);
            const mode = e.target.value;
            
            const singleHostDiv = document.getElementById('singleHostSelection');
            const clusterDiv = document.getElementById('clusterSelection');
            
            if (mode === 'single') {
                // Single mode: host dropdown göster
                if (singleHostDiv) singleHostDiv.style.display = 'block';
                if (clusterDiv) clusterDiv.style.display = 'none';
                
                // Host'ları yükle (eğer yüklenmemişse)
                const hostSelect = document.getElementById('mongodbHostSelect');
                if (hostSelect && hostSelect.options.length <= 1) {
                    loadMongoDBHosts();
                }
            } else if (mode === 'cluster') {
                // Cluster mode: cluster dropdown göster
                if (singleHostDiv) singleHostDiv.style.display = 'none';
                if (clusterDiv) clusterDiv.style.display = 'block';
                
                // Cluster'ları yükle (eğer yüklenmemişse)
                const clusterSelect = document.getElementById('clusterSelect');
                if (clusterSelect && clusterSelect.options.length <= 1) {
                    loadClusters();
                }
            }
            
            // Validation'ı güncelle
            if (selectedDataSource === 'opensearch') {
                validateAnalysisButton();
            }
        });
    });

    // Cluster dropdown için change event listener - YENİ
    document.getElementById('clusterSelect')?.addEventListener('change', (e) => {
        console.log('Cluster selected:', e.target.value);
        const clusterId = e.target.value;
        
        if (clusterId) {
            // Seçilen cluster'ın host'larını yükle ve göster
            loadClusterHosts(clusterId);
            
            // Validation'ı güncelle
            if (selectedDataSource === 'opensearch') {
                validateAnalysisButton();
            }
        }
    });

    // YENİ: Custom date/time selection değişimi için  
    document.querySelectorAll('input[name="modalTimeRange"]').forEach(radio => {
        radio.addEventListener('change', (e) => {
            console.log('Time range changed to:', e.target.value);
            const customDateInputs = document.getElementById('customDateInputs');
            
            if (e.target.value === 'custom') {
                // Custom seçildi, date input'ları göster
                if (customDateInputs) {
                    customDateInputs.style.display = 'block';
                    
                    // Test için default değerleri set et
                    const startInput = document.getElementById('customStartTime');
                    const endInput = document.getElementById('customEndTime');
                    
                    if (startInput && !startInput.value) {
                        // Test senaryosu: 10.09.2025 16:09
                        startInput.value = '2025-09-10T16:09';
                    }
                    if (endInput && !endInput.value) {
                        // Test senaryosu: 10.09.2025 16:11
                        endInput.value = '2025-09-10T16:11';
                    }
                }
            } else {
                // Diğer seçenekler, custom date'i gizle
                if (customDateInputs) {
                    customDateInputs.style.display = 'none';
                }
            }
        });
    });
    
    // MongoDB host seçimi değiştiğinde
    document.getElementById('mongodbHostSelect')?.addEventListener('change', (e) => {
        console.log('MongoDB host selected:', e.target.value);
        if (selectedDataSource === 'opensearch') {
            validateAnalysisButton();
        }
    });

    // MSSQL host seçildiğinde validate tetikle
    document.getElementById('mssqlHostSelect')?.addEventListener('change', (e) => {
        console.log('MSSQL host selected:', e.target.value);
        if (selectedDataSource === 'mssql_opensearch') {
            validateAnalysisButton();
        }
    });
    
    // Dosya radio button'larına event listener ekle (Event delegation)
    document.addEventListener('change', function(e) {
        if (e.target.matches('input[name="logFile"]')) {
            e.stopPropagation(); // Event bubbling'i durdur
            console.log('File selected:', e.target.value);
            // Upload kaynağı seçiliyse validation'ı tetikle
            if (selectedDataSource === 'upload') {
                validateAnalysisButton();
            }
        }
    });
    
    // Geçmiş tab'ları
    document.querySelectorAll('.history-tab').forEach(tab => {
        tab.addEventListener('click', (e) => {
            const selectedTab = e.target.dataset.tab;
            console.log('History tab selected:', selectedTab);
            console.log('Total items:', queryHistory.length);
            console.log('Anomaly items:', queryHistory.filter(h => h.type === 'anomaly').length);
            console.log('Chatbot items:', queryHistory.filter(h => h.type === 'chatbot').length);
            
            document.querySelectorAll('.history-tab').forEach(t => t.classList.remove('active'));
            e.target.classList.add('active');
            updateHistoryDisplay(selectedTab);
        });
    });

    // Geçmiş butonları
    document.getElementById('clearHistoryBtn').addEventListener('click', clearHistory);
    document.getElementById('exportHistoryBtn').addEventListener('click', exportHistory);
    
    // console.log ile hata ayıklama
    window.addEventListener('error', (e) => {
        console.error('Global error caught:', e.message);
    });

    // ML Panel Toggle butonu — Yeni sidebar class-based toggle
    // Not: Asil event listener script-core.js DOMContentLoaded'da baglaniyor.
    // Burasi backward compat icin korunuyor ama cifte listener onleniyor.
    // (script-core.js zaten toggleMLPanelBtn'i bagliyor)
    
    console.log('✅ Event listeners initialized successfully');
}

/**
 * İlk durum kontrolü
 */
async function checkInitialStatus() {
    console.log('Checking initial status...'); // DEBUG LOG
    
    try {
        const response = await fetch(API_ENDPOINTS.status);
        const data = await response.json();
        
        console.log('Initial status response:', data); // DEBUG LOG
        
        if (data.status === 'online') {
            console.log('System is online'); // DEBUG LOG
            updateStatus('online', 'Sistem hazır - API anahtarı ile bağlanın');
        } else {
            console.log('System is offline'); // DEBUG LOG
            updateStatus('offline', 'Sistem çevrimdışı');
        }
    } catch (error) {
        console.error('Initial status check failed:', error); // DEBUG LOG
        updateStatus('offline', 'Bağlantı hatası');
    }
}


/**
 * API bağlantısını kur
 */
async function handleConnect() {
    const key = elements.apiKeyInput.value.trim();
    
    console.log('handleConnect called with API key length:', key.length); // DEBUG LOG
    
    if (!key) {
        console.log('API key is empty'); // DEBUG LOG
        showNotification('Lütfen API anahtarını girin', 'error');
        return;
    }
    
    elements.connectBtn.disabled = true;
    elements.connectBtn.textContent = 'BAĞLANIYOR...';

    try {
        console.log('Attempting to connect to API...'); // DEBUG LOG
        // Test için collections endpoint'ini kullan
        const response = await fetch(`${API_ENDPOINTS.collections}?api_key=${key}`);
        
        console.log('API response status:', response.status); // DEBUG LOG

        if (response.ok) {
            // Global değişkenleri güncelle (helper fonksiyonlar ile)
            window.updateApiKey(key);
            window.updateConnectionStatus(true);

            // ✅ YENİ: API key'i hem localStorage hem MongoDB'ye kaydet
            localStorage.setItem('saved_api_key', key);
            console.log('✅ API key saved to localStorage');

            // MongoDB'ye de kaydet
            if (typeof saveApiKeyToMongoDB === 'function') {
                try {
                    await saveApiKeyToMongoDB(key);
                    console.log('✅ API key sent to MongoDB via backend endpoint');
                } catch (e) {
                    console.warn('❌ API key MongoDB\'ye kaydedilemedi:', e);
                }
            } else {
                console.warn('saveApiKeyToMongoDB fonksiyonu tanımlı değil!');
            }

            console.log('Connection successful, updating UI...'); // DEBUG LOG
            
            // UI'yi güncelle
            elements.mainContent.style.display = 'block';
            elements.apiKeyInput.disabled = true;

            // ML Sidebar: Baglaninca otomatik ac ve metrik yukle
            if (window.MLPanel) {
                setTimeout(() => {
                    if (window.MLPanel.show) window.MLPanel.show();
                }, 500);
            }
            elements.connectBtn.textContent = 'BAĞLANDI';
            elements.connectBtn.classList.add('connected');

            addStorageMenuButtons();   // ✅ storage menüsünü ekle

            // YENİ: Storage'dan son anomali analizini yükle
            setTimeout(async () => {
                const loaded = await loadLastAnomalyFromStorage();
                if (loaded) {
                    console.log('Previous anomaly analysis ready for chat queries');
                }
            }, 1500);
            
            updateStatus('online', 'Sistem bağlantısı başarılı');
            showNotification('Başarıyla bağlandı!', 'success');
            
            // İlk koleksiyon listesini göster
            const data = await response.json();
            if (data.collections && data.collections.length > 0) {
                console.log(`${data.collections.length} koleksiyon bulundu`);
            }
        } else {
            console.log('API connection failed with status:', response.status); // DEBUG LOG
            throw new Error('Geçersiz API anahtarı');
        }
    } catch (error) {
        console.error('Connection error:', error); // DEBUG LOG
        showNotification(error.message || 'Bağlantı hatası', 'error');
        elements.connectBtn.disabled = false;
        elements.connectBtn.textContent = 'BAĞLAN';
    }
}

/**
 * MongoDB sorgusunu gönder
 */
async function handleQuery() {
    const query = elements.queryInput.value.trim();
    
    // ENHANCED DEBUG - Query trim sorununu tespit için
    console.log('=== QUERY DEBUG START ===');
    console.log('1. Original input value:', elements.queryInput.value);
    console.log('2. After trim:', query);
    console.log('3. Query length:', query.length);
    console.log('4. Query bytes:', new TextEncoder().encode(query).length);
    console.log('5. First 50 chars:', query.substring(0, 50));
    console.log('6. Has lastAnomalyResult:', !!window.lastAnomalyResult);
    if (window.lastAnomalyResult?.storage_info) {
        console.log('7. Analysis ID:', window.lastAnomalyResult.storage_info.analysis_id);
    }
    console.log('=== QUERY DEBUG END ===');
        
    if (!query) {
        console.log('Query is empty'); // DEBUG LOG
        showNotification('Lütfen bir sorgu girin', 'warning');
        return;
    }
    
    // YENİ: Query uzunluk kontrolü
    const MAX_QUERY_LENGTH = 10000; // Backend ile aynı limit
    if (query.length > MAX_QUERY_LENGTH) {
        console.warn(`Query too long: ${query.length} characters (max: ${MAX_QUERY_LENGTH})`);
        showNotification(`Sorgu çok uzun! (${query.length} karakter, maksimum: ${MAX_QUERY_LENGTH})`, 'error');
        
        // Kullanıcıya öneride bulun
        showNotification('Lütfen sorgunuzu kısaltın veya birden fazla sorguya bölün.', 'info');
        return;
    }
    
    if (!isConnected) {
        console.log('Not connected to API'); // DEBUG LOG
        showNotification('Önce bağlantı kurmalısınız', 'error');
        return;
    }
    
    // UI'yi hazırla
    showLoader(true);
    elements.queryBtn.disabled = true;
    elements.resultSection.style.display = 'none';
    
    try {
        // YENİ: Chat anomali sorgusu tespiti - Daha geniş keyword listesi
        const chatAnomalyKeywords = [
            'anomali', 'anomaly', 'log', 'analiz', 'analyze', 'kritik', 'hata', 'sorun', 
            'problem', 'uyarı', 'warning', 'error', 'critical', 'tespit', 'detect', 'bul', 'göster',
            'listele', 'getir', 'nedir', 'açıkla', 'yorumla', 'özetle',
            'bağlantı hatası', 'zaman aşımı', 'kesinti',
            'primary değişti', 'replikasyon gecikmesi',
            'yavaş sorgu',
            'disk dolu', 'yüksek bellek', 'yüksek cpu',
            'journal hatası', 'çöktü',
            'çalışmıyor', 'yavaş', 'donuyor',
            'bağlanamıyor', 'disk doldu', 'bellek doldu',
            'replikasyon hatası', 'neden çalışmıyor', 'bozuldu',
            'takılıyor', 'bağlantı', 'bağlantı sorunu',
            'erişim', 'secondary', 'primary'
        ];

        // DEBUG: Detaylı kontrol
        console.log('=== CHAT ANOMALY DETECTION DEBUG ===');
        console.log('Query:', query);
        console.log('Query lowercase:', query.toLowerCase());
        console.log('Has lastAnomalyResult:', !!window.lastAnomalyResult);
        
        const hasKeyword = chatAnomalyKeywords.some(keyword => 
            query.toLowerCase().includes(keyword)
        ) && (
            query.toLowerCase().includes('anomali') || 
            query.toLowerCase().includes('log') ||
            window.lastAnomalyResult // Önceki anomali analizi varsa
        );
        console.log('Has matching keyword:', hasKeyword);
        
        const hasAnomalyOrLog = query.toLowerCase().includes('anomali') || 
                               query.toLowerCase().includes('log');
        console.log('Has anomaly or log keyword:', hasAnomalyOrLog);
        
        // Sidebar'dan sunucu seçildiyse her zaman chat anomaly query olarak değerlendir
        const hasSidebarServer = !!window.selectedChatServer;
        const isChatAnomalyQuery = hasSidebarServer || (hasKeyword && (hasAnomalyOrLog || window.lastAnomalyResult));
        console.log('Has sidebar server:', hasSidebarServer);
        console.log('Is chat anomaly query:', isChatAnomalyQuery);
        console.log('=== END DEBUG ===');

        // Chat anomali sorgusu kontrolü
        if (isChatAnomalyQuery) {
            console.log('🔍 DEBUG: Chat anomaly query detected, checking lastAnomalyResult...');
            console.log('🔍 DEBUG: window.lastAnomalyResult exists:', !!window.lastAnomalyResult);
            console.log('🔍 DEBUG: window.selectedChatServer:', window.selectedChatServer);
            console.log('🔍 DEBUG: window.selectedChatAnalysisId:', window.selectedChatAnalysisId);

            // Sidebar'dan sunucu seçildiyse (analysis_id olsun olmasın) lastAnomalyResult gerekmez
            const hasSidebarAnalysisId = !!window.selectedChatServer;

            // Eğer lastAnomalyResult yoksa ve sidebar'dan da seçim yapılmamışsa storage'dan yüklemeyi dene
            if (!window.lastAnomalyResult && !hasSidebarAnalysisId) {
                console.log('🔍 DEBUG: No lastAnomalyResult and no sidebar selection, attempting to load from storage...');

                try {
                    const loaded = await loadLastAnomalyFromStorage();
                    console.log('🔍 DEBUG: loadLastAnomalyFromStorage() returned:', loaded);

                    if (!loaded) {
                        console.log('⚠️ DEBUG: No storage data found, will proceed with normal query');
                        showNotification('Önceki analiz bulunamadı, yeni analiz yapılacak', 'info');
                        showLoader(false);
                        elements.queryBtn.disabled = false;
                    } else {
                        console.log('✅ DEBUG: Storage load successful, window.lastAnomalyResult now available');
                    }
                } catch (error) {
                    console.error('❌ DEBUG: Error in loadLastAnomalyFromStorage():', error);
                    showNotification('Storage yüklenirken hata oluştu', 'error');
                    showLoader(false);
                    elements.queryBtn.disabled = false;
                    return;
                }
            } else if (hasSidebarAnalysisId) {
                console.log('✅ DEBUG: Using sidebar-selected server:', window.selectedChatServer, 'analysis_id:', window.selectedChatAnalysisId);
            } else {
                console.log('✅ DEBUG: window.lastAnomalyResult already exists, skipping storage load');
            }

            // Sidebar seçimi veya lastAnomalyResult varsa devam et
            if (window.lastAnomalyResult || hasSidebarAnalysisId) {
                console.log('✅ Chat anomaly query CONFIRMED, using LCWGPT endpoint');
                console.log('🔍 DEBUG: lastAnomalyResult structure check:');
                console.log('🔍 DEBUG: - storage_info:', !!window.lastAnomalyResult?.storage_info);
                console.log('🔍 DEBUG: - storage_id:', !!window.lastAnomalyResult?.storage_id);
                console.log('🔍 DEBUG: - analysis_id from storage_info:', window.lastAnomalyResult?.storage_info?.analysis_id);
                console.log('🔍 DEBUG: - selectedChatAnalysisId:', window.selectedChatAnalysisId);

                // Sidebar'dan sunucu seçildiyse o sunucunun analysis_id'sini öncelikli kullan
                const lastAnalysisId = window.selectedChatAnalysisId ||
                                      window.lastAnomalyResult?.storage_info?.analysis_id ||
                                      window.lastAnomalyResult?.storage_id;

                // ✅ YENİ: Request ID Oluştur
                const requestId = generateUUID();
                console.log('Generated Request ID for Chat:', requestId);

                // --- PROGRESS FEEDBACK ENTEGRASYONU (CHAT MODU) ---
                if (window.AnomalyProgress) {
                    showLoader(false);

                    // Adımlar (Önceki adımda eklemiştik, aynen koruyoruz)
                    window.AnomalyProgress.steps = [
                        { id: 'context', text: 'Analiz bağlamı storage\'dan yükleniyor...', icon: '🗄️', duration: 1500 },
                        { id: 'connect', text: 'LCWGPT servisi ile bağlantı kuruluyor...', icon: '🔌', duration: 2000 },
                        { id: 'chunk',   text: 'Veri setleri parçalanıyor (Chunking)...', icon: '🧩', duration: 1500 },
                        { id: 'analyze', text: 'Yapay zeka analizi yapılıyor (Bu işlem zaman alabilir)...', icon: '🧠', duration: 15000 },
                        { id: 'merge',   text: 'Yanıtlar birleştiriliyor ve özetleniyor...', icon: '✨', duration: 1000 }
                    ];

                    // ✅ DEĞİŞİKLİK: requestId ile show() çağırıyoruz
                    window.AnomalyProgress.show(requestId);

                    // Başlık güncelleme (Mevcut kod aynen kalıyor)
                    setTimeout(() => {
                        const progressModal = document.getElementById('anomalyProgressModal');
                        if (progressModal) {
                            const headerTitle = progressModal.querySelector('.progress-header h3');
                            const headerDesc = progressModal.querySelector('.progress-header p');
                            if (headerTitle) {
                                headerTitle.innerHTML = '🤖 LCWGPT Asistan Devrede';
                                headerTitle.style.color = '#9b59b6';
                            }
                            if (headerDesc) headerDesc.textContent = 'Büyük veri setleri parçalı olarak işleniyor, lütfen bekleyin...';
                        }
                    }, 50);

                } else {
                    showLoader(true);
                }

                try {
                    // API İsteği
                    const chatResponse = await fetch('/api/chat-query-anomalies', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            query: query,
                            api_key: apiKey,
                            analysis_id: lastAnalysisId,
                            request_id: requestId  //  ID'yi backend'e gönderiyoruz
                        })
                    });

                console.log('LCWGPT response status:', chatResponse.status);

                if (chatResponse.ok) {
                    const chatResult = await chatResponse.json();

                    // YENİ: Progress Tamamla
                    if (window.AnomalyProgress) window.AnomalyProgress.complete();
                    else showLoader(false);

                    console.log('LCWGPT result:', chatResult);

                    // ✅ SIDEBAR AI YANIT — sidebar'da boş cevap sorununu gider
                    if (typeof window.addSidebarAIMessage === 'function') {
                        if (chatResult.status === 'success' && chatResult.ai_response) {
                            // Sidebar'a formatlanmış AI yanıtı ekle
                            const sidebarHtml = window.formatSidebarAIResponse
                                ? window.formatSidebarAIResponse(chatResult)
                                : chatResult.ai_response.substring(0, 2000) + (chatResult.ai_response.length > 2000 ? '...' : '');
                            window.addSidebarAIMessage(sidebarHtml);
                        } else {
                            // Hata veya boş yanıt durumunda bilgilendirme
                            window.addSidebarAIMessage(
                                '⚠️ ' + (chatResult.message || 'Yanıt alınamadı. Lütfen tekrar deneyin.')
                            );
                        }
                    }

                    // ✅ YENİ: Güvenli fonksiyon çağrısı - Race condition önleme
                    if (typeof window.displayChatAnomalyResult === 'function') {
                        window.displayChatAnomalyResult(chatResult, query);
                    } else if (typeof window.displayChatQueryResult === 'function') {
                        // Fallback: Aynı fonksiyonun alternatif ismi
                        console.warn('displayChatAnomalyResult not found, using displayChatQueryResult');
                        window.displayChatQueryResult(chatResult, query);
                    } else {
                        console.error('❌ No chat display function available!');
                        window.showNotification('Chat sonucu gösterilemedi. Sayfayı yenileyin.', 'error');
                    }
                    
                    
                    // History'ye ekle - chat-anomaly olarak işaretle
                    const historyItem = {
                        id: Date.now(),
                        timestamp: new Date().toISOString(),
                        query: query,
                        type: 'chat-anomaly',
                        category: 'anomaly',  // Anomaly tab'ında görünsün
                        result: chatResult,
                        durum: 'tamamlandı',
                        işlem: 'chat_query',
                        hasAIResponse: true
                    };

                    queryHistory.unshift(historyItem);
                    if (queryHistory.length > MAX_HISTORY_ITEMS) {
                        queryHistory = queryHistory.slice(0, MAX_HISTORY_ITEMS);
                    }
                    saveHistory();
                    updateHistoryDisplay();

                    // ✅ SORGU SONRASI SUNUCU SEÇİMİ — her yanıttan sonra tekrar göster
                    window.selectedChatServer = null;
                    window.selectedChatAnalysisId = null;

                    // Kısa gecikme ile (yanıt render olduktan sonra) sunucu seçim ekranını göster
                    setTimeout(function() {
                        if (typeof window.loadAnalyzedServers === 'function') {
                            window.loadAnalyzedServers().then(function() {
                                if (typeof window.addSidebarAIMessage === 'function') {
                                    window.addSidebarAIMessage('Başka bir sunucu hakkında soru sormak ister misiniz?');
                                }
                                if (typeof window.showServerSelection === 'function') {
                                    window.showServerSelection();
                                }
                                // Örnek soruları genel sete döndür
                                if (typeof window.renderExampleQuestions === 'function') {
                                    window.renderExampleQuestions(null);
                                }
                            });
                        }
                    }, 800);

                    return; // Burada return ediyoruz
                } else {
                    console.error('LCWGPT request failed:', chatResponse.status);
                    const errorText = await chatResponse.text();
                    console.error('Error response:', errorText);
                    // ✅ Sidebar'a HTTP hata mesajı
                    if (typeof window.addSidebarAIMessage === 'function') {
                        window.addSidebarAIMessage('❌ Yanıt alınamadı (HTTP ' + chatResponse.status + '). Lütfen tekrar deneyin.');
                    }
                    // Hata sonrası da sunucu seçimini tekrar göster
                    window.selectedChatServer = null;
                    window.selectedChatAnalysisId = null;
                    setTimeout(function() {
                        if (typeof window.showServerSelection === 'function') window.showServerSelection();
                    }, 500);
                }
            } catch (error) {
                console.error('LCWGPT error:', error);
                // YENİ: Progress Hata Gösterimi
                if (window.AnomalyProgress) window.AnomalyProgress.error();
                else showLoader(false);

                showNotification('Yapay zeka yanıtı alınırken hata oluştu.', 'error');
                // ✅ Sidebar'a exception hata mesajı
                if (typeof window.addSidebarAIMessage === 'function') {
                    window.addSidebarAIMessage('❌ Bir hata oluştu. Lütfen tekrar deneyin.');
                }
                // Hata sonrası da sunucu seçimini tekrar göster
                window.selectedChatServer = null;
                window.selectedChatAnalysisId = null;
                setTimeout(function() {
                    if (typeof window.showServerSelection === 'function') window.showServerSelection();
                }, 500);
            }
            }
        } else {
            console.log('❌ NOT a chat anomaly query or no lastAnomalyResult');
            console.log('Proceeding with normal query flow...');
        }

        const queryBody = {
            query: query,
            api_key: apiKey
        };
        
        // ENHANCED DEBUG - API isteği öncesi
        console.log('=== API REQUEST DEBUG ===');
        console.log('1. queryBody object:', queryBody);
        console.log('2. query field value:', queryBody.query);
        console.log('3. query field length:', queryBody.query.length);
        console.log('4. Stringified body:', JSON.stringify(queryBody));
        console.log('5. Stringified length:', JSON.stringify(queryBody).length);
        console.log('=== END API REQUEST DEBUG ===');
        
        const response = await fetch(API_ENDPOINTS.query, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(queryBody)
        });
        
        console.log('Query response status:', response.status); // DEBUG LOG
        
        const result = await response.json();
        console.log('Query result:', result); // DEBUG LOG
        
        // Direkt sonuç gösterimi - onay yok
        if (result.işlem === 'anomaly_analysis' || result.işlem === 'anomaly_from_storage') {
            console.log('Anomaly result received, displaying...');
            displayAnomalyResults(result);
            window.lastAnomalyResult = result; // Sakla
        } else {
            displayResult(result);
        }
        
    } catch (error) {
        console.error('Query error:', error); // DEBUG LOG
        showNotification('Sorgu işlenirken hata oluştu', 'error');
        console.error('Query error:', error);
    } finally {
        showLoader(false);
        elements.queryBtn.disabled = false;
    }
}





// ============================================
// ANOMALI ANALİZ FONKSİYONLARI
// ============================================
// NOT: Anomali analiz fonksiyonları script-anomaly.js modülünde tanımlıdır.
//      Backward compatibility için local alias'lar:
var updateParentAnomalyQuery = window.updateParentAnomalyQuery;
var displayChatAnomalyResult = window.displayChatAnomalyResult;
var decodeHtmlEntities = window.decodeHtmlEntities;
var formatAIResponse = window.formatAIResponse;
var displayAnomalyAnalysisResult = window.displayAnomalyAnalysisResult;
var exportAnomalyReport = window.exportAnomalyReport;
var scheduleFollowUp = window.scheduleFollowUp;
var saveFollowUp = window.saveFollowUp;
var formatSection = window.formatSection;
var highlightNumbers = window.highlightNumbers;
var parseAIExplanationFromText = window.parseAIExplanationFromText;
var handleAnalyzeLog = window.handleAnalyzeLog;
var closeAnomalyModal = window.closeAnomalyModal;
var displayAnomalyResults = window.displayAnomalyResults;
var toggleDetailedAnomalyList = window.toggleDetailedAnomalyList;
var detectAnomalyType = window.detectAnomalyType;
var renderDetailedAnomalyList = window.renderDetailedAnomalyList;
var getAnomalyExplanation = window.getAnomalyExplanation;
var requestDetailedAnomalies = window.requestDetailedAnomalies;
var showDetailedAnomalyModal = window.showDetailedAnomalyModal;
var exportAnomalyData = window.exportAnomalyData;
var renderCriticalAnomaliesTable = window.renderCriticalAnomaliesTable;
var generateMLInsights = window.generateMLInsights;
var renderMLInsightsSummary = window.renderMLInsightsSummary;
var renderSecurityAlertsDashboard = window.renderSecurityAlertsDashboard;
var toggleCriticalAnomalyMessages = window.toggleCriticalAnomalyMessages;
var toggleDetailedAnomalyMessages = window.toggleDetailedAnomalyMessages;

// displayResult fonksiyonu için özel durum - hala script.js'de kalması gerekiyor
// NOT: updateParentAnomalyQuery mantığı artık script-anomaly.js'de

/**
 * Sonucu görüntüle 
 */
function displayResult(result) {
    // DEBUG LOGS - Daha detaylı
    console.log('=== displayResult DETAILED DEBUG ===');
    console.log('Full result object:', JSON.stringify(result, null, 2));
    console.log('result.işlem:', result.işlem);
    console.log('result.durum:', result.durum);
    console.log('window.pendingAnomalyQueryId:', window.pendingAnomalyQueryId);
    console.log('window.lastQueryWasConfirmation:', window.lastQueryWasConfirmation);
    console.log('Current query text:', elements.queryInput.value);
    
    // Anomali analiz sonucu kontrolü için daha detaylı log
    const isAnomalyAnalysis = result.işlem === 'anomaly_analysis';
    const isSorguTamamlandi = result.işlem === 'sorgu_tamamlandı';
    const hasAnomalyTool = result.sonuç?.tools_used?.includes('analyze_mongodb_logs');
    
    console.log('isAnomalyAnalysis:', isAnomalyAnalysis);
    console.log('isSorguTamamlandi:', isSorguTamamlandi);
    console.log('hasAnomalyTool:', hasAnomalyTool);
    console.log('tools_used:', result.sonuç?.tools_used);
    console.log('displayResult called with result type:', result.işlem || 'unknown'); // DEBUG LOG
    
    // YENİ: İptal durumu kontrolü
    if (result.durum === 'iptal') {
        elements.resultSection.style.display = 'block';
        elements.resultContent.innerHTML = `
            <div class="result-status info">
                <strong>ℹ️ ${result.açıklama}</strong>
            </div>
            <div class="user-guidance">
                <p>Yeni bir sorgu girebilir veya parametreleri değiştirebilirsiniz.</p>
            </div>
        `;
        return;
    }
    
    // YENİ: Anomali analizi sonuçları için özel görüntüleme
    if (result.işlem === 'anomaly_analysis') {
        // ÖNCE PARENT GÜNCELLEMESİNİ YAP
        if (window.pendingAnomalyQueryId || localStorage.getItem('pendingAnomalyQueryId')) {
            // Parent güncelleme kodunu buraya taşı
            updateParentAnomalyQuery(result);
        }
        
        // Eğer summary data içindeyse, üst seviyeye taşı
        if (!result.sonuç.summary && result.sonuç.data?.summary) {
            result.sonuç.summary = result.sonuç.data.summary;
            result.sonuç.critical_anomalies = result.sonuç.data.critical_anomalies;
            result.sonuç.component_analysis = result.sonuç.data.component_analysis;
            result.sonuç.temporal_analysis = result.sonuç.data.temporal_analysis;
            result.sonuç.ai_explanation = result.sonuç.data.ai_explanation || result.sonuç.ai_explanation;
        }
        
        // YENİ: displayAnomalyAnalysisResult yerine displayAnomalyResults kullan
        // Böylece tüm anomaly sonuçları aynı fonksiyonla işlenir
        displayAnomalyResults(result);
        
        // YENİ: Eğer parent query yoksa direkt history'ye ekle
        if (!window.pendingAnomalyQueryId && !localStorage.getItem('pendingAnomalyQueryId')) {
            const historyItem = {
                id: Date.now(),
                timestamp: new Date().toISOString(),
                query: elements.queryInput.value || 'Anomaly Analizi',
                type: 'anomaly',
                category: 'anomaly',
                result: result,
                durum: result.durum || 'tamamlandı',
                işlem: 'anomaly_analysis',
                hasResult: true,
                childResult: result // AI açıklamaları dahil tüm sonuç
            };
            
            queryHistory.unshift(historyItem);
            if (queryHistory.length > MAX_HISTORY_ITEMS) {
                queryHistory = queryHistory.slice(0, MAX_HISTORY_ITEMS);
            }
            
            saveHistory();
            updateHistoryDisplay();
        }
        
        return;
    }
    
    elements.resultSection.style.display = 'block';

    // Performance analiz kontrolü - YENİ
    if (result.işlem === 'query_performance_analysis') {
        console.log('Displaying performance analysis result'); // DEBUG LOG
        displayPerformanceAnalysis(result);
        return;
    }

    // Durum göstergesi
    const statusClass = result.durum === 'başarılı' ? 'success' :
                       result.durum === 'uyarı' ? 'warning' : 'error';
    
    const statusIcon = result.durum === 'başarılı' ? '✅' :
                      result.durum === 'uyarı' ? '⚠️' : '❌';

    let html = `<div class="result-status ${statusClass}">`;
    html += `<strong>${statusIcon} ${result.durum.toUpperCase()}</strong>`;
    if (result.işlem) html += ` - ${result.işlem}`;
    html += `</div>`;

    // Ana içerik
    html += '<div class="result-details">';

    // Açıklama - Geliştirilmiş parse
    if (result.açıklama) {
        html += '<div class="result-field">';
        
        // Açıklamayı parse et ve yapılandır
        const formattedContent = parseAndFormatDescription(result.açıklama);
        html += formattedContent;
        
        html += '</div>';
    }

    // Koleksiyon
    if (result.koleksiyon) {
        html += `<div class="result-field">
                    <strong>📁 Koleksiyon:</strong> 
                    <span class="highlight">${escapeHtml(result.koleksiyon)}</span>
                 </div>`;
    }

    // Tahminler
    if (result.tahminler && result.tahminler.length > 0) {
        html += '<div class="result-field">';
        html += '<strong>💡 Yapılan Tahminler:</strong>';
        html += '<div class="prediction-list">';
        result.tahminler.forEach(tahmin => {
            html += `<div class="prediction-item">▸ ${escapeHtml(tahmin)}</div>`;
        });
        html += '</div></div>';
    }

    // Sonuç (JSON olarak) - Sadece gerekirse göster
    if (result.sonuç && !isSimpleMetricResult(result.sonuç)) {
        html += '<div class="result-field"><strong>📊 Sonuç Detayları:</strong>';
        html += `<pre class="json-display">${formatJSON(result.sonuç)}</pre>`;
        html += '</div>';
    }

    // Öneriler
    if (result.öneriler && result.öneriler.length > 0) {
        html += '<div class="result-field">';
        html += '<strong>💡 Öneriler:</strong>';
        html += '<div class="suggestion-list">';
        result.öneriler.forEach(öneri => {
            html += `<div class="suggestion-item">✓ ${escapeHtml(öneri)}</div>`;
        });
        html += '</div></div>';
    }

    html += '</div>';

    // Kullanıcı yönlendirmesi
    html += '<div class="user-guidance">';
    html += '<p>Yeni bir işlem yapmak ister misiniz?</p>';
    html += '</div>';

    // Timestamp
    if (result.timestamp) {
        const date = new Date(result.timestamp);
        html += `<div class="result-timestamp">🕐 İşlem zamanı: ${date.toLocaleString('tr-TR')}</div>`;
    }

    elements.resultContent.innerHTML = html;

    // Sonuç alanına scroll
    elements.resultSection.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    

    // Geçmişe ekle mantığı 
    const queryText = elements.queryInput.value.toLowerCase().trim();
    const isConfirmationResponse = ['evet', 'hayır', 'yes', 'no', 'onay', 'iptal'].includes(queryText);
    // Anomali analiz sonucu mu kontrol et 
    const isAnomalyResult = result.işlem === 'anomaly_analysis' || 
                           result.işlem === 'sorgu_tamamlandı' ||
                           result.işlem === 'anomali_analizi' ||
                           (result.işlem === 'sorgu_tamamlandı' && 
                            result.sonuç?.tools_used?.includes('analyze_mongodb_logs')) ||
                           (result.açıklama && result.açıklama.includes('anomali')) ||
                           (result.sonuç?.data?.summary); // summary varsa anomali sonucu

    // DEBUG LOG
    console.log('History update check:', {
        isConfirmationResponse,
        isAnomalyResult,
        pendingQueryId: window.pendingAnomalyQueryId,
        lastQueryWasConfirmation: window.lastQueryWasConfirmation
    });
    // ID'yi window'dan veya localStorage'dan al
    if (!window.pendingAnomalyQueryId) {
        const storedId = localStorage.getItem('pendingAnomalyQueryId');
        if (storedId) {
            window.pendingAnomalyQueryId = parseInt(storedId);
            console.log('Restored pendingAnomalyQueryId from localStorage:', window.pendingAnomalyQueryId);
        }
    }
    // ÖNCE ANOMALİ SONUCU KONTROLÜ - confirmation olsa bile parent güncellenmeli!
    if (isAnomalyResult) {
        console.log('Anomaly result detected - updating parent query');
        
        // Parent sorguyu bul - ID yoksa alternatif yöntemle bul
        let parentIndex = -1;
        
        if (window.pendingAnomalyQueryId) {
            parentIndex = queryHistory.findIndex(h => h.id === window.pendingAnomalyQueryId);
        } else {
            // ID yoksa, tamamlanmamış anomali parent'ını bul
            console.log('pendingAnomalyQueryId not found, searching for incomplete parent...');
            parentIndex = queryHistory.findIndex(h => 
                h.isAnomalyParent === true && 
                h.durum !== 'tamamlandı' &&
                h.durum !== 'iptal'
            );
        }
        console.log('Parent index found:', parentIndex);
        
        if (parentIndex !== -1) {
            // Parent'ı güncelle - daha kapsamlı
            queryHistory[parentIndex].childResult = result;
            queryHistory[parentIndex].hasResult = true;
            queryHistory[parentIndex].type = 'anomaly';
            queryHistory[parentIndex].durum = result.durum === 'tamamlandı' ? 'tamamlandı' : 'başarılı'; // API'den gelen durumu kullan
            queryHistory[parentIndex].işlem = 'anomaly_analysis_completed';
            queryHistory[parentIndex].completedAt = new Date().toISOString();
            queryHistory[parentIndex].executionTime = Date.now() - queryHistory[parentIndex].id;

            // Onay bekliyor durumunu temizle
            if (queryHistory[parentIndex].durum === 'onay_bekliyor') {
                queryHistory[parentIndex].durum = 'tamamlandı';
            }
            
            console.log('Parent updated successfully:', queryHistory[parentIndex]);
            
            saveHistory();
            updateHistoryDisplay();

            setTimeout(() => {
                const activeTab = document.querySelector('.history-tab.active')?.dataset.tab || 'all';
                updateHistoryDisplay(activeTab);
                
                // Eğer parent item görünüyorsa, detayını otomatik aç
                const parentElement = document.querySelector(`.history-item[data-id="${window.pendingAnomalyQueryId}"]`);
                if (parentElement && queryHistory[parentIndex].hasResult) {
                    // Detayı otomatik göster
                    showHistoryDetail(window.pendingAnomalyQueryId);
                }
            }, 100);
            
            // Parent ID'yi temizle
            window.pendingAnomalyQueryId = null;
            localStorage.removeItem('pendingAnomalyQueryId');
        } else {
            console.error('Parent query not found in history!');
        }
    }
    // Normal sorgular için history ekleme (anomali sonucu değilse)
    else if (!isAnomalyResult && !isConfirmationResponse && !window.lastQueryWasConfirmation) {
        // Normal sorgu - işlem tipine göre kategori belirle
        let queryType = 'chatbot';
        
        // Tool kullanımına bakarak da kontrol et
        const hasAnomalyTool = result.sonuç?.tools_used?.includes('analyze_mongodb_logs');

        const queryLower = elements.queryInput.value.toLowerCase();
        // Genişletilmiş anomali keyword listesi
        const isAnomalyQuery = queryLower.match(/anomali|anomaly|analiz.*yap|analiz et|analyze|log.*analiz|log.*kontrol|log.*incele|sorun.*tespit|sorun.*bul|hata.*bul|problem.*var|anormal.*durum|kritik.*olay|uyarı.*kontrol/);
        
        console.log('Category detection - Query:', queryLower);
        console.log('Category detection - isAnomalyQuery:', isAnomalyQuery);
        console.log('Category detection - işlem:', result.işlem);

        // Anomali ile ilgili tüm işlem tiplerini tanımla
        const anomalyOperations = ['anomaly_analysis', 'anomaly_analysis_completed', 'log_analysis', 'anomali_analizi', 'parametre_tespiti', 'parametre_onayı'];
        const işlemTipi = result.işlem?.toLowerCase() || '';

        // GENİŞLETİLMİŞ KATEGORİ KONTROLÜ
        if (isAnomalyQuery || 
            anomalyOperations.includes(işlemTipi) ||
            işlemTipi.includes('anomaly') || 
            işlemTipi.includes('anomali') ||
            result.durum === 'onay_bekliyor' ||
            hasAnomalyTool ||
            window.pendingAnomalyQueryId) {
            queryType = 'anomaly';
            console.log('Categorized as: anomaly', {
                reason: isAnomalyQuery ? 'query match' : 
                        anomalyOperations.includes(işlemTipi) ? 'operation type' :
                        hasAnomalyTool ? 'tool usage' : 
                        window.pendingAnomalyQueryId ? 'pending anomaly' : 'other'
            });
        }
        else if (result.işlem && (
            result.işlem.includes('performance') ||
            result.işlem === 'query_performance_analysis' ||
            result.sonuç?.tools_used?.includes('analyze_query_performance')
        )) {
            queryType = 'chatbot';
        }
        else if (result.işlem && (
            result.işlem === 'mongodb_query' ||
            result.işlem === 'schema_analysis' ||
            result.işlem === 'index_management' ||
            result.sonuç?.tools_used?.includes('mongodb_query')
        )) {
            queryType = 'chatbot';
        }
        
        addToHistory(elements.queryInput.value, result, queryType);
    } else {
        console.log('Skipping history addition - confirmation response or already handled');
    }

    // lastQueryWasConfirmation flag'ini resetle
    window.lastQueryWasConfirmation = false;
}


/**
 * Takip sorusu sor
 */
window.askFollowUp = function(question) {
    elements.queryInput.value = question;
    handleQuery();
};

// ============================================
// PERFORMANCE ANALİZ FONKSİYONLARI
// ============================================
// ========================================
// PERFORMANCE ANALYSIS MODULE REFERENCES
// ========================================
// Performance fonksiyonları script-performance.js modülüne taşındı
// Burada sadece referanslar tutuluyor

// Performance Analysis Functions - script-performance.js'den geliyor
const displayPerformanceAnalysis = window.displayPerformanceAnalysis;
const renderPerformanceScore = window.renderPerformanceScore;
const renderExecutionMetrics = window.renderExecutionMetrics;
const renderExecutionTree = window.renderExecutionTree;
const renderTreeNode = window.renderTreeNode;
const renderImprovementEstimate = window.renderImprovementEstimate;
const renderRecommendations = window.renderRecommendations;
const attachPerformanceEventListeners = window.attachPerformanceEventListeners;


// Sayfa yüklendiğinde otomatik bağlan (test için)
window.addEventListener('load', () => {
    // API key dolu ise otomatik bağlan
    if (elements.apiKeyInput.value) {
        setTimeout(() => {
            console.log('Test ortamı için otomatik bağlanıyor...');
            // handleConnect(); // Production'da kaldırılmalı
        }, 1000);
    }
});

/**
 * Koleksiyonları göster
 */
async function handleCollections() {
    if (!isConnected) {
        showNotification('Önce bağlantı kurmalısınız', 'error');
        return;
    }
    
    showLoader(true);
    
    try {
        const response = await fetch(`${API_ENDPOINTS.collections}?api_key=${apiKey}`);
        const data = await response.json();
        
        if (data.collections) {
            let content = '<h4>Mevcut Koleksiyonlar</h4>';
            content += '<div class="collections-grid">';
            
            data.collections.forEach((collection, index) => {
                content += `
                    <div class="collection-item">
                        <span class="collection-number">${index + 1}</span>
                        <span class="collection-name">${collection}</span>
                        <button class="btn-small" onclick="viewSchema('${collection}')">
                            Şema Görüntüle
                        </button>
                    </div>
                `;
            });
            
            content += '</div>';
            content += `<p class="collections-count">Toplam ${data.collections.length} koleksiyon</p>`;
            
            showModal('Koleksiyon Listesi', content);
        }
    } catch (error) {
        showNotification('Koleksiyonlar yüklenemedi', 'error');
    } finally {
        showLoader(false);
    }
}

/**
 * Sistem Reset Modal - Acar/Kapar/Islem
 */
function openSystemResetModal() {
    const modal = document.getElementById('systemResetModal');
    if (modal) {
        modal.style.display = 'flex';
        // Onceki sonuclari gizle
        const resultsPanel = document.getElementById('srResultsPanel');
        if (resultsPanel) resultsPanel.style.display = 'none';
    }
}

function closeSystemResetModal() {
    const modal = document.getElementById('systemResetModal');
    if (modal) modal.style.display = 'none';
}

function initSystemResetModal() {
    // Kapat butonu
    const closeBtn = document.getElementById('systemResetCloseBtn');
    if (closeBtn) closeBtn.addEventListener('click', closeSystemResetModal);

    // Overlay tiklayinca kapat
    const overlay = document.getElementById('systemResetModal');
    if (overlay) {
        overlay.addEventListener('click', function(e) {
            if (e.target === overlay) closeSystemResetModal();
        });
    }

    // Tumunu sec toggle
    const selectAll = document.getElementById('srSelectAll');
    if (selectAll) {
        selectAll.addEventListener('change', function() {
            const checkboxes = document.querySelectorAll('input[name="srCategory"]');
            checkboxes.forEach(cb => { cb.checked = selectAll.checked; });
        });
    }

    // Kategori checkboxlari - selectAll senkronizasyonu
    const categoryBoxes = document.querySelectorAll('input[name="srCategory"]');
    categoryBoxes.forEach(cb => {
        cb.addEventListener('change', function() {
            const allChecked = Array.from(categoryBoxes).every(c => c.checked);
            if (selectAll) selectAll.checked = allChecked;
        });
    });

    // DRY RUN butonu
    const dryRunBtn = document.getElementById('srDryRunBtn');
    if (dryRunBtn) dryRunBtn.addEventListener('click', () => executeSystemReset(true));

    // FULL RESET butonu
    const fullResetBtn = document.getElementById('srFullResetBtn');
    if (fullResetBtn) fullResetBtn.addEventListener('click', () => {
        if (confirm('UYARI: Secili tum veriler kalici olarak silinecek.\nBu islem geri alinamaz.\n\nDevam etmek istiyor musunuz?')) {
            executeSystemReset(false);
        }
    });

    // Sonuc paneli kapat
    const resultsCloseBtn = document.getElementById('srResultsCloseBtn');
    if (resultsCloseBtn) {
        resultsCloseBtn.addEventListener('click', function() {
            const panel = document.getElementById('srResultsPanel');
            if (panel) panel.style.display = 'none';
        });
    }
}

function getSelectedCategories() {
    const checkboxes = document.querySelectorAll('input[name="srCategory"]:checked');
    return Array.from(checkboxes).map(cb => cb.value);
}

async function executeSystemReset(dryRun) {
    const categories = getSelectedCategories();
    if (categories.length === 0) {
        showNotification('En az bir kategori secmelisiniz', 'warning');
        return;
    }

    // Butonlari disable et + spinner goster
    const dryRunBtn = document.getElementById('srDryRunBtn');
    const fullResetBtn = document.getElementById('srFullResetBtn');
    const activeBtn = dryRun ? dryRunBtn : fullResetBtn;

    const origContent = activeBtn.innerHTML;
    activeBtn.innerHTML = '<span class="sr-spinner"></span><span>Isleniyor...</span>';
    activeBtn.disabled = true;
    if (dryRunBtn) dryRunBtn.disabled = true;
    if (fullResetBtn) fullResetBtn.disabled = true;

    try {
        const response = await fetch(API_ENDPOINTS.systemReset, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                categories: categories,
                dry_run: dryRun
            })
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();
        displayResetResults(data, dryRun);

        if (!dryRun && data.status === 'success') {
            showNotification('Sistem basariyla sifirlandi', 'success');
            // ML Panel metriklerini sifirla
            if (window.updateMLPanelWithDefaults) {
                window.updateMLPanelWithDefaults();
            }
            // lastAnomalyResult'i temizle (eski analiz verileri)
            window.lastAnomalyResult = null;
        }
    } catch (error) {
        console.error('[SYSTEM RESET] Error:', error);
        const resultsPanel = document.getElementById('srResultsPanel');
        const resultsContent = document.getElementById('srResultsContent');
        const resultsTitle = document.getElementById('srResultsTitle');
        if (resultsPanel && resultsContent && resultsTitle) {
            resultsTitle.textContent = 'Hata';
            resultsContent.innerHTML = `<div class="sr-result-error">Islem sirasinda hata olustu: ${error.message}</div>`;
            resultsPanel.style.display = 'flex';
        }
        showNotification('Sistem reset sirasinda hata olustu', 'error');
    } finally {
        activeBtn.innerHTML = origContent;
        activeBtn.disabled = false;
        if (dryRunBtn) dryRunBtn.disabled = false;
        if (fullResetBtn) fullResetBtn.disabled = false;
    }
}

function displayResetResults(data, dryRun) {
    const resultsPanel = document.getElementById('srResultsPanel');
    const resultsContent = document.getElementById('srResultsContent');
    const resultsTitle = document.getElementById('srResultsTitle');

    if (!resultsPanel || !resultsContent || !resultsTitle) return;

    const prefix = dryRun ? '[DRY-RUN] ' : '';
    resultsTitle.textContent = prefix + 'Islem Sonucu';

    let html = '';

    // Kategori sonuclari
    const categoryLabels = {
        ml_models: 'ML Modelleri',
        anomaly_output: 'Anomali Analizleri',
        storage_depot: 'Storage Deposu',
        cache: 'Cache Dosyalari',
        mongodb: 'MongoDB',
        logs: 'Loglar',
        metrics: 'Metrikler',
        pycache: 'Python Cache'
    };

    if (data.file_results) {
        for (const [key, stats] of Object.entries(data.file_results)) {
            const label = categoryLabels[key] || key;
            const count = stats.deleted || 0;
            const size = stats.total_bytes_formatted || '0 B';
            const failed = stats.failed || 0;
            let stat = `${count} oge (${size})`;
            if (failed > 0) stat += ` | ${failed} hata`;
            html += `<div class="sr-result-category"><span class="sr-result-cat-name">${label}</span><span class="sr-result-cat-stat">${stat}</span></div>`;
        }
    }

    if (data.mongodb_results) {
        const mongo = data.mongodb_results;
        const cleared = mongo.cleared || 0;
        const docs = mongo.total_docs || 0;
        html += `<div class="sr-result-category"><span class="sr-result-cat-name">MongoDB</span><span class="sr-result-cat-stat">${cleared} koleksiyon (${docs} dokuman)</span></div>`;
    }

    // Ozet
    const totalFiles = data.total_files || 0;
    const totalSize = data.total_size_formatted || '0 B';

    if (dryRun) {
        html += `<div class="sr-result-summary sr-result-dryrun">Simulasyon: ${totalFiles} dosya/dizin (${totalSize}) silinecek</div>`;
    } else {
        html += `<div class="sr-result-summary">Tamamlandi: ${totalFiles} dosya/dizin (${totalSize}) silindi</div>`;
    }

    resultsContent.innerHTML = html;
    resultsPanel.style.display = 'flex';
}



/**
 * Şema görüntüleme (global fonksiyon)
 */
window.viewSchema = async function(collectionName) {
    showLoader(true);
    closeModal();
    
    try {
        const response = await fetch(
            `${API_ENDPOINTS.schema}/${collectionName}?api_key=${apiKey}&detailed=true`
        );
        const schema = await response.json();
        
        // Sonucu query input'a yaz ve çalıştır
        elements.queryInput.value = `${collectionName} koleksiyonunun detaylı şemasını göster`;
        
        // Şema bilgisini result olarak göster
        displayResult({
            durum: 'başarılı',
            işlem: 'schema_analysis',
            koleksiyon: collectionName,
            açıklama: `${collectionName} koleksiyonunun detaylı şema analizi`,
            sonuç: schema
        });
        
    } catch (error) {
        showNotification('Şema bilgisi alınamadı', 'error');
    } finally {
        showLoader(false);
    }
};

/**
 * MongoDB sunucularını yükle
 */
async function loadMongoDBHosts() {
    console.log('Loading MongoDB hosts from OpenSearch...');
    
    try {
        const response = await fetch(`${API_ENDPOINTS.mongodbHosts}?api_key=${apiKey}`);
        const data = await response.json();
        
        console.log('MongoDB hosts response:', data);
        
        const hostSelect = document.getElementById('mongodbHostSelect');
        if (!hostSelect) return;
        
        // Mevcut seçenekleri temizle
        hostSelect.innerHTML = '<option value="" disabled selected>Lütfen bir sunucu seçin</option>';
        
        if (data.hosts && data.hosts.length > 0) {
            data.hosts.forEach(host => {
                const option = document.createElement('option');
                option.value = host;
                option.textContent = host;
                hostSelect.appendChild(option);
            });
            
            console.log(`Loaded ${data.hosts.length} MongoDB hosts`);
            if (selectedDataSource === 'opensearch') {
                // Eğer pendingAnomalyParams'ta sunucu varsa otomatik seç
                if (window.pendingAnomalyParams && window.pendingAnomalyParams.server) {
                    hostSelect.value = window.pendingAnomalyParams.server;
                    console.log('Auto-selected host:', window.pendingAnomalyParams.server);
                }
                
                // Validation'ı tetikle
                validateAnalysisButton();
            }
        } else {
            console.log('No MongoDB hosts found');
        }
    } catch (error) {
        console.error('Error loading MongoDB hosts:', error);
        showNotification('MongoDB sunucuları yüklenemedi', 'error');
    }
}

/**
 * MSSQL sunucularını yükle (OpenSearch'ten)
 */
async function loadMSSQLHosts() {
    console.log('Loading MSSQL hosts from OpenSearch...');

    try {
        const response = await fetch(`${API_ENDPOINTS.mssqlHosts}?api_key=${apiKey}`);
        const data = await response.json();

        console.log('MSSQL hosts response:', data);

        const hostSelect = document.getElementById('mssqlHostSelect');
        if (!hostSelect) return;

        // Mevcut seçenekleri temizle
        hostSelect.innerHTML = '<option value="" disabled selected>MSSQL sunucu seçin...</option>';

        if (data.hosts && data.hosts.length > 0) {
            data.hosts.forEach(host => {
                const option = document.createElement('option');
                option.value = host;
                option.textContent = host;
                hostSelect.appendChild(option);
            });

            console.log(`Loaded ${data.hosts.length} MSSQL hosts`);

            if (window.selectedDataSource === 'mssql_opensearch') {
                validateAnalysisButton();
            }
        } else {
            console.log('No MSSQL hosts found');
        }
    } catch (error) {
        console.error('Error loading MSSQL hosts:', error);
        showNotification('MSSQL sunucuları yüklenemedi', 'error');
    }
}

/**
 * MongoDB cluster'larını yükle
 */
async function loadClusters() {
    console.log('Loading MongoDB clusters from backend...');
    
    try {
        const response = await fetch(`/api/mongodb/clusters?api_key=${apiKey}`);
        const data = await response.json();
        
        console.log('Clusters response:', data);
        
        const clusterSelect = document.getElementById('clusterSelect');
        if (!clusterSelect) return;
        
        // Mevcut seçenekleri temizle
        clusterSelect.innerHTML = '<option value="" disabled selected>Cluster seçin...</option>';
        
        // ✅ Object olarak gelen clusters'ı kontrol et ve işle
        if (data.clusters && Object.keys(data.clusters).length > 0) {
            // Object.entries ile Object'i Array'e çevir
            Object.entries(data.clusters).forEach(([clusterId, cluster]) => {
                const option = document.createElement('option');
                option.value = cluster.cluster_id || clusterId;
                option.textContent = cluster.display_name || cluster.cluster_id || clusterId;
                option.dataset.hostCount = cluster.node_count || cluster.hosts?.length || 0;
                clusterSelect.appendChild(option);
            });
            
            console.log(`Loaded ${Object.keys(data.clusters).length} MongoDB clusters`);
        } else {
            console.log('No clusters found');
        }
    } catch (error) {
        console.error('Error loading clusters:', error);
        showNotification('Cluster listesi yüklenemedi', 'error');
    }
}

/**
 * Seçilen cluster'ın host'larını yükle ve göster
 */
async function loadClusterHosts(clusterId) {
    if (!clusterId) return;
    
    console.log(`Loading hosts for cluster: ${clusterId}`);
    
    try {
        const response = await fetch(`${API_ENDPOINTS.mongodbClusterHosts}/${clusterId}/hosts?api_key=${apiKey}`);
        const data = await response.json();
        
        console.log('Cluster hosts response:', data);
        
        const hostsInfo = document.getElementById('clusterHostsInfo');
        const hostsList = document.getElementById('clusterHostsList');
        
        if (hostsInfo && hostsList) {
            if (data.hosts && data.hosts.length > 0) {
                hostsInfo.style.display = 'block';
                
                // Host listesini göster
                let hostsHtml = data.hosts.map(host => `
                    <span class="host-badge" style="
                        display: inline-block;
                        background: #e3f2fd;
                        color: #1976d2;
                        padding: 2px 8px;
                        border-radius: 4px;
                        margin: 2px;
                        font-size: 11px;
                    ">${host}</span>
                `).join('');
                
                hostsList.innerHTML = hostsHtml;
                console.log(`Showing ${data.hosts.length} hosts for cluster ${clusterId}`);
            } else {
                hostsInfo.style.display = 'none';
                console.log('No hosts found for cluster');
            }
        }
    } catch (error) {
        console.error('Error loading cluster hosts:', error);
    }
}

/**
 * Upload edilmiş dosyayı sil
 */
async function deleteUploadedFile(filename) {
    console.log('deleteUploadedFile called for:', filename); // DEBUG LOG
    
    if (!confirm(`${filename} dosyasını silmek istediğinizden emin misiniz?`)) {
        console.log('File deletion cancelled by user'); // DEBUG LOG
        return;
    }
    
    try {
        const response = await fetch(`${API_ENDPOINTS.deleteUploadedLog}/${filename}?api_key=${apiKey}`, {
            method: 'DELETE'
        });
        
        console.log('Delete response status:', response.status); // DEBUG LOG
        
        if (response.ok) {
            console.log('File deleted successfully:', filename); // DEBUG LOG
            showNotification('Dosya başarıyla silindi', 'success');
            updateUploadedFilesList();
        } else {
            throw new Error('Dosya silinemedi');
        }
    } catch (error) {
        console.error('Error deleting file:', filename, error); // DEBUG LOG
        showNotification('Dosya silinirken hata oluştu', 'error');
    }
}

  

// ============================================
// UI YARDIMCI FONKSİYONLARI
// ============================================
// NOT: Bu fonksiyonlar script-ui.js modülünde tanımlıdır.
//      Backward compatibility için local alias'lar:
var updateStatus = window.updateStatus;
var showNotification = window.showNotification;
var showLoader = window.showLoader;
var showModal = window.showModal;
var closeModal = window.closeModal;
var escapeHtml = window.escapeHtml;
var formatJSON = window.formatJSON;
var toggleMessageExpand = window.toggleMessageExpand;
var showStorageStatistics = window.showStorageStatistics;
var showModelRegistry = window.showModelRegistry;
var toggleStorageMenu = window.toggleStorageMenu;
var addStorageMenuButtons = window.addStorageMenuButtons;
var isSimpleMetricResult = window.isSimpleMetricResult;
var formatFileSize = window.formatFileSize;
var formatTimestamp = window.formatTimestamp;
var handleClear = window.handleClear;
var formatMetricBox = window.formatMetricBox;
var toggleViewMode = window.toggleViewMode;
var handleFileUpload = window.handleFileUpload;
var updateUploadedFilesList = window.updateUploadedFilesList;
var updateSourceInputs = window.updateSourceInputs;
var validateAnalysisButton = window.validateAnalysisButton;
var parseAndFormatDescription = window.parseAndFormatDescription;

// ============================================
// HISTORY YÖNETİMİ
// ============================================
// NOT: History fonksiyonları script-history.js modülünde tanımlıdır.
//      Backward compatibility için local alias'lar:
var loadHistory = window.loadHistory;
var mergeHistoryWithMongoDB = window.mergeHistoryWithMongoDB;
var addToHistory = window.addToHistory;
var saveHistory = window.saveHistory;
var verifyMongoDBSave = window.verifyMongoDBSave;
var syncUnsavedHistoryItems = window.syncUnsavedHistoryItems;
var updateHistoryDisplay = window.updateHistoryDisplay;
var reloadAllHistory = window.reloadAllHistory;
var syncSingleItem = window.syncSingleItem;
var loadAndMergeDBAHistory = window.loadAndMergeDBAHistory;
var loadAndMergeMSSQLHistory = window.loadAndMergeMSSQLHistory;
var updateHistoryDisplayWithDBA = window.updateHistoryDisplayWithDBA;
var loadHistoricalDBAAnalysis = window.loadHistoricalDBAAnalysis;
var showHistoryDetail = window.showHistoryDetail;
var replayQuery = window.replayQuery;
var clearHistory = window.clearHistory;
var checkStorageSize = window.checkStorageSize;
var exportHistory = window.exportHistory;
var loadMongoDBHistory = window.loadMongoDBHistory;
var loadAnomalyHistoryFromMongoDB = window.loadAnomalyHistoryFromMongoDB;

//Mevcut script.js dosyasında satır aralıkları: 1534-2210


// ========== DBA HISTORY ENTEGRASYONU ==========



/**
 * Detaylı anomali modalını göster
 */
function showDetailedAnomalyModal(anomalies) {
    const existingModal = document.getElementById('detailed-anomaly-modal');
    if (existingModal) {
        existingModal.remove();
    }
    
    const modalHtml = `
    <div id="detailed-anomaly-modal" class="modal" style="display: block;">
        <div class="modal-content" style="max-width: 90%; height: 80vh;">
            <div class="modal-header">
                <h3>📋 Detaylı Anomali Listesi</h3>
                <span class="close" onclick="document.getElementById('detailed-anomaly-modal').remove()">&times;</span>
            </div>
            <div class="modal-body" style="overflow-y: auto; max-height: calc(80vh - 120px);">
                ${renderDetailedAnomalyList(anomalies)}
            </div>
        </div>
    </div>`;
    
    document.body.insertAdjacentHTML('beforeend', modalHtml);
}
// ========== ML GÖRSELLEŞTIRME YARDIMCI FONKSİYONLARI ==========

/**
 * ML Model Metriklerini Render Et - SADELEŞTİRİLMİŞ VERSİYON
 */
// ML Visualization Fonksiyonları kaldırıldı, alias olarak yönlendirme eklendi
// window.showAllComponents ve window.exportComponentAnalysis helper'ları korunmalı

// ML Visualization Functions - script-ml-visualization.js'den geliyor
const renderMLModelMetrics = window.renderMLModelMetrics;

// toggleMLExpand fonksiyonu script-ml-visualization.js'ye taşındı
const toggleMLExpand = window.toggleMLExpand;


/**
 * Online Learning Status Render Et
 */
// ML Visualization Fonksiyonları kaldırıldı, alias olarak yönlendirme eklendi
// window.showAllComponents ve window.exportComponentAnalysis helper'ları korunmalı

// ML Visualization Functions - script-ml-visualization.js'den geliyor
const renderOnlineLearningStatus = window.renderOnlineLearningStatus;
const renderComponentComparisonChart = window.renderComponentComparisonChart;
const formatFeatureName = window.formatFeatureName;
const getFeatureDescription = window.getFeatureDescription;
const getFeatureInsight = window.getFeatureInsight;
const renderFeatureImportanceChart = window.renderFeatureImportanceChart;
const renderComponentDashboard = window.renderComponentDashboard;
const getComponentIcon = window.getComponentIcon;
const renderTemporalHeatmap = window.renderTemporalHeatmap;
const analyzeTemporalPatterns = window.analyzeTemporalPatterns;
const findConsecutiveHours = window.findConsecutiveHours;
const detectRegularPattern = window.detectRegularPattern;
const attachMLVisualizationListeners = window.attachMLVisualizationListeners;
const renderAnomalyScoreDistribution = window.renderAnomalyScoreDistribution;

// Yardımcı fonksiyonlar
window.showAllComponents = function() {
    // Tüm component'leri modal'da göster
    if (!window.lastAnomalyResult || !window.lastAnomalyResult.sonuç) return;
    
    const componentAnalysis = window.lastAnomalyResult.sonuç.component_analysis || 
                             window.lastAnomalyResult.sonuç.data?.component_analysis;
    
    if (!componentAnalysis) {
        showNotification('Component analiz verisi bulunamadı', 'warning');
        return;
    }
    
    let modalContent = '<div class="all-components-modal">';
    modalContent += '<h4>📊 Tüm Component Analizi</h4>';
    modalContent += '<table class="component-table">';
    modalContent += '<thead><tr>';
    modalContent += '<th>Component</th>';
    modalContent += '<th>Anomali Sayısı</th>';
    modalContent += '<th>Toplam Log</th>';
    modalContent += '<th>Anomali Oranı</th>';
    modalContent += '<th>Durum</th>';
    modalContent += '</tr></thead><tbody>';
    
    Object.entries(componentAnalysis)
        .sort(([,a], [,b]) => b.anomaly_rate - a.anomaly_rate)
        .forEach(([component, stats]) => {
            const criticalityClass = stats.anomaly_rate > 20 ? 'critical' : 
                                   stats.anomaly_rate > 10 ? 'warning' : 'normal';
            modalContent += `<tr class="${criticalityClass}">`;
            modalContent += `<td><strong>${component}</strong></td>`;
            modalContent += `<td>${stats.anomaly_count.toLocaleString('tr-TR')}</td>`;
            modalContent += `<td>${stats.total_count.toLocaleString('tr-TR')}</td>`;
            modalContent += `<td>%${stats.anomaly_rate.toFixed(1)}</td>`;
            modalContent += `<td><span class="status-badge ${criticalityClass}">${
                criticalityClass === 'critical' ? 'KRİTİK' : 
                criticalityClass === 'warning' ? 'UYARI' : 'NORMAL'
            }</span></td>`;
            modalContent += '</tr>';
        });
    
    modalContent += '</tbody></table>';
    modalContent += '</div>';
    
    showModal('Component Analizi - Tam Liste', modalContent);
};

window.exportComponentAnalysis = function() {
    if (!window.lastAnomalyResult) return;
    
    const componentData = {
        timestamp: new Date().toISOString(),
        component_analysis: window.lastAnomalyResult.sonuç.component_analysis || 
                           window.lastAnomalyResult.sonuç.data?.component_analysis,
        summary: window.lastAnomalyResult.sonuç.summary
    };
    
    const dataStr = JSON.stringify(componentData, null, 2);
    const dataUri = 'data:application/json;charset=utf-8,'+ encodeURIComponent(dataStr);
    
    const exportFileDefaultName = `component_analysis_${new Date().toISOString().split('T')[0]}.json`;
    
    const linkElement = document.createElement('a');
    linkElement.setAttribute('href', dataUri);
    linkElement.setAttribute('download', exportFileDefaultName);
    linkElement.click();
    
    showNotification('Component analizi başarıyla indirildi', 'success');
};

// ========== DBA ANALİZ FONKSİYONLARI ==========

/**
 * DBA Analiz modalını aç
 */
async function openDBAAnalysisModal() {
    // Modal içeriğini oluştur
    const modalContent = `
        <div class="dba-analysis-modal">
            <h4>🕐 DBA Spesifik Zaman Analizi</h4>
            <p>MongoDB loglarında belirli bir zaman aralığındaki anomalileri tespit edin.</p>
            
            <div class="dba-time-selection">
                <div style="margin-bottom: 15px;">
                    <label>Cluster Seçin:</label>
                    <select id="dbaClusterSelect" class="form-select" style="width: 100%; padding: 8px;">
                        <option value="">Yükleniyor...</option>
                    </select>
                </div>
                
                <div style="margin-top: 15px;">
                    <label>Başlangıç Zamanı (Türkiye Saati):</label>
                    <input type="datetime-local" id="dbaStartTime" class="form-input" style="width: 100%; padding: 8px;">
                    <small style="color: #888;">Örnek: Outbox rollback için 10.09.2025 16:09</small>
                </div>
                
                <div style="margin-top: 10px;">
                    <label>Bitiş Zamanı (Türkiye Saati):</label>
                    <input type="datetime-local" id="dbaEndTime" class="form-input" style="width: 100%; padding: 8px;">
                    <small style="color: #888;">Örnek: Outbox rollback için 10.09.2025 16:11 (2 dakikalık aralık)</small>
                </div>
                
                <small style="color: #666; margin-top: 10px; display: block;">
                    💡 İpucu: Spesifik olaylar için dar zaman aralıkları seçin:
                    <ul style="margin: 5px 0; padding-left: 20px;">
                        <li>Outbox rollback: 2-3 dakika</li>
                        <li>Performance issue: 10-15 dakika</li>
                        <li>Connection drop: 5-10 dakika</li>
                    </ul>
                </small>
                
                <button class="btn btn-primary" style="width: 100%; margin-top: 20px;" onclick="startDBAAnalysis()">
                    🚀 DBA Analizini Başlat
                </button>
            </div>
        </div>
    `;
    
    // Modal'ı göster
    showModal('DBA Zaman Bazlı Anomali Analizi', modalContent);
    
    // Cluster listesini yükle
    if (!apiKey || !isConnected) {
        console.error('API key not available or not connected');
        const clusterSelect = document.getElementById('dbaClusterSelect');
        if (clusterSelect) {
            clusterSelect.innerHTML = '<option value="">Önce bağlantı kurmanız gerekiyor</option>';
        }
        return;
    }

    try {
        console.log('Loading clusters for DBA analysis, API key:', apiKey ? 'present' : 'missing');
        const response = await fetch(`${API_ENDPOINTS.mongodbClusters}?api_key=${apiKey}`);
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        console.log('DBA clusters loaded:', data);
        
        const clusterSelect = document.getElementById('dbaClusterSelect');
        if (clusterSelect) {
            // Mevcut seçenekleri temizle
            clusterSelect.innerHTML = '<option value="" disabled selected>Cluster seçin...</option>';
            
            // Cluster'ları ekle
            if (data.clusters && Object.keys(data.clusters).length > 0) {
                Object.entries(data.clusters).forEach(([clusterId, cluster]) => {
                    const option = document.createElement('option');
                    option.value = cluster.cluster_id || clusterId;
                    option.textContent = cluster.display_name || cluster.cluster_id || clusterId;
                    
                    // Host listesini dataset'e ekle
                    if (cluster.hosts && Array.isArray(cluster.hosts)) {
                        option.dataset.hosts = cluster.hosts.join(',');
                        option.dataset.hostCount = cluster.hosts.length;
                    } else {
                        option.dataset.hostCount = cluster.node_count || 0;
                    }
                    
                    clusterSelect.appendChild(option);
                });
                console.log(`Loaded ${Object.keys(data.clusters).length} clusters for DBA analysis`);
            }
        }
    } catch (error) {
        console.error('Error loading clusters for DBA analysis:', error);
        const clusterSelect = document.getElementById('dbaClusterSelect');
        if (clusterSelect) {
            clusterSelect.innerHTML = '<option value="">Cluster listesi yüklenemedi</option>';
        }
    }
    
    // Default değerleri set et
    // DBA için daha spesifik: son 15 dakika (tipik incident window)
    const now = new Date();
    const fifteenMinutesAgo = new Date(now - 15 * 60 * 1000);
    
    // Türkiye saat dilimine göre formatla (datetime-local input için)
    const formatDateTimeLocal = (date) => {
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        const hours = String(date.getHours()).padStart(2, '0');
        const minutes = String(date.getMinutes()).padStart(2, '0');
        return `${year}-${month}-${day}T${hours}:${minutes}`;
    };
    
    document.getElementById('dbaStartTime').value = formatDateTimeLocal(fifteenMinutesAgo);
    document.getElementById('dbaEndTime').value = formatDateTimeLocal(now);
}

/**
 * DBA analizi başlat
 */
async function startDBAAnalysis() {
    const clusterSelect = document.getElementById('dbaClusterSelect');
    const cluster = clusterSelect.value;
    const startTimeLocal = document.getElementById('dbaStartTime').value;
    const endTimeLocal = document.getElementById('dbaEndTime').value;
    
    if (!cluster || !startTimeLocal || !endTimeLocal) {
        showNotification('Lütfen tüm alanları doldurun', 'error');
        return;
    }
    
    // Cluster'ın host listesini al (multiple host desteği için)
    let hostParam = cluster;  // Default: cluster adı
    
    // Cluster'ın host listesini dataset'ten al
    const selectedOption = clusterSelect.options[clusterSelect.selectedIndex];
    if (selectedOption && selectedOption.dataset.hosts) {
        // API'den gelen host listesini kullan
        hostParam = selectedOption.dataset.hosts;
        console.log(`Using hosts from API: ${hostParam}`);
    } else {
        // Host listesi yoksa sadece cluster adını kullan
        // Backend tek host olarak işleyecek
        console.warn(`No host list for cluster ${cluster}, using cluster name as single host`);
        hostParam = cluster;
    }
    
    console.log('DBA Analysis - Cluster:', cluster, 'Hosts:', hostParam);
    
    // Local time'ı UTC ISO formatına çevir (backend için)
    // Türkiye UTC+3 olduğu için 3 saat çıkarmamız gerekiyor
    const convertToUTC = (localDateTimeStr) => {
        const localDate = new Date(localDateTimeStr);
        // Türkiye offset'i (UTC+3)
        const turkeyOffset = 3 * 60 * 60 * 1000; // 3 saat in milliseconds
        const utcDate = new Date(localDate.getTime() - turkeyOffset);
        return utcDate.toISOString();
    };
    
    const startTimeUTC = convertToUTC(startTimeLocal);
    const endTimeUTC = convertToUTC(endTimeLocal);
    
    console.log('DBA Analysis Time Range:');
    console.log('Local Start:', startTimeLocal);
    console.log('UTC Start:', startTimeUTC);
    console.log('Local End:', endTimeLocal);
    console.log('UTC End:', endTimeUTC);
    
    closeModal();
    showLoader(true);
    
    try {
        // URL parametrelerini hazırla
        const params = new URLSearchParams({
            host: hostParam,  // backend 'host' parametresi bekliyor, cluster_id değil
            start_time: startTimeUTC,
            end_time: endTimeUTC,
            api_key: apiKey,
            auto_explain: 'true'
        });
        
        const response = await fetch(`/api/dba/analyze-specific-time?${params}`, {
            method: 'POST',  // Backend POST bekliyor
            headers: {
                'Content-Type': 'application/json',
            }
            // Body yok, parametreler URL'de
        });
        const result = await response.json();
        console.log('DBA analysis result:', result);
        
        // Sonuçları görüntüle
        displayDBAAnalysisResults(result, cluster, startTimeLocal, endTimeLocal);
        
        // ✅ YENİ: History'e ekle
        if (result.status === 'success') {
            const queryText = `DBA Analizi: ${cluster} (${new Date(startTimeLocal).toLocaleDateString('tr-TR')} ${new Date(startTimeLocal).toLocaleTimeString('tr-TR')} - ${new Date(endTimeLocal).toLocaleTimeString('tr-TR')})`;
            
            addToHistory(queryText, {
                durum: 'tamamlandı',
                işlem: 'dba_analysis',
                açıklama: `Toplam ${result.results?.anomaly_count || 0} anomali tespit edildi. Anomali oranı: %${(result.results?.anomaly_rate || 0).toFixed(2)}`,
                sonuç: result.results || {},
                storage_id: result.storage_id,
                host: cluster,
                time_range: `${startTimeLocal} - ${endTimeLocal}`
            }, 'anomaly');
        }
        
    } catch (error) {
        console.error('DBA analysis error:', error);
        showNotification('DBA analizi sırasında hata oluştu', 'error');
    } finally {
        showLoader(false);
    }
}

/**
 * DBA analiz sonuçlarını görüntüle
 */
function displayDBAAnalysisResults(result, cluster, startTime, endTime) {
    console.log('Displaying DBA analysis results:', result);
    
    let html = '<div class="dba-analysis-results">';
    html += '<div class="dba-header">';
    html += '<h2>🕐 DBA Zaman Bazlı Anomali Analiz Sonuçları</h2>';
    html += `<p class="time-range-info">
        <strong>Cluster:</strong> ${cluster} | 
        <strong>Zaman Aralığı:</strong> ${new Date(startTime).toLocaleString('tr-TR')} - ${new Date(endTime).toLocaleString('tr-TR')}
    </p>`;
    html += '</div>';
    
    // Hata durumu kontrolü
    if (result.status === 'error' || result.error) {
        html += '<div class="dba-error">';
        html += '<h3>❌ Analiz Hatası</h3>';
        html += `<p>${escapeHtml(result.error || result.message || 'Analiz sırasında bir hata oluştu')}</p>`;
        html += '</div>';
        html += '</div>';
        
        elements.resultContent.innerHTML = html;
        elements.resultSection.style.display = 'block';
        return;
    }
    
    // Özet bilgiler
    if (result.results) {
        const summary = {
            total_logs: result.results.total_logs_analyzed,
            total_anomalies: result.results.anomaly_count,
            anomaly_rate: result.results.anomaly_rate,
            hosts_analyzed: result.hosts ? result.hosts.split(',').length : 1
        };
        html += renderDBAAnalysisSummary(summary);
    }
    
    // Host bazlı breakdown
    if (result.host_breakdown && Object.keys(result.host_breakdown).length > 0) {
        html += renderDBAHostBreakdown(result.host_breakdown);
    }
    
    // Kritik anomaliler
    if (result.results && result.results.critical_anomalies && result.results.critical_anomalies.length > 0) {
        html += renderDBACriticalAnomalies(result.results.critical_anomalies);
    }
    
    // AI açıklaması (LCWGPT)
    if (result.results && result.results.ai_summary) {
        html += renderDBAExplanation(result.results.ai_summary);
    }
    
    // Aksiyonlar
    html += '<div class="dba-actions">';
    html += '<button class="btn btn-primary" onclick="saveDBAAnalysis()">💾 Analizi Kaydet</button>';
    html += '<button class="btn btn-secondary" onclick="exportDBAResults()">📥 Rapor İndir</button>';
    html += '<button class="btn btn-info" onclick="shareDBAResults()">📤 Paylaş</button>';
    html += '</div>';
    
    html += '</div>';
    
    // Sonuçları göster - TAM GENİŞLİKTE AMA SAYFA AKIŞINDA VE PADDING'Lİ
    elements.resultContent.innerHTML = html;
    elements.resultSection.style.display = 'block';

    // Normal akışta tut, padding ekle
    elements.resultSection.style.position = 'relative';
    elements.resultSection.style.width = 'calc(100% - 40px)';  // Sol-sağ 20px'er boşluk
    elements.resultSection.style.maxWidth = '100%';
    elements.resultSection.style.margin = '20px auto';  // Üst-alt margin ve ortalama
    elements.resultSection.style.marginLeft = '20px';  // Sol boşluk
    elements.resultSection.style.marginRight = '20px';  // Sağ boşluk
    elements.resultSection.style.padding = '30px';  // İç padding
    elements.resultSection.style.maxHeight = '80vh';
    elements.resultSection.style.overflowY = 'auto';
    elements.resultSection.style.backgroundColor = '#ffffff';
    elements.resultSection.style.borderRadius = '8px';  // Köşeleri yuvarla
    elements.resultSection.style.boxShadow = '0 2px 10px rgba(0,0,0,0.1)';
    elements.resultSection.style.marginBottom = '30px';  // History section'dan ayır

    // Parent wrapper kontrolü - genişliği koru ama padding ekle
    const resultWrapper = elements.resultSection.parentElement;
    if (resultWrapper && resultWrapper.classList.contains('result-wrapper')) {
        resultWrapper.style.width = '100%';
        resultWrapper.style.padding = '0 20px';  // Wrapper'a da yan padding
        resultWrapper.style.boxSizing = 'border-box';
    }

    // İçerik genişliğini ayarla
    const resultContentDiv = elements.resultContent.querySelector('.dba-analysis-results');
    if (resultContentDiv) {
        resultContentDiv.style.maxWidth = '100%';
        resultContentDiv.style.width = '100%';
        resultContentDiv.style.margin = '0 auto';
        resultContentDiv.style.padding = '0 10px';  // İçeriğe de hafif padding
    }

    // Smooth scroll
    elements.resultSection.scrollIntoView({ 
        behavior: 'smooth', 
        block: 'start',
        inline: 'nearest'
    });
    
    // Global değişkene kaydet
    window.lastDBAResult = {
        result: result,
        cluster: cluster,
        startTime: startTime,
        endTime: endTime,
        timestamp: new Date().toISOString()
    };
    
    // ✅ YENİ: DBA analizini chat geçmişine ekle
    if (result.status === 'success' && result.results) {
        const queryDescription = `DBA Analizi: ${cluster} - ${new Date(startTime).toLocaleString('tr-TR')} - ${new Date(endTime).toLocaleString('tr-TR')}`;
        
        // History'e ekle
        addToHistory(queryDescription, {
            durum: 'tamamlandı',
            işlem: 'dba_analysis',
            açıklama: `${result.results.anomaly_count || 0} anomali tespit edildi`,
            sonuç: {
                summary: {
                    total_logs: result.results.total_logs_analyzed || 0,
                    n_anomalies: result.results.anomaly_count || 0,
                    anomaly_rate: result.results.anomaly_rate || 0
                },
                critical_anomalies: result.results.critical_anomalies || [],
                ai_explanation: result.results.ai_summary || null
            },
            storage_id: result.storage_id
        }, 'anomaly');  // 'anomaly' tipinde kaydet
        

    }
}

/**
 * DBA özet bilgileri render et
 */
function renderDBAAnalysisSummary(summary) {
    let html = '<div class="dba-summary-section">';
    html += '<h3>📊 Analiz Özeti</h3>';
    html += '<div class="dba-metrics-grid" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px;">';
    
    const totalAnomalies = summary.total_anomalies || 0;
    const anomalyRate = summary.anomaly_rate || 0;
    const criticalityClass = anomalyRate > 5 ? 'critical' : 
                           anomalyRate > 2 ? 'warning' : 'normal';
    
    html += `
        <div class="dba-metric-card" style="padding: 15px; background: #f8f9fa; border-radius: 8px; border-left: 4px solid #0047BA;">
            <div class="metric-icon" style="font-size: 24px;">📄</div>
            <div class="metric-value" style="font-size: 28px; font-weight: bold; color: #333;">${(summary.total_logs || 0).toLocaleString('tr-TR')}</div>
            <div class="metric-label" style="color: #666;">Toplam Log</div>
        </div>
        
        <div class="dba-metric-card ${criticalityClass}" style="padding: 15px; background: ${criticalityClass === 'critical' ? '#fff5f5' : criticalityClass === 'warning' ? '#fffaf0' : '#f0f9ff'}; border-radius: 8px; border-left: 4px solid ${criticalityClass === 'critical' ? '#e74c3c' : criticalityClass === 'warning' ? '#f39c12' : '#3498db'};">
            <div class="metric-icon" style="font-size: 24px;">🚨</div>
            <div class="metric-value" style="font-size: 28px; font-weight: bold; color: ${criticalityClass === 'critical' ? '#e74c3c' : criticalityClass === 'warning' ? '#f39c12' : '#333'};">${totalAnomalies}</div>
            <div class="metric-label" style="color: #666;">Anomali Tespit</div>
        </div>
        
        <div class="dba-metric-card" style="padding: 15px; background: #f8f9fa; border-radius: 8px; border-left: 4px solid #0047BA;">
            <div class="metric-icon" style="font-size: 24px;">📊</div>
            <div class="metric-value" style="font-size: 28px; font-weight: bold; color: #333;">%${anomalyRate.toFixed(2)}</div>
            <div class="metric-label" style="color: #666;">Anomali Oranı</div>
        </div>
        
        <div class="dba-metric-card" style="padding: 15px; background: #f8f9fa; border-radius: 8px; border-left: 4px solid #0047BA;">
            <div class="metric-icon" style="font-size: 24px;">🖥️</div>
            <div class="metric-value" style="font-size: 28px; font-weight: bold; color: #333;">${summary.hosts_analyzed || 0}</div>
            <div class="metric-label" style="color: #666;">Analiz Edilen Host</div>
        </div>
    `;
    
    html += '</div>';
    
    // Eğer hiç anomali yoksa başarı mesajı
    if (totalAnomalies === 0) {
        html += '<div style="margin-top: 20px; padding: 15px; background: #d4edda; color: #155724; border-radius: 8px;">';
        html += '✅ Bu zaman aralığında anomali tespit edilmedi. Sistem normal çalışıyor.';
        html += '</div>';
    }
    
    html += '</div>';
    return html;
}

/**
 * Host bazlı breakdown render et
 */
function renderDBAHostBreakdown(hostBreakdown) {
    let html = '<div class="dba-host-breakdown">';
    html += '<h3>🖥️ Host Bazlı Anomali Dağılımı</h3>';
    html += '<div class="host-breakdown-grid" style="display: grid; gap: 10px;">';
    
    // Host'ları anomali sayısına göre sırala
    const sortedHosts = Object.entries(hostBreakdown)
        .sort(([,a], [,b]) => b.anomaly_count - a.anomaly_count);
    
    sortedHosts.forEach(([host, data]) => {
        const anomalyRate = data.anomaly_rate || 0;
        const criticalityClass = anomalyRate > 5 ? 'critical' : 
                               anomalyRate > 2 ? 'warning' : 'normal';
        
        const barColor = criticalityClass === 'critical' ? '#e74c3c' : 
                        criticalityClass === 'warning' ? '#f39c12' : '#3498db';
        
        html += `
            <div class="host-breakdown-card" style="padding: 12px; background: #fff; border: 1px solid #dee2e6; border-radius: 6px;">
                <div class="host-info" style="display: flex; justify-content: space-between; align-items: center;">
                    <div class="host-name" style="font-weight: 600; color: #333;">${host}</div>
                    <div class="host-stats" style="display: flex; gap: 15px; font-size: 14px;">
                        <span style="color: ${barColor}; font-weight: 600;">Anomali: ${data.anomaly_count}</span>
                        <span style="color: #666;">Toplam: ${data.total_logs}</span>
                        <span style="color: #333; font-weight: 600;">%${anomalyRate.toFixed(2)}</span>
                    </div>
                </div>
                <div class="host-bar" style="margin-top: 8px; height: 6px; background: #e9ecef; border-radius: 3px; overflow: hidden;">
                    <div style="width: ${Math.min(anomalyRate * 10, 100)}%; height: 100%; background: ${barColor};"></div>
                </div>
            </div>
        `;
    });
    
    html += '</div></div>';
    return html;
}

/**
 * Kritik anomalileri render et
 */
function renderDBACriticalAnomalies(anomalies) {
    // Pagination değişkenleri - DÜZELTME: undefined kontrolü
    const itemsPerPage = 30;
    const currentPage = window.dbaCurrentPage || 1;  
    const totalPages = Math.ceil(anomalies.length / itemsPerPage);
    
    // Mevcut sayfadaki anomalileri al
    const startIndex = (currentPage - 1) * itemsPerPage;
    const endIndex = startIndex + itemsPerPage;
    const pageAnomalies = anomalies.slice(startIndex, endIndex);
    
    // Debug log ekle
    console.log('Rendering page:', currentPage, 'Items:', startIndex, '-', endIndex, 'Total:', anomalies.length);
    let html = '<div class="dba-critical-anomalies">';
    html += `<h3>⚡ Kritik Anomaliler (${anomalies.length} toplam)</h3>`;
    
    // Pagination controls
    html += '<div class="pagination-controls" style="margin-bottom: 15px;">';
    html += `<button onclick="changeDBAPage(${currentPage-1})" ${currentPage === 1 ? 'disabled' : ''}>← Önceki</button>`;
    html += `<span style="margin: 0 15px;">Sayfa ${currentPage} / ${totalPages}</span>`;
    html += `<button onclick="changeDBAPage(${currentPage+1})" ${currentPage === totalPages ? 'disabled' : ''}>Sonraki →</button>`;
    html += '</div>';
    
    html += '<div class="dba-anomaly-list" style="max-height: 500px; overflow-y: auto; padding: 10px; border: 1px solid #dee2e6; border-radius: 4px; background: #fff;">';
    
    pageAnomalies.forEach((anomaly, index) => {
        const globalIndex = startIndex + index + 1;
        const severityColor = anomaly.severity_color || '#e74c3c';
        
        html += `
            <div class="dba-anomaly-item" style="padding: 20px; margin-bottom: 15px; background: #fff; border-left: 4px solid ${severityColor}; border-radius: 4px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); width: 100%; box-sizing: border-box;">
                <div class="anomaly-header" style="display: flex; justify-content: space-between; margin-bottom: 10px;">
                    <div style="display: flex; gap: 15px; align-items: center;">
                        <span class="anomaly-rank" style="background: ${severityColor}; color: white; padding: 2px 8px; border-radius: 4px; font-weight: 600;">#${globalIndex}</span>
                        <span class="anomaly-time" style="background: #ffd700; color: #000; font-weight: bold; font-size: 14px; padding: 4px 10px; border-radius: 4px; border: 1px solid #000; text-transform: uppercase; letter-spacing: 0.5px;">${new Date(anomaly.timestamp).toLocaleString('tr-TR')}</span>
                        <span class="anomaly-host" style="background: #ffd700; color: #000; font-weight: bold; font-size: 14px; padding: 4px 10px; border-radius: 4px; border: 1px solid #000; text-transform: uppercase; letter-spacing: 0.5px;">${anomaly.source_host || anomaly.host || 'N/A'}</span>
                    </div>
                    <span class="anomaly-score" style="color: ${severityColor}; font-weight: 600;">Score: ${anomaly.anomaly_score?.toFixed(3) || anomaly.score?.toFixed(3) || 'N/A'}</span>
                </div>
                <div class="anomaly-message" style="background: #f8f9fa; padding: 15px; border-radius: 4px; font-family: 'Courier New', monospace; font-size: 15px; font-weight: bold; word-break: break-word; white-space: pre-wrap; line-height: 1.5; width: 100%; box-sizing: border-box; overflow-x: auto;">
                    ${escapeHtml(anomaly.message || anomaly.full_message || 'No message available')}
                </div>
                ${anomaly.component ? `<div style="margin-top: 8px; font-size: 12px; color: #666;">Component: ${anomaly.component}</div>` : ''}
            </div>
        `;
    });
    
    html += '</div>';
    
    // Alt pagination
    if (totalPages > 1) {
        html += '<div class="pagination-info" style="text-align: center; margin-top: 20px; color: #666;">';
        html += `Gösterilen: ${startIndex + 1}-${Math.min(endIndex, anomalies.length)} / Toplam: ${anomalies.length} anomali`;
        html += '</div>';
    }
    
    html += '</div>';
    
    // Anomalileri global değişkende sakla
    window.dbaAnomalies = anomalies;
    
    return html;
}

// Sayfa değiştirme fonksiyonu
window.changeDBAPage = function(page) {
    window.dbaCurrentPage = page;
    // Sonuçları yeniden render et
    if (window.lastDBAResult) {
        displayDBAAnalysisResults(
            window.lastDBAResult.result,
            window.lastDBAResult.cluster,
            window.lastDBAResult.startTime,
            window.lastDBAResult.endTime
        );
    }
};

/**
 * AI açıklamasını render et
 */
function renderDBAExplanation(explanation) {
    let html = '<div class="dba-ai-explanation" style="margin-top: 30px; padding: 20px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border-radius: 8px;">';
    html += '<h3 style="margin-bottom: 15px;">🤖 LCWGPT Analizi</h3>';
    html += '<div class="ai-explanation-content" style="background: rgba(255,255,255,0.95); color: #333; padding: 15px; border-radius: 6px;">';
    
    // formatAIResponse fonksiyonunu kullan (mevcut fonksiyon)
    html += typeof formatAIResponse === 'function' ? formatAIResponse(explanation) : escapeHtml(explanation);
    
    html += '</div>';
    html += '</div>';
    return html;
}

// Global fonksiyonları tanımla
window.openDBAAnalysisModal = openDBAAnalysisModal;
window.startDBAAnalysis = startDBAAnalysis;
window.displayDBAAnalysisResults = displayDBAAnalysisResults;
window.saveDBAAnalysis = function() { showNotification('Analiz kaydediliyor...', 'info'); };
window.exportDBAResults = function() { showNotification('Rapor indiriliyor...', 'info'); };
window.shareDBAResults = function() { showNotification('Paylaşım linki oluşturuluyor...', 'info'); };

/**
 * Temporal Analysis Render Et - SADELEŞTİRİLMİŞ VERSİYON
 */
// ML viz fonksiyonları kaldırıldı, alias/eski referanslar eklendi



// window.showAllComponents ve window.exportComponentAnalysis helper'ları uygulamada korunmalı (ML viz değil, component analiz yardımcılarıdır)
// ========== MİNİ GÖRSELLEŞTİRME FONKSİYONLARI ==========

/**
 * Mini ML Metriklerini Render Et
 */
function renderMiniMLMetrics(summary, scoreStats) {
    let html = '<div class="mini-ml-metrics">';
    html += '<div class="mini-metric-cards">';
    
    // Anomali oranı
    const anomalyRate = summary.anomaly_rate || 0;
    const statusClass = anomalyRate > 5 ? 'critical' : 
                       anomalyRate > 2 ? 'warning' : 'success';
    
    html += `
        <div class="mini-metric-card ${statusClass}">
            <div class="mini-metric-icon">🎯</div>
            <div class="mini-metric-data">
                <div class="mini-metric-value">${summary.n_anomalies}</div>
                <div class="mini-metric-label">Anomali</div>
            </div>
            <div class="mini-metric-percentage">%${anomalyRate.toFixed(1)}</div>
        </div>
    `;
    
    // Toplam log
    html += `
        <div class="mini-metric-card">
            <div class="mini-metric-icon">📄</div>
            <div class="mini-metric-data">
                <div class="mini-metric-value">${summary.total_logs.toLocaleString('tr-TR')}</div>
                <div class="mini-metric-label">Toplam Log</div>
            </div>
        </div>
    `;
    
    // Score range
    if (scoreStats && scoreStats.min !== undefined) {
        html += `
            <div class="mini-metric-card">
                <div class="mini-metric-icon">📊</div>
                <div class="mini-metric-data">
                    <div class="mini-metric-value">${scoreStats.min.toFixed(3)} - ${scoreStats.max.toFixed(3)}</div>
                    <div class="mini-metric-label">Score Range</div>
                </div>
            </div>
        `;
    }
    
    html += '</div></div>';
    return html;
}

/**
 * Mini Component Dashboard Render Et
 */
function renderMiniComponentDashboard(componentAnalysis) {
    let html = '<div class="mini-component-dashboard">';
    html += '<h5>🎛️ Component Dağılımı</h5>';
    html += '<div class="mini-component-list">';
    
    // En kritik 3 component'i göster
    const sortedComponents = Object.entries(componentAnalysis)
        .sort(([,a], [,b]) => b.anomaly_rate - a.anomaly_rate)
        .slice(0, 3);
    
    sortedComponents.forEach(([component, stats]) => {
        const criticalityClass = stats.anomaly_rate > 20 ? 'critical' : 
                               stats.anomaly_rate > 10 ? 'warning' : 'normal';
        
        html += `
            <div class="mini-component-item ${criticalityClass}">
                <span class="component-name">${getComponentIcon(component)} ${component}</span>
                <span class="component-rate">%${stats.anomaly_rate.toFixed(1)}</span>
                <div class="component-bar">
                    <div class="component-bar-fill" style="width: ${stats.anomaly_rate}%"></div>
                </div>
            </div>
        `;
    });
    
    if (Object.keys(componentAnalysis).length > 3) {
        html += `<p class="more-components">+${Object.keys(componentAnalysis).length - 3} component daha</p>`;
    }
    
    html += '</div></div>';
    return html;
}

/**
 * Mini Temporal Heatmap Render Et
 */
function renderMiniTemporalHeatmap(temporalAnalysis) {
    let html = '<div class="mini-temporal-heatmap">';
    html += '<h5>⏰ Saatlik Dağılım</h5>';
    
    const hourlyData = temporalAnalysis.hourly_distribution || {};
    const maxValue = Math.max(...Object.values(hourlyData), 1);
    
    html += '<div class="mini-heatmap-grid">';
    
    // 24 saati 6'lık gruplara böl
    for (let i = 0; i < 4; i++) {
        html += '<div class="mini-heatmap-row">';
        for (let j = 0; j < 6; j++) {
            const hour = i * 6 + j;
            const value = hourlyData[hour] || 0;
            const intensity = value / maxValue;
            const isPeak = temporalAnalysis.peak_hours?.includes(hour);
            
            html += `
                <div class="mini-heatmap-cell ${isPeak ? 'peak' : ''}" 
                     style="--intensity: ${intensity}"
                     title="Saat ${hour}:00 - ${value} anomali">
                    <span class="hour-label">${hour}</span>
                </div>
            `;
        }
        html += '</div>';
    }
    
    html += '</div>';
    
    if (temporalAnalysis.peak_hours && temporalAnalysis.peak_hours.length > 0) {
        html += `<p class="peak-hours-info">En yoğun saatler: ${temporalAnalysis.peak_hours.join(', ')}</p>`;
    }
    
    html += '</div>';
    return html;
}

/**
 * Tam Görselleştirme Modal'ını Göster
 */
function showFullVisualizationModal(historyId) {
    const item = queryHistory.find(h => h.id === historyId);
    if (!item || !item.childResult) {
        showNotification('Görselleştirme verisi bulunamadı', 'warning');
        return;
    }
    
    const mlData = item.childResult.sonuç?.data || item.childResult.sonuç || {};
    
    // Modal içeriği oluştur
    let modalContent = '<div class="full-visualization-modal-content">';
    modalContent += '<h3>📊 Detaylı ML Analiz Görselleştirmesi</h3>';
    
    // Tüm görselleştirmeleri ekle
    if (mlData.summary || mlData.anomaly_score_stats) {
        modalContent += renderMLModelMetrics(mlData.summary || {}, mlData.anomaly_score_stats || {});
    }
    
    
    if (mlData.temporal_analysis?.hourly_distribution) {
        modalContent += renderTemporalHeatmap(mlData.temporal_analysis);
    }
    

    modalContent += '</div>';
    
    // Modal'ı göster
    showModal('Detaylı ML Analiz Görselleştirmesi', modalContent);
    
    // Event listener'ları ekle
    setTimeout(() => {
        attachMLVisualizationListeners();
    }, 100);
}


// Global fonksiyon tanımlamaları
window.showFullVisualizationModal = showFullVisualizationModal;
window.exportAnomalyData = exportAnomalyData;


// Yardımcı fonksiyonlar - Mevcut global fonksiyonları güncelle
window.investigateAlertType = function(alertType) {
    console.log('Investigating alert type:', alertType);
    
    // Alert detaylarını modal'da göster
    if (!window.lastAnomalyResult || !window.lastAnomalyResult.sonuç) return;
    
    const securityAlerts = window.lastAnomalyResult.sonuç.security_alerts || 
                          window.lastAnomalyResult.sonuç.data?.security_alerts;
    
    const alertData = securityAlerts?.[alertType];
    if (!alertData) {
        showNotification('Alert verisi bulunamadı', 'warning');
        return;
    }
    
    let modalContent = '<div class="alert-investigation">';
    modalContent += `<h4>🔍 ${alertType} Detaylı İnceleme</h4>`;
    modalContent += `<p><strong>Toplam Olay:</strong> ${alertData.count}</p>`;
    
    if (alertData.indices && alertData.indices.length > 0) {
        modalContent += '<h5>Etkilenen Tüm Index\'ler:</h5>';
        modalContent += '<div class="index-grid">';
        alertData.indices.forEach(idx => {
            modalContent += `<span class="index-badge">${idx}</span>`;
        });
        modalContent += '</div>';
    }
    
    modalContent += '</div>';
    
    showModal(`${alertType} Alert İnceleme`, modalContent);
};

window.showAlertTimeline = function(alertType) {
    console.log('Showing timeline for:', alertType);
    showNotification('Timeline özelliği yakında eklenecek', 'info');
};

/**
 * Alert detaylarını göster
 */
window.showAlertDetails = function(alertType, alertData) {
    const alertTypeInfo = {
        'drop_operations': { 
            title: 'DROP Operation Detayları',
            description: 'DROP operasyonları veri kaybına neden olabilir. Bu operasyonların yetkili kullanıcılar tarafından yapıldığından emin olun.'
        },
        'out_of_memory': { 
            title: 'Out of Memory Detayları',
            description: 'Bellek yetersizliği MongoDB performansını ciddi şekilde etkileyebilir. Working set boyutunu ve bellek kullanımını kontrol edin.'
        },
        'restarts': { 
            title: 'Service Restart Detayları',
            description: 'MongoDB servisinin yeniden başlatılması bağlantı kayıplarına ve geçici erişim sorunlarına neden olabilir.'
        },
        'memory_limits': { 
            title: 'Memory Limit Exceeded Detayları',
            description: 'WiredTiger cache limiti aşıldı. Cache boyutunu artırmayı veya veri erişim paternlerini optimize etmeyi düşünün.'
        },
        'shutdowns': { 
            title: 'Shutdown Event Detayları',
            description: 'MongoDB kapanma olayları. Planlı bakım mı yoksa beklenmedik kapanma mı olduğunu kontrol edin.'
        },
        'assertions': { 
            title: 'Assertion Error Detayları',
            description: 'MongoDB internal assertion hataları. Bu hatalar yazılım problemlerine veya veri tutarsızlıklarına işaret edebilir.'
        },
        'fatal_errors': { 
            title: 'Fatal Error Detayları',
            description: 'Kritik hatalar MongoDB\'nin düzgün çalışmasını engelleyebilir. Acil müdahale gerekebilir.'
        }
    };
    
    const info = alertTypeInfo[alertType] || { title: alertType, description: 'Alert detayları' };
    
    let modalContent = `
        <div class="alert-details">
            <h4>${info.title}</h4>
            <p class="alert-description">${info.description}</p>
            
            <div class="alert-stats">
                <div class="stat-item">
                    <span class="stat-label">Tespit Edilen Olay Sayısı:</span>
                    <span class="stat-value">${alertData.count || 0}</span>
                </div>
            </div>
            
            ${alertData.indices && alertData.indices.length > 0 ? `
                <div class="alert-indices">
                    <h5>Etkilenen Log İndeksleri:</h5>
                    <div class="index-list">
                        ${alertData.indices.map(idx => `<span class="index-badge">${idx}</span>`).join('')}
                    </div>
                </div>
            ` : ''}
            
            <div class="alert-actions">
                <button class="btn btn-primary" onclick="investigateAlertType('${alertType}')">
                    🔍 Detaylı İncele
                </button>
                <button class="btn btn-secondary" onclick="exportAlertData('${alertType}')">
                    📥 Veriyi İndir
                </button>
            </div>
        </div>
    `;
    
    showModal(info.title, modalContent);
};



window.exportAlertData = function(alertType) {
    console.log('Exporting alert data for:', alertType);
    showNotification('Alert verisi indiriliyor...', 'success');
};


/**
 * Section'ı genişlet/daralt
 */
window.toggleSectionExpand = function() {
    const wrapper = document.querySelector('.result-wrapper');
    const button = document.querySelector('.btn-expand-section');
    
    wrapper.classList.toggle('expanded');
    
    if (wrapper.classList.contains('expanded')) {
        button.innerHTML = '⛶';
        button.title = 'Normal Görünüme Dön';
    } else {
        button.innerHTML = '⛶';
        button.title = 'Alanı Genişlet';
    }
};

/**
 * Sayfa yüklendiğinde kullanıcı tercihini geri yükle
 */
window.restoreViewMode = function() {
    const savedMode = localStorage.getItem('anomalyViewMode') || 'expanded';
    setTimeout(() => {
        if (document.querySelector('.critical-anomalies-section')) {
            toggleViewMode(savedMode);
        }
    }, 100);
};


// renderSeverityDistribution fonksiyonu script-ml-visualization.js'ye taşındı
const renderSeverityDistribution = window.renderSeverityDistribution;


var investigateAnomaly = window.investigateAnomaly;
var loadAnomalyChunk = window.loadAnomalyChunk;


// Global fonksiyon tanımlamaları
window.showComponentDetails = function(component) {
    console.log('Showing details for component:', component);
    const componentData = window.lastAnomalyResult?.sonuç?.data?.component_analysis?.[component] || 
                         window.lastAnomalyResult?.sonuç?.component_analysis?.[component];
    
    if (componentData) {
        let modalContent = `
            <h4>Component: ${component}</h4>
            <p>Anomali Sayısı: ${componentData.anomaly_count}</p>
            <p>Toplam Log: ${componentData.total_count}</p>
            <p>Anomali Oranı: %${componentData.anomaly_rate.toFixed(2)}</p>
        `;
        showModal('Component Detayları', modalContent);
    }
};

// ===== GLOBAL FONKSİYON TANIMLAMALARI =====
// Tüm global fonksiyonları burada tanımlıyoruz
window.toggleDetailedAnomalyList = toggleDetailedAnomalyList;
// Mesaj genişletme/daraltma fonksiyonu
window.toggleMessageFull = function(button) {
    const messageDiv = button.parentElement;
    const preview = messageDiv.querySelector('.message-preview');
    const fullMsg = messageDiv.querySelector('.message-full');
    
    if (fullMsg.style.display === 'none') {
        preview.style.display = 'none';
        fullMsg.style.display = 'block';
        button.textContent = 'Gizle';
        button.classList.add('expanded');
    } else {
        preview.style.display = 'inline';
        fullMsg.style.display = 'none';
        button.textContent = 'Tümünü Göster';
        button.classList.remove('expanded');
    }
};

// History detayında mesaj genişletme/daraltma fonksiyonu
window.toggleHistoryMessage = function(button) {
    const container = button.closest('.message-expandable');
    const preview = container.querySelector('.message-preview');
    const fullMsg = container.querySelector('.message-full');
    
    if (fullMsg.style.display === 'none') {
        preview.style.display = 'none';
        fullMsg.style.display = 'block';
        button.textContent = 'Mesajı Gizle';
    } else {
        preview.style.display = 'block';
        fullMsg.style.display = 'none';
        button.textContent = 'Tam Mesajı Göster';
    }
};

// History fonksiyonları
window.replayQuery = replayQuery;
window.showHistoryDetail = showHistoryDetail;

  
// Anomaly fonksiyonları - ONAY AKIŞI KALDIRILDI
// window.confirmAnomalyAnalysis = confirmAnomalyAnalysis;  // DEPRECATED
// window.cancelAnomalyAnalysis = cancelAnomalyAnalysis;    // DEPRECATED
// window.modifyAnomalyParameters = modifyAnomalyParameters; // DEPRECATED


// Export/Schedule fonksiyonları
window.exportAnomalyReport = exportAnomalyReport;
window.scheduleFollowUp = scheduleFollowUp;
window.saveFollowUp = saveFollowUp;


// Dosya yönetimi
window.deleteUploadedFile = deleteUploadedFile;

// Schema görüntüleme
window.viewSchema = viewSchema;

/**
 * Feature detaylarını göster
 * Bu fonksiyonları script.js dosyasının sonuna ekleyin (satır 5800 civarı)
 * Diğer window.functionName tanımlamalarının yanına
 */
window.showFeatureDetails = function(featureName) {
    console.log('Showing feature details for:', featureName);
    
    if (!window.lastAnomalyResult || !window.lastAnomalyResult.sonuç) {
        showNotification('Feature analiz verisi bulunamadı', 'warning');
        return;
    }
    
    const featureImportance = window.lastAnomalyResult.sonuç.feature_importance || 
                             window.lastAnomalyResult.sonuç.data?.feature_importance;
    
    const featureData = featureImportance?.[featureName];
    
    if (!featureData) {
        showNotification('Feature verisi bulunamadı', 'warning');
        return;
    }
    
    // Feature ismini formatla
    const featureLabel = formatFeatureName(featureName);
    const featureDescription = getFeatureDescription(featureName);
    
    let modalContent = '<div class="feature-detail-modal">';
    modalContent += `<h4>📊 ${featureLabel} - Detaylı Analiz</h4>`;
    
    if (featureDescription) {
        modalContent += `<p class="feature-detail-description">${featureDescription}</p>`;
    }
    
    modalContent += '<div class="feature-detail-stats">';
    modalContent += '<h5>İstatistikler:</h5>';
    modalContent += '<div class="stats-grid">';
    
    modalContent += `
        <div class="stat-item">
            <span class="stat-label">Anomaly Rate:</span>
            <span class="stat-value">${featureData.anomaly_rate?.toFixed(2) || 0}%</span>
        </div>
        <div class="stat-item">
            <span class="stat-label">Normal Rate:</span>
            <span class="stat-value">${featureData.normal_rate?.toFixed(2) || 0}%</span>
        </div>
        <div class="stat-item">
            <span class="stat-label">Ratio:</span>
            <span class="stat-value ${featureData.ratio > 5 ? 'critical' : ''}">${
                featureData.ratio === Infinity ? '∞' : featureData.ratio.toFixed(2)
            }x</span>
        </div>
    `;
    
    modalContent += '</div>';
    modalContent += '</div>';
    
    // Önemi ve tavsiyeler
    modalContent += '<div class="feature-detail-insights">';
    modalContent += '<h5>Analiz ve Öneriler:</h5>';
    
    if (featureData.ratio === Infinity || featureData.ratio > 10) {
        modalContent += `
            <div class="insight-alert critical">
                <strong>⚠️ Kritik Gösterge!</strong>
                <p>Bu özellik neredeyse sadece anomalilerde görülüyor. Sistem konfigürasyonunu acilen kontrol edin.</p>
            </div>
        `;
    } else if (featureData.ratio > 5) {
        modalContent += `
            <div class="insight-alert high">
                <strong>📍 Yüksek Önem</strong>
                <p>Bu özellik anomali tespitinde güçlü bir gösterge. Yakından takip edilmeli.</p>
            </div>
        `;
    } else if (featureData.ratio > 2) {
        modalContent += `
            <div class="insight-alert medium">
                <strong>📊 Orta Önem</strong>
                <p>Bu özellik anomali göstergesi olarak değerli. Diğer göstergelerle birlikte değerlendirilmeli.</p>
            </div>
        `;
    } else {
        modalContent += `
            <div class="insight-alert low">
                <strong>ℹ️ Düşük Önem</strong>
                <p>Bu özellik yardımcı bir gösterge. Tek başına anomali belirteci değil.</p>
            </div>
        `;
    }
    
    modalContent += '</div>';
    
    // Feature-specific öneriler
    modalContent += '<div class="feature-recommendations">';
    modalContent += '<h5>Özel Öneriler:</h5>';
    modalContent += '<ul>';
    
    // Feature'a özel öneriler
    if (featureName.includes('drop_operation')) {
        modalContent += '<li>DROP operasyonları tespit edildi. Yetkilendirme kontrollerini gözden geçirin.</li>';
        modalContent += '<li>Audit log\'ları aktif edin ve düzenli kontrol edin.</li>';
    } else if (featureName.includes('rare_component')) {
        modalContent += '<li>Nadir görülen component\'ler tespit edildi. Sistem konfigürasyonunu kontrol edin.</li>';
        modalContent += '<li>Bu component\'lerin neden nadir olduğunu araştırın.</li>';
    } else if (featureName.includes('memory') || featureName.includes('oom')) {
        modalContent += '<li>Bellek ile ilgili sorunlar tespit edildi. Working set boyutunu kontrol edin.</li>';
        modalContent += '<li>Cache ayarlarını optimize edin.</li>';
    } else if (featureName.includes('query') || featureName.includes('slow')) {
        modalContent += '<li>Sorgu performans sorunları tespit edildi. Index\'leri gözden geçirin.</li>';
        modalContent += '<li>Sorgu optimizasyonu yapın.</li>';
    }
    
    modalContent += '</ul>';
    modalContent += '</div>';
    
    modalContent += '</div>';
    
    showModal(`Feature Analizi: ${featureLabel}`, modalContent);
};

/**
 * Feature analiz detaylarını göster
 */
window.showFeatureAnalysisDetails = function() {
    console.log('Showing detailed feature analysis report');
    
    if (!window.lastAnomalyResult || !window.lastAnomalyResult.sonuç) {
        showNotification('Analiz verisi bulunamadı', 'warning');
        return;
    }
    
    const featureImportance = window.lastAnomalyResult.sonuç.feature_importance || 
                             window.lastAnomalyResult.sonuç.data?.feature_importance;
    
    if (!featureImportance || Object.keys(featureImportance).length === 0) {
        showNotification('Feature importance verisi bulunamadı', 'warning');
        return;
    }
    
    let modalContent = '<div class="feature-analysis-report">';
    modalContent += '<h3>📊 Feature Importance Detaylı Rapor</h3>';
    
    // Özet bilgiler
    modalContent += '<div class="report-summary">';
    modalContent += '<h4>Özet Bilgiler:</h4>';
    
    const totalFeatures = Object.keys(featureImportance).length;
    const criticalFeatures = Object.entries(featureImportance)
        .filter(([,data]) => data.ratio > 10).length;
    const highImportanceFeatures = Object.entries(featureImportance)
        .filter(([,data]) => data.ratio > 5).length;
    
    modalContent += `
        <div class="summary-stats">
            <div class="summary-stat">
                <span>Toplam Feature:</span> <strong>${totalFeatures}</strong>
            </div>
            <div class="summary-stat">
                <span>Kritik Feature:</span> <strong class="critical">${criticalFeatures}</strong>
            </div>
            <div class="summary-stat">
                <span>Yüksek Önemli:</span> <strong class="high">${highImportanceFeatures}</strong>
            </div>
        </div>
    `;
    modalContent += '</div>';
    
    // Feature tablosu
    modalContent += '<div class="feature-table-container">';
    modalContent += '<h4>Tüm Feature Listesi:</h4>';
    modalContent += '<table class="feature-analysis-table">';
    modalContent += '<thead>';
    modalContent += '<tr>';
    modalContent += '<th>Rank</th>';
    modalContent += '<th>Feature</th>';
    modalContent += '<th>Anomaly Rate</th>';
    modalContent += '<th>Normal Rate</th>';
    modalContent += '<th>Ratio</th>';
    modalContent += '<th>Önem</th>';
    modalContent += '</tr>';
    modalContent += '</thead>';
    modalContent += '<tbody>';
    
    // Feature'ları ratio'ya göre sırala
    const sortedFeatures = Object.entries(featureImportance)
        .sort(([,a], [,b]) => (b.ratio || 0) - (a.ratio || 0));
    
    sortedFeatures.forEach(([feature, data], index) => {
        const ratio = data.ratio || 1;
        const ratioClass = ratio > 10 ? 'critical' : 
                          ratio > 5 ? 'high' : 
                          ratio > 2 ? 'medium' : 'low';
        
        const importanceLabel = ratio > 10 ? 'KRİTİK' : 
                               ratio > 5 ? 'YÜKSEK' : 
                               ratio > 2 ? 'ORTA' : 'DÜŞÜK';
        
        modalContent += `
            <tr class="${ratioClass}">
                <td>#${index + 1}</td>
                <td><strong>${formatFeatureName(feature)}</strong></td>
                <td>${data.anomaly_rate?.toFixed(2) || 0}%</td>
                <td>${data.normal_rate?.toFixed(2) || 0}%</td>
                <td class="${ratioClass}">${ratio === Infinity ? '∞' : ratio.toFixed(2)}x</td>
                <td><span class="importance-badge ${ratioClass}">${importanceLabel}</span></td>
            </tr>
        `;
    });
    
    modalContent += '</tbody>';
    modalContent += '</table>';
    modalContent += '</div>';
    
    // Aksiyon önerileri
    modalContent += '<div class="report-recommendations">';
    modalContent += '<h4>🎯 Aksiyon Önerileri:</h4>';
    modalContent += '<ol>';
    
    if (criticalFeatures > 0) {
        modalContent += '<li><strong>Kritik Feature\'lar:</strong> ' + criticalFeatures + ' adet kritik feature tespit edildi. Bu özellikler için acil aksiyon alınmalı.</li>';
    }
    
    modalContent += '<li><strong>Model Optimizasyonu:</strong> Düşük önemli feature\'lar model performansını etkileyebilir. Feature selection yapılması önerilir.</li>';
    modalContent += '<li><strong>Threshold Ayarlaması:</strong> Yüksek ratio\'lu feature\'lar için özel threshold değerleri belirlenebilir.</li>';
    modalContent += '<li><strong>İzleme Stratejisi:</strong> Kritik feature\'lar için özel monitoring dashboard\'ları oluşturulmalı.</li>';
    
    modalContent += '</ol>';
    modalContent += '</div>';
    
    modalContent += '</div>';
    
    showModal('Feature Importance Detaylı Rapor', modalContent);
};


/**
 * Feature importance verilerini dışa aktar
 */
window.exportFeatureImportance = function() {
    console.log('Exporting feature importance data');
    
    if (!window.lastAnomalyResult || !window.lastAnomalyResult.sonuç) {
        showNotification('İndirilecek veri bulunamadı', 'warning');
        return;
    }
    
    const featureImportance = window.lastAnomalyResult.sonuç.feature_importance || 
                             window.lastAnomalyResult.sonuç.data?.feature_importance;
    
    if (!featureImportance) {
        showNotification('Feature importance verisi bulunamadı', 'warning');
        return;
    }
    
    // Export için veri hazırla
    const exportData = {
        timestamp: new Date().toISOString(),
        analysis_summary: {
            total_logs: window.lastAnomalyResult.sonuç.summary?.total_logs || 0,
            anomaly_count: window.lastAnomalyResult.sonuç.summary?.n_anomalies || 0,
            anomaly_rate: window.lastAnomalyResult.sonuç.summary?.anomaly_rate || 0
        },
        feature_importance: featureImportance,
        feature_analysis: Object.entries(featureImportance).map(([feature, data]) => ({
            feature_name: feature,
            feature_label: formatFeatureName(feature),
            anomaly_rate: data.anomaly_rate,
            normal_rate: data.normal_rate,
            ratio: data.ratio,
            importance: data.ratio > 10 ? 'CRITICAL' : 
                       data.ratio > 5 ? 'HIGH' : 
                       data.ratio > 2 ? 'MEDIUM' : 'LOW'
        })).sort((a, b) => (b.ratio || 0) - (a.ratio || 0))
    };
    
    // JSON olarak indir
    const dataStr = JSON.stringify(exportData, null, 2);
    const dataUri = 'data:application/json;charset=utf-8,'+ encodeURIComponent(dataStr);
    
    const exportFileDefaultName = `feature_importance_${new Date().toISOString().split('T')[0]}.json`;
    
    const linkElement = document.createElement('a');
    linkElement.setAttribute('href', dataUri);
    linkElement.setAttribute('download', exportFileDefaultName);
    linkElement.click();
    
    showNotification('Feature importance verisi başarıyla indirildi', 'success');
};

// Debug için fonksiyon versiyonunu logla
console.log('Global functions initialized. showHistoryDetail version check:', 
    window.showHistoryDetail.toString().includes('showHistoryDetail DEBUG') ? 'DEBUG VERSION' : 'STANDARD VERSION'
);


/**
 * YENİ: Sayfa yüklendiğinde kullanıcı tercihini geri yükle
 */
function restoreMessageTogglePreference() {
    const savedPreference = localStorage.getItem('showFormattedMessages');
    if (savedPreference === 'true') {
        // Critical anomalies toggle'ı
        const criticalToggle = document.getElementById('criticalMessageToggle');
        if (criticalToggle) {
            criticalToggle.checked = true;
            toggleCriticalAnomalyMessages();
        }
        
        // Detailed anomalies toggle'ı
        const detailedToggle = document.getElementById('detailedMessageToggle');
        if (detailedToggle) {
            detailedToggle.checked = true;
            toggleDetailedAnomalyMessages();
        }
    }
}


// ========== STORAGE MANAGER ENTEGRASYONU ==========



// Global fonksiyonları window'a ekle
window.activateModel = activateModel;
window.showStorageStatistics = showStorageStatistics;
window.showModelRegistry = showModelRegistry;
window.performStorageCleanup = performStorageCleanup;

var loadMoreCriticalAnomalies = window.loadMoreCriticalAnomalies;

// ============================================
// ML VISUALIZATION FONKSİYONLARINI WINDOW'A ATA
// ============================================
// Bu fonksiyonlar script-anomaly.js tarafından kullanılıyor
window.renderMLModelMetrics = renderMLModelMetrics;
window.renderOnlineLearningStatus = renderOnlineLearningStatus;
window.renderComponentComparisonChart = renderComponentComparisonChart;
window.formatFeatureName = formatFeatureName;
window.getFeatureDescription = getFeatureDescription;
window.getFeatureInsight = getFeatureInsight;
window.renderFeatureImportanceChart = renderFeatureImportanceChart;
window.renderComponentDashboard = renderComponentDashboard;
window.getComponentIcon = getComponentIcon;
window.renderTemporalHeatmap = renderTemporalHeatmap;
window.analyzeTemporalPatterns = analyzeTemporalPatterns;
window.findConsecutiveHours = findConsecutiveHours;
window.detectRegularPattern = detectRegularPattern;
window.attachMLVisualizationListeners = attachMLVisualizationListeners;
window.renderAnomalyScoreDistribution = renderAnomalyScoreDistribution;
window.renderSeverityDistribution = renderSeverityDistribution;

console.log('✅ ML Visualization functions attached to window');

// ============================================
// TEST SUITE İÇİN WINDOW ATAMALARI
// ============================================
// Bu bölüm test suite'in fonksiyonlara erişebilmesi için eklenmiştir
// Mevcut kod yapısını bozmaz, sadece referans sağlar

// Ana fonksiyonları güvenli şekilde window objesine ata
if (typeof handleQuery !== 'undefined') {
    window.handleQuery = handleQuery;
}
if (typeof parseAndFormatDescription !== 'undefined') {
    window.parseAndFormatDescription = parseAndFormatDescription;
}
if (typeof showAllComponents !== 'undefined') {
    window.showAllComponents = showAllComponents;
}
if (typeof exportComponentAnalysis !== 'undefined') {
    window.exportComponentAnalysis = exportComponentAnalysis;
}
if (typeof loadMoreCriticalAnomalies !== 'undefined') {
    window.loadMoreCriticalAnomalies = loadMoreCriticalAnomalies;
}

// formatMetricBox fonksiyonu varsa ata
if (typeof formatMetricBox !== 'undefined') {
    window.formatMetricBox = formatMetricBox;
}

// Diğer helper fonksiyonlar (eğer mevcutsa)
if (typeof toggleMessageExpand !== 'undefined') {
    window.toggleMessageExpand = toggleMessageExpand;
}
if (typeof showFeatureDetails !== 'undefined') {
    window.showFeatureDetails = showFeatureDetails;
}
if (typeof showFeatureAnalysisDetails !== 'undefined') {
    window.showFeatureAnalysisDetails = showFeatureAnalysisDetails;
}
if (typeof exportFeatureImportance !== 'undefined') {
    window.exportFeatureImportance = exportFeatureImportance;
}
if (typeof toggleViewMode !== 'undefined') {
    window.toggleViewMode = toggleViewMode;
}
if (typeof toggleDetailedAnomalyList !== 'undefined') {
    window.toggleDetailedAnomalyList = toggleDetailedAnomalyList;
}
if (typeof toggleCriticalAnomalyMessages !== 'undefined') {
    window.toggleCriticalAnomalyMessages = toggleCriticalAnomalyMessages;
}
if (typeof loadLastAnomalyFromStorage !== 'undefined') {
    window.loadLastAnomalyFromStorage = loadLastAnomalyFromStorage;
}

// Connect, status ve diğer ana fonksiyonlar
if (typeof handleConnect !== 'undefined') {
    window.handleConnect = handleConnect;
}
if (typeof handleCollections !== 'undefined') {
    window.handleCollections = handleCollections;
}
if (typeof openSystemResetModal !== 'undefined') {
    window.openSystemResetModal = openSystemResetModal;
}
if (typeof handleClear !== 'undefined') {
    window.handleClear = handleClear;
}

// DBA Analysis fonksiyonları
if (typeof openDBAAnalysisModal !== 'undefined') {
    window.openDBAAnalysisModal = openDBAAnalysisModal;
}
if (typeof startDBAAnalysis !== 'undefined') {
    window.startDBAAnalysis = startDBAAnalysis;
}
if (typeof displayDBAAnalysisResults !== 'undefined') {
    window.displayDBAAnalysisResults = displayDBAAnalysisResults;
}

// History fonksiyonları
if (typeof addToHistory !== 'undefined') {
    window.addToHistory = addToHistory;
}
if (typeof reloadAllHistory !== 'undefined') {
    window.reloadAllHistory = reloadAllHistory;
}
if (typeof clearHistory !== 'undefined') {
    window.clearHistory = clearHistory;
}
if (typeof exportHistory !== 'undefined') {
    window.exportHistory = exportHistory;
}

// Storage fonksiyonları
if (typeof showStorageStatistics !== 'undefined') {
    window.showStorageStatistics = showStorageStatistics;
}
if (typeof showModelRegistry !== 'undefined') {
    window.showModelRegistry = showModelRegistry;
}
if (typeof performStorageCleanup !== 'undefined') {
    window.performStorageCleanup = performStorageCleanup;
}

// Debug için hangi fonksiyonların export edildiğini logla
const exportedFunctions = {
    handleQuery: typeof window.handleQuery,
    parseAndFormatDescription: typeof window.parseAndFormatDescription,
    showAllComponents: typeof window.showAllComponents,
    exportComponentAnalysis: typeof window.exportComponentAnalysis,
    loadMoreCriticalAnomalies: typeof window.loadMoreCriticalAnomalies,
    formatMetricBox: typeof window.formatMetricBox,
    toggleDetailedAnomalyList: typeof window.toggleDetailedAnomalyList,
    handleConnect: typeof window.handleConnect,
    openSystemResetModal: typeof window.openSystemResetModal
};

console.log('✅ Script.js functions exported to window for testing');
console.log('Exported functions:', exportedFunctions);

// ============================================
// DOSYA SONU
// ============================================
// Tüm anomaly render fonksiyonları script-anomaly.js modülünde
// Performance analiz fonksiyonları bu dosyada kalıyor