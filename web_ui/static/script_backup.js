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

// Sayfa yüklendiğinde storage butonlarını ekle (DOMContentLoaded event'inde)
function addStorageMenuButtons() {
    const quickActions = document.querySelector('.quick-actions');
    if (quickActions && isConnected) {
        // Storage dropdown menü ekle
        const storageDropdown = document.createElement('div');
        storageDropdown.className = 'storage-dropdown';
        storageDropdown.innerHTML = `
            <button class="btn btn-secondary dropdown-toggle" onclick="toggleStorageMenu()">
                💾 STORAGE
            </button>
            <div class="storage-menu" id="storageMenu" style="display: none;">
                <button onclick="showStorageStatistics()">📊 İstatistikler</button>
                <button onclick="showModelRegistry()">🤖 Model Registry</button>
                <button onclick="loadMongoDBHistory()">📜 Geçmiş Analizler</button>
                <button onclick="performStorageCleanup()">🗑️ Temizlik</button>
            </div>
        `;
        quickActions.appendChild(storageDropdown);
    }
}

// Storage menüsünü toggle et
window.toggleStorageMenu = function() {
    const menu = document.getElementById('storageMenu');
    if (menu) {
        menu.style.display = menu.style.display === 'none' ? 'block' : 'none';
    }
};

// MongoDB geçmişini yükle ve göster
window.loadMongoDBHistory = async function() {
    const history = await loadAnomalyHistoryFromMongoDB({ limit: 50 });
    
    let modalContent = '<div class="mongodb-history">';
    modalContent += '<h3>📜 MongoDB Anomali Geçmişi</h3>';
    
    if (history && history.length > 0) {
        modalContent += '<div class="history-list">';
        history.forEach(item => {
            modalContent += `
                <div class="history-item">
                    <div class="history-date">${new Date(item.timestamp).toLocaleString('tr-TR')}</div>
                    <div class="history-summary">
                        Anomali: ${item.anomaly_count} / ${item.logs_analyzed} 
                        (%${item.anomaly_rate?.toFixed(2) || 0})
                    </div>
                    <button onclick="viewStoredAnalysis('${item.analysis_id}')">Detay</button>
                </div>
            `;
        });
        modalContent += '</div>';
    } else {
        modalContent += '<p>Kayıtlı analiz bulunamadı.</p>';
    }
    
    modalContent += '</div>';
    showModal('MongoDB Anomali Geçmişi', modalContent);
};

// Kaydedilmiş analizi görüntüle
window.viewStoredAnalysis = async function(analysisId) {
    try {
        const response = await fetch(`${API_ENDPOINTS.anomalyDetail}/${analysisId}?api_key=${apiKey}`);
        
        if (response.ok) {
            const data = await response.json();
            
            // Detayları göster
            displayAnomalyResults({
                durum: 'tamamlandı',
                işlem: 'anomaly_analysis',
                sonuç: data.analysis
            });
            
            closeModal();
        }
    } catch (error) {
        console.error('Error loading analysis detail:', error);
        showNotification('Analiz detayı yüklenemedi', 'error');
    }
};
// Sayfa yüklendiğinde
document.addEventListener('DOMContentLoaded', async () => {
    // DOM element referanslarını initialize et (script-core.js'den)
    window.initializeElements();
    
    // Local alias'ları güncelle
    elements = window.elements;
    
    // Session ID oluştur
    if (!window.currentSessionId) {
        window.currentSessionId = `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
        console.log('📍 Session initialized:', window.currentSessionId);
    }
    
    initializeEventListeners();
    checkInitialStatus();
    restoreViewMode();
    
    // İlk yükleme - boş başla
    loadHistory();
    
    // API key localStorage'dan kontrol et (güvenlik için optional)
    const savedApiKey = localStorage.getItem('saved_api_key');
    if (savedApiKey && elements.apiKeyInput) {
        console.log('📌 Found saved API key, auto-connecting...');
        elements.apiKeyInput.value = savedApiKey;
        
        // Otomatik bağlan
        await handleConnect();
        
        // Bağlantı başarılıysa TÜM MongoDB verilerini yükle
        if (isConnected) {
            console.log('📊 Loading all data from MongoDB...');
            showNotification('MongoDB\'den veriler yükleniyor...', 'info');
            
            try {
                // Paralel olarak tüm verileri yükle
                const results = await Promise.all([
                    loadHistory(),                    // Query history
                    loadAnomalyHistoryFromMongoDB({limit: 50}),  // Anomaly history (mevcut fonksiyon)
                    loadAndMergeDBAHistory(),         // DBA analyses (mevcut fonksiyon)
                    checkStorageSize()                // Storage durumu
                ]);
                
                console.log('✅ All MongoDB data loaded successfully');
                console.log(`   📝 Query History: ${queryHistory.length} items`);
                console.log(`   🔍 Anomaly History: ${results[1]?.length || 0} items`);
                console.log(`   📊 DBA History merged`);
                
                showNotification('Tüm veriler MongoDB\'den yüklendi', 'success');
                
                // History display'i güncelle
                updateHistoryDisplay();
                
            } catch (error) {
                console.error('Error loading MongoDB data:', error);
                showNotification('Bazı veriler yüklenemedi', 'warning');
            }
        }
    } else {
        console.log('ℹ️ No saved API key, manual connection required');
    }
});

/**
 * Event listener'ları başlat
 */
function initializeEventListeners() {
    console.log('Initializing event listeners...'); // DEBUG LOG
    
    // Bağlan butonu
    elements.connectBtn.addEventListener('click', handleConnect);
    
    // Enter tuşu ile bağlan
    elements.apiKeyInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') handleConnect();
    });
    
    // Sorgu gönder butonu
    elements.queryBtn.addEventListener('click', handleQuery);
    
    // Enter tuşu ile sorgu gönder (Ctrl+Enter)
    elements.queryInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter' && e.ctrlKey) handleQuery();
    });
    
    // Hızlı işlem butonları
    document.getElementById('statusBtn').addEventListener('click', handleStatus);
    
    // Log Yükle butonu
    document.getElementById('logUploadBtn').addEventListener('click', () => {
        console.log('Log upload button clicked'); // DEBUG LOG
        document.getElementById('logFileInput').click();
    });

    // Dosya yükleme için event listener'lar
    const logFileInput = document.getElementById('logFileInput');
    const uploadDropzone = document.getElementById('uploadDropzone');
    
    if (logFileInput) {
        logFileInput.addEventListener('change', handleFileUpload);
    }
    
    if (uploadDropzone) {
        uploadDropzone.addEventListener('click', () => {
            logFileInput.click();
        });
        
        // Drag and Drop
        uploadDropzone.addEventListener('dragover', (e) => {
            e.preventDefault();
            uploadDropzone.classList.add('drag-over');
        });
        
        uploadDropzone.addEventListener('dragleave', () => {
            uploadDropzone.classList.remove('drag-over');
        });
        
        uploadDropzone.addEventListener('drop', (e) => {
            e.preventDefault();
            uploadDropzone.classList.remove('drag-over');
            
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                handleFileUpload({ target: { files: files } });
            }
        });
    }

    // Anomali Analizi butonu  
    document.getElementById('anomalyAnalysisBtn').addEventListener('click', () => {
        console.log('Anomaly Analysis Button clicked!');
        
        // Modal'ı göster
        document.getElementById('anomalyModal').style.display = 'block';
        
        // Dosyaları güncelle ama data source'u resetleme
        updateUploadedFilesList();
        
        // Eğer önceden upload seçiliyse, tekrar seç
        if (selectedDataSource === 'upload') {
            document.querySelector('input[name="dataSource"][value="upload"]').checked = true;
            updateSourceInputs('upload');
        }
        // YENİ: OpenSearch seçiliyse listeleri yükle
        else if (selectedDataSource === 'opensearch' && isConnected) {
            document.querySelector('input[name="dataSource"][value="opensearch"]').checked = true;
            updateSourceInputs('opensearch');
            setTimeout(() => {
                loadMongoDBHosts();
                loadClusters();
            }, 200);
        }
    });

    // DBA Analizi butonu - YENİ
    document.getElementById('dbaAnalysisBtn').addEventListener('click', () => {
        console.log('DBA Analysis Button clicked!');
        openDBAAnalysisModal();
    });
    
    // Event delegation for dynamically loaded buttons
    document.addEventListener('click', function(e) {
        if (e.target && e.target.id === 'dbaAnalysisBtn') {
            console.log('DBA TAVSİYE SİSTEMİ clicked via delegation!');
            e.preventDefault();
            openDBAAnalysisModal();
        }
    });
    
    
    // Anomaly Modal içindeki Analizi Başlat butonu  
    document.getElementById('startAnalysisBtn').addEventListener('click', handleAnalyzeLog);
    

    // Refresh hosts button - CLUSTER DESTEĞİ İLE
    document.getElementById('refreshHostsBtn')?.addEventListener('click', () => {
        const hostMode = document.querySelector('input[name="hostSelectionMode"]:checked')?.value || 'single';
        
        if (hostMode === 'single') {
            loadMongoDBHosts();
            showNotification('Host listesi yenileniyor...', 'info');
        } else if (hostMode === 'cluster') {
            loadClusters();
            showNotification('Cluster listesi yenileniyor...', 'info');
        }
    });
    
    // Örnek sorgu chip'leri
    document.querySelectorAll('.chip').forEach(chip => {
        chip.addEventListener('click', (e) => {
            console.log('Chip clicked:', e.target.dataset.query); // DEBUG LOG
            elements.queryInput.value = e.target.dataset.query;
            elements.queryInput.focus();
        });
    });
    
    // Modal kapatma
    document.querySelector('#modal .close').addEventListener('click', closeModal);
    window.addEventListener('click', (e) => {
        if (e.target === elements.modal) closeModal();
    });
    
    // Anomaly Modal kapatma butonu için event listener ekle
    document.querySelector('#anomalyModal .close').addEventListener('click', closeAnomalyModal);
    
    // Anomaly modal dışına tıklama ile kapatma
    window.addEventListener('click', (e) => {
        const anomalyModal = document.getElementById('anomalyModal');
        if (e.target === anomalyModal) {
            closeAnomalyModal();
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
    
    console.log('Event listeners initialized successfully'); // DEBUG LOG
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
 * Storage'dan son anomali analizini yükle
 * Sayfa yenilendiğinde veya ilk bağlantıda otomatik çalışır
 */
async function loadLastAnomalyFromStorage() {
    // Connection durumunu bekle (max 5 saniye)
    let retryCount = 0;
    while ((!isConnected || !apiKey) && retryCount < 50) {
        await new Promise(resolve => setTimeout(resolve, 100));
        retryCount++;
    }
    
    if (!isConnected || !apiKey) {
        console.log('Not connected after retry, skipping storage load');
        return;
    }
    
    try {
        console.log('Loading last anomaly analysis from storage...');
        
        // Backend'den storage kontrolü yap
        const response = await fetch(API_ENDPOINTS.query, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                query: "son anomali analizi",  // Backend'de anomali keyword'ü tetikler
                api_key: apiKey
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
                showNotification(
                    `Önceki analiz yüklendi: ${anomalyCount} anomali (${new Date(timestamp).toLocaleString('tr-TR')})`,
                    'info'
                );
                
                // Query input'a ipucu ekle
                if (elements.queryInput) {
                    elements.queryInput.placeholder = "Önceki analizle ilgili sorularınızı sorabilirsiniz...";
                }
                
                return true;
            }
        }
    } catch (error) {
        console.error('Error loading from storage:', error);
    }
    
    console.log('No previous analysis found in storage');
    return false;
}

// displayConfirmationDialog

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
            
            console.log('Connection successful, updating UI...'); // DEBUG LOG
            
            // UI'yi güncelle
            elements.mainContent.style.display = 'block';
            elements.apiKeyInput.disabled = true;
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
        
        const isChatAnomalyQuery = hasKeyword && (hasAnomalyOrLog || window.lastAnomalyResult);
        console.log('Is chat anomaly query:', isChatAnomalyQuery);
        console.log('=== END DEBUG ===');

        // Chat anomali sorgusu kontrolü
        if (isChatAnomalyQuery) {
            console.log('🔍 DEBUG: Chat anomaly query detected, checking lastAnomalyResult...');
            console.log('🔍 DEBUG: window.lastAnomalyResult exists:', !!window.lastAnomalyResult);
            
            // Eğer lastAnomalyResult yoksa storage'dan yüklemeyi dene
            if (!window.lastAnomalyResult) {
                console.log('🔍 DEBUG: No lastAnomalyResult found, attempting to load from storage...');
                console.log('🔍 DEBUG: Calling loadLastAnomalyFromStorage()...');
                
                try {
                    const loaded = await loadLastAnomalyFromStorage();
                    console.log('🔍 DEBUG: loadLastAnomalyFromStorage() returned:', loaded);
                    console.log('🔍 DEBUG: window.lastAnomalyResult after storage load:', !!window.lastAnomalyResult);
                    
                    if (!loaded) {
                        console.log('❌ DEBUG: Storage load failed, showing warning and exiting');
                        console.log('⚠️ DEBUG: No storage data found, will proceed with normal query');
                        // Storage'da da veri yoksa kullanıcıyı bilgilendir
                        showNotification('Önceki analiz bulunamadı, yeni analiz yapılacak', 'info');
                        showLoader(false);
                        elements.queryBtn.disabled = false;
                        //return;
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
            } else {
                console.log('✅ DEBUG: window.lastAnomalyResult already exists, skipping storage load');
            }
            
            // Artık window.lastAnomalyResult kesinlikle var
            if (window.lastAnomalyResult) {
                console.log('✅ Chat anomaly query CONFIRMED, using LCWGPT endpoint');
                console.log('🔍 DEBUG: lastAnomalyResult structure check:');
                console.log('🔍 DEBUG: - storage_info:', !!window.lastAnomalyResult.storage_info);
                console.log('🔍 DEBUG: - storage_id:', !!window.lastAnomalyResult.storage_id);
                console.log('🔍 DEBUG: - analysis_id from storage_info:', window.lastAnomalyResult.storage_info?.analysis_id);
            
            // Son anomali analizinin ID'sini al
            const lastAnalysisId = window.lastAnomalyResult.storage_info?.analysis_id || 
                                  window.lastAnomalyResult.storage_id;
            
            console.log('🔍 DEBUG: Final analysis_id for LCWGPT:', lastAnalysisId);
            
            console.log('Analysis ID:', lastAnalysisId);
            console.log('Sending query to LCWGPT:', query);
            
            showLoader(true);
            
            try {
                // Tek chunk gönderiliyor
                const chatResponse = await fetch('/api/chat-query-anomalies', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        query: query,
                        api_key: apiKey,
                        analysis_id: lastAnalysisId
                    })
                });
                
                console.log('LCWGPT response status:', chatResponse.status);
                
                if (chatResponse.ok) {
                    const chatResult = await chatResponse.json();
                    console.log('LCWGPT result:', chatResult);
                    
                    // Chat sonucunu özel formatta göster
                    displayChatAnomalyResult(chatResult, query);
                    
                    
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
                    
                    return; // Burada return ediyoruz
                } else {
                    console.error('LCWGPT request failed:', chatResponse.status);
                    const errorText = await chatResponse.text();
                    console.error('Error response:', errorText);
                }
            } catch (error) {
                console.error('LCWGPT error:', error);
            } finally {
                showLoader(false);
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

// [REMOVED] Tüm anomali analiz fonksiyonları script-anomaly.js'e taşındı
// Aşağıdaki fonksiyonlar artık script-anomaly.js modülünde tanımlı:
// - updateParentAnomalyQuery()
// - displayResult() 
// - displayChatAnomalyResult()
// - decodeHtmlEntities()
// - formatAIResponse()
// - displayAnomalyAnalysisResult()
// - exportAnomalyReport()
// - scheduleFollowUp()
// - saveFollowUp()
// - formatSection()
// - highlightNumbers()
// - parseAIExplanationFromText()
// - handleAnalyzeLog()
// - closeAnomalyModal()
// - displayAnomalyResults()

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

// ============================================
// ANOMALY FONKSİYONLARI
// ============================================
// Aşağıdaki fonksiyonlar script-anomaly.js modülüne taşındı:
// - displayChatAnomalyResult() → satır 95-216
// - decodeHtmlEntities() → satır 216-236  
// - formatAIResponse() → satır 236-317
// - displayAnomalyAnalysisResult() → satır 317-575
// - exportAnomalyReport() → satır 575-599
// - scheduleFollowUp() → satır 599-627
// - saveFollowUp() → satır 627-640
// - formatSection() → satır 640-650
// - highlightNumbers() → satır 650-686
// - parseAIExplanationFromText() → satır 686-730
// ============================================

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


// Yardımcı fonksiyon: Açıklama metnini parse et ve formatla
function parseAndFormatDescription(description) {
    let html = '';
    
    // Performance analiz için özel parse - YENİ
    if (description.includes('QUERY PERFORMANCE ANALİZİ') || 
        description.includes('PERFORMANS SKORU:')) {
        // Bu durumda açıklama zaten formatlanmış, direkt göster
        return `<pre class="formatted-description">${escapeHtml(description)}</pre>`;
    }
    
    // Önce ana açıklamayı ayır
    const lines = description.split(' - ');
    
    if (lines.length > 1) {
        // İlk satır ana açıklama
        html += `<div class="main-description">${escapeHtml(lines[0])}</div>`;
        
        // Geri kalanlar metrik veya detaylar
        html += '<div class="metric-grid">';
        
        for (let i = 1; i < lines.length; i++) {
            const line = lines[i].trim();
            
            // Metrik tipini belirle
            if (line.includes('CPU') || line.includes('Kullanım Yüzdesi') || line.includes('Kullanım Oranı')) {
                html += formatMetricBox('💻', line, 'cpu-metric');
            } else if (line.includes('Bellek') || line.includes('Memory') || line.includes('Toplam Bellek')) {
                html += formatMetricBox('💾', line, 'memory-metric');
            } else if (line.includes('Disk')) {
                html += formatMetricBox('💿', line, 'disk-metric');
            } else if (line.includes('Durum') || line.includes('Status')) {
                html += formatMetricBox('🔄', line, 'status-metric');
            } else if (line.includes('Port') || line.includes('IP')) {
                html += formatMetricBox('🌐', line, 'network-metric');
            } else if (line.includes('Çalışma Süresi') || line.includes('Uptime')) {
                html += formatMetricBox('⏱️', line, 'uptime-metric');
            } else if (line.includes('İşletim Sistemi') || line.includes('OS')) {
                html += formatMetricBox('🖥️', line, 'status-metric');
            } else if (line.includes('Hostname')) {
                html += formatMetricBox('🏷️', line, 'network-metric');
            } else {
                html += formatMetricBox('📌', line, 'general-metric');
            }
        }
        
        html += '</div>';
    } else {
        // Tek satırlık açıklama
        html += `<div class="simple-description">${escapeHtml(description)}</div>`;
    }
    
    return html;
}

// Yardımcı fonksiyon: Metrik kutusunu formatla
function formatMetricBox(icon, text, className) {
    // Anahtar:Değer formatını ayır
    const parts = text.split(':');
    
    if (parts.length === 2) {
        const label = parts[0].trim();
        let value = parts[1].trim();
        
        // Yüzde değerlerini vurgula
        if (value.includes('%')) {
            value = `<span class="percentage-value">${escapeHtml(value)}</span>`;
        }
        // Sayısal değerleri vurgula
        else if (/\d+/.test(value)) {
            value = `<span class="numeric-value">${escapeHtml(value)}</span>`;
        } else {
            value = escapeHtml(value);
        }
        
        return `
            <div class="metric-box ${className}">
                <div class="metric-icon">${icon}</div>
                <div class="metric-content">
                    <div class="metric-label">${escapeHtml(label)}</div>
                    <div class="metric-value">${value}</div>
                </div>
            </div>
        `;
    } else {
        // Düz metin
        return `
            <div class="metric-box ${className}">
                <div class="metric-icon">${icon}</div>
                <div class="metric-text">${escapeHtml(text)}</div>
            </div>
        `;
    }
}

// Yardımcı fonksiyon: Basit metrik sonucu mu kontrol et
function isSimpleMetricResult(result) {
    // Eğer sonuç sadece birkaç basit metrik içeriyorsa JSON gösterme
    if (result.intermediate_steps && result.tools_used && Object.keys(result).length <= 3) {
        return true;
    }
    return false;
}

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
 * Sistem durumunu göster
 */
async function handleStatus() {
    if (!isConnected) {
        showNotification('Önce bağlantı kurmalısınız', 'error');
        return;
    }
    
    showLoader(true);
    
    try {
        const response = await fetch(API_ENDPOINTS.status);
        const data = await response.json();
        
        let content = '<h4>Sistem Durumu</h4>';
        content += '<div class="status-grid">';
        
        if (data.agent_status) {
            const status = data.agent_status;
            content += `
                <div class="status-item">
                    <span class="status-label">MongoDB Bağlantısı:</span>
                    <span class="status-value ${status.mongodb_connected ? 'success' : 'error'}">
                        ${status.mongodb_connected ? 'Aktif' : 'Kapalı'}
                    </span>
                </div>
                <div class="status-item">
                    <span class="status-label">OpenAI Bağlantısı:</span>
                    <span class="status-value ${status.openai_connected ? 'success' : 'error'}">
                        ${status.openai_connected ? 'Aktif' : 'Kapalı'}
                    </span>
                </div>
                <div class="status-item">
                    <span class="status-label">Agent Durumu:</span>
                    <span class="status-value ${status.agent_ready ? 'success' : 'error'}">
                        ${status.agent_ready ? 'Hazır' : 'Hazır Değil'}
                    </span>
                </div>
                <div class="status-item">
                    <span class="status-label">Konuşma Geçmişi:</span>
                    <span class="status-value">${status.conversation_length} mesaj</span>
                </div>
            `;
            
            if (status.available_tools) {
                content += `
                    <div class="status-item">
                        <span class="status-label">Mevcut Araçlar:</span>
                        <span class="status-value">${status.available_tools.join(', ')}</span>
                    </div>
                `;
            }
        }
        
        content += '</div>';
        content += `<p class="status-timestamp">Kontrol zamanı: ${new Date().toLocaleString('tr-TR')}</p>`;
        
        showModal('Sistem Durumu', content);
    } catch (error) {
        showNotification('Durum bilgisi alınamadı', 'error');
    } finally {
        showLoader(false);
    }
}

/**
 * Temizleme işlemi
 */
function handleClear() {
    elements.queryInput.value = '';
    elements.resultSection.style.display = 'none';
    elements.resultContent.innerHTML = '';
    showNotification('Ekran temizlendi', 'info');
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
 * Veri kaynağı input alanlarını güncelle
 */
function updateSourceInputs(source) {
    console.log('updateSourceInputs called with source:', source); // DEBUG LOG
    
    // Tüm input alanlarını gizle
    document.getElementById('uploadSourceInputs').style.display = 'none';
    document.getElementById('mongoSourceInputs').style.display = 'none';
    document.getElementById('serverSourceInputs').style.display = 'none';
    document.getElementById('fileSelectionSection').style.display = 'none';
    document.getElementById('opensearchSourceInputs').style.display = 'none'; // YENİ
    
    // Seçilen kaynağa göre göster
    switch(source) {
        case 'file':
            console.log('Showing file source inputs'); // DEBUG LOG
            // Config dosyası seçildi, ekstra input gerekmez
            break;
        case 'upload':
            console.log('Showing upload source inputs'); // DEBUG LOG
            document.getElementById('uploadSourceInputs').style.display = 'block';
            document.getElementById('fileSelectionSection').style.display = 'block';
            break;
        case 'mongodb_direct':
            console.log('Showing MongoDB direct source inputs'); // DEBUG LOG
            document.getElementById('mongoSourceInputs').style.display = 'block';
            break;
        case 'test_servers':
            console.log('Showing test servers source inputs'); // DEBUG LOG
            document.getElementById('serverSourceInputs').style.display = 'block';
            break;
        case 'opensearch':
            console.log('Showing OpenSearch source inputs');
            document.getElementById('opensearchSourceInputs').style.display = 'block';
            
            // Default olarak single mode seçili olsun
            const singleModeRadio = document.querySelector('input[name="hostSelectionMode"][value="single"]');
            if (singleModeRadio) {
                singleModeRadio.checked = true;
            }
            
            // Single mode UI'ını göster
            document.getElementById('singleHostSelection').style.display = 'block';
            document.getElementById('clusterSelection').style.display = 'none';
            
            // MongoDB sunucularını yükle (single mode için)
            loadMongoDBHosts();
            
            // Cluster listesini de arka planda yükle (kullanıcı değiştirirse hazır olsun)
            setTimeout(() => {
                loadClusters();
            }, 500);
            break;
        default:
            console.log('Unknown source type:', source); // DEBUG LOG
    }
    
    // Analiz butonunu güncelle
    validateAnalysisButton();
}

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
 * Analiz butonu validasyonu
 */
function validateAnalysisButton() {
    console.log('validateAnalysisButton called for source:', selectedDataSource); // DEBUG LOG
    
    const startBtn = document.getElementById('startAnalysisBtn');
    if (!startBtn) {
        console.log('startAnalysisBtn element not found!'); // DEBUG LOG
        return;
    }
    
    let isValid = false;
    
    switch(selectedDataSource) {
        case 'file':
            isValid = true;
            console.log('File source - always valid'); // DEBUG LOG
            break;
        case 'upload':
            const selectedFile = document.querySelector('input[name="logFile"]:checked');
            isValid = selectedFile !== null;
            console.log('Upload source - selected file:', selectedFile?.value, 'isValid:', isValid); // DEBUG LOG
            break;
        case 'mongodb_direct':
            const connString = document.getElementById('mongoConnectionString').value;
            isValid = connString && connString.trim().length > 0;
            console.log('MongoDB direct source - connection string length:', connString?.length, 'isValid:', isValid); // DEBUG LOG
            break;
        case 'test_servers':
            const selectedServer = document.getElementById('testServerSelect').value;
            isValid = selectedServer && selectedServer.length > 0;
            console.log('Test servers source - selected server:', selectedServer, 'isValid:', isValid); // DEBUG LOG
            break;
        case 'opensearch':
            // Single/Cluster mode kontrolü
            const hostMode = document.querySelector('input[name="hostSelectionMode"]:checked')?.value || 'single';
            
            if (hostMode === 'cluster') {
                // Cluster mode validation - CLUSTER DROPDOWN DESTEĞİ
                const selectedCluster = document.getElementById('clusterSelect')?.value;
                isValid = selectedCluster && selectedCluster.length > 0;
                console.log('OpenSearch cluster mode - selected cluster:', selectedCluster, 'isValid:', isValid);
            } else {
                // Single mode validation
                const selectedHost = document.getElementById('mongodbHostSelect')?.value;
                isValid = selectedHost && selectedHost.length > 0;
                console.log('OpenSearch single mode - selected host:', selectedHost, 'isValid:', isValid);
            }
            break;
        default:
            console.log('Unknown data source for validation:', selectedDataSource); // DEBUG LOG
    }
    
    startBtn.disabled = !isValid;
    console.log('Analysis button disabled:', !isValid); // DEBUG LOG
}

// handleAnalyzeLog - Taşındı: script-anomaly.js (satır 732-1041)
// Alias için bkz: satır 916
// closeAnomalyModal - Taşındı: script-anomaly.js (satır 1040-1063)

// displayAnomalyResults - Taşındı: script-anomaly.js (satır 1063-1387)
/**
 * Upload edilmiş dosyaları listele ve güncelle
 */
async function updateUploadedFilesList() {
    console.log('updateUploadedFilesList called'); // DEBUG LOG
    
    // Mevcut seçimi sakla
    const currentSelection = document.querySelector('input[name="logFile"]:checked')?.value;
    
    try {
        console.log('Fetching uploaded files from API...'); // DEBUG LOG
        const response = await fetch(`${API_ENDPOINTS.uploadedLogs}?api_key=${apiKey}`);
        const data = await response.json();
        
        console.log('Uploaded files response:', data); // DEBUG LOG
        
        const fileList = document.getElementById('modalFilesList');
        if (!fileList) {
            console.log('modalFilesList element not found!'); // DEBUG LOG
            return;
        }
        
        fileList.innerHTML = '';
        
        if (data.logs && data.logs.length > 0) {
            console.log('Found', data.logs.length, 'uploaded files'); // DEBUG LOG
            data.logs.forEach(log => {
                console.log('Processing file:', log.filename, 'path:', log.path); // DEBUG LOG
                const fileItem = document.createElement('div');
                fileItem.className = 'file-item';
                fileItem.innerHTML = `
                    <input type="radio" name="logFile" value="${log.path}" id="file_${log.filename}">
                    <label for="file_${log.filename}">
                        <span class="file-name">${log.filename}</span>
                        <span class="file-size">${log.size_mb} MB</span>
                    </label>
                    <button class="delete-file-btn" onclick="deleteUploadedFile('${log.filename}')">🗑️</button>
                `;
                fileList.appendChild(fileItem);
            });
            
            // Seçimi geri yükle
            if (currentSelection) {
                const radio = document.querySelector(`input[name="logFile"][value="${currentSelection}"]`);
                if (radio) {
                    radio.checked = true;
                    // Upload source ise validation'ı tetikle
                    if (selectedDataSource === 'upload') {
                        validateAnalysisButton();
                    }
                } else if (selectedDataSource === 'upload' && data.logs.length > 0) {
                    // İlk açılışta ve dosya varsa, ilk dosyayı otomatik seç
                    const firstRadio = document.querySelector('input[name="logFile"]');
                    if (firstRadio) {
                        firstRadio.checked = true;
                        console.log('Auto-selected first file:', firstRadio.value);
                        validateAnalysisButton();
                    }
                }
            } else if (selectedDataSource === 'upload' && data.logs.length > 0) {
                // İlk açılışta ve dosya varsa, ilk dosyayı otomatik seç
                const firstRadio = document.querySelector('input[name="logFile"]');
                if (firstRadio) {
                    firstRadio.checked = true;
                    console.log('Auto-selected first file:', firstRadio.value);
                    validateAnalysisButton();
                }
            }
        } else {
            console.log('No uploaded files found'); // DEBUG LOG
            fileList.innerHTML = '<p class="no-files">Henüz dosya yüklenmemiş</p>';
        }
    } catch (error) {
        console.error('Error updating uploaded files list:', error); // DEBUG LOG
        console.error('Dosya listesi alınamadı:', error);
    }
}

/**
 * Dosya boyutunu formatla
 */
function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k =  1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
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
var updateHistoryDisplayWithDBA = window.updateHistoryDisplayWithDBA;
var loadHistoricalDBAAnalysis = window.loadHistoricalDBAAnalysis;
var showHistoryDetail = window.showHistoryDetail;
var replayQuery = window.replayQuery;
var clearHistory = window.clearHistory;
var checkStorageSize = window.checkStorageSize;
var exportHistory = window.exportHistory;
// handleFileUpload fonksiyonu için bkz: satır 3791 (file upload handler)

/**
 * Geçmişe yeni sorgu ekle
 */
async function addToHistory(query, result, type = 'chatbot') {
    // Kategori doğrulaması yap
    if (type === 'anomaly') {
        console.log('Adding ANOMALY query to history:', query);
    } else {
        console.log('Adding CHATBOT query to history:', query);
    }
    
    const historyItem = {
        id: Date.now(),
        timestamp: new Date().toISOString(),
        query: query,
        type: type,
        category: type,
        result: result,
        durum: result.durum,
        işlem: result.işlem,
        
        // Ekstra metadata
        executionTime: result.executionTime || null,
        mlData: result.sonuç?.data || null,
        aiExplanation: result.sonuç?.ai_explanation || result.ai_explanation || null,
        hasVisualization: !!(result.sonuç?.data?.summary || result.sonuç?.data?.component_analysis),
        hasResult: !!result.sonuç,
        
        // Browser metadata
        user_agent: navigator.userAgent,
        screen_resolution: `${window.screen.width}x${window.screen.height}`,
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
        
        // Session tracking
        session_id: currentSessionId,
        page_load_time: window.performance?.timing?.loadEventEnd - window.performance?.timing?.navigationStart,
        
        // Anomaly tracking
        isAnomalyQuery: type === 'anomaly' || result.işlem === 'anomaly_analysis',
        anomalyCount: result.sonuç?.critical_anomalies?.length || 0
    };
    
    // En başa ekle
    queryHistory.unshift(historyItem);
    
    // Maksimum sayıyı kontrol et
    if (queryHistory.length > MAX_HISTORY_ITEMS) {
        queryHistory = queryHistory.slice(0, MAX_HISTORY_ITEMS);
    }
    
    // MongoDB'ye kaydet
    await saveHistory();
    
    // Görüntüyü güncelle
    updateHistoryDisplay();
    
    // Storage boyutu kontrolü
    checkStorageSize();
    
    console.log('✅ History item added with full metadata');
}
/**
 * Geçmişi MongoDB'ye kaydet
 */
async function saveHistory(retryCount = 0) {
    const MAX_RETRIES = 3;
    const RETRY_DELAY = 1000; // 1 saniye
    
    try {
        // Session ID kontrolü
        if (!window.currentSessionId) {
            window.currentSessionId = `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
        }
        
        if (isConnected && apiKey && queryHistory.length > 0) {
            const lastItem = queryHistory[0];
            
            // Zaten MongoDB'den geldiyse kaydetme
            if (lastItem.fromMongoDB) {
                return true;
            }
            
            // Kayıt öncesi veriyi validate et
            if (!lastItem.query || !lastItem.timestamp) {
                console.warn('Invalid history item, skipping save:', lastItem);
                return false;
            }
            
            const response = await fetch('/api/query-history/save', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    ...lastItem,
                    api_key: apiKey,
                    session_id: window.currentSessionId,
                    save_timestamp: new Date().toISOString() // Kayıt zamanı
                })
            });
            
            if (response.ok) {
                const result = await response.json();
                
                // MongoDB ID'yi kaydet
                lastItem.id = result.query_id;
                lastItem.fromMongoDB = true;
                lastItem.mongoSaveTime = new Date().toISOString();
                
                console.log('✅ Saved to MongoDB:', result.query_id);
                
                // Başarılı kayıt sonrası verify et
                await verifyMongoDBSave(result.query_id);
                
                return true;
            } else {
                throw new Error(`Save failed: ${response.status}`);
            }
        }
        
        return false;
        
    } catch (e) {
        console.error(`MongoDB save error (attempt ${retryCount + 1}/${MAX_RETRIES}):`, e);
        
        // Retry logic
        if (retryCount < MAX_RETRIES - 1) {
            console.log(`Retrying save in ${RETRY_DELAY}ms...`);
            await new Promise(resolve => setTimeout(resolve, RETRY_DELAY));
            return saveHistory(retryCount + 1);
        }
        
        // Son deneme de başarısız olduysa kullanıcıyı bilgilendir
        showNotification('Veri MongoDB\'ye kaydedilemedi. Bağlantıyı kontrol edin.', 'error');
        return false;
    }
}

