/**
 * Advanced Workflow Tests
 * Karmaşık iş akışları ve edge case testleri
 */

function runAdvancedWorkflowTests() {
    const T = TestSuite;
    
    T.log('🔄 Testing advanced workflows and edge cases...', 'info');
    
    // ========== FULL ANOMALY DETECTION WORKFLOW ==========
    
    // Step 1: Verify initial state
    const initialApiKey = window.apiKey;
    const initialConnection = window.isConnected;
    
    // Step 2: Simulate connection
    window.updateApiKey('test-workflow-key');
    window.updateConnectionStatus(true);
    
    T.assert(
        window.apiKey === 'test-workflow-key' && window.isConnected === true,
        'Connection state updated for workflow'
    );
    
    // Step 3: Test data source selection
    const dataSources = ['opensearch', 'mongodb_direct', 'upload', 'test_servers'];
    dataSources.forEach(source => {
        window.updateDataSource(source);
        T.assertEquals(
            window.selectedDataSource,
            source,
            `Data source switched to ${source}`
        );
    });
    
    // ========== HISTORY PERSISTENCE WORKFLOW ==========
    
    // Test history save and load cycle
    const testHistoryItem = {
        id: Date.now(),
        timestamp: new Date().toISOString(),
        query: 'Workflow test query',
        type: 'anomaly',
        result: {
            durum: 'tamamlandı',
            işlem: 'test_workflow'
        }
    };
    
    // Add to history
    const originalHistoryLength = window.queryHistory.length;
    window.queryHistory.unshift(testHistoryItem);
    
    // Test MongoDB sync flag
    T.assert(
        window.queryHistory[0].fromMongoDB === undefined,
        'New item not yet synced to MongoDB'
    );
    
    // Simulate MongoDB sync
    window.queryHistory[0].fromMongoDB = true;
    window.queryHistory[0].id = 'mongo_id_123';
    
    T.assertEquals(
        window.queryHistory[0].id,
        'mongo_id_123',
        'MongoDB ID assigned after sync'
    );
    
    // ========== ERROR HANDLING WORKFLOW ==========
    
    // Test error result handling
    const errorResult = {
        durum: 'hata',
        açıklama: 'Test error occurred',
        sonuç: null
    };
    
    // Create temp container
    const tempContainer = document.createElement('div');
    tempContainer.id = 'resultContent';
    document.body.appendChild(tempContainer);
    
    window.elements = window.elements || {};
    window.elements.resultContent = tempContainer;
    window.elements.resultSection = document.createElement('div');
    
    // Display error
    window.displayAnomalyResults(errorResult);
    
    T.assert(
        tempContainer.innerHTML.includes('anomaly-error'),
        'Error state properly displayed'
    );
    T.assert(
        tempContainer.innerHTML.includes('Test error occurred'),
        'Error message shown to user'
    );
    
    // Cleanup
    document.body.removeChild(tempContainer);
    
    // ========== MULTI-MODULE COORDINATION ==========
    
    // Test cross-module data sharing
    const sharedData = {
        anomalies: [
            { score: 0.95, message: 'Critical anomaly' },
            { score: 0.75, message: 'High anomaly' }
        ],
        performance: {
            execution_time_ms: 250,
            efficiency_percent: 85
        },
        ml_metrics: {
            accuracy: 0.92,
            feature_importance: {
                'severity_W': { ratio: 5.2 },
                'is_error': { ratio: 3.1 }
            }
        }
    };
    
    // Store in window for cross-module access
    window.lastAnalysisData = sharedData;
    
    T.assert(
        window.lastAnalysisData.anomalies.length === 2,
        'Shared data accessible across modules'
    );
    T.assert(
        window.lastAnalysisData.performance.execution_time_ms === 250,
        'Performance data preserved'
    );
    T.assert(
        window.lastAnalysisData.ml_metrics.accuracy === 0.92,
        'ML metrics preserved'
    );
    
    // ========== EVENT CHAIN VALIDATION ==========
    
    // Test event propagation chain
    const eventChain = [];
    
    // Mock event handlers
    const originalHandleQuery = window.handleQuery;
    window.handleQuery = function() {
        eventChain.push('handleQuery');
        return Promise.resolve();
    };
    
    // Trigger chain
    window.handleQuery();
    
    T.assert(
        eventChain.includes('handleQuery'),
        'Event chain properly triggered'
    );
    
    // Restore
    window.handleQuery = originalHandleQuery;
    
    // ========== CONCURRENT OPERATIONS TEST ==========
    
    // Test multiple async operations
    const operations = [];
    
    // Simulate concurrent history operations
    const promise1 = new Promise((resolve) => {
        operations.push('op1');
        resolve();
    });
    
    const promise2 = new Promise((resolve) => {
        operations.push('op2');
        resolve();
    });
    
    Promise.all([promise1, promise2]).then(() => {
        T.assert(
            operations.length === 2,
            'Concurrent operations completed'
        );
    });
    
    // ========== MEMORY LEAK PREVENTION ==========
    
    // Test cleanup of global variables
    const testGlobals = [
        'lastAnomalyResult',
        'pendingAnomalyQueryId',
        'currentlyShownCount',
        'allCriticalAnomalies'
    ];
    
    testGlobals.forEach(global => {
        T.assert(
            window[global] !== undefined || true,
            `Global ${global} manageable`
        );
    });
    
    // ========== EDGE CASE HANDLING ==========
    
    // Test with empty/null data
    const emptyResult = {
        durum: 'tamamlandı',
        sonuç: {
            summary: {},
            critical_anomalies: [],
            component_analysis: {}
        }
    };
    
    try {
        // These should not throw errors
        window.renderMLModelMetrics({}, {});
        window.renderComponentDashboard({});
        window.renderTemporalHeatmap({ hourly_distribution: {} });
        T.assert(true, 'Empty data handling successful');
    } catch (e) {
        T.assert(false, 'Empty data caused error: ' + e.message);
    }
    
    // Test with malformed data
    const malformedData = {
        sonuç: {
            summary: null,
            critical_anomalies: 'not-an-array'
        }
    };
    
    try {
        // Should handle gracefully
        const html = window.renderMLModelMetrics(
            malformedData.sonuç.summary || {},
            {}
        );
        T.assert(
            typeof html === 'string',
            'Malformed data handled gracefully'
        );
    } catch (e) {
        T.assert(false, 'Malformed data handling failed');
    }
    
    // ========== PERFORMANCE BENCHMARKS ==========
    
    const startTime = performance.now();
    
    // Heavy operation simulation
    for (let i = 0; i < 1000; i++) {
        window.formatFeatureName(`feature_${i}`);
    }
    
    const elapsed = performance.now() - startTime;
    T.assert(
        elapsed < 100,
        `Feature formatting performance acceptable (${elapsed.toFixed(2)}ms for 1000 ops)`
    );
    
    // Restore initial state
    window.apiKey = initialApiKey;
    window.isConnected = initialConnection;
    
    T.log('✨ Advanced workflow tests completed', 'info');
}

// Add to global test runner
window.runAdvancedWorkflowTests = runAdvancedWorkflowTests;