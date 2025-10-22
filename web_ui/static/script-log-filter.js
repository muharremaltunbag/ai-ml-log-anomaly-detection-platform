// web_ui/static/script-log-filter.js
/**
 * LC Waikiki MongoDB Assistant - Log Filter & Grouping Module
 * 
 * Bu modül anomali loglarının filtrelenmesi ve gruplanması işlemlerini yönetir:
 * - Component bazlı filtreleme
 * - Severity bazlı filtreleme
 * - Host bazlı filtreleme
 * - Regex/Pattern bazlı arama
 * - Filter panel UI yönetimi
 */

console.log('🔍 Loading script-log-filter.js...');

// ============================================
// FILTER STATE YÖNETİMİ
// ============================================

/**
 * Global filter state
 */
window.logFilterState = {
    isOpen: false,
    activeFilters: {
        components: [],      // Seçili component'ler
        severities: [],      // Seçili severity'ler
        hosts: [],           // Seçili host'lar
        searchPattern: '',   // Regex/text arama
        useRegex: false      // Regex modu aktif mi?
    },
    availableOptions: {
        components: [],      // Tüm component listesi
        severities: [],      // Tüm severity listesi
        hosts: []            // Tüm host listesi
    },
    originalAnomalies: [],   // Filtrelenmemiş orijinal liste
    filteredAnomalies: []    // Filtrelenmiş liste
};

// ↓↓↓ BURAYA YENİ PATTERN LIBRARY EKLENİYOR ↓↓↓

// ============================================
// ADVANCED PATTERN LIBRARY
// ============================================

/**
 * Kategorize edilmiş regex pattern kütüphanesi
 */
window.advancedPatternLibrary = {
    'error_exception': {
        title: '🔴 Error & Exception Patterns',
        icon: '🔴',
        description: 'Hata ve istisna durumlarını yakalamak için',
        patterns: [
            {
                pattern: 'error|exception|failed',
                name: 'Genel Hata Arama',
                description: 'Tüm hata, exception ve başarısız işlemleri bulur',
                complexity: 'easy',
                example: 'Connection error, Exception thrown, Operation failed'
            },
            {
                pattern: '(error|exception).*\\b(timeout|timed out)\\b',
                name: 'Zaman Aşımı Hataları',
                description: 'Timeout ile ilgili tüm hataları yakalar',
                complexity: 'medium',
                example: 'Socket error: Connection timed out'
            },
            {
                pattern: 'fatal|critical|emergency',
                name: 'Kritik Hatalar',
                description: 'Sadece kritik seviyedeki hataları gösterir',
                complexity: 'easy',
                example: 'FATAL: Database connection lost'
            },
            {
                pattern: 'stack trace|stacktrace|\\tat \\w+',
                name: 'Stack Trace',
                description: 'Stack trace içeren logları bulur',
                complexity: 'medium',
                example: 'at com.mongodb.connection (line 142)'
            },
            {
                pattern: 'out of memory|oom|memory exhausted',
                name: 'Bellek Hataları',
                description: 'Bellek yetersizliği hatalarını yakalar',
                complexity: 'easy',
                example: 'Out of memory: Java heap space'
            },
            {
                pattern: 'null pointer|nullpointer|npe',
                name: 'Null Pointer Errors',
                description: 'Null pointer exception\'ları bulur',
                complexity: 'easy',
                example: 'NullPointerException at line 523'
            },
            {
                pattern: 'assertion (failed|error)|assert\\s+\\w+\\s+failed',
                name: 'Assertion Failures',
                description: 'Test ve assertion hatalarını gösterir',
                complexity: 'medium',
                example: 'Assertion failed: expected != actual'
            }
        ]
    },
    
    'performance': {
        title: '⚡ Performance Patterns',
        icon: '⚡',
        description: 'Performans sorunlarını tespit etmek için',
        patterns: [
            {
                pattern: '\\d{3,}ms',
                name: 'Yavaş İşlemler (300ms+)',
                description: '300 milisaniye ve üzeri süren işlemler',
                complexity: 'easy',
                example: 'Query executed in 1523ms'
            },
            {
                pattern: 'slow query|query.*slow|took \\d+ms',
                name: 'Yavaş Sorgular',
                description: 'Slow query loglarını yakalar',
                complexity: 'medium',
                example: 'Slow query detected: took 2500ms'
            },
            {
                pattern: '\\d+\\.\\d+s|\\d+ seconds?|\\d+sec',
                name: 'Saniye Cinsinden Süreler',
                description: 'Saniye bazında süre bilgilerini bulur',
                complexity: 'medium',
                example: 'Operation completed in 5.2s'
            },
            {
                pattern: 'high (cpu|memory|disk)|load average',
                name: 'Yüksek Kaynak Kullanımı',
                description: 'CPU, memory, disk kullanım uyarıları',
                complexity: 'easy',
                example: 'High CPU usage detected: 95%'
            },
            {
                pattern: 'queue (full|overflow)|backlog|throttl',
                name: 'Queue ve Throttling',
                description: 'Kuyruk ve throttling sorunları',
                complexity: 'medium',
                example: 'Request queue full, throttling enabled'
            }
        ]
    },
    
    'security': {
        title: '🔒 Security Patterns',
        icon: '🔒',
        description: 'Güvenlik olaylarını yakalamak için',
        patterns: [
            {
                pattern: 'authentication (failed|error)|auth.*fail|login.*fail',
                name: 'Kimlik Doğrulama Hataları',
                description: 'Başarısız login ve auth denemelerini bulur',
                complexity: 'easy',
                example: 'Authentication failed for user admin'
            },
            {
                pattern: 'unauthorized|forbidden|access denied',
                name: 'Yetkilendirme Hataları',
                description: 'Yetkisiz erişim denemelerini gösterir',
                complexity: 'easy',
                example: 'Access denied: insufficient permissions'
            },
            {
                pattern: 'ssl|tls|certificate.*error|cert.*invalid',
                name: 'SSL/TLS Sorunları',
                description: 'Sertifika ve şifreleme hataları',
                complexity: 'medium',
                example: 'SSL certificate verification failed'
            },
            {
                pattern: 'sql injection|xss|csrf|injection attack',
                name: 'Saldırı Girişimleri',
                description: 'Bilinen saldırı pattern\'lerini yakalar',
                complexity: 'medium',
                example: 'Potential SQL injection attempt detected'
            }
        ]
    },
    
    'mongodb': {
        title: '🍃 MongoDB Specific',
        icon: '🍃',
        description: 'MongoDB\'ye özel pattern\'ler',
        patterns: [
            {
                pattern: 'replica.*set|replication|oplog',
                name: 'Replica Set İşlemleri',
                description: 'Replikasyon ve replica set logları',
                complexity: 'easy',
                example: 'Replica set configuration changed'
            },
            {
                pattern: 'primary.*chang|election|step(ping)? down',
                name: 'Primary Değişiklikleri',
                description: 'Primary node değişimlerini yakalar',
                complexity: 'medium',
                example: 'Primary node changed: election complete'
            },
            {
                pattern: 'cursor.*timeout|cursor.*kill|cursor exceeded',
                name: 'Cursor Sorunları',
                description: 'Cursor timeout ve ilgili hatalar',
                complexity: 'easy',
                example: 'Cursor timeout after 10 minutes'
            },
            {
                pattern: 'index|createIndex|dropIndex',
                name: 'Index İşlemleri',
                description: 'Index oluşturma, silme ve kullanım',
                complexity: 'easy',
                example: 'createIndex on users.email'
            },
            {
                pattern: 'shard|sharding|chunk migration',
                name: 'Sharding İşlemleri',
                description: 'Sharding ve chunk operasyonları',
                complexity: 'medium',
                example: 'Chunk migration started: users.0 -> shard02'
            },
            {
                pattern: 'journal|checkpoint|fsync',
                name: 'Journal & Storage',
                description: 'Journal, fsync ve storage işlemleri',
                complexity: 'medium',
                example: 'Journal flush took 523ms'
            }
        ]
    },
    
    'network': {
        title: '🌐 Network & Connection',
        icon: '🌐',
        description: 'Ağ ve bağlantı sorunları için',
        patterns: [
            {
                pattern: 'connection (refused|reset|timeout|closed)',
                name: 'Bağlantı Sorunları',
                description: 'Connection hataları ve kopmaları',
                complexity: 'easy',
                example: 'Connection refused: port 27017'
            },
            {
                pattern: 'socket|tcp|udp',
                name: 'Socket İşlemleri',
                description: 'Socket seviyesi ağ olayları',
                complexity: 'easy',
                example: 'Socket error: broken pipe'
            },
            {
                pattern: 'dns|resolve|hostname',
                name: 'DNS Sorunları',
                description: 'DNS çözümleme hataları',
                complexity: 'easy',
                example: 'DNS resolution failed for mongodb.local'
            },
            {
                pattern: 'port \\d+|:\\d{4,5}',
                name: 'Port Numaraları',
                description: 'Port numarası içeren loglar',
                complexity: 'easy',
                example: 'Listening on port 27017'
            },
            {
                pattern: 'network.*error|net.*fail|io.*exception',
                name: 'Genel Network Hataları',
                description: 'Tüm network ve I/O hataları',
                complexity: 'medium',
                example: 'Network I/O exception during write'
            }
        ]
    }
};

