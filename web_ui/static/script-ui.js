// web_ui\static\script-ui.js
/**
 * MongoDB-LLM-assistant\web_ui\static\script-ui.js
 * LC Waikiki MongoDB Assistant - UI Helper Module
 * 
 * Bu modül UI ile ilgili yardımcı fonksiyonları içerir:
 * - Durum güncelleme (updateStatus)
 * - Bildirim sistemi (showNotification)
 * - Loader gösterme/gizleme
 * - Modal yönetimi
 * - HTML escape ve JSON formatlama
 * 
 * BAĞIMLILIK: script-core.js (elements objesi için)
 */

console.log('🎨 Loading script-ui.js...');

/**
 * Durum güncelleme
 * @param {string} status - Durum tipi ('online', 'offline', 'error', vb.)
 * @param {string} message - Gösterilecek mesaj
 */
function updateStatus(status, message) {
    if (!window.elements || !window.elements.statusElement) {
        console.warn('DOM elements not initialized yet');
        return;
    }
    window.elements.statusElement.className = `status ${status}`;
    window.elements.statusText.textContent = message;
}

/**
 * Bildirim göster
 * @param {string} message - Bildirim mesajı
 * @param {string} type - Bildirim tipi ('info', 'success', 'error', 'warning')
 */
function showNotification(message, type = 'info') {
    // Console'a log at
    console.log(`[${type.toUpperCase()}] ${message}`);
    
    if (!window.elements || !window.elements.statusElement) {
        console.warn('DOM elements not initialized yet');
        return;
    }
    
    // Geçici olarak status'te göster
    const originalStatus = window.elements.statusText.textContent;
    const originalClass = window.elements.statusElement.className;
    
    window.elements.statusElement.className = `status ${type}`;
    window.elements.statusText.textContent = message;
    
    setTimeout(() => {
        window.elements.statusElement.className = originalClass;
        window.elements.statusText.textContent = originalStatus;
    }, 3000);
}

/**
 * Loader göster/gizle
 * @param {boolean} show - true: göster, false: gizle
 */
function showLoader(show) {
    if (!window.elements || !window.elements.loader) {
        console.warn('DOM elements not initialized yet');
        return;
    }
    window.elements.loader.style.display = show ? 'flex' : 'none';

    // Adim listesini sifirla (acildiginda)
    if (show) {
        const steps = document.querySelectorAll('#processingSteps .processing-step');
        steps.forEach((step, i) => {
            step.className = 'processing-step ' + (i === 0 ? 'completed' : i === 1 ? 'active' : 'pending');
            const fill = step.querySelector('.step-progress-fill');
            if (fill) fill.style.width = '0%';
        });
    }
}

/**
 * Processing modal adim guncelleme
 * @param {string} stepName - Adim ismi (validation, connection, reading, feature_engineering, ml_inference)
 * @param {string} status - Durum (completed, active, pending)
 * @param {number} progress - 0-100 arasi ilerleme yuzdesi (opsiyonel)
 */
window.updateProcessingStep = function(stepName, status, progress) {
    const step = document.querySelector(`#processingSteps .processing-step[data-step="${stepName}"]`);
    if (!step) return;

    step.className = 'processing-step ' + status;

    if (status === 'completed') {
        const indicator = step.querySelector('.step-indicator');
        if (indicator) {
            indicator.className = 'step-indicator step-done';
            indicator.textContent = '✓';
        }
    }

    if (progress !== undefined) {
        const fill = step.querySelector('.step-progress-fill');
        if (fill) fill.style.width = progress + '%';
    }

    // Mesaji guncelle
    const msgEl = document.getElementById('processingMessage');
    if (msgEl) {
        const labels = {
            'validation': 'Parametreler doğrulanıyor...',
            'connection': 'Veri kaynağına bağlanılıyor...',
            'reading': 'Loglar okunuyor...',
            'feature_engineering': 'Feature engineering yapılıyor...',
            'ml_inference': 'ML modeli çalıştırılıyor...'
        };
        if (labels[stepName]) msgEl.textContent = labels[stepName];
    }
};