/**
 * MongoDB'ye kaydın başarılı olduğunu doğrula
 */
async function verifyMongoDBSave(queryId) {
    try {
        // Kısa bir gecikme
        await new Promise(resolve => setTimeout(resolve, 500));
        
        // MongoDB'den kaydı kontrol et
        const response = await fetch(`/api/query-history/verify/${queryId}?api_key=${apiKey}`);
        
        if (response.ok) {
            const data = await response.json();
            if (data.exists) {
                console.log('✅ MongoDB save verified:', queryId);
                return true;
            }
        }
        
        console.warn('⚠️ MongoDB save could not be verified:', queryId);
        return false;
        
    } catch (error) {
        console.error('Verification error:', error);
        return false;
    }
}

/**
 * Kayıtlı olmayan history item'ları bul ve kaydet
 */
async function syncUnsavedHistoryItems() {
    if (!isConnected || !apiKey) return;
    
    console.log('🔄 Syncing unsaved history items to MongoDB...');
    
    const unsavedItems = queryHistory.filter(item => !item.fromMongoDB);
    
    if (unsavedItems.length === 0) {
        console.log('✅ All items already saved to MongoDB');
        return;
    }
    
    console.log(`Found ${unsavedItems.length} unsaved items`);
    
    let savedCount = 0;
    for (const item of unsavedItems) {
        try {
            const response = await fetch('/api/query-history/save', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    ...item,
                    api_key: apiKey,
                    session_id: window.currentSessionId
                })
            });
            
            if (response.ok) {
                const result = await response.json();
                item.id = result.query_id;
                item.fromMongoDB = true;
                savedCount++;
                console.log(`✅ Synced item ${savedCount}/${unsavedItems.length}:`, result.query_id);
            }
            
        } catch (error) {
            console.error('Failed to sync item:', error);
        }
        
        // Rate limiting - her kayıt arası 100ms bekle
        await new Promise(resolve => setTimeout(resolve, 100));
    }
    
    console.log(`✅ Sync complete: ${savedCount}/${unsavedItems.length} items saved`);
    
    if (savedCount > 0) {
        showNotification(`${savedCount} kayıt MongoDB\'ye senkronize edildi`, 'success');
    }
}

// Sayfa yüklendiğinde veya bağlantı kurulduğunda sync'i çalıştır
window.addEventListener('load', () => {
    setTimeout(() => {
        if (isConnected) {
            syncUnsavedHistoryItems();
        }
    }, 5000); // 5 saniye sonra sync
});


/**
 * Geçmiş görüntüsünü güncelle - MongoDB desteği ile
 */
