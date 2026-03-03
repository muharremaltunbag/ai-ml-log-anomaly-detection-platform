// web_ui/static/script-ml-visualization.js
/**
 * ML Model Visualization Module
 * Machine Learning görselleştirme fonksiyonları
 */

(function() {
    'use strict';

    /**
     * ML Model Metriklerini Render Et - SADELEŞTİRİLMİŞ VERSİYON
     */
    function renderMLModelMetrics(summary, scoreStats) {
        let html = '<div class="ml-metrics-unified">';
        html += '<h3>ML Model Performans Metrikleri</h3>';
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
                    </div>
                    <div class="ml-metric-details">
                        <div class="ml-metric-title">Detection Statistics</div>
                        <div class="ml-metric-primary-value">${summary.n_anomalies?.toLocaleString('tr-TR') || 0}</div>
                        <div class="ml-metric-secondary-info">
                            <span class="ml-metric-badge">
                                Total Logs: ${summary.total_logs?.toLocaleString('tr-TR') || 0}
                            </span>
                            <span class="ml-metric-badge ${summary.anomaly_rate > 5 ? 'warning' : 'success'}">
                                Detection Rate: %${summary.anomaly_rate?.toFixed(2) || 0}
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
                        </div>
                        <div class="ml-metric-details">
                            <div class="ml-metric-title">Online Learning Status</div>
                            <div class="ml-metric-primary-value">${onlineStatus.mode === 'incremental' ? 'Aktif' : 'Standart'}</div>
                            <div class="ml-metric-secondary-info">
                                ${onlineStatus.buffer_size_mb !== undefined ? `
                                    <span class="ml-metric-badge ${onlineStatus.buffer_size_mb > 500 ? 'warning' : ''}">
                                        Buffer: ${onlineStatus.buffer_size_mb.toFixed(2)} MB
                                    </span>
                                ` : ''}
                                ${onlineStatus.total_samples !== undefined ? `
                                    <span class="ml-metric-badge">
                                        Samples: ${onlineStatus.total_samples.toLocaleString('tr-TR')}
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

    /**
     * Online Learning Status Render Et
     */
    function renderOnlineLearningStatus(onlineStatus) {
        if (!onlineStatus) return '';
        
        let html = '<div class="online-learning-status-section">';
        html += '<h3>Online Learning Status</h3>';
        html += '<div class="online-status-grid">';
        
        // Mode göstergesi
        const mode = onlineStatus.mode || 'standard';
        const modeClass = mode === 'incremental' ? 'active' : 'inactive';
        html += `
            <div class="online-status-card ${modeClass}">
                <div class="status-icon"></div>
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
                    <div class="status-icon"></div>
                    <div class="status-content">
                        <div class="status-label">Buffer Size</div>
                        <div class="status-value">${onlineStatus.buffer_size_mb.toFixed(2)} MB</div>
                        ${onlineStatus.buffer_size_mb > 500 ? 
                            '<div class="status-warning">Yuksek bellek kullanimi</div>' : ''}
                    </div>
                </div>
            `;
        }
        
        // Total Historical Samples
        if (onlineStatus.total_samples !== undefined) {
            html += `
                <div class="online-status-card">
                    <div class="status-icon"></div>
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
                    <div class="status-icon"></div>
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
                    <div class="status-icon"></div>
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
                    <div class="status-icon"></div>
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
                <p><strong>Incremental Learning Aktif:</strong> Model, gecmis pattern'lari hatirlayarak yeni verilerle guncelleniyor.</p>
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
            insightHtml += '<div class="insight-badge critical">Kritik Gosterge</div>';
            insightHtml += '<div class="insight-text">Bu özellik neredeyse sadece anomalilerde görülüyor!</div>';
        } else if (ratio > 5) {
            insightHtml += '<div class="insight-badge high">Yuksek Onem</div>';
            insightHtml += '<div class="insight-text">Anomali tespitinde güçlü bir gösterge</div>';
        } else if (ratio > 2) {
            insightHtml += '<div class="insight-badge medium">Orta Onem</div>';
            insightHtml += '<div class="insight-text">Anomali göstergesi olarak değerli</div>';
        } else {
            insightHtml += '<div class="insight-badge low">Dusuk Onem</div>';
            insightHtml += '<div class="insight-text">Yardımcı gösterge</div>';
        }
        
        insightHtml += '</div>';
        return insightHtml;
    }

    /**
     * Feature Importance Chart Render Et - SADELEŞTİRİLMİŞ VERSİYON
     */
    function renderFeatureImportanceChart(featureImportance) {
        let html = '<div class="feature-importance-unified">';
        html += '<h3>Feature Importance Analysis</h3>';
        
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
                        Detayli Analiz Raporu
                    </button>
                    <button class="feature-action-btn" onclick="exportFeatureImportance()">
                        Feature Verilerini Indir
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
        html += '<h3>Component Bazli Anomali Dagilimi</h3>';
        
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
                <div class="summary-icon"></div>
                <div class="summary-value">${totalComponents}</div>
                <div class="summary-label">Toplam Component</div>
            </div>
            <div class="component-summary-card critical">
                <div class="summary-icon"></div>
                <div class="summary-value">${criticalComponents}</div>
                <div class="summary-label">Kritik Component</div>
            </div>
            <div class="component-summary-card warning">
                <div class="summary-icon"></div>
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
            let criticalityIcon = '';

            if (anomalyRate > 20) {
                criticalityClass = 'critical';
                criticalityLabel = 'KRITIK';
                criticalityIcon = '';
            } else if (anomalyRate > 10) {
                criticalityClass = 'high';
                criticalityLabel = 'YUKSEK';
                criticalityIcon = '';
            } else if (anomalyRate > 5) {
                criticalityClass = 'medium';
                criticalityLabel = 'ORTA';
                criticalityIcon = '';
            } else if (anomalyRate > 2) {
                criticalityClass = 'low';
                criticalityLabel = 'DUSUK';
                criticalityIcon = '';
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
                            Bu component'teki tum loglar anomali olarak isaretlendi!
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
                        Tum Component'leri Goster
                    </button>
                </div>
            `;
        }
        
        html += '</div>';
        
        // Action buttons
        html += '<div class="component-actions">';
        html += `
            <button class="btn btn-primary" onclick="showAllComponents()">
                Detayli Component Analizi
            </button>
            <button class="btn btn-secondary" onclick="exportComponentAnalysis()">
                Component Verilerini Indir
            </button>
        `;
        html += '</div>';
        
        html += '</div>';
        return html;
    }

    /**
     * Get Component Icon
     */
    function getComponentIcon(component) {
        const iconMap = {
            'STORAGE': '',
            'NETWORK': '',
            'QUERY': '',
            'WRITE': '',
            'INDEX': '',
            'REPL': '',
            'COMMAND': '',
            'ACCESS': '',
            'CONTROL': '',
            'SHARDING': '',
            'CONNPOOL': '',
            'ELECTION': '',
            'RECOVERY': '',
            'ROLLBACK': '',
            'FTDC': ''
        };
        return iconMap[component] || '';
    }

    /**
     * Temporal Analysis Render Et - SADELEŞTİRİLMİŞ VERSİYON
     */
    function renderTemporalHeatmap(temporalAnalysis) {
        let html = '<div class="temporal-analysis-unified">';
        html += '<h3>Temporal Pattern Analysis</h3>';
        
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
                <div class="temporal-card-icon"></div>
                <div class="temporal-card-value">${totalAnomalies.toLocaleString('tr-TR')}</div>
                <div class="temporal-card-label">Toplam Anomali</div>
            </div>

            <div class="temporal-summary-card">
                <div class="temporal-card-icon"></div>
                <div class="temporal-card-value">${peakHours.length}</div>
                <div class="temporal-card-label">Yogun Saat</div>
            </div>

            <div class="temporal-summary-card">
                <div class="temporal-card-icon"></div>
                <div class="temporal-card-value">${maxValue}</div>
                <div class="temporal-card-label">En Yuksek</div>
            </div>
            
            <div class="temporal-summary-card">
                <div class="temporal-card-icon"></div>
                <div class="temporal-card-value">${avgPerHour.toFixed(1)}</div>
                <div class="temporal-card-label">Saat Başı Ort.</div>
            </div>
        `;
        
        html += '</div>';
        
        // Peak hours bilgisi
        if (peakHours.length > 0) {
            html += '<div class="peak-hours-section">';
            html += '<div class="peak-hours-title">';
            html += 'En Yogun Saatler';
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
        html += '<div class="patterns-title">Tespit Edilen Pattern\'ler</div>';
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

    /**
     * Temporal pattern analizi
     */
    function analyzeTemporalPatterns(hourlyData, peakHours) {
        const patterns = [];
        
        // İş saatleri analizi (09:00 - 18:00)
        const workHours = [9, 10, 11, 12, 13, 14, 15, 16, 17, 18];
        const workHourAnomalies = workHours.reduce((sum, h) => sum + (hourlyData[h] || 0), 0);
        const totalAnomalies = Object.values(hourlyData).reduce((sum, val) => sum + val, 0);
        const workHourPercentage = totalAnomalies > 0 ? (workHourAnomalies / totalAnomalies * 100).toFixed(1) : 0;
        
        if (workHourPercentage > 60) {
            patterns.push({
                icon: '',
                title: 'Is Saatleri Yogunlugu',
                description: `Anomalilerin %${workHourPercentage}'i iş saatlerinde (09:00-18:00) gerçekleşiyor. Bu, yüksek kullanım veya sistem yükü ile ilişkili olabilir.`
            });
        }
        
        // Gece saatleri analizi (00:00 - 06:00)
        const nightHours = [0, 1, 2, 3, 4, 5];
        const nightHourAnomalies = nightHours.reduce((sum, h) => sum + (hourlyData[h] || 0), 0);
        const nightHourPercentage = totalAnomalies > 0 ? (nightHourAnomalies / totalAnomalies * 100).toFixed(1) : 0;
        
        if (nightHourPercentage > 30) {
            patterns.push({
                icon: '',
                title: 'Gece Aktivitesi',
                description: `Anomalilerin %${nightHourPercentage}'i gece saatlerinde. Bakım işlemleri, batch job'lar veya anormal aktivite olabilir.`
            });
        }
        
        // Peak saat analizi
        if (peakHours.length > 0) {
            const consecutivePeaks = findConsecutiveHours(peakHours);
            if (consecutivePeaks.length > 0) {
                patterns.push({
                    icon: '',
                    title: 'Ardisik Yogun Saatler',
                    description: `${consecutivePeaks.map(range => `${range[0]}:00-${range[1]}:00`).join(', ')} arasında sürekli yüksek anomali. Sistemik bir sorun olabilir.`
                });
            }
        }
        
        // Düzenli pattern kontrolü
        const hourlyPattern = detectRegularPattern(hourlyData);
        if (hourlyPattern) {
            patterns.push({
                icon: '',
                title: hourlyPattern.title,
                description: hourlyPattern.description
            });
        }
        
        return patterns;
    }

    /**
     * Ardışık saatleri bulma
     */
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

    /**
     * Düzenli pattern tespiti
     */
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
        html += '<h3>Anomaly Score Distribution</h3>';
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

    /**
     * Severity Distribution Kompakt Liste
     */
    function renderSeverityDistribution(distribution) {
        let html = '<div class="severity-distribution-compact">';
        html += '<h3>Anomali Kritiklik Dagilimi</h3>';
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

    // Helper: toggleMLExpand
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

    // Global export
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

})();