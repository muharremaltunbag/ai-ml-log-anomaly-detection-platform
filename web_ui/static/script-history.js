// web_ui\static\script-history.js
/**
 * MongoDB-LLM-assistant\web_ui\static\script-history.js
 * LC Waikiki MongoDB Assistant - History Management Module
 * 
 * Bu modül konuşma geçmişi yönetimi ile ilgili tüm fonksiyonları içerir:
 * - History yükleme/kaydetme (MongoDB entegrasyonu)
 * - History görüntüleme ve filtreleme
 * - DBA history entegrasyonu
 * - History detay gösterimi
 * - Export/Import işlemleri
 * 
 * BAĞIMLILIKLAR:
 * - script-core.js (global değişkenler)
 * - script-ui.js (UI helpers)
 */

console.log('📚 Loading script-history.js...');

// ===== KONUŞMA GEÇMİŞİ YÖNETİMİ =====

/**
 * Geçmişi yükle - MongoDB entegrasyonu ile
 */
async function loadHistory() {
    try {
        // SADECE MongoDB'den yükle
        if (window.isConnected && window.apiKey) {
            console.log('Loading query history from MongoDB...');
            
            const response = await fetch(`/api/query-history/load?api_key=${window.apiKey}&limit=50`);
            
            if (response.ok) {
                const data = await response.json();
                
                if (data.status === 'success' && data.history) {
                    window.queryHistory = data.history;
                    console.log(`✅ Loaded ${data.count} items from MongoDB`);
                    updateHistoryDisplay();
                    return;
                }
            }
        } else {
            // MongoDB bağlantısı yoksa boş başla
            window.queryHistory = [];
            console.log('⚠️ MongoDB not connected, starting with empty history');
        }
    } catch (e) {
        console.error('MongoDB yükleme hatası:', e);
        window.queryHistory = [];
    }
}

/**
 * MongoDB geçmişini local history ile birleştir
 */