/**
 * Modal göster
 * @param {string} title - Modal başlığı
 * @param {string} content - Modal içeriği (HTML)
 */
function showModal(title, content) {
    if (!window.elements || !window.elements.modal) {
        console.warn('DOM elements not initialized yet');
        return;
    }
    window.elements.modalTitle.textContent = title;
    window.elements.modalBody.innerHTML = content;
    window.elements.modal.style.display = 'block';
}

/**
 * Modal kapat
 */
function closeModal() {
    if (!window.elements || !window.elements.modal) {
        console.warn('DOM elements not initialized yet');
        return;
    }
    window.elements.modal.style.display = 'none';
}

/**
 * HTML escape - XSS koruması için
 * @param {string} text - Escape edilecek metin
 * @returns {string} Escape edilmiş metin
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
 * @param {Object} obj - Formatlanacak obje
 * @returns {string} Formatlanmış ve renklendirilmiş JSON HTML
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

/**
 * Mesaj expand/collapse fonksiyonu
 */
function toggleMessageExpand(button) {
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
}

/**
 * Storage istatistiklerini göster
 */
async function showStorageStatistics() {
    try {
        const response = await fetch(`${window.API_ENDPOINTS.storageStats}?api_key=${window.apiKey}&days=30`);
        if (!response.ok) throw new Error('Failed to fetch storage stats');
        const data = await response.json();
        const stats = data.statistics || {};
        let modalContent = `<div class="storage-stats-modal">
            <h3>📊 Storage İstatistikleri (Son 30 Gün)</h3>`;

        // Analysis stats
        if (stats.analysis_stats) {
            modalContent += `<div class="stats-section">
                <h4>📈 Analiz İstatistikleri</h4>
                <div class="stats-grid">
                    <div class="stat-card">
                        <div class="stat-value">${stats.analysis_stats.total_analyses || 0}</div>
                        <div class="stat-label">Toplam Analiz</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">${stats.analysis_stats.total_anomalies || 0}</div>
                        <div class="stat-label">Tespit Edilen Anomali</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">${stats.analysis_stats.avg_anomaly_rate || 0}%</div>
                        <div class="stat-label">Ortalama Anomali Oranı</div>
                    </div>
                </div>
            </div>`;
        }

        // Storage stats
        if (stats.storage_stats) {
            modalContent += `<div class="stats-section">
                <h4>💾 Storage Kullanımı</h4>
                <div class="stats-grid">
                    <div class="stat-card">
                        <div class="stat-value">${stats.storage_stats.total_size_mb || 0} MB</div>
                        <div class="stat-label">Toplam Boyut</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">${stats.storage_stats.file_counts?.exports || 0}</div>
                        <div class="stat-label">Export Dosyası</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">${stats.storage_stats.file_counts?.models || 0}</div>
                        <div class="stat-label">Model Versiyonu</div>
                    </div>
                </div>
            </div>`;
        }

        modalContent += '</div>';
        showModal('Storage İstatistikleri', modalContent);
    } catch (error) {
        console.error('[STORAGE] Error loading storage statistics:', error);
        showNotification('Storage istatistikleri yüklenemedi', 'error');
    }
}

/**
 * Model registry'yi göster
 */
async function showModelRegistry() {
    try {
        const response = await fetch(`${window.API_ENDPOINTS.modelRegistry}?api_key=${window.apiKey}`);
        if (!response.ok) throw new Error('Failed to fetch model registry');
        const data = await response.json();
        let modalContent = `<div class="model-registry-modal">
            <h3>🤖 Model Registry</h3>`;

        if (Array.isArray(data.models) && data.models.length > 0) {
            modalContent += `
                <table class="model-table">
                    <thead>
                        <tr>
                            <th>Version</th>
                            <th>Type</th>
                            <th>Features</th>
                            <th>Created</th>
                            <th>Status</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>`;
            data.models.forEach(model => {
                const isActive = model.is_active;
                const statusClass = isActive ? 'active' : 'inactive';
                const statusText = isActive ? 'Active' : 'Inactive';
                modalContent += `
                        <tr>
                            <td><strong>${model.version}</strong></td>
                            <td>${model.model_type}</td>
                            <td>${model.n_features || 0}</td>
                            <td>${model.created_at ? new Date(model.created_at).toLocaleDateString('tr-TR') : '-'}</td>
                            <td><span class="status-badge ${statusClass}">${statusText}</span></td>
                            <td>
                                ${!isActive
                                    ? `<button class="btn-small" onclick="window.activateModel('${model.version}')">Activate</button>`
                                    : ''}
                            </td>
                        </tr>`;
            });
            modalContent += `</tbody></table>`;
        } else {
            modalContent += '<p>Henüz kayıtlı model bulunmuyor.</p>';
        }

        modalContent += '</div>';
        showModal('Model Registry', modalContent);
    } catch (error) {
        console.error('[MODEL REGISTRY] Error loading model registry:', error);
        showNotification('Model registry yüklenemedi', 'error');
    }
}