console.log('📚 [PATTERN LIBRARY] Loaded', 
    Object.keys(window.advancedPatternLibrary).length, 'categories with',
    Object.values(window.advancedPatternLibrary).reduce((sum, cat) => sum + cat.patterns.length, 0),
    'patterns'
);


// ============================================
// FILTER PANEL RENDER
// ============================================

/**
 * Filter panelini render et
 */
function renderLogFilterPanel() {
    console.log('Rendering log filter panel...');
    
    const state = window.logFilterState;
    
    let html = `
        <div id="logFilterPanel" class="log-filter-panel ${state.isOpen ? 'open' : ''}">
            <div class="filter-panel-header">
                <h4>🔍 Log Filtreleme</h4>
                <button class="btn-close-filter" onclick="toggleLogFilterPanel()">✕</button>
            </div>
            
            <div class="filter-panel-body">
                <!-- Arama / Regex -->
                <div class="filter-section">
                    <label class="filter-label">🔎 Metin Arama</label>
                    <div class="search-input-wrapper">
                        <input 
                            type="text" 
                            id="filterSearchInput" 
                            class="filter-search-input"
                            placeholder="Aramak için yazın..."
                            value="${window.escapeHtml(state.activeFilters.searchPattern)}"
                            oninput="validateRegexPattern()"
                        >
                        <label class="regex-toggle">
                            <input 
                                type="checkbox" 
                                id="filterRegexToggle"
                                ${state.activeFilters.useRegex ? 'checked' : ''}
                                onchange="validateRegexPattern()"
                            >
                            <span>Regex</span>
                        </label>
                    </div>
                    <div class="regex-validation" id="regexValidation" style="display: none;">
                        <span class="validation-icon"></span>
                        <span class="validation-message"></span>
                    </div>
                    <small class="filter-hint">Mesaj içeriğinde arama yapar</small>
                    
                    <!-- Regex Pattern Örnekleri -->
                    <div class="regex-pattern-examples" id="regexPatternExamples">
                        <label class="pattern-examples-label">💡 Örnek Pattern'ler:</label>
                        <div class="pattern-chips">
                            <span class="pattern-chip" 
                                  data-pattern="connection.*timeout"
                                  data-description="Bağlantı zaman aşımı sorunları"
                                  onclick="applyRegexPattern('connection.*timeout')">
                                connection.*timeout
                            </span>
                            <span class="pattern-chip" 
                                  data-pattern="error|warning|critical"
                                  data-description="Hata seviyesi filtreleme"
                                  onclick="applyRegexPattern('error|warning|critical')">
                                error|warning|critical
                            </span>
                            <span class="pattern-chip" 
                                  data-pattern="\\d{3,}ms"
                                  data-description="Yavaş sorgular (300ms+)"
                                  onclick="applyRegexPattern('\\d{3,}ms')">
                                \d{3,}ms
                            </span>
                            <span class="pattern-chip" 
                                  data-pattern="replica.*set"
                                  data-description="Replica set yapılandırma sorunları"
                                  onclick="applyRegexPattern('replica.*set')">
                                replica.*set
                            </span>
                            <span class="pattern-chip" 
                                  data-pattern="authentication.*failed"
                                  data-description="Kimlik doğrulama hataları"
                                  onclick="applyRegexPattern('authentication.*failed')">
                                authentication.*failed
                            </span>
                            <span class="pattern-chip" 
                                  data-pattern="primary.*changed"
                                  data-description="Primary node değişiklikleri"
                                  onclick="applyRegexPattern('primary.*changed')">
                                primary.*changed
                            </span>
                        </div>
                        <small class="pattern-hint">💡 Bir pattern'e tıklayarak hızlıca arama yapabilirsiniz</small>
                    </div>
                    
                    <!-- Advanced Pattern Library -->
                    <div class="pattern-library-container">
                        <button class="btn-toggle-library" onclick="togglePatternLibrary()">
                            📚 Pattern Kütüphanesini Aç (25+ Hazır Pattern)
                        </button>
                        <div class="pattern-library-wrapper" id="patternLibraryWrapper" style="display: none;">
                            ${renderPatternLibrary()}
                        </div>
                    </div>
                </div>
                
                <!-- Component Filtreleme -->
                <div class="filter-section">
                    <label class="filter-label">📦 Component</label>
                    <div class="filter-options" id="componentFilterOptions">
                        ${renderComponentOptions()}
                    </div>
                </div>
                
                <!-- Severity Filtreleme -->
                <div class="filter-section">
                    <label class="filter-label">⚠️ Severity</label>
                    <div class="filter-options" id="severityFilterOptions">
                        ${renderSeverityOptions()}
                    </div>
                </div>
                
                <!-- Host Filtreleme -->
                <div class="filter-section">
                    <label class="filter-label">🖥️ Host</label>
                    <div class="filter-options" id="hostFilterOptions">
                        ${renderHostOptions()}
                    </div>
                </div>
                
                <!-- Aktif Filtreler Özeti -->
                <div class="active-filters-summary">
                    <strong>Aktif Filtreler:</strong>
                    <div id="activeFilterTags"></div>
                </div>
                
                <!-- Action Buttons -->
                <div class="filter-actions">
                    <button class="btn btn-primary btn-small" onclick="applyLogFilters()">
                        ✓ Filtrele
                    </button>
                    <button class="btn btn-secondary btn-small" onclick="clearLogFilters()">
                        ✕ Temizle
                    </button>
                </div>
                
                <!-- Sonuç İstatistiği -->
                <div class="filter-stats">
                    <span id="filterResultCount">0</span> / <span id="filterTotalCount">0</span> log gösteriliyor
                </div>
            </div>
        </div>
        
        <!-- Toggle Button (Sabit, ekranın sağında) -->
        <button id="logFilterToggleBtn" class="log-filter-toggle-btn" onclick="toggleLogFilterPanel()">
            <span class="toggle-icon">🔍</span>
            <span class="toggle-text">Filtrele</span>
            <span class="filter-badge" id="filterBadge" style="display: none;">0</span>
        </button>
    `;
    
    return html;
}

