/**
 * ML Visualization Module Tests
 */

function runMLVisualizationTests() {
    const T = TestSuite;
    
    // Test 1: ML Visualization fonksiyonları mevcut mu?
    T.assertFunction(window.renderMLModelMetrics, 'renderMLModelMetrics is a function');
    T.assertFunction(window.renderOnlineLearningStatus, 'renderOnlineLearningStatus is a function');
    T.assertFunction(window.renderComponentComparisonChart, 'renderComponentComparisonChart is a function');
    T.assertFunction(window.formatFeatureName, 'formatFeatureName is a function');
    T.assertFunction(window.getFeatureDescription, 'getFeatureDescription is a function');
    T.assertFunction(window.getFeatureInsight, 'getFeatureInsight is a function');
    T.assertFunction(window.renderFeatureImportanceChart, 'renderFeatureImportanceChart is a function');
    T.assertFunction(window.renderComponentDashboard, 'renderComponentDashboard is a function');
    T.assertFunction(window.getComponentIcon, 'getComponentIcon is a function');
    T.assertFunction(window.renderTemporalHeatmap, 'renderTemporalHeatmap is a function');
    T.assertFunction(window.analyzeTemporalPatterns, 'analyzeTemporalPatterns is a function');
    T.assertFunction(window.findConsecutiveHours, 'findConsecutiveHours is a function');
    T.assertFunction(window.detectRegularPattern, 'detectRegularPattern is a function');
    T.assertFunction(window.attachMLVisualizationListeners, 'attachMLVisualizationListeners is a function');
    T.assertFunction(window.renderAnomalyScoreDistribution, 'renderAnomalyScoreDistribution is a function');
    T.assertFunction(window.renderSeverityDistribution, 'renderSeverityDistribution is a function');
    
    // Test 2: Feature name formatting çalışıyor mu?
    T.assertEquals(
        window.formatFeatureName('severity_W'), 
        'Uyarı Seviyesi', 
        'formatFeatureName formats severity_W correctly'
    );
    T.assertEquals(
        window.formatFeatureName('is_rare_component'), 
        'Nadir Bileşen', 
        'formatFeatureName formats is_rare_component correctly'
    );
    
    // Test 3: Component icon mapping çalışıyor mu?
    T.assertEquals(window.getComponentIcon('STORAGE'), '💾', 'STORAGE component gets correct icon');
    T.assertEquals(window.getComponentIcon('NETWORK'), '🌐', 'NETWORK component gets correct icon');
    T.assertEquals(window.getComponentIcon('QUERY'), '🔍', 'QUERY component gets correct icon');
    T.assertEquals(window.getComponentIcon('UNKNOWN'), '📦', 'Unknown component gets default icon');
    
    // Test 4: ML metrics render testi
    const mockSummary = {
        n_anomalies: 150,
        total_logs: 10000,
        anomaly_rate: 1.5
    };
    const mockScoreStats = {
        min: 0.001,
        max: 0.999,
        mean: 0.5,
        std: 0.25
    };
    
    const metricsHtml = window.renderMLModelMetrics(mockSummary, mockScoreStats);
    T.assert(typeof metricsHtml === 'string', 'renderMLModelMetrics returns string');
    T.assert(metricsHtml.includes('ml-metrics-unified'), 'ML metrics HTML has expected class');
    T.assert(metricsHtml.includes('150'), 'ML metrics shows anomaly count');
    
    // Test 5: Temporal pattern analizi
    const mockHourlyData = {
        0: 10, 1: 5, 2: 3, 9: 50, 10: 60, 11: 55,
        14: 45, 15: 40, 18: 30, 22: 15, 23: 12
    };
    const mockPeakHours = [9, 10, 11, 14, 15];
    
    const patterns = window.analyzeTemporalPatterns(mockHourlyData, mockPeakHours);
    T.assert(Array.isArray(patterns), 'analyzeTemporalPatterns returns array');
    T.assert(patterns.length > 0, 'Temporal patterns detected');
    
    // Test 6: Consecutive hours detection
    const testHours = [9, 10, 11, 14, 15, 16, 20];
    const consecutive = window.findConsecutiveHours(testHours);
    T.assert(Array.isArray(consecutive), 'findConsecutiveHours returns array');
    T.assert(consecutive.length >= 1, 'Consecutive hour ranges found');
    T.assert(consecutive[0][0] === 9 && consecutive[0][1] === 11, 'First consecutive range is 9-11');
}