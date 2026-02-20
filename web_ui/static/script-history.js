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
 * API key'i MongoDB'ye kaydet
 */
async function saveApiKeyToMongoDB(apiKey) {
    try {
        const response = await fetch('/api/config/save-api-key', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                api_key: apiKey,
                user_id: 'default',
                session_id: window.currentSessionId
            })
        });
        
        if (response.ok) {
            console.log('✅ API key saved to MongoDB storage');
            return true;
        }
    } catch (error) {
        console.error('Failed to save API key to MongoDB:', error);
    }
    return false;
}

/**
 * MongoDB'den API key'i al
 */
async function loadApiKeyFromMongoDB() {
    try {
        const response = await fetch('/api/config/get-api-key?user_id=default');
        
        if (response.ok) {
            const data = await response.json();
            
            if (data.status === 'success' && data.api_key) {
                console.log('✅ API key loaded from MongoDB');
                
                // localStorage'a da kaydet (cache)
                localStorage.setItem('saved_api_key', data.api_key);
                
                return data.api_key;
            }
        }
    } catch (error) {
        console.error('Failed to load API key from MongoDB:', error);
    }
    return null;
}

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
 * Uygulama başlatıldığında otomatik history yükleme
 * Mevcut fonksiyonları kullanarak MongoDB'den tüm verileri yükler
 */
async function autoLoadHistoryOnStartup() {
    console.log('🔄 Auto-loading history from MongoDB...');
    
    try {
        // Önce MongoDB'den API key'i kontrol et
        let apiKey = await loadApiKeyFromMongoDB();
        
        // MongoDB'de yoksa localStorage'dan al
        if (!apiKey) {
            apiKey = localStorage.getItem('saved_api_key');
            if (apiKey) {
                console.log('📌 Using API key from localStorage');
            }
        } else {
            console.log('📌 Using API key from MongoDB');
        }
        
        if (!apiKey) {
            console.log('ℹ️ No API key found in storage');
            return false;
        }
        
        // API key'i global değişkene set et
        window.apiKey = apiKey;
        window.isConnected = true;
        
        // LCWGPT: Bağlantı kurulunca sunucu listesini çek ve sidebar'da göster
        if (typeof window.loadAnalyzedServers === 'function') {
            window.loadAnalyzedServers().then(function() {
                if (window.chatServerList && window.chatServerList.length > 0 && !window.selectedChatServer) {
                    if (typeof window.showServerSelection === 'function') {
                        window.showServerSelection();
                    }
                }
                // Ornek sorulari guncelle (sunucu listesi yuklendikten sonra)
                if (typeof window.updateExampleQuestions === 'function') {
                    window.updateExampleQuestions();
                }
            });
        }

        // Paralel olarak tüm history türlerini yükle
        const results = await Promise.allSettled([
            loadQueryHistoryFromMongoDB(),
            loadAnomalyHistoryFromMongoDB({ limit: 50 }), // Mevcut fonksiyonu kullan
            loadAndMergeDBAHistory(), // Mevcut fonksiyonu kullan
            loadAndMergeMSSQLHistory(), // MSSQL history'yi de yükle
            loadAndMergeElasticsearchHistory() // Elasticsearch history'yi de yükle
        ]);

        // Sonuçları değerlendir
        let successCount = 0;
        const types = ['Query History', 'Anomaly History', 'DBA History', 'MSSQL History', 'ES History'];
        
        results.forEach((result, index) => {
            if (result.status === 'fulfilled' && result.value) {
                successCount++;
                console.log(`✅ ${types[index]} loaded successfully`);
            } else {
                console.warn(`⚠️ ${types[index]} failed:`, result.reason);
            }
        });
        
        if (successCount > 0) {
            console.log(`📊 Successfully loaded ${successCount}/3 history types`);
            
            // Son anomaly analizini otomatik göster
            await displayLastAnomalyAnalysis();
            
            // History display'i güncelle
            updateHistoryDisplay();
            
            // Başarılı yükleme bildirimi
            if (window.showNotification) {
                window.showNotification(
                    `MongoDB'den ${successCount} veri türü yüklendi`, 
                    'success'
                );
            }
            
            return true;
        }
        
        console.log('⚠️ No history data could be loaded');
        return false;
        
    } catch (error) {
        console.error('❌ Auto-load failed:', error);
        return false;
    }
}

/**
 * MongoDB'den sadece query history yükle
 * NOT: Bu fonksiyon yoksa eklenecek
 */
async function loadQueryHistoryFromMongoDB() {
    if (!window.apiKey) {
        throw new Error('No API key available');
    }
    
    try {
        const response = await fetch(
            `/api/query-history/load?api_key=${window.apiKey}&limit=100`
        );
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        const data = await response.json();
        
        if (data.status === 'success' && data.history) {
            // Mevcut loadHistory fonksiyonu gibi davran
            window.queryHistory = data.history;
            console.log(`✅ Loaded ${data.count} query history items`);
            return data.history;
        }
        
        return [];
    } catch (error) {
        console.error('Failed to load query history:', error);
        throw error;
    }
}

/**
 * Son anomaly analizini otomatik olarak görüntüle
 */