/**
 * Component seçeneklerini render et
 */
function renderComponentOptions() {
    const state = window.logFilterState;
    const components = state.availableOptions.components;
    
    if (components.length === 0) {
        return `
            <div class="empty-state">
                <div class="empty-state-icon">📦</div>
                <div class="empty-state-title">Component Bilgisi Yok</div>
                <div class="empty-state-description">
                    Bu analizde component bilgisi bulunmuyor.
                    Log formatı component içermiyor olabilir.
                </div>
                <div class="empty-state-hint">
                    💡 <strong>İpucu:</strong> OpenSearch ve MongoDB logları genellikle component içerir.
                </div>
            </div>
        `;
    }
    
    return components.map(comp => {
        const isActive = state.activeFilters.components.includes(comp);
        return `
            <label class="filter-checkbox">
                <input 
                    type="checkbox" 
                    value="${window.escapeHtml(comp)}"
                    ${isActive ? 'checked' : ''}
                    onchange="toggleFilterOption('component', '${window.escapeHtml(comp)}')"
                >
                <span>${window.escapeHtml(comp)}</span>
            </label>
        `;
    }).join('');
}

/**
 * Severity seçeneklerini render et
 */
function renderSeverityOptions() {
    const state = window.logFilterState;
    const severities = state.availableOptions.severities;

    if (severities.length === 0) {
        return `
            <div class="empty-state">
                <div class="empty-state-icon">⚠️</div>
                <div class="empty-state-title">Severity Bilgisi Yok</div>
                <div class="empty-state-description">
                    Bu analizde severity seviyesi hesaplanamadı.
                    Tüm anomaliler benzer kritiklik seviyesinde olabilir.
                </div>
                <div class="empty-state-hint">
                    💡 <strong>İpucu:</strong> ML modeli severity'yi otomatik hesaplar, 
                    az sayıda anomali olduğunda bu bilgi eksik olabilir.
                </div>
            </div>
        `;
    }

    const severityColors = {
        'CRITICAL': '#e74c3c',
        'HIGH': '#e67e22',
        'MEDIUM': '#f39c12',
        'LOW': '#3498db',
        'INFO': '#95a5a6'
    };

    return severities.map(sev => {
        const isActive = state.activeFilters.severities.includes(sev);
        const color = severityColors[sev] || '#95a5a6';
        return `
            <label class="filter-checkbox">
                <input 
                    type="checkbox" 
                    value="${window.escapeHtml(sev)}"
                    ${isActive ? 'checked' : ''}
                    onchange="toggleFilterOption('severity', '${window.escapeHtml(sev)}')"
                >
                <span class="severity-label" style="color: ${color}">
                    ${window.escapeHtml(sev)}
                </span>
            </label>
        `;
    }).join('');
}