/**
 * Storage menüsünü toggle et
 */
function toggleStorageMenu() {
    const menu = document.getElementById('storageMenu');
    if (menu) {
        menu.style.display = menu.style.display === 'none' ? 'block' : 'none';
    }
}

/**
 * Sayfa yüklendiğinde storage butonlarını ekle
 */
function addStorageMenuButtons() {
    const quickActions = document.querySelector('.quick-actions');
    if (quickActions && window.isConnected) {
        // Storage dropdown menü ekle
        const storageDropdown = document.createElement('div');
        storageDropdown.className = 'storage-dropdown';
        storageDropdown.innerHTML = `
            <button class="btn btn-secondary dropdown-toggle" onclick="window.toggleStorageMenu()">
                💾 STORAGE
            </button>
            <div class="storage-menu" id="storageMenu" style="display: none;">
                <button onclick="window.showStorageStatistics()">📊 İstatistikler</button>
                <button onclick="window.showModelRegistry()">🤖 Model Registry</button>
                <button onclick="window.loadMongoDBHistory()">📜 Geçmiş Analizler</button>
                <button onclick="window.performStorageCleanup()">🗑️ Temizlik</button>
            </div>
        `;
        quickActions.appendChild(storageDropdown);
    }
}

/**
 * Basit metrik sonucu mu kontrol et
 */
function isSimpleMetricResult(result) {
    // Eğer sonuç sadece birkaç basit metrik içeriyorsa JSON gösterme
    if (result.intermediate_steps && result.tools_used && Object.keys(result).length <= 3) {
        return true;
    }
    return false;
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
 * Timestamp formatla (Türkçe)
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
 * Ekranı temizle
 */
function handleClear() {
    if (window.elements) {
        window.elements.queryInput.value = '';
        window.elements.resultSection.style.display = 'none';
        window.elements.resultContent.innerHTML = '';
    }
    showNotification('Ekran temizlendi', 'info');
}

/**
 * Metrik kutusunu formatla
 */
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
        // Anahtar:değer formatında değilse, metni kaçışlayıp döndür
        return `
            <div class="metric-box ${className}">
                <div class="metric-icon">${icon}</div>
                <div class="metric-content">
                    <div class="metric-label">${escapeHtml(text)}</div>
                </div>
            </div>
        `;
    }
}

/**
 * Anomali görünüm modunu değiştir
 */
function toggleViewMode(mode) {
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
}

/**
 * Dosya yükleme işlemi - Progress Bar Destekli (XHR)
 */
