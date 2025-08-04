// web_ui\static\script.js

/**
 * LC Waikiki MongoDB Assistant - Frontend JavaScript
 * 
 * Bu dosya UI ile backend API arasındaki iletişimi sağlar.
 * Mevcut MongoDB Agent yapısına hiçbir müdahale yapmadan,
 * sadece API çağrıları üzerinden iletişim kurar.
 */

//  web_ui/static/script.js

// Global değişkenler
let apiKey = '';
let isConnected = false;
let selectedDataSource = 'upload';  // Varsayılan veri kaynağı

// Konuşma geçmişi için sabitler
const HISTORY_KEY = 'mongodb_query_history';
const MAX_HISTORY_ITEMS = 50;
let queryHistory = [];

// API endpoints
const API_BASE = window.location.origin;
const API_ENDPOINTS = {
    query: '/api/query',
    status: '/api/status',
    collections: '/api/collections',
    schema: '/api/schema',
    analyzeLog: '/api/analyze-uploaded-log',  // analyzeLog yerine analyze-uploaded-log
    uploadLog: '/api/upload-log',              // YENİ
    uploadedLogs: '/api/uploaded-logs',        // YENİ
    deleteUploadedLog: '/api/uploaded-log',    // YENİ
    mongodbHosts: '/api/mongodb/hosts'         // YENİ
};