/**
 * Host seçeneklerini render et
 */
function renderHostOptions() {
    const state = window.logFilterState;
    const hosts = state.availableOptions.hosts;
    
    if (hosts.length === 0) {
        return `
            <div class="empty-state">
                <div class="empty-state-icon">🖥️</div>
                <div class="empty-state-title">Host Bilgisi Yok</div>
                <div class="empty-state-description">
                    Bu analizde host/sunucu bilgisi bulunmuyor.
                    Tek sunucu analizi veya host bilgisi eksik olabilir.
                </div>
                <div class="empty-state-hint">
                    💡 <strong>İpucu:</strong> Cluster analizi yapıldığında 
                    birden fazla host görebilirsiniz.
                </div>
            </div>
        `;
    }
    
    return hosts.map(host => {
        const isActive = state.activeFilters.hosts.includes(host);
        return `
            <label class="filter-checkbox">
                <input 
                    type="checkbox" 
                    value="${window.escapeHtml(host)}"
                    ${isActive ? 'checked' : ''}
                    onchange="toggleFilterOption('host', '${window.escapeHtml(host)}')"
                >
                <span>${window.escapeHtml(host)}</span>
            </label>
        `;
    }).join('');
}

// ============================================
// FILTER MANTIK FONKSİYONLARI
// ============================================


/**
 * Filter seçeneğini aç/kapat
 */
function toggleFilterOption(type, value) {
    const state = window.logFilterState;
    
    // Type'a göre doğru filter key'ini belirle
    const filterKeyMap = {
        'component': 'components',
        'severity': 'severities',
        'host': 'hosts'
    };
    
    const filterKey = filterKeyMap[type];
    
    if (!filterKey) {
        console.error(`Unknown filter type: ${type}`);
        return;
    }
    
    const filterArray = state.activeFilters[filterKey];
    
    if (!filterArray) {
        console.error(`Filter array not found for key: ${filterKey}`);
        return;
    }
    
    const index = filterArray.indexOf(value);
    if (index > -1) {
        filterArray.splice(index, 1); // Kaldır
    } else {
        filterArray.push(value); // Ekle
    }
    
    console.log(`Filter toggled: ${type} = ${value}`, filterArray);
}

/**
 * Filtreleri uygula
 */
function applyLogFilters() {
    console.log('Applying log filters...');
    
    const state = window.logFilterState;
    const filters = state.activeFilters;
    
    // Arama pattern'ini güncelle
    const searchInput = document.getElementById('filterSearchInput');
    if (searchInput) {
        filters.searchPattern = searchInput.value;
    }
    
    // Regex toggle'ı güncelle
    const regexToggle = document.getElementById('filterRegexToggle');
    if (regexToggle) {
        filters.useRegex = regexToggle.checked;
    }
    
    // Filtreleme işlemi
    let filtered = [...state.originalAnomalies];
    
    // Component filtresi
    if (filters.components.length > 0) {
        filtered = filtered.filter(anomaly => 
            filters.components.includes(anomaly.component)
        );
    }
    
    // Severity filtresi
    if (filters.severities.length > 0) {
        filtered = filtered.filter(anomaly => 
            filters.severities.includes(anomaly.severity_level)
        );
    }
    
    // Host filtresi
    if (filters.hosts.length > 0) {
        filtered = filtered.filter(anomaly => 
            filters.hosts.includes(anomaly.host)
        );
    }
    
    // Metin/Regex arama
    if (filters.searchPattern.trim()) {
        if (filters.useRegex) {
            // Önce pattern'i validate et
            if (!isValidRegexPattern(filters.searchPattern)) {
                console.error('Invalid regex pattern detected in applyLogFilters');
                window.showNotification('❌ Geçersiz regex pattern! Lütfen düzeltin.', 'error');
                
                // Validation mesajını tetikle
                validateRegexPattern();
                return;
            }
            
            try {
                const regex = new RegExp(filters.searchPattern, 'i');
                filtered = filtered.filter(anomaly => 
                    regex.test(anomaly.message || '')
                );
            } catch (e) {
                console.error('Unexpected regex error:', e);
                window.showNotification('Regex işlenirken hata oluştu', 'error');
                return;
            }
        } else {
            const searchLower = filters.searchPattern.toLowerCase();
            filtered = filtered.filter(anomaly => 
                (anomaly.message || '').toLowerCase().includes(searchLower)
            );
        }
    }
    
    // Sonuçları güncelle
    state.filteredAnomalies = filtered;
    
    console.log(`Filtered: ${filtered.length} / ${state.originalAnomalies.length} anomalies`);
    
    // UI'ı güncelle
    updateFilteredAnomalyDisplay();
    updateFilterStats();
    updateActiveFilterTags();
    updateFilterBadge(); 
    
    window.showNotification(`${filtered.length} log filtrelendi`, 'success');
}

/**
 * Filtreleri temizle
 */
function clearLogFilters() {
    console.log('Clearing all filters...');
    
    const state = window.logFilterState;
    state.activeFilters = {
        components: [],
        severities: [],
        hosts: [],
        searchPattern: '',
        useRegex: false
    };
    
    state.filteredAnomalies = [...state.originalAnomalies];
    
    // Input'ları temizle
    const searchInput = document.getElementById('filterSearchInput');
    if (searchInput) searchInput.value = '';
    
    const regexToggle = document.getElementById('filterRegexToggle');
    if (regexToggle) regexToggle.checked = false;
    
    // Checkbox'ları temizle
    document.querySelectorAll('.filter-checkbox input[type="checkbox"]').forEach(cb => {
        cb.checked = false;
    });
    
    // UI'ı güncelle
    updateFilteredAnomalyDisplay();
    updateFilterStats();
    updateActiveFilterTags();
    updateFilterBadge(); // ← YENİ: Badge'i temizle

    window.showNotification('Tüm filtreler temizlendi', 'info');
}

