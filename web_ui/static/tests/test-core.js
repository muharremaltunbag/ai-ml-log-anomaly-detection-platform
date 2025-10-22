/**
 * Core Module Tests
 */

function runCoreTests() {
    const T = TestSuite;
    
    // Test 1: Global değişkenler mevcut mu?
    T.assert(window.apiKey !== undefined, 'window.apiKey exists');
    T.assert(window.isConnected !== undefined, 'window.isConnected exists');
    T.assert(window.selectedDataSource !== undefined, 'window.selectedDataSource exists');
    T.assert(window.currentSessionId !== undefined, 'window.currentSessionId exists');
    
    // Test 2: Sabitler mevcut mu?
    T.assert(window.HISTORY_KEY !== undefined, 'HISTORY_KEY constant exists');
    T.assert(window.MAX_HISTORY_ITEMS !== undefined, 'MAX_HISTORY_ITEMS constant exists');
    T.assert(window.API_BASE !== undefined, 'API_BASE constant exists');
    T.assert(window.API_ENDPOINTS !== undefined, 'API_ENDPOINTS object exists');
    
    // Test 3: API Endpoints doğru tanımlanmış mı?
    T.assert(window.API_ENDPOINTS.query !== undefined, 'API query endpoint exists');
    T.assert(window.API_ENDPOINTS.analyzeLog !== undefined, 'API analyzeLog endpoint exists');
    T.assert(window.API_ENDPOINTS.analyzeCluster !== undefined, 'API analyzeCluster endpoint exists');
    
    // Test 4: Fonksiyonlar mevcut ve çalışıyor mu?
    T.assertFunction(window.initializeElements, 'initializeElements is a function');
    T.assertFunction(window.updateApiKey, 'updateApiKey is a function');
    T.assertFunction(window.updateConnectionStatus, 'updateConnectionStatus is a function');
    T.assertFunction(window.updateDataSource, 'updateDataSource is a function');
    
    // Test 5: Fonksiyon çalışma testi
    const testKey = 'test-api-key-123';
    window.updateApiKey(testKey);
    T.assertEquals(window.apiKey, testKey, 'updateApiKey updates the API key correctly');
    
    window.updateConnectionStatus(true);
    T.assertEquals(window.isConnected, true, 'updateConnectionStatus updates connection status');
    
    const testSource = 'test_source';
    window.updateDataSource(testSource);
    T.assertEquals(window.selectedDataSource, testSource, 'updateDataSource updates data source');
}