// DOM elementleri
const elements = {
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

// Sayfa yüklendiğinde
document.addEventListener('DOMContentLoaded', () => {
    initializeEventListeners();
    checkInitialStatus();
    loadHistory(); // Geçmişi yükle
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
    document.getElementById('collectionsBtn').addEventListener('click', handleCollections);
    document.getElementById('statusBtn').addEventListener('click', handleStatus);
    document.getElementById('clearBtn').addEventListener('click', handleClear);
    
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
    });
    
    // Anomaly Modal içindeki Analizi Başlat butonu  
    document.getElementById('startAnalysisBtn').addEventListener('click', handleAnalyzeLog);
    
    // Refresh hosts button
    document.getElementById('refreshHostsBtn')?.addEventListener('click', loadMongoDBHosts);
    
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
            console.log('Data source changed from', selectedDataSource, 'to', e.target.value); // DEBUG LOG
            selectedDataSource = e.target.value;
            updateSourceInputs(selectedDataSource);
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
            apiKey = key;
            isConnected = true;
            
            console.log('Connection successful, updating UI...'); // DEBUG LOG
            
            // UI'yi güncelle
            elements.mainContent.style.display = 'block';
            elements.apiKeyInput.disabled = true;
            elements.connectBtn.textContent = 'BAĞLANDI';
            elements.connectBtn.classList.add('connected');
            
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
    
    console.log('handleQuery called with query:', query); // DEBUG LOG
        
    // Onay sorgusu kontrolü
    const isConfirmation = window.isConfirmationQuery || false;
    window.isConfirmationQuery = false; // Flag'i resetle
    console.log('handleQuery called with query:', query, 'isConfirmation:', isConfirmation);
    
    if (!query) {
        console.log('Query is empty'); // DEBUG LOG
        showNotification('Lütfen bir sorgu girin', 'warning');
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
        // Onay sorgusu flag'ini global olarak sakla
        window.lastQueryWasConfirmation = isConfirmation;
        const queryBody = {
            query: query,
            api_key: apiKey
        };
        
        console.log('Sending query to API...'); // DEBUG LOG
        
        const response = await fetch(API_ENDPOINTS.query, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(queryBody)
        });
        
        console.log('Query response status:', response.status); // DEBUG LOG
        
        const result = await response.json();
        console.log('Query result:', result); // DEBUG LOG
        
        // YENİ: Onay bekleyen durum kontrolü
        if (result.durum === 'onay_bekliyor') {
            console.log('Confirmation required for anomaly analysis');
            displayConfirmationDialog(result);
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

/**
 * Anomali analizi için onay dialogu göster
 */
function displayConfirmationDialog(result) {
    console.log('Displaying confirmation dialog for anomaly analysis');
    
    // İlk sorguyu geçmişe ekle ve ID'sini sakla
    const parentId = Date.now();
    window.pendingAnomalyQueryId = parentId;
    localStorage.setItem('pendingAnomalyQueryId', parentId);

    console.log('Parent ID set to:', parentId);
    console.log('window.pendingAnomalyQueryId:', window.pendingAnomalyQueryId);

    // Onay bekleyen sorguyu geçmişe ekle
    const historyItem = {
        id: parentId,
        timestamp: new Date().toISOString(),
        query: elements.queryInput.value,
        type: 'anomaly',  // ✅ Her zaman anomaly
        category: 'anomaly', // ✅ Açıkça belirt
        result: result,
        durum: result.durum,
        işlem: 'parametre_onayı',
        isAnomalyParent: true,
        childResultId: null,
        hasResult: false,
        awaitingConfirmation: true,
        originalQuery: elements.queryInput.value // ✅ Orijinal sorguyu sakla
    };

    queryHistory.unshift(historyItem);
    if (queryHistory.length > MAX_HISTORY_ITEMS) {
        queryHistory = queryHistory.slice(0, MAX_HISTORY_ITEMS);
    }
    saveHistory();
    updateHistoryDisplay();

    const confirmationHtml = `
        <div class="confirmation-dialog">
            <div class="confirmation-header">
                <h3>🔍 Anomali Analizi Onayı</h3>
            </div>
            <div class="confirmation-body">
                ${result.açıklama}
            </div>
            <div class="confirmation-actions">
                <button class="btn btn-primary" onclick="confirmAnomalyAnalysis()">
                    ✅ Onayla ve Başlat
                </button>
                <button class="btn btn-secondary" onclick="cancelAnomalyAnalysis()">
                    ❌ İptal Et
                </button>
                <button class="btn btn-info" onclick="modifyAnomalyParameters()">
                    ✏️ Parametreleri Değiştir
                </button>
            </div>
        </div>
    `;
    
    // Sonuç bölümünde göster
    elements.resultSection.style.display = 'block';
    elements.resultContent.innerHTML = confirmationHtml;
    
    // Parametreleri sakla
    window.pendingAnomalyParams = result.sonuç;

}

/**
 * Anomali analizini onayla
 */
async function confirmAnomalyAnalysis() {
    console.log('User confirmed anomaly analysis');
    
    // Onay bekleyen parent'ı güncelle
    if (window.pendingAnomalyQueryId) {
        const parentIndex = queryHistory.findIndex(h => h.id === window.pendingAnomalyQueryId);
        if (parentIndex !== -1) {
            queryHistory[parentIndex].awaitingConfirmation = false;
            queryHistory[parentIndex].durum = 'işleniyor'; // ✅ Ara durum
            saveHistory();
            updateHistoryDisplay();
        }
    }
    
    // Query input'a onay yazısı koy
    elements.queryInput.value = 'evet';
    
    // Onay sorgusu olduğunu işaretle
    window.isConfirmationQuery = true;
    
    // Tekrar sorgu gönder
    await handleQuery();
}

/**
 * Anomali analizini iptal et
 */
async function cancelAnomalyAnalysis() {
    console.log('User cancelled anomaly analysis');
    
    // Query input'a iptal yazısı koy
    elements.queryInput.value = 'hayır';
    
    // İptal de bir onay sorgusu olduğunu işaretle
    window.isConfirmationQuery = true;

    // Tekrar sorgu gönder
    await handleQuery();
}

/**
 * Anomali parametrelerini değiştir
 */
function modifyAnomalyParameters() {
    console.log('User wants to modify parameters');
    
    // Modal'ı aç ve parametreleri doldur
    const anomalyModal = document.getElementById('anomalyModal');
    if (anomalyModal) {
        // OpenSearch veri kaynağını seç
        document.querySelector('input[name="dataSource"][value="opensearch"]').checked = true;
        selectedDataSource = 'opensearch';
        updateSourceInputs('opensearch');
        
        // Eğer sunucu tespit edildiyse, dropdown'da seç
        if (window.pendingAnomalyParams && window.pendingAnomalyParams.server) {
            setTimeout(() => {
                const hostSelect = document.getElementById('mongodbHostSelect');
                if (hostSelect) {
                    // Önce host listesini yükle
                    loadMongoDBHosts().then(() => {
                        // Sonra seçimi yap
                        hostSelect.value = window.pendingAnomalyParams.server;
                    });
                }
            }, 500);
        }
        
        // Zaman aralığını seç
        if (window.pendingAnomalyParams && window.pendingAnomalyParams.time_range) {
            const timeMapping = {
                'last_hour': 'last_24h',
                'last_day': 'last_24h',
                'last_week': 'last_7d',
                'last_month': 'last_30d'
            };
            const radioValue = timeMapping[window.pendingAnomalyParams.time_range] || 'last_24h';
            const timeRadio = document.querySelector(`input[name="modalTimeRange"][value="${radioValue}"]`);
            if (timeRadio) timeRadio.checked = true;
        }
        
        // Modal'ı göster
        anomalyModal.style.display = 'block';
    }
    
    // Sonuç bölümünü temizle
    elements.resultSection.style.display = 'none';
}




/**
 * Parent anomali sorgusunu güncelle
 */
function updateParentAnomalyQuery(result) {
    console.log('Updating parent anomaly query...');
    
    // ID'yi window'dan veya localStorage'dan al
    if (!window.pendingAnomalyQueryId) {
        const storedId = localStorage.getItem('pendingAnomalyQueryId');
        if (storedId) {
            window.pendingAnomalyQueryId = parseInt(storedId);
            console.log('Restored pendingAnomalyQueryId from localStorage:', window.pendingAnomalyQueryId);
        }
    }
    
    if (!window.pendingAnomalyQueryId) {
        // ID yoksa, tamamlanmamış anomali parent'ını bul
        console.log('pendingAnomalyQueryId not found, searching for incomplete parent...');
        const parentIndex = queryHistory.findIndex(h => 
            h.isAnomalyParent === true && 
            h.durum !== 'tamamlandı' &&
            h.durum !== 'iptal'
        );
        
        if (parentIndex !== -1) {
            const parent = queryHistory[parentIndex];
            // Parent'ı güncelle
            parent.childResult = result;
            parent.hasResult = true;
            parent.durum = 'tamamlandı';
            parent.işlem = 'anomaly_analysis_completed';
            parent.completedAt = new Date().toISOString();
            parent.executionTime = Date.now() - parent.id;
            
            console.log('Parent updated successfully (by search):', parent);
            
            saveHistory();
            updateHistoryDisplay();
            
            // Detayı otomatik göster
            setTimeout(() => {
                showHistoryDetail(parent.id);
            }, 100);
        }
    } else {
        // ID varsa normal güncelleme
        const parentIndex = queryHistory.findIndex(h => h.id === window.pendingAnomalyQueryId);
        if (parentIndex !== -1) {
            const parent = queryHistory[parentIndex];
            parent.childResult = result;
            parent.hasResult = true;
            parent.durum = 'tamamlandı';
            parent.işlem = 'anomaly_analysis_completed';
            parent.completedAt = new Date().toISOString();
            parent.executionTime = Date.now() - parent.id;
            
            console.log('Parent updated successfully (by ID):', parent);
            
            saveHistory();
            updateHistoryDisplay();
            
            // Detayı otomatik göster
            // Detayı otomatik göster
            const queryIdToShow = window.pendingAnomalyQueryId; // ID'yi lokal değişkende sakla
            setTimeout(() => {
                showHistoryDetail(queryIdToShow); // Lokal değişkenden kullan
            }, 100);

            // ID'yi temizle
            window.pendingAnomalyQueryId = null;
            localStorage.removeItem('pendingAnomalyQueryId');
        }
    }
}

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
 * Doğal dil anomali analizi sonuçlarını göster - AI DESTEKLİ VERSİYON
 */
function displayAnomalyAnalysisResult(result) {
    console.log('Displaying AI-enhanced anomaly analysis result');
    
    let html = '<div class="anomaly-analysis-result ai-enhanced">';
    
    // Durum göstergesi
    const summary = result.sonuç?.summary;
    const anomalyRate = summary ? summary.anomaly_rate : 0;
    const statusClass = anomalyRate > 5 ? 'critical' : 
                       anomalyRate > 2 ? 'warning' : 'success';
    
    html += `<div class="result-status ${statusClass}">`;
    html += `<strong>✅ Anomali Analizi Tamamlandı</strong>`;
    html += `</div>`;
    
    // AI AÇIKLAMASI - ÖNCELİKLİ BÖLÜM
    let aiExplanation = result.sonuç?.ai_explanation || result.ai_explanation;

    // Eğer AI explanation string ise parse et
    if (typeof aiExplanation === 'string') {
        console.log('Parsing AI explanation from text...');
        aiExplanation = parseAIExplanationFromText(aiExplanation);
    }

    // Eğer açıklama field'ında varsa onu da kontrol et
    if (!aiExplanation && result.sonuç?.açıklama) {
        console.log('Parsing AI explanation from açıklama field...');
        aiExplanation = parseAIExplanationFromText(result.sonuç.açıklama);
    }

    if (aiExplanation && (aiExplanation.ne_tespit_edildi || typeof aiExplanation === 'object')) {
        html += '<div class="ai-explanation-section">';
        html += '<h3>🤖 AI Destekli Analiz</h3>';
        
        // Ne Tespit Edildi? - Ana açıklama
        html += '<div class="ai-section what-detected">';
        html += '<h4>🔍 Ne Tespit Edildi?</h4>';
        // Sayısal vurgulamayı ekle
        html += `<div class="ai-content">${highlightNumbers(escapeHtml(aiExplanation.ne_tespit_edildi))}</div>`;
        html += '</div>';
        
        // Potansiyel Etkiler - Görsel kartlar
        if (aiExplanation.potansiyel_etkiler && aiExplanation.potansiyel_etkiler.length > 0) {
            html += '<div class="ai-section potential-impacts">';
            html += '<h4>⚠️ Potansiyel Etkiler</h4>';
            html += '<div class="impact-cards">';
            
            aiExplanation.potansiyel_etkiler.forEach((etki, index) => {
                const impactLevel = etki.toLowerCase().includes('kritik') || etki.toLowerCase().includes('ciddi') ? 'high' :
                                   etki.toLowerCase().includes('orta') ? 'medium' : 'low';
                html += `
                    <div class="impact-card ${impactLevel}">
                        <span class="impact-number">${index + 1}</span>
                        <span class="impact-text">${highlightNumbers(escapeHtml(etki))}</span>
                    </div>
                `;
            });
            
            html += '</div></div>';
        }
        
        // Muhtemel Nedenler - Timeline tarzı
        if (aiExplanation.muhtemel_nedenler && aiExplanation.muhtemel_nedenler.length > 0) {
            html += '<div class="ai-section probable-causes">';
            html += '<h4>🎯 Muhtemel Nedenler</h4>';
            html += '<div class="causes-timeline">';
            
            aiExplanation.muhtemel_nedenler.forEach((neden, index) => {
                html += `
                    <div class="cause-item">
                        <div class="cause-marker">${index + 1}</div>
                        <div class="cause-content">
                            <div class="cause-text">${highlightNumbers(escapeHtml(neden))}</div>
                        </div>
                    </div>
                `;
            });
            
            html += '</div></div>';
        }
        
        // Önerilen Aksiyonlar - Öncelikli aksiyonlar
        if (aiExplanation.onerilen_aksiyonlar && aiExplanation.onerilen_aksiyonlar.length > 0) {
            html += '<div class="ai-section recommended-actions">';
            html += '<h4>🚀 Ne Yapmalısınız?</h4>';
            html += '<div class="action-cards">';
            
            aiExplanation.onerilen_aksiyonlar.forEach((aksiyon, index) => {
                let priorityClass = 'normal';
                let priorityIcon = '📌';
                
                if (aksiyon.toLowerCase().includes('hemen') || aksiyon.toLowerCase().includes('acil')) {
                    priorityClass = 'urgent';
                    priorityIcon = '🔴';
                } else if (aksiyon.toLowerCase().includes('kontrol') || aksiyon.toLowerCase().includes('incele')) {
                    priorityClass = 'check';
                    priorityIcon = '🔍';
                } else if (aksiyon.toLowerCase().includes('öneri') || aksiyon.toLowerCase().includes('düşün')) {
                    priorityClass = 'suggestion';
                    priorityIcon = '💡';
                }
                
                html += `
                    <div class="action-card ${priorityClass}" data-step="${index + 1}">
                        <div class="action-header">
                            <span class="action-icon">${priorityIcon}</span>
                            <span class="action-step">Adım ${index + 1}</span>
                        </div>
                        <div class="action-content">${highlightNumbers(escapeHtml(aksiyon))}</div>
                    </div>
                `;
            });
            
            html += '</div></div>';
        }
        
        html += '</div>'; // ai-explanation-section end
    }
    
    // Özet Metrikler - Daha görsel hale getirilmiş
    if (summary) {
        html += '<div class="metrics-overview">';
        html += '<h3>📊 Genel Bakış</h3>';
        html += '<div class="metric-cards-grid">';
        
        // Ana metrik kartı
        html += `
            <div class="metric-card primary ${statusClass}">
                <div class="metric-icon">🎯</div>
                <div class="metric-value">${summary.n_anomalies.toLocaleString('tr-TR')}</div>
                <div class="metric-label">Anomali Tespit Edildi</div>
                <div class="metric-percentage">%${summary.anomaly_rate.toFixed(1)}</div>
            </div>
        `;
        
        // Toplam log kartı
        html += `
            <div class="metric-card secondary">
                <div class="metric-icon">📄</div>
                <div class="metric-value">${summary.total_logs.toLocaleString('tr-TR')}</div>
                <div class="metric-label">Toplam Log Analiz Edildi</div>
            </div>
        `;
        
        // Kritik bulgular kartı
        if (result.sonuç.security_alerts?.drop_operations) {
            html += `
                <div class="metric-card alert">
                    <div class="metric-icon">🚨</div>
                    <div class="metric-value">${result.sonuç.security_alerts.drop_operations.count}</div>
                    <div class="metric-label">DROP Operasyonu</div>
                    <div class="metric-badge critical">KRİTİK</div>
                </div>
            `;
        }
        
        // Temporal analiz kartı
        if (result.sonuç.temporal_analysis?.peak_hours) {
            const peakHours = result.sonuç.temporal_analysis.peak_hours;
            html += `
                <div class="metric-card info">
                    <div class="metric-icon">⏰</div>
                    <div class="metric-value">${peakHours[0]}:00</div>
                    <div class="metric-label">En Yoğun Saat</div>
                </div>
            `;
        }
        
        html += '</div></div>';
    }
    
    // Kritik Anomaliler - Sadece ilk 5 tanesi, daha kompakt
    if (result.sonuç.critical_anomalies && result.sonuç.critical_anomalies.length > 0) {
        html += '<div class="critical-section">';
        html += '<h3>⚡ En Kritik 5 Anomali</h3>';
        html += '<div class="critical-list">';
        
        result.sonuç.critical_anomalies.slice(0, 5).forEach((anomaly, index) => {
            const scorePercent = Math.abs(anomaly.score) * 100;
            html += `
                <div class="critical-item">
                    <div class="critical-rank">#${index + 1}</div>
                    <div class="critical-details">
                        <div class="critical-component">${escapeHtml(anomaly.component || 'N/A')}</div>
                        <div class="critical-message">${escapeHtml(anomaly.message || '').substring(0, 100)}...</div>
                    </div>
                    <div class="critical-score">
                        <div class="score-bar" style="width: ${scorePercent}%"></div>
                        <span class="score-text">${anomaly.score.toFixed(3)}</span>
                    </div>
                </div>
            `;
        });
        
        html += '</div></div>';
    }
    
    // Component Dağılımı - Pie chart benzeri görsel
    if (result.sonuç.component_analysis) {
        html += '<div class="component-distribution">';
        html += '<h3>📈 Component Bazlı Dağılım</h3>';
        html += '<div class="component-chart">';
        
        const sortedComponents = Object.entries(result.sonuç.component_analysis)
            .sort(([,a], [,b]) => b.anomaly_count - a.anomaly_count)
            .slice(0, 5);
        
        sortedComponents.forEach(([component, stats]) => {
            const percentage = stats.anomaly_rate.toFixed(1);
            html += `
                <div class="component-bar-item">
                    <div class="component-info">
                        <span class="component-name">${escapeHtml(component)}</span>
                        <span class="component-stats">${stats.anomaly_count} anomali (%${percentage})</span>
                    </div>
                    <div class="component-bar-container">
                        <div class="component-bar-fill" style="width: ${percentage}%"></div>
                    </div>
                </div>
            `;
        });
        
        html += '</div></div>';
    }
    
    // YENİ: Component Analiz Tablosu
    if (result.sonuç.component_analysis) {
        html += '<div class="component-analysis-table">';
        html += '<h3>📊 Detaylı Component Analizi</h3>';
        html += '<table class="analysis-table">';
        html += '<thead>';
        html += '<tr>';
        html += '<th>Component</th>';
        html += '<th>Anomali Sayısı</th>';
        html += '<th>Toplam Log</th>';
        html += '<th>Anomali Oranı</th>';
        html += '<th>Kritiklik</th>';
        html += '</tr>';
        html += '</thead>';
        html += '<tbody>';
        
        Object.entries(result.sonuç.component_analysis)
            .sort(([,a], [,b]) => b.anomaly_count - a.anomaly_count)
            .forEach(([component, stats]) => {
                const criticalityClass = stats.anomaly_rate > 20 ? 'critical' : 
                                       stats.anomaly_rate > 10 ? 'warning' : 'normal';
                html += `<tr class="${criticalityClass}">`;
                html += `<td><strong>${escapeHtml(component)}</strong></td>`;
                html += `<td class="numeric">${stats.anomaly_count.toLocaleString('tr-TR')}</td>`;
                html += `<td class="numeric">${stats.total_count.toLocaleString('tr-TR')}</td>`;
                html += `<td class="percentage">%${stats.anomaly_rate.toFixed(1)}</td>`;
                html += `<td><span class="criticality-badge ${criticalityClass}">${
                    criticalityClass === 'critical' ? 'KRİTİK' : 
                    criticalityClass === 'warning' ? 'UYARI' : 'NORMAL'
                }</span></td>`;
                html += '</tr>';
            });
        
        html += '</tbody>';
        html += '</table>';
        html += '</div>';
    }
    
    // YENİ: Zamansal Analiz Grafiği
    if (result.sonuç.temporal_analysis?.hourly_distribution) {
        html += '<div class="temporal-chart-section">';
        html += '<h3>📈 Saatlik Anomali Dağılımı</h3>';
        html += '<div class="hourly-chart">';
        
        const hourlyData = result.sonuç.temporal_analysis.hourly_distribution;
        const maxValue = Math.max(...Object.values(hourlyData));
        
        for (let hour = 0; hour < 24; hour++) {
            const value = hourlyData[hour] || 0;
            const height = maxValue > 0 ? (value / maxValue) * 100 : 0;
            const isHighHour = result.sonuç.temporal_analysis.peak_hours?.includes(hour);
            
            html += `<div class="hour-bar ${isHighHour ? 'peak' : ''}" 
                          style="height: ${height}%" 
                          data-hour="${hour}"
                          data-value="${value}">
                        <span class="hour-value">${value}</span>
                        <span class="hour-label">${hour}</span>
                     </div>`;
        }
        
        html += '</div>';
        html += '<div class="chart-legend">';
        html += '<span class="legend-item"><span class="legend-color peak"></span> En Yoğun Saatler</span>';
        html += '<span class="legend-item"><span class="legend-color normal"></span> Normal Saatler</span>';
        html += '</div>';
        html += '</div>';
    }
    
    // Eylem Butonları
    html += '<div class="analysis-actions">';
    html += '<button class="btn btn-primary" onclick="toggleDetailedAnomalyList()">📋 Detaylı Anomali Listesi</button>';
    html += '<button class="btn btn-secondary" onclick="exportAnomalyReport()">📥 Raporu İndir</button>';
    html += '<button class="btn btn-info" onclick="scheduleFollowUp()">📅 Takip Planla</button>';
    html += '</div>';
    
    html += '</div>';
    
    elements.resultContent.innerHTML = html;
    elements.resultSection.style.display = 'block';
    elements.resultSection.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    
    // Detaylı sonuçları sakla
    window.lastAnomalyResult = result;
}

// Yeni yardımcı fonksiyonlar
function exportAnomalyReport() {
    if (!window.lastAnomalyResult) return;
    
    const report = {
        timestamp: new Date().toISOString(),
        summary: window.lastAnomalyResult.sonuç.summary,
        ai_analysis: window.lastAnomalyResult.sonuç.ai_explanation,
        critical_anomalies: window.lastAnomalyResult.sonuç.critical_anomalies,
        recommendations: window.lastAnomalyResult.öneriler
    };
    
    const dataStr = JSON.stringify(report, null, 2);
    const dataUri = 'data:application/json;charset=utf-8,'+ encodeURIComponent(dataStr);
    
    const exportFileDefaultName = `anomaly_report_${new Date().toISOString().split('T')[0]}.json`;
    
    const linkElement = document.createElement('a');
    linkElement.setAttribute('href', dataUri);
    linkElement.setAttribute('download', exportFileDefaultName);
    linkElement.click();
    
    showNotification('Rapor başarıyla indirildi', 'success');
}

function scheduleFollowUp() {
    const followUpHtml = `
        <div class="follow-up-form">
            <h4>📅 Anomali Takip Planı</h4>
            <p>Bu anomali analizi için takip planı oluşturun:</p>
            
            <div class="form-group">
                <label>Takip Süresi:</label>
                <select id="followUpPeriod">
                    <option value="1h">1 Saat Sonra</option>
                    <option value="4h">4 Saat Sonra</option>
                    <option value="1d" selected>1 Gün Sonra</option>
                    <option value="1w">1 Hafta Sonra</option>
                </select>
            </div>
            
            <div class="form-group">
                <label>Notlar:</label>
                <textarea id="followUpNotes" rows="3" placeholder="Takip için notlarınız..."></textarea>
            </div>
            
            <button class="btn btn-primary" onclick="saveFollowUp()">Takibi Kaydet</button>
        </div>
    `;
    
    showModal('Anomali Takip Planı', followUpHtml);
}

function saveFollowUp() {
    const period = document.getElementById('followUpPeriod').value;
    const notes = document.getElementById('followUpNotes').value;
    
    // Gerçek bir uygulamada bu bilgi backend'e kaydedilir
    console.log('Follow-up scheduled:', { period, notes });
    
    closeModal();
    showNotification('Takip planı oluşturuldu', 'success');
}


// Helper function for formatting sections
function formatSection(section) {
    return section
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\n/g, '<br>');
}


/**
 * Metindeki sayısal değerleri vurgula - GELİŞTİRİLMİŞ VERSİYON
 */
function highlightNumbers(text) {
    if (!text) return '';
    
    // Önce HTML escape yap
    text = escapeHtml(text);
    
    // 1. Yüzde değerleri
    text = text.replace(/(%\d+(?:\.\d+)?)/g, 
        '<span class="percentage-highlight">$1</span>');
    
    // 2. Sayı + birim kombinasyonları
    text = text.replace(/(\d+(?:\.\d+)?)\s*(ms|MB|GB|KB|anomali|log|adet|kez|doküman|document|kayıt|satır|saat|dakika|saniye)/gi, 
        '<span class="metric-highlight">$1 $2</span>');
    
    // 3. Büyük sayılar (binlik ayraçlı)
    text = text.replace(/(\d{1,3}(?:\.\d{3})*(?:,\d+)?)/g, 
        '<span class="number-highlight">$1</span>');
    
    // 4. Saat formatları
    text = text.replace(/(saat\s+\d+|Saat\s+\d+|\d{1,2}:\d{2})/g, 
        '<span class="time-highlight">$1</span>');
    
    // 5. Tarih formatları
    text = text.replace(/(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4})/g, 
        '<span class="date-highlight">$1</span>');
    
    // 6. Kritik kelimeler
    text = text.replace(/(kritik|acil|hemen|önemli|dikkat)/gi, 
        '<span class="critical-word">$1</span>');
    
    return text;
}

