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
    deleteUploadedLog: '/api/uploaded-log'     // YENİ
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
        
        displayResult(result);
        
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
 * Sonucu görüntüle - GELİŞTİRİLMİŞ VERSİYON
 */
function displayResult(result) {
    console.log('displayResult called with result type:', result.işlem || 'unknown'); // DEBUG LOG
    
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
        default:
            console.log('Unknown source type:', source); // DEBUG LOG
    }
    
    // Analiz butonunu güncelle
    validateAnalysisButton();
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
    
    // Veri kaynağına göre parametreleri hazırla
    let requestData = {
        api_key: apiKey,
        time_range: timeRange,
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
        default:
            console.log('Unknown data source for analysis:', selectedDataSource); // DEBUG LOG
    }
    
    console.log('Request Data:', requestData); // DEBUG LOG

    closeAnomalyModal();
    showLoader();
    
    try {
        console.log('Sending analysis request to API...'); // DEBUG LOG
        const response = await fetch(API_ENDPOINTS.analyzeLog, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(requestData)
        });
        
        console.log('Analysis response status:', response.status); // DEBUG LOG
        
        const result = await response.json();
        console.log('Analysis result received:', result); // DEBUG LOG
        
        displayAnomalyResults(result);
    } catch (error) {
        console.error('Analiz hatası:', error);
        console.error('Analysis request failed:', error); // DEBUG LOG
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
 * Anomaly analiz sonuçlarını görüntüle
 */
function displayAnomalyResults(result) {
    console.log('displayAnomalyResults called with result:', result); // DEBUG LOG
    
    // Eğer açıklama varsa ve summary yoksa, text formatında göster
    if (result.açıklama && !result.summary) {
        const formattedText = result.açıklama
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')  // Bold text
            .replace(/### (.*?)$/gm, '<h3>$1</h3>')           // Headers
            .replace(/- /g, '• ')                              // List items
            .replace(/\n/g, '<br>');                          // Line breaks
            
        showModal('Anomaly Analiz Sonuçları', 
            `<div class="anomaly-text-results">
                <div class="formatted-anomaly-text">${formattedText}</div>
            </div>`
        );
        return;
    }
    
    // Ana sonuç container'ı oluştur
    let html = '<div class="anomaly-results">';
    
    // Başlık ve özet bilgi
    html += '<div class="anomaly-header">';
    html += '<h2>🔍 Anomaly Analiz Sonuçları</h2>';
    
    if (result.summary) {
        console.log('Result summary found:', result.summary); // DEBUG LOG
        html += '<div class="anomaly-summary">';
        html += `<p><strong>Toplam Log:</strong> ${result.summary.total_logs || 0}</p>`;
        html += `<p><strong>Anomali Sayısı:</strong> ${result.summary.anomaly_count || 0}</p>`;
        html += `<p><strong>Anomali Oranı:</strong> %${((result.summary.anomaly_count / result.summary.total_logs) * 100).toFixed(2)}</p>`;
        html += '</div>';
    } else {
        console.log('No summary found in result'); // DEBUG LOG
    }
    
    // Kritik anomaliler
    if (result.critical_anomalies && result.critical_anomalies.length > 0) {
        html += '<div class="critical-anomalies-section">';
        html += '<h3>⚠️ Kritik Anomaliler</h3>';
        html += '<div class="anomaly-list">';
        
        result.critical_anomalies.forEach(anomaly => {
            html += `
                <div class="anomaly-item critical">
                    <div class="anomaly-score">${anomaly.anomaly_score.toFixed(3)}</div>
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
    
    // Tüm anomaliler
    if (result.anomalies && result.anomalies.length > 0) {
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
    if (result.component_stats) {
        html += '<div class="component-stats-section">';
        html += '<h3>📈 Component Dağılımı</h3>';
        html += '<div class="component-grid">';
        
        Object.entries(result.component_stats).forEach(([component, count]) => {
            const percentage = ((count / result.summary.anomaly_count) * 100).toFixed(1);
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
        console.log('Error result detected:', result.açıklama); // DEBUG LOG
        html = '<div class="anomaly-error">';
        html += '<h3>❌ Hata</h3>';
        html += `<p>${escapeHtml(result.açıklama || "Bilinmeyen hata")}</p>`;
        html += '</div>';
    }
    
    html += '</div>';
    
    // Sonuçları göster
    console.log('Showing modal with anomaly results'); // DEBUG LOG
    showModal('Anomaly Analiz Sonuçları', html);
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
    const k = 1024;
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

// Global fonksiyon olarak tanımla
window.deleteUploadedFile = deleteUploadedFile;

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