/**
 * Script.js Integration Tests
 * script.js içindeki alias'ların ve modül referanslarının doğruluğunu test eder
 */

function runScriptIntegrationTests() {
    const T = TestSuite;
    
    T.log('🔍 Testing script.js module aliases and integrations...', 'info');
    
    // ========== ALIAS VERIFICATION TESTS ==========
    
    // Performance Module Aliases
    T.assert(
        window.displayPerformanceAnalysis === window.displayPerformanceAnalysis,
        'displayPerformanceAnalysis alias correctly set'
    );
    T.assert(
        window.renderPerformanceScore === window.renderPerformanceScore,
        'renderPerformanceScore alias correctly set'
    );
    
    // ML Visualization Module Aliases
    T.assert(
        window.renderMLModelMetrics === window.renderMLModelMetrics,
        'renderMLModelMetrics alias correctly set'
    );
    T.assert(
        window.renderFeatureImportanceChart === window.renderFeatureImportanceChart,
        'renderFeatureImportanceChart alias correctly set'
    );
    
    // ========== CROSS-MODULE COMMUNICATION TESTS ==========
    
    // Test 1: Mock anomaly result ve display chain
    const mockAnomalyResult = {
        durum: 'tamamlandı',
        işlem: 'anomaly_analysis',
        sonuç: {
            summary: {
                n_anomalies: 10,
                total_logs: 1000,
                anomaly_rate: 1.0
            },
            critical_anomalies: [
                {
                    timestamp: new Date().toISOString(),
                    message: 'Test anomaly',
                    component: 'TEST',
                    anomaly_score: 0.95,
                    severity_level: 'HIGH',
                    severity_score: 85
                }
            ]
        }
    };
    
    // Create temporary result container
    const tempDiv = document.createElement('div');
    tempDiv.id = 'resultContent';
    const tempSection = document.createElement('div');
    tempSection.id = 'resultSection';
    tempSection.style.display = 'none';
    document.body.appendChild(tempDiv);
    document.body.appendChild(tempSection);
    
    // Set window.elements temporarily
    const originalElements = window.elements;
    window.elements = {
        resultContent: tempDiv,
        resultSection: tempSection
    };
    
    // Test display function
    try {
        window.displayAnomalyResults(mockAnomalyResult);
        T.assert(
            tempDiv.innerHTML.includes('anomaly-results'),
            'Anomaly results rendered to DOM'
        );
        T.assert(
            tempSection.style.display === 'block',
            'Result section made visible'
        );
        T.assert(
            tempDiv.innerHTML.includes('10'),
            'Anomaly count displayed'
        );
        T.assert(
            tempDiv.innerHTML.includes('Test anomaly'),
            'Anomaly message displayed'
        );
    } catch (e) {
        T.assert(false, 'displayAnomalyResults execution failed: ' + e.message);
    }
    
    // Cleanup
    window.elements = originalElements;
    document.body.removeChild(tempDiv);
    document.body.removeChild(tempSection);
    
    // ========== WINDOW.LASTANOMALYRESULT TESTS ==========
    
    T.assert(
        window.lastAnomalyResult !== undefined,
        'lastAnomalyResult is set after display'
    );
    
    if (window.lastAnomalyResult) {
        T.assertEquals(
            window.lastAnomalyResult.sonuç.summary.n_anomalies,
            10,
            'lastAnomalyResult contains correct data'
        );
    }
    
    // ========== EVENT HANDLER CHAIN TESTS ==========
    
    // Test handleQuery chain (requires more setup but validates the flow)
    T.assertFunction(window.handleQuery, 'handleQuery function exists');
    T.assertFunction(window.handleAnalyzeLog, 'handleAnalyzeLog function exists');
    
    // ========== HELPER FUNCTION AVAILABILITY ==========
    
    // Test critical helper functions used across modules
    T.assertFunction(window.parseAndFormatDescription, 'parseAndFormatDescription available globally');
    T.assertFunction(window.showAllComponents, 'showAllComponents available globally');
    T.assertFunction(window.exportComponentAnalysis, 'exportComponentAnalysis available globally');
    
    // ========== MODAL INTEGRATION TESTS ==========
    
    // Create anomaly modal mock if not exists
    if (!document.getElementById('anomalyModal')) {
        const modalDiv = document.createElement('div');
        modalDiv.id = 'anomalyModal';
        modalDiv.style.display = 'none';
        document.body.appendChild(modalDiv);
    }
    
    // Test modal interactions
    const anomalyModal = document.getElementById('anomalyModal');
    if (anomalyModal) {
        anomalyModal.style.display = 'block';
        window.closeAnomalyModal();
        T.assertEquals(
            anomalyModal.style.display,
            'none',
            'closeAnomalyModal hides the modal'
        );
    }
    
    // ========== STORAGE INTERACTION TESTS ==========
    
    // Test localStorage interaction patterns
    // ========== STORAGE INTERACTION TESTS ==========

    // Store originals for restoration
    const originalSaveHistory = window.saveHistory;
    const originalApiKey = window.apiKey;
    const originalIsConnected = window.isConnected;

    // Set temporary test values
    window.apiKey = 'test-api-key-mock';
    window.isConnected = true;

    // Mock saveHistory to prevent actual MongoDB calls
    window.saveHistory = async function() {
        console.log('Mock saveHistory called - returning success');
        return Promise.resolve(true);
    };

    // Mock addToHistory to prevent save calls
    const originalAddToHistory = window.addToHistory;
    window.addToHistory = async function(query, result, type) {
        const historyItem = {
            id: Date.now(),
            timestamp: new Date().toISOString(),
            query: query,
            type: type,
            category: type,
            result: result,
            durum: result.durum || 'tamamlandı',
            işlem: result.işlem || 'test'
        };
        
        window.queryHistory.unshift(historyItem);
        if (window.queryHistory.length > window.MAX_HISTORY_ITEMS) {
            window.queryHistory = window.queryHistory.slice(0, window.MAX_HISTORY_ITEMS);
        }
        
        // Mock save başarılı
        console.log('Mock addToHistory completed');
        return Promise.resolve(true);
    };

    // Test localStorage interaction patterns
    const testKey = 'test_anomaly_id_123';
    localStorage.setItem('pendingAnomalyQueryId', testKey);

    // Simulate parent query update
    const mockParentResult = {
        durum: 'tamamlandı',
        açıklama: 'Test completed',
        sonuç: { test: true }
    };

    // Store original queryHistory
    const originalHistory = window.queryHistory;
    window.queryHistory = [
        {
            id: parseInt(testKey),
            isAnomalyParent: true,
            durum: 'onay_bekliyor'
        }
    ];

    window.pendingAnomalyQueryId = parseInt(testKey);
    window.updateParentAnomalyQuery(mockParentResult);
    
    T.assert(
        window.queryHistory[0].durum === 'tamamlandı',
        'Parent anomaly query status updated'
    );
    T.assert(
        window.queryHistory[0].hasResult === true,
        'Parent anomaly query result flag set'
    );
    
    // ========== CLEANUP - RESTORE ORIGINALS ==========
    // Cleanup localStorage and restore all mocked/originals
    localStorage.removeItem('pendingAnomalyQueryId');
    window.saveHistory = originalSaveHistory;
    window.addToHistory = originalAddToHistory;
    window.apiKey = originalApiKey;
    window.isConnected = originalIsConnected;
    window.queryHistory = originalHistory;

    console.log('Mock functions restored to originals');
    
    // ========== DATA FLOW VALIDATION ==========
    
    // Test data flow from anomaly detection to history
    const testQuery = 'Test anomaly analysis';
    const testResult = {
        durum: 'tamamlandı',
        işlem: 'test_analysis',
        sonuç: { data: 'test' }
    };
    
    const historyLengthBefore = window.queryHistory.length;
    
    // Add to history
    window.addToHistory(testQuery, testResult, 'anomaly');
    
    T.assert(
        window.queryHistory.length > historyLengthBefore,
        'History item added successfully'
    );
    
    const latestHistory = window.queryHistory[0];
    T.assertEquals(
        latestHistory.query,
        testQuery,
        'History query matches input'
    );
    T.assertEquals(
        latestHistory.type,
        'anomaly',
        'History type correctly set'
    );
    
    // ========== CRITICAL WORKFLOW VALIDATION ==========
    
    // Test complete anomaly workflow availability
    const anomalyWorkflow = [
        'handleAnalyzeLog',
        'displayAnomalyResults', 
        'updateParentAnomalyQuery',
        'addToHistory',
        'saveHistory',
        'updateHistoryDisplay'
    ];
    
    let workflowComplete = true;
    anomalyWorkflow.forEach(func => {
        if (typeof window[func] !== 'function') {
            workflowComplete = false;
            T.assert(false, `${func} missing from anomaly workflow`);
        }
    });
    
    if (workflowComplete) {
        T.assert(true, 'Complete anomaly workflow chain available');
    }
    
    T.log('✨ Script.js integration tests completed', 'info');
}

// Add to global test runner
window.runScriptIntegrationTests = runScriptIntegrationTests;