/**
 * AI açıklamasını text'ten parse et ve yapılandırılmış objeye çevir
 */
function parseAIExplanationFromText(text) {
    if (!text) return null;
    
    const sections = {
        ne_tespit_edildi: '',
        potansiyel_etkiler: [],
        muhtemel_nedenler: [],
        onerilen_aksiyonlar: []
    };
    
    // Text'i satırlara böl
    const lines = text.split('\n').filter(line => line.trim());
    let currentSection = '';
    
    lines.forEach(line => {
        const trimmedLine = line.trim();
        
        // Bölüm başlıklarını kontrol et
        if (trimmedLine.includes('Ne Tespit Edildi') || trimmedLine.includes('NE TESPİT EDİLDİ')) {
            currentSection = 'ne_tespit_edildi';
        } else if (trimmedLine.includes('Potansiyel Etkiler') || trimmedLine.includes('POTANSİYEL ETKİLER')) {
            currentSection = 'potansiyel_etkiler';
        } else if (trimmedLine.includes('Muhtemel Nedenler') || trimmedLine.includes('MUHTEMEL NEDENLER')) {
            currentSection = 'muhtemel_nedenler';
        } else if (trimmedLine.includes('Önerilen Aksiyonlar') || trimmedLine.includes('ÖNERİLEN AKSİYONLAR')) {
            currentSection = 'onerilen_aksiyonlar';
        } else if (trimmedLine && currentSection) {
            // İçeriği ilgili bölüme ekle
            if (currentSection === 'ne_tespit_edildi') {
                sections.ne_tespit_edildi += (sections.ne_tespit_edildi ? ' ' : '') + trimmedLine;
            } else if (trimmedLine.startsWith('-') || trimmedLine.startsWith('•') || trimmedLine.match(/^\d+\./)) {
                // Liste elemanı
                const cleanedItem = trimmedLine.replace(/^[-•]\s*/, '').replace(/^\d+\.\s*/, '');
                sections[currentSection].push(cleanedItem);
            }
        }
    });
    
    return sections;
}

/**
 * Performance Analiz Sonuçlarını Görselleştir - YENİ
 */
function displayPerformanceAnalysis(result) {
    const statusClass = result.durum === 'başarılı' ? 'success' : 'error';
    const statusIcon = result.durum === 'başarılı' ? '✅' : '❌';
    
    let html = `<div class="result-status ${statusClass}">`;
    html += `<strong>${statusIcon} ${result.durum.toUpperCase()}</strong> - Performance Analizi`;
    html += `</div>`;
    
    html += '<div class="result-details performance-analysis">';
    
    // Koleksiyon bilgisi
    if (result.koleksiyon) {
        html += `<div class="result-field">
                    <strong>📁 Koleksiyon:</strong> 
                    <span class="highlight">${escapeHtml(result.koleksiyon)}</span>
                 </div>`;
    }
    
    // Performance analiz detayları
    if (result.sonuç) {
        const data = result.sonuç;
        
        // 1. Performans Skoru - YENİ
        if (data.performance_score) {
            html += renderPerformanceScore(data.performance_score);
        }
        
        // 2. Execution Metrikleri - YENİ
        if (data.execution_stats) {
            html += renderExecutionMetrics(data.execution_stats);
        }
        
        // 3. Execution Tree - YENİ
        if (data.execution_tree) {
            html += renderExecutionTree(data.execution_tree);
        }
        
        // 4. İyileştirme Tahmini - YENİ
        if (data.improvement_estimate) {
            html += renderImprovementEstimate(data.improvement_estimate);
        }
    }
    
    // Açıklama metni (text based format için)
    if (result.açıklama) {
        html += '<div class="result-field performance-description">';
        html += '<h3>📋 Detaylı Analiz</h3>';
        html += `<pre class="analysis-text">${escapeHtml(result.açıklama)}</pre>`;
        html += '</div>';
    }
    
    // Öneriler
    if (result.öneriler && result.öneriler.length > 0) {
        html += renderRecommendations(result.öneriler);
    }
    
    html += '</div>';
    
    // Kullanıcı yönlendirmesi
    html += '<div class="user-guidance">';
    html += '<p>Yeni bir performans analizi yapmak ister misiniz?</p>';
    html += '</div>';
    
    // Timestamp
    if (result.timestamp) {
        const date = new Date(result.timestamp);
        html += `<div class="result-timestamp">🕐 İşlem zamanı: ${date.toLocaleString('tr-TR')}</div>`;
    }
    
    elements.resultContent.innerHTML = html;
    elements.resultSection.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    
    // Event listener'ları ekle - YENİ
    setTimeout(() => {
        attachPerformanceEventListeners();
    }, 100);
}

/**
 * Performans Skorunu Render Et - YENİ
 */
function renderPerformanceScore(scoreData) {
    const score = scoreData.score || 0;
    const level = scoreData.level || 'Bilinmiyor';
    const scoreColor = score >= 80 ? '#4CAF50' : 
                      score >= 60 ? '#FF9800' : 
                      score >= 40 ? '#FF5722' : '#F44336';
    
    let html = '<div class="performance-score-section">';
    html += '<h3>⚡ Performans Skoru</h3>';
    
    // Ana skor
    html += '<div class="main-score">';
    html += `<div class="score-circle" style="--score-color: ${scoreColor}">`;
    html += `<svg viewBox="0 0 200 200">`;
    html += `<circle cx="100" cy="100" r="90" class="score-bg"/>`;
    html += `<circle cx="100" cy="100" r="90" class="score-fill" 
                     style="stroke-dasharray: ${565 * score / 100} 565"/>`;
    html += `</svg>`;
    html += `<div class="score-text">`;
    html += `<span class="score-number">${score}</span>`;
    html += `<span class="score-label">/100</span>`;
    html += `</div>`;
    html += `</div>`;
    html += `<div class="score-level ${level.toLowerCase()}">${level}</div>`;
    html += '</div>';
    
    // Detaylı skorlar
    if (scoreData.detailed_scores) {
        html += '<div class="detailed-scores">';
        html += '<h4>📊 Detaylı Skorlar</h4>';
        html += '<div class="score-breakdown">';
        
        const scores = scoreData.detailed_scores;
        const scoreItems = [
            { key: 'time', label: 'Zaman', max: 30, icon: '⏱️' },
            { key: 'efficiency', label: 'Verimlilik', max: 30, icon: '📈' },
            { key: 'index', label: 'Index Kullanımı', max: 25, icon: '🔑' },
            { key: 'result_size', label: 'Sonuç Boyutu', max: 15, icon: '📄' }
        ];
        
        scoreItems.forEach(item => {
            const value = scores[item.key] || 0;
            const percentage = (value / item.max) * 100;
            html += `
                <div class="score-item">
                    <div class="score-header">
                        <span class="score-icon">${item.icon}</span>
                        <span class="score-label">${item.label}</span>
                        <span class="score-value">${value}/${item.max}</span>
                    </div>
                    <div class="score-bar-container">
                        <div class="score-bar" style="width: ${percentage}%"></div>
                    </div>
                </div>
            `;
        });
        
        html += '</div>';
        html += '</div>';
    }
    
    // Tespit edilen sorunlar
    if (scoreData.reasons && scoreData.reasons.length > 0) {
        html += '<div class="score-issues">';
        html += '<h4>⚠️ Tespit Edilen Sorunlar</h4>';
        html += '<ul>';
        scoreData.reasons.forEach(reason => {
            html += `<li>${escapeHtml(reason)}</li>`;
        });
        html += '</ul>';
        html += '</div>';
    }
    
    html += '</div>';
    return html;
}

/**
 * Execution Metriklerini Render Et - YENİ
 */