/**
 * Filter panelini aç/kapat
 */
function toggleLogFilterPanel() {
    const state = window.logFilterState;
    state.isOpen = !state.isOpen;
    
    const panel = document.getElementById('logFilterPanel');
    if (panel) {
        if (state.isOpen) {
            panel.classList.add('open');
        } else {
            panel.classList.remove('open');
        }
    }
    
    console.log('Filter panel toggled:', state.isOpen);
}

// ============================================
// UI GÜNCELLEME FONKSİYONLARI
// ============================================

/**
 * Filtrelenmiş anomali listesini güncelle
 */
function updateFilteredAnomalyDisplay() {
    console.log('Updating filtered anomaly display...');
    
    const state = window.logFilterState;
    const container = document.getElementById('criticalAnomaliesList');
    
    if (!container) {
        console.warn('Anomaly list container not found');
        return;
    }
    
    // Mevcut listeyi temizle
    container.innerHTML = '';
    
    // Filtrelenmiş anomalileri göster
    state.filteredAnomalies.forEach(anomaly => {
        const severityColor = anomaly.severity_color || '#e74c3c';
        const severityLevel = anomaly.severity_level || 'HIGH';
        const severityScore = anomaly.severity_score || 0;
        
        const fullMessage = anomaly.message || 'No message available';
        const isLongMessage = fullMessage.length > 500;

        // YENİ: Aktif arama pattern'ini al
        const searchPattern = state.activeFilters.searchPattern;
        const useRegex = state.activeFilters.useRegex;
        const hasSearchPattern = searchPattern && searchPattern.trim();

        // YENİ: Eşleşme sayısını hesapla (istatistik için)
        let matchCount = 0;
        if (hasSearchPattern) {
            matchCount = countMatches(fullMessage, searchPattern, useRegex);
        }

        // YENİ: Mesajı vurgula (eğer arama varsa)
        let highlightedMessage = fullMessage;
        let highlightedPreview = fullMessage.substring(0, 500);

        if (hasSearchPattern) {
            highlightedMessage = highlightMatches(fullMessage, searchPattern, useRegex);
            highlightedPreview = highlightMatches(fullMessage.substring(0, 500), searchPattern, useRegex);
        } else {
            // Arama yoksa normal escape
            highlightedMessage = window.escapeHtml(fullMessage);
            highlightedPreview = window.escapeHtml(fullMessage.substring(0, 500));
        }

        let html = `
            <div class="critical-anomaly-card" style="--severity-color: ${severityColor}">
                <div class="anomaly-header-with-severity">
                    <div class="anomaly-info">
                        <span class="anomaly-time">${new Date(anomaly.timestamp).toLocaleString('tr-TR')}</span>
                        <span class="severity-badge ${severityLevel.toLowerCase()}">${severityLevel}</span>
                        <span class="severity-score-inline">${severityScore}/100</span>
                        ${anomaly.component ? `<span class="component-badge">${anomaly.component}</span>` : ''}
                        ${anomaly.host ? `<span class="host-badge">📍 ${anomaly.host}</span>` : ''}
                        ${matchCount > 0 ? `<span class="match-count-badge">🎯 ${matchCount} eşleşme</span>` : ''}
                    </div>
                </div>
                <div class="anomaly-content">
                    <div class="anomaly-main-message">
                        ${isLongMessage ? `
                            <div class="message-expandable">
                                <div class="message-preview">
                                    <pre class="log-message-pre">${highlightedPreview}...</pre>
                                </div>
                                <div class="message-full" style="display: none;">
                                    <pre class="log-message-pre">${highlightedMessage}</pre>
                                </div>
                                <button class="btn-expand" onclick="toggleMessageExpand(this)">
                                    Tam Mesajı Göster
                                </button>
                            </div>
                        ` : `
                            <pre class="log-message-pre">${highlightedMessage}</pre>
                        `}
                    </div>
                </div>
            </div>
        `;
        
        container.innerHTML += html;
    });
    
    console.log(`Displayed ${state.filteredAnomalies.length} filtered anomalies`);
}

/**
 * Filter istatistiklerini güncelle
 */
function updateFilterStats() {
    const state = window.logFilterState;
    
    const resultCount = document.getElementById('filterResultCount');
    const totalCount = document.getElementById('filterTotalCount');
    
    if (resultCount) resultCount.textContent = state.filteredAnomalies.length;
    if (totalCount) totalCount.textContent = state.originalAnomalies.length;
}

/**
 * Aktif filter tag'lerini güncelle
 */
function updateActiveFilterTags() {
    const state = window.logFilterState;
    const container = document.getElementById('activeFilterTags');
    
    if (!container) return;
    
    container.innerHTML = '';
    
    let hasFilters = false;
    
    // Component tags
    state.activeFilters.components.forEach(comp => {
        hasFilters = true;
        container.innerHTML += `<span class="filter-tag">📦 ${window.escapeHtml(comp)}</span>`;
    });
    
    // Severity tags
    state.activeFilters.severities.forEach(sev => {
        hasFilters = true;
        container.innerHTML += `<span class="filter-tag">⚠️ ${window.escapeHtml(sev)}</span>`;
    });
    
    // Host tags
    state.activeFilters.hosts.forEach(host => {
        hasFilters = true;
        container.innerHTML += `<span class="filter-tag">🖥️ ${window.escapeHtml(host)}</span>`;
    });
    
    // Search pattern tag
    if (state.activeFilters.searchPattern.trim()) {
        hasFilters = true;
        const icon = state.activeFilters.useRegex ? '🔧' : '🔎';
        container.innerHTML += `<span class="filter-tag">${icon} ${window.escapeHtml(state.activeFilters.searchPattern)}</span>`;
    }
    
    if (!hasFilters) {
        container.innerHTML = '<span class="no-filters">Aktif filtre yok</span>';
    }
}

// ============================================
// BAŞLATMA FONKSİYONU
// ============================================

/**
 * Filter sistemini başlat
 */
