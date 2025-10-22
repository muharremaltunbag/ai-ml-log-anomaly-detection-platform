/**
 * Performance Module Tests
 */

function runPerformanceTests() {
    const T = TestSuite;
    
    // Test 1: Performance fonksiyonları mevcut mu?
    T.assertFunction(window.displayPerformanceAnalysis, 'displayPerformanceAnalysis is a function');
    T.assertFunction(window.renderPerformanceScore, 'renderPerformanceScore is a function');
    T.assertFunction(window.renderExecutionMetrics, 'renderExecutionMetrics is a function');
    T.assertFunction(window.renderExecutionTree, 'renderExecutionTree is a function');
    T.assertFunction(window.renderTreeNode, 'renderTreeNode is a function');
    T.assertFunction(window.renderImprovementEstimate, 'renderImprovementEstimate is a function');
    T.assertFunction(window.renderRecommendations, 'renderRecommendations is a function');
    T.assertFunction(window.attachPerformanceEventListeners, 'attachPerformanceEventListeners is a function');
    
    // Test 2: Render fonksiyonları HTML döndürüyor mu?
    const mockScoreData = {
        score: 75,
        level: 'Good',
        detailed_scores: {
            time: 20,
            efficiency: 25,
            index: 20,
            result_size: 10
        }
    };
    
    const scoreHtml = window.renderPerformanceScore(mockScoreData);
    T.assert(typeof scoreHtml === 'string', 'renderPerformanceScore returns string');
    T.assert(scoreHtml.includes('performance-score-section'), 'Score HTML contains expected class');
    T.assert(scoreHtml.includes('75'), 'Score HTML contains score value');
    
    // Test 3: Execution metrics render testi
    const mockStats = {
        execution_time_ms: 150,
        total_docs_examined: 5000,
        total_keys_examined: 10000,
        docs_returned: 50,
        efficiency_percent: 65
    };

    const metricsHtml = window.renderExecutionMetrics(mockStats);
    T.assert(typeof metricsHtml === 'string', 'renderExecutionMetrics returns string');
    T.assert(metricsHtml.includes('150ms'), 'Metrics HTML contains execution time');

    // DÜZELTİLMİŞ: Türkçe locale formatting için kontrol
    T.assert(
        metricsHtml.includes('5,000') || 
        metricsHtml.includes('5000') || 
        metricsHtml.includes('5.000'), // Türkçe format
        'Metrics HTML contains docs examined'
    );
    
    // Test 4: Tree node render testi
    const mockTreeNode = {
        stage: 'IXSCAN',
        index_name: 'test_index',
        docs_examined: 100,
        keys_examined: 200,
        execution_time: 50,
        children: []
    };
    
    const treeHtml = window.renderTreeNode(mockTreeNode);
    T.assert(typeof treeHtml === 'string', 'renderTreeNode returns string');
    T.assert(treeHtml.includes('IXSCAN'), 'Tree HTML contains stage name');
    T.assert(treeHtml.includes('test_index'), 'Tree HTML contains index name');
}