function renderExecutionMetrics(stats) {
    let html = '<div class="execution-metrics-section">';
    html += '<h3>📊 Execution Metrikleri</h3>';
    html += '<div class="metrics-grid">';
    
    // Metrik kartları
    const metrics = [
        {
            icon: '⏱️',
            label: 'Çalışma Süresi',
            value: `${stats.execution_time_ms}ms`,
            type: 'time'
        },
        {
            icon: '📄',
            label: 'Taranan Doküman',
            value: stats.total_docs_examined.toLocaleString('tr-TR'),
            type: 'docs'
        },
        {
            icon: '🔑',
            label: 'Taranan Index',
            value: stats.total_keys_examined.toLocaleString('tr-TR'),
            type: 'keys'
        },
        {
            icon: '✅',
            label: 'Dönen Doküman',
            value: stats.docs_returned.toLocaleString('tr-TR'),
            type: 'returned'
        }
    ];
    
    metrics.forEach(metric => {
        html += `
            <div class="metric-card ${metric.type}">
                <div class="metric-icon">${metric.icon}</div>
                <div class="metric-content">
                    <div class="metric-value">${metric.value}</div>
                    <div class="metric-label">${metric.label}</div>
                </div>
            </div>
        `;
    });
    
    // Verimlilik
    if (stats.efficiency_percent !== undefined) {
        const efficiencyColor = stats.efficiency_percent >= 80 ? '#4CAF50' :
                               stats.efficiency_percent >= 50 ? '#FF9800' :
                               stats.efficiency_percent >= 20 ? '#FF5722' : '#F44336';
        
        html += `
            <div class="metric-card efficiency">
                <div class="metric-icon">📈</div>
                <div class="metric-content">
                    <div class="metric-value" style="color: ${efficiencyColor}">
                        %${stats.efficiency_percent}
                    </div>
                    <div class="metric-label">Verimlilik</div>
                </div>
                <div class="efficiency-bar-container">
                    <div class="efficiency-bar" 
                         style="width: ${stats.efficiency_percent}%; background: ${efficiencyColor}"></div>
                </div>
            </div>
        `;
    }
    
    html += '</div>';
    html += '</div>';
    return html;
}

/**
 * Execution Tree'yi Render Et - YENİ
 */
function renderExecutionTree(tree) {
    let html = '<div class="execution-tree-section">';
    html += '<h3>🔍 Execution Plan</h3>';
    html += '<div class="tree-container">';
    html += renderTreeNode(tree);
    html += '</div>';
    html += '</div>';
    return html;
}

/**
 * Tree Node'u Render Et - YENİ
 */
function renderTreeNode(node, isRoot = true) {
    const stageEmoji = {
        'COLLSCAN': '🔴',
        'IXSCAN': '🟢',
        'FETCH': '🔵',
        'SORT': '🟡',
        'COUNT': '🟣',
        'UNKNOWN': '⚪'
    }[node.stage] || '⚪';
    
    const stageClass = {
        'COLLSCAN': 'stage-bad',
        'IXSCAN': 'stage-good',
        'FETCH': 'stage-neutral',
        'SORT': 'stage-warning',
        'COUNT': 'stage-info'
    }[node.stage] || 'stage-unknown';
    
    let html = `<div class="tree-node ${isRoot ? 'root' : ''}" data-stage="${node.stage}">`;
    
    // Node başlığı
    html += `<div class="node-header ${stageClass}">`;
    html += `<span class="stage-emoji">${stageEmoji}</span>`;
    html += `<span class="stage-name">${node.stage}</span>`;
    
    if (node.index_name) {
        html += `<span class="index-name">(${escapeHtml(node.index_name)})</span>`;
    }
    
    if (node.children && node.children.length > 0) {
        html += `<span class="toggle-icon">▼</span>`;
    }
    
    html += '</div>';
    
    // Node detayları
    html += '<div class="node-details">';
    
    if (node.stage_info) {
        html += `<div class="stage-info">${escapeHtml(node.stage_info)}</div>`;
    }
    
    html += '<div class="node-metrics">';
    if (node.docs_examined > 0) {
        html += `<span class="metric">📄 Docs: ${node.docs_examined.toLocaleString('tr-TR')}</span>`;
    }
    if (node.keys_examined > 0) {
        html += `<span class="metric">🔑 Keys: ${node.keys_examined.toLocaleString('tr-TR')}</span>`;
    }
    if (node.execution_time > 0) {
        html += `<span class="metric">⏱️ Time: ${node.execution_time}ms</span>`;
    }
    html += '</div>';
    
    html += '</div>';
    
    // Alt node'lar
    if (node.children && node.children.length > 0) {
        html += '<div class="node-children">';
        node.children.forEach(child => {
            html += renderTreeNode(child, false);
        });
        html += '</div>';
    }
    
    html += '</div>';
    return html;
}

/**
 * İyileştirme Tahminini Render Et - YENİ
 */
function renderImprovementEstimate(estimate) {
    if (!estimate || estimate.improvement_percent === 0) {
        return '';
    }
    
    let html = '<div class="improvement-estimate-section">';
    html += '<h3>🚀 İyileştirme Tahmini</h3>';
    
    const currentTime = estimate.current_time_ms;
    const estimatedTime = estimate.estimated_time_ms;
    const improvementPercent = estimate.improvement_percent;
    
    html += '<div class="improvement-comparison">';
    
    // Mevcut durum
    html += '<div class="comparison-item current">';
    html += '<h4>Mevcut Durum</h4>';
    html += `<div class="time-value">${currentTime}ms</div>`;
    html += '<div class="time-bar-container">';
    html += '<div class="time-bar current-bar" style="width: 100%"></div>';
    html += '</div>';
    html += '</div>';
    
    // Ok işareti
    html += '<div class="comparison-arrow">→</div>';
    
    // Tahmini durum
    const estimatedWidth = (estimatedTime / currentTime) * 100;
    html += '<div class="comparison-item estimated">';
    html += '<h4>Index Sonrası</h4>';
    html += `<div class="time-value">${estimatedTime.toFixed(1)}ms</div>`;
    html += '<div class="time-bar-container">';
    html += `<div class="time-bar estimated-bar" style="width: ${estimatedWidth}%"></div>`;
    html += '</div>';
    html += '</div>';
    
    html += '</div>';
    
    // İyileşme yüzdesi
    html += `<div class="improvement-percentage">`;
    html += `<span class="percentage-value">%${improvementPercent}</span> iyileşme bekleniyor`;
    html += '</div>';
    
    // Doküman tarama iyileştirmesi
    if (estimate.docs_examined_reduction > 0) {
        html += '<div class="docs-reduction">';
        html += `📉 ${estimate.docs_examined_reduction.toLocaleString('tr-TR')} daha az doküman taranacak`;
        html += '</div>';
    }
    
    html += '</div>';
    return html;
}

/**
 * Önerileri Render Et - GELİŞTİRİLMİŞ
 */
function renderRecommendations(recommendations) {
    if (!recommendations || recommendations.length === 0) {
        return '';
    }
    
    let html = '<div class="recommendations-section">';
    html += '<h3>💡 Performans Önerileri</h3>';
    html += '<div class="recommendations-list">';
    
    recommendations.forEach(rec => {
        // Öneri metnini parse et
        const parts = rec.split('] ');
        let priority = 'MEDIUM';
        let content = rec;
        
        if (parts.length > 1) {
            const priorityMatch = parts[0].match(/\[(.*?)$/);
            if (priorityMatch) {
                priority = priorityMatch[1];
            }
            content = parts[1];
        }
        
        const priorityClass = {
            'CRITICAL': 'priority-critical',
            'HIGH': 'priority-high',
            'MEDIUM': 'priority-medium',
            'LOW': 'priority-low'
        }[priority] || 'priority-medium';
        
        html += `<div class="recommendation-item ${priorityClass}">`;
        html += `<span class="priority-badge">${priority}</span>`;
        html += `<span class="recommendation-content">${escapeHtml(content)}</span>`;
        html += '</div>';
    });
    
    html += '</div>';
    html += '</div>';
    
    return html;
}

/**
 * Performance Event Listener'ları Ekle - YENİ
 */
function attachPerformanceEventListeners() {
    // Tree node toggle
    document.querySelectorAll('.node-header').forEach(header => {
        header.addEventListener('click', function() {
            const node = this.parentElement;
            const children = node.querySelector('.node-children');
            if (children) {
                children.classList.toggle('collapsed');
                const icon = this.querySelector('.toggle-icon');
                if (icon) {
                    icon.textContent = children.classList.contains('collapsed') ? '▶' : '▼';
                }
            }
        });
    });
}

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
            loadMongoDBHosts(); // MongoDB sunucularını yükle
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
            const selectedHost = document.getElementById('mongodbHostSelect').value;
            isValid = selectedHost && selectedHost.length > 0;
            console.log('OpenSearch source - selected host:', selectedHost, 'isValid:', isValid); // DEBUG LOG
            break;
        default:
            console.log('Unknown data source for validation:', selectedDataSource); // DEBUG LOG
    }
    
    startBtn.disabled = !isValid;
    console.log('Analysis button disabled:', !isValid); // DEBUG LOG
}

/**
 * Anomali analiz işlemini başlat
 */