function initializeLogFilter(anomalies) {
    console.log('Initializing log filter system...', anomalies.length, 'anomalies');
    
    const state = window.logFilterState;
    
    // Orijinal anomalileri sakla
    state.originalAnomalies = anomalies;
    state.filteredAnomalies = [...anomalies];
    
    // Benzersiz seçenekleri çıkar
    const components = new Set();
    const severities = new Set();
    const hosts = new Set();
    
    anomalies.forEach(anomaly => {
        if (anomaly.component) components.add(anomaly.component);
        if (anomaly.severity_level) severities.add(anomaly.severity_level);
        if (anomaly.host) hosts.add(anomaly.host);
    });
    
    state.availableOptions.components = Array.from(components).sort();
    state.availableOptions.severities = Array.from(severities).sort();
    state.availableOptions.hosts = Array.from(hosts).sort();
    
    console.log('Filter options extracted:', {
        components: state.availableOptions.components.length,
        severities: state.availableOptions.severities.length,
        hosts: state.availableOptions.hosts.length
    });
}

// ============================================
// REGEX PATTERN YARDIMCI FONKSİYONU
// ============================================

/**
 * Regex pattern'i arama kutusuna uygula
 * @param {string} pattern - Uygulanacak regex pattern
 */
function applyRegexPattern(pattern) {
    console.log('🔍 [PATTERN] Applying regex pattern:', pattern);
    
    const searchInput = document.getElementById('filterSearchInput');
    const regexToggle = document.getElementById('filterRegexToggle');
    
    if (searchInput && regexToggle) {
        // Pattern'i input'a yaz
        searchInput.value = pattern;
        
        // Regex mode'u aktif et
        regexToggle.checked = true;
        
        // State'i güncelle
        const state = window.logFilterState;
        state.activeFilters.searchPattern = pattern;
        state.activeFilters.useRegex = true;
        
        // Input'a focus ver
        searchInput.focus();
        
        console.log('✅ [PATTERN] Pattern applied successfully');
        
        // Kullanıcıya bildirim
        window.showNotification(`Pattern uygulandı: ${pattern}`, 'info');
    } else {
        console.error('❌ [PATTERN] Search input or regex toggle not found');
    }
}

// ============================================
// BADGE COUNTER FONKSİYONU
// ============================================

/**
 * Aktif filtre sayısını hesapla ve badge'i güncelle
 */
function updateFilterBadge() {
    const state = window.logFilterState;
    const badge = document.getElementById('filterBadge');
    
    if (!badge) {
        console.warn('Filter badge element not found');
        return;
    }
    
    // Aktif filtre sayısını hesapla
    let activeCount = 0;
    
    // Component filtreleri
    activeCount += state.activeFilters.components.length;
    
    // Severity filtreleri
    activeCount += state.activeFilters.severities.length;
    
    // Host filtreleri
    activeCount += state.activeFilters.hosts.length;
    
    // Metin/Regex arama (eğer varsa)
    if (state.activeFilters.searchPattern.trim()) {
        activeCount += 1;
    }
    
    console.log('🔢 [BADGE] Active filter count:', activeCount);
    
    // Badge'i güncelle
    if (activeCount > 0) {
        badge.textContent = activeCount;
        badge.style.display = 'inline-flex';
        badge.classList.add('active');
        console.log('✅ [BADGE] Badge shown with count:', activeCount);
    } else {
        badge.style.display = 'none';
        badge.classList.remove('active');
        console.log('ℹ️ [BADGE] Badge hidden (no active filters)');
    }
    
    // Toggle button rengini güncelle (opsiyonel görsel feedback)
    const toggleBtn = document.getElementById('logFilterToggleBtn');
    if (toggleBtn) {
        if (activeCount > 0) {
            toggleBtn.classList.add('has-filters');
        } else {
            toggleBtn.classList.remove('has-filters');
        }
    }
}

// ============================================
// REGEX VALIDATION FONKSİYONU
// ============================================

/**
 * Regex pattern'i validate et ve görsel feedback ver
 */
function validateRegexPattern() {
    const searchInput = document.getElementById('filterSearchInput');
    const regexToggle = document.getElementById('filterRegexToggle');
    const validationDiv = document.getElementById('regexValidation');
    
    if (!searchInput || !regexToggle || !validationDiv) {
        return;
    }
    
    const pattern = searchInput.value.trim();
    const isRegexMode = regexToggle.checked;
    
    // Eğer regex mode değilse veya pattern boşsa, validation gösterme
    if (!isRegexMode || !pattern) {
        validationDiv.style.display = 'none';
        searchInput.classList.remove('valid', 'invalid');
        return;
    }
    
    // Regex pattern'i test et
    try {
        // Pattern'i compile et (syntax kontrolü)
        new RegExp(pattern);
        
        // Geçerli pattern
        validationDiv.style.display = 'flex';
        validationDiv.className = 'regex-validation valid';
        validationDiv.querySelector('.validation-icon').textContent = '✓';
        validationDiv.querySelector('.validation-message').textContent = 'Geçerli regex pattern';
        
        searchInput.classList.remove('invalid');
        searchInput.classList.add('valid');
        
        console.log('✅ [VALIDATION] Valid regex pattern:', pattern);
        
    } catch (error) {
        // Geçersiz pattern
        validationDiv.style.display = 'flex';
        validationDiv.className = 'regex-validation invalid';
        validationDiv.querySelector('.validation-icon').textContent = '✕';
        
        // Hata mesajını kullanıcı dostu yap
        let errorMessage = 'Geçersiz regex pattern';
        const errorStr = error.message.toLowerCase();
        
        if (errorStr.includes('unterminated character class')) {
            errorMessage = 'Karakter sınıfı kapatılmamış (] eksik)';
        } else if (errorStr.includes('unmatched')) {
            errorMessage = 'Eşleşmeyen parantez';
        } else if (errorStr.includes('nothing to repeat')) {
            errorMessage = 'Geçersiz tekrar operatörü (*, +, ?)';
        } else if (errorStr.includes('invalid group')) {
            errorMessage = 'Geçersiz grup yapısı';
        } else if (errorStr.includes('incomplete')) {
            errorMessage = 'Tamamlanmamış ifade';
        } else {
            errorMessage = `Syntax hatası: ${error.message}`;
        }
        
        validationDiv.querySelector('.validation-message').textContent = errorMessage;
        
        searchInput.classList.remove('valid');
        searchInput.classList.add('invalid');
        
        console.warn('❌ [VALIDATION] Invalid regex pattern:', pattern);
        console.warn('Error:', error.message);
    }
}