function mergeHistoryWithMongoDB(mongoHistory) {
    console.log('Merging MongoDB history, items:', mongoHistory.length);
    
    if (!mongoHistory || mongoHistory.length === 0) {
        console.log('No MongoDB history to merge');
        return;
    }
    
    mongoHistory.forEach(mongoItem => {
        // Debug için veri yapısını logla
        console.log('Processing MongoDB item:', mongoItem.analysis_id);
        
        // Local history'de yoksa ekle
        const exists = window.queryHistory.find(h => 
            h.storage_id === mongoItem.analysis_id ||
            (h.timestamp && mongoItem.timestamp && 
             new Date(h.timestamp).getTime() === new Date(mongoItem.timestamp).getTime())
        );
        
        if (!exists) {
            // Summary ve source verilerini çıkar
            const summary = mongoItem.summary || {};
            const source = mongoItem.source || {};
            
            // ✅ ÖNEMLİ: Doğru anomali alanlarını kullan
            const criticalAnomalies = mongoItem.critical_anomalies_full || 
                                     mongoItem.critical_anomalies || 
                                     mongoItem.critical_anomalies_display || 
                                     [];
            
            const unfilteredAnomalies = mongoItem.unfiltered_anomalies || 
                                        mongoItem.critical_anomalies_full || 
                                        [];
            
            // MongoDB verisini local format'a çevir
            const historyItem = {
                id: Date.now() + Math.random(),
                timestamp: mongoItem.timestamp,
                query: source.host ? 
                    `Anomali Analizi: ${source.host}` : 
                    'MongoDB Anomaly Analysis',
                type: 'anomaly',
                category: 'anomaly',
                result: {
                    durum: 'tamamlandı',
                    işlem: 'anomaly_analysis',
                    sonuç: {
                        critical_anomalies: criticalAnomalies,
                        unfiltered_anomalies: unfilteredAnomalies,
                        anomaly_count: summary.n_anomalies || mongoItem.anomaly_count || 0,
                        total_logs: summary.total_logs || mongoItem.logs_analyzed || 0,
                        anomaly_rate: summary.anomaly_rate || mongoItem.anomaly_rate || 0,
                        summary: summary
                    }
                },
                // ✅ childResult ekle (showHistoryDetail için)
                childResult: {
                    durum: 'tamamlandı',
                    işlem: 'anomaly_analysis',
                    sonuç: {
                        critical_anomalies: criticalAnomalies,
                        summary: summary
                    }
                },
                storage_id: mongoItem.analysis_id,
                fromMongoDB: true,
                hasResult: true,
                host: source.host || mongoItem.host,
                source_type: source.type || source.source_type
            };
            
            window.queryHistory.push(historyItem);
            console.log(`Added MongoDB item to history: ${historyItem.query} (${criticalAnomalies.length} anomalies)`);
        } else {
            console.log('Item already exists in history:', mongoItem.analysis_id);
        }
    });
    
    // Tarihe göre sırala
    window.queryHistory.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
    
    // Limit uygula
    if (window.queryHistory.length > window.MAX_HISTORY_ITEMS) {
        window.queryHistory = window.queryHistory.slice(0, window.MAX_HISTORY_ITEMS);
    }
    
    updateHistoryDisplay();
    console.log('History merge complete. Total items:', window.queryHistory.length);
}

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
        session_id: window.currentSessionId,
        page_load_time: window.performance?.timing?.loadEventEnd - window.performance?.timing?.navigationStart,
        
        // Anomaly tracking
        isAnomalyQuery: type === 'anomaly' || result.işlem === 'anomaly_analysis',
        anomalyCount: result.sonuç?.critical_anomalies?.length || 0
    };
    
    // En başa ekle
    window.queryHistory.unshift(historyItem);
    
    // Maksimum sayıyı kontrol et
    if (window.queryHistory.length > window.MAX_HISTORY_ITEMS) {
        window.queryHistory = window.queryHistory.slice(0, window.MAX_HISTORY_ITEMS);
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
        
        if (window.isConnected && window.apiKey && window.queryHistory.length > 0) {
            const lastItem = window.queryHistory[0];
            
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
                    api_key: window.apiKey,
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
        window.showNotification('Veri MongoDB\'ye kaydedilemedi. Bağlantıyı kontrol edin.', 'error');
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
        const response = await fetch(`/api/query-history/verify/${queryId}?api_key=${window.apiKey}`);
        
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
    if (!window.isConnected || !window.apiKey) return;

    console.log('🔄 Syncing unsaved history items to MongoDB...');

    const unsavedItems = window.queryHistory.filter(item => !item.fromMongoDB);

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
                    api_key: window.apiKey,
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
        window.showNotification(`${savedCount} kayıt MongoDB\'ye senkronize edildi`, 'success');
    }
}

// Sayfa yüklendiğinde veya bağlantı kurulduğunda sync'i çalıştır
window.addEventListener('load', () => {
    setTimeout(() => {
        if (window.isConnected) {
            syncUnsavedHistoryItems();
        }
    }, 5000); // 5 saniye sonra sync
});

/**
 * Tek bir item'ı MongoDB'ye kaydet
 */
async function syncSingleItem(itemId) {
    const item = window.queryHistory.find(h => h.id === itemId);
    if (!item || item.fromMongoDB) return;
    
    try {
        const response = await fetch('/api/query-history/save', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                ...item,
                api_key: window.apiKey,
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
            window.updateHistoryDisplay();
        }
    } catch (error) {
        console.error('Sync error:', error);
        showNotification('Kayıt başarısız', 'error');
    }
}

/**
 * Geçmiş görüntüsünü güncelle - MongoDB desteği ile
 */