async function handleAnalyzeLog() {
    console.log('handleAnalyzeLog çağrıldı!'); // DEBUG LOG
    
    const timeRange = document.querySelector('input[name="modalTimeRange"]:checked').value;
    console.log('Time Range:', timeRange); // DEBUG LOG
    console.log('Selected Data Source:', selectedDataSource); // DEBUG LOG
    
    // Zaman aralığını backend formatına çevir
    let backendTimeRange = timeRange;
    if (timeRange === 'last_24h') {
        backendTimeRange = 'last_day';
    } else if (timeRange === 'last_7d') {
        backendTimeRange = 'last_week';
    } else if (timeRange === 'last_30d') {
        backendTimeRange = 'last_month';
    }
    
    // Veri kaynağına göre parametreleri hazırla
    let requestData = {
        api_key: apiKey,
        time_range: backendTimeRange,
        source_type: selectedDataSource
    };
    
    // Kaynağa özel parametreler
    switch(selectedDataSource) {
        case 'file':
            requestData.file_path = 'config';  // Backend config'den okuyacak
            console.log('Using config file source'); // DEBUG LOG
            break;
            
        case 'upload':
            const selectedFile = document.querySelector('input[name="logFile"]:checked');
            if (!selectedFile) {
                console.log('No file selected for upload source'); // DEBUG LOG
                alert('Lütfen bir dosya seçin!');
                return;
            }
            requestData.file_path = selectedFile.value;
            console.log('Using uploaded file:', selectedFile.value); // DEBUG LOG
            break;
            
        case 'mongodb_direct':
            requestData.connection_string = document.getElementById('mongoConnectionString').value;
            requestData.file_path = 'mongodb';  // Dummy değer
            console.log('Using MongoDB direct connection'); // DEBUG LOG
            break;
            
        case 'test_servers':
            requestData.server_name = document.getElementById('testServerSelect').value;
            requestData.file_path = 'server';  // Dummy değer
            console.log('Using test server:', requestData.server_name); // DEBUG LOG
            break;
            
        case 'opensearch':
            const selectedHost = document.getElementById('mongodbHostSelect').value;
            console.log('SELECTED HOST VALUE:', selectedHost);
            console.log('OpenSearch Analysis - Selected Host Debug:', selectedHost);
            console.log('Host Select Element:', document.getElementById('mongodbHostSelect'));
            console.log('Host Select Element Value:', document.getElementById('mongodbHostSelect')?.value);
            console.log('Host Select Element Selected Index:', document.getElementById('mongodbHostSelect')?.selectedIndex);
            
            requestData.file_path = 'opensearch';  // Dummy değer
            if (selectedHost) {
                requestData.host_filter = selectedHost;
                console.log('Using OpenSearch with host filter:', selectedHost);
                console.log('Request data with host filter:', JSON.stringify(requestData, null, 2));
            } else {
                console.log('WARNING: No host selected for OpenSearch analysis!');
                console.log('This should not happen - validation should prevent this');
                console.log('Available options in select:', Array.from(document.getElementById('mongodbHostSelect').options).map(opt => opt.value));
            }
            break;
            
        default:
            console.log('Unknown data source for analysis:', selectedDataSource); // DEBUG LOG
    }
    
    console.log('Final Request Data for Analysis:', JSON.stringify(requestData, null, 2));
    console.log('Request Data - Source Type:', requestData.source_type);
    console.log('Request Data - Host Filter:', requestData.host_filter);

    closeAnomalyModal();
    showLoader();
    
    try {
        console.log('Sending analysis request to API...'); // DEBUG LOG
        console.log('API Endpoint:', API_ENDPOINTS.analyzeLog);
        console.log('Request Method: POST');
        console.log('Request Headers: Content-Type: application/json');
        console.log('Request Body:', JSON.stringify(requestData, null, 2));
        
        const response = await fetch(API_ENDPOINTS.analyzeLog, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(requestData)
        });
        
        console.log('Analysis response status:', response.status); // DEBUG LOG
        console.log('Analysis response headers:', response.headers);
        
        const result = await response.json();
        console.log('Analysis result received:', result); // DEBUG LOG
        console.log('BACKEND RESPONSE:', {
            durum: result.durum,
            işlem: result.işlem,
            açıklama: result.açıklama ? result.açıklama.substring(0, 100) + '...' : 'YOK',
            hasResult: !!result.sonuç,
            resultKeys: result.sonuç ? Object.keys(result.sonuç) : []
        });

        // Eğer onay bekliyor response'u ise özel handle et
        if (result.durum === 'onay_bekliyor') {
            console.error('HATA: Backend hala onay bekliyor response döndürüyor!');
            console.log('Onay response detayı:', result);
        }
        console.log('Analysis result type:', typeof result);
        console.log('Analysis result keys:', Object.keys(result));
        console.log('FULL RESULT:', JSON.stringify(result, null, 2));
        console.log('Result durum:', result.durum);
        console.log('Result işlem:', result.işlem);
        
        displayAnomalyResults(result);

        // YENİ: Butonla yapılan anomaly analizini history'ye ekle
        if (result.durum !== 'hata' && result.işlem === 'anomaly_analysis') {
            // Query text'i oluştur - kullanıcının seçtiği parametrelere göre
            let queryText = '';
            
            if (selectedDataSource === 'opensearch' && requestData.host_filter) {
                queryText = `${requestData.host_filter} için anomali analizi`;
            } else if (selectedDataSource === 'upload' && requestData.file_path) {
                const fileName = requestData.file_path.split('/').pop();
                queryText = `${fileName} dosyası için anomali analizi`;
            } else if (selectedDataSource === 'test_servers' && requestData.server_name) {
                queryText = `${requestData.server_name} sunucusu için anomali analizi`;
            } else {
                queryText = `Anomali analizi (${selectedDataSource})`;
            }
            
            // Zaman aralığını ekle
            const timeRangeText = timeRange === 'last_24h' ? 'son 24 saat' :
                                timeRange === 'last_7d' ? 'son 7 gün' :
                                timeRange === 'last_30d' ? 'son 30 gün' : '';
            
            if (timeRangeText) {
                queryText += ` - ${timeRangeText}`;
            }
            
            console.log('Adding manual anomaly analysis to history:', queryText);
            
            // History item oluştur
            const historyItem = {
                id: Date.now(),
                timestamp: new Date().toISOString(),
                query: queryText,
                type: 'anomaly',
                category: 'anomaly', 
                result: result,
                durum: result.durum || 'tamamlandı',
                işlem: 'anomaly_analysis',
                isManualAnalysis: true,  // Manuel analiz olduğunu işaretle
                sourceType: selectedDataSource,
                hasResult: true,
                childResult: result  // Direkt sonucu childResult olarak sakla
            };
            
            // History'ye ekle
            queryHistory.unshift(historyItem);
            if (queryHistory.length > MAX_HISTORY_ITEMS) {
                queryHistory = queryHistory.slice(0, MAX_HISTORY_ITEMS);
            }
            
            saveHistory();
            updateHistoryDisplay();
            
            console.log('Manual anomaly analysis added to history successfully');
        }
    } catch (error) {
        console.error('Analiz hatası:', error);
        console.error('Analysis request failed:', error); // DEBUG LOG
        console.error('Error details:', error.message);
        console.error('Error stack:', error.stack);
        alert('Analiz sırasında bir hata oluştu!');
    } finally {
        showLoader(false);  // hideLoader() yerine
    }
}

/**
 * Anomaly Modal'ı kapat
 */
function closeAnomalyModal() {
    console.log('closeAnomalyModal called'); // DEBUG LOG
    const anomalyModal = document.getElementById('anomalyModal');
    if (anomalyModal) {
        anomalyModal.style.display = 'none';
        console.log('Anomaly modal closed'); // DEBUG LOG
        
        // Data source'u upload'da tut
        if (selectedDataSource === 'upload') {
            // Bir sonraki açılış için hazırla
            setTimeout(() => {
                const uploadRadio = document.querySelector('input[name="dataSource"][value="upload"]');
                if (uploadRadio) uploadRadio.checked = true;
            }, 100);
        }
    } else {
        console.log('Anomaly modal element not found!'); // DEBUG LOG
    }
}

/**
 * Anomali analiz sonuçlarını görüntüle
 */
function displayAnomalyResults(result) {
    console.log('displayAnomalyResults called with result:', result);
    
    // YENİ: Backend'den gelen tüm veriyi kontrol et
    const mlData = result.sonuç?.data || result.sonuç || {};
    const summary = mlData.summary || {};
    const componentAnalysis = mlData.component_analysis || {};
    const temporalAnalysis = mlData.temporal_analysis || {};
    const featureImportance = mlData.feature_importance || {};
    const criticalAnomalies = mlData.critical_anomalies || [];
    const anomalyScoreStats = mlData.anomaly_score_stats || {};
    
    // YENİ: AI açıklaması mevcutsa parse et
    let aiExplanation = result.sonuç?.ai_explanation || result.ai_explanation;
    
    // Eğer AI explanation string ise parse et
    if (typeof aiExplanation === 'string') {
        console.log('Parsing AI explanation from text...');
        aiExplanation = parseAIExplanationFromText(aiExplanation);
    }
    
    // Eğer açıklama field'ında varsa onu da kontrol et
    if (!aiExplanation && result.açıklama) {
        console.log('Parsing AI explanation from açıklama field...');
        aiExplanation = parseAIExplanationFromText(result.açıklama);
    }
    
    // Eğer sadece text tabanlı sonuçsa, mevcut mantığı kullan
    if (!result.summary && !result.sonuç?.summary && result.açıklama) {
        // AI açıklama varsa öncelikle onu kullan
        if (aiExplanation && (aiExplanation.ne_tespit_edildi || typeof aiExplanation === 'object')) {
            let aiHtml = '<div class="anomaly-ai-text-results">';
            aiHtml += '<h3>🤖 AI Destekli Anomali Analizi</h3>';
            
            // AI bölümlerini render et
            if (aiExplanation.ne_tespit_edildi) {
                aiHtml += '<div class="ai-text-section">';
                aiHtml += '<h4>🔍 Ne Tespit Edildi?</h4>';
                aiHtml += `<div class="ai-text-content">${highlightNumbers(aiExplanation.ne_tespit_edildi)}</div>`;
                aiHtml += '</div>';
            }
            
            if (aiExplanation.potansiyel_etkiler && aiExplanation.potansiyel_etkiler.length > 0) {
                aiHtml += '<div class="ai-text-section">';
                aiHtml += '<h4>⚠️ Potansiyel Etkiler</h4><ul>';
                aiExplanation.potansiyel_etkiler.forEach(etki => {
                    aiHtml += `<li>${highlightNumbers(etki)}</li>`;
                });
                aiHtml += '</ul></div>';
            }
            
            if (aiExplanation.muhtemel_nedenler && aiExplanation.muhtemel_nedenler.length > 0) {
                aiHtml += '<div class="ai-text-section">';
                aiHtml += '<h4>🎯 Muhtemel Nedenler</h4><ul>';
                aiExplanation.muhtemel_nedenler.forEach(neden => {
                    aiHtml += `<li>${highlightNumbers(neden)}</li>`;
                });
                aiHtml += '</ul></div>';
            }
            
            if (aiExplanation.onerilen_aksiyonlar && aiExplanation.onerilen_aksiyonlar.length > 0) {
                aiHtml += '<div class="ai-text-section">';
                aiHtml += '<h4>💡 Önerilen Aksiyonlar</h4><ol>';
                aiExplanation.onerilen_aksiyonlar.forEach(aksiyon => {
                    aiHtml += `<li>${highlightNumbers(aksiyon)}</li>`;
                });
                aiHtml += '</ol></div>';
            }
            
            aiHtml += '</div>';
            
            // Modal yerine ana result alanında göster
            elements.resultContent.innerHTML = aiHtml;
            elements.resultSection.style.display = 'block';
            elements.resultSection.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            return;
        }
        
        // AI yoksa normal text formatting
        const formattedText = highlightNumbers(result.açıklama)
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/### (.*?)$/gm, '<h3>$1</h3>')
            .replace(/\n/g, '<br>')
            .replace(/- /g, '• ');
            
        elements.resultContent.innerHTML = 
            `<div class="anomaly-text-results">
                <div class="formatted-anomaly-text">${formattedText}</div>
            </div>`;
        elements.resultSection.style.display = 'block';
        elements.resultSection.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        return;
    }
    
    // Ana sonuç container'ı oluştur - ML ENHANCED VERSION
    let html = '<div class="anomaly-results ml-enhanced">';
    
    // Başlık
    html += '<div class="anomaly-header">';
    html += '<h2>🔍 Anomali Analiz Sonuçları - ML Detaylı Görünüm</h2>';
    html += '</div>';
    
    // YENİ: ML Model Performans Metrikleri
    if (summary.total_logs || anomalyScoreStats.min !== undefined) {
        html += renderMLModelMetrics(summary, anomalyScoreStats);
    }
    
    // YENİ: Feature Importance Grafiği
    if (Object.keys(featureImportance).length > 0) {
        html += renderFeatureImportanceChart(featureImportance);
    }
    
    // Mevcut AI Explanation (varsa)
    if (aiExplanation && (aiExplanation.ne_tespit_edildi || typeof aiExplanation === 'object')) {
        html += '<div class="ai-explanation-section">';
        html += '<h3>🤖 AI Destekli Analiz</h3>';
        
        // Ne Tespit Edildi?
        if (aiExplanation.ne_tespit_edildi) {
            html += '<div class="ai-section what-detected">';
            html += '<h4>🔍 Ne Tespit Edildi?</h4>';
            html += `<div class="ai-content">${highlightNumbers(aiExplanation.ne_tespit_edildi)}</div>`;
            html += '</div>';
        }
        
        // Potansiyel Etkiler
        if (aiExplanation.potansiyel_etkiler && aiExplanation.potansiyel_etkiler.length > 0) {
            html += '<div class="ai-section potential-impacts">';
            html += '<h4>⚠️ Potansiyel Etkiler</h4>';
            html += '<div class="impact-cards">';
            
            aiExplanation.potansiyel_etkiler.forEach((etki, index) => {
                const impactLevel = etki.toLowerCase().includes('kritik') || etki.toLowerCase().includes('ciddi') ? 'high' :
                                   etki.toLowerCase().includes('orta') ? 'medium' : 'low';
                html += `
                    <div class="impact-card ${impactLevel}">
                        <span class="impact-number">${index + 1}</span>
                        <span class="impact-text">${highlightNumbers(etki)}</span>
                    </div>
                `;
            });
            
            html += '</div></div>';
        }
        
        // Muhtemel Nedenler
        if (aiExplanation.muhtemel_nedenler && aiExplanation.muhtemel_nedenler.length > 0) {
            html += '<div class="ai-section probable-causes">';
            html += '<h4>🎯 Muhtemel Nedenler</h4>';
            html += '<div class="causes-timeline">';
            
            aiExplanation.muhtemel_nedenler.forEach((neden, index) => {
                html += `
                    <div class="cause-item">
                        <div class="cause-marker">${index + 1}</div>
                        <div class="cause-content">
                            <div class="cause-text">${highlightNumbers(neden)}</div>
                        </div>
                    </div>
                `;
            });
            
            html += '</div></div>';
        }
        
        // Önerilen Aksiyonlar
        if (aiExplanation.onerilen_aksiyonlar && aiExplanation.onerilen_aksiyonlar.length > 0) {
            html += '<div class="ai-section recommended-actions">';
            html += '<h4>🚀 Ne Yapmalısınız?</h4>';
            html += '<div class="action-cards">';
            
            aiExplanation.onerilen_aksiyonlar.forEach((aksiyon, index) => {
                let priorityClass = 'normal';
                let priorityIcon = '📌';
                
                if (aksiyon.toLowerCase().includes('hemen') || aksiyon.toLowerCase().includes('acil')) {
                    priorityClass = 'urgent';
                    priorityIcon = '🔴';
                } else if (aksiyon.toLowerCase().includes('kontrol') || aksiyon.toLowerCase().includes('incele')) {
                    priorityClass = 'check';
                    priorityIcon = '🔍';
                } else if (aksiyon.toLowerCase().includes('öneri') || aksiyon.toLowerCase().includes('düşün')) {
                    priorityClass = 'suggestion';
                    priorityIcon = '💡';
                }
                
                html += `
                    <div class="action-card ${priorityClass}" data-step="${index + 1}">
                        <div class="action-header">
                            <span class="action-icon">${priorityIcon}</span>
                            <span class="action-step">Adım ${index + 1}</span>
                        </div>
                        <div class="action-content">${highlightNumbers(aksiyon)}</div>
                    </div>
                `;
            });
            
            html += '</div></div>';
        }
        
        html += '</div>'; // ai-explanation-section end
    }
    
    // GELİŞTİRİLMİŞ: Component Analysis Dashboard
    if (Object.keys(componentAnalysis).length > 0) {
        html += renderComponentDashboard(componentAnalysis);
    }
    
    // GELİŞTİRİLMİŞ: Temporal Analysis Heatmap
    if (temporalAnalysis.hourly_distribution) {
        html += renderTemporalHeatmap(temporalAnalysis);
    }

    // YENİ: Security Alerts Dashboard
    const securityAlerts = mlData.security_alerts || result.sonuç?.security_alerts || {};
    if (Object.keys(securityAlerts).length > 0) {
        html += renderSecurityAlertsDashboard(securityAlerts);
    }
    
    // Kritik anomaliler
    if (criticalAnomalies.length > 0) {
        html += '<div class="critical-anomalies-section">';
        html += '<h3>⚠️ Kritik Anomaliler</h3>';
        html += '<div class="anomaly-list">';
        
        criticalAnomalies.slice(0, 10).forEach(anomaly => {
            html += `
                <div class="anomaly-item critical">
                    <div class="anomaly-score">${anomaly.anomaly_score?.toFixed(3) || anomaly.score?.toFixed(3) || 'N/A'}</div>
                    <div class="anomaly-details">
                        <div class="anomaly-time">${new Date(anomaly.timestamp).toLocaleString('tr-TR')}</div>
                        <div class="anomaly-message">${escapeHtml(anomaly.message)}</div>
                        <div class="anomaly-component">Component: ${escapeHtml(anomaly.component || 'N/A')}</div>
                    </div>
                </div>
            `;
        });
        
        html += '</div>';
        html += '</div>';
    }
    
    // Tüm anomaliler (eğer kritik anomaliler gösterildiyse atlayabilir)
    if (result.anomalies && result.anomalies.length > 0 && !criticalAnomalies.length) {
        html += '<div class="all-anomalies-section">';
        html += '<h3>📊 Tüm Anomaliler</h3>';
        html += '<div class="anomaly-list">';
        
        result.anomalies.slice(0, 50).forEach(anomaly => {
            const severityClass = anomaly.anomaly_score > 0.8 ? 'high' : 
                                 anomaly.anomaly_score > 0.6 ? 'medium' : 'low';
            
            html += `
                <div class="anomaly-item ${severityClass}">
                    <div class="anomaly-score">${anomaly.anomaly_score.toFixed(3)}</div>
                    <div class="anomaly-details">
                        <div class="anomaly-time">${new Date(anomaly.timestamp).toLocaleString('tr-TR')}</div>
                        <div class="anomaly-message">${escapeHtml(anomaly.message)}</div>
                        ${anomaly.component ? `<div class="anomaly-component">Component: ${escapeHtml(anomaly.component)}</div>` : ''}
                    </div>
                </div>
            `;
        });
        
        if (result.anomalies.length > 50) {
            html += `<p class="more-anomalies">... ve ${result.anomalies.length - 50} anomali daha</p>`;
        }
        
        html += '</div>';
        html += '</div>';
    }
    
    // Component dağılımı
    if (result.component_stats && !Object.keys(componentAnalysis).length) {
        html += '<div class="component-stats-section">';
        html += '<h3>📈 Component Dağılımı</h3>';
        html += '<div class="component-grid">';
        
        Object.entries(result.component_stats).forEach(([component, count]) => {
            const percentage = ((count / (result.summary?.anomaly_count || 1)) * 100).toFixed(1);
            html += `
                <div class="component-stat">
                    <div class="component-name">${escapeHtml(component)}</div>
                    <div class="component-count">${count} anomali</div>
                    <div class="component-bar" style="width: ${percentage}%"></div>
                    <div class="component-percentage">${percentage}%</div>
                </div>
            `;
        });
        
        html += '</div>';
        html += '</div>';
    }
    
    // Hata durumu
    if (result.durum === "hata") {
        console.log('Error result detected:', result.açıklama);
        html = '<div class="anomaly-error">';
        html += '<h3>❌ Hata</h3>';
        html += `<p>${escapeHtml(result.açıklama || "Bilinmeyen hata")}</p>`;
        html += '</div>';
    }
    
    // Eylem butonları
    html += '<div class="analysis-actions">';
    html += '<button class="btn btn-primary" onclick="toggleDetailedAnomalyList()">📋 Detaylı Anomali Listesi</button>';
    html += '<button class="btn btn-secondary" onclick="exportAnomalyReport()">📥 Raporu İndir</button>';
    html += '<button class="btn btn-info" onclick="scheduleFollowUp()">📅 Takip Planla</button>';
    html += '</div>';
    
    html += '</div>';
    
    // Sonuçları göster
    elements.resultContent.innerHTML = html;
    elements.resultSection.style.display = 'block';
    elements.resultSection.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    
    // Event listener'ları ekle
    setTimeout(() => {
        attachMLVisualizationListeners();
    }, 100);
    
    // Detaylı sonuçları sakla
    window.lastAnomalyResult = result;
}

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