function updateHistoryDisplay(filter = 'all') {
    const historyContent = document.getElementById('historyContent');
    if (!historyContent) return;
    
    // MongoDB'den gelen veri sayısını göster
    console.log(`📊 Updating history display - Total items: ${queryHistory.length}`);
    console.log(`   Filter: ${filter}`);
    console.log(`   MongoDB items: ${queryHistory.filter(h => h.fromMongoDB).length}`);
    console.log(`   Anomaly items: ${queryHistory.filter(h => h.type === 'anomaly').length}`);
    console.log(`   Chatbot items: ${queryHistory.filter(h => h.type === 'chatbot').length}`);
    
    // Filtreleme - DÜZELTME BURADA
    let filteredHistory = [];
    
    if (filter === 'all') {
        filteredHistory = queryHistory;
    } 
    else if (filter === 'chatbot') {
        filteredHistory = queryHistory.filter(item => {
            // Sadece chatbot type ve anomaly category'si OLMAYANLAR
            return item.type === 'chatbot' && 
                   item.category !== 'anomaly' && 
                   item.subType !== 'DBA';
        });
    } 
    else if (filter === 'anomaly') {
        filteredHistory = queryHistory.filter(item => {
            // Anomaly veya DBA olan her şey
            return item.type === 'anomaly' || 
                   item.category === 'anomaly' ||
                   item.subType === 'DBA' ||
                   item.isAnomalyParent === true;
        });
    }
    
    console.log(`   Filtered items: ${filteredHistory.length}`);
    
    // MongoDB sync durumunu göster
    const unsyncedCount = queryHistory.filter(h => !h.fromMongoDB).length;
    if (unsyncedCount > 0) {
        console.warn(`⚠️ ${unsyncedCount} items not synced to MongoDB`);
    }
    
    if (filteredHistory.length === 0) {
        historyContent.innerHTML = `
            <div class="history-empty">
                <p>Bu kategoride geçmiş bulunmuyor.</p>
                <small>${isConnected ? 'MongoDB\'den veri yükleniyor...' : 'MongoDB bağlantısı bekleniyor...'}</small>
                ${isConnected ? '<button class="btn-small" onclick="reloadAllHistory()">🔄 Yeniden Yükle</button>' : ''}
            </div>
        `;
        return;
    }
    
    let html = '<div class="history-list">';
    
    // MongoDB sync durumu göstergesi
    if (isConnected) {
        const syncedCount = filteredHistory.filter(h => h.fromMongoDB).length;
        const totalCount = filteredHistory.length;
        const syncPercentage = totalCount > 0 ? ((syncedCount / totalCount) * 100).toFixed(0) : 0;
        
        html += `
            <div class="mongodb-sync-status">
                <span class="sync-indicator ${syncPercentage == 100 ? 'synced' : 'partial'}">
                    💾 MongoDB Sync: ${syncedCount}/${totalCount} (${syncPercentage}%)
                </span>
                ${unsyncedCount > 0 ? `
                    <button class="btn-sync" onclick="syncUnsavedHistoryItems()">
                        🔄 Sync Now
                    </button>
                ` : ''}
            </div>
        `;
    }
    
    // History item'ları göster
    filteredHistory.forEach(item => {
        const date = new Date(item.timestamp);
        const typeIcon = item.subType === 'DBA' ? '🕐' : 
                        item.type === 'anomaly' ? '🔍' : 
                        item.type === 'chat-anomaly' ? '🤖' : '💬';
        
        // MongoDB durumu
        const mongoIcon = item.fromMongoDB ? '✅' : '⏳';
        const mongoTitle = item.fromMongoDB ? 'MongoDB\'de kayıtlı' : 'MongoDB\'ye kaydedilecek';
        
        // Durum kontrolü
        const statusClass = item.durum === 'tamamlandı' ? 'completed' :
                           item.durum === 'başarılı' ? 'success' : 
                           item.durum === 'hata' ? 'error' :
                           item.durum === 'onay_bekliyor' ? 'pending' : 
                           item.durum === 'iptal' ? 'cancelled' : 'warning';
        
        const statusIcon = item.durum === 'tamamlandı' ? '✅' :
                          item.durum === 'onay_bekliyor' ? '⏳' :
                          item.durum === 'başarılı' ? '✔️' :
                          item.durum === 'iptal' ? '❌' : '⚠️';
        
        const itemClass = item.isAnomalyParent ? 'history-item anomaly-parent' : 'history-item';
        const resultIndicator = item.hasResult && item.childResult ? 
            '<span class="result-indicator">✅ Analiz Tamamlandı</span>' : 
            item.awaitingConfirmation && item.durum === 'onay_bekliyor' ? 
            '<span class="result-indicator pending animated">⏳ Onay Bekliyor</span>' : 
            item.durum === 'iptal' ?
            '<span class="result-indicator cancelled">❌ İptal Edildi</span>' : '';
        
        html += `
            <div class="${itemClass}" data-id="${item.id}" data-has-result="${item.hasResult || false}" data-from-mongodb="${item.fromMongoDB}">
                <div class="history-item-header">
                    <span class="history-type">${typeIcon}</span>
                    <span class="history-time">${date.toLocaleString('tr-TR')}</span>
                    <span class="mongodb-status" title="${mongoTitle}">${mongoIcon}</span>
                    ${resultIndicator}
                    <span class="history-status ${statusClass}">${statusIcon} ${item.durum}</span>
                    ${item.executionTime ? `<span class="execution-time">⏱️ ${(item.executionTime/1000).toFixed(1)}s</span>` : ''}
                </div>
                <div class="history-query">${escapeHtml(item.query)}</div>
                ${item.id ? `<div class="history-id">ID: ${item.id}</div>` : ''}
                <div class="history-actions">
                    ${!item.parentId ? `
                        <button class="btn-small" onclick="window.replayQuery('${item.id.replace(/'/g, "\\'")}')" >
                            🔄 Tekrar Çalıştır
                        </button>
                    ` : ''}
                    <button class="btn-small" onclick="window.showHistoryDetail('${item.id}')">
                        ${item.hasResult && item.childResult ? '📊 Sonuçları Göster' : '👁️ Detay'}
                    </button>
                    ${!item.fromMongoDB ? `
                        <button class="btn-small" onclick="syncSingleItem('${item.id}')">
                            💾 MongoDB'ye Kaydet
                        </button>
                    ` : ''}
                </div>
            </div>
        `;
    });
    
    html += '</div>';
    historyContent.innerHTML = html;
}

/**
 * Tüm history'yi MongoDB'den yeniden yükle
 */
async function reloadAllHistory() {
    console.log('🔄 Reloading all history from MongoDB...');
    showLoader(true);
    
    try {
        // Önce mevcut history'yi temizle
        queryHistory = [];
        
        // MongoDB'den tüm verileri yükle
        await Promise.all([
            loadHistory(),
            loadAnomalyHistoryFromMongoDB({limit: 100}),
            loadAndMergeDBAHistory()
        ]);
        
        console.log(`✅ Reloaded ${queryHistory.length} items from MongoDB`);
        showNotification('Tüm veriler MongoDB\'den yeniden yüklendi', 'success');
        
        // UI'ı güncelle
        updateHistoryDisplay();
        
    } catch (error) {
        console.error('Reload error:', error);
        showNotification('Veriler yüklenirken hata oluştu', 'error');
    } finally {
        showLoader(false);
    }
}

/**
 * Tek bir item'ı MongoDB'ye kaydet
 */
async function syncSingleItem(itemId) {
    const item = queryHistory.find(h => h.id === itemId);
    if (!item || item.fromMongoDB) return;
    
    try {
        const response = await fetch('/api/query-history/save', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                ...item,
                api_key: apiKey,
                session_id: window.currentSessionId
            })
        });
        
        if (response.ok) {
            const result = await response.json();
            item.id = result.query_id;
            item.fromMongoDB = true;
            
            console.log(`✅ Item synced to MongoDB: ${result.query_id}`);
            showNotification('MongoDB\'ye kaydedildi', 'success');
            
            // UI'ı güncelle
            updateHistoryDisplay();
        }
    } catch (error) {
        console.error('Sync error:', error);
        showNotification('Kayıt başarısız', 'error');
    }
}

// ========== DBA HISTORY ENTEGRASYONU ==========

/**
 * MongoDB'den DBA analizlerini çek ve history'e ekle
 */
async function loadAndMergeDBAHistory() {
    try {
        // MongoDB'den DBA analizlerini çek
        const response = await fetch(`/api/dba/analysis-history?limit=20&days_back=30&api_key=${apiKey}`);
        const data = await response.json();
        
        if (data.status === 'success' && data.analyses && data.analyses.length > 0) {
            console.log(`Loaded ${data.analyses.length} DBA analyses from MongoDB`);
            
            // Her DBA analizini history formatına çevir
            data.analyses.forEach(analysis => {
                // Zaten history'de var mı kontrol et (storage_id ile)
                const exists = queryHistory.find(h => h.storage_id === analysis._id);
                if (!exists) {
                    // History item formatına çevir
                    const historyItem = {
                        id: Date.now() + Math.random(), // Unique ID
                        timestamp: analysis.timestamp,
                        query: `DBA Analizi: ${analysis.host} - ${analysis.time_range || 'Custom time range'}`,
                        type: 'anomaly',
                        category: 'anomaly',
                        subType: 'DBA', // DBA olduğunu belirtmek için
                        storage_id: analysis._id,
                        result: {
                            durum: 'tamamlandı',
                            işlem: 'dba_analysis'
                        },
                        // DBA spesifik veriler
                        dbaData: {
                            host: analysis.host,
                            anomaly_count: analysis.anomaly_count,
                            total_logs: analysis.total_logs,
                            anomaly_rate: analysis.anomaly_rate,
                            time_range: analysis.time_range,
                            has_ai_explanation: analysis.has_ai_explanation
                        },
                        hasVisualization: true,
                        fromMongoDB: true // MongoDB'den geldiğini işaretle
                    };
                    
                    // History'e ekle
                    queryHistory.unshift(historyItem);
                }
            });
            
            // Tarihe göre sırala
            queryHistory.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
            
            // Fazla kayıtları temizle
            if (queryHistory.length > MAX_HISTORY_ITEMS) {
                queryHistory = queryHistory.slice(0, MAX_HISTORY_ITEMS);
            }
            
            // LocalStorage'a kaydet
            saveHistory();
            
            // Display'i güncelle
            updateHistoryDisplayWithDBA();
        }
    } catch (error) {
        console.error('Failed to load DBA history from MongoDB:', error);
    }
}

/**
 * History display'i DBA desteğiyle güncelle
 */
function updateHistoryDisplayWithDBA(filter = 'all') {
    const historyContent = document.getElementById('historyContent');
    if (!historyContent) return;
    
    // Filtreleme
    let filteredHistory = queryHistory;
    if (filter === 'anomaly') {
        filteredHistory = queryHistory.filter(item => 
            item.type === 'anomaly' || 
            item.category === 'anomaly' ||
            item.isAnomalyParent === true
        );
    } else if (filter === 'chatbot') {
        filteredHistory = queryHistory.filter(item => 
            item.type === 'chatbot' && item.subType !== 'DBA'
        );
    }
    
    if (filteredHistory.length === 0) {
        historyContent.innerHTML = `
            <div class="history-empty">
                <p>Bu kategoride geçmiş bulunmuyor.</p>
                <small>Yaptığınız sorgular burada görüntülenecek.</small>
            </div>
        `;
        return;
    }
    
    let html = '<div class="history-list">';
    
    filteredHistory.forEach(item => {
        const date = new Date(item.timestamp);
        
        // DBA için özel ikon ve renk
        const typeIcon = item.subType === 'DBA' ? '🕐' : 
                        item.type === 'anomaly' ? '🔍' : 
                        item.type === 'chat-anomaly' ? '🤖' : '💬';
        
        const borderColor = item.subType === 'DBA' ? '#0047BA' : '#e67e22';
        
        const statusClass = item.durum === 'tamamlandı' ? 'completed' :
                           item.durum === 'başarılı' ? 'success' : 
                           item.durum === 'hata' ? 'error' : 'warning';
        
        const statusIcon = item.durum === 'tamamlandı' ? '✅' :
                          item.durum === 'başarılı' ? '✔️' : '⚠️';
        
        html += `
            <div class="history-item ${item.subType === 'DBA' ? 'dba-item' : ''}" 
                 data-id="${item.id}" 
                 style="border-left: 4px solid ${borderColor};">
                <div class="history-item-header">
                    <span class="history-type">${typeIcon}</span>
                    ${item.subType === 'DBA' ? '<span class="dba-badge" style="background: #0047BA; color: white; padding: 2px 6px; border-radius: 3px; font-size: 11px;">DBA</span>' : ''}
                    <span class="history-time">${date.toLocaleString('tr-TR')}</span>
                    ${item.fromMongoDB ? '<span class="mongodb-indicator" title="MongoDB\'den yüklendi">💾</span>' : ''}
                    <span class="history-status ${statusClass}">${statusIcon} ${item.durum}</span>
                </div>
                <div class="history-query">${escapeHtml(item.query)}</div>
                ${item.dbaData ? `
                    <div class="dba-summary" style="margin-top: 5px; font-size: 12px; color: #666;">
                        📊 ${item.dbaData.anomaly_count} anomali | 
                        📄 ${(item.dbaData.total_logs || 0).toLocaleString('tr-TR')} log | 
                        📈 %${(item.dbaData.anomaly_rate || 0).toFixed(2)}
                    </div>
                ` : ''}
                <div class="history-actions">
                    ${item.subType === 'DBA' && item.storage_id ? `
                        <button class="btn-small" onclick="loadHistoricalDBAAnalysis('${item.storage_id}')">
                            📊 Sonuçları Göster
                        </button>
                    ` : `
                        <button class="btn-small" onclick="showHistoryDetail(${item.id})">
                            👁️ Detay
                        </button>
                    `}
                    ${!item.fromMongoDB ? `
                        <button class="btn-small" onclick="replayQuery(${item.id})">
                            🔄 Tekrar
                        </button>
                    ` : ''}
                </div>
            </div>
        `;
    });
    
    html += '</div>';
    historyContent.innerHTML = html;
}

/**
 * Geçmişten DBA analizini yükle ve göster
 */
async function loadHistoricalDBAAnalysis(analysisId) {
    try {
        showLoader(true);
        
        const response = await fetch(`/api/dba/analysis/${analysisId}?api_key=${apiKey}`);
        const data = await response.json();
        
        if (data.status === 'success' && data.analysis) {
            const analysis = data.analysis;
            const result = analysis.analysis_result || {};
            const sonuc = result.sonuç || {};
            
            // DBA sonuçlarını formatla
            const formattedResult = {
                status: 'success',
                results: {
                    critical_anomalies: sonuc.critical_anomalies || [],
                    total_logs_analyzed: sonuc.total_logs || 0,
                    anomaly_count: sonuc.anomaly_count || 0,
                    anomaly_rate: sonuc.anomaly_rate || 0,
                    ai_summary: result.ai_explanation
                },
                host: analysis.host,
                time_range: analysis.time_range,
                storage_id: analysisId
            };
            
            // Pagination'ı resetle
            window.dbaCurrentPage = 1;
            
            // Sonuçları görüntüle
            displayDBAAnalysisResults(
                formattedResult,
                analysis.host || 'Unknown',
                analysis.time_range ? analysis.time_range.split(' to ')[0] : '',
                analysis.time_range ? analysis.time_range.split(' to ')[1] : ''
            );
            
            showNotification('DBA analizi yüklendi', 'success');
        }
    } catch (error) {
        console.error('Failed to load DBA analysis:', error);
        showNotification('DBA analizi yüklenemedi', 'error');
    } finally {
        showLoader(false);
    }
}

// Sayfa yüklendiğinde ve API bağlandığında DBA geçmişini yükle
document.addEventListener('DOMContentLoaded', function() {
    // Mevcut tab event listener'larına ek olarak
    const originalUpdateDisplay = updateHistoryDisplay;
    
    // updateHistoryDisplay'i override et
    window.updateHistoryDisplay = function(filter = 'all') {
        // Önce DBA history'i yükle
        if (apiKey) {
            loadAndMergeDBAHistory().then(() => {
                updateHistoryDisplayWithDBA(filter);
            });
        } else {
            originalUpdateDisplay(filter);
        }
    };
});

// API bağlandığında otomatik yükle
window.addEventListener('apiConnected', function() {
    loadAndMergeDBAHistory();
});

// Global fonksiyonları tanımla
window.loadHistoricalDBAAnalysis = loadHistoricalDBAAnalysis;
window.loadAndMergeDBAHistory = loadAndMergeDBAHistory;

/**
 * Geçmiş detayını göster
 */
