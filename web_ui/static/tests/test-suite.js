/**
 * MongoDB Assistant Test Suite - Main Test Runner
 */

// Test Suite Global Variables
window.TestSuite = {
    results: [],
    totalTests: 0,
    passedTests: 0,
    failedTests: 0,
    startTime: null,
    currentModule: null,
    
    // Test assertion functions
    assert: function(condition, message) {
        this.totalTests++;
        if (condition) {
            this.passedTests++;
            this.log('✅ ' + message, 'pass');
            return true;
        } else {
            this.failedTests++;
            this.log('❌ ' + message, 'fail');
            return false;
        }
    },
    
    assertEquals: function(actual, expected, message) {
        const condition = actual === expected;
        const fullMessage = `${message} (Expected: ${expected}, Got: ${actual})`;
        return this.assert(condition, fullMessage);
    },
    
    assertNotNull: function(value, message) {
        return this.assert(value !== null && value !== undefined, message);
    },
    
    assertType: function(value, type, message) {
        const condition = typeof value === type;
        const fullMessage = `${message} (Expected type: ${type}, Got: ${typeof value})`;
        return this.assert(condition, fullMessage);
    },
    
    assertFunction: function(fn, message) {
        return this.assertType(fn, 'function', message);
    },
    
    // Logging functions
    log: function(message, type = 'info') {
        const result = {
            module: this.currentModule,
            message: message,
            type: type,
            timestamp: new Date().toISOString()
        };
        this.results.push(result);
        this.updateDisplay(result);
    },
    
    // Display update
    updateDisplay: function(result) {
        const resultsDiv = document.getElementById('test-results');
        if (!resultsDiv) return;
        
        // Module başlığını kontrol et
        let moduleDiv = document.getElementById(`module-${this.currentModule}`);
        if (!moduleDiv) {
            moduleDiv = document.createElement('div');
            moduleDiv.id = `module-${this.currentModule}`;
            moduleDiv.className = 'test-module';
            moduleDiv.innerHTML = `
                <div class="test-module-header">
                    <span class="module-name">${this.currentModule.toUpperCase()}</span>
                    <span class="module-status status-running">RUNNING</span>
                </div>
                <div class="test-items"></div>
            `;
            resultsDiv.appendChild(moduleDiv);
        }
        
        // Test sonucunu ekle
        const itemsDiv = moduleDiv.querySelector('.test-items');
        const testItem = document.createElement('div');
        testItem.className = `test-item test-${result.type}`;
        testItem.textContent = result.message;
        itemsDiv.appendChild(testItem);
        
        // Özet güncelle
        this.updateSummary();
    },
    
    updateSummary: function() {
        document.getElementById('total-tests').textContent = this.totalTests;
        document.getElementById('passed-tests').textContent = this.passedTests;
        document.getElementById('failed-tests').textContent = this.failedTests;
        
        if (this.startTime) {
            const elapsed = Date.now() - this.startTime;
            document.getElementById('test-time').textContent = elapsed + 'ms';
        }
    },
    
    // Test runner (ASYNC to support async tests)
    runModule: async function(moduleName, testFunction) {
        this.currentModule = moduleName;
        this.log(`🏁 Starting ${moduleName} tests...`, 'info');
        
        try {
            // AWAIT test function if it's async
            const result = testFunction();
            if (result && typeof result.then === 'function') {
                await result;
            }
            
            // Module durumunu güncelle
            const moduleDiv = document.getElementById(`module-${moduleName}`);
            if (moduleDiv) {
                const statusSpan = moduleDiv.querySelector('.module-status');
                const moduleTests = this.results.filter(r => r.module === moduleName);
                const hasFailed = moduleTests.some(r => r.type === 'fail');
                
                statusSpan.className = `module-status status-${hasFailed ? 'failed' : 'passed'}`;
                statusSpan.textContent = hasFailed ? 'FAILED' : 'PASSED';
            }
            
            this.log(`✨ Completed ${moduleName} tests`, 'info');
        } catch (error) {
            this.log(`💥 Error in ${moduleName}: ${error.message}`, 'fail');
            console.error(error);
        }
    },
    
    reset: function() {
        this.results = [];
        this.totalTests = 0;
        this.passedTests = 0;
        this.failedTests = 0;
        this.startTime = null;
        this.currentModule = null;
        
        const resultsDiv = document.getElementById('test-results');
        if (resultsDiv) {
            resultsDiv.innerHTML = '<p style="text-align: center; color: #666;">Test başlatılıyor...</p>';
        }
        
        this.updateSummary();
    }
};

