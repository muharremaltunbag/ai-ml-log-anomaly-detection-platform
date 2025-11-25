// web_ui\static\script-anomaly.js

/**
 * LC Waikiki MongoDB Assistant - Anomaly Analysis Module
 * 
 * Bu modül anomali analizi ile ilgili tüm fonksiyonları içerir:
 * - Anomali analiz başlatma ve yönetim
 * - ML model görselleştirme
 * - Security alert işlemleri
 * - DBA analiz fonksiyonları
 * - AI destekli açıklamalar
 */

console.log('🔍 Loading script-anomaly.js...');

// ============================================
// PARENT ANOMALY QUERY YÖNETİMİ
// ============================================

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
        const parentIndex = window.queryHistory.findIndex(h => 
            h.isAnomalyParent === true && 
            h.durum !== 'tamamlandı' &&
            h.durum !== 'iptal'
        );
        
        if (parentIndex !== -1) {
            const parent = window.queryHistory[parentIndex];
            // Parent'ı güncelle
            parent.childResult = result;
            parent.hasResult = true;
            parent.durum = 'tamamlandı';
            parent.işlem = 'anomaly_analysis_completed';
            parent.completedAt = new Date().toISOString();
            parent.executionTime = Date.now() - parent.id;
            
            console.log('Parent updated successfully (by search):', parent);
            
            window.saveHistory();
            window.updateHistoryDisplay();
            
            // Detayı otomatik göster
            setTimeout(() => {
                window.showHistoryDetail(parent.id);
            }, 100);
        }
    } else {
        // ID varsa normal güncelleme
        const parentIndex = window.queryHistory.findIndex(h => h.id === window.pendingAnomalyQueryId);
        if (parentIndex !== -1) {
            const parent = window.queryHistory[parentIndex];
            parent.childResult = result;
            parent.hasResult = true;
            parent.durum = 'tamamlandı';
            parent.işlem = 'anomaly_analysis_completed';
            parent.completedAt = new Date().toISOString();
            parent.executionTime = Date.now() - parent.id;
            
            console.log('Parent updated successfully (by ID):', parent);
            
            window.saveHistory();
            window.updateHistoryDisplay();
            
            // Detayı otomatik göster
            const queryIdToShow = window.pendingAnomalyQueryId; // ID'yi lokal değişkende sakla
            setTimeout(() => {
                window.showHistoryDetail(queryIdToShow); // Lokal değişkenden kullan
            }, 100);

            // ID'yi temizle
            window.pendingAnomalyQueryId = null;
            localStorage.removeItem('pendingAnomalyQueryId');
        }
    }
}

/**
 * Chat anomali sonuçlarını göster
 */