function showHistoryDetail(id) {
    console.log('=== showHistoryDetail DEBUG ===');
    console.log('Looking for item with ID:', id);
    
    const item = queryHistory.find(h => h.id === id);
    if (!item) {
        console.error('Item not found in history!');
        return;
    }
    
    console.log('Item found:', item);
    console.log('Item type:', item.type);
    console.log('Has childResult:', !!item.childResult);
    console.log('childResult:', item.childResult);
    
    // History item elementini bul
    const historyItemElement = document.querySelector(`.history-item[data-id="${id}"]`);
    if (!historyItemElement) return;
    
    // Zaten açık mı kontrol et
    const existingDetail = historyItemElement.querySelector('.inline-detail');
    if (existingDetail) {
        // Varsa toggle yap
        existingDetail.remove();
        return;
    }
    
    // İnline detay container'ı oluştur
    const detailContainer = document.createElement('div');
    detailContainer.className = 'inline-detail';
    
    let content = '<div class="history-detail-content">';
    
    // Tarih ve durum bilgileri
    content += '<div class="detail-meta">';
    content += `<p><strong>Tarih:</strong> ${new Date(item.timestamp).toLocaleString('tr-TR')}</p>`;
    
    if (item.completedAt) {
        content += `<p><strong>Tamamlanma:</strong> ${new Date(item.completedAt).toLocaleString('tr-TR')}</p>`;
    }
    
    const statusBadge = item.durum === 'tamamlandı' ? 
        '<span class="status-badge completed">✅ Tamamlandı</span>' :
        item.durum === 'onay_bekliyor' ? 
        '<span class="status-badge pending">⏳ Onay Bekliyor</span>' :
        item.durum === 'başarılı' ?
        '<span class="status-badge success">✔️ Başarılı</span>' :
        item.durum === 'iptal' ?
        '<span class="status-badge cancelled">❌ İptal Edildi</span>' :
        `<span class="status-badge">${item.durum}</span>`;
    
    content += `<p><strong>Durum:</strong> ${statusBadge}</p>`;
    
    if (item.executionTime) {
        content += `<p><strong>Çalışma Süresi:</strong> ${(item.executionTime/1000).toFixed(1)} saniye</p>`;
    }
    content += '</div>';
    
    // ÖNEMLİ: Eğer anomali analiziyse ve childResult varsa, direkt AI sonuçlarını göster
    if (item.type === 'anomaly' && item.childResult) {
        console.log('Showing anomaly child result inline:', item.childResult);
        
        // ML DATA KONTROLÜ VE GÖRSELLEŞTİRME
        const mlData = item.childResult.sonuç?.data || item.childResult.sonuç || {};
        const hasMlData = mlData.summary || mlData.component_analysis || mlData.temporal_analysis || mlData.feature_importance;

        if (hasMlData) {
            content += '<div class="ml-visualizations-inline">';
            content += '<h4>📊 ML Analiz Sonuçları</h4>';
            
            // TAM GÖRSELLEŞTİRMELERİ RENDER ET
            // 1. ML Model Metrikleri
            if (mlData.summary || mlData.anomaly_score_stats) {
                content += renderMLModelMetrics(mlData.summary || {}, mlData.anomaly_score_stats || {});
            }
            
            
            // 4. Temporal Heatmap
            if (mlData.temporal_analysis?.hourly_distribution) {
                content += renderTemporalHeatmap(mlData.temporal_analysis);
            }
            
            
            // Export ve diğer aksiyonlar
            content += `<div class="visualization-actions">
                <button class="btn btn-primary" onclick="showFullVisualizationModal(${id})">
                    🖼️ Modal'da Göster
                </button>
                <button class="btn btn-secondary" onclick="exportAnomalyData(${id})">
                    📥 Veriyi İndir
                </button>
            </div>`;
            
            content += '</div>';
        }
        
        // AI DESTEKLİ AÇIKLAMA GEÇMİŞ DETAYINDA DEVRE DIŞI - COMMENT OUT EDİLDİ
        
        // AI explanation yoksa ama açıklama varsa, text format kullan - BU KISIM KALACAK
        // else if yerine direkt if olmalı çünkü üstteki blok comment out edildi
        if (item.childResult.açıklama && !item.childResult.açıklama.includes('AI DESTEKLİ')) {
            content += '<div class="anomaly-text-result">';
            content += '<h4>🔍 Anomali Analiz Sonuçları</h4>';
            content += '<div class="formatted-anomaly-text">';
            
            // Text'i formatla - backend'den gelen markdown benzeri formatı HTML'e çevir
            const formattedText = item.childResult.açıklama
                .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')  // Bold text
                .replace(/### (.*?)$/gm, '<h5>$1</h5>')            // H3 headers
                .replace(/## (.*?)$/gm, '<h4>$1</h4>')             // H2 headers
                .replace(/# (.*?)$/gm, '<h3>$1</h3>')              // H1 headers
                .replace(/^\* (.*?)$/gm, '• $1')                   // Bullet points
                .replace(/^- (.*?)$/gm, '• $1')                    // Dash lists
                .replace(/^\d+\. (.*?)$/gm, '<li>$1</li>')         // Numbered lists
                .replace(/\n\n/g, '</p><p>')                        // Paragraphs
                .replace(/\n/g, '<br>');                            // Line breaks
            
            content += `<p>${formattedText}</p>`;
            content += '</div>';
            content += '</div>';
        }
        
        // Özet istatistikler
        if (item.childResult.sonuç?.summary) {
            const summary = item.childResult.sonuç.summary;
            content += '<div class="anomaly-stats-summary">';
            content += '<h5>📊 İstatistikler</h5>';
            content += '<div class="stats-grid">';
            content += `<div class="stat-item">
                            <span class="stat-label">Toplam Log:</span>
                            <span class="stat-value">${summary.total_logs.toLocaleString('tr-TR')}</span>
                        </div>`;
            content += `<div class="stat-item">
                            <span class="stat-label">Anomali Sayısı:</span>
                            <span class="stat-value">${summary.n_anomalies}</span>
                        </div>`;
            content += `<div class="stat-item">
                            <span class="stat-label">Anomali Oranı:</span>
                            <span class="stat-value">%${summary.anomaly_rate.toFixed(1)}</span>
                        </div>`;
            content += '</div></div>';
        }

        // Critical Anomalies Listesi
        if (item.childResult.sonuç?.critical_anomalies && item.childResult.sonuç.critical_anomalies.length > 0) {
            content += '<div class="history-critical-anomalies">';
            content += '<h5>🚨 Kritik Anomaliler (İlk 10)</h5>';
            content += '<div class="history-anomaly-list">';
            
            item.childResult.sonuç.critical_anomalies.slice(0, 10).forEach((anomaly, index) => {
                const severityScore = anomaly.severity_score || 0;
                const severityLevel = anomaly.severity_level || 'MEDIUM';
                const severityColor = anomaly.severity_color || '#e67e22';
                
                content += `
                    <div class="history-anomaly-item">
                        <div class="anomaly-header">
                            <span class="anomaly-rank">#${index + 1}</span>
                            <span class="anomaly-timestamp">${new Date(anomaly.timestamp).toLocaleString('tr-TR')}</span>
                            <span class="anomaly-score-badge" style="color: ${severityColor}">
                                Score: ${anomaly.anomaly_score?.toFixed(3) || 'N/A'}
                            </span>
                        </div>
                        <div class="anomaly-body">
                            <div class="anomaly-message">
                                <strong>Log:</strong>
                                ${anomaly.message && anomaly.message.length > 500 ? `
                                    <div class="message-expandable">
                                        <div class="message-preview">
                                            <pre>${escapeHtml(anomaly.message.substring(0, 500))}...</pre>
                                        </div>
                                        <div class="message-full" style="display:none;">
                                            <pre>${escapeHtml(anomaly.message)}</pre>
                                        </div>
                                        <button class="btn-expand-message" onclick="toggleHistoryMessage(this)">Tam Mesajı Göster</button>
                                    </div>
                                ` : `
                                    <pre class="message-short">${escapeHtml(anomaly.message || '')}</pre>
                                `}
                            </div>
                            ${anomaly.component ? `
                                <div class="anomaly-component">
                                    <strong>Component:</strong> ${escapeHtml(anomaly.component)}
                                </div>
                            ` : ''}
                            ${anomaly.severity_factors && anomaly.severity_factors.length > 0 ? `
                                <div class="anomaly-factors">
                                    <strong>Faktörler:</strong>
                                    ${anomaly.severity_factors.map(f => `<span class="factor-chip">${f}</span>`).join('')}
                                </div>
                            ` : ''}
                        </div>
                    </div>
                `;
            });
            
            if (item.childResult.sonuç.critical_anomalies.length > 10) {
                content += `<p class="more-anomalies">... ve ${item.childResult.sonuç.critical_anomalies.length - 10} anomali daha</p>`;
            }
            
            content += '</div></div>';
        }
    }
    // Normal sorgu sonucu
    else if (item.result.açıklama) {
        content += '<div class="normal-result">';
        content += '<h5>📝 Sonuç:</h5>';
        content += parseAndFormatDescription(item.result.açıklama);
        content += '</div>';
    }
    
    content += '</div>';
    detailContainer.innerHTML = content;
    historyItemElement.appendChild(detailContainer);
    
    // Animasyon için
    setTimeout(() => {
        detailContainer.classList.add('show');
        
        // SHOW CLASS'I EKLENDİKTEN SONRA ÖLÇÜM YAP
        setTimeout(() => {
            console.log('=== Container Measurements After Show ===');
            console.log('Detail container scrollHeight:', detailContainer.scrollHeight);
            console.log('Detail container clientHeight:', detailContainer.clientHeight);
            console.log('Detail container offsetHeight:', detailContainer.offsetHeight);
            console.log('Content length:', content.length);
            console.log('Container max-height style:', window.getComputedStyle(detailContainer).maxHeight);
            console.log('Container overflow-y style:', window.getComputedStyle(detailContainer).overflowY);
            
            // CONTAINER YÜKSEKLİK DÜZELTMESİ
            const realHeight = detailContainer.scrollHeight;
            const viewportHeight = window.innerHeight;
            
            // Eğer içerik görünür alanı aşıyorsa
            if (realHeight > detailContainer.clientHeight) {
                console.log('Content overflows! Applying fixes...');
                
                // Max height'ı viewport'un %80'ine ayarla
                detailContainer.style.maxHeight = `${viewportHeight * 0.8}px`;
                detailContainer.style.overflowY = 'auto';
                detailContainer.style.overflowX = 'hidden';
                
                // Scroll pozisyonunu en üste getir
                detailContainer.scrollTop = 0;
            }
            
            // PARENT CONTAINER OVERFLOW KONTROLÜ
            let parent = detailContainer.parentElement;
            while (parent && parent !== document.body) {
                const computedStyle = window.getComputedStyle(parent);
                if (computedStyle.overflow === 'hidden' || computedStyle.overflowY === 'hidden') {
                    console.warn('Parent has overflow:hidden, fixing:', parent.className);
                    parent.style.overflow = 'visible';
                }
                parent = parent.parentElement;
            }
            
        }, 100); // Show animasyonu tamamlandıktan sonra
        
    }, 10);

    // ML visualization event listener'ları ekle
    const mlData = item.childResult?.sonuç?.data || item.childResult?.sonuç || {};
    const hasMlDataCheck = mlData.summary || mlData.component_analysis || mlData.temporal_analysis || mlData.feature_importance;

    if (hasMlDataCheck) {
        setTimeout(() => {
            attachMLVisualizationListeners();
        }, 200); // Biraz daha gecikme ekledik
    }
}

/**
 * Sorguyu tekrar çalıştır
 */
function replayQuery(id) {
    const item = queryHistory.find(h => h.id === id);
    if (!item) return;
    
    elements.queryInput.value = item.query;
    elements.queryInput.focus();
    
    // Otomatik çalıştır
    if (confirm('Bu sorguyu tekrar çalıştırmak istiyor musunuz?')) {
        handleQuery();
    }
}

/**
 * Geçmişı temizle
 */
async function clearHistory() {
    if (confirm('Tüm sorgu geçmişini silmek istediğinizden emin misiniz?')) {
        try {
            // MongoDB'den temizle
            if (isConnected && apiKey) {
                const response = await fetch('/api/query-history/clear', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        api_key: apiKey,
                        session_id: currentSessionId
                    })
                });
                
                if (response.ok) {
                    const result = await response.json();
                    console.log(`✅ Cleared ${result.deleted_count} items from MongoDB`);
                }
            }
            
            // Local değişkeni temizle
            queryHistory = [];
            
            // localStorage TEMİZLEMESİ YOK
            
            updateHistoryDisplay();
            showNotification('Geçmiş temizlendi', 'success');
        } catch (e) {
            console.error('Geçmiş temizleme hatası:', e);
            showNotification('Geçmiş temizlenirken hata oluştu', 'error');
        }
    }
}

/**
 * Storage boyutunu kontrol et ve gerekirse temizlik yap
 */
async function checkStorageSize() {
    if (!isConnected || !apiKey) return;
    
    try {
        const response = await fetch(`/api/storage/check-size?api_key=${apiKey}`);
        
        if (response.ok) {
            const data = await response.json();
            
            if (data.is_over_limit) {
                console.warn(`⚠️ Storage limit exceeded: ${data.size_info.total_size_gb.toFixed(2)} GB`);
                
                if (data.deleted_count > 0) {
                    console.log(`🧹 Cleaned up ${data.deleted_count} old records`);
                    showNotification(`Disk alanı temizlendi: ${data.deleted_count} eski kayıt silindi`, 'info');
                }
            }
        }
    } catch (e) {
        console.error('Storage size check failed:', e);
    }
}

/**
 * Geçmişi dışa aktar
 */
function exportHistory() {
    const dataStr = JSON.stringify(queryHistory, null, 2);
    const dataUri = 'data:application/json;charset=utf-8,'+ encodeURIComponent(dataStr);
    
    const exportFileDefaultName = `mongodb_history_${new Date().toISOString().split('T')[0]}.json`;
    
    const linkElement = document.createElement('a');
    linkElement.setAttribute('href', dataUri);
    linkElement.setAttribute('download', exportFileDefaultName);
    linkElement.click();
    
    showNotification('Geçmiş dışa aktarıldı', 'success');
}


/**
 * Dosya yükleme işlemi
 */