function handleFileUpload(event) {
    const file = event.target.files[0];
    if (!file) {
        console.log('No file selected');
        return;
    }

    console.log('File selected:', file.name, file.size, 'bytes');

    // Dosya boyutu kontrolü (1GB limit)
    const maxSize = 1024 * 1024 * 1024; // 1GB
    if (file.size > maxSize) {
        showNotification('Dosya boyutu 1GB\'dan büyük olamaz', 'error');
        event.target.value = ''; // Input'u temizle
        return;
    }

    // UI: Dropzone'u Progress Bar'a dönüştür
    const dropzone = document.getElementById('uploadDropzone');
    let originalContent = '';
    
    if (dropzone) {
        originalContent = dropzone.innerHTML;
        dropzone.innerHTML = `
            <div class="upload-progress-container" style="text-align: center; padding: 15px; color: #0047BA;">
                <div class="spinner" style="margin: 0 auto 10px; width: 30px; height: 30px; border-width: 3px;"></div>
                <p style="margin: 5px 0; font-weight: bold; font-size: 0.9em;">Yükleniyor...</p>
                <p style="margin: 0; font-size: 0.8em; color: #666; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 100%;">${window.escapeHtml(file.name)}</p>
                
                <div class="progress-bar-bg" style="background: #e0e0e0; height: 8px; border-radius: 4px; width: 100%; margin-top: 15px; overflow: hidden;">
                    <div id="uploadProgressBar" style="background: #27ae60; height: 100%; width: 0%; transition: width 0.1s linear;"></div>
                </div>
                <p id="uploadStatusText" style="font-size: 0.8em; color: #888; margin-top: 5px;">%0</p>
            </div>
        `;
    } else {
        // Fallback: Dropzone yoksa normal loader
        showLoader(true);
    }

    const formData = new FormData();
    formData.append('file', file);

    const xhr = new XMLHttpRequest();
    // URL param olarak API key ekle
    xhr.open('POST', `${window.API_ENDPOINTS.uploadLog}?api_key=${encodeURIComponent(window.apiKey)}`, true);

    // Progress Event
    xhr.upload.onprogress = function(e) {
        if (e.lengthComputable) {
            const percentComplete = Math.round((e.loaded / e.total) * 100);
            
            const progressBar = document.getElementById('uploadProgressBar');
            const statusText = document.getElementById('uploadStatusText');
            
            if (progressBar) progressBar.style.width = `${percentComplete}%`;
            if (statusText) statusText.textContent = `%${percentComplete}`;
        }
    };

    // Load Event (Success/Error)
    xhr.onload = async function() {
        if (dropzone) showLoader(false); // Fallback loader'ı kapat

        if (xhr.status === 200) {
            try {
                const data = JSON.parse(xhr.responseText);
                console.log('Upload success:', data);

                // UI: Başarılı Mesajı
                if (dropzone) {
                    dropzone.innerHTML = `
                        <div style="text-align: center; color: #27ae60; padding: 20px; animation: fadeIn 0.3s;">
                            <div style="font-size: 40px; margin-bottom: 10px;">✅</div>
                            <p style="font-weight: bold; margin: 5px 0;">Yükleme Başarılı!</p>
                            <p style="font-size: 0.8em; color: #555;">${window.escapeHtml(data.filename)}</p>
                        </div>
                    `;
                }
                showNotification('Dosya başarıyla yüklendi!', 'success');

                // Dosya listesini güncelle
                await window.updateUploadedFilesList();

                // Anomali modal açıksa, yeni dosyayı otomatik seç
                // Backend 'file_path' dönüyor, listedeki 'path' ile eşleşmeli
                const savedPath = data.file_path || data.path; 
                
                // Modal ve Radio button seçimi
                setTimeout(() => {
                    const newFileRadio = document.querySelector(`input[name="logFile"][value="${savedPath}"]`);
                    if (newFileRadio) {
                        newFileRadio.checked = true;
                        // Seçimi tetikle
                        newFileRadio.dispatchEvent(new Event('change', { bubbles: true }));
                        
                        // Validasyonu tetikle
                        if (typeof window.validateAnalysisButton === 'function') {
                            window.validateAnalysisButton();
                        }
                    }
                    
                    // 3 Saniye sonra Dropzone'u eski haline getir
                    if (dropzone) {
                        dropzone.innerHTML = originalContent;
                    }
                }, 2000);

            } catch (e) {
                console.error('JSON Parse error:', e);
                handleError('Sunucu yanıtı işlenemedi.');
            }
        } else {
            let errorMsg = 'Yükleme başarısız.';
            try {
                const errData = JSON.parse(xhr.responseText);
                errorMsg = errData.detail || errorMsg;
            } catch (e) {}
            handleError(errorMsg);
        }
        
        // Input'u temizle ki aynı dosya tekrar seçilebilsin
        event.target.value = '';
    };

    // Error Event (Network)
    xhr.onerror = function() {
        handleError('Ağ hatası oluştu.');
        event.target.value = '';
    };

    // Hata Yönetimi Yardımcısı
    function handleError(msg) {
        console.error('Upload error:', msg);
        showNotification(msg, 'error');
        
        if (dropzone) {
            dropzone.innerHTML = `
                <div style="text-align: center; color: #c0392b; padding: 20px;">
                    <div style="font-size: 40px; margin-bottom: 10px;">❌</div>
                    <p style="font-weight: bold;">Hata!</p>
                    <p style="font-size: 0.9em;">${window.escapeHtml(msg)}</p>
                </div>
            `;
            // 3 sn sonra reset
            setTimeout(() => {
                dropzone.innerHTML = originalContent;
            }, 3000);
        } else {
            showLoader(false);
        }
    }

    xhr.send(formData);
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
        const response = await fetch(`${window.API_ENDPOINTS.uploadedLogs}?api_key=${window.apiKey}`);
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
                    <button class="delete-file-btn" onclick="window.deleteUploadedFile('${log.filename}')">🗑️</button>
                `;
                fileList.appendChild(fileItem);
            });

            // Seçimi geri yükle
            if (currentSelection) {
                const radio = document.querySelector(`input[name="logFile"][value="${currentSelection}"]`);
                if (radio) {
                    radio.checked = true;
                    // Upload source ise validation'ı tetikle
                    if (window.selectedDataSource === 'upload') {
                        window.validateAnalysisButton();
                    }
                } else if (window.selectedDataSource === 'upload' && data.logs.length > 0) {
                    // İlk açılışta ve dosya varsa, ilk dosyayı otomatik seç
                    const firstRadio = document.querySelector('input[name="logFile"]');
                    if (firstRadio) {
                        firstRadio.checked = true;
                        console.log('Auto-selected first file:', firstRadio.value);
                        window.validateAnalysisButton();
                    }
                }
            } else if (window.selectedDataSource === 'upload' && data.logs.length > 0) {
                // İlk açılışta ve dosya varsa, ilk dosyayı otomatik seç
                const firstRadio = document.querySelector('input[name="logFile"]');
                if (firstRadio) {
                    firstRadio.checked = true;
                    console.log('Auto-selected first file:', firstRadio.value);
                    window.validateAnalysisButton();
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
 * Veri kaynağı input alanlarını güncelle
 */
function updateSourceInputs(source) {
    console.log('updateSourceInputs called with source:', source);
    
    // GÜVENLİ: Sadece HTML'de VAR OLAN elementlere erişim
    const uploadInputs = document.getElementById('uploadSourceInputs');
    const fileSelection = document.getElementById('fileSelectionSection');
    const opensearchInputs = document.getElementById('opensearchSourceInputs');
    const mssqlInputs = document.getElementById('mssqlSourceInputs');
    const esInputs = document.getElementById('elasticsearchSourceInputs');

    // Tüm input alanlarını gizle
    if (uploadInputs) uploadInputs.style.display = 'none';
    if (fileSelection) fileSelection.style.display = 'none';
    if (opensearchInputs) opensearchInputs.style.display = 'none';
    if (mssqlInputs) mssqlInputs.style.display = 'none';
    if (esInputs) esInputs.style.display = 'none';
    
    // Seçilen kaynağa göre göster
    switch(source) {
        case 'upload':
            console.log('Showing upload source inputs');
            if (uploadInputs) uploadInputs.style.display = 'block';
            if (fileSelection) fileSelection.style.display = 'block';
            break;
            
        case 'opensearch':
            console.log('Showing OpenSearch source inputs');
            if (opensearchInputs) opensearchInputs.style.display = 'block';
            
            // Default olarak single mode seçili olsun
            const singleModeRadio = document.querySelector('input[name="hostSelectionMode"][value="single"]');
            if (singleModeRadio) {
                singleModeRadio.checked = true;
            }
            
            // Single mode UI'ını göster
            const singleHostDiv = document.getElementById('singleHostSelection');
            const clusterDiv = document.getElementById('clusterSelection');
            if (singleHostDiv) singleHostDiv.style.display = 'block';
            if (clusterDiv) clusterDiv.style.display = 'none';
            
            // MongoDB sunucularını yükle (single mode için)
            if (window.loadMongoDBHosts) {
                window.loadMongoDBHosts();
            }
            
            // Cluster listesini de arka planda yükle
            setTimeout(() => {
                if (window.loadClusters) {
                    window.loadClusters();
                }
            }, 500);
            break;

        case 'mssql_opensearch':
            console.log('Showing MSSQL OpenSearch source inputs');
            if (mssqlInputs) mssqlInputs.style.display = 'block';

            // MSSQL sunucularını yükle
            if (window.loadMSSQLHosts) {
                window.loadMSSQLHosts();
            }
            break;

        case 'elasticsearch_opensearch':
            console.log('Showing Elasticsearch source inputs');
            if (esInputs) esInputs.style.display = 'block';

            // Elasticsearch node'larını yükle
            if (window.loadESHosts) {
                window.loadESHosts();
            }
            break;

        default:
            console.log('Unknown source type:', source);
    }

    // ===== Zaman Filtresi UI Yönetimi =====
    const timeOptionsGrid = document.querySelector('.analysis-options .options-grid');
    const timeOptionsTitle = document.querySelector('.analysis-options h4');
    const customDateSection = document.getElementById('customDateInputs');
    const startBtn = document.getElementById('startAnalysisBtn');

    // Eski bilgilendirme mesajını temizle
    const existingMsg = document.getElementById('upload-mode-info');
    if (existingMsg) existingMsg.remove();

    if (source === 'upload') {
        // Upload: Zaman filtrelerini gizle
        if (timeOptionsGrid) timeOptionsGrid.style.display = 'none';
        if (customDateSection) customDateSection.style.display = 'none';
        if (timeOptionsTitle && timeOptionsTitle.textContent.includes('Analiz Seçenekleri')) {
            timeOptionsTitle.style.display = 'none';
        }

        // Bilgilendirme mesajı ekle
        const msg = document.createElement('div');
        msg.id = 'upload-mode-info';
        msg.style.cssText = 'background: #e3f2fd; color: #0d47a1; padding: 15px; border-radius: 8px; margin: 15px 0; font-size: 0.95em; border-left: 5px solid #2196f3; display: flex; align-items: center; gap: 10px;';
        msg.innerHTML = '<span style="font-size: 1.5em;">ℹ️</span> <div><strong>Tam Dosya Analizi Modu</strong><br><span style="font-size: 0.9em; opacity: 0.9;">Yüklediğiniz dosyanın tamamı analiz edilecektir.</span></div>';
        
        if (startBtn && startBtn.parentNode) {
            startBtn.parentNode.insertBefore(msg, startBtn);
        }
    } else {
        // OpenSearch: Zaman filtrelerini göster
        if (timeOptionsGrid) timeOptionsGrid.style.display = '';
        if (timeOptionsTitle) timeOptionsTitle.style.display = '';

        // Custom date kontrolü
        const customRadio = document.querySelector('input[name="modalTimeRange"][value="custom"]');
        if (customDateSection && customRadio) {
            customDateSection.style.display = customRadio.checked ? 'block' : 'none';
        }
    }
    
    // Validation güncelle
    if (window.validateAnalysisButton) {
        window.validateAnalysisButton();
    }
}

/**
 * Analiz butonu validasyonu
 */
function validateAnalysisButton() {
    console.log('validateAnalysisButton called for source:', window.selectedDataSource); // DEBUG LOG
    
    const startBtn = document.getElementById('startAnalysisBtn');
    if (!startBtn) {
        console.log('startAnalysisBtn element not found!'); // DEBUG LOG
        return;
    }
    
    let isValid = false;
    
    switch(window.selectedDataSource) {
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
        case 'mssql_opensearch':
            // MSSQL OpenSearch - sunucu seçildi mi kontrol et
            const mssqlHost = document.getElementById('mssqlHostSelect')?.value;
            isValid = mssqlHost && mssqlHost.length > 0;
            console.log('MSSQL OpenSearch - selected host:', mssqlHost, 'isValid:', isValid);
            break;
        default:
            console.log('Unknown data source for validation:', window.selectedDataSource); // DEBUG LOG
    }
    
    startBtn.disabled = !isValid;
    console.log('Analysis button disabled:', !isValid); // DEBUG LOG
}

/**
 * Açıklama metnini parse et ve formatla
 */
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

/**
 * ML Insights Summary Render Et (UI)
 */
function renderMLInsightsSummary(mlData) {
    let html = '<div class="ml-insights-summary">';
    html += '<h3>💡 ML Model Insights</h3>';
    html += '<div class="insights-grid">';
    
    // Key Insights (business logic'den al)
    const insights = window.generateMLInsights(mlData);  // ✅ window. kullan - başka dosya
    
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
 * Security Alerts Dashboard Render Et (UI)
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
            if (b.data.count !== a.data.count) {
                return b.data.count - a.data.count;
            }
            return b.info.priority - a.info.priority;
        });
    
    if (sortedAlerts.some(alert => alert.data.count > 0)) {
        html += '<div class="priority-alert-list">';
        
        sortedAlerts.forEach(({ type, data, info }) => {
            const count = data.count || 0;
            
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
                            <div class="alert-count-label">Olay</div>
                        </div>
                        ${count > 0 ? `
                            <div class="alert-item-actions">
                                <button class="alert-action-btn" onclick="window.investigateAlertType('${type}')">
                                    🔍 İncele
                                </button>
                                <button class="alert-action-btn" onclick="window.showAlertTimeline('${type}')">
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
        html += '<div class="no-alerts-state">';
        html += '<div class="no-alerts-icon">✅</div>';
        html += '<div class="no-alerts-title">Güvenlik Olayı Tespit Edilmedi</div>';
        html += '<div class="no-alerts-message">Analiz edilen log\'larda kritik güvenlik olayı bulunmamaktadır.</div>';
        html += '</div>';
    }
    
    html += '</div>';
    return html;
}