function updateHistoryDisplay(filter = 'all') {
    const historyContent = document.getElementById('historyContent');
    if (!historyContent) return;

    // MongoDB'den gelen veri sayısını göster
    console.log(`📊 Updating history display - Total items: ${window.queryHistory.length}`);
    console.log(`   Filter: ${filter}`);
    console.log(`   MongoDB items: ${window.queryHistory.filter(h => h.fromMongoDB).length}`);
    console.log(`   Anomaly items: ${window.queryHistory.filter(h => h.type === 'anomaly').length}`);
    console.log(`   Chatbot items: ${window.queryHistory.filter(h => h.type === 'chatbot').length}`);

    // Filtreleme - DÜZELTME BURADA
    let filteredHistory = [];

    if (filter === 'all') {
        filteredHistory = window.queryHistory;
    } 
    else if (filter === 'chatbot') {
        filteredHistory = window.queryHistory.filter(item => {
            // Sadece chatbot type ve anomaly category'si OLMAYANLAR
            return item.type === 'chatbot' && 
                   item.category !== 'anomaly' && 
                   item.subType !== 'DBA';
        });
    } 
    else if (filter === 'anomaly') {
        filteredHistory = window.queryHistory.filter(item => {
            // Anomaly veya DBA olan her şey
            return item.type === 'anomaly' || 
                   item.category === 'anomaly' ||
                   item.subType === 'DBA' ||
                   item.isAnomalyParent === true;
        });
    }

    console.log(`   Filtered items: ${filteredHistory.length}`);

    // MongoDB sync durumunu göster
    const unsyncedCount = window.queryHistory.filter(h => !h.fromMongoDB).length;
    if (unsyncedCount > 0) {
        console.warn(`⚠️ ${unsyncedCount} items not synced to MongoDB`);
    }

    if (filteredHistory.length === 0) {
        historyContent.innerHTML = `
            <div class="history-empty">
                <p>Bu kategoride geçmiş bulunmuyor.</p>
                <small>${window.isConnected ? 'MongoDB\'den veri yükleniyor...' : 'MongoDB bağlantısı bekleniyor...'}</small>
                ${window.isConnected ? '<button class="btn-small" onclick="window.reloadAllHistory()">🔄 Yeniden Yükle</button>' : ''}
            </div>
        `;
        return;
    }

    let html = '<div class="history-list">';

    // MongoDB sync durumu göstergesi
    if (window.isConnected) {
        const syncedCount = filteredHistory.filter(h => h.fromMongoDB).length;
        const totalCount = filteredHistory.length;
        const syncPercentage = totalCount > 0 ? ((syncedCount / totalCount) * 100).toFixed(0) : 0;

        html += `
            <div class="mongodb-sync-status">
                <span class="sync-indicator ${syncPercentage == 100 ? 'synced' : 'partial'}">
                    💾 MongoDB Sync: ${syncedCount}/${totalCount} (${syncPercentage}%)
                </span>
                ${unsyncedCount > 0 ? `
                    <button class="btn-sync" onclick="window.syncUnsavedHistoryItems()">
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
                <div class="history-query">${window.escapeHtml(item.query)}</div>
                ${item.id ? `<div class="history-id">ID: ${item.id}</div>` : ''}
                <div class="history-actions">
                    ${!item.parentId ? `
                        <button class="btn-small" onclick="window.replayQuery('${String(item.id).replace(/'/g, "\\'")}')" >
                            🔄 Tekrar Çalıştır
                        </button>
                    ` : ''}
                    <button class="btn-small" onclick="window.showHistoryDetail('${String(item.id).replace(/'/g, "\\'")}')" >
                        ${item.hasResult && item.childResult ? '📊 Sonuçları Göster' : '👁️ Detay'}
                    </button>
                    ${!item.fromMongoDB ? `
                        <button class="btn-small" onclick="window.syncSingleItem('${String(item.id).replace(/'/g, "\\'")}')">
                            💾 MongoDB'ye Kaydet
                        </button>
                    ` : ''}
                </div>
            </div>
        `;
    });

    html += '</div>';
    historyContent.innerHTML = html;
};

/**
 * Tüm history'yi MongoDB'den yeniden yükle
 */
async function reloadAllHistory() {
    console.log('🔄 Reloading all history from MongoDB...');
    window.showLoader(true);

    try {
        // Önce mevcut history'yi temizle
        window.queryHistory = [];

        // MongoDB'den tüm verileri yükle
        await Promise.all([
            loadHistory(),
            window.loadAnomalyHistoryFromMongoDB({limit: 100}),
            loadAndMergeDBAHistory()
        ]);

        // Not: queryHistory, loadHistory() ile doldurulacak
        // Diğerleri ayrı depolanıyor ya da merge ediliyor

        console.log(`✅ Reloaded ${window.queryHistory.length} items from MongoDB`);
        window.showNotification('Tüm veriler MongoDB\'den yeniden yüklendi', 'success');

        // UI'ı güncelle
        updateHistoryDisplay();
        
    } catch (error) {
        console.error('Reload error:', error);
        window.showNotification('Veriler yüklenirken hata oluştu', 'error');
    } finally {
        window.showLoader(false);
    }
}

/**
 * Tek bir item'ı MongoDB'ye kaydet
 */
async function syncSingleItem(itemId) {
    const item = window.queryHistory.find(h => h.id === itemId);
    if (!item || item.fromMongoDB) return;
    
    try {
        const response = await fetch('/api/query-history/save', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                ...item,
                api_key: window.apiKey,
                session_id: window.currentSessionId
            })
        });
        
        if (response.ok) {
            const result = await response.json();
            item.id = result.query_id;
            item.fromMongoDB = true;
            
            console.log(`✅ Item synced to MongoDB: ${result.query_id}`);
            window.showNotification('MongoDB\'ye kaydedildi', 'success');
            
            // UI'ı güncelle
            updateHistoryDisplay();
        }
    } catch (error) {
        console.error('Sync error:', error);
        window.showNotification('Kayıt başarısız', 'error');
    }
}

// ========== DBA HISTORY ENTEGRASYONU ==========

/**
 * MongoDB'den DBA analizlerini çek ve history'e ekle
 */
async function loadAndMergeDBAHistory() {
    try {
        // MongoDB'den DBA analizlerini çek
        const response = await fetch(`/api/dba/analysis-history?limit=20&days_back=30&api_key=${window.apiKey}`);
        const data = await response.json();
        
        if (data.status === 'success' && data.analyses && data.analyses.length > 0) {
            console.log(`Loaded ${data.analyses.length} DBA analyses from MongoDB`);
            
            // Her DBA analizini history formatına çevir
            data.analyses.forEach(analysis => {
                // Zaten history'de var mı kontrol et (storage_id ile)
                const exists = window.queryHistory.find(h => h.storage_id === analysis._id);
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
                    window.queryHistory.unshift(historyItem);
                }
            });
            
            // Tarihe göre sırala
            window.queryHistory.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
            
            // Fazla kayıtları temizle
            if (window.queryHistory.length > window.MAX_HISTORY_ITEMS) {
                window.queryHistory = window.queryHistory.slice(0, window.MAX_HISTORY_ITEMS);
            }
            
            // LocalStorage'a kaydet
            window.saveHistory();
            
            // Display'i güncelle
            window.updateHistoryDisplayWithDBA();
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
    let filteredHistory = window.queryHistory;
    if (filter === 'anomaly') {
        filteredHistory = window.queryHistory.filter(item => 
            item.type === 'anomaly' || 
            item.category === 'anomaly' ||
            item.isAnomalyParent === true
        );
    } else if (filter === 'chatbot') {
        filteredHistory = window.queryHistory.filter(item => 
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
                <div class="history-query">${window.escapeHtml(item.query)}</div>
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
        window.showLoader(true);
        
        const response = await fetch(`/api/dba/analysis/${analysisId}?api_key=${window.apiKey}`);
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
            window.displayDBAAnalysisResults(
                formattedResult,
                analysis.host || 'Unknown',
                analysis.time_range ? analysis.time_range.split(' to ')[0] : '',
                analysis.time_range ? analysis.time_range.split(' to ')[1] : ''
            );
            
            window.showNotification('DBA analizi yüklendi', 'success');
        }
    } catch (error) {
        console.error('Failed to load DBA analysis:', error);
        window.showNotification('DBA analizi yüklenemedi', 'error');
    } finally {
        window.showLoader(false);
    }
}

/**
 * Geçmiş detayını göster
 */
function showHistoryDetail(id) {
    console.log('=== showHistoryDetail DEBUG ===');
    console.log('Looking for item with ID:', id);
    console.log('ID type:', typeof id);
    
    // ID'yi normalize et - hem string hem number olarak kontrol et
    const normalizedId = String(id);
    
    // Hem string hem number olarak ara
    const item = window.queryHistory.find(h => {
        return String(h.id) === normalizedId || 
               h.id === parseInt(normalizedId, 10) || 
               h.id === normalizedId ||
               h.id == id;  // Loose equality as fallback
    });
    
    if (!item) {
        console.error('Item not found in history!');
        console.error('Available IDs:', window.queryHistory.map(h => ({id: h.id, type: typeof h.id})));
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
                content += window.renderMLModelMetrics(mlData.summary || {}, mlData.anomaly_score_stats || {});
            }
            
            // 4. Temporal Heatmap
            if (mlData.temporal_analysis?.hourly_distribution) {
                content += window.renderTemporalHeatmap(mlData.temporal_analysis);
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
        
        // AI explanation yoksa ama açıklama varsa, text format kullan
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
                                            <pre>${window.escapeHtml(anomaly.message.substring(0, 500))}...</pre>
                                        </div>
                                        <div class="message-full" style="display:none;">
                                            <pre>${window.escapeHtml(anomaly.message)}</pre>
                                        </div>
                                        <button class="btn-expand-message" onclick="toggleHistoryMessage(this)">Tam Mesajı Göster</button>
                                    </div>
                                ` : `
                                    <pre class="message-short">${window.escapeHtml(anomaly.message || '')}</pre>
                                `}
                            </div>
                            ${anomaly.component ? `
                                <div class="anomaly-component">
                                    <strong>Component:</strong> ${window.escapeHtml(anomaly.component)}
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
        content += window.parseAndFormatDescription(item.result.açıklama);
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
            window.attachMLVisualizationListeners();
        }, 200); // Biraz daha gecikme ekledik
    }
}

/**
 * Sorguyu tekrar çalıştır
 */
function replayQuery(id) {
    const item = window.queryHistory.find(h => h.id === id);
    if (!item) return;
    
    window.elements.queryInput.value = item.query;
    window.elements.queryInput.focus();
    
    // Otomatik çalıştır
    if (confirm('Bu sorguyu tekrar çalıştırmak istiyor musunuz?')) {
        window.handleQuery();
    }
}

/**
 * Geçmişı temizle
 */
async function clearHistory() {
    if (confirm('Tüm sorgu geçmişini silmek istediğinizden emin misiniz?')) {
        try {
            // MongoDB'den temizle
            if (window.isConnected && window.apiKey) {
                const response = await fetch('/api/query-history/clear', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        api_key: window.apiKey,
                        session_id: window.currentSessionId
                    })
                });
                
                if (response.ok) {
                    const result = await response.json();
                    console.log(`✅ Cleared ${result.deleted_count} items from MongoDB`);
                }
            }
            
            // Local değişkeni temizle
            window.queryHistory = [];
            
            updateHistoryDisplay();
            window.showNotification('Geçmiş temizlendi', 'success');
        } catch (e) {
            console.error('Geçmiş temizleme hatası:', e);
            window.showNotification('Geçmiş temizlenirken hata oluştu', 'error');
        }
    }
}

/**
 * Storage boyutunu kontrol et ve gerekirse temizlik yap
 */
async function checkStorageSize() {
    if (!window.isConnected || !window.apiKey) return;
    
    try {
        const response = await fetch(`/api/storage/check-size?api_key=${window.apiKey}`);
        
        if (response.ok) {
            const data = await response.json();
            
            if (data.is_over_limit) {
                console.warn(`⚠️ Storage limit exceeded: ${data.size_info.total_size_gb.toFixed(2)} GB`);
                
                if (data.deleted_count > 0) {
                    console.log(`🧹 Cleaned up ${data.deleted_count} old records`);
                    window.showNotification(`Disk alanı temizlendi: ${data.deleted_count} eski kayıt silindi`, 'info');
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
    const dataStr = JSON.stringify(window.queryHistory, null, 2);
    const dataUri = 'data:application/json;charset=utf-8,' + encodeURIComponent(dataStr);

    const exportFileDefaultName = `mongodb_history_${new Date().toISOString().split('T')[0]}.json`;

    const linkElement = document.createElement('a');
    linkElement.setAttribute('href', dataUri);
    linkElement.setAttribute('download', exportFileDefaultName);
    linkElement.click();

    window.showNotification('Geçmiş dışa aktarıldı', 'success');
}

/**
 * MongoDB geçmişini yükle ve göster
 */
async function loadMongoDBHistory() {
    const history = await window.loadAnomalyHistoryFromMongoDB({ limit: 50 });

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
                    <button onclick="window.viewStoredAnalysis('${item.analysis_id}')">Detay</button>
                </div>
            `;
        });
        modalContent += '</div>';
    } else {
        modalContent += '<p>Kayıtlı analiz bulunamadı.</p>';
    }

    modalContent += '</div>';
    window.showModal('MongoDB Anomali Geçmişi', modalContent);
}