// TestUtils - Simple test helper for all test modules
window.TestUtils = {
    test: async function(description, testFn) {
        console.log('🧪 Testing: ' + description);
        try {
            // Run the test function
            const result = testFn();
            if (result && typeof result.then === 'function') {
                // Handle async test - AWAIT it!
                await result;
            }
        } catch (error) {
            console.error('Test failed:', error);
            window.TestSuite.assert(false, description + ' - Error: ' + error.message);
        }
    },
    assert: function(condition, message) {
        return window.TestSuite.assert(condition, message);
    },
    assertEquals: function(actual, expected, message) {
        return window.TestSuite.assertEquals(actual, expected, message);
    },
    assertNotNull: function(value, message) {
        return window.TestSuite.assertNotNull(value, message);
    },
    assertType: function(value, type, message) {
        return window.TestSuite.assertType(value, type, message);
    }
};

// Global test functions
async function runAllTests() {
    TestSuite.reset();
    TestSuite.startTime = Date.now();
    
    // Her modülü sırayla çalıştır (ASYNC - sequential execution)
    await TestSuite.runModule('core', runCoreTests);
    await TestSuite.runModule('ui', runUITests);
    await TestSuite.runModule('history', runHistoryTests);
    await TestSuite.runModule('anomaly', runAnomalyTests);
    await TestSuite.runModule('performance', runPerformanceTests);
    await TestSuite.runModule('ml-visualization', runMLVisualizationTests);
    await TestSuite.runModule('integration', runIntegrationTests);
    
    // Final summary (AFTER all tests complete)
    const percentage = TestSuite.totalTests > 0 
        ? ((TestSuite.passedTests / TestSuite.totalTests) * 100).toFixed(1)
        : 0;
    
    TestSuite.log(`
        🎯 TEST TAMAMLANDI!
        Toplam: ${TestSuite.totalTests}
        Başarılı: ${TestSuite.passedTests}
        Başarısız: ${TestSuite.failedTests}
        Başarı Oranı: %${percentage}
    `, TestSuite.failedTests > 0 ? 'warn' : 'info');
}

// runModuleTests fonksiyonuna yeni case'ler ekleyin
async function runModuleTests(moduleName) {
    TestSuite.reset();
    TestSuite.startTime = Date.now();
    
    switch(moduleName) {
        case 'core':
            await TestSuite.runModule('core', runCoreTests);
            break;
        case 'ui':
            await TestSuite.runModule('ui', runUITests);
            break;
        case 'history':
            await TestSuite.runModule('history', runHistoryTests);
            break;
        case 'anomaly':
            await TestSuite.runModule('anomaly', runAnomalyTests);
            break;
        case 'performance':
            await TestSuite.runModule('performance', runPerformanceTests);
            break;
        case 'ml':
            await TestSuite.runModule('ml-visualization', runMLVisualizationTests);
            break;
        case 'integration':
            await TestSuite.runModule('integration', runIntegrationTests);
            break;

        // YENİ TEST MODÜL CASE'LERİ
        case 'script-integration':
            await TestSuite.runModule('script-integration', runScriptIntegrationTests);
            break;
        case 'ui-interaction':
            await TestSuite.runModule('ui-interaction', runUIInteractionTests);
            break;
        case 'workflows':
            await TestSuite.runModule('advanced-workflows', runAdvancedWorkflowTests);
            break;
    }
}

function clearResults() {
    TestSuite.reset();
    document.getElementById('test-results').innerHTML = 
        '<p style="text-align: center; color: #666;">Test sonuçları temizlendi.</p>';
}

// Console override for logging
(function() {
    const consoleDiv = document.getElementById('console-logs');
    const originalLog = console.log;
    const originalError = console.error;
    const originalWarn = console.warn;
    
    console.log = function(...args) {
        originalLog.apply(console, args);
        if (consoleDiv) {
            const log = document.createElement('div');
            log.className = 'console-log';
            log.textContent = '📝 ' + args.join(' ');
            consoleDiv.appendChild(log);
        }
    };
    
    console.error = function(...args) {
        originalError.apply(console, args);
        if (consoleDiv) {
            const log = document.createElement('div');
            log.className = 'console-error';
            log.textContent = '❌ ' + args.join(' ');
            consoleDiv.appendChild(log);
        }
    };
    
    console.warn = function(...args) {
        originalWarn.apply(console, args);
        if (consoleDiv) {
            const log = document.createElement('div');
            log.className = 'console-warn';
            log.textContent = '⚠️ ' + args.join(' ');
            consoleDiv.appendChild(log);
        }
    };
})();