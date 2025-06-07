/**
 * LC Waikiki MongoDB Assistant - Frontend JavaScript
 * 
 * Bu dosya UI ile backend API arasındaki iletişimi sağlar.
 * Mevcut MongoDB Agent yapısına hiçbir müdahale yapmadan,
 * sadece API çağrıları üzerinden iletişim kurar.
 */

// Global değişkenler
let apiKey = '';
let isConnected = false;

// API endpoints
const API_BASE = window.location.origin;
const API_ENDPOINTS = {
    query: '/api/query',
    status: '/api/status',
    collections: '/api/collections',
    schema: '/api/schema'
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
    
    // Örnek sorgu chip'leri
    document.querySelectorAll('.chip').forEach(chip => {
        chip.addEventListener('click', (e) => {
            elements.queryInput.value = e.target.dataset.query;
            elements.queryInput.focus();
        });
    });
    
    // Modal kapatma
    document.querySelector('.close').addEventListener('click', closeModal);
    window.addEventListener('click', (e) => {
        if (e.target === elements.modal) closeModal();
    });
}

/**
 * İlk durum kontrolü
 */
async function checkInitialStatus() {
    try {
        const response = await fetch(API_ENDPOINTS.status);
        const data = await response.json();
        
        if (data.status === 'online') {
            updateStatus('online', 'Sistem hazır - API anahtarı ile bağlanın');
        } else {
            updateStatus('offline', 'Sistem çevrimdışı');
        }
    } catch (error) {
        updateStatus('offline', 'Bağlantı hatası');
    }
}

/**
 * API bağlantısını kur
 */
async function handleConnect() {
    const key = elements.apiKeyInput.value.trim();
    
    if (!key) {
        showNotification('Lütfen API anahtarını girin', 'error');
        return;
    }
    
    elements.connectBtn.disabled = true;
    elements.connectBtn.textContent = 'BAĞLANIYOR...';
    
    try {
        // Test için collections endpoint'ini kullan
        const response = await fetch(`${API_ENDPOINTS.collections}?api_key=${key}`);
        
        if (response.ok) {
            apiKey = key;
            isConnected = true;
            
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
            throw new Error('Geçersiz API anahtarı');
        }
    } catch (error) {
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
    
    if (!query) {
        showNotification('Lütfen bir sorgu girin', 'warning');
        return;
    }
    
    if (!isConnected) {
        showNotification('Önce bağlantı kurmalısınız', 'error');
        return;
    }
    
    // UI'yi hazırla
    showLoader(true);
    elements.queryBtn.disabled = true;
    elements.resultSection.style.display = 'none';
    
    try {
        const response = await fetch(API_ENDPOINTS.query, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                query: query,
                api_key: apiKey
            })
        });
        
        const result = await response.json();
        displayResult(result);
        
    } catch (error) {
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
    elements.resultSection.style.display = 'block';

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

// Yardımcı fonksiyon: Açıklama metnini parse et ve formatla
function parseAndFormatDescription(description) {
    let html = '';
    
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
 * Loader göster/gizle
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
    return text.replace(/[&<>"']/g, m => map[m]);
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