// Yardımcı fonksiyonlar

/**
 * Durum güncelleme
 */
function updateStatus(status, message) {
    elements.statusElement.className = `status ${status}`;
    elements.statusText.textContent = message;
}

/**
 * Bildirim göster
 */
function showNotification(message, type = 'info') {
    // Basit bir bildirim sistemi (toast notification eklenebilir)
    console.log(`[${type.toUpperCase()}] ${message}`);
    
    // Geçici olarak status'te göster
    const originalStatus = elements.statusText.textContent;
    const originalClass = elements.statusElement.className;
    
    elements.statusElement.className = `status ${type}`;
    elements.statusText.textContent = message;
    
    setTimeout(() => {
        elements.statusElement.className = originalClass;
        elements.statusText.textContent = originalStatus;
    }, 3000);
}

/**
 * Loader göster/gizle - PARAMETRELİ VERSİYON
 */
function showLoader(show) {
    elements.loader.style.display = show ? 'block' : 'none';
}

/**
 * Modal göster
 */
function showModal(title, content) {
    elements.modalTitle.textContent = title;
    elements.modalBody.innerHTML = content;
    elements.modal.style.display = 'block';
}

/**
 * Modal kapat
 */
function closeModal() {
    elements.modal.style.display = 'none';
}

/**
 * HTML escape
 */