async function handleFileUpload(event) {
    const file = event.target.files[0];
    if (!file) {
        console.log('No file selected');
        return;
    }
    
    console.log('File selected:', file.name, file.size, 'bytes');
    
    // Dosya boyutu kontrolü (100MB limit)
    const maxSize = 100 * 1024 * 1024; // 100MB
    if (file.size > maxSize) {
        showNotification('Dosya boyutu 100MB\'dan büyük olamaz', 'error');
        return;
    }
    
    const formData = new FormData();
    formData.append('file', file);
    formData.append('api_key', apiKey);
    
    try {
        showLoader(true);
        showNotification('Dosya yükleniyor...', 'info');
        
        const response = await fetch(API_ENDPOINTS.uploadLog, {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        
        if (response.ok) {
            showNotification('Dosya başarıyla yüklendi!', 'success');
            console.log('File uploaded successfully:', data);
            
            // Dosya listesini güncelle
            await updateUploadedFilesList();
            
            // Anomali modal açıksa, yeni dosyayı otomatik seç
            const modal = document.getElementById('anomalyModal');
            if (modal && modal.style.display === 'flex') {
                setTimeout(() => {
                    const newFileRadio = document.querySelector(`input[name="logFile"][value="${data.path}"]`);
                    if (newFileRadio) {
                        newFileRadio.checked = true;
                        validateAnalysisButton();
                    }
                }, 100);
            }
        } else {
            throw new Error(data.detail || 'Dosya yüklenemedi');
        }
    } catch (error) {
        console.error('File upload error:', error);
        showNotification(`Hata: ${error.message}`, 'error');
    } finally {
        showLoader(false);
        // Input'u temizle
        event.target.value = '';
    }
}

/**
 * Detaylı anomali listesini toggle et
 */
function toggleDetailedAnomalyList() {
    const existingDetail = document.getElementById('detailed-anomaly-modal');
    
    if (existingDetail) {
        existingDetail.remove();
        return;
    }
    
    // DEBUG: Data kontrolü
    console.log('toggleDetailedAnomalyList called');
    console.log('window.lastAnomalyResult:', window.lastAnomalyResult);
    console.log('sonuç data:', window.lastAnomalyResult?.sonuç);
    
    if (!window.lastAnomalyResult || !window.lastAnomalyResult.sonuç) {
        console.warn('No anomaly result data available');
        showNotification('Gösterilecek anomali sonucu bulunamadı. Önce bir anomali analizi yapın.', 'warning');
        return;
    }
    
    const result = window.lastAnomalyResult.sonuç;
    
    // Tüm anomalileri topla
    const allAnomalies = [];
    
    // Kritik anomalileri ekle
    if (result.critical_anomalies && result.critical_anomalies.length > 0) {
        result.critical_anomalies.forEach(anomaly => {
            allAnomalies.push({
                ...anomaly,
                category: 'critical',
                anomaly_type: detectAnomalyType(anomaly)
            });
        });
    }
    
    // Component bazlı anomalileri ekle (eğer detaylı veri yoksa)
    if (allAnomalies.length === 0 && result.component_analysis) {
        // Backend'den detaylı veri talep et
        requestDetailedAnomalies();
        return;
    }
    
    // Modal oluştur
    let modalHtml = `
    <div id="detailed-anomaly-modal" class="modal" style="display: block;">
        <div class="modal-content" style="max-width: 90%; height: 80vh;">
            <div class="modal-header">
                <h3>📋 Detaylı Anomali Listesi</h3>
                <span class="close" onclick="document.getElementById('detailed-anomaly-modal').remove()">&times;</span>
            </div>
            <div class="modal-body" style="overflow-y: auto; max-height: calc(80vh - 120px);">
                ${renderDetailedAnomalyList(allAnomalies)}
            </div>
        </div>
    </div>`;
    
    document.body.insertAdjacentHTML('beforeend', modalHtml);
}

/**
 * Anomali tipini tespit et
 */
function detectAnomalyType(anomaly) {
    const message = (anomaly.message || '').toLowerCase();
    const component = (anomaly.component || '').toLowerCase();
    const severity = (anomaly.severity || '').toLowerCase();
    
    // 🔒 SECURITY & AUTHENTICATION PATTERNS
    if (message.includes('authentication failed') || message.includes('unauthorized') || 
        message.includes('access denied') || message.includes('invalid credentials')) {
        return 'auth_failure';
    }
    
    // 🗂️ INDEX & SCHEMA OPERATIONS  
    if (message.includes('drop') && (message.includes('index') || message.includes('collection'))) {
        return 'drop_operation';
    }
    if (message.includes('createindex') || message.includes('index build') || message.includes('indexbuild')) {
        return 'index_build';
    }
    if (message.includes('dropindex') || message.includes('index dropped')) {
        return 'index_drop';
    }
    
    // ⚡ PERFORMANCE CRITICAL PATTERNS
    if (message.includes('collscan') || message.includes('collection scan') || message.includes('full table scan')) {
        return 'collection_scan';
    }
    if (message.includes('docsexamined') && (message.includes('high') || /docsexamined.*[1-9]\d{4,}/.test(message))) {
        return 'high_doc_scan';
    }
    if (message.includes('slow query') || message.includes('slow operation') || /took.*\d+ms/.test(message)) {
        return 'slow_query';
    }
    
    // 🔄 AGGREGATION & PIPELINE
    if (message.includes('aggregate') || message.includes('pipeline') || message.includes('$match') || message.includes('$group')) {
        return 'aggregation_issue';
    }
    
    // 🖥️ SYSTEM & RESOURCE PATTERNS
    if (message.includes('out of memory') || message.includes('oom') || message.includes('memory allocation failed')) {
        return 'out_of_memory';
    }
    if (message.includes('too many connections') || message.includes('connection limit') || message.includes('pool exhausted')) {
        return 'connection_limit';
    }
    if (message.includes('assertion') || message.includes('assert') || message.includes('invariant')) {
        return 'assertion_failure';
    }
    
    // 🔄 REPLICATION & CLUSTER
    if (component === 'repl' || message.includes('oplog') || message.includes('replication')) {
        return 'replication_issue';
    }
    if (message.includes('election') || message.includes('primary') || message.includes('secondary')) {
        return 'replica_set_issue';
    }
    
    // 💾 STORAGE & IO PATTERNS
    if (message.includes('compact') || message.includes('reindex') || message.includes('collmod')) {
        return 'storage_operation';
    }
    if (message.includes('journal') || message.includes('checkpoint') || message.includes('sync')) {
        return 'storage_sync';
    }
    
    // 🚨 SYSTEM EVENTS
    if (message.includes('shutdown') || message.includes('shutting down')) {
        return 'shutdown';
    }
    if (message.includes('restart') || message.includes('restarted') || message.includes('startup')) {
        return 'service_restart';
    }
    if (message.includes('fatal') || severity === 'f') {
        return 'fatal_error';
    }
    
    // 🌐 NETWORK & CONNECTION
    if (message.includes('connection') && (message.includes('drop') || message.includes('closed') || message.includes('timeout'))) {
        return 'connection_drop';
    }
    if (component === 'network' || message.includes('socket') || message.includes('tcp')) {
        return 'network_issue';
    }
    
    // 📊 GENERAL ERROR LEVELS
    if (severity === 'e' || message.includes('error')) {
        return 'error';
    }
    if (severity === 'w' || message.includes('warning')) {
        return 'warning';
    }
    if (component === 'query') {
        return 'query_issue';
    }
    
    return 'unknown';
}

/**
 * Detaylı anomali listesini render et
 */
function renderDetailedAnomalyList(anomalies) {
    if (!anomalies || anomalies.length === 0) {
        return '<p class="no-data">Gösterilecek anomali bulunamadı.</p>';
    }
    
    // Anomali tipine göre grupla
    const groupedAnomalies = {};
    anomalies.forEach(anomaly => {
        const type = anomaly.anomaly_type || 'unknown';
        if (!groupedAnomalies[type]) {
            groupedAnomalies[type] = [];
        }
        groupedAnomalies[type].push(anomaly);
    });
    
    // Anomali tip açıklamaları - MongoDB-SPESİFİK GENİŞLETİLMİŞ VERSİYON
    const typeDescriptions = {
        // 🔒 SECURITY & AUTHENTICATION
        'auth_failure': { icon: '🔐', name: 'Kimlik Doğrulama Hataları', color: '#e74c3c' },
        
        // 🗂️ INDEX & SCHEMA OPERATIONS  
        'drop_operation': { icon: '🗑️', name: 'Drop İşlemleri (Collection/Index)', color: '#e74c3c' },
        'index_build': { icon: '🏗️', name: 'Index Oluşturma İşlemleri', color: '#f39c12' },
        'index_drop': { icon: '📑', name: 'Index Silme İşlemleri', color: '#e67e22' },
        'index_build_fail': { icon: '📑', name: 'Index Oluşturma Hataları', color: '#f39c12' },
        
        // ⚡ PERFORMANCE CRITICAL
        'collection_scan': { icon: '🔍', name: 'Collection Scan (COLLSCAN)', color: '#e67e22' },
        'high_doc_scan': { icon: '📊', name: 'Yüksek Document Scan', color: '#f39c12' },
        'slow_query': { icon: '🐌', name: 'Yavaş Sorgular', color: '#3498db' },
        
        // 🔄 AGGREGATION & PIPELINE
        'aggregation_issue': { icon: '⚙️', name: 'Aggregation Pipeline Sorunları', color: '#9b59b6' },
        
        // 🖥️ SYSTEM & RESOURCE
        'out_of_memory': { icon: '💾', name: 'Bellek Yetersizliği (OOM)', color: '#e74c3c' },
        'connection_limit': { icon: '🔗', name: 'Bağlantı Limiti Aşıldı', color: '#e74c3c' },
        'assertion_failure': { icon: '❗', name: 'Assertion Hataları', color: '#e74c3c' },
        
        // 🔄 REPLICATION & CLUSTER
        'replication_issue': { icon: '🔄', name: 'Replikasyon Sorunları', color: '#9b59b6' },
        'replica_set_issue': { icon: '👥', name: 'Replica Set Sorunları', color: '#8e44ad' },
        
        // 💾 STORAGE & IO
        'storage_operation': { icon: '💿', name: 'Storage İşlemleri (Compact/Reindex)', color: '#16a085' },
        'storage_sync': { icon: '🔄', name: 'Storage Sync İşlemleri', color: '#27ae60' },
        
        // 🚨 SYSTEM EVENTS
        'shutdown': { icon: '⏹️', name: 'Kapanma Olayları', color: '#7f8c8d' },
        'service_restart': { icon: '🔄', name: 'Servis Yeniden Başlatmaları', color: '#9b59b6' },
        'fatal_error': { icon: '💀', name: 'Fatal Hatalar', color: '#c0392b' },
        
        // 🌐 NETWORK & CONNECTION
        'connection_drop': { icon: '🔌', name: 'Bağlantı Kopmaları', color: '#e67e22' },
        'network_issue': { icon: '🌐', name: 'Network Sorunları', color: '#3498db' },
        
        // 📊 GENERAL CATEGORIES
        'error': { icon: '❌', name: 'Genel Hatalar', color: '#e74c3c' },
        'warning': { icon: '⚠️', name: 'Uyarılar', color: '#f39c12' },
        'query_issue': { icon: '❓', name: 'Sorgu Sorunları', color: '#e67e22' },
        'unknown': { icon: '❔', name: 'Sınıflandırılmamış', color: '#95a5a6' }
    };
    
    let html = '<div class="anomaly-type-groups">';
    
    // Özet bilgi
    console.log('[DEBUG FRONTEND] renderDetailedAnomalyList - received anomalies count:', anomalies.length);
    html += `
        <div class="anomaly-summary-stats">
            <h4>📊 Özet Bilgiler</h4>
            <div class="summary-grid">
                <div class="summary-card">
                    <span class="summary-value">${anomalies.length}</span>
                    <span class="summary-label">Toplam Anomali</span>
                </div>
                <div class="summary-card">
                    <span class="summary-value">${Object.keys(groupedAnomalies).length}</span>
                    <span class="summary-label">Farklı Tip</span>
                </div>
                <div class="summary-card warning">
                    <span class="summary-value">${anomalies.filter(a => a.category === 'critical').length}</span>
                    <span class="summary-label">Kritik Anomali</span>
                </div>
            </div>
        </div>
    `;
    
    // Her tip için anomalileri listele
    Object.entries(groupedAnomalies).forEach(([type, typeAnomalies]) => {
        const typeInfo = typeDescriptions[type] || typeDescriptions['unknown'];
        
        html += `
            <div class="anomaly-type-section">
                <h4 style="color: ${typeInfo.color}">
                    ${typeInfo.icon} ${typeInfo.name} (${typeAnomalies.length})
                </h4>
                <div class="anomaly-list-by-type">
        `;
        
        // Tüm anomalileri göster
        typeAnomalies.forEach((anomaly, index) => {
            const score = anomaly.score || anomaly.anomaly_score || 0;
            const scoreClass = score < -0.78 ? 'critical' : score < -0.75 ? 'high' : 'medium';
            
            html += `
                <div class="detailed-anomaly-item ${scoreClass}">
                    <div class="anomaly-header-row">
                        <span class="anomaly-number">#${anomaly.index || index + 1}</span>
                        <span class="anomaly-timestamp">${new Date(anomaly.timestamp).toLocaleString('tr-TR')}</span>
                        <span class="anomaly-score-badge ${scoreClass}">Score: ${score.toFixed(4)}</span>
                    </div>
                    <div class="anomaly-content">
                        <div class="anomaly-message">
                            <strong>Log:</strong> ${escapeHtml(anomaly.message)}
                        </div>
                        <div class="anomaly-metadata">
                            <span class="metadata-item">
                                <strong>Severity:</strong> ${anomaly.severity || 'N/A'}
                            </span>
                        </div>
                        ${getAnomalyExplanation(type)}
                    </div>
                </div>
            `;
        });
        
        // Tüm anomaliler gösteriliyor, ek mesaj gerekmiyor
        
        html += '</div></div>';
    });
    
    html += '</div>';
    return html;
}

/**
 * Anomali tipi için açıklama getir
 */
function getAnomalyExplanation(type) {
    const explanations = {
        'auth_failure': '<div class="anomaly-explanation">⚡ Kullanıcı kimlik doğrulama başarısız. Yanlış şifre veya yetkisiz erişim denemesi olabilir.</div>',
        'connection_drop': '<div class="anomaly-explanation">⚡ İstemci bağlantısı beklenmedik şekilde kesildi. Network sorunları veya timeout olabilir.</div>',
        'slow_query': '<div class="anomaly-explanation">⚡ Sorgu çok uzun sürdü. Index eksikliği veya verimsiz sorgu yapısı olabilir.</div>',
        'out_of_memory': '<div class="anomaly-explanation">⚡ Bellek yetersizliği. Working set çok büyük veya bellek sızıntısı olabilir.</div>',
        'collection_scan': '<div class="anomaly-explanation">⚡ Tüm koleksiyon tarandı. Uygun index oluşturulmalı.</div>',
        'assertion_failure': '<div class="anomaly-explanation">⚡ MongoDB internal assertion hatası. Yazılım hatası veya veri tutarsızlığı olabilir.</div>',
        default: ''
    };
    
    return explanations[type] || explanations.default;
}

/**
 * Backend'den detaylı anomali verisi iste
 */
async function requestDetailedAnomalies() {
    try {
        showLoading('Detaylı anomali verileri yükleniyor...');
        
        // Mevcut analiz parametrelerini kullan
        const lastParams = window.lastAnalysisParams || {};
        
        const response = await fetch('/api/get-detailed-anomalies', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                api_key: API_KEY,
                source_type: lastParams.source_type || 'opensearch',
                host_filter: lastParams.host_filter,
                time_range: lastParams.time_range || 'last_day',
                limit: 2000 // Maksimum 2000 anomali getir
            })
        });
        
        hideLoading();
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        
        if (data.anomalies && data.anomalies.length > 0) {
            // Detaylı veriyi göster
            const detailedAnomalies = data.anomalies.map(anomaly => ({
                ...anomaly,
                anomaly_type: detectAnomalyType(anomaly)
            }));
            
            // Modal oluştur ve göster
            showDetailedAnomalyModal(detailedAnomalies);
        } else {
            showNotification('Detaylı anomali verisi bulunamadı', 'warning');
        }
        
    } catch (error) {
        hideLoading();
        console.error('Detaylı anomali verisi alınırken hata:', error);
        showNotification('Detaylı veriler yüklenemedi', 'error');
    }
}

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
// ============================================
// ML VISUALIZATION FUNCTIONS
// ============================================
// script-ml-visualization.js'den window objesi üzerinden alınıyor
const renderMLModelMetrics = window.renderMLModelMetrics;
    let html = '<div class="ml-metrics-unified">';
    html += '<h3>🤖 ML Model Performans Metrikleri</h3>';
    html += '<div class="ml-priority-metrics">';
    
    // 1. Model Accuracy Score
    const modelAccuracy = summary.anomaly_rate ? (100 - summary.anomaly_rate).toFixed(1) : 'N/A';
    const accuracyLevel = modelAccuracy >= 95 ? 'excellent' : 
                         modelAccuracy >= 90 ? 'good' : 
                         modelAccuracy >= 80 ? 'average' : 
                         modelAccuracy >= 70 ? 'poor' : 'critical';
    
    html += `
        <div class="ml-metric-row ${accuracyLevel === 'excellent' || accuracyLevel === 'good' ? 'normal' : 
                                   accuracyLevel === 'average' ? 'high' : 'critical'}">
            <div class="ml-metric-content">
                <div class="ml-metric-icon-wrapper">
                    🎯
                </div>
                <div class="ml-metric-details">
                    <div class="ml-metric-title">Model Accuracy</div>
                    <div class="ml-metric-primary-value">${modelAccuracy}%</div>
                    <div class="ml-metric-secondary-info">
                        <span class="ml-metric-badge ${accuracyLevel === 'excellent' || accuracyLevel === 'good' ? 'success' : 
                                                       accuracyLevel === 'average' ? 'warning' : 'danger'}">
                            ${accuracyLevel.toUpperCase()}
                        </span>
                        <span class="ml-metric-badge">
                            Anomali Oranı: %${summary.anomaly_rate?.toFixed(2) || 0}
                        </span>
                    </div>
                </div>
                <div class="ml-metric-progress">
                    <div class="ml-progress-label">
                        <span>Accuracy</span>
                        <span>${modelAccuracy}%</span>
                    </div>
                    <div class="ml-progress-bar">
                        <div class="ml-progress-fill ${accuracyLevel}" style="width: ${modelAccuracy}%"></div>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    // 2. Anomaly Detection Statistics
    html += `
        <div class="ml-metric-row info">
            <div class="ml-metric-content">
                <div class="ml-metric-icon-wrapper">
                    🔍
                </div>
                <div class="ml-metric-details">
                    <div class="ml-metric-title">Detection Statistics</div>
                    <div class="ml-metric-primary-value">${summary.n_anomalies?.toLocaleString('tr-TR') || 0}</div>
                    <div class="ml-metric-secondary-info">
                        <span class="ml-metric-badge">
                            📊 Total Logs: ${summary.total_logs?.toLocaleString('tr-TR') || 0}
                        </span>
                        <span class="ml-metric-badge ${summary.anomaly_rate > 5 ? 'warning' : 'success'}">
                            📈 Detection Rate: %${summary.anomaly_rate?.toFixed(2) || 0}
                        </span>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    // 3. Isolation Score Range
    if (scoreStats && scoreStats.min !== undefined) {
        const scoreRange = `${scoreStats.min?.toFixed(3) || 'N/A'} - ${scoreStats.max?.toFixed(3) || 'N/A'}`;
        const meanPosition = scoreStats.mean && scoreStats.min && scoreStats.max ? 
                           ((scoreStats.mean - scoreStats.min) / (scoreStats.max - scoreStats.min) * 100) : 50;
        
        html += `
            <div class="ml-metric-row normal">
                <div class="ml-metric-content">
                    <div class="ml-metric-icon-wrapper">
                        📊
                    </div>
                    <div class="ml-metric-details">
                        <div class="ml-metric-title">Anomaly Score Range</div>
                        <div class="ml-metric-primary-value">${scoreRange}</div>
                        <div class="ml-metric-secondary-info">
                            <span class="ml-metric-badge">
                                Mean: ${scoreStats.mean?.toFixed(3) || 'N/A'}
                            </span>
                            <span class="ml-metric-badge">
                                Std Dev: ${scoreStats.std?.toFixed(3) || 'N/A'}
                            </span>
                        </div>
                    </div>
                    <div class="ml-metric-progress">
                        <div class="ml-progress-label">
                            <span>Min</span>
                            <span>Max</span>
                        </div>
                        <div class="ml-progress-bar">
                            <div class="ml-progress-fill average" style="width: 100%"></div>
                            <div style="position: absolute; left: ${meanPosition}%; top: -5px; 
                                        width: 2px; height: 18px; background: #2196F3; 
                                        border-radius: 1px;" title="Mean: ${scoreStats.mean?.toFixed(3)}"></div>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }
    
  
    // 5. Online Learning Status (varsa)
    if (summary.online_learning_status) {
        const onlineStatus = summary.online_learning_status;
        const statusClass = onlineStatus.mode === 'incremental' ? 'info' : 'normal';
        
        html += `
            <div class="ml-metric-row ${statusClass}">
                <div class="ml-metric-content">
                    <div class="ml-metric-icon-wrapper">
                        🔄
                    </div>
                    <div class="ml-metric-details">
                        <div class="ml-metric-title">Online Learning Status</div>
                        <div class="ml-metric-primary-value">${onlineStatus.mode === 'incremental' ? 'Aktif' : 'Standart'}</div>
                        <div class="ml-metric-secondary-info">
                            ${onlineStatus.buffer_size_mb !== undefined ? `
                                <span class="ml-metric-badge ${onlineStatus.buffer_size_mb > 500 ? 'warning' : ''}>
                                    💾 Buffer: ${onlineStatus.buffer_size_mb.toFixed(2)} MB
                                </span>
                            ` : ''}
                            ${onlineStatus.total_samples !== undefined ? `
                                <span class="ml-metric-badge">
                                    📊 Samples: ${onlineStatus.total_samples.toLocaleString('tr-TR')}
                                </span>
                            ` : ''}
                        </div>
                    </div>
                </div>
            </div>
        `;
    }
    
    html += '</div></div>';
    return html;
}

// Yardımcı fonksiyon - Expand/Collapse için
window.toggleMLExpand = function(button) {
    const content = button.nextElementSibling;
    const isExpanded = content.classList.contains('show');
    
    if (isExpanded) {
        content.classList.remove('show');
        button.textContent = 'Kural Detaylarını Göster ▼';
    } else {
        content.classList.add('show');
        button.textContent = 'Kural Detaylarını Gizle ▲';
    }
};

/**
 * Online Learning Status Render Et
 */
function renderOnlineLearningStatus(onlineStatus) {
    if (!onlineStatus) return '';
    
    let html = '<div class="online-learning-status-section">';
    html += '<h3>🔄 Online Learning Status</h3>';
    html += '<div class="online-status-grid">';
    
    // Mode göstergesi
    const mode = onlineStatus.mode || 'standard';
    const modeClass = mode === 'incremental' ? 'active' : 'inactive';
    html += `
        <div class="online-status-card ${modeClass}">
            <div class="status-icon">🧠</div>
            <div class="status-content">
                <div class="status-label">Learning Mode</div>
                <div class="status-value">${mode === 'incremental' ? 'Incremental (Aktif)' : 'Standard'}</div>
            </div>
        </div>
    `;
    
    // Historical Buffer Size
    if (onlineStatus.buffer_size_mb !== undefined) {
        const sizeClass = onlineStatus.buffer_size_mb > 500 ? 'warning' : 
                         onlineStatus.buffer_size_mb > 1000 ? 'critical' : 'normal';
        html += `
            <div class="online-status-card ${sizeClass}">
                <div class="status-icon">💾</div>
                <div class="status-content">
                    <div class="status-label">Buffer Size</div>
                    <div class="status-value">${onlineStatus.buffer_size_mb.toFixed(2)} MB</div>
                    ${onlineStatus.buffer_size_mb > 500 ? 
                        '<div class="status-warning">⚠️ Yüksek bellek kullanımı</div>' : ''}
                </div>
            </div>
        `;
    }
    
    // Total Historical Samples
    if (onlineStatus.total_samples !== undefined) {
        html += `
            <div class="online-status-card">
                <div class="status-icon">📊</div>
                <div class="status-content">
                    <div class="status-label">Historical Samples</div>
                    <div class="status-value">${onlineStatus.total_samples.toLocaleString('tr-TR')}</div>
                    ${onlineStatus.anomaly_samples ? 
                        `<div class="status-info">${onlineStatus.anomaly_samples} anomali</div>` : ''}
                </div>
            </div>
        `;
    }
    
    // Last Update Time
    if (onlineStatus.last_update) {
        const updateTime = new Date(onlineStatus.last_update);
        const timeDiff = Date.now() - updateTime.getTime();
        const hoursAgo = Math.floor(timeDiff / (1000 * 60 * 60));
        
        html += `
            <div class="online-status-card">
                <div class="status-icon">⏰</div>
                <div class="status-content">
                    <div class="status-label">Son Güncelleme</div>
                    <div class="status-value">${updateTime.toLocaleString('tr-TR')}</div>
                    <div class="status-info">${hoursAgo > 0 ? `${hoursAgo} saat önce` : 'Yakın zamanda'}</div>
                </div>
            </div>
        `;
    }
    
    // Model Version
    if (onlineStatus.model_version) {
        html += `
            <div class="online-status-card">
                <div class="status-icon">🏷️</div>
                <div class="status-content">
                    <div class="status-label">Model Version</div>
                    <div class="status-value">v${onlineStatus.model_version}</div>
                </div>
            </div>
        `;
    }
    
    // Historical Anomaly Rate
    if (onlineStatus.historical_anomaly_rate !== undefined) {
        const rateClass = onlineStatus.historical_anomaly_rate > 10 ? 'warning' : 'normal';
        html += `
            <div class="online-status-card ${rateClass}">
                <div class="status-icon">📈</div>
                <div class="status-content">
                    <div class="status-label">Historical Anomaly Rate</div>
                    <div class="status-value">%${onlineStatus.historical_anomaly_rate.toFixed(2)}</div>
                </div>
            </div>
        `;
    }
    
    html += '</div>';
    
    // Bilgi mesajı
    if (mode === 'incremental') {
        html += `<div class="online-learning-info">
            <p>ℹ️ <strong>Incremental Learning Aktif:</strong> Model, geçmiş pattern'ları hatırlayarak yeni verilerle güncelleniyor.</p>
        </div>`;
    }
    
    html += '</div>';
    return html;
}

/**
 * Component Comparison Chart Render Et
 */
function renderComponentComparisonChart(componentAnalysis) {
    // Component analiz için ek grafik
    return ''; // Şimdilik boş, gerekirse eklenebilir
}


/**
 * Feature isimlerini Türkçe'ye çevir ve formatla
 */
function formatFeatureName(name) {
    const nameMap = {
        'severity_W': 'Uyarı Seviyesi',
        'component_encoded': 'Component Kodu',
        'is_rare_component': 'Nadir Bileşen', 
        'is_rare_combo': 'Nadir Kombinasyon',
        'has_error_key': 'Hata Anahtarı',
        'is_auth_failure': 'Kimlik Doğrulama Hatası',
        'is_drop_operation': 'DROP İşlemi',
        'is_rare_message': 'Nadir Mesaj',
        'extreme_burst_flag': 'Aşırı Yoğunluk',
        'burst_density': 'Yoğunluk Seviyesi',
        'component_changed': 'Component Değişimi',
        'hour_of_day': 'Günün Saati',
        'is_weekend': 'Hafta Sonu',
        'attr_key_count': 'Özellik Sayısı',
        'has_many_attrs': 'Çok Özellikli',
        'is_collscan': 'Koleksiyon Tarama',
        'is_index_build': 'İndeks Oluşturma',
        'is_slow_query': 'Yavaş Sorgu',
        'is_high_doc_scan': 'Yüksek Doküman Tarama',
        'is_shutdown': 'Kapatma',
        'is_assertion': 'Assertion',
        'is_fatal': 'Kritik Hata',
        'is_error': 'Hata',
        'is_replication_issue': 'Replikasyon Sorunu',
        'is_out_of_memory': 'Bellek Yetersizliği',
        'is_restart': 'Yeniden Başlatma',
        'is_memory_limit': 'Bellek Limiti',
        'query_duration_ms': 'Sorgu Süresi (ms)',
        'docs_examined_count': 'İncelenen Doküman',
        'keys_examined_count': 'İncelenen Anahtar',
        'performance_score': 'Performans Skoru'
    };
    
    if (nameMap[name]) {
        return nameMap[name];
    }
    
    return name
        .replace(/_/g, ' ')
        .replace(/\b\w/g, l => l.toUpperCase());
}

/**
 * Feature açıklamalarını getir
 */
function getFeatureDescription(name) {
    const descMap = {
        'severity_W': 'Uyarı seviyesindeki log kayıtları',
        'component_encoded': 'MongoDB component kodlaması',
        'is_rare_component': 'Nadir görülen MongoDB bileşenleri',
        'is_rare_combo': 'Nadir görülen özellik kombinasyonları',
        'has_error_key': 'Hata anahtarı içeren log kayıtları',
        'is_auth_failure': 'Kimlik doğrulama başarısızlıkları',
        'is_drop_operation': 'Veritabanı veya koleksiyon DROP işlemleri',
        'is_rare_message': 'Nadir görülen log mesajları',
        'extreme_burst_flag': 'Aşırı yoğunluk dönemleri',
        'burst_density': 'Log yoğunluğu seviyesi',
        'component_changed': 'Component değişikliği olan kayıtlar',
        'hour_of_day': 'Olayın gerçekleştiği saat',
        'is_weekend': 'Hafta sonu gerçekleşen olaylar',
        'attr_key_count': 'Log kaydındaki özellik sayısı',
        'has_many_attrs': 'Çok sayıda özellik içeren kayıtlar',
        'is_collscan': 'İndeks kullanmayan koleksiyon tarama işlemleri',
        'is_index_build': 'İndeks oluşturma işlemleri',
        'is_slow_query': 'Yavaş çalışan MongoDB sorguları',
        'is_high_doc_scan': 'Yüksek sayıda doküman tarayan işlemler',
        'is_shutdown': 'MongoDB servis kapatma işlemleri',
        'is_assertion': 'MongoDB assertion hataları',
        'is_fatal': 'Kritik sistem hataları',
        'is_error': 'Genel hata durumları',
        'is_replication_issue': 'Replikasyon ile ilgili sorunlar',
        'is_out_of_memory': 'Bellek yetersizliği hataları',
        'is_restart': 'Sistem yeniden başlatma olayları',
        'is_memory_limit': 'Bellek limiti aşımları',
        'query_duration_ms': 'Sorgu çalışma süresi (milisaniye)',
        'docs_examined_count': 'Sorgu tarafından incelenen doküman sayısı',
        'keys_examined_count': 'Sorgu tarafından incelenen anahtar sayısı',
        'performance_score': 'Genel performans skoru'
    };
    
    return descMap[name] || '';
}

/**
 * Feature için insight üret
 */
function getFeatureInsight(feature, ratio, anomalyRate, normalRate) {
    let insightHtml = '<div class="feature-insight">';
    
    if (ratio === Infinity || ratio > 10) {
        insightHtml += '<div class="insight-badge critical">⚠️ Kritik Gösterge</div>';
        insightHtml += '<div class="insight-text">Bu özellik neredeyse sadece anomalilerde görülüyor!</div>';
    } else if (ratio > 5) {
        insightHtml += '<div class="insight-badge high">📍 Yüksek Önem</div>';
        insightHtml += '<div class="insight-text">Anomali tespitinde güçlü bir gösterge</div>';
    } else if (ratio > 2) {
        insightHtml += '<div class="insight-badge medium">📊 Orta Önem</div>';
        insightHtml += '<div class="insight-text">Anomali göstergesi olarak değerli</div>';
    } else {
        insightHtml += '<div class="insight-badge low">ℹ️ Düşük Önem</div>';
        insightHtml += '<div class="insight-text">Yardımcı gösterge</div>';
    }
    
    insightHtml += '</div>';
    return insightHtml;
}

/**
 * Component Dashboard Render Et - SADELEŞTİRİLMİŞ VERSİYON
 */
function renderFeatureImportanceChart(featureImportance) {
    let html = '<div class="feature-importance-unified">';
    html += '<h3>📈 Feature Importance Analysis</h3>';
    
    // Feature'ları ratio'ya göre sırala
    const sortedFeatures = Object.entries(featureImportance)
        .sort(([,a], [,b]) => (b.ratio || 0) - (a.ratio || 0));
    
    html += '<div class="feature-grid">';
    
    sortedFeatures.forEach(([feature, stats], index) => {
        const ratio = stats.ratio || 1;
        const anomalyRate = stats.anomaly_rate || 0;
        const normalRate = stats.normal_rate || 0;
        
        // Ratio severity belirleme
        let ratioClass = 'low';
        if (ratio === Infinity || ratio > 10) {
            ratioClass = 'critical';
        } else if (ratio > 5) {
            ratioClass = 'high';
        } else if (ratio > 2) {
            ratioClass = 'medium';
        }
        
        // Feature ismini daha okunabilir hale getir
        const featureLabel = formatFeatureName(feature);
        const featureDescription = getFeatureDescription(feature);
        
        // Anomaly vs Normal oranını hesapla
        const totalRate = anomalyRate + normalRate;
        const anomalyPercent = totalRate > 0 ? (anomalyRate / totalRate * 100) : 0;
        const normalPercent = totalRate > 0 ? (normalRate / totalRate * 100) : 0;
        
        html += `
            <div class="feature-card" onclick="showFeatureDetails('${feature}')">
                <div class="feature-tooltip">?</div>
                
                <div class="feature-header">
                    <div class="feature-name-box">
                        <div class="feature-label feature-name-${feature}">${featureLabel}</div>
                        ${featureDescription ? `<div class="feature-description">${featureDescription}</div>` : ''}
                    </div>
                    <div class="feature-ratio-indicator ratio-${ratioClass}">
                        <div class="feature-ratio-value">${ratio === Infinity ? '∞' : ratio.toFixed(1)}x</div>
                        <div class="feature-ratio-label">RATIO</div>
                    </div>
                </div>
                
                <div class="feature-metrics">
                    <div class="feature-metric-box anomaly">
                        <div class="feature-metric-title">Anomaly Rate</div>
                        <div class="feature-metric-percent">${anomalyRate.toFixed(1)}%</div>
                        <div class="feature-metric-count">Anomalilerde görülme</div>
                    </div>
                    <div class="feature-metric-box normal">
                        <div class="feature-metric-title">Normal Rate</div>
                        <div class="feature-metric-percent">${normalRate.toFixed(1)}%</div>
                        <div class="feature-metric-count">Normal loglarda görülme</div>
                    </div>
                </div>
                
                <div class="feature-comparison-bar">
                    ${anomalyPercent > 0 ? `
                        <div class="comparison-segment anomaly" style="width: ${anomalyPercent}%">
                            ${anomalyPercent > 20 ? `${anomalyPercent.toFixed(0)}%` : ''}
                        </div>
                    ` : ''}
                    ${normalPercent > 0 ? `
                        <div class="comparison-segment normal" style="width: ${normalPercent}%">
                            ${normalPercent > 20 ? `${normalPercent.toFixed(0)}%` : ''}
                        </div>
                    ` : ''}
                    ${anomalyPercent > 0 && normalPercent > 0 ? `
                        <div class="comparison-divider" style="left: ${anomalyPercent}%"></div>
                    ` : ''}
                </div>
                
                ${getFeatureInsight(feature, ratio, anomalyRate, normalRate)}
            </div>
        `;
    });
    
    html += '</div>';
    
    // Bilgi ve aksiyonlar
    html += `
        <div class="feature-actions-section">
            <p class="feature-info-note">
                <strong>Feature Importance</strong>, her bir özelliğin anomali tespitindeki önemini gösterir. 
                Yüksek ratio değeri, o özelliğin anomali tespitinde kritik rol oynadığını belirtir.
            </p>
            <div class="feature-action-buttons">
                <button class="feature-action-btn" onclick="showFeatureAnalysisDetails()">
                    📊 Detaylı Analiz Raporu
                </button>
                <button class="feature-action-btn" onclick="exportFeatureImportance()">
                    📥 Feature Verilerini İndir
                </button>
            </div>
        </div>
    `;
    
    html += '</div>';
    return html;
}

/**
 * Component Dashboard Render Et - SADELEŞTİRİLMİŞ VERSİYON
 */
function renderComponentDashboard(componentAnalysis) {
    let html = '<div class="component-dashboard-unified">';
    html += '<h3>🎛️ Component Bazlı Anomali Dağılımı</h3>';
    
    // Component'leri anomali oranına göre sırala
    const sortedComponents = Object.entries(componentAnalysis)
        .sort(([,a], [,b]) => b.anomaly_rate - a.anomaly_rate);
    
    // Özet istatistikler
    const totalComponents = sortedComponents.length;
    const criticalComponents = sortedComponents.filter(([,stats]) => stats.anomaly_rate > 20).length;
    const warningComponents = sortedComponents.filter(([,stats]) => stats.anomaly_rate > 10 && stats.anomaly_rate <= 20).length;
    
    // Özet kartları
    html += '<div class="component-summary-cards">';
    html += `
        <div class="component-summary-card">
            <div class="summary-icon">📊</div>
            <div class="summary-value">${totalComponents}</div>
            <div class="summary-label">Toplam Component</div>
        </div>
        <div class="component-summary-card critical">
            <div class="summary-icon">🚨</div>
            <div class="summary-value">${criticalComponents}</div>
            <div class="summary-label">Kritik Component</div>
        </div>
        <div class="component-summary-card warning">
            <div class="summary-icon">⚠️</div>
            <div class="summary-value">${warningComponents}</div>
            <div class="summary-label">Dikkat Gerektiren</div>
        </div>
    `;
    html += '</div>';
    
    // Component listesi - Priority based
    html += '<div class="component-priority-list">';
    
    // İlk 10 component'i göster
    const componentsToShow = sortedComponents.slice(0, 10);
    
    componentsToShow.forEach(([component, stats], index) => {
        const anomalyRate = stats.anomaly_rate || 0;
        const anomalyCount = stats.anomaly_count || 0;
        const totalCount = stats.total_count || 1;
        
        // Kritiklik seviyesi belirleme
        let criticalityClass = 'normal';
        let criticalityLabel = 'Normal';
        let criticalityIcon = '✅';
        
        if (anomalyRate > 20) {
            criticalityClass = 'critical';
            criticalityLabel = 'KRİTİK';
            criticalityIcon = '🔴';
        } else if (anomalyRate > 10) {
            criticalityClass = 'high';
            criticalityLabel = 'YÜKSEK';
            criticalityIcon = '🟠';
        } else if (anomalyRate > 5) {
            criticalityClass = 'medium';
            criticalityLabel = 'ORTA';
            criticalityIcon = '🟡';
        } else if (anomalyRate > 2) {
            criticalityClass = 'low';
            criticalityLabel = 'DÜŞÜK';
            criticalityIcon = '🔵';
        }
        
        // Component icon
        const componentIcon = getComponentIcon(component);
        
        html += `
            <div class="component-item ${criticalityClass}" data-component="${component}">
                <div class="component-content">
                    <div class="component-rank">#${index + 1}</div>
                    <div class="component-icon-box">
                        ${componentIcon}
                    </div>
                    <div class="component-info">
                        <div class="component-name">${component}</div>
                        <div class="component-metrics">
                            <span class="metric-item">
                                <strong>Anomali:</strong> ${anomalyCount.toLocaleString('tr-TR')}
                            </span>
                            <span class="metric-item">
                                <strong>Toplam:</strong> ${totalCount.toLocaleString('tr-TR')}
                            </span>
                        </div>
                    </div>
                    <div class="component-rate-visual">
                        <div class="rate-percentage ${criticalityClass}">
                            %${anomalyRate.toFixed(1)}
                        </div>
                        <div class="rate-bar">
                            <div class="rate-bar-fill ${criticalityClass}" style="width: ${Math.min(anomalyRate, 100)}%"></div>
                        </div>
                        <div class="criticality-badge ${criticalityClass}">
                            ${criticalityIcon} ${criticalityLabel}
                        </div>
                    </div>
                </div>
                ${anomalyRate === 100 ? `
                    <div class="component-alert">
                        ⚠️ Bu component'teki tüm loglar anomali olarak işaretlendi!
                    </div>
                ` : ''}
            </div>
        `;
    });
    
    // Daha fazla component varsa göster
    if (sortedComponents.length > 10) {
        html += `
            <div class="more-components-notice">
                <p>... ve ${sortedComponents.length - 10} component daha</p>
                <button class="btn btn-secondary" onclick="showAllComponents()">
                    📋 Tüm Component'leri Göster
                </button>
            </div>
        `;
    }
    
    html += '</div>';
    
    // Action buttons
    html += '<div class="component-actions">';
    html += `
        <button class="btn btn-primary" onclick="showAllComponents()">
            📊 Detaylı Component Analizi
        </button>
        <button class="btn btn-secondary" onclick="exportComponentAnalysis()">
            📥 Component Verilerini İndir
        </button>
    `;
    html += '</div>';
    
    html += '</div>';
    return html;
}

/**
 * Get Component Icon - Eğer tanımlı değilse bu helper fonksiyonu da ekleyin
 */
function getComponentIcon(component) {
    const iconMap = {
        'STORAGE': '💾',
        'NETWORK': '🌐', 
        'QUERY': '🔍',
        'WRITE': '✏️',
        'INDEX': '📑',
        'REPL': '🔄',
        'COMMAND': '⚡',
        'ACCESS': '🔐',
        'CONTROL': '🎛️',
        'SHARDING': '🔀',
        'CONNPOOL': '🔌',
        'ELECTION': '🗳️',
        'RECOVERY': '🔧',
        'ROLLBACK': '↩️',
        'FTDC': '📊'
    };
    return iconMap[component] || '📦';
}

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
function renderTemporalHeatmap(temporalAnalysis) {
    let html = '<div class="temporal-analysis-unified">';
    html += '<h3>🗓️ Temporal Pattern Analysis</h3>';
    
    const hourlyData = temporalAnalysis.hourly_distribution || {};
    const peakHours = temporalAnalysis.peak_hours || [];
    
    // Toplam anomali sayısı ve maksimum değer
    const totalAnomalies = Object.values(hourlyData).reduce((sum, val) => sum + val, 0);
    const maxValue = Math.max(...Object.values(hourlyData), 1);
    const avgPerHour = totalAnomalies / 24;
    
    // Özet kartları
    html += '<div class="temporal-summary-cards">';
    
    html += `
        <div class="temporal-summary-card">
            <div class="temporal-card-icon">📊</div>
            <div class="temporal-card-value">${totalAnomalies.toLocaleString('tr-TR')}</div>
            <div class="temporal-card-label">Toplam Anomali</div>
        </div>
        
        <div class="temporal-summary-card">
            <div class="temporal-card-icon">⏰</div>
            <div class="temporal-card-value">${peakHours.length}</div>
            <div class="temporal-card-label">Yoğun Saat</div>
        </div>
        
        <div class="temporal-summary-card">
            <div class="temporal-card-icon">📈</div>
            <div class="temporal-card-value">${maxValue}</div>
            <div class="temporal-card-label">En Yüksek</div>
        </div>
        
        <div class="temporal-summary-card">
            <div class="temporal-card-icon">📉</div>
            <div class="temporal-card-value">${avgPerHour.toFixed(1)}</div>
            <div class="temporal-card-label">Saat Başı Ort.</div>
        </div>
    `;
    
    html += '</div>';
    
    // Peak hours bilgisi
    if (peakHours.length > 0) {
        html += '<div class="peak-hours-section">';
        html += '<div class="peak-hours-title">';
        html += '🚨 En Yoğun Saatler';
        html += '</div>';
        html += '<div class="peak-hours-list">';
        
        peakHours.forEach(hour => {
            const count = hourlyData[hour] || 0;
            html += `
                <div class="peak-hour-badge">
                    <span>Saat ${hour}:00</span>
                    <span class="peak-hour-count">${count} anomali</span>
                </div>
            `;
        });
        
        html += '</div>';
        html += '</div>';
    }
    
    // Basitleştirilmiş görsel grafik
    html += '<div class="hour-distribution-chart">';
    html += '<div class="chart-title">24 Saatlik Dağılım</div>';
    html += '<div class="hour-bars">';
    
    for (let hour = 0; hour < 24; hour++) {
        const value = hourlyData[hour] || 0;
        const height = maxValue > 0 ? (value / maxValue) * 100 : 0;
        const isPeak = peakHours.includes(hour);
        
        html += `
            <div class="hour-bar-item ${isPeak ? 'is-peak' : ''}" 
                 style="height: ${height}%">
                <div class="hour-bar-tooltip">
                    Saat ${hour}:00 - ${value} anomali
                </div>
            </div>
        `;
    }
    
    html += '</div>';
    html += '<div class="hour-labels">';
    
    for (let hour = 0; hour < 24; hour++) {
        html += `<div class="hour-label-item">${hour}</div>`;
    }
    
    html += '</div>';
    html += '</div>';
    
    // Detaylı saat blokları (önemli saatler için)
    const significantHours = Object.entries(hourlyData)
        .filter(([hour, count]) => count > avgPerHour || peakHours.includes(parseInt(hour)))
        .sort(([,a], [,b]) => b - a);
    
    if (significantHours.length > 0) {
        html += '<div class="hourly-timeline">';
        html += '<div class="timeline-header">';
        html += '<div class="timeline-title">Önemli Saatler</div>';
        html += '<div class="timeline-legend">';
        html += '<div class="legend-item"><span class="legend-dot high"></span> Kritik</div>';
        html += '<div class="legend-item"><span class="legend-dot medium"></span> Yüksek</div>';
        html += '<div class="legend-item"><span class="legend-dot low"></span> Normal</div>';
        html += '</div>';
        html += '</div>';
        
        html += '<div class="hour-blocks">';
        
        significantHours.slice(0, 12).forEach(([hour, count]) => {
            const severity = count > maxValue * 0.8 ? 'critical' :
                           count > maxValue * 0.5 ? 'high' :
                           count > avgPerHour ? 'medium' : 'low';
            
            const percentage = totalAnomalies > 0 ? (count / totalAnomalies * 100).toFixed(1) : 0;
            
            html += `
                <div class="hour-block ${severity}">
                    <div class="hour-block-header">
                        <div class="hour-time">Saat ${hour}:00</div>
                        <div class="hour-anomaly-count">${count}</div>
                    </div>
                    <div class="hour-details">
                        Toplam anomalinin %${percentage}'i
                    </div>
                </div>
            `;
        });
        
        html += '</div>';
        html += '</div>';
    }
    
    // Temporal pattern insights
    html += '<div class="temporal-patterns">';
    html += '<div class="patterns-title">📊 Tespit Edilen Pattern\'ler</div>';
    html += '<div class="pattern-insights">';
    
    // Pattern analizi
    const patterns = analyzeTemporalPatterns(hourlyData, peakHours);
    
    patterns.forEach(pattern => {
        html += `
            <div class="pattern-insight">
                <div class="pattern-icon">${pattern.icon}</div>
                <div class="pattern-content">
                    <div class="pattern-title">${pattern.title}</div>
                    <div class="pattern-description">${pattern.description}</div>
                </div>
            </div>
        `;
    });
    
    html += '</div>';
    html += '</div>';
    
    html += '</div>';
    return html;
}

// Temporal pattern analizi için yardımcı fonksiyon
function analyzeTemporalPatterns(hourlyData, peakHours) {
    const patterns = [];
    
    // İş saatleri analizi (09:00 - 18:00)
    const workHours = [9, 10, 11, 12, 13, 14, 15, 16, 17, 18];
    const workHourAnomalies = workHours.reduce((sum, h) => sum + (hourlyData[h] || 0), 0);
    const totalAnomalies = Object.values(hourlyData).reduce((sum, val) => sum + val, 0);
    const workHourPercentage = totalAnomalies > 0 ? (workHourAnomalies / totalAnomalies * 100).toFixed(1) : 0;
    
    if (workHourPercentage > 60) {
        patterns.push({
            icon: '💼',
            title: 'İş Saatleri Yoğunluğu',
            description: `Anomalilerin %${workHourPercentage}'i iş saatlerinde (09:00-18:00) gerçekleşiyor. Bu, yüksek kullanım veya sistem yükü ile ilişkili olabilir.`
        });
    }
    
    // Gece saatleri analizi (00:00 - 06:00)
    const nightHours = [0, 1, 2, 3, 4, 5];
    const nightHourAnomalies = nightHours.reduce((sum, h) => sum + (hourlyData[h] || 0), 0);
    const nightHourPercentage = totalAnomalies > 0 ? (nightHourAnomalies / totalAnomalies * 100).toFixed(1) : 0;
    
    if (nightHourPercentage > 30) {
        patterns.push({
            icon: '🌙',
            title: 'Gece Aktivitesi',
            description: `Anomalilerin %${nightHourPercentage}'i gece saatlerinde. Bakım işlemleri, batch job'lar veya anormal aktivite olabilir.`
        });
    }
    
    // Peak saat analizi
    if (peakHours.length > 0) {
        const consecutivePeaks = findConsecutiveHours(peakHours);
        if (consecutivePeaks.length > 0) {
            patterns.push({
                icon: '📈',
                title: 'Ardışık Yoğun Saatler',
                description: `${consecutivePeaks.map(range => `${range[0]}:00-${range[1]}:00`).join(', ')} arasında sürekli yüksek anomali. Sistemik bir sorun olabilir.`
            });
        }
    }
    
    // Düzenli pattern kontrolü
    const hourlyPattern = detectRegularPattern(hourlyData);
    if (hourlyPattern) {
        patterns.push({
            icon: '🔄',
            title: hourlyPattern.title,
            description: hourlyPattern.description
        });
    }
    
    return patterns;
}