function displayAnomalyResults(result) {
    console.log('displayAnomalyResults called with result:', result);
    
    // YENİ: ML Panel'i otomatik güncelle
    if (window.MLPanel && window.MLPanel.autoUpdate) {
        try {
            window.MLPanel.autoUpdate(result);
            console.log('✅ ML Panel auto-updated with anomaly results');
        } catch (error) {
            console.error('ML Panel update error:', error);
        }
    }

    const elements = window.elements;
    elements.resultSection.style.display = 'block';
    
    let html = '<div class="chat-result">';
    
    // Kullanıcı sorusu
    html += '<div class="chat-message user-message">';
    html += '<div class="message-header">👤 Siz</div>';
    html += `<div class="message-content">${window.escapeHtml(userQuery)}</div>`;
    html += '</div>';
    
    // AI yanıtı
    html += '<div class="chat-message ai-message">';
    html += '<div class="message-header">🤖 LCWGPT Asistan</div>';
    html += '<div class="message-content">';
    
    if (result.status === 'success' && result.ai_response) {
        // AI yanıtını önce decode et, sonra formatla
        const decodedResponse = decodeHtmlEntities(result.ai_response);
        const formattedResponse = formatAIResponse(decodedResponse);
        html += formattedResponse;
        
        // Meta bilgiler - GENİŞLETİLMİŞ
        html += '<div class="response-meta enhanced">';
        html += '<div class="meta-primary">';
        html += `<span class="meta-item">📊 <strong>${result.total_anomalies}</strong> toplam anomali</span>`;

        // Multi-chunk bilgisi ekle
        if (result.chunks_processed && result.chunks_processed > 1) {
            html += `<span class="meta-item">🔄 <strong>${result.chunks_processed}</strong> chunk işlendi</span>`;
            html += `<span class="meta-item">✅ Multi-chunk aggregation uygulandı</span>`;
        } else if (result.chunk_info) {
            html += `<span class="meta-item">📍 ${result.chunk_info}</span>`;
        }

        html += '</div>';

        // Eğer aggregated response ise, hangi chunk'lar işlendiğini göster
        if (result.processed_chunks && Array.isArray(result.processed_chunks)) {
            html += '<div class="meta-secondary">';
            html += '<span class="chunks-processed-label">İşlenen Chunk\'lar:</span>';
            html += '<div class="processed-chunks-list">';
            result.processed_chunks.forEach(chunkInfo => {
                html += `<span class="chunk-badge" title="${chunkInfo.anomaly_count} anomali">
                            Chunk ${chunkInfo.chunk_idx} 
                            <small>(${chunkInfo.anomaly_count})</small>
                         </span>`;
            });
            html += '</div>';
            html += '</div>';
        }

        html += '</div>';
    } else {
        html += `<div class="error-message">❌ ${result.message || 'Yanıt alınamadı'}</div>`;
    }
    
    html += '</div>';
    html += '</div>';
    
    // Chunk navigation butonları
    if (result.chunk_info && result.total_chunks > 1) {
        html += '<div class="chunk-navigation-controls">';
        html += '<div class="chunk-info-display">';
        html += `<span class="chunk-status">📊 Gösterilen: ${result.chunk_info}</span>`;
        html += `<span class="chunk-total">Toplam ${result.total_anomalies} anomaliden ${result.anomalies_in_chunk} tanesi</span>`;
        html += '</div>';
        html += '<div class="chunk-buttons">';
        
        // Önceki chunk butonu
        if (result.chunk_index > 0) {
            html += `<button class="btn-chunk-nav" onclick="loadAnomalyChunk('${window.lastAnomalyResult?.storage_info?.analysis_id}', ${result.chunk_index - 1})">`;
            html += `⬅️ Önceki Chunk (${result.chunk_index}/${result.total_chunks})`;
            html += '</button>';
        }
        
        // Sonraki chunk butonu
        if (result.has_next) {
            html += `<button class="btn-chunk-nav" onclick="loadAnomalyChunk('${window.lastAnomalyResult?.storage_info?.analysis_id}', ${result.chunk_index + 1})">`;
            html += `Sonraki Chunk (${result.chunk_index + 2}/${result.total_chunks}) ➡️`;
            html += '</button>';
        }
        
        // Chunk seçici dropdown
        if (result.total_chunks > 2) {
            html += '<select class="chunk-selector" onchange="loadAnomalyChunk(\'' + window.lastAnomalyResult?.storage_info?.analysis_id + '\', this.value)">';
            html += '<option value="">Chunk Seç...</option>';
            for (let i = 0; i < result.total_chunks; i++) {
                const selected = i === result.chunk_index ? 'selected' : '';
                html += `<option value="${i}" ${selected}>Chunk ${i + 1}/${result.total_chunks}</option>`;
            }
            html += '</select>';
        }
        
        html += '</div>';
        html += '</div>';
    }
    
    // Daha fazla soru önerileri
    html += '<div class="follow-up-suggestions">';
    html += '<p>İlgili sorular:</p>';
    html += '<div class="suggestion-chips">';
    html += '<span class="chip" onclick="askFollowUp(\'En kritik 5 anomali nedir?\')">En kritik 5 anomali</span>';
    html += '<span class="chip" onclick="askFollowUp(\'Hangi component en çok anomali içeriyor?\')">Component dağılımı</span>';
    html += '<span class="chip" onclick="askFollowUp(\'Bu anomaliler için ne önerirsin?\')">Öneriler</span>';
    html += '<span class="chip" onclick="askFollowUp(\'Anomali pattern\'leri var mı?\')">Pattern analizi</span>';
    html += '</div>';
    html += '</div>';
    
    html += '</div>';
    
    elements.resultContent.innerHTML = html;
    elements.resultSection.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

/**
 * HTML entity'leri tam decode et (çoklu decode desteği)
 */
function decodeHtmlEntities(text) {
    if (!text) return '';
    
    // Birden fazla kez encode edilmiş olabilir, 2 kez decode et
    let decoded = text;
    for (let i = 0; i < 2; i++) {
        const textArea = document.createElement('textarea');
        textArea.innerHTML = decoded;
        decoded = textArea.value;
        
        // Eğer değişiklik yoksa döngüyü kır
        if (decoded === text) break;
        text = decoded;
    }
    return decoded;
}

/**
 * AI yanıtını formatla - GELİŞTİRİLMİŞ VERSİYON
 */
function formatAIResponse(response) {
    // ÖNCE decode et
    let decoded = response;
    
    // HTML entity'leri decode et
    decoded = decoded.replace(/&#039;/g, "'");
    decoded = decoded.replace(/&quot;/g, '"');
    decoded = decoded.replace(/&lt;/g, '<');
    decoded = decoded.replace(/&gt;/g, '>');
    decoded = decoded.replace(/&amp;/g, '&');
    
    // Code block'ları koru
    const codeBlocks = [];
    decoded = decoded.replace(/```([\s\S]*?)```/g, (match, code) => {
        codeBlocks.push(code);
        return `__CODE_BLOCK_${codeBlocks.length - 1}__`;
    });
    
    // Güvenli escape (code block'lar hariç)
    let formatted = window.escapeHtml(decoded);
    
    // Code block'ları geri koy ve formatla
    codeBlocks.forEach((code, index) => {
        formatted = formatted.replace(
            `__CODE_BLOCK_${index}__`,
            `<div class="code-block"><pre>${window.escapeHtml(code.trim())}</pre></div>`
        );
    });
    
    // Markdown başlıkları - ### ile başlayanlar
    formatted = formatted.replace(/^####\s+(.*?)$/gm, '<h5 class="ai-heading">$1</h5>');
    formatted = formatted.replace(/^###\s+(.*?)$/gm, '<h4 class="ai-heading">$1</h4>');
    formatted = formatted.replace(/^##\s+(.*?)$/gm, '<h3 class="ai-heading">$1</h3>');
    formatted = formatted.replace(/^#\s+(.*?)$/gm, '<h2 class="ai-heading">$1</h2>');
    
    // Bold text - ** veya __ ile sarılı
    formatted = formatted.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    formatted = formatted.replace(/__(.*?)__/g, '<strong>$1</strong>');
    
    // Italic text
    formatted = formatted.replace(/\*(.*?)\*/g, '<em>$1</em>');
    formatted = formatted.replace(/_(.*?)_/g, '<em>$1</em>');
    
    // Bullet listeler - tire ile başlayanlar
    formatted = formatted.replace(/^[\s]*[-•]\s+(.*?)$/gm, '<li class="ai-list-item">$1</li>');
    formatted = formatted.replace(/^[\s]*\d+\.\s+(.*?)$/gm, '<li class="ai-list-item numbered">$1</li>');
    
    // Ardışık li elementlerini ul/ol içine al
    formatted = formatted.replace(/(<li class="ai-list-item">.*?<\/li>\n?)+/g, (match) => {
        return '<ul class="ai-list">' + match + '</ul>';
    });
    formatted = formatted.replace(/(<li class="ai-list-item numbered">.*?<\/li>\n?)+/g, (match) => {
        return '<ol class="ai-list">' + match + '</ol>';
    });
    
    // Emoji ve özel karakterleri koru
    formatted = formatted.replace(/📊/g, '<span class="emoji">📊</span>');
    formatted = formatted.replace(/🔍/g, '<span class="emoji">🔍</span>');
    formatted = formatted.replace(/⚠️/g, '<span class="emoji">⚠️</span>');
    formatted = formatted.replace(/✅/g, '<span class="emoji">✅</span>');
    formatted = formatted.replace(/💡/g, '<span class="emoji">💡</span>');
    
    // Satır sonları ve paragraflar
    formatted = formatted.replace(/\n\n+/g, '</p><p class="ai-paragraph">');
    formatted = formatted.replace(/\n/g, '<br>');
    
    // İçeriği container'a sar
    return `<div class="ai-response-content"><p class="ai-paragraph">${formatted}</p></div>`;
}

/**
 * Takip sorusu sor
 */
window.askFollowUp = function(question) {
    window.elements.queryInput.value = question;
    window.handleQuery();
};

/**
 * Doğal dil anomali analizi sonuçlarını göster - AI DESTEKLİ VERSİYON
 */
function displayAnomalyAnalysisResult(result) {
    console.log('Displaying AI-enhanced anomaly analysis result');
    
    // YENİ: ML Panel'i otomatik güncelle
    if (window.MLPanel && window.MLPanel.autoUpdate) {
        try {
            window.MLPanel.autoUpdate(result);
            console.log('✅ ML Panel auto-updated with AI-enhanced analysis');
        } catch (error) {
            console.error('ML Panel update error:', error);
        }
    }
    
    const elements = window.elements;
    
    // Hata durumu kontrolü
    if (result.durum === 'hata' || !result.sonuç) {
        console.log('Error in anomaly analysis:', result.açıklama);
        let html = '<div class="anomaly-error">';
        html += '<h3>❌ Analiz Hatası</h3>';
        html += `<p>${window.escapeHtml(result.açıklama || "Analiz sırasında bir hata oluştu")}</p>`;
        
        // Eğer API rate limit hatası ise özel mesaj
        if (result.açıklama && result.açıklama.includes('rate_limit_exceeded')) {
            html += '<p class="info-message">💡 <strong>Not:</strong> AI açıklama servisi token limiti aşıldığı için kullanılamadı. Anomali analizi başarıyla tamamlandı ancak AI destekli açıklamalar oluşturulamadı.</p>';
        }
        
        html += '</div>';
        elements.resultContent.innerHTML = html;
        return;
    }
    
    let html = '<div class="anomaly-analysis-result ai-enhanced">';
    
    // Durum göstergesi
    const summary = result.sonuç?.summary;
    const anomalyRate = summary ? summary.anomaly_rate : 0;
    const statusClass = anomalyRate > 5 ? 'critical' : 
                       anomalyRate > 2 ? 'warning' : 'success';
    
    html += `<div class="result-status ${statusClass}">`;
    html += `<strong>✅ Anomali Analizi Tamamlandı</strong>`;
    html += `</div>`;
    
    // AI AÇIKLAMASI - VERİ PARSE EDİLİYOR AMA UI'DA GÖSTERİLMİYOR
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

    // AI DESTEKLİ AÇIKLAMA BÖLÜMÜ DEVRE DIŞI BIRAKILDI
    // Backend'den veri gelmeye devam ediyor ama UI'da gösterilmiyor
   
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
    
    // Kritik Anomaliler - Sadece ilk 20 tanesi, daha kompakt + ENHANCED with toggle
    if (result.sonuç.critical_anomalies && result.sonuç.critical_anomalies.length > 0) {
        html += '<div class="critical-section">';
        html += '<h3>⚡ En Kritik 20 Anomali</h3>';
        
        // YENİ: Toggle kontrolü ekle
        html += `
            <div class="message-toggle-control">
                <label class="toggle-switch">
                    <input type="checkbox" id="criticalMessageToggle" onchange="toggleCriticalAnomalyMessages()">
                    <span class="toggle-slider"></span>
                </label>
                <span class="toggle-label">Formatlı Mesajları Göster</span>
            </div>
        `;
        
        html += '<div class="critical-list">';
        
        result.sonuç.critical_anomalies.forEach((anomaly, index) => {
            const scorePercent = Math.abs(anomaly.score) * 100;
            
            // Hem formatlı hem orijinal mesajı hazırla
            const originalMessage = window.escapeHtml(anomaly.message || '');
            const formattedMessage = window.escapeHtml(anomaly.formatted_message || originalMessage);
            const anomalyType = anomaly.anomaly_type || 'unknown';
            const riskLevel = anomaly.risk_level || '🟢 DÜŞÜK';
            
            html += `
                <div class="critical-item enhanced-anomaly-item" data-anomaly-type="${anomalyType}">
                    <div class="critical-rank">#${index + 1}</div>
                    <div class="critical-details">
                        <div class="critical-component">${window.escapeHtml(anomaly.component || 'N/A')} 
                            <span class="risk-badge">${riskLevel}</span>
                        </div>
                        <div class="critical-message-container">
                            <div class="critical-message original-message">${originalMessage}</div>
                            <div class="critical-message formatted-message" style="display: none;">${formattedMessage}</div>
                        </div>
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
                        <span class="component-name">${window.escapeHtml(component)}</span>
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
                html += `<td><strong>${window.escapeHtml(component)}</strong></td>`;
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
    
    window.showNotification('Rapor başarıyla indirildi', 'success');
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
    
    window.showModal('Anomali Takip Planı', followUpHtml);
}

function saveFollowUp() {
    const period = document.getElementById('followUpPeriod').value;
    const notes = document.getElementById('followUpNotes').value;
    
    // Gerçek bir uygulamada bu bilgi backend'e kaydedilir
    console.log('Follow-up scheduled:', { period, notes });
    
    window.closeModal();
    window.showNotification('Takip planı oluşturuldu', 'success');
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
    text = window.escapeHtml(text);
    
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
 * Anomali analiz işlemini başlat
 */
async function handleAnalyzeLog() {
    console.log('handleAnalyzeLog çağrıldı!'); // DEBUG LOG

    // Zaman aralığını al
    const timeRange = document.querySelector('input[name="modalTimeRange"]:checked').value;
    console.log('Time Range:', timeRange); // DEBUG LOG
    console.log('Selected Data Source:', window.selectedDataSource); // DEBUG LOG

    // Temel requestData hazırla
    let requestData = {
        api_key: window.apiKey,
        source_type: window.selectedDataSource
    };

    // Zaman aralığına göre parametre ekle
    if (timeRange === 'custom') {
        const startTime = document.getElementById('customStartTime')?.value;
        const endTime = document.getElementById('customEndTime')?.value;

        if (!startTime || !endTime) {
            alert('Lütfen başlangıç ve bitiş zamanlarını seçin!');
            return;
        }

        requestData.start_time = new Date(startTime).toISOString();
        requestData.end_time = new Date(endTime).toISOString();
        requestData.time_range = 'custom';

        console.log('Custom date range:', {
            start: requestData.start_time,
            end: requestData.end_time
        });
    } else {
        // Backend'e uygun time_range çevir
        let backendTimeRange = timeRange;
        if (timeRange === 'last_24h') backendTimeRange = 'last_day';
        else if (timeRange === 'last_7d') backendTimeRange = 'last_week';
        else if (timeRange === 'last_30d') backendTimeRange = 'last_month';
        requestData.time_range = backendTimeRange;
    }

    // Kaynağa özel parametreler
    switch (window.selectedDataSource) {
        case 'file':
            requestData.file_path = 'config';
            console.log('Using config file source');
            break;

        case 'upload': {
            const selectedFile = document.querySelector('input[name="logFile"]:checked');
            if (!selectedFile) {
                console.log('No file selected for upload source');
                alert('Lütfen bir dosya seçin!');
                return;
            }
            requestData.file_path = selectedFile.value;
            console.log('Using uploaded file:', selectedFile.value);
            break;
        }

        case 'mongodb_direct':
            requestData.connection_string = document.getElementById('mongoConnectionString').value;
            requestData.file_path = 'mongodb';
            console.log('Using MongoDB direct connection');
            break;

        case 'test_servers':
            requestData.server_name = document.getElementById('testServerSelect').value;
            requestData.file_path = 'server';
            console.log('Using test server:', requestData.server_name);
            break;

        case 'opensearch': {
            // Single/Cluster mode kontrolü
            const hostMode = document.querySelector('input[name="hostSelectionMode"]:checked')?.value || 'single';
            console.log('Host selection mode:', hostMode);

            let hostFilter = ''; 

            if (hostMode === 'cluster') {
                const selectedCluster = document.getElementById('clusterSelect')?.value;
                if (!selectedCluster) {
                    alert('Lütfen bir cluster seçin!');
                    return;
                }

                // Backend'e cluster_id gönder
                requestData.cluster_id = selectedCluster;
                requestData.analysis_mode = 'cluster';
                requestData.file_path = 'opensearch';

                console.log('Cluster mode - selected cluster:', selectedCluster);

                // Cluster analizi için özel endpoint kullan
                // Backend /api/analyze-cluster endpoint'ini kullanacak

                window.showLoader(true);
                closeAnomalyModal();

                try {
                    const clusterResponse = await fetch(window.API_ENDPOINTS.analyzeCluster, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            cluster_id: selectedCluster,
                            api_key: window.apiKey,
                            time_range: requestData.time_range,
                            start_time: requestData.start_time,
                            end_time: requestData.end_time
                        })
                    });

                    const clusterResult = await clusterResponse.json();
                    console.log('Cluster analysis result:', clusterResult);

                    displayAnomalyResults({
                        durum: 'tamamlandı',
                        işlem: 'anomaly_analysis',
                        açıklama: `Cluster ${selectedCluster} analizi tamamlandı`,
                        sonuç: {
                            summary: {
                                n_anomalies: clusterResult.total_anomalies,
                                total_logs: clusterResult.total_logs_analyzed,
                                anomaly_rate: clusterResult.anomaly_rate
                            },
                            critical_anomalies: clusterResult.top_anomalies,
                            host_breakdown: clusterResult.host_breakdown,
                            cluster_info: {
                                cluster_id: selectedCluster,
                                hosts_analyzed: clusterResult.hosts_analyzed,
                                successful_hosts: clusterResult.successful_hosts,
                                failed_hosts: clusterResult.failed_hosts
                            }
                        }
                    });

                    if (clusterResult.storage_id) {
                        window.lastAnomalyResult = {
                            storage_info: {
                                analysis_id: clusterResult.storage_id
                            }
                        };
                    }

                    return;
                } catch (error) {
                    console.error('Cluster analysis error:', error);
                    alert('Cluster analizi sırasında hata oluştu: ' + error.message);
                    return;
                } finally {
                    window.showLoader(false);
                }
            } else {
                // Single mode: dropdown'dan seç
                hostFilter = document.getElementById('mongodbHostSelect')?.value; // ✅ const yerine sadece atama

                if (!hostFilter) {
                    alert('Lütfen bir MongoDB sunucusu seçin!');
                    return;
                }
                requestData.host_filter = hostFilter;
                requestData.analysis_mode = 'single';
                requestData.file_path = 'opensearch';
                console.log('Single mode - selected host:', hostFilter);
            }

            console.log('OpenSearch Analysis Configuration:', {
                mode: hostMode,
                hosts: hostFilter,
                hostCount: hostFilter ? hostFilter.split(',').length : 0,
                timeRange: requestData.time_range,
                customStartTime: requestData.start_time || 'N/A',
                customEndTime: requestData.end_time || 'N/A'
            });

            break;
        }

        default:
            console.log('Unknown data source for analysis:', window.selectedDataSource);
    }

    console.log('Final Request Data for Analysis:', JSON.stringify(requestData, null, 2));
    console.log('Request Data - Source Type:', requestData.source_type);
    console.log('Request Data - Host Filter:', requestData.host_filter);

    closeAnomalyModal();
    window.showLoader();

    try {
        console.log('Sending analysis request to API...');
        console.log('API Endpoint:', window.API_ENDPOINTS.analyzeLog);
        console.log('Request Method: POST');
        console.log('Request Headers: Content-Type: application/json');
        console.log('Request Body:', JSON.stringify(requestData, null, 2));

        const response = await fetch(window.API_ENDPOINTS.analyzeLog, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestData)
        });

        console.log('Analysis response status:', response.status);
        console.log('Analysis response headers:', response.headers);

        const result = await response.json();
        console.log('Analysis result received:', result);
        console.log('BACKEND RESPONSE:', {
            durum: result.durum,
            işlem: result.işlem,
            açıklama: result.açıklama ? result.açıklama.substring(0, 100) + '...' : 'YOK',
            hasResult: !!result.sonuç,
            resultKeys: result.sonuç ? Object.keys(result.sonuç) : []
        });

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

        // Analiz başarılıysa history'ye ekle
        if (result.durum !== 'hata' && result.işlem === 'anomaly_analysis') {
            let queryText = '';
            if (window.selectedDataSource === 'opensearch' && requestData.host_filter) {
                queryText = `${requestData.host_filter} için anomali analizi`;
            } else if (window.selectedDataSource === 'upload' && requestData.file_path) {
                const fileName = requestData.file_path.split('/').pop();
                queryText = `${fileName} dosyası için anomali analizi`;
            } else if (window.selectedDataSource === 'test_servers' && requestData.server_name) {
                queryText = `${requestData.server_name} sunucusu için anomali analizi`;
            } else {
                queryText = `Anomali analizi (${window.selectedDataSource})`;
            }

            const timeRangeText =
                timeRange === 'last_24h' ? 'son 24 saat' :
                timeRange === 'last_7d' ? 'son 7 gün' :
                timeRange === 'last_30d' ? 'son 30 gün' : '';

            if (timeRangeText) {
                queryText += ` - ${timeRangeText}`;
            }

            console.log('Adding manual anomaly analysis to history:', queryText);

            const historyItem = {
                id: Date.now(),
                timestamp: new Date().toISOString(),
                query: queryText,
                type: 'anomaly',
                category: 'anomaly',
                result: result,
                durum: result.durum || 'tamamlandı',
                işlem: 'anomaly_analysis',
                isManualAnalysis: true,
                sourceType: window.selectedDataSource,
                hasResult: true,
                childResult: result
            };

            window.queryHistory.unshift(historyItem);
            if (window.queryHistory.length > window.MAX_HISTORY_ITEMS) {
                window.queryHistory = window.queryHistory.slice(0, window.MAX_HISTORY_ITEMS);
            }

            window.saveHistory();
            window.updateHistoryDisplay();

            console.log('Manual anomaly analysis added to history successfully');
        }
    } catch (error) {
        console.error('Analiz hatası:', error);
        console.error('Analysis request failed:', error);
        console.error('Error details:', error.message);
        console.error('Error stack:', error.stack);
        alert('Analiz sırasında bir hata oluştu!');
    } finally {
        window.showLoader(false);
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
        if (window.selectedDataSource === 'upload') {
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

    const elements = window.elements;

    // Hata durumu kontrolü
    if (result.durum === 'hata' || !result.sonuç) {
        console.log('Error in anomaly analysis:', result.açıklama);
        let html = '<div class="anomaly-error">';
        html += '<h3>❌ Analiz Hatası</h3>';
        html += `<p>${window.escapeHtml(result.açıklama || "Analiz sırasında bir hata oluştu")}</p>`;

        // Eğer API rate limit hatası ise özel mesaj
        if (result.açıklama && result.açıklama.includes('rate_limit_exceeded')) {
            html += '<p class="info-message">💡 <strong>Not:</strong> AI açıklama servisi token limiti aşıldığı için kullanılamadı. Anomali analizi başarıyla tamamlandı ancak AI destekli açıklamalar oluşturulamadı.</p>';
            html += '<p>Lütfen birkaç dakika bekleyip tekrar deneyin veya daha küçük bir zaman aralığı seçin.</p>';
        }

        html += '</div>';
        elements.resultContent.innerHTML = html;
        return;
    }

    // Backend'den gelen tüm veriyi kontrol et
    const mlData = result.sonuç?.data || result.sonuç || {};
    const summary = mlData.summary || {};
    const componentAnalysis = mlData.component_analysis || {};
    const temporalAnalysis = mlData.temporal_analysis || {};
    const featureImportance = mlData.feature_importance || {};
    const criticalAnomalies = mlData.critical_anomalies || [];
    console.log('[DEBUG FRONTEND] displayAnomalyResults - criticalAnomalies length:', criticalAnomalies.length);
    console.log('[DEBUG FRONTEND] mlData structure:', Object.keys(mlData));
    console.log('[DEBUG FRONTEND] result.sonuç structure:', Object.keys(result.sonuç || {}));
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

    // Server bilgisini göster (eğer varsa)
    if (result.server_info) {
        html += `<div class="server-info-banner">
            📍 Analiz Sunucusu: ${result.server_info.server_name || 'Bilinmiyor'}
            ${result.server_info.model_version ? `| Model: v${result.server_info.model_version}` : ''}
        </div>`;
    }

    // ML Model Performans Metrikleri
    if (summary.total_logs || anomalyScoreStats.min !== undefined) {
        html += renderMLModelMetrics(summary, anomalyScoreStats);
    }

    // Online Learning Status Göstergesi
    if (mlData.online_learning_status || summary.online_learning_status) {
        const onlineStatus = mlData.online_learning_status || summary.online_learning_status;
        html += renderOnlineLearningStatus(onlineStatus);
    }

    // Temporal Analysis Heatmap
    if (temporalAnalysis.hourly_distribution) {
        html += renderTemporalHeatmap(temporalAnalysis);
    }

    // Severity Distribution Göster
    if (result.sonuç.severity_distribution) {
        html += renderSeverityDistribution(result.sonuç.severity_distribution);
    }

    // Kritik anomaliler
    if (criticalAnomalies.length > 0) {
        console.log('[DEBUG FRONTEND] About to render critical anomalies section with', criticalAnomalies.length, 'items');
        html += '<div class="critical-anomalies-section expanded-view">'; // expanded-view class'ı eklendi
        html += `<h3>⚠️ Kritik Anomaliler (${criticalAnomalies.length} toplam)</h3>`;
        html += `
            <div class="view-controls">
                <button class="btn-view-mode" onclick="toggleViewMode('compact')">📱 Kompakt</button>
                <button class="btn-view-mode active" onclick="toggleViewMode('expanded')">🖥️ Geniş</button>
                <button class="btn-view-mode" onclick="toggleViewMode('fullscreen')">⛶ Tam Ekran</button>
            </div>
        `;
        html += '<div class="anomaly-list" id="criticalAnomaliesList">';
        
        // İlk 20 anomaliyi göster
        const itemsToShow = 20;
        const visibleAnomalies = criticalAnomalies.slice(0, itemsToShow);
        const remainingCount = criticalAnomalies.length - itemsToShow;

        visibleAnomalies.forEach(anomaly => {
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
                            ${anomaly.host ? `<span class="host-badge">📍 ${anomaly.host}</span>` : ''}
                        </div>
                    </div>
                    <div class="anomaly-content">
                        <div class="anomaly-main-message">
                            ${isLongMessage ? `
                                <div class="message-expandable">
                                    <div class="message-preview">
                                        <pre class="log-message-pre">${window.escapeHtml(fullMessage.substring(0, 500))}...</pre>
                                    </div>
                                    <div class="message-full" style="display: none;">
                                        <pre class="log-message-pre">${window.escapeHtml(fullMessage)}</pre>
                                    </div>
                                    <button class="btn-expand" onclick="toggleMessageExpand(this)">
                                        Tam Mesajı Göster
                                    </button>
                                </div>
                            ` : `
                                <pre class="log-message-pre">${window.escapeHtml(fullMessage)}</pre>
                            `}
                        </div>
                    </div>
                </div>
            `;
        });

        // "Daha fazla göster" butonu ekle
        if (remainingCount > 0) {
            html += `
                <div class="load-more-section" style="text-align: center; margin: 20px 0;">
                    <button class="btn btn-secondary" onclick="loadMoreCriticalAnomalies()" id="loadMoreCriticalBtn">
                        Daha Fazla Göster (+${remainingCount} anomali)
                    </button>
                </div>
            `;
        }

        html += '</div>';
        html += '</div>';

        window.allCriticalAnomalies = criticalAnomalies;
        window.currentlyShownCount = itemsToShow;
    }

    // Tüm anomaliler (eğer kritik anomaliler gösterildiyse atlayabilir)
    if (result.anomalies && result.anomalies.length > 0 && !criticalAnomalies.length) {
        html += '<div class="all-anomalies-section">';
        html += '<h3>📊 Tüm Anomaliler</h3>';
        html += '<div class="anomaly-list">';

        result.anomalies.slice(0, 100).forEach(anomaly => {
            const severityClass = anomaly.anomaly_score > 0.8 ? 'high' : 
                                 anomaly.anomaly_score > 0.6 ? 'medium' : 'low';
            
            html += `
                <div class="anomaly-item ${severityClass}">
                    <div class="anomaly-score">${anomaly.anomaly_score.toFixed(3)}</div>
                    <div class="anomaly-details">
                        <div class="anomaly-time">${new Date(anomaly.timestamp).toLocaleString('tr-TR')}</div>
                        <div class="anomaly-message">${window.escapeHtml(anomaly.message)}</div>
                        ${anomaly.component ? `<div class="anomaly-component">Component: ${window.escapeHtml(anomaly.component)}</div>` : ''}
                    </div>
                </div>
            `;
        });

        if (result.anomalies.length > 100) {
            html += `<p class="more-anomalies">... ve ${result.anomalies.length - 100} anomali daha</p>`;
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
                    <div class="component-name">${window.escapeHtml(component)}</div>
                    <div class="component-count">${count} anomali</div>
                    <div class="component-bar" style="width: ${percentage}%"></div>
                    <div class="component-percentage">${percentage}%</div>
                </div>
            `;
        });
        html += '</div>';
        html += '</div>';
    }

    // Hata durumu (tekrar kontrol)
    if (result.durum === "hata") {
        console.log('Error result detected:', result.açıklama);
        html = '<div class="anomaly-error">';
        html += '<h3>❌ Hata</h3>';
        html += `<p>${window.escapeHtml(result.açıklama || "Bilinmeyen hata")}</p>`;
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

    // YENİ: Data'yı güvenilir şekilde set et
    window.lastAnomalyResult = result;

    // Fallback: Eğer critical_anomalies yoksa, normal anomalies'i critical olarak ekle
    if (result.sonuç && (!result.sonuç.critical_anomalies || result.sonuç.critical_anomalies.length === 0)) {
        if (result.sonuç.data?.critical_anomalies) {
            result.sonuç.critical_anomalies = result.sonuç.data.critical_anomalies;
        } else if (result.anomalies) {
            result.sonuç.critical_anomalies = result.anomalies;
        }
    }

    console.log('Anomaly result saved to window.lastAnomalyResult');
    console.log('Critical anomalies count:', result.sonuç?.critical_anomalies?.length || 0);
    console.log('Feature importance available:', !!(result.sonuç?.feature_importance));

    // Storage info varsa göster
    if (result.storage_info) {
        console.log('Analysis auto-saved with ID:', result.storage_info.analysis_id);

        // Bildirim göster
        setTimeout(() => {
            window.showNotification(
                `✅ Analiz otomatik olarak kaydedildi (ID: ${result.storage_info.analysis_id.substring(0, 8)}...)`,
                'success'
            );
        }, 1000);

        // Geçmişe storage bilgisini ekle
        if (window.lastAnomalyResult) {
            window.lastAnomalyResult.storage_id = result.storage_info.analysis_id;
            window.lastAnomalyResult.storage_path = result.storage_info.file_path;
        }
    }

    // ============================================
    // FILTER SİSTEMİ BAŞLATMA
    // ============================================
    // Critical anomalies varsa filter sistemini başlat
    const criticalAnomaliesForFilter = result.sonuç?.critical_anomalies ||
                                       result.sonuç?.data?.critical_anomalies ||
                                       [];

    console.log('🔍 [FILTER] Checking for critical anomalies...');
    console.log('🔍 [FILTER] Critical anomalies count:', criticalAnomaliesForFilter.length);

    if (criticalAnomaliesForFilter.length > 0) {
        setTimeout(() => {
            console.log('🔍 [FILTER] Initializing filter system with', criticalAnomaliesForFilter.length, 'anomalies');
            try {
                // 1. Filter sistemini başlat (veriyi yükle)
                window.initializeLogFilter(criticalAnomaliesForFilter);
                console.log('✅ [FILTER] Filter system initialized');

                // 2. Filter panelini DOM'a ekle (eğer yoksa)
                if (!document.getElementById('logFilterPanel')) {
                    const filterPanelHTML = window.renderLogFilterPanel();
                    document.body.insertAdjacentHTML('beforeend', filterPanelHTML);
                    console.log('✅ [FILTER] Filter panel added to DOM');
                } else {
                    console.log('ℹ️ [FILTER] Filter panel already exists, updating data...');
                    const componentOptions = document.getElementById('componentFilterOptions');
                    const severityOptions = document.getElementById('severityFilterOptions');
                    const hostOptions = document.getElementById('hostFilterOptions');

                    if (componentOptions) {
                        componentOptions.innerHTML = renderComponentOptions();
                    }
                    if (severityOptions) {
                        severityOptions.innerHTML = renderSeverityOptions();
                    }
                    if (hostOptions) {
                        hostOptions.innerHTML = renderHostOptions();
                    }
                    console.log('✅ [FILTER] Filter options updated');
                }

                // 3. İstatistikleri güncelle
                window.updateFilterStats();
                console.log('✅ [FILTER] Filter stats updated');

                // 4. Kullanıcıya bildirim göster
                window.showNotification(
                    `🔍 ${criticalAnomaliesForFilter.length} anomali filtrelemeye hazır`,
                    'info'
                );
            } catch (error) {
                console.error('❌ [FILTER] Error initializing filter system:', error);
                console.error('Error stack:', error.stack);
            }
        }, 200);
    } else {
        console.log('ℹ️ [FILTER] No critical anomalies found, filter system not needed');
    }
}

/**
 * Kaydedilmiş analizi görüntüle
 */
async function viewStoredAnalysis(analysisId) {
    try {
        const response = await fetch(`${window.API_ENDPOINTS.anomalyDetail}/${analysisId}?api_key=${window.apiKey}`);
        
        if (response.ok) {
            const data = await response.json();
            
            // Detayları göster
            displayAnomalyResults({
                durum: 'tamamlandı',
                işlem: 'anomaly_analysis',
                sonuç: data.analysis
            });
            
            window.closeModal();
        }
    } catch (error) {
        console.error('Error loading analysis detail:', error);
        window.showNotification('Analiz detayı yüklenemedi', 'error');
    }
}

/**
 * Anomaliyi detaylı incele
 */
function investigateAnomaly(index) {
    console.log('Investigating anomaly at index:', index);
    window.showNotification('Anomali detaylı analizi başlatılıyor...', 'info');
}

/**
 * Daha fazla kritik anomali göster (Pagination)
 */
function loadMoreCriticalAnomalies() {
    if (!Array.isArray(window.allCriticalAnomalies) || typeof window.currentlyShownCount !== 'number') {
        console.error('[ANOMALY PAGINATION] Anomaly data not available or not initialized');
        return;
    }
    const nextBatch = 20;
    const currentCount = window.currentlyShownCount;
    const totalCount = window.allCriticalAnomalies.length;
    const startIndex = currentCount;
    const endIndex = Math.min(currentCount + nextBatch, totalCount);
    const newAnomalies = window.allCriticalAnomalies.slice(startIndex, endIndex);

    const anomalyList = document.getElementById('criticalAnomaliesList');
    if (!anomalyList) {
        console.error('[ANOMALY PAGINATION] Anomaly list container not found');
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
                        <span class="anomaly-time">${anomaly.timestamp ? new Date(anomaly.timestamp).toLocaleString('tr-TR') : '-'}</span>
                        <span class="severity-badge ${severityLevel.toLowerCase()}">${severityLevel}</span>
                        <span class="severity-score-inline">${severityScore}/100</span>
                        ${anomaly.component ? `<span class="component-badge">${anomaly.component}</span>` : ''}
                    </div>
                </div>
                <div class="anomaly-message">
                    ${
                        isLongMessage
                        ? `
                            <div class="message-preview">
                                <pre class="log-message-pre">${window.escapeHtml(fullMessage.substring(0, 500))}...</pre>
                            </div>
                            <div class="message-full" style="display: none;">
                                <pre class="log-message-pre">${window.escapeHtml(fullMessage)}</pre>
                            </div>
                            <button class="btn-expand" onclick="window.toggleMessageExpand(this)">
                                Tam Mesajı Göster
                            </button>
                        `
                        : `<pre class="log-message-pre">${window.escapeHtml(fullMessage)}</pre>`
                    }
                </div>
            </div>
        `;
    });
    
    // Butonu kaldır
    const loadMoreBtn = document.getElementById('loadMoreCriticalBtn');
    if (loadMoreBtn && loadMoreBtn.parentElement) {
        loadMoreBtn.parentElement.remove();
    }
    
    // Yeni HTML'i ekle
    anomalyList.insertAdjacentHTML('beforeend', html);

    window.currentlyShownCount = endIndex;

    // Kalan anomaly için yeniden "Daha Fazla" ekle
    const remainingCount = totalCount - endIndex;
    if (remainingCount > 0) {
        const loadMoreHtml = `
            <div class="load-more-section" style="text-align: center; margin: 20px 0;">
                <button class="btn btn-secondary" onclick="window.loadMoreCriticalAnomalies()" id="loadMoreCriticalBtn">
                    Daha Fazla Göster (+${remainingCount} anomali)
                </button>
            </div>
        `;
        anomalyList.insertAdjacentHTML('afterend', loadMoreHtml);
    }

    console.debug(`[ANOMALY PAGINATION] Loaded anomalies: ${startIndex + 1}-${endIndex} of ${totalCount}`);
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
        window.showNotification('Gösterilecek anomali sonucu bulunamadı. Önce bir anomali analizi yapın.', 'warning');
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
                            <strong>Log:</strong> ${window.escapeHtml(anomaly.message)}
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
        window.showLoader(true);
        window.showNotification('Detaylı anomali verileri yükleniyor...', 'info');
        
        // Mevcut analiz parametrelerini kullan
        const lastParams = window.lastAnalysisParams || {};
        
        const response = await fetch('/api/get-detailed-anomalies', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                api_key: window.apiKey,
                source_type: lastParams.source_type || 'opensearch',
                host_filter: lastParams.host_filter,
                time_range: lastParams.time_range || 'last_day',
                limit: 2000 // Maksimum 2000 anomali getir
            })
        });
        
        window.showLoader(false);
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        
        if (data.anomalies && data.anomalies.length > 0) {
            // Detaylı veriyi göster
            const detailedAnomalies = data.anomalies.map(anomaly => ({
                ...anomaly,
                anomaly_type: detectAnomalyType(anomaly)  // ✅ Aynı dosya, window. YOK
            }));
            
            // Modal oluştur ve göster
            showDetailedAnomalyModal(detailedAnomalies);  // ✅ Aynı dosya, window. YOK
        } else {
            window.showNotification('Detaylı anomali verisi bulunamadı', 'warning');
        }
        
    } catch (error) {
        window.showLoader(false);
        console.error('Detaylı anomali verisi alınırken hata:', error);
        window.showNotification('Detaylı veriler yüklenemedi', 'error');
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

/**
 * Anomali verisini dışa aktar
 */
function exportAnomalyData(historyId) {
    const item = window.queryHistory.find(h => h.id === historyId);
    if (!item || !item.childResult) {
        window.showNotification('İndirilecek veri bulunamadı', 'warning');
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
    
    window.showNotification('Analiz verisi indirildi', 'success');
}

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
        html += `<td class="timestamp">${window.formatTimestamp(anomaly.timestamp)}</td>`;
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
                                <pre>${window.escapeHtml(anomaly.message.substring(0, 300))}...</pre>
                            </div>
                            <div class="message-full" style="display:none">
                                <pre>${window.escapeHtml(anomaly.message)}</pre>
                            </div>
                            <button class="btn-expand" onclick="window.toggleMessageExpand(this)">Detay</button>
                        </div>
                    ` : `
                        <pre class="message-full">${window.escapeHtml(anomaly.message || '')}</pre>
                    `}
                 </td>`;
        html += `<td class="actions">
                    <button class="btn-investigate" onclick="window.investigateAnomaly(${anomaly.index || index})">
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
 * ML Insights Oluştur (Business Logic)
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
 * Kaydedilmiş analizi görüntüle
 */
async function viewStoredAnalysis(analysisId) {
    try {
        const response = await fetch(`${window.API_ENDPOINTS.anomalyDetail}/${analysisId}?api_key=${window.apiKey}`);
        
        if (response.ok) {
            const data = await response.json();
            
            // Detayları göster
            displayAnomalyResults({
                durum: 'tamamlandı',
                işlem: 'anomaly_analysis',
                sonuç: data.analysis
            });
            
            window.closeModal();
        }
    } catch (error) {
        console.error('Error loading analysis detail:', error);
        window.showNotification('Analiz detayı yüklenemedi', 'error');
    }
}

/**
 * Belirli bir anomali chunk'ını yükle
 */
async function loadAnomalyChunk(analysisId, chunkIndex) {
    if (!analysisId) {
        window.showNotification('Analysis ID bulunamadı', 'error');
        return;
    }
    
    // Loading göster
    window.showLoader(true);
    window.elements.resultSection.style.display = 'block';
    window.elements.resultContent.innerHTML = '<div class="loading-chunk">Chunk yükleniyor...</div>';
    
    try {
        const response = await fetch('/api/get-anomaly-chunk', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                analysis_id: analysisId,
                chunk_index: parseInt(chunkIndex),
                api_key: window.apiKey
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
            window.elements.resultSection.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            
            window.showNotification(`Chunk ${result.chunk_index + 1}/${result.total_chunks} yüklendi`, 'success');
        } else {
            throw new Error(result.error || 'Chunk yüklenemedi');
        }
        
    } catch (error) {
        console.error('Chunk yükleme hatası:', error);
        window.showNotification('Chunk yüklenirken hata oluştu: ' + error.message, 'error');
        window.elements.resultContent.innerHTML = '<div class="error-message">Chunk yüklenemedi. Lütfen tekrar deneyin.</div>';
    } finally {
        window.showLoader(false);
    }
}

// ============================================
// GLOBAL ERİŞİM İÇİN WINDOW'A ATAMA
// ============================================
window.updateParentAnomalyQuery = updateParentAnomalyQuery;
window.displayChatAnomalyResult = displayAnomalyResults;  // Mevcut fonksiyona yönlendir
window.decodeHtmlEntities = decodeHtmlEntities;
window.formatAIResponse = formatAIResponse;
window.displayAnomalyAnalysisResult = displayAnomalyAnalysisResult;
window.exportAnomalyReport = exportAnomalyReport;
window.scheduleFollowUp = scheduleFollowUp;
window.saveFollowUp = saveFollowUp;
window.formatSection = formatSection;
window.highlightNumbers = highlightNumbers;
window.parseAIExplanationFromText = parseAIExplanationFromText;
window.handleAnalyzeLog = handleAnalyzeLog;
window.closeAnomalyModal = closeAnomalyModal;
window.displayAnomalyResults = displayAnomalyResults;
window.viewStoredAnalysis = viewStoredAnalysis;
window.investigateAnomaly = investigateAnomaly;
window.loadAnomalyChunk = loadAnomalyChunk;
window.loadMoreCriticalAnomalies = loadMoreCriticalAnomalies;
window.toggleDetailedAnomalyList = toggleDetailedAnomalyList;
window.detectAnomalyType = detectAnomalyType;
window.renderDetailedAnomalyList = renderDetailedAnomalyList;
window.getAnomalyExplanation = getAnomalyExplanation;
window.renderCriticalAnomaliesTable = renderCriticalAnomaliesTable;
window.generateMLInsights = generateMLInsights;
console.log('✅ Anomaly module loaded successfully');