/**
 * MongoDB'den anomali geçmişini yükle
 */
async function loadAnomalyHistoryFromMongoDB(filters = {}) {
    try {
        const params = new URLSearchParams({ api_key: window.apiKey, ...filters });
        const response = await fetch(`${window.API_ENDPOINTS.anomalyHistory}?${params}`);
        if (!response.ok) throw new Error('Failed to fetch anomaly history');
        const data = await response.json();
        console.info(`[STORAGE] Anomaly history loaded: ${data.count} records`);
        return data.history || [];
    } catch (error) {
        console.error('[STORAGE] Error loading anomaly history from MongoDB:', error);
        return [];
    }
}
// ============================================
// EVENT LISTENERS
// ============================================

// Sayfa yüklendiğinde veya bağlantı kurulduğunda sync'i çalıştır
window.addEventListener('load', () => {
    setTimeout(() => {
        if (window.isConnected) {
            syncUnsavedHistoryItems();
        }
    }, 5000); // 5 saniye sonra sync
});

// Sayfa yüklendiğinde ve API bağlandığında DBA geçmişini yükle
document.addEventListener('DOMContentLoaded', function() {
    // Mevcut tab event listener'larına ek olarak
    const originalUpdateDisplay = updateHistoryDisplay;
    
    // updateHistoryDisplay'i override et
    window.updateHistoryDisplay = function(filter = 'all') {
        // Önce DBA history'i yükle
        if (window.apiKey) {
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

// ============================================
// GLOBAL ERİŞİM İÇİN WINDOW'A ATAMA
// ============================================
window.loadHistory = loadHistory;
window.mergeHistoryWithMongoDB = mergeHistoryWithMongoDB;
window.addToHistory = addToHistory;
window.saveHistory = saveHistory;
window.verifyMongoDBSave = verifyMongoDBSave;
window.syncUnsavedHistoryItems = syncUnsavedHistoryItems;
window.updateHistoryDisplay = updateHistoryDisplay;
window.reloadAllHistory = reloadAllHistory;
window.syncSingleItem = syncSingleItem;
window.loadAndMergeDBAHistory = loadAndMergeDBAHistory;
window.updateHistoryDisplayWithDBA = updateHistoryDisplayWithDBA;
window.loadHistoricalDBAAnalysis = loadHistoricalDBAAnalysis;
window.showHistoryDetail = showHistoryDetail;
window.replayQuery = replayQuery;
window.clearHistory = clearHistory;
window.checkStorageSize = checkStorageSize;
window.exportHistory = exportHistory;
window.loadMongoDBHistory = loadMongoDBHistory;
window.loadAnomalyHistoryFromMongoDB = loadAnomalyHistoryFromMongoDB;
console.log('✅ History module loaded successfully');
