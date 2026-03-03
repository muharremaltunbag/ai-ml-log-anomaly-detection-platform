// web_ui/static/script-dba-explorer.js
/**
 * LC Waikiki MongoDB Assistant - DBA Log Explorer Module
 * 
 * Bu modül DBA Explorer panelini yönetir:
 * - Server-side filtreleme
 * - Pagination
 * - Anomali detay görüntüleme
 */

console.log('🔧 Loading script-dba-explorer.js...');

// ============================================
// DBA EXPLORER MODULE
// ============================================

const DBAExplorer = {
    // Context bilgileri
    context: {
        hostName: null,
        startTime: null,
        endTime: null,
        analysisId: null
    },
    
    // Pagination state
    pagination: {
        currentSkip: 0,
        pageSize: 50,
        totalCount: 0,
        isLoading: false
    },
    
    // Current filter values
    filters: {
        component: 'ALL',
        minSeverity: 0,
        pattern: ''
    },

    /**
     * Context ayarla (analiz sonucu geldiğinde çağrılır)
     */
    setContext: function(hostName, startTime, endTime, analysisId) {
        console.log('🔧 [DBA Explorer] Setting context:', { hostName, startTime, endTime, analysisId });
        
        this.context.hostName = hostName;
        this.context.startTime = startTime;
        this.context.endTime = endTime;
        this.context.analysisId = analysisId;
        
        // Reset pagination
        this.pagination.currentSkip = 0;
        this.pagination.totalCount = 0;
        
        // Update UI badge
        const hostBadge = document.getElementById('currentHostBadge');
        if (hostBadge && hostName) {
            hostBadge.textContent = `Host: ${hostName}`;
            hostBadge.style.display = 'inline-block';
        }
        
        console.log('✅ [DBA Explorer] Context set successfully');
    },

    /**
     * Event listener'ları bağla
     */
    bindEvents: function() {
        console.log('🔧 [DBA Explorer] Binding events...');
        
        // Filter Apply Button
        const applyBtn = document.getElementById('btnApplyFilter');
        if (applyBtn) {
            // Önceki listener'ı kaldır (duplicate önleme)
            applyBtn.replaceWith(applyBtn.cloneNode(true));
            const newApplyBtn = document.getElementById('btnApplyFilter');
            newApplyBtn.addEventListener('click', () => this.applyFilters());
            console.log('  ✓ Apply filter button bound');
        }
        
        // Filter Reset Button
        const resetBtn = document.getElementById('btnResetFilter');
        if (resetBtn) {
            resetBtn.replaceWith(resetBtn.cloneNode(true));
            const newResetBtn = document.getElementById('btnResetFilter');
            newResetBtn.addEventListener('click', () => this.resetFilters());
            console.log('  ✓ Reset filter button bound');
        }
        
        // Load More Button
        const loadMoreBtn = document.getElementById('btnLoadMoreAnomalies');
        if (loadMoreBtn) {
            loadMoreBtn.replaceWith(loadMoreBtn.cloneNode(true));
            const newLoadMoreBtn = document.getElementById('btnLoadMoreAnomalies');
            newLoadMoreBtn.addEventListener('click', () => this.loadMore());
            console.log('  ✓ Load more button bound');
        }
        
        // Severity Range Slider
        const severityRange = document.getElementById('filterSeverityRange');
        const severityValue = document.getElementById('filterSeverityValue');
        if (severityRange && severityValue) {
            severityRange.addEventListener('input', (e) => {
                severityValue.textContent = e.target.value;
                this.filters.minSeverity = parseInt(e.target.value);
            });
            console.log('  ✓ Severity slider bound');
        }
        
        // Component Select
        const componentSelect = document.getElementById('filterComponent');
        if (componentSelect) {
            componentSelect.addEventListener('change', (e) => {
                this.filters.component = e.target.value;
            });
            console.log('  ✓ Component select bound');
        }
        
        // Pattern Input
        const patternInput = document.getElementById('filterPattern');
        if (patternInput) {
            patternInput.addEventListener('input', (e) => {
                this.filters.pattern = e.target.value;
            });
            // Enter tuşu ile filtreleme
            patternInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    this.applyFilters();
                }
            });
            console.log('  ✓ Pattern input bound');
        }
        
        console.log('✅ [DBA Explorer] All events bound successfully');
    },

    /**
     * Filtreleri uygula ve verileri getir
     */
    applyFilters: async function() {
        console.log('🔍 [DBA Explorer] Applying filters...');
        
        // Context kontrolü
        if (!this.context.analysisId && !this.context.hostName) {
            console.warn('⚠️ [DBA Explorer] No context set, cannot filter');
            if (window.showNotification) {
                window.showNotification('Önce bir anomali analizi yapmalısınız', 'warning');
            }
            return;
        }
        
        // UI'dan filter değerlerini al
        const componentSelect = document.getElementById('filterComponent');
        const severityRange = document.getElementById('filterSeverityRange');
        const patternInput = document.getElementById('filterPattern');
        
        this.filters.component = componentSelect?.value || 'ALL';
        this.filters.minSeverity = parseInt(severityRange?.value || '0');
        this.filters.pattern = patternInput?.value || '';
        
        // Reset pagination for new filter
        this.pagination.currentSkip = 0;
        
        // Fetch data
        await this.fetchFilteredAnomalies(false);
    },

    /**
     * Filtreleri sıfırla
     */
    resetFilters: function() {
        console.log('🗑️ [DBA Explorer] Resetting filters...');
        
        // Reset filter values
        this.filters = {
            component: 'ALL',
            minSeverity: 0,
            pattern: ''
        };
        
        // Reset UI
        const componentSelect = document.getElementById('filterComponent');
        const severityRange = document.getElementById('filterSeverityRange');
        const severityValue = document.getElementById('filterSeverityValue');
        const patternInput = document.getElementById('filterPattern');
        
        if (componentSelect) componentSelect.value = 'ALL';
        if (severityRange) severityRange.value = '0';
        if (severityValue) severityValue.textContent = '0';
        if (patternInput) patternInput.value = '';
        
        // Reset pagination
        this.pagination.currentSkip = 0;
        
        // Clear results table
        const tbody = document.getElementById('dbaResultsBody');
        if (tbody) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="4" style="text-align: center; padding: 20px; color: #777;">
                        Filtreleme yapmak için yukarıdaki kriterleri seçip "Filtrele & Getir" butonuna basın.
                    </td>
                </tr>
            `;
        }
        
        // Hide pagination
        const pagination = document.getElementById('dbaPagination');
        if (pagination) pagination.style.display = 'none';
        
        if (window.showNotification) {
            window.showNotification('Filtreler sıfırlandı', 'info');
        }
    },

    /**
     * Daha fazla veri yükle
     */
    loadMore: async function() {
        if (this.pagination.isLoading) return;
        
        this.pagination.currentSkip += this.pagination.pageSize;
        await this.fetchFilteredAnomalies(true);
    },

    /**
     * Backend'den filtrelenmiş anomalileri getir
     */
    fetchFilteredAnomalies: async function(append = false) {
        if (this.pagination.isLoading) return;
        
        this.pagination.isLoading = true;
        
        const loadMoreBtn = document.getElementById('btnLoadMoreAnomalies');
        const tbody = document.getElementById('dbaResultsBody');
        const applyBtn = document.getElementById('btnApplyFilter');
        
        // Loading state
        if (loadMoreBtn) loadMoreBtn.disabled = true;
        if (applyBtn) {
            applyBtn.disabled = true;
            applyBtn.innerHTML = '⏳ Yükleniyor...';
        }
        
        if (!append && tbody) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="4" style="text-align: center; padding: 30px;">
                        <div class="loading-spinner">⏳</div>
                        <p>Veriler sunucudan çekiliyor...</p>
                    </td>
                </tr>
            `;
        }
        
        try {
            // Request body hazırla
            const requestBody = {
                api_key: window.apiKey,
                analysis_id: this.context.analysisId,
                host_filter: this.context.hostName,
                // "ALL" ise null gönder (backend tüm component'leri getirir)
                component: this.filters.component === 'ALL' ? null : this.filters.component,
                min_severity: this.filters.minSeverity,
                pattern: this.filters.pattern || null,  // Boş string yerine null
                skip: this.pagination.currentSkip,
                limit: this.pagination.pageSize
            };
            // Zaman aralığı (varsa)
            if (this.context.startTime) requestBody.start_time = this.context.startTime;
            if (this.context.endTime) requestBody.end_time = this.context.endTime;
            
            console.log('📡 [DBA Explorer] Fetching with params:', requestBody);
            
            // API endpoint - backend'deki doğru path
            const endpoint = window.API_ENDPOINTS?.filterAnomalies || '/api/anomalies/filter';
            
            const response = await fetch(endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(requestBody)
            });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const result = await response.json();
            console.log('📥 [DBA Explorer] Received:', result);
            
            // Sonuçları render et
            this.renderResults(result, append);
            
        } catch (error) {
            console.error('❌ [DBA Explorer] Fetch error:', error);
            
            if (tbody) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="4" style="text-align: center; padding: 30px; color: #e74c3c;">
                            <strong>Veri cekilirken hata olustu</strong>
                            <p style="font-size: 12px; margin-top: 10px;">${error.message}</p>
                            <p style="font-size: 13px; color: #888;">API endpoint: ${window.API_ENDPOINTS?.filterAnomalies || '/api/filter-anomalies'}</p>
                        </td>
                    </tr>
                `;
            }
            
            if (window.showNotification) {
                window.showNotification('Veri çekilirken hata: ' + error.message, 'error');
            }
        } finally {
            this.pagination.isLoading = false;
            
            if (loadMoreBtn) loadMoreBtn.disabled = false;
            if (applyBtn) {
                applyBtn.disabled = false;
                applyBtn.innerHTML = 'Filtrele';
            }
        }
    },

    /**
     * Sonuçları tabloya render et
     */
    renderResults: function(result, append = false) {
        const tbody = document.getElementById('dbaResultsBody');
        const pagination = document.getElementById('dbaPagination');
        const countInfo = document.getElementById('dbaResultCountInfo');
        
        if (!tbody) return;
        
        const anomalies = result.anomalies || result.data || [];
        const totalCount = result.total_count || result.total || anomalies.length;
        
        this.pagination.totalCount = totalCount;
        
        // Sonuç yoksa
        if (anomalies.length === 0 && !append) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="4" style="text-align: center; padding: 30px; color: #666;">
                        <div style="font-size: 14px; margin-bottom: 10px; color: #999;">--</div>
                        <strong>Kriterlere uygun anomali bulunamadı</strong>
                        <p style="font-size: 12px; margin-top: 10px;">Farklı filtre kriterleri deneyin.</p>
                    </td>
                </tr>
            `;
            if (pagination) pagination.style.display = 'none';
            return;
        }
        
        // Append değilse tabloyu temizle
        if (!append) {
            tbody.innerHTML = '';
        }
        
        // Anomalileri render et
        anomalies.forEach(anomaly => {
            const row = document.createElement('tr');
            row.className = 'dba-result-row';
            
            const timestamp = anomaly.timestamp ? 
                new Date(anomaly.timestamp).toLocaleString('tr-TR') : '-';
            const severity = anomaly.severity_score || anomaly.severity || 0;
            const component = anomaly.component || '-';
            const message = anomaly.message || anomaly.log_message || '-';
            
            // Severity renklendirme
            let severityClass = 'low';
            if (severity >= 70) severityClass = 'critical';
            else if (severity >= 50) severityClass = 'high';
            else if (severity >= 30) severityClass = 'medium';
            
            row.innerHTML = `
                <td style="padding: 10px; white-space: nowrap;">${timestamp}</td>
                <td style="padding: 10px;">
                    <span class="severity-badge ${severityClass}">${severity}</span>
                </td>
                <td style="padding: 10px;">
                    <span class="component-badge">${window.escapeHtml ? window.escapeHtml(component) : component}</span>
                </td>
                <td style="padding: 10px; max-width: 500px;">
                    <div class="log-message-cell" title="${window.escapeHtml ? window.escapeHtml(message) : message}">
                        ${message.length > 200 ? 
                            `<span class="message-preview">${window.escapeHtml ? window.escapeHtml(message.substring(0, 200)) : message.substring(0, 200)}...</span>
                             <button class="btn-show-full" onclick="DBAExplorer.showFullMessage(this, '${encodeURIComponent(message)}')">Tam Göster</button>` 
                            : (window.escapeHtml ? window.escapeHtml(message) : message)
                        }
                    </div>
                </td>
            `;
            
            tbody.appendChild(row);
        });
        
        // Pagination göster/gizle
        const currentCount = tbody.querySelectorAll('tr').length;
        const hasMore = currentCount < totalCount;
        
        if (pagination) {
            pagination.style.display = hasMore ? 'block' : 'none';
        }
        
        if (countInfo) {
            countInfo.textContent = `${currentCount} / ${totalCount} kayıt gösteriliyor`;
        }
        
        if (window.showNotification && !append) {
            window.showNotification(`${anomalies.length} anomali bulundu (toplam: ${totalCount})`, 'success');
        }
    },

    /**
     * Tam mesajı göster
     */
    showFullMessage: function(btn, encodedMessage) {
        const message = decodeURIComponent(encodedMessage);
        const cell = btn.closest('.log-message-cell');
        
        if (cell) {
            cell.innerHTML = `<pre class="log-message-full">${window.escapeHtml ? window.escapeHtml(message) : message}</pre>`;
        }
    }
};

// ============================================
// GLOBAL ERİŞİM İÇİN WINDOW'A ATAMA
// ============================================
window.DBAExplorer = DBAExplorer;

console.log('✅ DBA Explorer module loaded successfully');