/**
 * Kritik anomali mesajları toggle (UI)
 */
function toggleCriticalAnomalyMessages() {
    const toggle = document.getElementById('criticalMessageToggle');
    const isFormatted = toggle.checked;
    
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
    
    localStorage.setItem('showFormattedMessages', isFormatted.toString());
}

/**
 * Detaylı anomali mesajları toggle (UI)
 */
function toggleDetailedAnomalyMessages() {
    const toggle = document.getElementById('detailedMessageToggle');
    const isFormatted = toggle.checked;
    
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
    
    localStorage.setItem('showFormattedMessages', isFormatted.toString());
}


// ============================================
// GLOBAL ERİŞİM İÇİN WINDOW'A ATAMA
// ============================================
window.updateStatus = updateStatus;
window.showNotification = showNotification;
window.showLoader = showLoader;
window.showModal = showModal;
window.closeModal = closeModal;
window.escapeHtml = escapeHtml;
window.formatJSON = formatJSON;
window.toggleMessageExpand = toggleMessageExpand;
window.showStorageStatistics = showStorageStatistics;
window.showModelRegistry = showModelRegistry;
window.toggleStorageMenu = toggleStorageMenu;
window.addStorageMenuButtons = addStorageMenuButtons;
window.isSimpleMetricResult = isSimpleMetricResult;
window.formatFileSize = formatFileSize;
window.formatTimestamp = formatTimestamp;
window.handleClear = handleClear;
window.formatMetricBox = formatMetricBox;
window.toggleViewMode = toggleViewMode;
window.handleFileUpload = handleFileUpload;
window.updateUploadedFilesList = updateUploadedFilesList;
window.updateSourceInputs = updateSourceInputs;
window.validateAnalysisButton = validateAnalysisButton;
window.parseAndFormatDescription = parseAndFormatDescription;
window.renderMLInsightsSummary = renderMLInsightsSummary;
window.renderSecurityAlertsDashboard = renderSecurityAlertsDashboard;
window.toggleCriticalAnomalyMessages = toggleCriticalAnomalyMessages;
window.toggleDetailedAnomalyMessages = toggleDetailedAnomalyMessages;

console.log('✅ UI module loaded successfully');