function escapeHtml(text) {
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    };
    return String(text).replace(/[&<>"']/g, m => map[m]);
}

/**
 * JSON formatla ve renklendir
 */
function formatJSON(obj) {
    const json = JSON.stringify(obj, null, 2);
    
    // Basit JSON renklendirme
    return json
        .replace(/("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g, 
        function (match) {
            let cls = 'json-number';
            if (/^"/.test(match)) {
                if (/:$/.test(match)) {
                    cls = 'json-key';
                } else {
                    cls = 'json-string';
                }
            } else if (/true|false/.test(match)) {
                cls = 'json-boolean';
            } else if (/null/.test(match)) {
                cls = 'json-null';
            }
            return '<span class="' + cls + '">' + match + '</span>';
        });
}

// ===== KONUŞMA GEÇMİŞİ YÖNETİMİ =====

/**
 * Geçmişi localStorage'dan yükle
 */
function loadHistory() {
    try {
        const saved = localStorage.getItem(HISTORY_KEY);
        if (saved) {
            queryHistory = JSON.parse(saved);
            updateHistoryDisplay();
        }
    } catch (e) {
        console.error('Geçmiş yüklenemedi:', e);
        queryHistory = [];
    }
}

/**
 * Geçmişe yeni sorgu ekle
 */
function addToHistory(query, result, type = 'chatbot') {
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
        category: type, // ✅ Aynı değeri category olarak da sakla
        result: result,
        durum: result.durum,
        işlem: result.işlem,
        // ML verilerini sakla
        mlData: result.sonuç?.data || null,
        aiExplanation: result.sonuç?.ai_explanation || result.ai_explanation || null,
        hasVisualization: !!(result.sonuç?.data?.summary || result.sonuç?.data?.component_analysis)
    };
    
    // En başa ekle
    queryHistory.unshift(historyItem);
    
    // Maksimum sayıyı aş
    if (queryHistory.length > MAX_HISTORY_ITEMS) {
        queryHistory = queryHistory.slice(0, MAX_HISTORY_ITEMS);
    }
    
    // localStorage'a kaydet
    saveHistory();
    
    // Görüntüyü güncelle
    updateHistoryDisplay();
}

/**
 * Geçmişi localStorage'a kaydet
 */
function saveHistory() {
    try {
        localStorage.setItem(HISTORY_KEY, JSON.stringify(queryHistory));
    } catch (e) {
        console.error('Geçmiş kaydedilemedi:', e);
    }
}

/**
 * Geçmiş görüntüsünü güncelle
 */
function updateHistoryDisplay(filter = 'all') {
    const historyContent = document.getElementById('historyContent');
    if (!historyContent) return;
    
    // Filtreleme
    let filteredHistory = queryHistory;
    if (filter === 'chatbot') {
        filteredHistory = queryHistory.filter(item => 
            item.type === 'chatbot' || (!item.type && item.category === 'chatbot')
        );
    } else if (filter === 'anomaly') {
        filteredHistory = queryHistory.filter(item => 
            item.type === 'anomaly' || 
            item.category === 'anomaly' ||
            item.isAnomalyParent === true
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
        const typeIcon = item.type === 'anomaly' ? '🔍' : '💬';
        
        // GENİŞLETİLMİŞ DURUM KONTROLÜ
        const statusClass = item.durum === 'tamamlandı' ? 'completed' :
                           item.durum === 'başarılı' ? 'success' : 
                           item.durum === 'hata' ? 'error' :
                           item.durum === 'onay_bekliyor' ? 'pending' : 
                           item.durum === 'iptal' ? 'cancelled' : 'warning';
        
        // Durum ikonu
        const statusIcon = item.durum === 'tamamlandı' ? '✅' :
                          item.durum === 'onay_bekliyor' ? '⏳' :
                          item.durum === 'başarılı' ? '✔️' :
                          item.durum === 'iptal' ? '❌' : '⚠️';
        
        // Parent sorgu için özel stil
        // Parent-child ilişkisini daha net göster
        const itemClass = item.isAnomalyParent ? 'history-item anomaly-parent' : 'history-item';

        // Eğer bu bir anomali parent ise ve sonucu varsa, özel işaretleme ekle
        const resultIndicator = item.hasResult && item.childResult ? 
            '<span class="result-indicator">✅ Analiz Tamamlandı</span>' : 
            item.awaitingConfirmation && item.durum === 'onay_bekliyor' ? 
            '<span class="result-indicator pending animated">⏳ Onay Bekliyor</span>' : 
            item.durum === 'iptal' ?
            '<span class="result-indicator cancelled">❌ İptal Edildi</span>' : '';
        html += `
            <div class="${itemClass}" data-id="${item.id}" data-has-result="${item.hasResult || false}">
                <div class="history-item-header">
                    <span class="history-type">${typeIcon}</span>
                    <span class="history-time">${date.toLocaleString('tr-TR')}</span>
                    ${resultIndicator}
                    <span class="history-status ${statusClass}">${statusIcon} ${item.durum}</span>
                    ${item.executionTime ? `<span class="execution-time">⏱️ ${(item.executionTime/1000).toFixed(1)}s</span>` : ''}
                </div>
                <div class="history-query">${escapeHtml(item.query)}</div>
                <div class="history-actions">
                ${!item.parentId ? `
                    <button class="btn-small" onclick="replayQuery(${item.id})">
                        🔄 Tekrar Çalıştır
                    </button>
                ` : ''}
                <button class="btn-small" onclick="window.showHistoryDetail(${item.id})">
                    ${item.hasResult && item.childResult ? '📊 Sonuçları Göster' : '👁️ Detay'}
                </button>
            </div>
        </div>
    `;
});
    
    html += '</div>';
    historyContent.innerHTML = html;
}

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
            
            // 2. Feature Importance Chart
            if (mlData.feature_importance && Object.keys(mlData.feature_importance).length > 0) {
                content += renderFeatureImportanceChart(mlData.feature_importance);
            }
            
            // 3. Component Dashboard
            if (mlData.component_analysis) {
                content += renderComponentDashboard(mlData.component_analysis);
            }
            
            // 4. Temporal Heatmap
            if (mlData.temporal_analysis?.hourly_distribution) {
                content += renderTemporalHeatmap(mlData.temporal_analysis);
            }
            
            // 5. Score Distribution (eğer varsa)
            if (mlData.anomaly_score_stats && mlData.summary) {
                content += renderAnomalyScoreDistribution(mlData.anomaly_score_stats, mlData.summary);
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
        
        // AI destekli açıklama varsa öncelikle onu göster
        if (item.childResult.sonuç?.ai_explanation || 
            (item.childResult.açıklama && item.childResult.açıklama.includes('AI DESTEKLİ'))) {
            
            content += '<div class="anomaly-ai-result">';
            content += '<h4>🤖 AI Destekli Anomali Analiz Sonuçları</h4>';
            
            // AI explanation obje ise
            const aiExpl = item.childResult.sonuç?.ai_explanation;
            if (aiExpl && typeof aiExpl === 'object') {
                // Ne Tespit Edildi?
                if (aiExpl.ne_tespit_edildi) {
                    content += '<div class="ai-section">';
                    content += '<h5>🔍 Ne Tespit Edildi?</h5>';
                    content += `<div class="ai-content">${highlightNumbers(escapeHtml(aiExpl.ne_tespit_edildi))}</div>`;
                    content += '</div>';
                }
                
                // Potansiyel Etkiler
                if (aiExpl.potansiyel_etkiler && aiExpl.potansiyel_etkiler.length > 0) {
                    content += '<div class="ai-section">';
                    content += '<h5>⚠️ Potansiyel Etkiler</h5>';
                    content += '<ul>';
                    aiExpl.potansiyel_etkiler.forEach(etki => {
                        content += `<li>${highlightNumbers(escapeHtml(etki))}</li>`;
                    });
                    content += '</ul>';
                    content += '</div>';
                }
                
                // Muhtemel Nedenler
                if (aiExpl.muhtemel_nedenler && aiExpl.muhtemel_nedenler.length > 0) {
                    content += '<div class="ai-section">';
                    content += '<h5>🎯 Muhtemel Nedenler</h5>';
                    content += '<ul>';
                    aiExpl.muhtemel_nedenler.forEach(neden => {
                        content += `<li>${highlightNumbers(escapeHtml(neden))}</li>`;
                    });
                    content += '</ul>';
                    content += '</div>';
                }
                
                // Önerilen Aksiyonlar
                if (aiExpl.onerilen_aksiyonlar && aiExpl.onerilen_aksiyonlar.length > 0) {
                    content += '<div class="ai-section">';
                    content += '<h5>💡 Önerilen Aksiyonlar</h5>';
                    content += '<ol>';
                    aiExpl.onerilen_aksiyonlar.forEach(aksiyon => {
                        content += `<li>${highlightNumbers(escapeHtml(aksiyon))}</li>`;
                    });
                    content += '</ol>';
                    content += '</div>';
                }
            }
            // AI explanation text ise (açıklama field'ında)
            else if (item.childResult.açıklama && item.childResult.açıklama.includes('AI DESTEKLİ')) {
                content += '<div class="ai-formatted-text">';
                const formattedAI = item.childResult.açıklama
                    .replace(/🔍\s*\*\*(.*?)\*\*/g, '<h5>🔍 <strong>$1</strong></h5>')
                    .replace(/⚠️\s*\*\*(.*?)\*\*/g, '<h5>⚠️ <strong>$1</strong></h5>')
                    .replace(/🎯\s*\*\*(.*?)\*\*/g, '<h5>🎯 <strong>$1</strong></h5>')
                    .replace(/💡\s*\*\*(.*?)\*\*/g, '<h5>💡 <strong>$1</strong></h5>')
                    .replace(/📊\s*\*\*(.*?)\*\*/g, '<h5>📊 <strong>$1</strong></h5>')
                    .replace(/• (.*?)$/gm, '<li>$1</li>')
                    .replace(/\n/g, '<br>');
                content += formattedAI;
                content += '</div>';
            }
            
            content += '</div>';
        }
        // AI explanation yoksa ama açıklama varsa, text format kullan
        else if (item.childResult.açıklama) {
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
function clearHistory() {
    if (confirm('Tüm sorgu geçmişini silmek istediğinizden emin misiniz?')) {
        queryHistory = [];
        saveHistory();
        updateHistoryDisplay();
        showNotification('Geçmiş temizlendi', 'success');
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
    if (!file) return;
    
    // Dosya tipi kontrolü
    if (!file.name.match(/\.(log|txt|json)$/i)) {
        showNotification('Sadece .log, .txt veya .json dosyaları kabul edilir', 'error');
        return;
    }
    
    // Dosya boyutu kontrolü (100MB)
    if (file.size > 100 * 1024 * 1024) {
        showNotification('Dosya boyutu 100MB\'dan büyük olamaz', 'error');
        return;
    }
    
    const formData = new FormData();
    formData.append('file', file);
    
    showLoader(true);
    
    try {
        const response = await fetch(`${API_ENDPOINTS.uploadLog}?api_key=${apiKey}`, {
            method: 'POST',
            body: formData
        });
        
        if (response.ok) {
            const result = await response.json();
            showNotification(`Dosya başarıyla yüklendi: ${result.filename}`, 'success');
            
            // Yüklenen dosyalar listesini güncelle
            updateUploadedFilesList();
            
            // Uploaded files bölümünü göster
            document.getElementById('uploadedFiles').style.display = 'block';
        } else {
            throw new Error('Dosya yüklenemedi');
        }
    } catch (error) {
        showNotification('Dosya yükleme hatası: ' + error.message, 'error');
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
    
    if (!window.lastAnomalyResult || !window.lastAnomalyResult.sonuç) {
        showNotification('Gösterilecek anomali sonucu bulunamadı', 'warning');
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
    
    // Anomali tip tespiti
    if (message.includes('auth') || message.includes('authentication')) {
        return 'auth_failure';
    } else if (message.includes('connection') && (message.includes('drop') || message.includes('closed'))) {
        return 'connection_drop';
    } else if (message.includes('index') && (message.includes('fail') || message.includes('error'))) {
        return 'index_build_fail';
    } else if (message.includes('slow') || message.includes('took')) {
        return 'slow_query';
    } else if (message.includes('memory') || message.includes('oom')) {
        return 'out_of_memory';
    } else if (message.includes('restart') || message.includes('restarted')) {
        return 'service_restart';
    } else if (message.includes('collscan') || message.includes('collection scan')) {
        return 'collection_scan';
    } else if (message.includes('assertion') || message.includes('assert')) {
        return 'assertion_failure';
    } else if (message.includes('fatal') || severity === 'f') {
        return 'fatal_error';
    } else if (message.includes('shutdown')) {
        return 'shutdown';
    } else if (severity === 'e' || message.includes('error')) {
        return 'error';
    } else if (severity === 'w' || message.includes('warning')) {
        return 'warning';
    } else if (component === 'network') {
        return 'network_issue';
    } else if (component === 'repl') {
        return 'replication_issue';
    } else if (component === 'query') {
        return 'query_issue';
    } else {
        return 'unknown';
    }
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
    
    // Anomali tip açıklamaları
    const typeDescriptions = {
        'auth_failure': { icon: '🔐', name: 'Kimlik Doğrulama Hataları', color: '#e74c3c' },
        'connection_drop': { icon: '🔌', name: 'Bağlantı Kopmaları', color: '#e67e22' },
        'index_build_fail': { icon: '📑', name: 'Index Oluşturma Hataları', color: '#f39c12' },
        'slow_query': { icon: '🐌', name: 'Yavaş Sorgular', color: '#3498db' },
        'out_of_memory': { icon: '💾', name: 'Bellek Yetersizliği', color: '#e74c3c' },
        'service_restart': { icon: '🔄', name: 'Servis Yeniden Başlatmaları', color: '#9b59b6' },
        'collection_scan': { icon: '🔍', name: 'Collection Scan Uyarıları', color: '#1abc9c' },
        'assertion_failure': { icon: '❗', name: 'Assertion Hataları', color: '#e74c3c' },
        'fatal_error': { icon: '💀', name: 'Fatal Hatalar', color: '#c0392b' },
        'shutdown': { icon: '⏹️', name: 'Kapanma Olayları', color: '#7f8c8d' },
        'error': { icon: '❌', name: 'Genel Hatalar', color: '#e74c3c' },
        'warning': { icon: '⚠️', name: 'Uyarılar', color: '#f39c12' },
        'network_issue': { icon: '🌐', name: 'Network Sorunları', color: '#3498db' },
        'replication_issue': { icon: '🔄', name: 'Replikasyon Sorunları', color: '#9b59b6' },
        'query_issue': { icon: '❓', name: 'Sorgu Sorunları', color: '#e67e22' },
        'unknown': { icon: '❔', name: 'Sınıflandırılmamış', color: '#95a5a6' }
    };
    
    let html = '<div class="anomaly-type-groups">';
    
    // Özet bilgi
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
        
        // En fazla 20 anomali göster
        typeAnomalies.slice(0, 20).forEach((anomaly, index) => {
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
                                <strong>Component:</strong> ${anomaly.component || 'N/A'}
                            </span>
                            <span class="metadata-item">
                                <strong>Severity:</strong> ${anomaly.severity || 'N/A'}
                            </span>
                        </div>
                        ${getAnomalyExplanation(type)}
                    </div>
                </div>
            `;
        });
        
        if (typeAnomalies.length > 20) {
            html += `<p class="more-items">... ve ${typeAnomalies.length - 20} ${typeInfo.name.toLowerCase()} daha</p>`;
        }
        
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
                limit: 1000 // Maksimum 1000 anomali getir
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
// ========== ML GÖRSELLEŞTIRME YARDIMCI FONKSİYONLARI ==========

/**
 * ML Model Metriklerini Render Et
 */
function renderMLModelMetrics(summary, scoreStats) {
    let html = '<div class="ml-model-metrics-section">';
    html += '<h3>🤖 ML Model Performans Metrikleri</h3>';
    html += '<div class="ml-metrics-grid">';
    
    // Model Accuracy Score
    const modelAccuracy = summary.anomaly_rate ? (100 - summary.anomaly_rate).toFixed(1) : 'N/A';
    html += `
        <div class="ml-metric-card accuracy">
            <div class="ml-metric-header">
                <span class="ml-metric-icon">🎯</span>
                <span class="ml-metric-label">Model Accuracy</span>
            </div>
            <div class="ml-metric-value">${modelAccuracy}%</div>
            <div class="ml-metric-chart">
                <svg viewBox="0 0 100 100" class="accuracy-ring">
                    <circle cx="50" cy="50" r="45" class="ring-bg"/>
                    <circle cx="50" cy="50" r="45" class="ring-progress" 
                            style="stroke-dasharray: ${282.7 * modelAccuracy / 100} 282.7"/>
                </svg>
            </div>
        </div>
    `;
    
    // Isolation Score Range
    html += `
        <div class="ml-metric-card score-range">
            <div class="ml-metric-header">
                <span class="ml-metric-icon">📊</span>
                <span class="ml-metric-label">Anomaly Score Range</span>
            </div>
            <div class="score-range-visual">
                <div class="score-range-bar">
                    <span class="score-min">${scoreStats.min?.toFixed(3) || 'N/A'}</span>
                    <div class="score-range-fill">
                        <div class="score-mean-marker" style="left: ${((scoreStats.mean - scoreStats.min) / (scoreStats.max - scoreStats.min) * 100)}%">
                            <span class="score-mean-value">${scoreStats.mean?.toFixed(3) || 'N/A'}</span>
                        </div>
                    </div>
                    <span class="score-max">${scoreStats.max?.toFixed(3) || 'N/A'}</span>
                </div>
            </div>
        </div>
    `;
    
    // Detection Statistics
    html += `
        <div class="ml-metric-card detection-stats">
            <div class="ml-metric-header">
                <span class="ml-metric-icon">🔍</span>
                <span class="ml-metric-label">Detection Statistics</span>
            </div>
            <div class="detection-stats-grid">
                <div class="stat-item">
                    <span class="stat-value">${summary.total_logs?.toLocaleString('tr-TR') || 0}</span>
                    <span class="stat-label">Total Logs</span>
                </div>
                <div class="stat-item anomaly">
                    <span class="stat-value">${summary.n_anomalies?.toLocaleString('tr-TR') || 0}</span>
                    <span class="stat-label">Anomalies</span>
                </div>
                <div class="stat-item rate">
                    <span class="stat-value">%${summary.anomaly_rate?.toFixed(2) || 0}</span>
                    <span class="stat-label">Detection Rate</span>
                </div>
            </div>
        </div>
    `;
    
    html += '</div></div>';
    return html;
}

/**
 * Feature Importance Chart Render Et
 */
function renderFeatureImportanceChart(featureImportance) {
    let html = '<div class="feature-importance-section">';
    html += '<h3>📈 Feature Importance Analysis</h3>';
    html += '<div class="feature-importance-chart">';
    
    // Feature'ları ratio'ya göre sırala
    const sortedFeatures = Object.entries(featureImportance)
        .sort(([,a], [,b]) => (b.ratio || 0) - (a.ratio || 0));
    
    sortedFeatures.forEach(([feature, stats]) => {
        const ratio = stats.ratio || 1;
        const anomalyRate = stats.anomaly_rate || 0;
        const normalRate = stats.normal_rate || 0;
        
        // Feature isimlerini daha okunabilir hale getir
        const featureLabel = feature
            .replace(/_/g, ' ')
            .replace(/\b\w/g, l => l.toUpperCase());
        
        html += `
            <div class="feature-item">
                <div class="feature-header">
                    <span class="feature-name">${featureLabel}</span>
                    <span class="feature-ratio ${ratio > 5 ? 'high' : ratio > 2 ? 'medium' : 'low'}">
                        ${ratio === Infinity ? '∞' : ratio.toFixed(1)}x
                    </span>
                </div>
                <div class="feature-bars">
                    <div class="feature-bar anomaly" style="width: ${Math.min(anomalyRate, 100)}%">
                        <span class="bar-label">Anomaly: ${anomalyRate.toFixed(1)}%</span>
                    </div>
                    <div class="feature-bar normal" style="width: ${Math.min(normalRate, 100)}%">
                        <span class="bar-label">Normal: ${normalRate.toFixed(1)}%</span>
                    </div>
                </div>
            </div>
        `;
    });
    
    html += '</div></div>';
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
 * Component Dashboard Render Et
 */
function renderComponentDashboard(componentAnalysis) {
    let html = '<div class="component-dashboard-section">';
    html += '<h3>🎛️ Component Analysis Dashboard</h3>';
    
    // Component cards grid
    html += '<div class="component-cards-grid">';
    
    // En kritik 6 component'i göster
    const sortedComponents = Object.entries(componentAnalysis)
        .sort(([,a], [,b]) => b.anomaly_rate - a.anomaly_rate)
        .slice(0, 6);
    
    sortedComponents.forEach(([component, stats]) => {
        const criticalityClass = stats.anomaly_rate > 20 ? 'critical' : 
                               stats.anomaly_rate > 10 ? 'warning' : 'normal';
        
        html += `
            <div class="component-card ${criticalityClass}">
                <div class="component-card-header">
                    <span class="component-icon">${getComponentIcon(component)}</span>
                    <span class="component-name">${component}</span>
                </div>
                <div class="component-stats-visual">
                    <div class="circular-progress" data-percentage="${stats.anomaly_rate}">
                        <svg viewBox="0 0 100 100">
                            <circle cx="50" cy="50" r="45" class="progress-bg"/>
                            <circle cx="50" cy="50" r="45" class="progress-fill" 
                                    style="stroke-dasharray: ${282.7 * stats.anomaly_rate / 100} 282.7"/>
                        </svg>
                        <div class="progress-text">
                            <span class="percentage">${stats.anomaly_rate.toFixed(1)}%</span>
                        </div>
                    </div>
                </div>
                <div class="component-details">
                    <div class="detail-row">
                        <span class="detail-label">Anomalies:</span>
                        <span class="detail-value">${stats.anomaly_count}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Total Logs:</span>
                        <span class="detail-value">${stats.total_count}</span>
                    </div>
                </div>
            </div>
        `;
    });
    
    html += '</div>';
    html += '</div>';
    return html;
}

/**
 * Temporal Heatmap Render Et
 */
function renderTemporalHeatmap(temporalAnalysis) {
    let html = '<div class="temporal-heatmap-section">';
    html += '<h3>🗓️ Temporal Pattern Heatmap</h3>';
    
    const hourlyData = temporalAnalysis.hourly_distribution || {};
    const maxValue = Math.max(...Object.values(hourlyData), 1);
    
    // Heatmap grid
    html += '<div class="temporal-heatmap">';
    
    // Hour labels
    html += '<div class="heatmap-hours">';
    for (let hour = 0; hour < 24; hour++) {
        html += `<div class="hour-label">${hour}:00</div>`;
    }
    html += '</div>';
    
    // Heatmap cells
    html += '<div class="heatmap-grid">';
    for (let hour = 0; hour < 24; hour++) {
        const value = hourlyData[hour] || 0;
        const intensity = value / maxValue;
        const isPeak = temporalAnalysis.peak_hours?.includes(hour);
        
        html += `
            <div class="heatmap-cell ${isPeak ? 'peak' : ''}" 
                 style="--intensity: ${intensity}"
                 data-hour="${hour}"
                 data-value="${value}">
                <div class="cell-tooltip">
                    Saat ${hour}:00 - ${value} anomali
                    ${isPeak ? '(Peak Hour)' : ''}
                </div>
            </div>
        `;
    }
    html += '</div>';
    
    // Heatmap legend
    html += '<div class="heatmap-legend">';
    html += '<span class="legend-label">Az</span>';
    html += '<div class="legend-gradient"></div>';
    html += '<span class="legend-label">Çok</span>';
    html += '</div>';
    
    html += '</div></div>';
    return html;
}

/**
 * Get Component Icon
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
        'CONTROL': '🎛️'
    };
    return iconMap[component] || '📊';
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
    
    if (mlData.feature_importance && Object.keys(mlData.feature_importance).length > 0) {
        modalContent += renderFeatureImportanceChart(mlData.feature_importance);
    }
    
    if (mlData.component_analysis) {
        modalContent += renderComponentDashboard(mlData.component_analysis);
    }
    
    if (mlData.temporal_analysis?.hourly_distribution) {
        modalContent += renderTemporalHeatmap(mlData.temporal_analysis);
    }
    
    if (mlData.anomaly_score_stats && mlData.summary) {
        modalContent += renderAnomalyScoreDistribution(mlData.anomaly_score_stats, mlData.summary);
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
    
    criticalAnomalies.slice(0, 10).forEach((anomaly, index) => {
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
                    <div class="message-preview">${escapeHtml(anomaly.message || '').substring(0, 100)}...</div>
                    <button class="btn-expand" onclick="toggleMessageExpand(this)">Detay</button>
                    <div class="message-full" style="display:none">${escapeHtml(anomaly.message || '')}</div>
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
 * Security Alerts Dashboard Render Et
 */
function renderSecurityAlertsDashboard(securityAlerts) {
    let html = '<div class="security-alerts-dashboard">';
    html += '<h3>🚨 Security & Critical Alerts</h3>';
    html += '<div class="security-alerts-grid">';
    
    // Alert type mapping
    const alertTypeInfo = {
        'drop_operations': { icon: '🗑️', label: 'DROP Operations', color: '#e74c3c' },
        'shutdowns': { icon: '⏹️', label: 'Shutdown Events', color: '#34495e' },
        'assertions': { icon: '❗', label: 'Assertion Errors', color: '#e67e22' },
        'fatal_errors': { icon: '💀', label: 'Fatal Errors', color: '#c0392b' },
        'out_of_memory': { icon: '💾', label: 'Out of Memory', color: '#8e44ad' },
        'restarts': { icon: '🔄', label: 'Service Restarts', color: '#2980b9' },
        'memory_limits': { icon: '📊', label: 'Memory Limit Exceeded', color: '#f39c12' }
    };
    
    // Her alert tipini göster
    Object.entries(securityAlerts).forEach(([alertType, alertData]) => {
        const info = alertTypeInfo[alertType] || { icon: '⚠️', label: alertType, color: '#95a5a6' };
        const count = alertData.count || 0;
        
        // Kritiklik seviyesi belirleme
        let criticalityClass = 'low';
        if (alertType === 'fatal_errors' || alertType === 'out_of_memory') {
            criticalityClass = 'critical';
        } else if (alertType === 'shutdowns' || alertType === 'restarts' || alertType === 'memory_limits') {
            criticalityClass = 'high';
        } else if (count > 10) {
            criticalityClass = 'medium';
        }
        
        html += `
            <div class="security-alert-card ${criticalityClass}" onclick="showAlertDetails('${alertType}', ${JSON.stringify(alertData).replace(/"/g, '&quot;')})">
                <div class="alert-icon" style="color: ${info.color}">${info.icon}</div>
                <div class="alert-content">
                    <div class="alert-label">${info.label}</div>
                    <div class="alert-count">${count}</div>
                    ${count > 0 ? '<div class="alert-status">DETECTED</div>' : '<div class="alert-status ok">CLEAR</div>'}
                </div>
                ${alertData.indices && alertData.indices.length > 0 ? 
                    `<div class="alert-preview">İlk ${Math.min(3, alertData.indices.length)} örnek: ${alertData.indices.slice(0, 3).join(', ')}...</div>` : 
                    ''}
            </div>
        `;
    });
    
    html += '</div>';
    
    // Alert özeti
    const totalAlerts = Object.values(securityAlerts).reduce((sum, alert) => sum + (alert.count || 0), 0);
    if (totalAlerts > 0) {
        html += `<div class="security-alerts-summary">
                    <p><strong>Toplam ${totalAlerts} güvenlik/kritik olay tespit edildi.</strong></p>
                    <p>Detaylı inceleme için kartlara tıklayın.</p>
                 </div>`;
    }
    
    html += '</div>';
    return html;
}

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

// History fonksiyonları
window.replayQuery = replayQuery;
window.showHistoryDetail = showHistoryDetail;

// Anomaly fonksiyonları  
window.confirmAnomalyAnalysis = confirmAnomalyAnalysis;
window.cancelAnomalyAnalysis = cancelAnomalyAnalysis;
window.modifyAnomalyParameters = modifyAnomalyParameters;

// Export/Schedule fonksiyonları
window.exportAnomalyReport = exportAnomalyReport;
window.scheduleFollowUp = scheduleFollowUp;
window.saveFollowUp = saveFollowUp;


// Dosya yönetimi
window.deleteUploadedFile = deleteUploadedFile;

// Schema görüntüleme
window.viewSchema = viewSchema;


// Debug için fonksiyon versiyonunu logla
console.log('Global functions initialized. showHistoryDetail version check:', 
    window.showHistoryDetail.toString().includes('showHistoryDetail DEBUG') ? 'DEBUG VERSION' : 'STANDARD VERSION'
);