async function displayLastAnomalyAnalysis() {
    try {
        // Mevcut loadAnomalyHistoryFromMongoDB fonksiyonunu kullan
        const anomalyHistory = await loadAnomalyHistoryFromMongoDB({ limit: 1 });
        
        if (anomalyHistory && anomalyHistory.length > 0) {
            const lastAnalysis = anomalyHistory[0];
            console.log('📊 Found last anomaly analysis:', lastAnalysis.analysis_id);
            
            // Detaylı veriyi al
            const detailResponse = await fetch(
                `/api/anomaly-history/${lastAnalysis.analysis_id}?api_key=${window.apiKey}`
            );
            
            if (detailResponse.ok) {
                const detailData = await detailResponse.json();
                
                if (detailData.status === 'success' && detailData.analysis) {
                    const analysis = detailData.analysis;

                    // Önce detailed_data'dan, yoksa root'tan al
                    const dataSource = analysis.detailed_data || analysis;

                    // Anomali verilerini çoklu fallback ile al
                    const criticalAnomalies = dataSource.critical_anomalies_full || 
                                             dataSource.critical_anomalies || 
                                             dataSource.critical_anomalies_display || 
                                             analysis.critical_anomalies_full ||
                                             analysis.critical_anomalies ||
                                             [];

                    const unfilteredAnomalies = dataSource.unfiltered_anomalies || 
                                               analysis.unfiltered_anomalies ||
                                               criticalAnomalies;
                    // Summary bilgilerini al
                    const summary = dataSource.summary || analysis.summary || {};
                    const anomalyCount = summary.n_anomalies || 
                                        dataSource.anomaly_count || 
                                        analysis.anomaly_count || 
                                        criticalAnomalies.length;

                    // Veri var mı kontrol et
                    if (criticalAnomalies.length > 0 || anomalyCount > 0) {
                        // Global değişkene kaydet - frontend'in beklediği yapıda
                        window.lastAnomalyResult = {
                            durum: 'tamamlandı',
                            işlem: 'anomaly_from_storage',
                            açıklama: `📊 Önceki anomali analizi yüklendi\n\nAnaliz ID: ${analysis.analysis_id}\nZaman: ${analysis.timestamp}`,
                            analysis_id: analysis.analysis_id,

                            // ✅ Frontend beklentisine uygun sonuç yapısı
                            sonuç: {

                                critical_anomalies: criticalAnomalies,
                                unfiltered_anomalies: unfilteredAnomalies,
                                anomaly_count: anomalyCount,
                                total_logs: summary.total_logs || dataSource.logs_analyzed || analysis.logs_analyzed || 0,
                                anomaly_rate: summary.anomaly_rate || dataSource.anomaly_rate || analysis.anomaly_rate || 0,
                                summary: summary
                            },
                            storage_info: {
                                analysis_id: analysis.analysis_id,
                                timestamp: analysis.timestamp,
                                host: analysis.host || dataSource.host
                            }
                        };
                        // Display fonksiyonunu çağır
                        if (window.displayAnomalyResults) {
                            window.displayAnomalyResults(window.lastAnomalyResult);
                            console.log('✅ Last anomaly analysis displayed automatically');
                        }
                    } else {
                        console.log('ℹ️ Analysis found but no anomaly data available');
                    }
                }
            }
        } else {
            console.log('ℹ️ No previous anomaly analysis found');
        }
    } catch (error) {
        console.error('Failed to display last anomaly:', error);
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

            // ✅ YENİ: Model metadata extraction (MongoDB yapısına uyumlu)
            const modelMetadata = mongoItem.model_metadata || mongoItem.model_info || {};
            const modelInfo = {
                model_version: modelMetadata.model_version || null,
                model_path: modelMetadata.model_path || null,
                server_name: modelMetadata.server_name || null,
                is_ensemble_mode: modelMetadata.is_ensemble_mode || false,
                ensemble_model_count: modelMetadata.ensemble_model_count || 0,
                historical_buffer_samples: modelMetadata.historical_buffer_samples || 0,
                model_trained_at: modelMetadata.model_trained_at || null,
                feature_count: modelMetadata.feature_count || 0,
                contamination: modelMetadata.contamination || null
            };

            console.log('Extracted model_info for', mongoItem.analysis_id, ':', modelInfo.model_version || 'N/A');
            
            // Backend'den gelen "source" alanı bir string olabilir (örn: "opensearch")
            // veya eski kayıtlarda obje olabilir. Güvenli kontrol:
            const sourceObj = (typeof mongoItem.source === 'object' && mongoItem.source !== null) 
                            ? mongoItem.source 
                            : {};

            // Host ve Source Type belirleme (Mapping Düzeltmesi)
            // Backend'de "host" genellikle root seviyesindedir.
            const hostName = mongoItem.host || sourceObj.host || 'Unknown Host';
            const sourceType = mongoItem.source_type || mongoItem.source || sourceObj.type || 'unknown';
            
            // ✅ ÖNEMLİ: Doğru anomali alanlarını kullan
            const criticalAnomalies = mongoItem.critical_anomalies_full || 
                                     mongoItem.critical_anomalies || 
                                     mongoItem.critical_anomalies_display || 
                                     [];
            
            const unfilteredAnomalies = mongoItem.unfiltered_anomalies || 
                                      mongoItem.critical_anomalies_full || 
                                      [];
            // ✅ Özet bilgileri hazırla (tek seferde, tutarlı)
            const anomalyCount = summary.n_anomalies || mongoItem.anomaly_count || criticalAnomalies.length || 0;
            const totalLogs = summary.total_logs || mongoItem.logs_analyzed || 0;
            const anomalyRate = summary.anomaly_rate || mongoItem.anomaly_rate || 0;

            // ✅ Ortak sonuç yapısı (DRY - Don't Repeat Yourself)
            const commonSonuc = {
                critical_anomalies: criticalAnomalies,
                unfiltered_anomalies: unfilteredAnomalies,
                anomaly_count: anomalyCount,
                total_logs: totalLogs,
                anomaly_rate: anomalyRate,
                summary: {
                    ...summary,
                    n_anomalies: anomalyCount,
                    total_logs: totalLogs,
                    anomaly_rate: anomalyRate
                }
            };

            // MongoDB verisini local history formatına çevir
            const historyItem = {
                id: Date.now() + Math.random(),
                timestamp: mongoItem.timestamp,
                query: hostName !== 'Unknown Host' ? 
                    `Anomali Analizi: ${hostName}` : 
                    'MongoDB Anomaly Analysis',
                type: 'anomaly',
                category: 'anomaly',

                // ✅ result objesi - tutarlı yapı
                result: {
                    durum: 'tamamlandı',
                    işlem: 'anomaly_analysis',
                    açıklama: `📊 ${hostName} sunucusu için anomali analizi\n\n` +
                              `• Toplam Log: ${totalLogs.toLocaleString('tr-TR')}\n` +
                              `• Anomali Sayısı: ${anomalyCount}\n` +
                              `• Anomali Oranı: %${anomalyRate.toFixed(2)}`,
                    sonuç: commonSonuc
                },

                // ✅ childResult - showHistoryDetail için (aynı yapı)
                childResult: {
                    durum: 'tamamlandı',
                    işlem: 'anomaly_analysis',
                    açıklama: `📊 ${hostName} için ${anomalyCount} anomali tespit edildi.`,
                    sonuç: commonSonuc
                },

                // Metadata
                storage_id: mongoItem.analysis_id,
                analysis_id: mongoItem.analysis_id,  //  bazı fonksiyonlar bunu bekliyor
                fromMongoDB: true,
                hasResult: true,
                host: hostName,
                source_type: sourceType,
                time_range: mongoItem.time_range || '',

                // Model metadata (UI gösterimi için)
                model_info: modelInfo,
                model_metadata: modelMetadata,

                // Flat yapı erişimi için de sakla (fallback)
                critical_anomalies_full: criticalAnomalies,
                unfiltered_anomalies: unfilteredAnomalies,
                summary: commonSonuc.summary
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

    let html = '';

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

    // Yatay scroll kart listesi (Figma layout)
    html += '<div class="history-scroll-container">';
    html += '<div class="history-cards-row">';

    filteredHistory.forEach(item => {
        const date = new Date(item.timestamp);
        const typeIcon = item.subType === 'DBA' ? '🕐' :
                        item.type === 'anomaly' ? '🔍' :
                        item.type === 'chat-anomaly' ? '🤖' : '💬';

        // Durum rengi (kart ust sag kosesindeki nokta)
        const dotColor = item.durum === 'tamamlandı' || item.durum === 'başarılı' ? '#28a745' :
                        item.durum === 'hata' ? '#dc3545' :
                        item.durum === 'onay_bekliyor' ? '#ffc107' : '#6b7280';

        // Kaynak tipi
        const sourceLabel = item.subType === 'DBA' ? 'DBA' :
                           item.source_type === 'opensearch' ? 'MongoDB' :
                           item.source_type === 'mssql_opensearch' ? 'MSSQL' :
                           item.type === 'anomaly' ? 'Anomali' : 'Chatbot';

        // Anomali sayisi
        const anomalyCount = item.anomalyCount || item.summary?.n_anomalies || item.dbaData?.anomaly_count || 0;
        const anomalyLabel = anomalyCount > 0 ? `${anomalyCount} Anomali` : 'Temiz';
        const anomalyColor = anomalyCount > 5 ? '#dc3545' : anomalyCount > 0 ? '#ffc107' : '#6b7280';

        // Kart kisa baslik
        const shortQuery = item.query && item.query.length > 35 ? item.query.substring(0, 35) + '...' : (item.query || 'Analiz');

        // Tarih formati (kisa)
        const dateStr = date.toLocaleDateString('tr-TR', { month: 'short', day: 'numeric' });
        const timeStr = date.toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' });

        html += `
            <div class="history-card" data-id="${item.id}" data-has-result="${item.hasResult || false}" data-from-mongodb="${item.fromMongoDB}"
                 onclick="window.showHistoryDetail('${String(item.id).replace(/'/g, "\\'")}')"
                 title="${window.escapeHtml(item.query || '')}">
                <div class="history-card-top">
                    <span class="history-card-date">${dateStr}, ${timeStr}</span>
                    <span class="history-card-dot" style="background-color: ${dotColor};"></span>
                </div>
                <div class="history-card-title">${typeIcon} ${window.escapeHtml(shortQuery)}</div>
                <div class="history-card-source">${sourceLabel}</div>
                <div class="history-card-footer">
                    <span class="history-card-anomaly" style="color: ${anomalyColor};">${anomalyLabel}</span>
                    <span class="history-card-status">${item.durum || ''}</span>
                </div>
            </div>
        `;
    });

    html += '</div></div>';
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
            loadAndMergeDBAHistory(),
            loadAndMergeMSSQLHistory(),
            loadAndMergeElasticsearchHistory()
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
                        // Host undefined ise 'Unknown' kullan
                        query: `DBA Analizi: ${analysis.host || 'Unknown'} - ${analysis.time_range || 'Custom time range'}`,
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
            
            // ✅ YENİ: Başarılı durumda analyses'i döndür
            return data.analyses;
        }
        
        // ✅ YENİ: Veri yoksa boş array döndür
        return [];
        
    } catch (error) {
        console.error('Failed to load DBA history from MongoDB:', error);
        // ✅ YENİ: Hata durumunda da boş array döndür
        return [];
    }
}


