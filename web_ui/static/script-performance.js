// web_ui/static/script-performance.js
/**
 * MongoDB Performance Analysis Module
 * Performans analizi görselleştirme fonksiyonları
 */

(function() {
    'use strict';

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
                        <span class="highlight">${window.escapeHtml(result.koleksiyon)}</span>
                     </div>`;
        }
        
        // Performance analiz detayları
        if (result.sonuç) {
            const data = result.sonuç;
            
            // 1. Performans Skoru - YENİ
            if (data.performance_score) {
                html += renderPerformanceScore(data.performance_score);
            }
            
            // 2. Execution Metrikleri
            if (data.execution_stats) {
                html += renderExecutionMetrics(data.execution_stats);
            }
            
            // 3. Execution Tree
            if (data.execution_tree) {
                html += renderExecutionTree(data.execution_tree);
            }
            
            // 4. İyileştirme Tahmini
            if (data.improvement_estimate) {
                html += renderImprovementEstimate(data.improvement_estimate);
            }
        }
        
        // Açıklama metni
        if (result.açıklama) {
            html += '<div class="result-field performance-description">';
            html += '<h3>📋 Detaylı Analiz</h3>';
            html += `<pre class="analysis-text">${window.escapeHtml(result.açıklama)}</pre>`;
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
        
        window.elements.resultContent.innerHTML = html;
        window.elements.resultSection.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        
        // Event listener'ları ekle
        setTimeout(() => {
            attachPerformanceEventListeners();
        }, 100);
    }

    /**
     * Performans Skorunu Render Et
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
                html += `<li>${window.escapeHtml(reason)}</li>`;
            });
            html += '</ul>';
            html += '</div>';
        }
        
        html += '</div>';
        return html;
    }

    /**
     * Execution Metriklerini Render Et
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
     * Execution Tree'yi Render Et
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
     * Tree Node'u Render Et
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
            html += `<span class="index-name">(${window.escapeHtml(node.index_name)})</span>`;
        }
        
        if (node.children && node.children.length > 0) {
            html += `<span class="toggle-icon">▼</span>`;
        }
        
        html += '</div>';
        
        // Node detayları
        html += '<div class="node-details">';
        
        if (node.stage_info) {
            html += `<div class="stage-info">${window.escapeHtml(node.stage_info)}</div>`;
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
     * İyileştirme Tahminini Render Et
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
     * Önerileri Render Et
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
            html += `<span class="recommendation-content">${window.escapeHtml(content)}</span>`;
            html += '</div>';
        });
        
        html += '</div>';
        html += '</div>';
        
        return html;
    }

    /**
     * Performance Event Listener'ları Ekle
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

    // Global export
    window.displayPerformanceAnalysis = displayPerformanceAnalysis;
    window.renderPerformanceScore = renderPerformanceScore;
    window.renderExecutionMetrics = renderExecutionMetrics;
    window.renderExecutionTree = renderExecutionTree;
    window.renderTreeNode = renderTreeNode;
    window.renderImprovementEstimate = renderImprovementEstimate;
    window.renderRecommendations = renderRecommendations;
    window.attachPerformanceEventListeners = attachPerformanceEventListeners;

})();