// Ardışık saatleri bulma
function findConsecutiveHours(hours) {
    if (hours.length === 0) return [];
    
    const sorted = [...hours].sort((a, b) => a - b);
    const ranges = [];
    let start = sorted[0];
    let end = sorted[0];
    
    for (let i = 1; i < sorted.length; i++) {
        if (sorted[i] === end + 1) {
            end = sorted[i];
        } else {
            if (end - start >= 2) {
                ranges.push([start, end]);
            }
            start = sorted[i];
            end = sorted[i];
        }
    }
    
    if (end - start >= 2) {
        ranges.push([start, end]);
    }
    
    return ranges;
}

// Düzenli pattern tespiti
function detectRegularPattern(hourlyData) {
    const hours = Object.keys(hourlyData).map(Number);
    
    // Her N saatte bir pattern kontrolü
    for (let interval of [2, 3, 4, 6, 8, 12]) {
        let patternFound = true;
        let patternHours = [];
        
        for (let start = 0; start < interval; start++) {
            let hasAnomaly = false;
            for (let h = start; h < 24; h += interval) {
                if (hourlyData[h] && hourlyData[h] > 0) {
                    hasAnomaly = true;
                    patternHours.push(h);
                }
            }
            
            if (hasAnomaly && patternHours.length >= 3) {
                return {
                    title: `${interval} Saatlik Döngü`,
                    description: `Anomaliler yaklaşık her ${interval} saatte bir tekrarlanıyor (${patternHours.slice(0, 3).map(h => h + ':00').join(', ')}...). Zamanlanmış işlemler veya döngüsel sorunlar olabilir.`
                };
            }
        }
    }
    
    return null;
}