// ========== MSSQL HISTORY ENTEGRASYONU ==========

/**
 * MongoDB'den MSSQL analizlerini çek ve history'e ekle
 * DBA history ile aynı yapı, source_type='mssql_opensearch' filtreli
 */
async function loadAndMergeMSSQLHistory() {
    try {
        // MongoDB'den MSSQL analizlerini çek
        const response = await fetch(`/api/mssql/analysis-history?limit=20&days_back=30&api_key=${window.apiKey}`);
        const data = await response.json();

        if (data.status === 'success' && data.analyses && data.analyses.length > 0) {
            console.log(`Loaded ${data.analyses.length} MSSQL analyses from MongoDB`);

            // Her MSSQL analizini history formatına çevir
            data.analyses.forEach(analysis => {
                // Zaten history'de var mı kontrol et (storage_id ile)
                const exists = window.queryHistory.find(h => h.storage_id === analysis._id);
                if (!exists) {
                    // History item formatına çevir
                    const historyItem = {
                        id: Date.now() + Math.random(), // Unique ID
                        timestamp: analysis.timestamp,
                        query: `MSSQL Analizi: ${analysis.host || 'Unknown'} - ${analysis.time_range || 'Custom time range'}`,
                        type: 'anomaly',
                        category: 'anomaly',
                        subType: 'MSSQL', // MSSQL olduğunu belirtmek için
                        database_type: 'mssql',
                        storage_id: analysis._id,
                        result: {
                            durum: 'tamamlandı',
                            işlem: 'mssql_analysis'
                        },
                        // MSSQL spesifik veriler (DBA ile aynı yapı)
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

            return data.analyses;
        }

        return [];

    } catch (error) {
        console.error('Failed to load MSSQL history from MongoDB:', error);
        return [];
    }
}


// ========== ELASTICSEARCH HISTORY ENTEGRASYONU ==========

/**
 * MongoDB'den Elasticsearch analizlerini çek ve history'e ekle
 * MSSQL history ile aynı yapı, source_type='elasticsearch_opensearch' filtreli
 */
async function loadAndMergeElasticsearchHistory() {
    try {
        // MongoDB'den Elasticsearch analizlerini çek
        const response = await fetch(`/api/elasticsearch/analysis-history?limit=20&days_back=30&api_key=${window.apiKey}`);
        const data = await response.json();

        if (data.status === 'success' && data.analyses && data.analyses.length > 0) {
            console.log(`Loaded ${data.analyses.length} Elasticsearch analyses from MongoDB`);

            // Her Elasticsearch analizini history formatına çevir
            data.analyses.forEach(analysis => {
                // Zaten history'de var mı kontrol et (storage_id ile)
                const exists = window.queryHistory.find(h => h.storage_id === analysis._id);
                if (!exists) {
                    // History item formatına çevir
                    const historyItem = {
                        id: Date.now() + Math.random(), // Unique ID
                        timestamp: analysis.timestamp,
                        query: `ES Analizi: ${analysis.host || 'Unknown'} - ${analysis.time_range || 'Custom time range'}`,
                        type: 'anomaly',
                        category: 'anomaly',
                        subType: 'Elasticsearch',
                        database_type: 'elasticsearch',
                        storage_id: analysis._id,
                        result: {
                            durum: 'tamamlandı',
                            işlem: 'es_anomaly_analysis'
                        },
                        // Elasticsearch spesifik veriler (DBA/MSSQL ile aynı yapı)
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

            return data.analyses;
        }

        return [];

    } catch (error) {
        console.error('Failed to load Elasticsearch history from MongoDB:', error);
        return [];
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
        
        // DBA, MSSQL ve Elasticsearch için özel ikon ve renk
        const typeIcon = item.subType === 'Elasticsearch' ? '🔎' :
                        item.subType === 'MSSQL' ? '🗄️' :
                        item.subType === 'DBA' ? '🕐' :
                        item.type === 'anomaly' ? '🔍' :
                        item.type === 'chat-anomaly' ? '🤖' : '💬';

        const borderColor = item.subType === 'Elasticsearch' ? '#F0BF1A' :
                           item.subType === 'MSSQL' ? '#CC2936' :
                           item.subType === 'DBA' ? '#0047BA' : '#e67e22';
        
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
                    ${item.subType === 'Elasticsearch' ? '<span class="es-badge" style="background: #F0BF1A; color: #333; padding: 2px 6px; border-radius: 3px; font-size: 11px;">ES</span>' : ''}
                    ${item.subType === 'MSSQL' ? '<span class="mssql-badge" style="background: #CC2936; color: white; padding: 2px 6px; border-radius: 3px; font-size: 11px;">MSSQL</span>' : ''}
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
                    ${(item.subType === 'DBA' || item.subType === 'MSSQL' || item.subType === 'Elasticsearch') && item.storage_id ? `
                        <button class="btn-small" onclick="loadHistoricalDBAAnalysis('${item.storage_id}')">
                            📊 Sonuçları Göster
                        </button>
                    ` : `
                        <button class="btn-small" onclick="showHistoryDetail('${String(item.id).replace(/'/g, "\\'")}')">
                            👁️ Detay
                        </button>
                    `}
                    ${!item.fromMongoDB ? `
                        <button class="btn-small" onclick="replayQuery('${String(item.id).replace(/'/g, "\\'")}')">
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
 * Geçmişten analizi yükle ve göster (DBA + MSSQL ortak)
 * MongoDB document top-level field'larından okur (analysis_result key'i yok)
 * JSON fallback: detailed_data varsa ondan da alır
 */
async function loadHistoricalDBAAnalysis(analysisId) {
    try {
        window.showLoader(true);

        const response = await fetch(`/api/dba/analysis/${analysisId}?api_key=${window.apiKey}`);
        const data = await response.json();

        if (data.status === 'success' && data.analysis) {
            const analysis = data.analysis;
            // JSON fallback verileri (include_details=True ile yüklenir)
            const detailed = analysis.detailed_data || {};

            // Document top-level field'larından oku (mongodb_handler.save_anomaly_result şeması)
            // Fallback: detailed_data (JSON dosyasından normalize edilmiş veri)
            const formattedResult = {
                status: 'success',
                results: {
                    critical_anomalies: analysis.critical_anomalies_full || analysis.critical_anomalies_display || detailed.critical_anomalies_full || [],
                    total_logs_analyzed: analysis.logs_analyzed || detailed.logs_analyzed || 0,
                    anomaly_count: analysis.anomaly_count || detailed.anomaly_count || 0,
                    anomaly_rate: analysis.anomaly_rate || detailed.anomaly_rate || 0,
                    ai_summary: analysis.ai_explanation || detailed.ai_explanation
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

            window.showNotification('Analiz yüklendi', 'success');
        }
    } catch (error) {
        console.error('Failed to load analysis:', error);
        window.showNotification('Analiz yüklenemedi', 'error');
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
    
    // ÖNEMLİ: Eğer anomali analiziyse, çoklu kaynaklardan veri çek
    if (item.type === 'anomaly' || item.category === 'anomaly' || item.subType === 'DBA') {
        console.log('=== showHistoryDetail: Anomaly Data Extraction ===');
        console.log('Item keys:', Object.keys(item));
        
        // Çoklu fallback ile veri çıkarma (mergeHistoryWithMongoDB pattern'i)
        // Öncelik sırası: childResult > result > item root (flat yapı)
        
        // 1. Critical anomalileri bul
        let criticalAnomalies = [];
        let summary = {};
        let mlData = {};
        
        // childResult'tan dene
        if (item.childResult?.sonuç?.critical_anomalies) {
            criticalAnomalies = item.childResult.sonuç.critical_anomalies;
            summary = item.childResult.sonuç.summary || {};
            mlData = item.childResult.sonuç.data || item.childResult.sonuç || {};
            console.log('Data source: childResult.sonuç');
        }
        // result.sonuç'tan dene
        else if (item.result?.sonuç?.critical_anomalies) {
            criticalAnomalies = item.result.sonuç.critical_anomalies;
            summary = item.result.sonuç.summary || {};
            mlData = item.result.sonuç.data || item.result.sonuç || {};
            console.log('Data source: result.sonuç');
        }
        // Flat yapıdan dene (MongoDB'den direkt gelen)
        else if (item.critical_anomalies_full || item.critical_anomalies) {
            criticalAnomalies = item.critical_anomalies_full || item.critical_anomalies || [];
            summary = item.summary || {};
            mlData = { summary: summary };
            console.log('Data source: flat structure (root)');
        }
        // dbaData'dan dene
        else if (item.dbaData) {
            // DBA history item'ları için özel durum
            console.log('Data source: dbaData (DBA history item)');
            summary = {
                n_anomalies: item.dbaData.anomaly_count || 0,
                total_logs: item.dbaData.total_logs || 0,
                anomaly_rate: item.dbaData.anomaly_rate || 0
            };
            mlData = { summary: summary };
            // DBA item'ları için detaylı veri yüklemesi gerekebilir
            if (item.storage_id && criticalAnomalies.length === 0) {
                console.log('DBA item needs detail fetch, storage_id:', item.storage_id);
                content += `
                    <div class="dba-detail-placeholder">
                        <p>📊 DBA analiz detayları yükleniyor...</p>
                        <button class="btn btn-primary" onclick="window.loadHistoricalDBAAnalysis('${item.storage_id}')">
                            📥 Detayları Yükle
                        </button>
                    </div>
                `;
            }
        }
        
        console.log('Extracted critical_anomalies count:', criticalAnomalies.length);
        console.log('Extracted summary:', summary);
        
        // ML Data kontrolü
        const hasMlData = mlData.summary || mlData.component_analysis || mlData.temporal_analysis || mlData.feature_importance;

        if (hasMlData) {
            content += '<div class="ml-visualizations-inline">';
            content += '<h4>📊 ML Analiz Sonuçları</h4>';
            
            // 1. ML Model Metrikleri
            if (mlData.summary || mlData.anomaly_score_stats) {
                content += window.renderMLModelMetrics ? 
                    window.renderMLModelMetrics(mlData.summary || {}, mlData.anomaly_score_stats || {}) : 
                    `<p>Summary: ${JSON.stringify(mlData.summary || {})}</p>`;
            }
            
            // 4. Temporal Heatmap
            if (mlData.temporal_analysis?.hourly_distribution) {
                content += window.renderTemporalHeatmap ? 
                    window.renderTemporalHeatmap(mlData.temporal_analysis) : '';
            }
            
            // Export ve diğer aksiyonlar
            content += `<div class="visualization-actions">
                <button class="btn btn-primary" onclick="showFullVisualizationModal('${item.id}')">
                    🖼️ Modal'da Göster
                </button>
                <button class="btn btn-secondary" onclick="exportAnomalyData('${item.id}')">
                    📥 Veriyi İndir
                </button>
            </div>`;
            
            content += '</div>';
        }
        
        // Özet istatistikler - her zaman göster (veri varsa)
        if (summary && (summary.total_logs || summary.n_anomalies || Object.keys(summary).length > 0)) {
            content += '<div class="anomaly-stats-summary">';
            content += '<h5>📊 İstatistikler</h5>';
            content += '<div class="stats-grid">';
            content += `<div class="stat-item">
                            <span class="stat-label">Toplam Log:</span>
                            <span class="stat-value">${(summary.total_logs || 0).toLocaleString('tr-TR')}</span>
                        </div>`;
            content += `<div class="stat-item">
                            <span class="stat-label">Anomali Sayısı:</span>
                            <span class="stat-value">${summary.n_anomalies || criticalAnomalies.length || 0}</span>
                        </div>`;
            content += `<div class="stat-item">
                            <span class="stat-label">Anomali Oranı:</span>
                            <span class="stat-value">%${(summary.anomaly_rate || 0).toFixed(2)}</span>
                        </div>`;
            content += '</div></div>';
        }


        // ✅ YENİ: Model Info Section

        const itemModelInfo = item.model_info || item.model_metadata ||
                              item.childResult?.sonuç?.model_info ||
                              item.result?.sonuç?.model_info || {};

        if (itemModelInfo.model_version || itemModelInfo.model_path) {
            content += '<div class="history-model-info-section">';
            content += '<h5>🤖 Model Bilgileri</h5>';
            content += '<div class="model-info-grid">';

            // Model Version
            if (itemModelInfo.model_version) {
                content += `<div class="model-info-item">
                    <span class="info-label">Versiyon:</span>
                    <span class="info-value">${itemModelInfo.model_version}</span>
                </div>`;
            }

            // Model Path
            if (itemModelInfo.model_path) {
                const shortPath = itemModelInfo.model_path.split('/').pop();
                content += `<div class="model-info-item">
                    <span class="info-label">Model Dosyası:</span>
                    <span class="info-value" title="${window.escapeHtml(itemModelInfo.model_path)}">${window.escapeHtml(shortPath)}</span>
                </div>`;
            }

            // Server Name
            if (itemModelInfo.server_name) {
                content += `<div class="model-info-item">
                    <span class="info-label">Sunucu:</span>
                    <span class="info-value">${window.escapeHtml(itemModelInfo.server_name)}</span>
                </div>`;
            }

            // Training Date
            if (itemModelInfo.model_trained_at) {
                content += `<div class="model-info-item">
                    <span class="info-label">Eğitim Tarihi:</span>
                    <span class="info-value">${new Date(itemModelInfo.model_trained_at).toLocaleString('tr-TR')}</span>
                </div>`;
            }

            // Ensemble Mode
            content += `<div class="model-info-item">
                <span class="info-label">Ensemble:</span>
                <span class="info-value ${itemModelInfo.is_ensemble_mode ? 'active' : ''}">
                    ${itemModelInfo.is_ensemble_mode ? '✅ Aktif (' + (itemModelInfo.ensemble_model_count || 0) + ' model)' : '❌ Pasif'}
                </span>
            </div>`;

            // Buffer Size
            if (itemModelInfo.historical_buffer_samples > 0) {
                content += `<div class="model-info-item">
                    <span class="info-label">Buffer:</span>
                    <span class="info-value">${itemModelInfo.historical_buffer_samples.toLocaleString('tr-TR')} örnek</span>
                </div>`;
            }

            // Feature Count
            if (itemModelInfo.feature_count > 0) {
                content += `<div class="model-info-item">
                    <span class="info-label">Feature:</span>
                    <span class="info-value">${itemModelInfo.feature_count} adet</span>
                </div>`;
            }

            // Contamination
            if (itemModelInfo.contamination) {
                content += `<div class="model-info-item">
                    <span class="info-label">Contamination:</span>
                    <span class="info-value">${(itemModelInfo.contamination * 100).toFixed(1)}%</span>
                </div>`;
            }

            content += '</div></div>';
        }


        // Critical Anomalies Listesi
        if (criticalAnomalies && criticalAnomalies.length > 0) {
            content += '<div class="history-critical-anomalies">';
            content += '<h5>🚨 Kritik Anomaliler (İlk 10)</h5>';
            content += '<div class="history-anomaly-list">';
            
            criticalAnomalies.slice(0, 10).forEach((anomaly, index) => {
                const severityScore = anomaly.severity_score || 0;
                const severityLevel = anomaly.severity_level || 'MEDIUM';
                const severityColor = anomaly.severity_color || '#e67e22';
                
                content += `
                    <div class="history-anomaly-item">
                        <div class="anomaly-header">
                            <span class="anomaly-rank">#${index + 1}</span>
                            <span class="anomaly-timestamp">${anomaly.timestamp ? new Date(anomaly.timestamp).toLocaleString('tr-TR') : 'N/A'}</span>
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
                                    <pre class="message-short">${window.escapeHtml(anomaly.message || 'Mesaj yok')}</pre>
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
            
            if (criticalAnomalies.length > 10) {
                content += `<p class="more-anomalies">... ve ${criticalAnomalies.length - 10} anomali daha</p>`;
            }
            
            content += '</div></div>';

        } else if (!item.dbaData) {
            // Anomali verisi yoksa - OTOMATİK LAZY LOADING

            const loadableId = item.storage_id || item.analysis_id;

            if (loadableId && !item._detailLoaded && !item._loadingDetail) {
                // Henüz yüklenmemiş, otomatik yükle
                console.log('🔄 Auto-loading detail for item:', loadableId);

                content += `
                    <div class="loading-anomaly-data">
                        <p>⏳ Anomali verileri yükleniyor...</p>
                        <div class="loading-spinner"></div>
                    </div>
                `;

                // Detay container'ı eklendikten sonra yükleme başlat
                // Async olarak yükle, UI bloklanmasın
                item._loadingDetail = true;
                setTimeout(async () => {
                    const success = await window.loadFullAnalysisDetail(loadableId);
                    if (!success) {
                        item._loadingDetail = false;
                    }
                }, 100);

            } else if (item._loadingDetail) {
                // Zaten yükleniyor
                content += `
                    <div class="loading-anomaly-data">
                        <p>⏳ Anomali verileri yükleniyor...</p>
                        <div class="loading-spinner"></div>
                    </div>
                `;
            } else {
                // Yükleme denendi ama başarısız oldu
                content += `
                    <div class="no-anomaly-data">
                        <p>⚠️ Bu analiz için detaylı anomali verisi bulunamadı.</p>
                        <p>Veri MongoDB'de veya JSON dosyasında mevcut olmayabilir.</p>
                        ${loadableId ? `
                            <button class="btn btn-primary" onclick="window.loadFullAnalysisDetail('${loadableId}')">
                                🔄 Tekrar Dene
                            </button>
                        ` : ''}
                    </div>
                `;
            }
        }

        // AI explanation kontrolü - childResult veya result'tan
        const aiExplanation = item.childResult?.açıklama || item.result?.açıklama || item.aiExplanation;
        if (aiExplanation && !aiExplanation.includes('AI DESTEKLİ')) {
            content += '<div class="anomaly-text-result">';
            content += '<h4>🔍 AI Analiz Açıklaması</h4>';
            content += '<div class="formatted-anomaly-text">';
            
            const formattedText = aiExplanation
                .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
                .replace(/### (.*?)$/gm, '<h5>$1</h5>')
                .replace(/## (.*?)$/gm, '<h4>$1</h4>')
                .replace(/# (.*?)$/gm, '<h3>$1</h3>')
                .replace(/^\* (.*?)$/gm, '• $1')
                .replace(/^- (.*?)$/gm, '• $1')
                .replace(/^\d+\. (.*?)$/gm, '<li>$1</li>')
                .replace(/\n\n/g, '</p><p>')
                .replace(/\n/g, '<br>');
            
            content += `<p>${formattedText}</p>`;
            content += '</div>';
            content += '</div>';
        }
    }
    // Normal sorgu sonucu (chatbot)
    else if (item.result?.açıklama) {
        content += '<div class="normal-result">';
        content += '<h5>📝 Sonuç:</h5>';
        content += window.parseAndFormatDescription(item.result.açıklama);
        content += '</div>';
    }
    // Hiçbir veri bulunamadıysa
    else {
        content += `
            <div class="no-data-message">
                <p>ℹ️ Bu kayıt için görüntülenecek detay bulunmuyor.</p>
                <p>Kayıt türü: ${item.type || 'bilinmiyor'}</p>
            </div>
        `;
    }
    
    content += '</div>';
    detailContainer.innerHTML = content;
    historyItemElement.appendChild(detailContainer);
    // ✅ GELİŞTİRİLMİŞ: Immediate height calculation + optimized animation

    // CSS class ile başlangıç ayarları (gecikme olmadan)
    detailContainer.style.maxHeight = '0';
    detailContainer.style.overflow = 'hidden';
    detailContainer.style.transition = 'max-height 0.3s ease-out, opacity 0.3s ease-out';
    detailContainer.style.opacity = '0';

    // requestAnimationFrame ile smooth animation (setTimeout'tan daha performanslı)
    requestAnimationFrame(() => {
        // İçerik yüksekliğini hesapla
        const contentHeight = detailContainer.scrollHeight;
        const viewportHeight = window.innerHeight;
        const maxAllowedHeight = Math.min(contentHeight, viewportHeight * 0.75);

        console.log('=== Container Height Calculation ===');
        console.log('Content height:', contentHeight);
        console.log('Viewport height:', viewportHeight);
        console.log('Max allowed height:', maxAllowedHeight);

        // Animasyonlu açılış
        requestAnimationFrame(() => {
            detailContainer.style.maxHeight = `${maxAllowedHeight}px`;
            detailContainer.style.opacity = '1';
            detailContainer.style.overflowY = contentHeight > maxAllowedHeight ? 'auto' : 'visible';
            detailContainer.style.overflowX = 'hidden';
            detailContainer.classList.add('show');

            // Scroll pozisyonunu en üste getir
            detailContainer.scrollTop = 0;
        });

        // PARENT CONTAINER OVERFLOW KONTROLÜ (sadece gerektiğinde)
        let parent = detailContainer.parentElement;
        let depth = 0;
        while (parent && parent !== document.body && depth < 5) {
            const computedStyle = window.getComputedStyle(parent);
            if (computedStyle.overflow === 'hidden' || computedStyle.overflowY === 'hidden') {
                console.warn('Parent has overflow:hidden, fixing:', parent.className);
                parent.style.overflow = 'visible';
            }
            parent = parent.parentElement;
            depth++;
        }
    });
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
    const warningMessage = "⚠️ DİKKAT: BU İŞLEM GERİ ALINAMAZ!\n\n" +
                           "MongoDB üzerindeki TÜM kayıtlar silinecektir:\n" +
                           "1. Tüm Sohbet Geçmişi\n" +
                           "2. Tüm Anomali Analizleri\n" +
                           "3. Tüm DBA Raporları\n\n" +
                           "Veritabanı tamamen temizlenecektir. Devam etmek istiyor musunuz?";

    if (confirm(warningMessage)) {
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
                    console.log(`✅ Global Wipe: ${result.deleted_count} items deleted`);
                    
                    // Bildirim göster
                    if (window.showNotification) {
                        window.showNotification(`🧹 Tam Temizlik Başarılı: ${result.deleted_count} kayıt silindi`, 'success');
                    }
                }
            }
            
            // UI ve Local değişkeni temizle
            window.queryHistory = [];
            
            // Ekranı güncelle
            updateHistoryDisplay();
            
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

/**
 * Storage ID ile analiz detayını yükle ve göster
 */
async function loadFullAnalysisDetail(analysisId) {
    try {
        window.showLoader(true);
        
        const response = await fetch(
            `/api/anomaly-history/${analysisId}?api_key=${window.apiKey}`
        );
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        const data = await response.json();
        
        if (data.status === 'success' && data.analysis) {
            console.log('✅ Full analysis detail loaded:', analysisId);
            
            // queryHistory'deki ilgili item'ı güncelle
            const itemIndex = window.queryHistory.findIndex(h => 
                h.storage_id === analysisId || h.analysis_id === analysisId
            );
            
            if (itemIndex !== -1) {
                // Veriyi flat yapıdan çıkar
                const analysis = data.analysis;
                const dataSource = analysis.detailed_data || analysis;
                
                const criticalAnomalies = dataSource.critical_anomalies_full || 
                                         dataSource.critical_anomalies || 
                                         analysis.critical_anomalies_full ||
                                         [];
                
                // Item'ı güncelle
                window.queryHistory[itemIndex].childResult = {
                    durum: 'tamamlandı',
                    işlem: 'anomaly_analysis',
                    sonuç: {
                        critical_anomalies: criticalAnomalies,
                        unfiltered_anomalies: dataSource.unfiltered_anomalies || criticalAnomalies,
                        summary: dataSource.summary || analysis.summary || {},
                        anomaly_count: criticalAnomalies.length
                    }
                };
                
                // Detay panelini yeniden aç
                const itemId = window.queryHistory[itemIndex].id;
                
                // Önce mevcut detayı kapat
                const existingDetail = document.querySelector(`.history-item[data-id="${itemId}"] .inline-detail`);
                if (existingDetail) {
                    existingDetail.remove();
                }
                
                // Yeniden aç
                window.showHistoryDetail(itemId);
                
                window.showNotification('Analiz detayları yüklendi', 'success');
            }
        }
    } catch (error) {
        console.error('Failed to load analysis detail:', error);
        window.showNotification('Detaylar yüklenirken hata oluştu', 'error');
    } finally {
        window.showLoader(false);
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
        // Önce DBA, MSSQL ve Elasticsearch history'leri yükle
        if (window.apiKey) {
            Promise.allSettled([
                loadAndMergeDBAHistory(),
                loadAndMergeMSSQLHistory(),
                loadAndMergeElasticsearchHistory()
            ]).then(() => {
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
    loadAndMergeMSSQLHistory();
    loadAndMergeElasticsearchHistory();
});

/**
 * Storage ID veya Analysis ID ile analiz detayını API'den yükle
 * Lazy loading için kullanılır
 */
async function loadFullAnalysisDetail(analysisId) {
    console.log('🔄 Loading full analysis detail for:', analysisId);
    
    try {
        window.showLoader(true);
        
        const response = await fetch(
            `/api/anomaly-history/${analysisId}?api_key=${window.apiKey}`
        );
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        const data = await response.json();
        console.log('API Response:', data);
        
        if (data.status === 'success' && data.analysis) {
            console.log('✅ Full analysis detail loaded:', analysisId);
            
            // Veriyi flat yapıdan çıkar
            const analysis = data.analysis;
            const dataSource = analysis.detailed_data || analysis;
            
            const criticalAnomalies = dataSource.critical_anomalies_full || 
                                     dataSource.critical_anomalies || 
                                     analysis.critical_anomalies_full ||
                                     analysis.critical_anomalies ||
                                     [];
            
            const unfilteredAnomalies = dataSource.unfiltered_anomalies || 
                                       analysis.unfiltered_anomalies ||
                                       criticalAnomalies;
            
            const summary = dataSource.summary || analysis.summary || {};
            const anomalyCount = summary.n_anomalies || analysis.anomaly_count || criticalAnomalies.length;
            const totalLogs = summary.total_logs || dataSource.logs_analyzed || analysis.logs_analyzed || 0;
            const anomalyRate = summary.anomaly_rate || dataSource.anomaly_rate || analysis.anomaly_rate || 0;

            //  Model metadata extraction
            const modelMetadata = analysis.model_metadata ||
                                  dataSource.model_info ||
                                  analysis.model_info || {};
            const modelInfo = {
                model_version: modelMetadata.model_version || null,
                model_path: modelMetadata.model_path || null,
                server_name: modelMetadata.server_name || null,
                is_ensemble_mode: modelMetadata.is_ensemble_mode || false,
                ensemble_model_count: modelMetadata.ensemble_model_count || 0,
                historical_buffer_samples: modelMetadata.historical_buffer_samples || 0,
                model_trained_at: modelMetadata.model_trained_at || null,
                feature_count: modelMetadata.feature_count || 0,
                contamination: modelMetadata.contamination || null
            };

            console.log('Extracted data:', {
                criticalAnomalies: criticalAnomalies.length,
                summary: summary,
                anomalyCount: anomalyCount,
                modelInfo: modelInfo.model_version || 'N/A'
            });
            
            // queryHistory'deki ilgili item'ı bul ve güncelle
            const itemIndex = window.queryHistory.findIndex(h => 
                h.storage_id === analysisId || 
                h.analysis_id === analysisId ||
                String(h.id) === String(analysisId)
            );
            
            if (itemIndex !== -1) {
                const item = window.queryHistory[itemIndex];
                
                // Ortak sonuç yapısı
                const commonSonuc = {
                    critical_anomalies: criticalAnomalies,
                    unfiltered_anomalies: unfilteredAnomalies,
                    anomaly_count: anomalyCount,
                    total_logs: totalLogs,
                    anomaly_rate: anomalyRate,
                    summary: {
                        n_anomalies: anomalyCount,
                        total_logs: totalLogs,
                        anomaly_rate: anomalyRate,
                        ...summary
                    }
                };
                // Item'ı güncelle
                window.queryHistory[itemIndex] = {
                    ...item,
                    result: {
                        durum: 'tamamlandı',
                        işlem: 'anomaly_analysis',
                        açıklama: `📊 ${analysis.host || 'Unknown'} için ${anomalyCount} anomali tespit edildi.`,
                        sonuç: commonSonuc
                    },
                    childResult: {
                        durum: 'tamamlandı',
                        işlem: 'anomaly_analysis',
                        açıklama: `📊 ${analysis.host || 'Unknown'} için ${anomalyCount} anomali tespit edildi.`,
                        sonuç: commonSonuc
                    },
                    critical_anomalies_full: criticalAnomalies,
                    unfiltered_anomalies: unfilteredAnomalies,
                    summary: commonSonuc.summary,
                    //  Model bilgileri
                    model_info: modelInfo,
                    model_metadata: modelMetadata,
                    hasResult: true,
                    _detailLoaded: true  // Detay yüklendiğini işaretle
                };
                
                console.log('✅ Item updated in queryHistory');
                
                // Detay panelini yeniden aç
                const itemId = window.queryHistory[itemIndex].id;
                
                // Önce mevcut detayı kapat
                const existingDetail = document.querySelector(`.history-item[data-id="${itemId}"] .inline-detail`);
                if (existingDetail) {
                    existingDetail.remove();
                }
                
                // Yeniden aç
                window.showHistoryDetail(itemId);
                
                window.showNotification(`${criticalAnomalies.length} anomali yüklendi`, 'success');
                return true;
            } else {
                console.warn('Item not found in queryHistory for update');
                window.showNotification('Analiz bulunamadı', 'warning');
                return false;
            }
        } else {
            throw new Error(data.message || 'Analysis not found');
        }
    } catch (error) {
        console.error('Failed to load analysis detail:', error);
        window.showNotification('Detaylar yüklenirken hata oluştu: ' + error.message, 'error');
        return false;
    } finally {
        window.showLoader(false);
    }
}

(function injectHistoryModelInfoStyles() {
    if (document.getElementById('history-model-info-style')) return;
    
    const style = document.createElement('style');
    style.id = 'history-model-info-style';
    style.textContent = `
        .history-model-info-section {
            background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
            border: 1px solid #dee2e6;
            border-radius: 8px;
            padding: 15px;
            margin: 15px 0;
            border-left: 4px solid #667eea;
        }
        .history-model-info-section h5 {
            margin: 0 0 12px 0;
            color: #495057;
            font-size: 0.95em;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .model-info-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 10px;
        }
        .model-info-item {
            display: flex;
            flex-direction: column;
            gap: 2px;
            padding: 8px;
            background: white;
            border-radius: 6px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        }
        .model-info-item .info-label {
            font-size: 0.7em;
            color: #6c757d;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .model-info-item .info-value {
            font-size: 0.9em;
            font-weight: 500;
            color: #212529;
            word-break: break-word;
        }
        .model-info-item .info-value.active {
            color: #28a745;
        }
        .model-info-item .info-value[title] {
            cursor: help;
        }
    `;
    document.head.appendChild(style);
})();

(function injectInlineDetailScrollStyles() {
    if (document.getElementById('inline-detail-scroll-style')) return;
    
    const style = document.createElement('style');
    style.id = 'inline-detail-scroll-style';
    style.textContent = `
        /* Inline Detail Container - Scroll Optimization */
        .inline-detail {
            position: relative;
            border-top: 1px solid #e9ecef;
            margin-top: 10px;
            padding-top: 15px;
            background: #fafbfc;
            border-radius: 0 0 8px 8px;
            transition: max-height 0.3s ease-out, opacity 0.3s ease-out;
        }
        
        .inline-detail.show {
            opacity: 1;
        }
        
        .inline-detail:not(.show) {
            opacity: 0;
            max-height: 0 !important;
            overflow: hidden !important;
            padding: 0 !important;
            margin: 0 !important;
            border: none !important;
        }
        
        /* Scrollbar Styling */
        .inline-detail::-webkit-scrollbar {
            width: 8px;
        }
        
        .inline-detail::-webkit-scrollbar-track {
            background: #f1f1f1;
            border-radius: 4px;
        }
        
        .inline-detail::-webkit-scrollbar-thumb {
            background: #c1c1c1;
            border-radius: 4px;
        }
        
        .inline-detail::-webkit-scrollbar-thumb:hover {
            background: #a1a1a1;
        }
        
        /* History Detail Content - Better Spacing */
        .history-detail-content {
            padding: 0 15px 15px 15px;
        }
        
        /* Anomaly List Scroll */
        .history-anomaly-list {
            max-height: 400px;
            overflow-y: auto;
            padding-right: 5px;
        }
        
        .history-anomaly-list::-webkit-scrollbar {
            width: 6px;
        }
        
        .history-anomaly-list::-webkit-scrollbar-thumb {
            background: #d1d1d1;
            border-radius: 3px;
        }
        
        /* Critical Anomalies Section */
        .history-critical-anomalies {
            margin-top: 15px;
            padding: 10px;
            background: #fff5f5;
            border-radius: 8px;
            border: 1px solid #ffe0e0;
        }
        
        .history-critical-anomalies h5 {
            margin: 0 0 10px 0;
            color: #c0392b;
        }
        
        /* Anomaly Item in History */
        .history-anomaly-item {
            background: white;
            border: 1px solid #eee;
            border-radius: 6px;
            padding: 12px;
            margin-bottom: 10px;
            transition: box-shadow 0.2s;
        }
        
        .history-anomaly-item:hover {
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        }
        
        .history-anomaly-item .anomaly-header {
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 8px;
            flex-wrap: wrap;
        }
        
        .history-anomaly-item .anomaly-rank {
            background: #e74c3c;
            color: white;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 0.8em;
            font-weight: bold;
        }
        
        .history-anomaly-item .anomaly-timestamp {
            color: #666;
            font-size: 0.85em;
        }
        
        .history-anomaly-item .anomaly-score-badge {
            font-weight: bold;
            font-size: 0.85em;
        }
        
        /* Message Expandable */
        .message-expandable {
            position: relative;
        }
        
        .message-preview pre,
        .message-full pre,
        .message-short {
            background: #f8f9fa;
            padding: 10px;
            border-radius: 4px;
            font-size: 0.85em;
            overflow-x: auto;
            white-space: pre-wrap;
            word-break: break-word;
            max-height: 150px;
            overflow-y: auto;
        }
        
        .btn-expand-message {
            background: #667eea;
            color: white;
            border: none;
            padding: 4px 12px;
            border-radius: 4px;
            font-size: 0.8em;
            cursor: pointer;
            margin-top: 5px;
        }
        
        .btn-expand-message:hover {
            background: #5a6fd6;
        }
        
        /* Stats Grid */
        .anomaly-stats-summary {
            background: #f0f7ff;
            border: 1px solid #d0e3ff;
            border-radius: 8px;
            padding: 15px;
            margin: 15px 0;
        }
        
        .anomaly-stats-summary h5 {
            margin: 0 0 12px 0;
            color: #2980b9;
        }
        
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 10px;
        }
        
        .stat-item {
            background: white;
            padding: 10px;
            border-radius: 6px;
            text-align: center;
        }
        
        .stat-item .stat-label {
            display: block;
            font-size: 0.75em;
            color: #666;
            margin-bottom: 4px;
        }
        
        .stat-item .stat-value {
            display: block;
            font-size: 1.1em;
            font-weight: bold;
            color: #2c3e50;
        }
        
        /* More Anomalies Indicator */
        .more-anomalies {
            text-align: center;
            color: #666;
            font-style: italic;
            margin-top: 10px;
            padding: 10px;
            background: #f8f9fa;
            border-radius: 4px;
        }
    `;
    document.head.appendChild(style);
})();


/**
 * History detayında mesaj expand/collapse toggle
 */
function toggleHistoryMessage(button) {
    const container = button.closest('.message-expandable');
    if (!container) return;
    
    const preview = container.querySelector('.message-preview');
    const full = container.querySelector('.message-full');
    
    if (preview && full) {
        const isExpanded = full.style.display !== 'none';
        
        if (isExpanded) {
            // Collapse
            preview.style.display = 'block';
            full.style.display = 'none';
            button.textContent = 'Tam Mesajı Göster';
        } else {
            // Expand
            preview.style.display = 'none';
            full.style.display = 'block';
            button.textContent = 'Mesajı Daralt';
        }
    }
}


// ============================================
// GLOBAL ERİŞİM İÇİN WINDOW'A ATAMA
// ============================================
window.toggleHistoryMessage = toggleHistoryMessage;
window.loadFullAnalysisDetail = loadFullAnalysisDetail;
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
window.loadAndMergeMSSQLHistory = loadAndMergeMSSQLHistory;
window.loadAndMergeElasticsearchHistory = loadAndMergeElasticsearchHistory;
window.updateHistoryDisplayWithDBA = updateHistoryDisplayWithDBA;
window.loadHistoricalDBAAnalysis = loadHistoricalDBAAnalysis;
window.showHistoryDetail = showHistoryDetail;
window.replayQuery = replayQuery;
window.clearHistory = clearHistory;
window.checkStorageSize = checkStorageSize;
window.exportHistory = exportHistory;
window.loadMongoDBHistory = loadMongoDBHistory;
window.loadAnomalyHistoryFromMongoDB = loadAnomalyHistoryFromMongoDB;
window.loadFullAnalysisDetail = loadFullAnalysisDetail;
window.saveApiKeyToMongoDB = saveApiKeyToMongoDB;
window.loadApiKeyFromMongoDB = loadApiKeyFromMongoDB;
console.log('✅ History module loaded successfully');