// ============================================
// REGEX VALIDATION FONKSİYONU
// ============================================

/**
 * Pattern geçerli mi kontrol et (filtreleme öncesi)
 */
function isValidRegexPattern(pattern) {
    try {
        new RegExp(pattern);
        return true;
    } catch (e) {
        return false;
    }
}


// ============================================
// MATCH HIGHLIGHTING FONKSİYONU
// ============================================

/**
 * Text içindeki regex eşleşmelerini vurgula
 * @param {string} text - Vurgulanacak text
 * @param {string} pattern - Regex pattern
 * @param {boolean} useRegex - Regex modu aktif mi?
 * @returns {string} HTML ile vurgulanmış text
 */
function highlightMatches(text, pattern, useRegex) {
    // Eğer pattern boş veya text yoksa, orijinal text'i döndür
    if (!text || !pattern || !pattern.trim()) {
        return window.escapeHtml(text || '');
    }
    
    // Önce text'i escape et (XSS koruması)
    let escapedText = window.escapeHtml(text);
    
    try {
        if (useRegex) {
            // Regex mode - Pattern'i kullan
            const regex = new RegExp(pattern, 'gi'); // global + case-insensitive
            const matches = text.match(regex);
            
            if (!matches || matches.length === 0) {
                return escapedText;
            }
            
            console.log(`🎨 [HIGHLIGHT] Found ${matches.length} matches for pattern: ${pattern}`);
            
            // Eşleşmeleri vurgula
            // Her benzersiz eşleşmeyi tek tek replace et
            const uniqueMatches = [...new Set(matches)];
            
            uniqueMatches.forEach(match => {
                // Escape edilmiş text içinde escape edilmiş match'i bul
                const escapedMatch = window.escapeHtml(match);
                const highlightedMatch = `<mark class="regex-highlight">${escapedMatch}</mark>`;
                
                // Global replace
                const matchRegex = new RegExp(escapedMatch.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi');
                escapedText = escapedText.replace(matchRegex, highlightedMatch);
            });
            
            return escapedText;
            
        } else {
            // Normal text search - case-insensitive
            const searchLower = pattern.toLowerCase();
            const textLower = text.toLowerCase();
            
            if (!textLower.includes(searchLower)) {
                return escapedText;
            }
            
            console.log(`🎨 [HIGHLIGHT] Text search match found: ${pattern}`);
            
            // Case-insensitive replace
            const regex = new RegExp(pattern.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi');
            const matches = text.match(regex);
            
            if (matches && matches.length > 0) {
                matches.forEach(match => {
                    const escapedMatch = window.escapeHtml(match);
                    const highlightedMatch = `<mark class="text-highlight">${escapedMatch}</mark>`;
                    
                    const matchRegex = new RegExp(escapedMatch.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g');
                    escapedText = escapedText.replace(matchRegex, highlightedMatch);
                });
            }
            
            return escapedText;
        }
    } catch (error) {
        console.warn('❌ [HIGHLIGHT] Error highlighting matches:', error);
        // Hata durumunda orijinal escaped text'i döndür
        return escapedText;
    }
}
// ============================================
// MATCH HIGHLIGHTING FONKSİYONU
// ============================================

/**
 * Eşleşme sayısını hesapla (istatistik için)
 * @param {string} text - Kontrol edilecek text
 * @param {string} pattern - Regex pattern
 * @param {boolean} useRegex - Regex modu aktif mi?
 * @returns {number} Eşleşme sayısı
 */
function countMatches(text, pattern, useRegex) {
    if (!text || !pattern || !pattern.trim()) {
        return 0;
    }
    
    try {
        if (useRegex) {
            const regex = new RegExp(pattern, 'gi');
            const matches = text.match(regex);
            return matches ? matches.length : 0;
        } else {
            const searchLower = pattern.toLowerCase();
            const textLower = text.toLowerCase();
            
            if (!textLower.includes(searchLower)) {
                return 0;
            }
            
            // Occurrence sayısını hesapla
            let count = 0;
            let pos = textLower.indexOf(searchLower);
            
            while (pos !== -1) {
                count++;
                pos = textLower.indexOf(searchLower, pos + 1);
            }
            
            return count;
        }
    } catch (error) {
        console.warn('Error counting matches:', error);
        return 0;
    }
}


// ============================================
// ADVANCED PATTERN LIBRARY RENDER
// ============================================

/**
 * Pattern library'yi render et
 */
function renderPatternLibrary() {
    const library = window.advancedPatternLibrary;
    
    let html = '<div class="pattern-library">';
    html += '<div class="pattern-library-header">';
    html += '<h4>📚 Gelişmiş Pattern Kütüphanesi</h4>';
    html += '<button class="btn-collapse-all" onclick="collapseAllPatternCategories()">Tümünü Daralt</button>';
    html += '</div>';
    
    // Her kategori için
    Object.keys(library).forEach((categoryKey, index) => {
        const category = library[categoryKey];
        const isFirstOpen = index === 0; // İlk kategori açık başlasın
        
        html += `
            <div class="pattern-category" data-category="${categoryKey}">
                <div class="pattern-category-header" onclick="togglePatternCategory('${categoryKey}')">
                    <div class="category-info">
                        <span class="category-icon">${category.icon}</span>
                        <span class="category-title">${category.title}</span>
                        <span class="category-count">(${category.patterns.length})</span>
                    </div>
                    <span class="category-toggle">${isFirstOpen ? '▼' : '▶'}</span>
                </div>
                <div class="pattern-category-description">${category.description}</div>
                <div class="pattern-category-body" style="display: ${isFirstOpen ? 'block' : 'none'};">
        `;
        
        // Kategori içindeki pattern'ler
        category.patterns.forEach(patternData => {
            const complexityClass = `complexity-${patternData.complexity}`;
            const complexityLabel = patternData.complexity === 'easy' ? 'Kolay' :
                                   patternData.complexity === 'medium' ? 'Orta' : 'İleri';
            
            html += `
                <div class="pattern-library-item">
                    <div class="pattern-item-header">
                        <div class="pattern-item-info">
                            <strong class="pattern-name">${patternData.name}</strong>
                            <span class="pattern-complexity ${complexityClass}">${complexityLabel}</span>
                        </div>
                        <button class="btn-use-pattern" 
                                onclick="applyLibraryPattern('${escapeForAttribute(patternData.pattern)}')">
                            Kullan
                        </button>
                    </div>
                    <div class="pattern-item-description">${patternData.description}</div>
                    <div class="pattern-item-pattern">
                        <code>${window.escapeHtml(patternData.pattern)}</code>
                    </div>
                    <div class="pattern-item-example">
                        <small>💡 Örnek: "${patternData.example}"</small>
                    </div>
                </div>
            `;
        });
        
        html += '</div></div>'; // pattern-category-body + pattern-category
    });
    
    html += '</div>'; // pattern-library
    
    return html;
}

/**
 * Pattern kategorisini aç/kapat
 */
function togglePatternCategory(categoryKey) {
    const category = document.querySelector(`[data-category="${categoryKey}"]`);
    if (!category) return;
    
    const body = category.querySelector('.pattern-category-body');
    const toggle = category.querySelector('.category-toggle');
    
    if (body.style.display === 'none') {
        body.style.display = 'block';
        toggle.textContent = '▼';
    } else {
        body.style.display = 'none';
        toggle.textContent = '▶';
    }
}

/**
 * Tüm kategorileri daralt
 */
function collapseAllPatternCategories() {
    document.querySelectorAll('.pattern-category-body').forEach(body => {
        body.style.display = 'none';
    });
    document.querySelectorAll('.category-toggle').forEach(toggle => {
        toggle.textContent = '▶';
    });
}

/**
 * Library'den pattern uygula
 */
function applyLibraryPattern(pattern) {
    console.log('📚 [LIBRARY] Applying pattern from library:', pattern);
    
    const searchInput = document.getElementById('filterSearchInput');
    const regexToggle = document.getElementById('filterRegexToggle');
    
    if (searchInput && regexToggle) {
        // Pattern'i input'a yaz
        searchInput.value = pattern;
        
        // Regex mode'u aktif et
        regexToggle.checked = true;
        
        // State'i güncelle
        const state = window.logFilterState;
        state.activeFilters.searchPattern = pattern;
        state.activeFilters.useRegex = true;
        
        // Validation tetikle
        validateRegexPattern();
        
        // Input'a focus ver
        searchInput.focus();
        
        // Scroll to input
        searchInput.scrollIntoView({ behavior: 'smooth', block: 'center' });
        
        console.log('✅ [LIBRARY] Pattern applied successfully');
        
        // Kullanıcıya bildirim
        window.showNotification(`✅ Pattern uygulandı. "Filtrele" butonuna tıklayın.`, 'success');
    }
}

/**
 * Pattern library'yi aç/kapat
 */
function togglePatternLibrary() {
    const wrapper = document.getElementById('patternLibraryWrapper');
    const button = document.querySelector('.btn-toggle-library');
    
    if (!wrapper || !button) return;
    
    if (wrapper.style.display === 'none') {
        wrapper.style.display = 'block';
        button.textContent = '📚 Pattern Kütüphanesini Kapat';
        button.classList.add('active');
        
        // Scroll to library
        wrapper.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    } else {
        wrapper.style.display = 'none';
        button.textContent = '📚 Pattern Kütüphanesini Aç (25+ Hazır Pattern)';
        button.classList.remove('active');
    }
}

/**
 * HTML attribute için escape
 */
function escapeForAttribute(str) {
    return str.replace(/'/g, "\\'").replace(/"/g, '&quot;');
}

// ============================================
// GET ACTIVE FILTER COUNT FONKSİYONU
// ============================================

/**
 * Aktif filtre sayısını al (diğer fonksiyonlar için)
 */
function getActiveFilterCount() {
    const state = window.logFilterState;
    let count = 0;
    
    count += state.activeFilters.components.length;
    count += state.activeFilters.severities.length;
    count += state.activeFilters.hosts.length;
    
    if (state.activeFilters.searchPattern.trim()) {
        count += 1;
    }
    
    return count;
}

// ============================================
// GLOBAL ERİŞİM İÇİN WINDOW'A ATAMA
// ============================================
window.renderLogFilterPanel = renderLogFilterPanel;
window.toggleFilterOption = toggleFilterOption;
window.applyLogFilters = applyLogFilters;
window.clearLogFilters = clearLogFilters;
window.toggleLogFilterPanel = toggleLogFilterPanel;
window.updateFilteredAnomalyDisplay = updateFilteredAnomalyDisplay;
window.updateFilterStats = updateFilterStats;
window.updateActiveFilterTags = updateActiveFilterTags;
window.initializeLogFilter = initializeLogFilter;
window.applyRegexPattern = applyRegexPattern;
window.updateFilterBadge = updateFilterBadge;
window.getActiveFilterCount = getActiveFilterCount;
window.validateRegexPattern = validateRegexPattern;
window.isValidRegexPattern = isValidRegexPattern;
window.highlightMatches = highlightMatches;
window.countMatches = countMatches;
window.renderPatternLibrary = renderPatternLibrary; 
window.togglePatternCategory = togglePatternCategory; 
window.collapseAllPatternCategories = collapseAllPatternCategories; 
window.applyLibraryPattern = applyLibraryPattern; 
window.togglePatternLibrary = togglePatternLibrary; 


console.log('✅ Log filter module loaded successfully');