/**
 * ML Visualization Event Listeners Ekle
 */
function attachMLVisualizationListeners() {
    // Heatmap hover effects
    document.querySelectorAll('.heatmap-cell').forEach(cell => {
        cell.addEventListener('mouseenter', function() {
            this.querySelector('.cell-tooltip').style.display = 'block';
        });
        cell.addEventListener('mouseleave', function() {
            this.querySelector('.cell-tooltip').style.display = 'none';
        });
    });
    
    // Component card clicks
    document.querySelectorAll('.component-card').forEach(card => {
        card.addEventListener('click', function() {
            const component = this.querySelector('.component-name').textContent;
            showComponentDetails(component);
        });
    });
}
/**
 * Anomaly Score Distribution Render Et
 */
function renderAnomalyScoreDistribution(scoreStats, summary) {
    let html = '<div class="anomaly-score-distribution-section">';
    html += '<h3>📊 Anomaly Score Distribution</h3>';
    html += '<div class="score-distribution-container">';
    
    // Score distribution visualization
    html += '<div class="score-distribution-chart">';
    
    // Min-Max range bar
    html += '<div class="distribution-bar">';
    html += `<div class="distribution-segment normal" style="width: 70%">
                <span class="segment-label">Normal Range</span>
             </div>`;
    html += `<div class="distribution-segment warning" style="width: 20%">
                <span class="segment-label">Warning</span>
             </div>`;
    html += `<div class="distribution-segment critical" style="width: 10%">
                <span class="segment-label">Critical</span>
             </div>`;
    html += '</div>';
    
    // Score markers
    html += '<div class="score-markers">';
    html += `<div class="marker min" style="left: 0%">
                <span class="marker-value">${scoreStats.min?.toFixed(3) || 'N/A'}</span>
                <span class="marker-label">Min</span>
             </div>`;
    html += `<div class="marker mean" style="left: 50%">
                <span class="marker-value">${scoreStats.mean?.toFixed(3) || 'N/A'}</span>
                <span class="marker-label">Mean</span>
             </div>`;
    html += `<div class="marker max" style="left: 100%">
                <span class="marker-value">${scoreStats.max?.toFixed(3) || 'N/A'}</span>
                <span class="marker-label">Max</span>
             </div>`;
    html += '</div>';
    
    html += '</div>';
    
    // Distribution stats
    html += '<div class="distribution-stats">';
    html += `<div class="dist-stat">
                <span class="dist-stat-label">Threshold</span>
                <span class="dist-stat-value">0.03 (3%)</span>
             </div>`;
    html += `<div class="dist-stat">
                <span class="dist-stat-label">Detected Anomalies</span>
                <span class="dist-stat-value">${summary.n_anomalies || 0}</span>
             </div>`;
    html += `<div class="dist-stat">
                <span class="dist-stat-label">Detection Rate</span>
                <span class="dist-stat-value">%${summary.anomaly_rate?.toFixed(2) || 0}</span>
             </div>`;
    html += '</div>';
    
    html += '</div></div>';
    return html;
}
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

/**
 * Anomali Verisini İndir
 */
function exportAnomalyData(historyId) {
    const item = queryHistory.find(h => h.id === historyId);
    if (!item || !item.childResult) {
        showNotification('İndirilecek veri bulunamadı', 'warning');
        return;
    }
    
    const exportData = {
        query: item.query,
        timestamp: item.timestamp,
        analysis_result: item.childResult,
        ml_data: item.childResult.sonuç?.data || item.childResult.sonuç,
        ai_explanation: item.childResult.sonuç?.ai_explanation || item.childResult.ai_explanation
    };
    
    const dataStr = JSON.stringify(exportData, null, 2);
    const dataUri = 'data:application/json;charset=utf-8,'+ encodeURIComponent(dataStr);
    
    const exportFileDefaultName = `anomaly_analysis_${item.id}_${new Date().toISOString().split('T')[0]}.json`;
    
    const linkElement = document.createElement('a');
    linkElement.setAttribute('href', dataUri);
    linkElement.setAttribute('download', exportFileDefaultName);
    linkElement.click();
    
    showNotification('Analiz verisi indirildi', 'success');
}

// Global fonksiyon tanımlamaları
window.showFullVisualizationModal = showFullVisualizationModal;
window.exportAnomalyData = exportAnomalyData;

/**
 * Critical Anomalies Table Render Et
 */
function renderCriticalAnomaliesTable(criticalAnomalies) {
    let html = '<div class="critical-anomalies-table-section">';
    html += '<h3>🚨 Kritik Anomaliler - Detaylı Liste</h3>';
    
    html += '<div class="critical-table-container">';
    html += '<table class="critical-anomalies-table">';
    html += '<thead>';
    html += '<tr>';
    html += '<th>Rank</th>';
    html += '<th>Score</th>';
    html += '<th>Timestamp</th>';
    html += '<th>Component</th>';
    html += '<th>Severity</th>';
    html += '<th>Message</th>';
    html += '<th>Actions</th>';
    html += '</tr>';
    html += '</thead>';
    html += '<tbody>';
    
    criticalAnomalies.forEach((anomaly, index) => {
        const score = anomaly.anomaly_score || anomaly.score || 0;
        const scoreClass = score < -0.5 ? 'critical' : 
                          score < -0.3 ? 'high' : 'medium';
        
        html += `<tr class="anomaly-row ${scoreClass}">`;
        html += `<td class="rank">#${index + 1}</td>`;
        html += `<td class="score">
                    <span class="score-badge ${scoreClass}">${score.toFixed(4)}</span>
                 </td>`;
        html += `<td class="timestamp">${formatTimestamp(anomaly.timestamp)}</td>`;
        html += `<td class="component">
                    <span class="component-badge">${anomaly.component || 'N/A'}</span>
                 </td>`;
        html += `<td class="severity">
                    <span class="severity-badge ${anomaly.severity?.toLowerCase() || 'info'}">
                        ${anomaly.severity || 'INFO'}
                    </span>
                 </td>`;
        html += `<td class="message">
                    ${anomaly.message && anomaly.message.length > 300 ? `
                        <div class="message-expandable">
                            <div class="message-preview">
                                <pre>${escapeHtml(anomaly.message.substring(0, 300))}...</pre>
                            </div>
                            <div class="message-full" style="display:none">
                                <pre>${escapeHtml(anomaly.message)}</pre>
                            </div>
                            <button class="btn-expand" onclick="toggleMessageExpand(this)">Detay</button>
                        </div>
                    ` : `
                        <pre class="message-full">${escapeHtml(anomaly.message || '')}</pre>
                    `}
                 </td>`;
        html += `<td class="actions">
                    <button class="btn-investigate" onclick="investigateAnomaly(${anomaly.index || index})">
                        🔍 İncele
                    </button>
                 </td>`;
        html += '</tr>';
    });
    
    html += '</tbody>';
    html += '</table>';
    html += '</div>';
    
    html += '</div>';
    return html;
}

/**
 * ML Insights Summary Render Et
 */
function renderMLInsightsSummary(mlData) {
    let html = '<div class="ml-insights-summary">';
    html += '<h3>💡 ML Model Insights</h3>';
    html += '<div class="insights-grid">';
    
    // Key Insights
    const insights = generateMLInsights(mlData);
    
    insights.forEach(insight => {
        html += `
            <div class="insight-card ${insight.type}">
                <div class="insight-icon">${insight.icon}</div>
                <div class="insight-content">
                    <h4>${insight.title}</h4>
                    <p>${insight.description}</p>
                    ${insight.recommendation ? `<div class="insight-recommendation">
                        <strong>Öneri:</strong> ${insight.recommendation}
                    </div>` : ''}
                </div>
            </div>
        `;
    });
    
    html += '</div></div>';
    return html;
}

/**
 * Security Alerts Dashboard Render Et - SADELEŞTİRİLMİŞ VERSİYON
 */
function renderSecurityAlertsDashboard(securityAlerts) {
    let html = '<div class="security-alerts-unified">';
    html += '<h3>🚨 Security & Critical Alerts</h3>';
    
    // Alert type bilgileri
    const alertTypeInfo = {
        'drop_operations': { 
            icon: '🗑️', 
            label: 'DROP Operations', 
            description: 'Veritabanı veya koleksiyon silme işlemleri. Veri kaybına neden olabilir.',
            priority: 10
        },
        'out_of_memory': { 
            icon: '💾', 
            label: 'Out of Memory', 
            description: 'Bellek yetersizliği hataları. Performans sorunlarına ve crash\'lere neden olabilir.',
            priority: 9
        },
        'fatal_errors': { 
            icon: '💀', 
            label: 'Fatal Errors', 
            description: 'Kritik sistem hataları. Acil müdahale gerektirir.',
            priority: 8
        },
        'assertions': { 
            icon: '❗', 
            label: 'Assertion Errors', 
            description: 'MongoDB internal assertion hataları. Yazılım hatası veya veri tutarsızlığı göstergesi.',
            priority: 7
        },
        'shutdowns': { 
            icon: '⏹️', 
            label: 'Shutdown Events', 
            description: 'MongoDB servis kapanma olayları. Planlı/plansız kontrol edilmeli.',
            priority: 6
        },
        'restarts': { 
            icon: '🔄', 
            label: 'Service Restarts', 
            description: 'Servis yeniden başlatma olayları. Sık tekrarlanıyorsa sorun var demektir.',
            priority: 5
        },
        'memory_limits': { 
            icon: '📊', 
            label: 'Memory Limit Exceeded', 
            description: 'WiredTiger cache limit aşımları. Cache boyutu ayarlanmalı.',
            priority: 4
        }
    };
    
    // Toplam alert sayısını hesapla
    const totalAlerts = Object.values(securityAlerts).reduce((sum, alert) => sum + (alert.count || 0), 0);
    const criticalAlerts = Object.entries(securityAlerts)
        .filter(([type, data]) => data.count > 0 && alertTypeInfo[type]?.priority >= 8)
        .reduce((sum, [, data]) => sum + data.count, 0);
    
    // Özet banner
    if (totalAlerts > 0) {
        html += '<div class="alert-summary-banner">';
        html += '<div class="alert-summary-content">';
        
        html += '<div class="alert-total-count">';
        html += `<span>${totalAlerts}</span>`;
        html += '<span class="alert-total-label">Toplam Güvenlik Olayı</span>';
        html += '</div>';
        
        html += '<div class="alert-critical-info">';
        if (criticalAlerts > 0) {
            html += '<div class="critical-stat">';
            html += `<div class="critical-stat-value">${criticalAlerts}</div>`;
            html += '<div class="critical-stat-label">Kritik</div>';
            html += '</div>';
        }
        
        const uniqueTypes = Object.entries(securityAlerts)
            .filter(([, data]) => data.count > 0).length;
        
        html += '<div class="critical-stat">';
        html += `<div class="critical-stat-value">${uniqueTypes}</div>`;
        html += '<div class="critical-stat-label">Farklı Tip</div>';
        html += '</div>';
        html += '</div>';
        
        html += '</div>';
        html += '</div>';
    }
    
    // Alert listesi - önceliğe göre sıralı
    const sortedAlerts = Object.entries(securityAlerts)
        .map(([type, data]) => ({
            type,
            data,
            info: alertTypeInfo[type] || { icon: '⚠️', label: type, priority: 0 }
        }))
        .sort((a, b) => {
            // Önce count'a göre, sonra priority'ye göre sırala
            if (b.data.count !== a.data.count) {
                return b.data.count - a.data.count;
            }
            return b.info.priority - a.info.priority;
        });
    
    if (sortedAlerts.some(alert => alert.data.count > 0)) {
        html += '<div class="priority-alert-list">';
        
        sortedAlerts.forEach(({ type, data, info }) => {
            const count = data.count || 0;
            
            // Severity belirleme
            let severityClass = 'clear';
            if (count > 0) {
                if (info.priority >= 8) severityClass = 'critical';
                else if (info.priority >= 6) severityClass = 'high';
                else if (info.priority >= 4) severityClass = 'medium';
                else severityClass = 'low';
            }
            
            html += `
                <div class="security-alert-item ${severityClass}">
                    <div class="alert-content-grid">
                        <div class="alert-icon-box">
                            ${info.icon}
                        </div>
                        <div class="alert-main-info">
                            <div class="alert-type-name">${info.label}</div>
                            <div class="alert-description">${info.description}</div>
                            <div class="alert-impact">
                                ${count > 0 ? `
                                    <span class="impact-badge count">
                                        📍 ${count} olay tespit edildi
                                    </span>
                                ` : ''}
                                ${data.indices && data.indices.length > 0 ? `
                                    <span class="impact-badge indices">
                                        📑 ${data.indices.length} log index'i etkilendi
                                    </span>
                                ` : ''}
                            </div>
                            ${data.indices && data.indices.length > 0 && count > 0 ? `
                                <div class="indices-preview">
                                    <div class="indices-label">Etkilenen Index'ler:</div>
                                    <div class="indices-list">
                                        ${data.indices.slice(0, 5).map(idx => 
                                            `<span class="index-chip">${idx}</span>`
                                        ).join('')}
                                        ${data.indices.length > 5 ? 
                                            `<span class="index-chip">+${data.indices.length - 5} daha</span>` : ''}
                                    </div>
                                </div>
                            ` : ''}
                        </div>
                        <div class="alert-count-display">
                            <div class="alert-count-number">${count}</div>
                            <div class="alert-count-label">${count === 1 ? 'Olay' : 'Olay'}</div>
                        </div>
                        ${count > 0 ? `
                            <div class="alert-item-actions">
                                <button class="alert-action-btn" onclick="investigateAlertType('${type}')">
                                    🔍 İncele
                                </button>
                                <button class="alert-action-btn" onclick="showAlertTimeline('${type}')">
                                    📅 Timeline
                                </button>
                            </div>
                        ` : ''}
                    </div>
                </div>
            `;
        });
        
        html += '</div>';
        
        // Öneriler bölümü
        if (totalAlerts > 0) {
            html += '<div class="alert-recommendations">';
            html += '<div class="recommendations-title">💡 Öneriler</div>';
            html += '<div class="recommendation-list">';
            
            if (criticalAlerts > 0) {
                html += `
                    <div class="recommendation-item">
                        <div class="recommendation-icon">🚨</div>
                        <div class="recommendation-text">
                            ${criticalAlerts} kritik olay tespit edildi. Sistem loglarını detaylı inceleyip acil aksiyon alın.
                        </div>
                    </div>
                `;
            }
            
            if (securityAlerts.drop_operations?.count > 0) {
                html += `
                    <div class="recommendation-item">
                        <div class="recommendation-icon">🔒</div>
                        <div class="recommendation-text">
                            DROP operasyonları tespit edildi. Yetkisiz erişim kontrolü yapın ve audit log'ları inceleyin.
                        </div>
                    </div>
                `;
            }
            
            if (securityAlerts.out_of_memory?.count > 0 || securityAlerts.memory_limits?.count > 0) {
                html += `
                    <div class="recommendation-item">
                        <div class="recommendation-icon">💾</div>
                        <div class="recommendation-text">
                            Bellek sorunları tespit edildi. Working set boyutunu kontrol edin ve gerekirse bellek artırımı yapın.
                        </div>
                    </div>
                `;
            }
            
            if (securityAlerts.restarts?.count > 3) {
                html += `
                    <div class="recommendation-item">
                        <div class="recommendation-icon">🔄</div>
                        <div class="recommendation-text">
                            Sık servis yeniden başlatması tespit edildi. Sistem stabilitesini kontrol edin.
                        </div>
                    </div>
                `;
            }
            
            html += '</div>';
            html += '</div>';
        }
    } else {
        // Hiç alert yoksa
        html += '<div class="no-alerts-state">';
        html += '<div class="no-alerts-icon">✅</div>';
        html += '<div class="no-alerts-title">Güvenlik Olayı Tespit Edilmedi</div>';
        html += '<div class="no-alerts-message">Analiz edilen log\'larda kritik güvenlik olayı bulunmamaktadır.</div>';
        html += '</div>';
    }
    
    html += '</div>';
    return html;
}

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

// Yardımcı fonksiyonlar
window.investigateAlertType = function(alertType) {
    console.log('Investigating alert type:', alertType);
    closeModal();
    showNotification(`${alertType} için detaylı analiz başlatılıyor...`, 'info');
};

window.exportAlertData = function(alertType) {
    console.log('Exporting alert data for:', alertType);
    showNotification('Alert verisi indiriliyor...', 'success');
};

/**
 * Anomali görünüm modunu değiştir
 */
