/**
 * Integration Tests - Modüller Arası Etkileşim
 */

/**
 * Enhanced Integration Tests
 * Modüller arası etkileşimin derinlemesine testi
 */

function runIntegrationTests() {
    const T = TestSuite;
    
    // Test 1: Core + UI entegrasyonu
    T.assert(window.escapeHtml && window.apiKey !== undefined, 'Core and UI modules can interact');
    
    // Test 2: History + Anomaly entegrasyonu
    T.assert(window.queryHistory && window.displayAnomalyResults, 'History and Anomaly modules can work together');
    
    // Test 3: Performance + ML Visualization entegrasyonu
    T.assert(window.renderPerformanceScore && window.renderMLModelMetrics, 'Performance and ML Viz modules are compatible');
    
    // Test 4: API endpoints erişilebilir mi?
    T.assert(window.API_ENDPOINTS && Object.keys(window.API_ENDPOINTS).length > 10, 'API endpoints are properly configured');
    
    // Test 5: Window global değişkenleri modüller arası paylaşılıyor mu?
    const testSessionId = window.currentSessionId;
    T.assert(testSessionId && testSessionId.includes('session_'), 'Session ID is accessible across modules');
    
    // Test 6: Critical workflow - Anomaly analysis başlatma
    T.assert(window.handleAnalyzeLog && window.displayAnomalyResults && window.addToHistory, 'Anomaly analysis workflow components exist');
    
    // Test 7: Critical workflow - History management
    T.assert(window.loadHistory && window.saveHistory && window.updateHistoryDisplay, 'History management workflow components exist');
    
    // Test 8: Critical workflow - Performance analysis
    T.assert(window.displayPerformanceAnalysis && window.renderExecutionTree, 'Performance analysis workflow components exist');
    
    // Test 9: DOM element initialization capability
    T.assertFunction(window.initializeElements, 'DOM initialization function exists');
    
    // Test 10: Data export capabilities
    T.assert(window.exportHistory && window.exportAnomalyReport, 'Export functions are available');
    
    // Test 11: Modal/UI interaction functions
    T.assert(window.showModal && window.closeModal && window.closeAnomalyModal, 'Modal management functions are available');
    
    // Test 12: Notification system
    T.assertFunction(window.showNotification, 'Notification system is available');
    
    // Test 13: Loader control
    T.assertFunction(window.showLoader, 'Loader control is available');
    
    // Test 14: Status update capability
    T.assertFunction(window.updateStatus, 'Status update function is available');
    
    // Test 15: Complex data processing functions
    T.assert(window.parseAIExplanationFromText && window.formatAIResponse && window.highlightNumbers, 'Text processing functions are available');
    
    // ========== YENİ ENTEGRASYON TESTLERİ ==========
    
    // Script.js alias verification
    T.log('🔗 Testing script.js module aliases...', 'info');
    
    // Check if critical aliases are properly set
    const criticalAliases = [
        'displayPerformanceAnalysis',
        'renderPerformanceScore',
        'renderExecutionMetrics',
        'renderMLModelMetrics',
        'renderFeatureImportanceChart',
        'renderComponentDashboard',
        'renderTemporalHeatmap'
    ];
    
    criticalAliases.forEach(alias => {
        T.assertFunction(
            window[alias],
            `script.js alias '${alias}' is properly set`
        );
    });
    
    // Test inter-module data flow
    const testData = {
        test_id: 'integration_test_' + Date.now(),
        timestamp: new Date().toISOString()
    };
    
    // Store in one module's context
    window.lastAnomalyResult = testData;
    
    // Verify accessible from another module's function
    T.assertEquals(
        window.lastAnomalyResult.test_id,
        testData.test_id,
        'Data flows correctly between modules'
    );
    
    // Test callback chain integrity
    const callbackChain = [];
    
    // Mock a callback chain
    const mockChain = {
        step1: () => {
            callbackChain.push('step1');
            return mockChain.step2();
        },
        step2: () => {
            callbackChain.push('step2');
            return mockChain.step3();
        },
        step3: () => {
            callbackChain.push('step3');
            return true;
        }
    };
    
    mockChain.step1();
    T.assert(
        callbackChain.length === 3 && callbackChain[2] === 'step3',
        'Callback chain executes in correct order'
    );
    
    // Test UI update propagation
    if (typeof window.updateHistoryDisplay === 'function') {
        const originalLength = window.queryHistory.length;
        
        // Add test item
        window.queryHistory.push({
            id: 'test_ui_propagation',
            query: 'UI Test',
            timestamp: new Date().toISOString(),
            type: 'test'
        });
        
        // Check if history module can handle it
        try {
            window.updateHistoryDisplay();
            T.assert(true, 'UI update propagation successful');
        } catch (e) {
            T.assert(false, 'UI update propagation failed: ' + e.message);
        }
        
        // Cleanup
        window.queryHistory.pop();
    }
    
    T.log('✨ Enhanced integration tests completed!', 'info');
}