window.toggleViewMode = function(mode) {
    const resultsSection = document.getElementById('resultSection');
    const anomalySection = document.querySelector('.critical-anomalies-section');
    
    // Tüm modları temizle
    resultsSection.classList.remove('compact-mode', 'expanded-mode', 'fullscreen-mode');
    
    // Seçilen modu ekle
    switch(mode) {
        case 'compact':
            resultsSection.classList.add('compact-mode');
            break;
        case 'expanded':
            resultsSection.classList.add('expanded-mode');
            break;
        case 'fullscreen':
            resultsSection.classList.add('fullscreen-mode');
            // Tam ekran için scroll
            resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
            break;
    }
    
    // Aktif butonu güncelle
    document.querySelectorAll('.btn-view-mode').forEach(btn => {
        btn.classList.remove('active');
        if (btn.textContent.toLowerCase().includes(mode.toLowerCase()) || 
            (mode === 'fullscreen' && btn.textContent.includes('Tam Ekran'))) {
            btn.classList.add('active');
        }
    });
    
    // Kullanıcı tercihini kaydet
    localStorage.setItem('anomalyViewMode', mode);
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

/**
 * Analysis Actions Render Et
 */
function renderAnalysisActions() {
    return ''; // Zaten displayAnomalyResults içinde action butonları var
}

/**
 * Timestamp Formatla
 */
function formatTimestamp(timestamp) {
    if (!timestamp) return 'N/A';
    const date = new Date(timestamp);
    return date.toLocaleString('tr-TR', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
}

/**
 * ML Insights Oluştur
 */
function generateMLInsights(mlData) {
    const insights = [];
    const summary = mlData.summary || {};
    
    // Anomaly rate insight
    if (summary.anomaly_rate > 5) {
        insights.push({
            type: 'critical',
            icon: '🚨',
            title: 'Yüksek Anomali Oranı',
            description: `Sistem %${summary.anomaly_rate.toFixed(1)} anomali oranı ile normal üstü davranış gösteriyor.`,
            recommendation: 'Sistem loglarını detaylı inceleyip, altyapı değişikliklerini kontrol edin.'
        });
    }
    
    // Component insight
    const criticalComponents = Object.entries(mlData.component_analysis || {})
        .filter(([,stats]) => stats.anomaly_rate > 20);
    
    if (criticalComponents.length > 0) {
        insights.push({
            type: 'warning',
            icon: '⚠️',
            title: 'Kritik Component\'ler',
            description: `${criticalComponents.length} component %20\'nin üzerinde anomali oranına sahip.`,
            recommendation: 'Bu component\'lerin konfigürasyonunu ve performansını gözden geçirin.'
        });
    }
    
    // Temporal insight
    if (mlData.temporal_analysis?.peak_hours?.length > 0) {
        const peakHours = mlData.temporal_analysis.peak_hours;
        insights.push({
            type: 'info',
            icon: '⏰',
            title: 'Zamansal Pattern',
            description: `Anomaliler özellikle saat ${peakHours.join(', ')} arasında yoğunlaşıyor.`,
            recommendation: 'Bu saatlerdeki planned job\'ları ve yük dağılımını kontrol edin.'
        });
    }
    
    // Score distribution insight
    if (mlData.anomaly_score_stats?.mean > 0.5) {
        insights.push({
            type: 'warning',
            icon: '📊',
            title: 'Yüksek Ortalama Anomali Skoru',
            description: `Ortalama anomali skoru ${mlData.anomaly_score_stats.mean.toFixed(3)} ile yüksek seviyelerde.`,
            recommendation: 'Isolation Forest model parametrelerini gözden geçirin veya yeniden eğitin.'
        });
    }
    
    return insights;
}

/**
 * Severity Distribution Kompakt Liste
 */
function renderSeverityDistribution(distribution) {
    let html = '<div class="severity-distribution-compact">';
    html += '<h3>🎯 Anomali Kritiklik Dağılımı</h3>';
    html += '<div class="severity-list">';
    
    const levels = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'];
    const colors = {
        'CRITICAL': '#e74c3c',
        'HIGH': '#e67e22',
        'MEDIUM': '#f39c12',
        'LOW': '#3498db',
        'INFO': '#95a5a6'
    };
    
    const levelNames = {
        'CRITICAL': 'Kritik',
        'HIGH': 'Yüksek',
        'MEDIUM': 'Orta',
        'LOW': 'Düşük',
        'INFO': 'Bilgi'
    };
    
    const totalAnomalies = Object.values(distribution).reduce((a, b) => a + b, 0);
    
    levels.forEach(level => {
        const count = distribution[level] || 0;
        const percentage = totalAnomalies > 0 ? (count / totalAnomalies * 100) : 0;
        
        html += `
            <div class="severity-list-item">
                <div class="severity-list-left">
                    <span class="severity-badge ${level.toLowerCase()}">${level}</span>
                    <span class="severity-label">${levelNames[level]}</span>
                </div>
                <div class="severity-list-right">
                    <div class="severity-bar-mini">
                        <div class="severity-bar-mini-fill" 
                             style="background-color: ${colors[level]}; width: ${percentage}%"></div>
                    </div>
                    <span class="severity-count-compact">${count}</span>
                    <span class="severity-percent-compact">%${percentage.toFixed(1)}</span>
                </div>
            </div>
        `;
    });
    
    // Toplam satırı
    html += `
        <div class="severity-list-item severity-total-row">
            <div class="severity-list-left">
                <strong>TOPLAM</strong>
            </div>
            <div class="severity-list-right">
                <strong>${totalAnomalies} anomali</strong>
            </div>
        </div>
    `;
    
    html += '</div>';
    html += '</div>';
    return html;
}

// Global fonksiyonları tanımla
window.toggleMessageExpand = function(button) {
    const messageCell = button.closest('.message');
    const preview = messageCell.querySelector('.message-preview');
    const full = messageCell.querySelector('.message-full');
    
    if (full.style.display === 'none') {
        preview.style.display = 'none';
        full.style.display = 'block';
        button.textContent = 'Gizle';
    } else {
        preview.style.display = 'block';
        full.style.display = 'none';
        button.textContent = 'Detay';
    }
};

window.investigateAnomaly = function(index) {
    console.log('Investigating anomaly at index:', index);
    showNotification('Anomali detaylı analizi başlatılıyor...', 'info');
};

/**
 * Belirli bir anomali chunk'ını yükle
 */
window.loadAnomalyChunk = async function(analysisId, chunkIndex) {
    if (!analysisId) {
        showNotification('Analysis ID bulunamadı', 'error');
        return;
    }
    
    // Loading göster
    showLoader(true);
    elements.resultSection.style.display = 'block';
    elements.resultContent.innerHTML = '<div class="loading-chunk">Chunk yükleniyor...</div>';
    
    try {
        const response = await fetch('/api/get-anomaly-chunk', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                analysis_id: analysisId,
                chunk_index: parseInt(chunkIndex),
                api_key: apiKey
            })
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const result = await response.json();
        
        if (result.status === 'success') {
            // Yeni chunk'ı göster
            displayChatAnomalyResult({
                status: 'success',
                ai_response: result.ai_response,
                chunk_info: result.chunk_info,
                chunk_index: result.chunk_index,
                total_chunks: result.total_chunks,
                anomalies_in_chunk: result.anomalies_in_chunk,
                total_anomalies: result.total_anomalies,
                has_next: result.has_next,
                has_previous: result.has_previous
            }, `Chunk ${result.chunk_index + 1}/${result.total_chunks} gösteriliyor`);
            
            // Sayfayı yukarı kaydır
            elements.resultSection.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            
            showNotification(`Chunk ${result.chunk_index + 1}/${result.total_chunks} yüklendi`, 'success');
        } else {
            throw new Error(result.error || 'Chunk yüklenemedi');
        }
        
    } catch (error) {
        console.error('Chunk yükleme hatası:', error);
        showNotification('Chunk yüklenirken hata oluştu: ' + error.message, 'error');
        elements.resultContent.innerHTML = '<div class="error-message">Chunk yüklenemedi. Lütfen tekrar deneyin.</div>';
    } finally {
        showLoader(false);
    }
};

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

// Mesaj expand/collapse fonksiyonu
window.toggleMessageExpand = function(button) {
    const container = button.closest('.message-expandable, .message-text, td');
    const preview = container.querySelector('.message-preview');
    const fullMsg = container.querySelector('.message-full');
    
    if (!preview || !fullMsg) {
        console.error('Preview or full message element not found');
        return;
    }
    
    if (fullMsg.style.display === 'none' || fullMsg.style.display === '') {
        preview.style.display = 'none';
        fullMsg.style.display = 'block';
        button.textContent = 'Gizle';
        button.classList.add('expanded');
    } else {
        preview.style.display = 'block';
        fullMsg.style.display = 'none';
        button.textContent = button.textContent === 'Gizle' ? 'Detay' : 'Tam Mesajı Göster';
        button.classList.remove('expanded');
    }
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
 * YENİ: Kritik anomali mesajları toggle fonksiyonu
 */
function toggleCriticalAnomalyMessages() {
    const toggle = document.getElementById('criticalMessageToggle');
    const isFormatted = toggle.checked;
    
    // Tüm critical-item'ları bul
    const criticalItems = document.querySelectorAll('.enhanced-anomaly-item');
    
    criticalItems.forEach(item => {
        const originalMsg = item.querySelector('.original-message');
        const formattedMsg = item.querySelector('.formatted-message');
        
        if (originalMsg && formattedMsg) {
            if (isFormatted) {
                originalMsg.style.display = 'none';
                formattedMsg.style.display = 'block';
            } else {
                originalMsg.style.display = 'block';
                formattedMsg.style.display = 'none';
            }
        }
    });
    
    // Storage'a tercihi kaydet
    localStorage.setItem('showFormattedMessages', isFormatted.toString());
}

/**
 * YENİ: Detaylı anomali listesi toggle fonksiyonu
 */
function toggleDetailedAnomalyMessages() {
    const toggle = document.getElementById('detailedMessageToggle');
    const isFormatted = toggle.checked;
    
    // Tüm detailed anomaly item'ları bul
    const detailedItems = document.querySelectorAll('.detailed-anomaly-item');
    
    detailedItems.forEach(item => {
        const originalMsg = item.querySelector('.original-message');
        const formattedMsg = item.querySelector('.formatted-message');
        
        if (originalMsg && formattedMsg) {
            if (isFormatted) {
                originalMsg.style.display = 'none';
                formattedMsg.style.display = 'block';
            } else {
                originalMsg.style.display = 'block';
                formattedMsg.style.display = 'none';
            }
        }
    });
    
    // Storage'a tercihi kaydet
    localStorage.setItem('showFormattedMessages', isFormatted.toString());
}

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

/**
 * MongoDB'den anomali geçmişini yükle
 */
async function loadAnomalyHistoryFromMongoDB(filters = {}) {
    try {
        const params = new URLSearchParams({
            api_key: apiKey,
            ...filters
        });
        
        const response = await fetch(`${API_ENDPOINTS.anomalyHistory}?${params}`);
        
        if (response.ok) {
            const data = await response.json();
            console.log(`Loaded ${data.count} anomaly records from MongoDB`);
            return data.history;
        }
    } catch (error) {
        console.error('Error loading anomaly history from MongoDB:', error);
    }
    return [];
}

/**
 * Storage istatistiklerini göster
 */
async function showStorageStatistics() {
    try {
        const response = await fetch(`${API_ENDPOINTS.storageStats}?api_key=${apiKey}&days=30`);
        
        if (response.ok) {
            const data = await response.json();
            const stats = data.statistics;
            
            let modalContent = '<div class="storage-stats-modal">';
            modalContent += '<h3>📊 Storage İstatistikleri (Son 30 Gün)</h3>';
            
            // Analysis stats
            if (stats.analysis_stats) {
                modalContent += '<div class="stats-section">';
                modalContent += '<h4>📈 Analiz İstatistikleri</h4>';
                modalContent += '<div class="stats-grid">';
                modalContent += `<div class="stat-card">
                    <div class="stat-value">${stats.analysis_stats.total_analyses || 0}</div>
                    <div class="stat-label">Toplam Analiz</div>
                </div>`;
                modalContent += `<div class="stat-card">
                    <div class="stat-value">${stats.analysis_stats.total_anomalies || 0}</div>
                    <div class="stat-label">Tespit Edilen Anomali</div>
                </div>`;
                modalContent += `<div class="stat-card">
                    <div class="stat-value">${stats.analysis_stats.avg_anomaly_rate || 0}%</div>
                    <div class="stat-label">Ortalama Anomali Oranı</div>
                </div>`;
                modalContent += '</div></div>';
            }
            
            // Storage stats
            if (stats.storage_stats) {
                modalContent += '<div class="stats-section">';
                modalContent += '<h4>💾 Storage Kullanımı</h4>';
                modalContent += '<div class="stats-grid">';
                modalContent += `<div class="stat-card">
                    <div class="stat-value">${stats.storage_stats.total_size_mb || 0} MB</div>
                    <div class="stat-label">Toplam Boyut</div>
                </div>`;
                modalContent += `<div class="stat-card">
                    <div class="stat-value">${stats.storage_stats.file_counts?.exports || 0}</div>
                    <div class="stat-label">Export Dosyası</div>
                </div>`;
                modalContent += `<div class="stat-card">
                    <div class="stat-value">${stats.storage_stats.file_counts?.models || 0}</div>
                    <div class="stat-label">Model Versiyonu</div>
                </div>`;
                modalContent += '</div></div>';
            }
            
            modalContent += '</div>';
            showModal('Storage İstatistikleri', modalContent);
        }
    } catch (error) {
        console.error('Error loading storage statistics:', error);
        showNotification('Storage istatistikleri yüklenemedi', 'error');
    }
}

/**
 * Model registry'yi göster
 */
async function showModelRegistry() {
    try {
        const response = await fetch(`${API_ENDPOINTS.modelRegistry}?api_key=${apiKey}`);
        
        if (response.ok) {
            const data = await response.json();
            
            let modalContent = '<div class="model-registry-modal">';
            modalContent += '<h3>🤖 Model Registry</h3>';
            
            if (data.models && data.models.length > 0) {
                modalContent += '<table class="model-table">';
                modalContent += '<thead><tr>';
                modalContent += '<th>Version</th>';
                modalContent += '<th>Type</th>';
                modalContent += '<th>Features</th>';
                modalContent += '<th>Created</th>';
                modalContent += '<th>Status</th>';
                modalContent += '<th>Actions</th>';
                modalContent += '</tr></thead><tbody>';
                
                data.models.forEach(model => {
                    const isActive = model.is_active;
                    const statusClass = isActive ? 'active' : 'inactive';
                    const statusText = isActive ? 'Active' : 'Inactive';
                    
                    modalContent += '<tr>';
                    modalContent += `<td><strong>${model.version}</strong></td>`;
                    modalContent += `<td>${model.model_type}</td>`;
                    modalContent += `<td>${model.n_features || 0}</td>`;
                    modalContent += `<td>${new Date(model.created_at).toLocaleDateString('tr-TR')}</td>`;
                    modalContent += `<td><span class="status-badge ${statusClass}">${statusText}</span></td>`;
                    modalContent += '<td>';
                    if (!isActive) {
                        modalContent += `<button class="btn-small" onclick="activateModel('${model.version}')">Activate</button>`;
                    }
                    modalContent += '</td>';
                    modalContent += '</tr>';
                });
                
                modalContent += '</tbody></table>';
            } else {
                modalContent += '<p>Henüz kayıtlı model bulunmuyor.</p>';
            }
            
            modalContent += '</div>';
            showModal('Model Registry', modalContent);
        }
    } catch (error) {
        console.error('Error loading model registry:', error);
        showNotification('Model registry yüklenemedi', 'error');
    }
}

/**
 * Model'i aktif et
 */
async function activateModel(versionId) {
    if (!confirm(`${versionId} versiyonunu aktif model olarak ayarlamak istiyor musunuz?`)) {
        return;
    }
    
    try {
        const response = await fetch(`${API_ENDPOINTS.modelRegistry}/${versionId}/activate`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ api_key: apiKey })
        });
        
        if (response.ok) {
            showNotification('Model başarıyla aktif edildi', 'success');
            closeModal();
            // Registry'yi yeniden yükle
            setTimeout(() => showModelRegistry(), 500);
        } else {
            throw new Error('Model aktif edilemedi');
        }
    } catch (error) {
        console.error('Error activating model:', error);
        showNotification('Model aktif edilirken hata oluştu', 'error');
    }
}

/**
 * Storage cleanup işlemi
 */
async function performStorageCleanup() {
    if (!confirm('Eski storage verilerini temizlemek istediğinizden emin misiniz?')) {
        return;
    }
    
    try {
        const response = await fetch(`${API_ENDPOINTS.storageCleanup}?api_key=${apiKey}`, {
            method: 'POST'
        });
        
        if (response.ok) {
            const data = await response.json();
            const stats = data.cleanup_stats;
            
            showNotification(
                `Temizlik tamamlandı: ${stats.files_deleted} dosya silindi, ${stats.space_freed_mb.toFixed(2)} MB alan boşaltıldı`,
                'success'
            );
        }
    } catch (error) {
        console.error('Error during storage cleanup:', error);
        showNotification('Temizlik işlemi başarısız oldu', 'error');
    }
}

// Global fonksiyonları window'a ekle
window.activateModel = activateModel;
window.showStorageStatistics = showStorageStatistics;
window.showModelRegistry = showModelRegistry;
window.performStorageCleanup = performStorageCleanup;

/**
 * Daha fazla kritik anomali göster (Pagination)
 */
function loadMoreCriticalAnomalies() {
    if (!window.allCriticalAnomalies || !window.currentlyShownCount) {
        console.error('Anomaly data not available for pagination');
        return;
    }
    
    const nextBatch = 20; // Bir seferde 20 daha göster
    const currentCount = window.currentlyShownCount;
    const totalCount = window.allCriticalAnomalies.length;
    
    // Yeni gösterilecek anomaliler
    const startIndex = currentCount;
    const endIndex = Math.min(currentCount + nextBatch, totalCount);
    const newAnomalies = window.allCriticalAnomalies.slice(startIndex, endIndex);
    
    // Mevcut listeye yeni anomalileri ekle
    const anomalyList = document.getElementById('criticalAnomaliesList');
    if (!anomalyList) {
        console.error('Anomaly list container not found');
        return;
    }
    
    let html = '';
    newAnomalies.forEach(anomaly => {
        const severityColor = anomaly.severity_color || '#e74c3c';
        const severityLevel = anomaly.severity_level || 'HIGH';
        const severityScore = anomaly.severity_score || 0;
        
        const fullMessage = anomaly.message || 'No message available';
        const isLongMessage = fullMessage.length > 500;
        
        html += `
            <div class="critical-anomaly-card" style="--severity-color: ${severityColor}">
                <div class="anomaly-header-with-severity">
                    <div class="anomaly-info">
                        <span class="anomaly-time">${new Date(anomaly.timestamp).toLocaleString('tr-TR')}</span>
                        <span class="severity-badge ${severityLevel.toLowerCase()}">${severityLevel}</span>
                        <span class="severity-score-inline">${severityScore}/100</span>
                        ${anomaly.component ? `<span class="component-badge">${anomaly.component}</span>` : ''}
                    </div>
                </div>
                <div class="anomaly-message">
                    ${isLongMessage ? `
                        <div class="message-preview">
                            <pre class="log-message-pre">${escapeHtml(fullMessage.substring(0, 500))}...</pre>
                        </div>
                        <div class="message-full" style="display: none;">
                            <pre class="log-message-pre">${escapeHtml(fullMessage)}</pre>
                        </div>
                        <button class="btn-expand" onclick="toggleMessageExpand(this)">
                            Tam Mesajı Göster
                        </button>
                    ` : `
                        <pre class="log-message-pre">${escapeHtml(fullMessage)}</pre>
                    `}
                </div>
            </div>
        `;
    });
    
    // Butonu kaldır
    const loadMoreBtn = document.getElementById('loadMoreCriticalBtn');
    if (loadMoreBtn) {
        loadMoreBtn.parentElement.remove();
    }
    
    // Yeni HTML'i ekle
    anomalyList.insertAdjacentHTML('beforeend', html);
    
    // Sayacı güncelle
    window.currentlyShownCount = endIndex;
    
    // Eğer daha fazla varsa yeni buton ekle
    const remainingCount = totalCount - endIndex;
    if (remainingCount > 0) {
        const loadMoreHtml = `
            <div class="load-more-section" style="text-align: center; margin: 20px 0;">
                <button class="btn btn-secondary" onclick="loadMoreCriticalAnomalies()" id="loadMoreCriticalBtn">
                    Daha Fazla Göster (+${remainingCount} anomali)
                </button>
            </div>
        `;
        anomalyList.insertAdjacentHTML('afterend', loadMoreHtml);
    }
    
    console.log(`[DEBUG FRONTEND] Loaded more anomalies: ${startIndex+1}-${endIndex} of ${totalCount}`);
}

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
// DOSYA SONU
// ============================================
// Tüm anomaly render fonksiyonları script-anomaly.js modülünde
// Performance analiz fonksiyonları bu dosyada kalıyor